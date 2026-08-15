import time

import pytest

from autoplay import KeyScheduler, _vk_for


class FakeSender:
    def __init__(self):
        self.events = []  # ("press"|"release", key)
        self.pressed = set()

    def press(self, key):
        self.events.append(("press", key))
        self.pressed.add(key)

    def release(self, key):
        self.events.append(("release", key))
        self.pressed.discard(key)

    def release_all(self):
        for key in list(self.pressed):
            self.release(key)


def make_scheduler(delay=0, keys=("D", "F")):
    return KeyScheduler(FakeSender(), list(keys), delay)


def test_immediate_press_and_release():
    s = make_scheduler(delay=0)
    s.update(0, True, 0)
    s.tick(0)
    assert s._sender.events == [("press", "D")]
    s.update(0, False, 1)
    assert s._sender.events == [("press", "D"), ("release", "D")]


def test_delayed_press():
    s = make_scheduler(delay=50)
    s.update(0, True, 0)
    s.tick(49)
    assert s._sender.events == []
    s.tick(50)
    assert s._sender.events == [("press", "D")]


def test_delayed_press_after_note_passed():
    """延迟期间音符已过：到期按下并至少按住 MIN_HOLD_MS 再松开。"""
    s = make_scheduler(delay=50)
    s.update(0, True, 0)
    s.update(0, False, 10)  # 未执行前变回背景
    s.tick(50)
    assert s._sender.events == [("press", "D")]
    s.tick(89)
    assert s._sender.events == [("press", "D")]  # 未到最小按住时长
    s.tick(90)
    assert s._sender.events == [("press", "D"), ("release", "D")]


def test_negative_delay_is_zero():
    s = make_scheduler(delay=-5)
    s.update(0, True, 0)
    s.tick(0)
    assert s._sender.events == [("press", "D")]


def test_hold_does_not_repeat_press():
    s = make_scheduler(delay=0)
    s.update(0, True, 0)
    s.tick(0)
    s.update(0, True, 10)
    s.tick(10)
    assert s._sender.events == [("press", "D")]


def test_set_delay_rebounds():
    s = make_scheduler(delay=0)
    s.set_delay(-100)
    s.update(0, True, 0)
    s.tick(0)
    assert s._sender.events == [("press", "D")]


def test_vk_for():
    assert _vk_for("D") == 0x44
    assert _vk_for("d") == 0x44
    assert _vk_for("Space") == 0x20
    assert _vk_for("shift") == 0x10
    with pytest.raises(ValueError):
        _vk_for("__invalid__")
