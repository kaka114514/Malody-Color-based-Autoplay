"""透明覆盖层（纯 Win32 + GDI）：黄框、红线、蓝点。

不用 Tk canvas——Tk 的 canvas 在 WS_EX_LAYERED + 透明色窗口上无法渲染
（实测像素为 0），且 Tk 窗口过程会覆盖 WM_NCHITTEST 导致点击被拦截。
本模块创建独立 Win32 分层窗口，自绘内容并实现点击穿透。
"""

import ctypes
import ctypes.wintypes as wintypes
import logging
import threading
from typing import List, Optional, Tuple


user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32

# 样式与消息常量
WS_POPUP = 0x80000000
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOPMOST = 0x00000008
HWND_TOPMOST = -1
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
WM_NCHITTEST = 0x0084
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_ERASEBKGND = 0x0014
WM_PAINT = 0x000F
WM_CLOSE = 0x0010
WM_DESTROY = 0x0002
HTTRANSPARENT = -1
HTCLIENT = 1
LWA_COLORKEY = 0x0001
PS_SOLID = 0
TRANSPARENT_KEY_BGR = 0x00030201  # RGB(1,2,3) 作为透明色

log = logging.getLogger("autoplay_debug")

YELLOW = (255, 216, 0)
RED = (255, 59, 48)
BLUE = (59, 130, 246)
SELECTED_BLUE = (0, 208, 255)
GREEN = (0, 255, 0)
FRAME_WIDTH = 8
FRAME_INSET = 4    # 边框向内偏移
LINE_WIDTH = 3
NOTCH = 6
RING_RADIUS = 5
RING_WIDTH = 2
DOT_SIZE = 7       # 鼠标绿点窗口尺寸
DOT_PX = 5         # 绿点像素大小


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class PAINTSTRUCT(ctypes.Structure):
    _fields_ = [
        ("hdc", wintypes.HDC),
        ("fErase", wintypes.BOOL),
        ("rcPaint", RECT),
        ("fRestore", wintypes.BOOL),
        ("fIncUpdate", wintypes.BOOL),
        ("rgbReserved", ctypes.c_byte * 32),
    ]


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", wintypes.POINT),
    ]


WNDPROC = ctypes.WINFUNCTYPE(
    ctypes.c_long, wintypes.HWND, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM
)


class WNDCLASS(ctypes.Structure):
    _fields_ = [
        ("style", ctypes.c_uint),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


# 关键 API 参数类型（64 位句柄安全）
HWND_P = wintypes.HWND
user32.CreateWindowExW.argtypes = [
    ctypes.c_uint, wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_uint,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    HWND_P, wintypes.HMENU, wintypes.HINSTANCE, ctypes.c_void_p,
]
user32.CreateWindowExW.restype = HWND_P
user32.SetLayeredWindowAttributes.argtypes = [HWND_P, ctypes.c_uint, ctypes.c_byte, ctypes.c_uint]
user32.SetLayeredWindowAttributes.restype = wintypes.BOOL
user32.SetWindowPos.argtypes = [HWND_P, HWND_P, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
user32.SetWindowPos.restype = wintypes.BOOL
user32.ShowWindow.argtypes = [HWND_P, ctypes.c_int]
user32.InvalidateRect.argtypes = [HWND_P, ctypes.c_void_p, wintypes.BOOL]
user32.InvalidateRect.restype = wintypes.BOOL
user32.BeginPaint.argtypes = [HWND_P, ctypes.POINTER(PAINTSTRUCT)]
user32.BeginPaint.restype = wintypes.HDC
user32.EndPaint.argtypes = [HWND_P, ctypes.POINTER(PAINTSTRUCT)]
user32.EndPaint.restype = wintypes.BOOL
user32.PostMessageW.argtypes = [HWND_P, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM]
user32.PostMessageW.restype = wintypes.BOOL
user32.ClientToScreen.argtypes = [HWND_P, ctypes.POINTER(wintypes.POINT)]
user32.ClientToScreen.restype = wintypes.BOOL
user32.DestroyWindow.argtypes = [HWND_P]
user32.DestroyWindow.restype = wintypes.BOOL
user32.DefWindowProcW.argtypes = [HWND_P, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = ctypes.c_long
user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASS)]
user32.RegisterClassW.restype = wintypes.BOOL
user32.FillRect.argtypes = [wintypes.HDC, ctypes.POINTER(RECT), wintypes.HBRUSH]
user32.FillRect.restype = ctypes.c_int
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
gdi32.CreateSolidBrush.argtypes = [ctypes.c_uint]
gdi32.CreateSolidBrush.restype = wintypes.HBRUSH
gdi32.MoveToEx.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
gdi32.MoveToEx.restype = wintypes.BOOL
gdi32.LineTo.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
gdi32.LineTo.restype = wintypes.BOOL
gdi32.CreatePen.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint]
gdi32.CreatePen.restype = wintypes.HPEN
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteObject.restype = wintypes.BOOL
gdi32.Ellipse.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
gdi32.Ellipse.restype = wintypes.BOOL
gdi32.GetStockObject.argtypes = [ctypes.c_int]
gdi32.GetStockObject.restype = wintypes.HGDIOBJ


def _rgb(color: Tuple[int, int, int]) -> int:
    r, g, b = color
    return (b << 16) | (g << 8) | r


class Overlay:
    """Win32 分层覆盖窗口：GDI 自绘黄框/红线/蓝点，点击穿透。"""

    _class_registered = False
    _class_lock = threading.Lock()

    def __init__(self, root=None) -> None:
        self._hwnd: Optional[int] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._ready = threading.Event()
        self._lock = threading.Lock()
        self._rect: Optional[Tuple[int, int, int, int]] = None
        self._rel_y = 0.5
        self._rel_xs: List[float] = []
        self._selected = -1
        self._frame_color = YELLOW
        self._click_block = False
        self._click_callback = None
        self._create_window()

    @property
    def hwnd(self) -> Optional[int]:
        return self._hwnd

    # ---------- 生命周期 ----------
    def _create_window(self) -> None:
        # 窗口必须与消息循环同线程，WM_PAINT 才能被派发
        self._running = True
        self._thread = threading.Thread(target=self._thread_main, daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout=5.0):
            raise OSError("overlay window thread failed to start")

    def _thread_main(self) -> None:
        try:
            with self._class_lock:
                if not Overlay._class_registered:
                    self._register_class()
                    Overlay._class_registered = True

            hinst = kernel32.GetModuleHandleW(None)
            hwnd = user32.CreateWindowExW(
                WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_TOPMOST,
                "MalodyOverlayClass", "",
                WS_POPUP,
                0, 0, 1, 1,
                None, None, hinst, None,
            )
            if not hwnd:
                raise OSError("CreateWindowExW failed")
            user32.SetLayeredWindowAttributes(hwnd, TRANSPARENT_KEY_BGR, 0, LWA_COLORKEY)
            self._hwnd = int(hwnd)
            _OVERLAYS[self._hwnd] = self
            self._ready.set()
            self._msg_loop()
        finally:
            self._running = False
            if self._hwnd:
                _OVERLAYS.pop(self._hwnd, None)
                self._hwnd = None

    @classmethod
    def _register_class(cls) -> None:
        wc = WNDCLASS()
        wc.style = 0
        wc.lpfnWndProc = _WNDPROC_CALLBACK
        wc.cbClsExtra = 0
        wc.cbWndExtra = 0
        wc.hInstance = kernel32.GetModuleHandleW(None)
        wc.hIcon = None
        wc.hCursor = None
        wc.hbrBackground = None
        wc.lpszMenuName = None
        wc.lpszClassName = "MalodyOverlayClass"
        if not user32.RegisterClassW(ctypes.byref(wc)):
            raise OSError("RegisterClassW failed")

    def _msg_loop(self) -> None:
        msg = MSG()
        while self._running:
            ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if ret <= 0:
                break
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def destroy(self) -> None:
        self._running = False
        if self._hwnd:
            user32.PostMessageW(self._hwnd, WM_CLOSE, 0, 0)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._hwnd = None

    # ---------- 外部接口（与旧 Overlay 一致） ----------
    def set_game_rect(self, rect: Tuple[int, int, int, int]) -> None:
        left, top, right, bottom = rect
        width = max(1, right - left)
        height = max(1, bottom - top)
        with self._lock:
            self._rect = rect
        user32.SetWindowPos(
            self._hwnd, HWND_TOPMOST, left, top, width, height,
            SWP_NOACTIVATE | SWP_SHOWWINDOW,
        )
        self._redraw()

    def set_judgement_y(self, rel_y: float) -> None:
        with self._lock:
            self._rel_y = max(0.0, min(1.0, rel_y))
        self._redraw()

    def set_columns(self, rel_xs: List[float], selected: int = -1) -> None:
        with self._lock:
            self._rel_xs = list(rel_xs)
            self._selected = selected
        self._redraw()

    def clear_columns(self) -> None:
        with self._lock:
            self._rel_xs = []
            self._selected = -1
        self._redraw()

    def set_frame_color(self, color: Tuple[int, int, int]) -> None:
        with self._lock:
            self._frame_color = tuple(color)
        self._redraw()

    def set_click_block(self, block: bool) -> None:
        """True：拦截点击（采集模式）；False：点击穿透。

        同时切换 WS_EX_TRANSPARENT：该样式会让系统在命中测试时跳过窗口，
        即使 WM_NCHITTEST 返回 HTCLIENT 也会穿透到下层窗口。
        """
        with self._lock:
            self._click_block = bool(block)
        if self._hwnd:
            style = user32.GetWindowLongW(self._hwnd, -20)  # GWL_EXSTYLE
            if block:
                style &= ~0x20  # 移除 WS_EX_TRANSPARENT
            else:
                style |= 0x20  # 恢复 WS_EX_TRANSPARENT
            user32.SetWindowLongW(self._hwnd, -20, style)

    def set_click_callback(self, callback) -> None:
        """点击被拦截时回调 (screen_x, screen_y)。"""
        with self._lock:
            self._click_callback = callback

    def show(self) -> None:
        if self._hwnd:
            user32.ShowWindow(self._hwnd, 5)  # SW_SHOW

    def hide(self) -> None:
        if self._hwnd:
            user32.ShowWindow(self._hwnd, 0)  # SW_HIDE

    def _redraw(self) -> None:
        if self._hwnd:
            user32.InvalidateRect(self._hwnd, None, True)

    def _hit_result(self) -> int:
        with self._lock:
            return HTCLIENT if self._click_block else HTTRANSPARENT

    def _handle_click(self, hwnd, l_param) -> None:
        x = l_param & 0xFFFF
        y = (l_param >> 16) & 0xFFFF
        pt = ctypes.wintypes.POINT(x, y)
        user32.ClientToScreen(hwnd, ctypes.byref(pt))
        with self._lock:
            callback = self._click_callback
        if callback is not None:
            try:
                callback(int(pt.x), int(pt.y))
            except Exception:
                pass

    # ---------- GDI 绘制 ----------
    def _paint(self, hwnd) -> None:
        try:
            with self._lock:
                rect = self._rect
                rel_y = self._rel_y
                rel_xs = list(self._rel_xs)
                selected = self._selected
            if rect is None:
                return
            left, top, right, bottom = rect
            width = max(1, right - left)
            height = max(1, bottom - top)

            ps = PAINTSTRUCT()
            hdc = user32.BeginPaint(hwnd, ctypes.byref(ps))
            try:
                # 透明背景（color key 填充）
                bg_brush = gdi32.CreateSolidBrush(TRANSPARENT_KEY_BGR)
                user32.FillRect(hdc, ctypes.byref(RECT(0, 0, width, height)), bg_brush)
                gdi32.DeleteObject(bg_brush)

                # 边框（8px，黄或蓝）
                pen = gdi32.CreatePen(PS_SOLID, FRAME_WIDTH, _rgb(self._frame_color))
                old = gdi32.SelectObject(hdc, pen)
                half = FRAME_WIDTH // 2 + FRAME_INSET
                # 四条线在角部收于交点处，避免四角凸出
                self._line(hdc, half, half, width - half, half)
                self._line(hdc, half, height - half, width - half, height - half)
                self._line(hdc, half, half, half, height - half)
                self._line(hdc, width - half, half, width - half, height - half)
                gdi32.SelectObject(hdc, old)
                gdi32.DeleteObject(pen)

                # 红线（3px，蓝点处断开）
                y = min(int(rel_y * height), max(0, height - 1))
                pen = gdi32.CreatePen(PS_SOLID, LINE_WIDTH, _rgb(RED))
                old = gdi32.SelectObject(hdc, pen)
                xs = sorted(rel_x * width for rel_x in rel_xs)
                prev = 0
                for cx in xs:
                    a = max(prev, cx - NOTCH)
                    b = cx + NOTCH
                    if a > prev:
                        self._line(hdc, prev, y, a, y)
                    prev = b
                if prev < width:
                    self._line(hdc, prev, y, width, y)
                gdi32.SelectObject(hdc, old)
                gdi32.DeleteObject(pen)

                # 蓝点（空心圆环：蓝色画笔 + 不填充，中心天然透明供检测取色）
                for i, rel_x in enumerate(rel_xs):
                    cx = int(rel_x * width)
                    color = SELECTED_BLUE if i == selected else BLUE
                    pen = gdi32.CreatePen(PS_SOLID, RING_WIDTH, _rgb(color))
                    old_pen = gdi32.SelectObject(hdc, pen)
                    old_brush = gdi32.SelectObject(hdc, gdi32.GetStockObject(5))  # NULL_BRUSH
                    gdi32.Ellipse(
                        hdc, cx - RING_RADIUS, y - RING_RADIUS,
                        cx + RING_RADIUS, y + RING_RADIUS,
                    )
                    gdi32.SelectObject(hdc, old_brush)
                    gdi32.SelectObject(hdc, old_pen)
                    gdi32.DeleteObject(pen)
            finally:
                user32.EndPaint(hwnd, ctypes.byref(ps))
        except Exception:
            log.exception("overlay paint failed")

    @staticmethod
    def _line(hdc, x1, y1, x2, y2) -> None:
        gdi32.MoveToEx(hdc, int(x1), int(y1), None)
        gdi32.LineTo(hdc, int(x2), int(y2))


class CursorDot:
    """采集模式下的鼠标绿点：2px、置顶、点击穿透。"""

    _class_registered = False
    _class_lock = threading.Lock()

    def __init__(self) -> None:
        self._hwnd: Optional[int] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._ready = threading.Event()
        self._create_window()

    @property
    def hwnd(self) -> Optional[int]:
        return self._hwnd

    def _create_window(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._thread_main, daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout=5.0):
            raise OSError("cursor dot thread failed to start")

    def _thread_main(self) -> None:
        try:
            with self._class_lock:
                if not CursorDot._class_registered:
                    self._register_class()
                    CursorDot._class_registered = True
            hinst = kernel32.GetModuleHandleW(None)
            hwnd = user32.CreateWindowExW(
                WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_TOPMOST,
                "MalodyCursorDotClass", "",
                WS_POPUP,
                0, 0, DOT_SIZE, DOT_SIZE,
                None, None, hinst, None,
            )
            if not hwnd:
                raise OSError("CreateWindowExW failed")
            user32.SetLayeredWindowAttributes(hwnd, TRANSPARENT_KEY_BGR, 0, LWA_COLORKEY)
            self._hwnd = int(hwnd)
            _OVERLAYS[self._hwnd] = self
            self._ready.set()
            self._msg_loop()
        finally:
            self._running = False
            if self._hwnd:
                _OVERLAYS.pop(self._hwnd, None)
                self._hwnd = None

    @classmethod
    def _register_class(cls) -> None:
        wc = WNDCLASS()
        wc.style = 0
        wc.lpfnWndProc = _WNDPROC_CALLBACK
        wc.cbClsExtra = 0
        wc.cbWndExtra = 0
        wc.hInstance = kernel32.GetModuleHandleW(None)
        wc.hIcon = None
        wc.hCursor = None
        wc.hbrBackground = None
        wc.lpszMenuName = None
        wc.lpszClassName = "MalodyCursorDotClass"
        if not user32.RegisterClassW(ctypes.byref(wc)):
            raise OSError("RegisterClassW failed")

    def _msg_loop(self) -> None:
        msg = MSG()
        while self._running:
            ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if ret <= 0:
                break
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def destroy(self) -> None:
        self._running = False
        if self._hwnd:
            user32.PostMessageW(self._hwnd, WM_CLOSE, 0, 0)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._hwnd = None

    def show_at(self, x: int, y: int) -> None:
        if not self._hwnd:
            return
        user32.SetWindowPos(
            self._hwnd, HWND_TOPMOST,
            x - DOT_SIZE // 2, y - DOT_SIZE // 2, DOT_SIZE, DOT_SIZE,
            SWP_NOACTIVATE | SWP_SHOWWINDOW,
        )
        user32.InvalidateRect(self._hwnd, None, True)

    def hide(self) -> None:
        if self._hwnd:
            user32.ShowWindow(self._hwnd, 0)  # SW_HIDE

    def _hit_result(self) -> int:
        return HTTRANSPARENT

    def _paint(self, hwnd) -> None:
        ps = PAINTSTRUCT()
        hdc = user32.BeginPaint(hwnd, ctypes.byref(ps))
        try:
            bg_brush = gdi32.CreateSolidBrush(TRANSPARENT_KEY_BGR)
            user32.FillRect(hdc, ctypes.byref(RECT(0, 0, DOT_SIZE, DOT_SIZE)), bg_brush)
            gdi32.DeleteObject(bg_brush)
            green_brush = gdi32.CreateSolidBrush(_rgb(GREEN))
            offset = (DOT_SIZE - DOT_PX) // 2
            user32.FillRect(
                hdc, ctypes.byref(RECT(offset, offset, offset + DOT_PX, offset + DOT_PX)),
                green_brush,
            )
            gdi32.DeleteObject(green_brush)
            # 最中间像素透明，便于精确定位
            hole_brush = gdi32.CreateSolidBrush(TRANSPARENT_KEY_BGR)
            center = DOT_SIZE // 2
            user32.FillRect(
                hdc, ctypes.byref(RECT(center, center, center + 1, center + 1)),
                hole_brush,
            )
            gdi32.DeleteObject(hole_brush)
        finally:
            user32.EndPaint(hwnd, ctypes.byref(ps))


def _wndproc(hwnd, msg, w_param, l_param):
    if msg == WM_NCHITTEST:
        ov = _get_overlay(hwnd)
        if ov is not None:
            return ov._hit_result()
        return HTTRANSPARENT
    if msg == WM_LBUTTONDOWN:
        ov = _get_overlay(hwnd)
        if ov is not None:
            ov._handle_click(hwnd, l_param)
        return 0
    if msg == WM_LBUTTONUP:
        return 0  # 采集模式消费抬起事件，确保点击完全不传给游戏
    if msg == WM_ERASEBKGND:
        return 1
    if msg == WM_PAINT:
        ov = _get_overlay(hwnd)
        if ov is not None:
            ov._paint(hwnd)
        else:
            user32.ValidateRect(hwnd, None)
        return 0
    if msg == WM_CLOSE:
        user32.DestroyWindow(hwnd)
        return 0
    if msg == WM_DESTROY:
        _forget_overlay(hwnd)
        return 0
    return user32.DefWindowProcW(hwnd, msg, w_param, l_param)


# 窗口过程回调必须保持引用，否则 GC 后访问冲突
_WNDPROC_CALLBACK = WNDPROC(_wndproc)

_OVERLAYS: dict = {}


def _get_overlay(hwnd) -> Optional[Overlay]:
    return _OVERLAYS.get(hwnd)


def _forget_overlay(hwnd) -> None:
    _OVERLAYS.pop(hwnd, None)
