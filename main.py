"""程序入口。"""

import atexit
import logging
import tkinter as tk

import window_utils as wu
from app import App
from input_hook import restore_system_cursor


def main() -> None:
    logging.basicConfig(
        filename="autoplay_debug.log",
        level=logging.DEBUG,
        format="%(asctime)s %(message)s",
        encoding="utf-8",
    )
    wu.set_process_dpi_aware()
    restore_system_cursor()  # 兜底：清除上次异常退出残留的吸管光标
    atexit.register(restore_system_cursor)
    root = tk.Tk()
    # 初始位置放到屏幕右上角，避免遮住游戏窗口
    root.update_idletasks()
    width = root.winfo_reqwidth()
    height = root.winfo_reqheight()
    screen_w = root.winfo_screenwidth()
    root.geometry(f"{width}x{height}+{max(0, screen_w - width - 30)}+30")
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
