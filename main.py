"""程序入口。"""

import tkinter as tk

import window_utils as wu
from app import App


def main() -> None:
    wu.set_process_dpi_aware()
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
