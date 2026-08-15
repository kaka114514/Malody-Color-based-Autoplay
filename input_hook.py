"""全局键盘低级钩子与鼠标状态读取。"""

import ctypes
import ctypes.wintypes
import threading
from typing import Callable, Optional, Tuple


WH_KEYBOARD_LL = 13
WH_MOUSE_LL = 14
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
WM_QUIT = 0x0012
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
VK_NUMPAD_BASE = 0x60
VK_CONTROL = 0x11


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", ctypes.wintypes.POINT),
        ("mouseData", ctypes.c_ulong),
        ("flags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.c_ulonglong),
    ]


LowLevelMouseProc = ctypes.WINFUNCTYPE(
    ctypes.c_long, ctypes.c_int, ctypes.c_uint, ctypes.c_void_p
)


LowLevelKeyboardProc = ctypes.WINFUNCTYPE(
    ctypes.c_long, ctypes.c_int, ctypes.c_uint, ctypes.c_void_p
)
ctypes.windll.user32.CallNextHookEx.argtypes = [
    ctypes.c_void_p, ctypes.c_int, ctypes.c_uint, ctypes.c_void_p
]
ctypes.windll.user32.CallNextHookEx.restype = ctypes.c_long


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", ctypes.c_ulong),
        ("scanCode", ctypes.c_ulong),
        ("flags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.c_ulonglong),
    ]


def map_vk_to_hotkey(vk: int) -> Optional[str]:
    """数字键 0~9（含小键盘）→ "0".."9"；其它返回 None。"""
    if vk == VK_CONTROL:
        return "ctrl"
    if 0x30 <= vk <= 0x39:
        return chr(vk)
    if VK_NUMPAD_BASE <= vk <= VK_NUMPAD_BASE + 9:
        return chr(vk - VK_NUMPAD_BASE)
    return None


class GlobalKeyHook:
    """低级键盘钩子，在独立线程运行，把 1~5 数字键回调给调用方。"""

    def __init__(self, callback: Callable[[str], None]):
        self._callback = callback
        self._proc = LowLevelKeyboardProc(self._impl)
        self._hook = None
        self._thread: Optional[threading.Thread] = None
        self._running = False

    def _impl(self, n_code, w_param, l_param) -> int:
        if n_code >= 0 and w_param in (WM_KEYDOWN, WM_SYSKEYDOWN):
            kb = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            vk = kb.vkCode & 0xFF
            key = map_vk_to_hotkey(vk)
            if key is not None:
                try:
                    self._callback(key)
                except Exception:
                    pass
        return ctypes.windll.user32.CallNextHookEx(self._hook, n_code, w_param, l_param)

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        self._hook = ctypes.windll.user32.SetWindowsHookExW(
            WH_KEYBOARD_LL, self._proc, None, 0
        )
        if not self._hook:
            self._running = False
            return
        msg = ctypes.wintypes.MSG()
        while self._running and ctypes.windll.user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            ctypes.windll.user32.TranslateMessage(ctypes.byref(msg))
            ctypes.windll.user32.DispatchMessageW(ctypes.byref(msg))
        ctypes.windll.user32.UnhookWindowsHookEx(self._hook)
        self._hook = None

    def stop(self) -> None:
        self._running = False
        if self._hook:
            ctypes.windll.user32.PostThreadMessageW(
                self._thread.ident, WM_QUIT, 0, 0
            )
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)


class MouseReader:
    """轮询式鼠标状态（不依赖钩子）。"""

    VK_LBUTTON = 0x01

    @staticmethod
    def left_pressed() -> bool:
        state = ctypes.windll.user32.GetAsyncKeyState(MouseReader.VK_LBUTTON)
        return bool(state & 0x8000)

    @staticmethod
    def cursor_pos() -> Tuple[int, int]:
        pt = ctypes.wintypes.POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
        return int(pt.x), int(pt.y)


class MouseBlocker:
    """低级鼠标钩子：在指定区域内拦截左键点击（采集模式防误触）。

    分层窗口的透明像素在命中测试时会被系统视为透明而跳过，
    因此仅靠窗口命中测试无法拦截透明区域的点击；低级鼠标钩子
    可在事件到达任何窗口前将其吞掉。
    """

    def __init__(self, in_block_region, on_blocked_click=None):
        self._in_block_region = in_block_region
        self._on_click = on_blocked_click
        self._hook = None
        self._thread: Optional[threading.Thread] = None
        self._running = False

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._hook:
            ctypes.windll.user32.PostThreadMessageW(self._thread.ident, WM_QUIT, 0, 0)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._hook = None

    def _run(self) -> None:
        self._proc = LowLevelMouseProc(self._impl)
        self._hook = ctypes.windll.user32.SetWindowsHookExW(WH_MOUSE_LL, self._proc, None, 0)
        msg = ctypes.wintypes.MSG()
        while self._running and ctypes.windll.user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            ctypes.windll.user32.TranslateMessage(ctypes.byref(msg))
            ctypes.windll.user32.DispatchMessageW(ctypes.byref(msg))
        if self._hook:
            ctypes.windll.user32.UnhookWindowsHookEx(self._hook)
            self._hook = None

    def _impl(self, n_code, w_param, l_param):
        if n_code >= 0 and w_param in (WM_LBUTTONDOWN, WM_LBUTTONUP):
            msll = ctypes.cast(l_param, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
            x, y = int(msll.pt.x), int(msll.pt.y)
            if self._in_block_region(x, y):
                if w_param == WM_LBUTTONDOWN and self._on_click is not None:
                    try:
                        self._on_click(x, y)
                    except Exception:
                        pass
                return 1  # 吞掉事件，游戏收不到点击
        return ctypes.windll.user32.CallNextHookEx(self._hook, n_code, w_param, l_param)
