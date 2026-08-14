import tkinter as tk
import time

import win32con
import win32gui

import window_utils as wu


def test_window_utils_with_single_tk_root():
    """单个 Tk 窗口验证：查找、矩形、最小化检测。

    合并为单个测试避免连续创建多个 Tk 根窗口导致的 Tcl 状态损坏。
    """
    root = tk.Tk()
    root.geometry("240x120+200+200")
    root.update_idletasks()
    root.update()
    time.sleep(0.2)

    # 查找窗口并验证矩形包含该点
    hwnd = wu.find_window_at_point(320, 260)  # 窗口中心（不含标题栏偏移）
    assert hwnd is not None
    rect = wu.get_window_rect(hwnd)
    assert len(rect) == 4
    assert rect[2] > rect[0]
    assert rect[3] > rect[1]
    left, top, right, bottom = rect
    assert left <= 320 <= right
    assert top <= 260 <= bottom

    # 最小化检测
    win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
    root.update()
    time.sleep(0.2)
    assert wu.is_minimized(hwnd) is True
    root.destroy()
