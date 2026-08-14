import tkinter as tk
import time
import ctypes

import win32gui
from overlay import Overlay


user32 = ctypes.windll.user32
user32.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
user32.SendMessageW.restype = ctypes.c_long
WM_NCHITTEST = 0x0084
HTTRANSPARENT = -1


def _make_overlay():
    root = tk.Tk()
    ov = Overlay(root)
    ov.set_game_rect((100, 100, 500, 400))
    ov.set_judgement_y(0.5)
    ov.set_columns([0.25, 0.5, 0.75], selected=0)
    root.update_idletasks()
    root.update()
    time.sleep(0.1)
    return root, ov


def test_overlay_creates_drawings():
    root, ov = _make_overlay()
    canvas = ov._canvas
    n_before = len(canvas.find_all())
    assert n_before > 0
    root.destroy()


def test_overlay_hide_show():
    root, ov = _make_overlay()
    ov.hide()
    root.update()
    assert not ov._window.winfo_ismapped()
    ov.show()
    root.update()
    assert ov._window.winfo_ismapped()
    root.destroy()


def test_overlay_clear_columns():
    root, ov = _make_overlay()
    ov.clear_columns()
    root.update()
    root.destroy()


def test_overlay_hit_test_is_transparent():
    """覆盖层命中测试必须返回 HTTRANSPARENT，否则会拦截游戏点击。"""
    root, ov = _make_overlay()
    hwnd = int(ov._window.winfo_id())
    rect = win32gui.GetWindowRect(hwnd)
    cx, cy = (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2
    lp = (cy << 16) | (cx & 0xFFFF)
    result = user32.SendMessageW(hwnd, WM_NCHITTEST, 0, lp)
    assert result == HTTRANSPARENT
    root.destroy()
