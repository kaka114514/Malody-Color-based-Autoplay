"""GUI 冒烟测试：启动界面，验证窗口与渲染，2 秒后自动退出。"""

import tkinter as tk

import window_utils as wu
from PIL import ImageGrab

from app import App


def main() -> None:
    wu.set_process_dpi_aware()
    root = tk.Tk()
    app = App(root)
    root.update()

    def smoke() -> None:
        hwnd = int(root.winfo_id())
        rect = wu.get_window_rect(hwnd)
        print("hwnd:", hwnd)
        print("rect:", rect)
        img = ImageGrab.grab(bbox=rect)
        print("shot size:", img.size)
        img.save("smoke_ui.png")
        assert rect[2] > rect[0] and rect[3] > rect[1]
        assert app.delay_var.get() == str(app.delay_ms)
        assert app.status_var.get()
        assert app.overlay is not None
        print("SMOKE OK")
        root.destroy()

    root.after(800, smoke)
    root.mainloop()


if __name__ == "__main__":
    main()
