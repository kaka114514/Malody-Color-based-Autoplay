import ctypes
import time

import win32gui
import win32con

from capture import grab_rect
from overlay import Overlay


user32 = ctypes.windll.user32
user32.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
user32.SendMessageW.restype = ctypes.c_long
gdi32 = ctypes.windll.gdi32
gdi32.GetPixel.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
gdi32.GetPixel.restype = ctypes.c_uint
WM_NCHITTEST = 0x0084
HTTRANSPARENT = -1


def _make_overlay(rect=(100, 100, 600, 500)):
    ov = Overlay()
    ov.set_game_rect(rect)
    ov.show()
    time.sleep(0.25)
    return ov


def _is_yellow(rgb) -> bool:
    r, g, b = rgb
    return r > 200 and g > 180 and b < 100


def test_overlay_window_created():
    ov = _make_overlay()
    assert ov.hwnd
    assert win32gui.IsWindow(ov.hwnd)
    ov.destroy()


def test_overlay_hide_show():
    ov = _make_overlay()
    ov.hide()
    time.sleep(0.1)
    assert not win32gui.IsWindowVisible(ov.hwnd)
    ov.show()
    time.sleep(0.1)
    assert win32gui.IsWindowVisible(ov.hwnd)
    ov.destroy()


def test_overlay_hit_test_is_transparent():
    """覆盖层命中测试必须返回 HTTRANSPARENT，否则会拦截游戏点击。"""
    ov = _make_overlay()
    rect = win32gui.GetWindowRect(ov.hwnd)
    cx, cy = (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2
    lp = (cy << 16) | (cx & 0xFFFF)
    result = user32.SendMessageW(ov.hwnd, WM_NCHITTEST, 0, lp)
    assert result == HTTRANSPARENT
    ov.destroy()


def test_overlay_frame_renders_yellow():
    """黄框必须真实渲染到屏幕上（10px 边缘）。"""
    ov = _make_overlay()
    hdc = user32.GetDC(ov.hwnd)
    try:
        # 窗口客户区 (0,0,500,400) 内四边采样（黄框 10px）
        top = gdi32.GetPixel(hdc, 250, 3) & 0xFFFFFF
        left = gdi32.GetPixel(hdc, 3, 100) & 0xFFFFFF
        right = gdi32.GetPixel(hdc, 496, 100) & 0xFFFFFF
        bottom = gdi32.GetPixel(hdc, 250, 396) & 0xFFFFFF
    finally:
        user32.ReleaseDC(ov.hwnd, hdc)
    yellow_bgr = 0x00D8FF  # RGB(255,216,0)
    assert top == yellow_bgr, f"顶部黄线缺失 top=0x{top:06X}"
    assert left == yellow_bgr, f"左侧黄线缺失 left=0x{left:06X}"
    assert right == yellow_bgr, f"右侧黄线缺失 right=0x{right:06X}"
    assert bottom == yellow_bgr, f"底部黄线缺失 bottom=0x{bottom:06X}"
    ov.destroy()


def test_overlay_clear_columns():
    ov = _make_overlay()
    ov.set_columns([0.25, 0.5, 0.75], selected=0)
    ov.clear_columns()
    time.sleep(0.1)
    ov.destroy()
