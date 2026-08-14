"""全局键盘低级钩子与鼠标状态读取。"""

import ctypes
import ctypes.wintypes
import threading
from pathlib import Path
from typing import Callable, Optional, Tuple


WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
WM_QUIT = 0x0012
VK_NUMPAD_BASE = 0x60


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
    """数字键 1~7（含小键盘）→ "1".."7"；其它返回 None。"""
    if 0x31 <= vk <= 0x37:
        return chr(vk)
    if VK_NUMPAD_BASE + 1 <= vk <= VK_NUMPAD_BASE + 7:
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


def set_global_cursor(cur_path: Path) -> None:
    """把系统箭头临时替换为吸管光标（取色结束后必须恢复）。"""
    hcur = ctypes.windll.user32.LoadImageW(
        None, str(cur_path), 2, 0, 0, 0x0010  # IMAGE_CURSOR, LR_LOADFROMFILE
    )
    if hcur:
        ctypes.windll.user32.SetSystemCursor(hcur, 32512)  # OCR_NORMAL


def restore_system_cursor() -> None:
    """恢复系统默认箭头光标。"""
    hcur = ctypes.windll.user32.LoadCursorW(None, 32512)  # IDC_ARROW
    if hcur:
        ctypes.windll.user32.SetSystemCursor(hcur, 32512)
