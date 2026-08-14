import struct
from pathlib import Path

import cursor_make
from input_hook import GlobalKeyHook, MouseReader, map_vk_to_hotkey


def test_map_vk_to_hotkey():
    assert map_vk_to_hotkey(0x31) == "1"
    assert map_vk_to_hotkey(0x35) == "5"
    assert map_vk_to_hotkey(0x36) == "6"
    assert map_vk_to_hotkey(0x37) == "7"
    assert map_vk_to_hotkey(0x38) == "8"
    assert map_vk_to_hotkey(0x41) is None  # 'A'
    assert map_vk_to_hotkey(0) is None


def test_cursor_generated(tmp_path: Path):
    path = tmp_path / "cursor.cur"
    cursor_make.generate_cursor(path)
    assert path.exists()
    data = path.read_bytes()
    reserved, ctype, count = struct.unpack("<HHH", data[:6])
    assert (reserved, ctype, count) == (0, 2, 1)  # type=2 表示光标
    width, height, _, _, hx, hy, size, offset = struct.unpack("<BBBBHHII", data[6:22])
    assert (width, height) == (32, 32)
    assert offset == 22
    assert len(data) - offset == size
    assert data[offset:offset + 8] == b"\x89PNG\r\n\x1a\n"  # PNG 图像数据


def test_hook_start_stop():
    events = []
    hook = GlobalKeyHook(events.append)
    hook.start()
    hook.stop()


def test_mouse_reader_cursor_pos():
    x, y = MouseReader.cursor_pos()
    assert isinstance(x, int)
    assert isinstance(y, int)
