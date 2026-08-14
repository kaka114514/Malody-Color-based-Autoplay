"""屏幕截屏与像素采样。只抓包含检测点的最小矩形。"""

import ctypes
from ctypes import wintypes
from typing import List, Tuple

from PIL import Image


RGB = Tuple[int, int, int]
Point = Tuple[int, int]

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
SRCCOPY = 0x00CC0020
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


def make_bbox(points: List[Point], pad: int = 2) -> Tuple[int, int, int, int]:
    """根据屏幕坐标点列表计算带边距的 bbox (left, top, right, bottom)。"""
    if not points:
        return (0, 0, 1, 1)
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    left = max(0, min(xs) - pad)
    top = max(0, min(ys) - pad)
    right = max(xs) + pad + 1
    bottom = max(ys) + pad + 1
    return (left, top, right, bottom)


def grab_rect(rect: Tuple[int, int, int, int]) -> Image.Image:
    """用 BitBlt 截取屏幕矩形区域，返回 RGB 图像（远快于 ImageGrab）。"""
    left, top, right, bottom = rect
    width = right - left
    height = bottom - top
    if width <= 0 or height <= 0:
        return Image.new("RGB", (1, 1))

    hdc_screen = user32.GetDC(None)
    if not hdc_screen:
        raise OSError("GetDC failed")
    try:
        hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
        if not hdc_mem:
            raise OSError("CreateCompatibleDC failed")
        try:
            hbmp = gdi32.CreateCompatibleBitmap(hdc_screen, width, height)
            if not hbmp:
                raise OSError("CreateCompatibleBitmap failed")
            try:
                old = gdi32.SelectObject(hdc_mem, hbmp)
                if not gdi32.BitBlt(hdc_mem, 0, 0, width, height, hdc_screen, left, top, SRCCOPY):
                    raise OSError("BitBlt failed")

                header = BITMAPINFOHEADER()
                header.biSize = ctypes.sizeof(BITMAPINFOHEADER)
                header.biWidth = width
                header.biHeight = -height  # top-down
                header.biPlanes = 1
                header.biBitCount = 32
                header.biCompression = 0

                buf = ctypes.create_string_buffer(width * height * 4)
                if not gdi32.GetDIBits(
                    hdc_mem, hbmp, 0, height, buf,
                    ctypes.byref(BITMAPINFO(header)), DIB_RGB_COLORS,
                ):
                    raise OSError("GetDIBits failed")
                return Image.frombytes("RGB", (width, height), buf.raw, "raw", "BGRX")
            finally:
                gdi32.SelectObject(hdc_mem, old)
                gdi32.DeleteObject(hbmp)
        finally:
            gdi32.DeleteDC(hdc_mem)
    finally:
        user32.ReleaseDC(None, hdc_screen)


def sample_pixel(img: Image.Image, x: int, y: int) -> RGB:
    """读取图像内 (x, y) 的 RGB 像素。"""
    return tuple(img.getpixel((int(x), int(y))))[:3]


def sample_points(img: Image.Image, points: List[Point]) -> List[RGB]:
    """按图像内相对坐标批量采样。"""
    return [sample_pixel(img, x, y) for x, y in points]
