"""用 Pillow 生成一个 32x32 吸管光标（.cur）。

Pillow 12 移除了 CUR 保存格式，这里手工构造 CUR 容器
（ICONDIR + ICONDIRENTRY + PNG 图像数据，Windows Vista+ 支持）。
"""

import io
import struct
from pathlib import Path

from PIL import Image, ImageDraw


def generate_cursor(path: Path) -> None:
    img = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.polygon(
        [(4, 22), (10, 28), (24, 14), (22, 12), (18, 16), (12, 10), (10, 12)],
        fill=(200, 60, 200, 255), outline=(255, 255, 255, 255),
    )
    d.rectangle([(4, 22), (10, 28)], fill=(180, 180, 180, 255), outline=(255, 255, 255, 255))
    d.line([(7, 25), (9, 27)], fill=(255, 255, 255, 255))
    png_buf = io.BytesIO()
    img.save(png_buf, format="PNG")
    png = png_buf.getvalue()
    hotspot = (3, 3)  # 吸管尖端热区
    header = struct.pack("<HHH", 0, 2, 1)  # reserved, type=cursor, count=1
    entry = struct.pack(
        "<BBBBHHII",
        32, 32, 0, 0,
        hotspot[0], hotspot[1],
        len(png), 22,
    )
    Path(path).write_bytes(header + entry + png)


if __name__ == "__main__":
    import sys
    generate_cursor(Path(sys.argv[1]))
