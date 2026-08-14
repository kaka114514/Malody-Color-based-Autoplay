import tkinter as tk
import time

import pytest

import win32con
import win32gui

import window_utils as wu


def test_find_window_at_point_and_rect():
    """创建一个小窗口，点击其中心应返回该窗口句柄，矩形应包含该点。"""
    root = tk.Tk()
    root.geometry("240x120+200+200")
    root.update_idletasks()
    root.update()
    time.sleep(0.2)
    hwnd = wu.find_window_at_point(320, 260)  # 窗口中心（不含标题栏偏移）
    assert hwnd is not None
    rect = wu.get_window_rect(hwnd)
    left, top, right, bottom = rect
    assert left <= 320 <= right
    assert top <= 260 <= bottom
    root.destroy()


def test_rect_shape():
    hwnd = wu.find_window_at_point(320, 260)
    if hwnd is None:
        pytest.skip("no window found")
    rect = wu.get_window_rect(hwnd)
    assert len(rect) == 4
    assert rect[2] > rect[0]
    assert rect[3] > rect[1]


def test_is_minimized_after_iconify():
    root = tk.Tk()
    root.geometry("240x120+200+200")
    root.update_idletasks()
    root.update()
    time.sleep(0.2)
    hwnd = wu.find_window_at_point(320, 260)
    assert hwnd is not None
    win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
    root.update()
    time.sleep(0.2)
    assert wu.is_minimized(hwnd) is True
    root.destroy()
