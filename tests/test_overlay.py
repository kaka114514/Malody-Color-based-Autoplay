import ctypes
import time

import win32gui
import win32con

from capture import grab_rect
from overlay import BLUE, YELLOW, Overlay


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


def test_overlay_blue_block_mode():
    """蓝框采集模式：边框变蓝、命中测试返回 HTCLIENT（拦截点击）。"""
    ov = _make_overlay()
    ov.set_frame_color(BLUE)
    ov.set_click_block(True)
    time.sleep(0.1)
    rect = win32gui.GetWindowRect(ov.hwnd)
    cx, cy = (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2
    lp = (cy << 16) | (cx & 0xFFFF)
    assert user32.SendMessageW(ov.hwnd, WM_NCHITTEST, 0, lp) == 1  # HTCLIENT
    hdc = user32.GetDC(ov.hwnd)
    try:
        col = gdi32.GetPixel(hdc, 250, 3) & 0xFFFFFF
    finally:
        user32.ReleaseDC(ov.hwnd, hdc)
    assert col == 0x00F6823B, f"边框应为蓝色，实际 0x{col:06X}"  # BGR of (59,130,246)
    ov.destroy()


def test_overlay_frame_color_toggle_back():
    """切回黄框后边框恢复黄色。"""
    ov = _make_overlay()
    ov.set_frame_color(BLUE)
    time.sleep(0.1)
    ov.set_frame_color(YELLOW)
    time.sleep(0.1)
    hdc = user32.GetDC(ov.hwnd)
    try:
        col = gdi32.GetPixel(hdc, 250, 3) & 0xFFFFFF
    finally:
        user32.ReleaseDC(ov.hwnd, hdc)
    assert col == 0x00D8FF, f"边框应为黄色，实际 0x{col:06X}"
    ov.destroy()


def test_overlay_click_callback():
    """拦截模式下点击触发回调，返回屏幕坐标。"""
    ov = _make_overlay()
    got = []
    ov.set_click_block(True)
    ov.set_click_callback(lambda x, y: got.append((x, y)))
    rect = win32gui.GetWindowRect(ov.hwnd)
    # 发送 WM_LBUTTONDOWN（客户区坐标 250,200）
    user32.SendMessageW(ov.hwnd, 0x0201, 1, (200 << 16) | 250)
    time.sleep(0.1)
    assert got, "点击回调未触发"
    sx, sy = got[0]
    assert abs(sx - (rect[0] + 250)) <= 1
    assert abs(sy - (rect[1] + 200)) <= 1
    ov.destroy()
