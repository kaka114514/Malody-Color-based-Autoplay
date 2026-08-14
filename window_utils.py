"""Windows 窗口操作：选取、矩形、置前、可见性。"""

import ctypes
from typing import Optional, Tuple

import win32gui
import win32con


Rect = Tuple[int, int, int, int]


def set_process_dpi_aware() -> None:
    """让进程感知 DPI，保证屏幕坐标一致。失败时静默忽略。"""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # PROCESS_PER_MONITOR_DPI_AWARE
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def find_window_at_point(x: int, y: int) -> Optional[int]:
    """返回屏幕上 (x, y) 处最顶层窗口句柄；无窗口返回 None。"""
    hwnd = win32gui.WindowFromPoint((x, y))
    return int(hwnd) if hwnd else None


def get_window_rect(hwnd: int) -> Rect:
    """返回窗口屏幕矩形 (left, top, right, bottom)。"""
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    return int(left), int(top), int(right), int(bottom)


def set_foreground(hwnd: int) -> bool:
    """将窗口置为前台。"""
    try:
        win32gui.SetForegroundWindow(hwnd)
        return True
    except win32gui.error:
        return False


def is_minimized(hwnd: int) -> bool:
    """窗口是否最小化。"""
    return bool(win32gui.IsIconic(hwnd))


def is_visible(hwnd: int) -> bool:
    return bool(win32gui.IsWindowVisible(hwnd))
