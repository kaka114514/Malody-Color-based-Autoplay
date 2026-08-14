"""自动游玩引擎：识别循环 + 延迟调度 + SendInput 按键。"""

import ctypes
import threading
import time
from typing import Callable, Dict, List, Optional, Tuple

import window_utils as wu
from capture import grab_rect, make_bbox, sample_points
from color_matcher import ColorMatcher


VK_MAP = {
    "space": 0x20, "enter": 0x0D, "tab": 0x09,
    "shift": 0x10, "ctrl": 0x11, "alt": 0x12,
    "esc": 0x1B, "backspace": 0x08,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
}


def _vk_for(key: str) -> int:
    k = key.strip().lower()
    if k in VK_MAP:
        return VK_MAP[k]
    if len(k) == 1 and k.isprintable():
        return ord(k.upper())
    raise ValueError(f"无法识别按键: {key}")


class KeySender:
    """通过 SendInput 注入键盘事件。"""

    KEYEVENTF_KEYUP = 0x0002
    INPUT_KEYBOARD = 1

    def __init__(self) -> None:
        self._pressed: set = set()
        self._lock = threading.Lock()

    def press(self, key: str) -> None:
        self._send(key, down=True)
        with self._lock:
            self._pressed.add(key)

    def release(self, key: str) -> None:
        self._send(key, down=False)
        with self._lock:
            self._pressed.discard(key)

    def release_all(self) -> None:
        with self._lock:
            keys = list(self._pressed)
            self._pressed.clear()
        for key in keys:
            self._send(key, down=False)

    def _send(self, key: str, down: bool) -> None:
        vk = _vk_for(key)
        flags = 0 if down else self.KEYEVENTF_KEYUP

        class MOUSEINPUT(ctypes.Structure):
            _fields_ = [
                ("dx", ctypes.c_long),
                ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", ctypes.c_ulonglong),
            ]

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [
                ("wVk", ctypes.c_ushort),
                ("wScan", ctypes.c_ushort),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", ctypes.c_ulonglong),
            ]

        class HARDWAREINPUT(ctypes.Structure):
            _fields_ = [
                ("uMsg", ctypes.c_ulong),
                ("wParamL", ctypes.c_ushort),
                ("wParamH", ctypes.c_ushort),
            ]

        class _INPUTUNION(ctypes.Union):
            _fields_ = [
                ("mi", MOUSEINPUT),
                ("ki", KEYBDINPUT),
                ("hi", HARDWAREINPUT),
            ]

        class INPUT(ctypes.Structure):
            _anonymous_ = ("u",)
            _fields_ = [
                ("type", ctypes.c_ulong),
                ("u", _INPUTUNION),
            ]

        inp = INPUT(self.INPUT_KEYBOARD)
        inp.ki = KEYBDINPUT(vk, 0, flags, 0, 0)
        ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


class KeyScheduler:
    """按键调度：按下沿带延迟、松开沿立即；纯逻辑，便于测试。"""

    def __init__(self, sender, keys: List[str], delay_ms: int = 0) -> None:
        self._sender = sender
        self._keys = list(keys)
        self._delay = max(0, int(delay_ms))
        self._desired: List[bool] = []
        self._pressed: List[bool] = []
        self._pending_at: Dict[int, float] = {}

    def set_delay(self, ms: int) -> None:
        self._delay = max(0, int(ms))

    def set_count(self, n: int) -> None:
        self._desired = [False] * n
        self._pressed = [False] * n
        self._pending_at.clear()

    def update(self, i: int, desired: bool, now_ms: float) -> None:
        while len(self._desired) <= i:
            self._desired.append(False)
            self._pressed.append(False)
        self._desired[i] = desired
        if desired:
            if not self._pressed[i] and i not in self._pending_at:
                self._pending_at[i] = now_ms + self._delay
        else:
            self._pending_at.pop(i, None)  # 取消未执行的按下
            if self._pressed[i]:
                self._pressed[i] = False
                self._sender.release(self._keys[i])

    def tick(self, now_ms: float) -> None:
        for i in list(self._pending_at):
            if self._pending_at[i] <= now_ms and self._desired[i] and not self._pressed[i]:
                self._pending_at.pop(i)
                self._pressed[i] = True
                self._sender.press(self._keys[i])

    def reset(self) -> None:
        self._pending_at.clear()
        self._sender.release_all()
        self._pressed = [False] * len(self._pressed)


class AutoplayEngine:
    """检测线程：截屏 → 颜色分类 → 调度按键。"""

    def __init__(
        self,
        matcher: ColorMatcher,
        hwnd: int,
        keys: List[str],
        rel_points: List[Tuple[float, float]],
        delay_ms: int = 0,
        on_log: Optional[Callable[[str], None]] = None,
        on_stopped: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._matcher = matcher
        self._hwnd = hwnd
        self._keys = list(keys)
        self._rel_points = [(float(x), float(y)) for x, y in rel_points]
        self._sender = KeySender()
        self._scheduler = KeyScheduler(self._sender, self._keys, delay_ms)
        self._on_log = on_log or (lambda msg: None)
        self._on_stopped = on_stopped
        self._running = False
        self._thread: Optional[threading.Thread] = None

    @property
    def running(self) -> bool:
        return self._running

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._scheduler.set_count(len(self._keys))
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        self._scheduler.reset()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def set_delay(self, ms: int) -> None:
        self._scheduler.set_delay(ms)

    def _loop(self) -> None:
        frames = 0
        last_log = time.perf_counter()
        while self._running:
            if wu.is_minimized(self._hwnd) or not wu.is_visible(self._hwnd):
                self._running = False
                self._sender.release_all()
                if self._on_stopped:
                    self._on_stopped("游戏窗口不可见，已自动暂停")
                return

            rect = wu.get_window_rect(self._hwnd)
            width = max(1, rect[2] - rect[0])
            height = max(1, rect[3] - rect[1])
            screen_points = [
                (rect[0] + int(x * width), rect[1] + int(y * height))
                for x, y in self._rel_points
            ]
            bbox = make_bbox(screen_points, pad=2)
            try:
                img = grab_rect(bbox)
            except Exception as exc:
                self._on_log(f"截屏失败: {exc}")
                time.sleep(0.01)
                continue

            local_points = [(p[0] - bbox[0], p[1] - bbox[1]) for p in screen_points]
            colors = sample_points(img, local_points)
            now_ms = time.perf_counter() * 1000.0

            for i, color in enumerate(colors):
                cls = self._matcher.classify(color)
                if cls == "key":
                    self._scheduler.update(i, True, now_ms)
                elif cls == "background":
                    self._scheduler.update(i, False, now_ms)
                # "unknown"：保持上一帧状态，避免闪烁
            self._scheduler.tick(now_ms)

            frames += 1
            now_real = time.perf_counter()
            if now_real - last_log >= 1.0:
                fps = frames / (now_real - last_log)
                self._on_log(f"检测频率: {fps:.0f} 次/秒")
                frames = 0
                last_log = now_real
