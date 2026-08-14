import tkinter as tk
import time

from overlay import Overlay


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
