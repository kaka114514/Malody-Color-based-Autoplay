"""屏幕截屏与像素采样。只抓包含检测点的最小矩形。"""

import ctypes
from ctypes import wintypes
from typing import List, Tuple

from PIL import Image

try:
    import dxcam
    import numpy as np
    _DXCAM_OK = True
except Exception:
    _DXCAM_OK = False


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


class _CaptureCache:
    """复用屏幕 DC 与内存位图，避免每帧创建销毁的开销。"""

    def __init__(self) -> None:
        self.hdc_screen = user32.GetDC(None)
        self.hdc_mem = None
        self.hbmp = None
        self.old_bmp = None
        self.buf = None
        self.width = 0
        self.height = 0

    def grab(self, rect: Tuple[int, int, int, int]) -> Image.Image:
        left, top, right, bottom = rect
        width = right - left
        height = bottom - top
        if width <= 0 or height <= 0:
            return Image.new("RGB", (1, 1))

        if self.hdc_mem is None or self.width != width or self.height != height:
            if self.hbmp:
                gdi32.SelectObject(self.hdc_mem, self.old_bmp)
                gdi32.DeleteObject(self.hbmp)
            if self.hdc_mem:
                gdi32.DeleteDC(self.hdc_mem)
            self.hdc_mem = gdi32.CreateCompatibleDC(self.hdc_screen)
            self.hbmp = gdi32.CreateCompatibleBitmap(self.hdc_screen, width, height)
            self.old_bmp = gdi32.SelectObject(self.hdc_mem, self.hbmp)
            self.buf = ctypes.create_string_buffer(width * height * 4)
            self.width = width
            self.height = height

        if not gdi32.BitBlt(self.hdc_mem, 0, 0, width, height, self.hdc_screen, left, top, SRCCOPY):
            raise OSError("BitBlt failed")

        header = BITMAPINFOHEADER()
        header.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        header.biWidth = width
        header.biHeight = -height
        header.biPlanes = 1
        header.biBitCount = 32
        header.biCompression = 0
        if not gdi32.GetDIBits(
            self.hdc_mem, self.hbmp, 0, height, self.buf,
            ctypes.byref(BITMAPINFO(header)), DIB_RGB_COLORS,
        ):
            raise OSError("GetDIBits failed")
        return Image.frombytes("RGB", (width, height), self.buf.raw, "raw", "BGRX")


_capture_cache = None

_dxcam_camera = None
_screen_size = None


def _get_screen_size() -> Tuple[int, int]:
    global _screen_size
    if _screen_size is None:
        _screen_size = (
            ctypes.windll.user32.GetSystemMetrics(0),
            ctypes.windll.user32.GetSystemMetrics(1),
        )
    return _screen_size


def _get_dxcam():
    global _dxcam_camera
    if _dxcam_camera is None:
        _dxcam_camera = dxcam.create(output_color="RGB")
    return _dxcam_camera


def grab_rect(rect: Tuple[int, int, int, int]) -> Image.Image:
    """截取屏幕矩形区域：优先 DXGI（dxcam，硬件加速），失败回退 BitBlt。"""
    left, top, right, bottom = rect
    if _DXCAM_OK:
        sw, sh = _get_screen_size()
        if left >= 0 and top >= 0 and right <= sw and bottom <= sh:
            try:
                frame = _get_dxcam().grab(region=rect)
                if frame is not None:
                    return Image.fromarray(frame)
            except Exception:
                pass
    global _capture_cache
    if _capture_cache is None:
        _capture_cache = _CaptureCache()
    return _capture_cache.grab(rect)


def sample_pixel(img: Image.Image, x: int, y: int) -> RGB:
    """读取图像内 (x, y) 的 RGB 像素。"""
    return tuple(img.getpixel((int(x), int(y))))[:3]


def sample_points(img: Image.Image, points: List[Point]) -> List[RGB]:
    """按图像内相对坐标批量采样（用快速像素访问器）。"""
    pixels = img.load()
    return [tuple(pixels[x, y])[:3] for x, y in points]
