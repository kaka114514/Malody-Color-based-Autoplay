"""端到端验证：模拟游戏窗口 → 颜色检测 → SendInput → 全局钩子捕获。"""

import tkinter as tk
import time

import win32con
import win32gui

import window_utils as wu
from autoplay import AutoplayEngine
from color_matcher import ColorMatcher
from input_hook import GlobalKeyHook


BG = (40, 44, 52)          # 模拟背景色
KEY = (255, 60, 60)        # 模拟按键色


def main() -> None:
    root = tk.Tk()
    root.geometry("400x300+100+100")
    root.configure(bg="#282c34")
    root.update_idletasks()
    root.update()
    hwnd = int(root.winfo_id())
    win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 100, 100, 0, 0, win32con.SWP_NOSIZE)
    time.sleep(0.3)
    rect = wu.get_window_rect(hwnd)
    rel = (0.5, 0.5)  # 窗口矩形中心

    matcher = ColorMatcher(tolerance=20)
    matcher.add_background(BG)
    matcher.add_key(KEY)

    got = []
    hook = GlobalKeyHook(got.append)
    hook.start()
    time.sleep(0.3)

    engine = AutoplayEngine(matcher, hwnd, ["1"], [rel], delay_ms=0, on_log=print)
    engine.start()
    time.sleep(0.5)
    assert not got, f"背景色不应触发按键: {got}"
    print("阶段1 OK：背景色无触发")

    root.configure(bg="#ff3c3c")  # 整个窗口变为按键色
    root.update()
    time.sleep(1.0)
    assert "1" in got, f"按键色应触发 1，实际 {got}"
    print("阶段2 OK：按键色触发按键:", got)

    root.configure(bg="#282c34")  # 恢复背景色
    root.update()
    time.sleep(0.8)
    with engine._sender._lock:
        still_pressed = list(engine._sender._pressed)
    assert still_pressed == [], f"背景恢复后应松开，仍按住: {still_pressed}"
    print("阶段3 OK：背景恢复后松开")

    engine.stop()
    hook.stop()
    root.destroy()
    print("END-TO-END OK")


if __name__ == "__main__":
    main()
