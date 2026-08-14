from input_hook import GlobalKeyHook, MouseReader, map_vk_to_hotkey


def test_map_vk_to_hotkey():
    assert map_vk_to_hotkey(0x11) == "ctrl"
    assert map_vk_to_hotkey(0x31) == "1"
    assert map_vk_to_hotkey(0x35) == "5"
    assert map_vk_to_hotkey(0x36) == "6"
    assert map_vk_to_hotkey(0x37) == "7"
    assert map_vk_to_hotkey(0x38) == "8"
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
