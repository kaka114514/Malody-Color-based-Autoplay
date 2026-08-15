import ctypes

from input_hook import GlobalKeyHook, MouseBlocker, MouseReader, map_vk_to_hotkey


def test_map_vk_to_hotkey():
    assert map_vk_to_hotkey(0x11) == "ctrl"
    assert map_vk_to_hotkey(0x31) == "1"
    assert map_vk_to_hotkey(0x35) == "5"
    assert map_vk_to_hotkey(0x36) == "6"
    assert map_vk_to_hotkey(0x37) == "7"
    assert map_vk_to_hotkey(0x38) == "8"
    assert map_vk_to_hotkey(0x39) == "9"
    assert map_vk_to_hotkey(0x30) == "0"
    assert map_vk_to_hotkey(0x41) is None  # 'A'
    assert map_vk_to_hotkey(0) is None


def test_hook_start_stop():
    events = []
    hook = GlobalKeyHook(events.append)
    hook.start()
    hook.stop()


def test_mouse_reader_cursor_pos():
    x, y = MouseReader.cursor_pos()
    assert isinstance(x, int)
    assert isinstance(y, int)


def _make_mouse_event(x, y):
    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    class M(ctypes.Structure):
        _fields_ = [
            ("pt", POINT),
            ("mouseData", ctypes.c_ulong),
            ("flags", ctypes.c_ulong),
            ("time", ctypes.c_ulong),
            ("dwExtraInfo", ctypes.c_ulonglong),
        ]

    m = M()
    m.pt.x = x
    m.pt.y = y
    return ctypes.cast(ctypes.pointer(m), ctypes.c_void_p)


def test_mouse_blocker_blocks_inside_region():
    events = []

    def in_region(x, y):
        return 100 <= x < 200 and 100 <= y < 200

    b = MouseBlocker(in_region, lambda x, y: events.append((x, y)))
    # 区域内按下：吞掉并回调
    result = b._impl(0, 0x0201, _make_mouse_event(150, 150))
    assert result == 1
    assert events == [(150, 150)]
    # 区域内抬起：吞掉但不回调
    result = b._impl(0, 0x0202, _make_mouse_event(150, 150))
    assert result == 1
    assert events == [(150, 150)]
    # 区域外：放行
    result = b._impl(0, 0x0201, _make_mouse_event(50, 50))
    assert result != 1
    assert events == [(150, 150)]
