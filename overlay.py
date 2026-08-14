"""透明覆盖层：黄框、红线、蓝点。点击穿透、置顶、不抢焦点。"""

import ctypes
import tkinter as tk
from typing import List, Optional, Tuple

import win32gui
import win32con


TRANSPARENT_KEY = "#010203"   # tkinter 透明色
YELLOW = "#FFD800"
RED = "#FF3B30"
BLUE = "#3B82F6"
FRAME_WIDTH = 10              # 黄框线宽
LINE_WIDTH = 3                # 红线线宽
NOTCH = 6                     # 红线在蓝点处断开半径
RING_RADIUS = 5               # 蓝点外径
RING_WIDTH = 2

WM_NCHITTEST = 0x0084
HTTRANSPARENT = -1
GWLP_WNDPROC = -4


class Overlay:
    def __init__(self, root: tk.Tk):
        self._root = root
        self._window = tk.Toplevel(root)
        self._window.overrideredirect(True)
        self._window.attributes("-topmost", True)
        self._window.attributes("-transparentcolor", TRANSPARENT_KEY)
        self._canvas = tk.Canvas(
            self._window,
            bg=TRANSPARENT_KEY,
            highlightthickness=0,
            bd=0,
        )
        self._canvas.pack(fill="both", expand=True)
        self._rect: Optional[Tuple[int, int, int, int]] = None
        self._rel_y = 0.5
        self._rel_xs: List[float] = []
        self._selected = -1
        self._apply_click_through()
        self._install_hit_test_hook()

    def _apply_click_through(self) -> None:
        """加扩展样式：分层、点击穿透、工具窗口、不激活。"""
        hwnd = int(self._window.winfo_id())
        style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
        style |= (
            win32con.WS_EX_LAYERED
            | win32con.WS_EX_TRANSPARENT
            | win32con.WS_EX_TOOLWINDOW
            | win32con.WS_EX_NOACTIVATE
        )
        win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, style)

    def _install_hit_test_hook(self) -> None:
        """替换窗口过程：WM_NCHITTEST 返回 HTTRANSPARENT，实现点击穿透。

        Tk 的窗口过程对 WM_NCHITTEST 返回 HTCLIENT，会覆盖
        WS_EX_TRANSPARENT 的默认穿透行为，导致覆盖层拦截鼠标点击。
        """
        hwnd = int(self._window.winfo_id())
        user32 = ctypes.windll.user32
        user32.SetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
        user32.SetWindowLongPtrW.restype = ctypes.c_void_p
        user32.CallWindowProcW.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint,
            ctypes.c_void_p, ctypes.c_void_p,
        ]
        user32.CallWindowProcW.restype = ctypes.c_long

        wndproc_type = ctypes.WINFUNCTYPE(
            ctypes.c_long, ctypes.c_void_p, ctypes.c_uint,
            ctypes.c_void_p, ctypes.c_void_p,
        )
        old_proc = ctypes.c_void_p()

        def proc(hwnd, msg, w_param, l_param):
            if msg == WM_NCHITTEST:
                return HTTRANSPARENT
            return user32.CallWindowProcW(old_proc, hwnd, msg, w_param, l_param)

        # 回调与旧过程必须保持引用，避免被 GC
        self._wndproc = wndproc_type(proc)
        self._old_wndproc = user32.SetWindowLongPtrW(hwnd, GWLP_WNDPROC, self._wndproc)

    def set_game_rect(self, rect: Tuple[int, int, int, int]) -> None:
        """定位覆盖层到游戏窗口矩形并重绘。"""
        left, top, right, bottom = rect
        width = max(1, right - left)
        height = max(1, bottom - top)
        self._rect = rect
        self._window.geometry(f"{width}x{height}+{left}+{top}")
        self._canvas.configure(width=width, height=height)
        self._redraw()

    def set_judgement_y(self, rel_y: float) -> None:
        self._rel_y = max(0.0, min(1.0, rel_y))
        self._redraw()

    def set_columns(self, rel_xs: List[float], selected: int = -1) -> None:
        self._rel_xs = list(rel_xs)
        self._selected = selected
        self._redraw()

    def clear_columns(self) -> None:
        self._rel_xs = []
        self._selected = -1
        self._redraw()

    def show(self) -> None:
        self._window.deiconify()
        self._window.lift()

    def hide(self) -> None:
        self._window.withdraw()

    def _redraw(self) -> None:
        c = self._canvas
        c.delete("all")
        if self._rect is None:
            return
        width = int(c.cget("width"))
        height = int(c.cget("height"))

        # 黄框（窗口边缘，5px）
        c.create_rectangle(
            0, 0, width - 1, height - 1,
            outline=YELLOW, width=FRAME_WIDTH,
        )

        # 红线（3px，在蓝点 x 处断开 ±NOTCH）
        y = self._rel_y * height
        xs = [rel_x * width for rel_x in self._rel_xs]
        segments = []
        prev = 0
        for cx in sorted(xs):
            a = max(prev, cx - NOTCH)
            b = cx + NOTCH
            if a > prev:
                segments.append((prev, a))
            prev = b
        if prev < width:
            segments.append((prev, width))
        for a, b in segments:
            c.create_line(a, y, b, y, fill=RED, width=LINE_WIDTH)

        # 蓝点：空心圆环（中心透明，供检测取色）
        for i, rel_x in enumerate(self._rel_xs):
            cx = rel_x * width
            outline = BLUE
            if i == self._selected:
                outline = "#00D0FF"
            c.create_oval(
                cx - RING_RADIUS, y - RING_RADIUS,
                cx + RING_RADIUS, y + RING_RADIUS,
                outline=outline, width=RING_WIDTH, fill=TRANSPARENT_KEY,
            )
