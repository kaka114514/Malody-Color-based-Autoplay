"""主控制界面：布局、模式状态机、线程协调。"""

import logging
import queue
import shutil
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import List, Optional, Tuple

import win32gui
from PIL import ImageTk

import window_utils as wu
from autoplay import AutoplayEngine
from capture import grab_rect, sample_pixel
from color_matcher import ColorMatcher
from config import load_config, save_config
from icon_utils import extract_exe_icon
from input_hook import GlobalKeyHook, MouseBlocker, MouseReader
from overlay import BLUE, YELLOW, CursorDot, Overlay


BASE_DIR = Path(__file__).resolve().parent
MALODY_EXE = Path(r"D:\App\Game\Malody\malody.exe")
CONFIG_DIR = BASE_DIR / "configs"
CONFIG_PATH = CONFIG_DIR / "config.json"
LAST_CONFIG_FILE = CONFIG_DIR / ".last"

log = logging.getLogger("autoplay_debug")


def resolve_config_path(config_dir: Path = CONFIG_DIR) -> Path:
    """决定启动时加载的配置路径：优先 .last 记录的最近保存文件，其次默认 config.json。"""
    config_dir = Path(config_dir)
    config_dir.mkdir(parents=True, exist_ok=True)
    # 旧版本兼容：根目录 config.json 迁移到配置文件夹
    default_path = config_dir / "config.json"
    old_path = config_dir.parent / "config.json"
    if not default_path.exists() and old_path.exists():
        shutil.copy2(old_path, default_path)
    last_file = config_dir / ".last"
    if last_file.exists():
        try:
            last = Path(last_file.read_text(encoding="utf-8").strip())
            if last.is_file():
                return last
        except OSError:
            pass
    return default_path


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Malody Color-based Autoplay")
        self.root.resizable(True, True)
        # 使用 Malody 游戏图标作为程序图标
        if MALODY_EXE.exists():
            try:
                icon_img = extract_exe_icon(str(MALODY_EXE), 32)
                if icon_img is not None:
                    self._icon_photo = ImageTk.PhotoImage(icon_img)
                    self.root.iconphoto(True, self._icon_photo)
            except Exception:
                pass

        self._config_path = resolve_config_path()
        self.cfg = load_config(self._config_path)
        size = self.cfg.get("window_size", [0, 0])
        if isinstance(size, (list, tuple)) and len(size) == 2 and size[0] > 0 and size[1] > 0:
            geometry = f"{int(size[0])}x{int(size[1])}"
            pos = self.cfg.get("window_position", [-1, -1])
            if isinstance(pos, (list, tuple)) and len(pos) == 2 and pos[0] >= 0 and pos[1] >= 0:
                geometry += f"+{int(pos[0])}+{int(pos[1])}"
            self.root.geometry(geometry)
        self.rel_y = float(self.cfg["judgement_line_y"])
        self.judgement_px = int(self.cfg.get("judgement_line_px", 0))
        self.column_xs: List[float] = [c["x"] for c in self.cfg["columns"]]
        self.keys: List[str] = [c["key"] for c in self.cfg["columns"]]
        self.delay_ms = int(self.cfg["delay_ms"])
        self.min_hold_ms = int(self.cfg.get("min_hold_ms", 20))
        self.matcher = ColorMatcher(tolerance=int(self.cfg["tolerance"]))

        self.game_hwnd: Optional[int] = None
        self.game_rect: Optional[Tuple[int, int, int, int]] = None
        self.mode = "idle"
        self.eyedrop_active = False
        self.selected_col = -1
        self._overlay_visible = True
        self._frame_blue = False
        self._applying = False
        self.engine: Optional[AutoplayEngine] = None
        self._last_left = False
        self._closing = False
        self._msg_queue: queue.Queue = queue.Queue(maxsize=100)

        self.overlay = Overlay(root)
        self.overlay.hide()
        self.overlay.set_click_callback(self._on_overlay_click)
        self.dot = CursorDot()
        self.dot.hide()
        self._blocker = MouseBlocker(self._in_block_region, self._on_overlay_click)

        self._build_ui()
        self.freq_var.set("检测速度：请运行")
        self.root.update_idletasks()
        # 判定线高度按当前窗口实际高度换算像素显示，与输入值一致
        win_h = max(1, self.root.winfo_height())
        if self.judgement_px > 0:
            self.judgement_var.set(str(self.judgement_px))
        else:
            self.judgement_var.set(str(int(self.rel_y * win_h)))
        self._restore_matcher()
        self._refresh_swatches()

        self._hook = GlobalKeyHook(self.on_hotkey)
        self._hook.start()

        self.root.after(100, self._tick_tracking)
        self.root.after(30, self._tick_mouse)
        self.root.after(50, self._tick_messages)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.bind("<Button-1>", self._on_ui_click)
        self.status("就绪：先选择游戏窗口")

    # ---------- 界面构建 ----------
    def _build_ui(self) -> None:
        pad = dict(padx=8, pady=4)
        f = tk.Frame(self.root)
        f.pack(fill="x")

        tk.Button(f, text="选择游戏窗口（点击后点游戏窗口）", command=self.on_select_window).pack(fill="x", **pad)

        row = tk.Frame(f)
        row.pack(fill="x", **pad)
        tk.Label(row, text="判定线高度").pack(side="left")
        self.judgement_var = tk.StringVar(value=str(int(self.rel_y * 1000)))
        ent = tk.Entry(row, textvariable=self.judgement_var, width=8)
        ent.pack(side="left", padx=4)
        ent.bind("<Return>", lambda _e: self.apply_judgement_entry())
        self.judgement_var.trace_add("write", self._judgement_trace)
        tk.Button(row, text="设置(1上/2下/3结束)", command=self.on_judgement).pack(side="left", padx=4)

        row = tk.Frame(f)
        row.pack(fill="x", **pad)
        tk.Label(row, text="列数").pack(side="left")
        self.col_count_var = tk.StringVar(
            value=str(self.cfg.get("column_count", len(self.column_xs) or 4))
        )
        tk.Entry(row, textvariable=self.col_count_var, width=5).pack(side="left", padx=4)
        tk.Label(row, text="按键").pack(side="left")
        self.key_string_var = tk.StringVar(value=str(self.cfg.get("key_string", "")))
        ent = tk.Entry(row, textvariable=self.key_string_var, width=14)
        ent.pack(side="left", padx=4)
        ent.bind("<Return>", lambda _e: self.apply_key_string())
        self.key_string_var.trace_add("write", self._key_trace)
        tk.Button(row, text="设置列(1左/2右/3结束)", command=self.on_columns).pack(side="left", padx=4)

        row = tk.Frame(f)
        row.pack(fill="x", **pad)
        tk.Label(row, text="背景颜色").pack(side="left")
        tk.Button(row, text="吸色(按1激活,左键取色)", command=self.on_eyedrop_bg).pack(side="left", padx=4)
        self.bg_swatch_frame = tk.Frame(row)
        self.bg_swatch_frame.pack(side="left", padx=4)

        row = tk.Frame(f)
        row.pack(fill="x", **pad)
        tk.Label(row, text="按键颜色").pack(side="left")
        tk.Button(row, text="吸色(按1激活,左键取色)", command=self.on_eyedrop_key).pack(side="left", padx=4)
        self.key_swatch_frame = tk.Frame(row)
        self.key_swatch_frame.pack(side="left", padx=4)

        row = tk.Frame(f)
        row.pack(fill="x", **pad)
        tk.Label(row, text="延迟(ms)").pack(side="left")
        self.delay_var = tk.StringVar(value=str(self.delay_ms))
        ent = tk.Entry(row, textvariable=self.delay_var, width=8)
        ent.pack(side="left", padx=4)
        ent.bind("<Return>", lambda _e: self.apply_delay_entry())
        self.delay_var.trace_add("write", self._delay_trace)
        tk.Label(row, text="运行中 4=提前5ms 5=推后5ms").pack(side="left")

        row = tk.Frame(f)
        row.pack(fill="x", **pad)
        tk.Label(row, text="最短按压时长(ms)").pack(side="left")
        self.min_hold_var = tk.StringVar(value=str(self.min_hold_ms))
        ent = tk.Entry(row, textvariable=self.min_hold_var, width=5)
        ent.pack(side="left", padx=4)
        self.min_hold_var.trace_add("write", self._min_hold_trace)

        row = tk.Frame(f)
        row.pack(fill="x", pady=6)
        self.run_btn = tk.Button(row, text="运行", command=self.on_run, width=8)
        self.run_btn.pack(side="left", padx=8)
        self.pause_btn = tk.Button(row, text="暂停", command=self.on_pause, width=8, state="disabled")
        self.pause_btn.pack(side="left", padx=8)
        tk.Button(row, text="配置", command=self.on_save, width=8).pack(side="left", padx=8)
        tk.Button(row, text="恢复", command=self.on_restore, width=8).pack(side="left", padx=8)

        self.status_var = tk.StringVar(value="")
        self.freq_var = tk.StringVar(value="")
        tk.Label(f, textvariable=self.freq_var, anchor="w", justify="left", fg="#444444").pack(fill="x", **pad)
        self._status_label = tk.Label(f, textvariable=self.status_var, anchor="w", justify="left")
        self._status_label.pack(fill="x", **pad)
        self._hint_labels = [
        tk.Label(f, text="6 切换覆盖层显示 | 7 黄键/蓝键(采集模式)切换", anchor="w", justify="left", fg="#666666"),
        tk.Label(f, text="8 运行 | 9 暂停", anchor="w", justify="left", fg="#666666"),
        ]
        for lbl in self._hint_labels:
            lbl.pack(fill="x", **pad)
        # 窗口宽度变化时，长文字自动换行
        self.root.bind("<Configure>", self._on_resize)
        self.root.minsize(360, 260)

    def _on_resize(self, event) -> None:
        """状态栏与热键提示随窗口宽度自动换行。"""
        if not hasattr(self, "_status_label"):
            return
        wrap = max(100, event.width - 24)
        self._status_label.config(wraplength=wrap)
        for lbl in self._hint_labels:
            lbl.config(wraplength=wrap)

    def status(self, msg: str) -> None:
        """线程安全的状态栏更新（经消息队列转发到主线程）。"""
        try:
            self._msg_queue.put_nowait(("status", msg))
        except queue.Full:
            pass

    def _judgement_trace(self, *_args) -> None:
        if self._applying:
            return
        self._applying = True
        try:
            self.apply_judgement_entry()
        finally:
            self._applying = False

    def _key_trace(self, *_args) -> None:
        if self._applying:
            return
        self._applying = True
        try:
            self.apply_key_string()
        finally:
            self._applying = False

    def _delay_trace(self, *_args) -> None:
        if self._applying:
            return
        self._applying = True
        try:
            self.apply_delay_entry()
        finally:
            self._applying = False

    def _min_hold_trace(self, *_args) -> None:
        if self._applying:
            return
        self._applying = True
        try:
            self.apply_min_hold()
        finally:
            self._applying = False

    def apply_min_hold(self) -> None:
        try:
            self.min_hold_ms = max(0, int(self.min_hold_var.get()))
        except ValueError:
            return
        if self.engine:
            self.engine.set_min_hold(self.min_hold_ms)

    def _on_ui_click(self, _event) -> None:
        """点击按钮/空白处取消输入状态；点击输入框不打断输入。"""
        widget = _event.widget
        if isinstance(widget, tk.Entry):
            return
        self._cancel_eyedrop()
        self.root.focus_set()  # 输入框失焦，取消输入状态

    def _cancel_eyedrop(self) -> None:
        if self.eyedrop_active:
            self.eyedrop_active = False
            self.status("已取消吸管")

    def _on_overlay_click(self, sx: int, sy: int) -> None:
        """蓝框采集模式：点击被覆盖层捕获时，读取坐标与颜色。"""
        self._handle_collect_click(sx, sy)

    def _handle_collect_click(self, sx: int, sy: int) -> None:
        try:
            img = grab_rect((sx, sy, sx + 1, sy + 1))
            color = sample_pixel(img, 0, 0)
        except Exception as exc:
            self.status("读取颜色失败")
            return
        self.status(f"坐标 ({sx}, {sy}) 颜色值 {tuple(color)}")

    def _in_block_region(self, x: int, y: int) -> bool:
        if self.eyedrop_active:
            return False  # 吸管激活时放行点击，用于取色
        if not self.game_rect:
            return False
        left, top, right, bottom = self.game_rect
        return left <= x < right and top <= y < bottom

    def _tick_messages(self) -> None:
        try:
            while True:
                kind, payload = self._msg_queue.get_nowait()
                if kind == "status":
                    if payload.startswith("freq:"):
                        self.freq_var.set(f"检测速度：{payload[5:].strip()}")
                    elif payload.startswith("state:"):
                        self.status_var.set(payload[6:].strip())
                    else:
                        self.status_var.set(payload)
                elif kind == "hotkey":
                    self._handle_hotkey(payload)
                elif kind == "engine_stopped":
                    self.engine = None
                    self._reset_buttons()
                    self.freq_var.set("检测速度：请运行")
                    self.status_var.set(payload)
        except queue.Empty:
            pass
        if not self._closing:
            self.root.after(50, self._tick_messages)

    # ---------- 配置恢复 ----------
    def _restore_matcher(self) -> None:
        for c in self.cfg.get("background_colors", []):
            self.matcher.add_background(tuple(c))
        for c in self.cfg.get("key_colors", []):
            self.matcher.add_key(tuple(c))

    def _refresh_swatches(self) -> None:
        for frame in (self.bg_swatch_frame, self.key_swatch_frame):
            for w in frame.winfo_children():
                w.destroy()
        for i, c in enumerate(self.matcher.background_colors):
            tk.Button(
                self.bg_swatch_frame, bg="#%02x%02x%02x" % c, width=4,
                command=lambda idx=i: self._remove_bg(idx),
            ).pack(side="left", padx=1)
        for i, c in enumerate(self.matcher.key_colors):
            tk.Button(
                self.key_swatch_frame, bg="#%02x%02x%02x" % c, width=4,
                command=lambda idx=i: self._remove_key(idx),
            ).pack(side="left", padx=1)

    def _remove_bg(self, idx: int) -> None:
        self.matcher.remove_background(self.matcher.background_colors[idx])
        self._refresh_swatches()

    def _remove_key(self, idx: int) -> None:
        self.matcher.remove_key(self.matcher.key_colors[idx])
        self._refresh_swatches()

    # ---------- 窗口 ----------
    def on_select_window(self) -> None:
        self.mode = "select_window"
        self.status("请在游戏窗口上点击左键")

    def select_game_window(self, hwnd: int) -> None:
        log.info("select_game_window hwnd=%s own_root=%s own_overlay=%s",
                 hwnd, int(self.root.winfo_id()), self.overlay.hwnd)
        self.game_hwnd = hwnd
        # 按保存的像素高度换算判定线（游戏窗口尺寸确定后）
        rect = wu.get_window_rect(hwnd)
        if self.judgement_px > 0:
            h = max(1, rect[3] - rect[1])
            max_y = max(0.0, (h - 1) / h)
            self.rel_y = max(0.0, min(max_y, self.judgement_px / h))
            self.judgement_var.set(str(self.judgement_px))
        self._refresh_tracking()
        self.mode = "idle"
        log.info("after select: mode=%s game_hwnd=%s", self.mode, self.game_hwnd)
        self.status("已选择游戏窗口（黄色线框）")

    def _refresh_tracking(self) -> None:
        if not self.game_hwnd:
            return
        if wu.is_minimized(self.game_hwnd) or not wu.is_visible(self.game_hwnd):
            log.info("tracking: window hidden/minimized hwnd=%s minimized=%s visible=%s",
                     self.game_hwnd, wu.is_minimized(self.game_hwnd), wu.is_visible(self.game_hwnd))
            self.overlay.hide()
            return
        self.game_rect = wu.get_window_rect(self.game_hwnd)
        log.info("tracking: rect=%s overlay_visible=%s", self.game_rect,
                 bool(self.overlay.hwnd and win32gui.IsWindowVisible(self.overlay.hwnd)))
        if not self._overlay_visible:
            self.overlay.hide()
            return
        self.overlay.set_game_rect(self.game_rect)
        self.overlay.set_judgement_y(self.rel_y)
        self.overlay.set_columns(self.column_xs, self.selected_col)
        self.overlay.show()

    # ---------- 判定线 ----------
    def on_judgement(self) -> None:
        if not self.game_hwnd:
            messagebox.showwarning("提示", "请先选择游戏窗口")
            return
        self.mode = "judgement"
        self._refresh_tracking()
        self.status("判定线设置：1上移 2下移 左键选高度 3结束")

    def apply_judgement_entry(self) -> None:
        try:
            y = int(self.judgement_var.get())
        except ValueError:
            self.status("判定线高度请输入数字")
            return
        self._set_judgement_px(y)

    def _set_judgement_px(self, px: int) -> None:
        self.judgement_px = px
        if not self.game_rect:
            return
        h = max(1, self.game_rect[3] - self.game_rect[1])
        max_y = max(0.0, (h - 1) / h)
        self.rel_y = max(0.0, min(max_y, px / h))
        self.judgement_var.set(str(px))
        self.overlay.set_judgement_y(self.rel_y)

    def nudge_judgement(self, delta_px: int) -> None:
        if not self.game_rect:
            return
        h = max(1, self.game_rect[3] - self.game_rect[1])
        self.rel_y = max(0.0, min(1.0, self.rel_y + delta_px / h))
        self.judgement_px = int(self.rel_y * h)
        self.judgement_var.set(str(self.judgement_px))
        self.overlay.set_judgement_y(self.rel_y)

    # ---------- 列 ----------
    def on_columns(self) -> None:
        if not self.game_hwnd:
            messagebox.showwarning("提示", "请先选择游戏窗口")
            return
        if len(self.column_xs) == 0:
            self.column_xs = [0.5]
        self.mode = "columns"
        self.selected_col = max(0, len(self.column_xs) - 1)
        self._refresh_tracking()
        self.status("列设置：左键添加/选中 1左移 2右移 3结束")

    def apply_key_string(self) -> None:
        self.keys = self._parse_keys()
        if len(self.keys) != len(self.column_xs):
            self.status(f"按键数量({len(self.keys)})与列数({len(self.column_xs)})不匹配，已忽略")
            self.keys = []
        else:
            self.status("按键绑定已更新")

    def _parse_keys(self) -> List[str]:
        s = self.key_string_var.get().strip()
        if not s:
            return []
        if len(s) == len(self.column_xs):
            return list(s.upper())
        return [part.strip() for part in s.split() if part.strip()]

    def nudge_column(self, delta_px: int) -> None:
        if self.selected_col < 0 or not self.game_rect:
            return
        w = max(1, self.game_rect[2] - self.game_rect[0])
        self.column_xs[self.selected_col] = max(
            0.0, min(1.0, self.column_xs[self.selected_col] + delta_px / w)
        )
        self._refresh_tracking()

    # ---------- 吸色 ----------
    def on_eyedrop_bg(self) -> None:
        self.mode = "eyedrop_bg"
        self.status("吸管模式：按 1 激活，左键取色")

    def on_eyedrop_key(self) -> None:
        self.mode = "eyedrop_key"
        self.status("吸管模式：按 1 激活，左键取色")

    def activate_eyedrop(self) -> None:
        if self.eyedrop_active:
            return
        self.eyedrop_active = True
        self.status("吸管已激活，左键取色")

    def _pick_color(self) -> None:
        x, y = MouseReader.cursor_pos()
        try:
            img = grab_rect((x, y, x + 1, y + 1))
            color = sample_pixel(img, 0, 0)
        except Exception as exc:
            self.status("取色失败，请重试")
            return
        if self.mode == "eyedrop_bg":
            self.matcher.add_background(color)
        else:
            self.matcher.add_key(color)
        self.eyedrop_active = False
        self._refresh_swatches()
        self.status(f"已吸取颜色 {tuple(color)}，按 1 继续吸色")

    # ---------- 延迟 ----------
    def apply_delay_entry(self) -> None:
        try:
            self.delay_ms = int(self.delay_var.get())
        except ValueError:
            self.status("延迟请输入整数")
            return
        if self.engine:
            self.engine.set_delay(self.delay_ms)
        self.status(f"延迟已设为 {self.delay_ms} ms")

    def nudge_delay(self, delta_ms: int) -> None:
        self.delay_ms = self.delay_ms + delta_ms
        self.delay_var.set(str(self.delay_ms))
        if self.engine:
            self.engine.set_delay(self.delay_ms)
        self.status(f"延迟 {self.delay_ms} ms")

    # ---------- 运行 / 暂停 / 保存 ----------
    def _sorted_columns(self) -> List[Tuple[float, str]]:
        pairs = sorted(zip(self.column_xs, self.keys or self._parse_keys()))
        return [(x, k) for x, k in pairs if k]

    def on_run(self) -> None:
        errors = []
        if not self.game_hwnd:
            errors.append("请先选择游戏窗口")
        if not self.column_xs:
            errors.append("请先设置列")
        if not self._sorted_columns():
            errors.append("请设置按键绑定（与列数匹配）")
        if not self.matcher.background_colors:
            errors.append("请先吸取背景颜色")
        if not self.matcher.key_colors:
            errors.append("请先吸取按键颜色")
        if errors:
            messagebox.showwarning("提示", "\n".join(errors))
            return

        fg_ok = wu.set_foreground(self.game_hwnd)
        log.info("run: set_foreground=%s fg=%s game=%s",
                 fg_ok, win32gui.GetWindowText(win32gui.GetForegroundWindow()), self.game_hwnd)
        if not fg_ok:
            self.status("警告：未能自动置前游戏窗口，请点击一下游戏窗口后按 9 运行")
            return
        rel_points = [(x, self.rel_y) for x, _ in self._sorted_columns()]
        keys = [k for _, k in self._sorted_columns()]
        self.engine = AutoplayEngine(
            self.matcher, self.game_hwnd, keys, rel_points,
            self.delay_ms, min_hold_ms=self.min_hold_ms,
            on_log=self.status, on_stopped=self._on_engine_stopped,
        )
        self.engine.start()
        self.run_btn.config(state="disabled")
        self.pause_btn.config(state="normal")
        self._refresh_tracking()
        self.status("运行中…（按4/5调延迟）")

    def on_pause(self) -> None:
        if self.engine:
            self.engine.stop()
            self.engine = None
        self.freq_var.set("检测速度：请运行")
        self.run_btn.config(state="normal")
        self.pause_btn.config(state="disabled")
        self.overlay.show()
        self._refresh_tracking()
        self.status("已暂停")

    def _on_engine_stopped(self, msg: str) -> None:
        """检测线程回调：入队后由主线程恢复界面。"""
        try:
            self._msg_queue.put_nowait(("engine_stopped", msg))
        except queue.Full:
            pass

    def _reset_buttons(self) -> None:
        self.run_btn.config(state="normal")
        self.pause_btn.config(state="disabled")

    def _build_cfg(self) -> dict:
        sorted_cols = self._sorted_columns()
        if sorted_cols:
            columns = [{"x": x, "key": k} for x, k in sorted_cols]
        else:
            columns = [{"x": x, "key": k} for x, k in zip(self.column_xs, self.keys)]
        try:
            col_count = max(1, int(self.col_count_var.get()))
        except ValueError:
            col_count = len(columns)
        # 判定线像素：优先用当前像素值；否则按游戏窗口高度换算
        if self.judgement_px > 0:
            judgement_px = self.judgement_px
        elif self.game_rect:
            h = max(1, self.game_rect[3] - self.game_rect[1])
            judgement_px = int(round(self.rel_y * h))
        else:
            judgement_px = int(round(self.rel_y * 1000))
        return {
            "judgement_line_y": self.rel_y,
            "judgement_line_px": judgement_px,
            "column_count": col_count,
            "key_string": self.key_string_var.get().strip(),
            "columns": columns,
            "background_colors": [list(c) for c in self.matcher.background_colors],
            "key_colors": [list(c) for c in self.matcher.key_colors],
            "delay_ms": self.delay_ms,
            "tolerance": self.matcher.tolerance,
            "min_hold_ms": self.min_hold_ms,
            "window_size": [self.root.winfo_width(), self.root.winfo_height()],
            "window_position": [self.root.winfo_x(), self.root.winfo_y()],
        }

    def _remember_config(self, path: Path) -> None:
        """记录最近使用的配置文件。"""
        self._config_path = Path(path)
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            LAST_CONFIG_FILE.write_text(str(self._config_path), encoding="utf-8")
        except OSError:
            pass

    def on_save(self) -> None:
        """弹出另存为窗口，将当前设置保存为配置文件。"""
        self._cancel_eyedrop()  # 保存前取消吸管状态
        initial_file = self._config_path.name if self._config_path else "config.json"
        path = filedialog.asksaveasfilename(
            title="保存配置",
            initialdir=str(CONFIG_DIR),
            initialfile=initial_file,
            defaultextension=".json",
            filetypes=[("JSON 配置", "*.json"), ("所有文件", "*.*")],
        )
        if not path:
            self.status("已取消保存")
            return
        path = Path(path)
        save_config(path, self._build_cfg())
        self._remember_config(path)
        self.status(f"配置已保存到 {path.name}")

    def on_restore(self) -> None:
        """弹出打开窗口，选择配置文件并应用全部设置。"""
        path = filedialog.askopenfilename(
            title="选择配置文件",
            initialdir=str(CONFIG_DIR),
            filetypes=[("JSON 配置", "*.json"), ("所有文件", "*.*")],
        )
        if not path:
            self.status("已取消恢复")
            return
        self._apply_cfg(load_config(Path(path)))
        self._remember_config(Path(path))

    def _apply_cfg(self, cfg: dict) -> None:
        """应用配置到程序状态与界面。"""
        self.cfg = cfg
        self.rel_y = float(cfg["judgement_line_y"])
        self.judgement_px = int(cfg.get("judgement_line_px", 0))
        self.column_xs = [c["x"] for c in cfg["columns"]]
        self.keys = [c["key"] for c in cfg["columns"]]
        self.delay_ms = int(cfg["delay_ms"])
        self.min_hold_ms = int(cfg.get("min_hold_ms", 20))
        self.matcher = ColorMatcher(tolerance=int(cfg["tolerance"]))
        for c in cfg.get("background_colors", []):
            self.matcher.add_background(tuple(c))
        for c in cfg.get("key_colors", []):
            self.matcher.add_key(tuple(c))

        # UI 回显
        self.key_string_var.set(str(cfg.get("key_string", "")))
        self.col_count_var.set(str(cfg.get("column_count", len(self.column_xs) or 4)))
        self.delay_var.set(str(self.delay_ms))
        self.min_hold_var.set(str(self.min_hold_ms))
        win_h = max(1, self.root.winfo_height())
        if self.judgement_px > 0:
            self.judgement_var.set(str(self.judgement_px))
        else:
            self.judgement_var.set(str(int(self.rel_y * win_h)))

        # 窗口大小
        size = cfg.get("window_size", [0, 0])
        if isinstance(size, (list, tuple)) and len(size) == 2 and size[0] > 0 and size[1] > 0:
            geometry = f"{int(size[0])}x{int(size[1])}"
            pos = cfg.get("window_position", [-1, -1])
            if isinstance(pos, (list, tuple)) and len(pos) == 2 and pos[0] >= 0 and pos[1] >= 0:
                geometry += f"+{int(pos[0])}+{int(pos[1])}"
            self.root.geometry(geometry)

        # 判定线按像素换算（若已选游戏窗口）
        if self.game_rect and self.judgement_px > 0:
            h = max(1, self.game_rect[3] - self.game_rect[1])
            max_y = max(0.0, (h - 1) / h)
            self.rel_y = max(0.0, min(max_y, self.judgement_px / h))

        self._refresh_swatches()
        self._refresh_tracking()
        self.status("已从配置文件恢复设置")

    # ---------- 全局输入 ----------
    def on_hotkey(self, key: str) -> None:
        """钩子线程回调：入队后由主线程处理。"""
        if self._closing:
            return
        try:
            self._msg_queue.put_nowait(("hotkey", key))
        except queue.Full:
            pass

    def _handle_hotkey(self, key: str) -> None:
        focused = self.root.focus_get()
        if isinstance(focused, tk.Entry) and key != "ctrl":
            return  # 输入状态：不触发热键，仅作为输入字符
        if key == "ctrl":
            # 按 Ctrl 取消吸管与输入状态
            self._cancel_eyedrop()
            self.root.focus_set()
            return
        if key in ("4", "5"):
            # 延迟调整在任何模式下都生效
            self.nudge_delay(-5 if key == "4" else 5)
            return
        if key == "6":
            # 切换覆盖层显示状态
            self._overlay_visible = not self._overlay_visible
            if self._overlay_visible:
                self._refresh_tracking()
                if self.game_hwnd:
                    wu.set_foreground(self.game_hwnd)
                self.status("覆盖层已显示")
            else:
                self.overlay.hide()
                self.status("覆盖层已隐藏")
            return
        if key == "7":
            # 切换黄框/蓝框采集模式
            self._frame_blue = not self._frame_blue
            self.overlay.set_frame_color(BLUE if self._frame_blue else YELLOW)
            self.overlay.set_click_block(self._frame_blue)
            if self._frame_blue:
                self._blocker.start()
                self.dot.show_at(*MouseReader.cursor_pos())
                self.status("蓝框采集模式：点击游戏抓取坐标/颜色（再按7返回）")
            else:
                self._blocker.stop()
                self.dot.hide()
                self.status("黄框正常模式：点击穿透")
            return
        if key == "8":
            self.on_run()
            return
        if key == "9":
            self.on_pause()
            return
        if self.mode == "judgement":
            if key == "1":
                self.nudge_judgement(-1)
            elif key == "2":
                self.nudge_judgement(1)
            elif key == "3":
                self.mode = "idle"
                self.status("判定线设置结束")
            return
        if self.mode == "columns":
            if key == "1":
                self.nudge_column(-1)
            elif key == "2":
                self.nudge_column(1)
            elif key == "3":
                self.mode = "idle"
                self.status("列设置结束")
            return
        if self.mode in ("eyedrop_bg", "eyedrop_key") and key == "1":
            self.activate_eyedrop()
            return

    # ---------- 轮询 ----------
    def _tick_tracking(self) -> None:
        if not self._closing:
            # 运行中与设置模式下都保持覆盖层跟随窗口
            self._refresh_tracking()
            self.root.after(100, self._tick_tracking)

    def _tick_mouse(self) -> None:
        pressed = MouseReader.left_pressed()
        if pressed and not self._last_left:
            self._on_left_click()
        self._last_left = pressed
        if self._frame_blue:
            self.dot.show_at(*MouseReader.cursor_pos())
        if not self._closing:
            self.root.after(30, self._tick_mouse)

    def _on_left_click(self) -> None:
        x, y = MouseReader.cursor_pos()
        log.info("left click mode=%s at (%s,%s)", self.mode, x, y)
        if self.mode == "select_window":
            hwnd = wu.find_window_at_point(x, y)
            own = {int(self.root.winfo_id()), self.overlay.hwnd}
            log.info("select hit: hwnd=%s own=%s", hwnd, hwnd in own)
            if hwnd and hwnd not in own:
                self.select_game_window(hwnd)
        elif self.mode == "judgement":
            rel = self._rel_point(x, y)
            if rel:
                h = max(1, self.game_rect[3] - self.game_rect[1])
                self._set_judgement_px(int(rel[1] * h))
        elif self.mode == "columns":
            self._click_column(x, y)
        elif self.mode in ("eyedrop_bg", "eyedrop_key") and self.eyedrop_active:
            self._pick_color()

    def _rel_point(self, sx: int, sy: int) -> Optional[Tuple[float, float]]:
        if not self.game_rect:
            return None
        left, top, right, bottom = self.game_rect
        if not (left <= sx < right and top <= sy < bottom):
            return None
        return (
            (sx - left) / max(1, right - left),
            (sy - top) / max(1, bottom - top),
        )

    def _click_column(self, sx: int, sy: int) -> None:
        rel = self._rel_point(sx, sy)
        if rel is None:
            return
        rx, _ = rel
        for i, x in enumerate(self.column_xs):
            if abs(x - rx) < 0.01:
                self.selected_col = i
                self._refresh_tracking()
                self.status(f"选中第 {i + 1} 列，1左移 2右移")
                return
        try:
            count = max(1, int(self.col_count_var.get()))
        except ValueError:
            count = 1
        if len(self.column_xs) >= count:
            self.status(f"列数已满（{count}），可点击蓝点重新选中")
            return
        self.column_xs.append(rx)
        self.keys = self._parse_keys()
        self.selected_col = len(self.column_xs) - 1
        self._refresh_tracking()
        self.status(f"已添加第 {len(self.column_xs)} 列，1左移 2右移")

    # ---------- 关闭 ----------
    def on_close(self) -> None:
        self._closing = True
        if self.engine:
            self.engine.stop()
        self._hook.stop()
        self._blocker.stop()
        self.overlay.destroy()
        self.dot.destroy()
        try:
            # 关闭时自动保存到当前配置文件，并记录为最近使用
            save_config(self._config_path, self._build_cfg())
            self._remember_config(self._config_path)
        except Exception:
            pass
        self.root.destroy()
