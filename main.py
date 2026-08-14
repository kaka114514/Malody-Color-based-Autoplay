"""程序入口。"""

import tkinter as tk

import window_utils as wu
from app import App


def main() -> None:
    wu.set_process_dpi_aware()
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
