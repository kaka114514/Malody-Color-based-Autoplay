"""从 exe 提取图标并转为 PIL 图像。"""

import ctypes
import os
import tempfile
from ctypes import wintypes
from typing import Optional

from PIL import Image, ImageDraw, ImageFont


user32 = ctypes.windll.user32
shell32 = ctypes.windll.shell32
gdi32 = ctypes.windll.gdi32
DI_NORMAL = 3
DIB_RGB_COLORS = 0


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER)]


def extract_exe_icon(exe_path: str, size: int = 32) -> Optional[Image.Image]:
    """提取 exe 的第一个大图标并绘制为指定尺寸的 RGB 图像。"""
    hicons = (ctypes.c_void_p * 1)()
    count = shell32.ExtractIconExW(exe_path, 0, hicons, None, 1)
    if count <= 0 or not hicons[0]:
        return None
    hicon = hicons[0]
    try:
        hdc_screen = user32.GetDC(None)
        try:
            hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
            try:
                header = BITMAPINFOHEADER()
                header.biSize = ctypes.sizeof(BITMAPINFOHEADER)
                header.biWidth = size
                header.biHeight = -size
                header.biPlanes = 1
                header.biBitCount = 32
                header.biCompression = 0
                bits = ctypes.c_void_p()
                hbmp = gdi32.CreateDIBSection(
                    hdc_mem, ctypes.byref(BITMAPINFO(header)),
                    DIB_RGB_COLORS, ctypes.byref(bits), None, 0,
                )
                try:
                    old = gdi32.SelectObject(hdc_mem, hbmp)
                    # 清空像素（alpha=0，透明背景）
                    ctypes.memset(bits, 0, size * size * 4)
                    if not user32.DrawIconEx(hdc_mem, 0, 0, hicon, size, size, 0, None, DI_NORMAL):
                        return None
                    buf = ctypes.string_at(bits, size * size * 4)
                    gdi32.SelectObject(hdc_mem, old)
                    return Image.frombytes("RGBA", (size, size), buf, "raw", "BGRA")
                finally:
                    gdi32.DeleteObject(hbmp)
            finally:
                gdi32.DeleteDC(hdc_mem)
        finally:
            user32.ReleaseDC(None, hdc_screen)
    finally:
        user32.DestroyIcon(hicon)


def extract_exe_hicons(exe_path: str):
    """提取 exe 的大/小图标句柄（HICON）。返回 (hicon_large, hicon_small) 或 (None, None)。"""
    large = (ctypes.c_void_p * 1)()
    small = (ctypes.c_void_p * 1)()
    count = shell32.ExtractIconExW(exe_path, 0, large, small, 1)
    if count <= 0:
        return None, None
    return int(large[0] or 0) or None, int(small[0] or 0) or None


def make_app_icon(exe_path: str, size: int = 32) -> Optional[Image.Image]:
    """Malody 游戏图标 + 右上角红色 A（Autoplay 标识）。"""
    img = extract_exe_icon(exe_path, size)
    if img is None:
        return None
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arialbd.ttf", max(12, size // 2))
    except Exception:
        font = ImageFont.load_default()
    draw.text((size - size // 2, -2), "A", fill=(255, 0, 0, 255), font=font)
    return img


def icon_to_hicon(img: Image.Image):
    """PIL RGBA 图像 → HICON（经临时 .ico 加载）。"""
    fd, path = tempfile.mkstemp(suffix=".ico")
    os.close(fd)
    try:
        img.save(path, format="ICO")
        hicon = user32.LoadImageW(None, path, 1, 0, 0, 0x0010)  # IMAGE_ICON, LR_LOADFROMFILE
        return int(hicon) or None
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
