"""屏幕截屏与像素采样。只抓包含检测点的最小矩形。"""

from typing import List, Tuple

from PIL import Image, ImageGrab


RGB = Tuple[int, int, int]
Point = Tuple[int, int]


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
    """截取屏幕矩形区域，返回 RGB 图像。"""
    return ImageGrab.grab(bbox=rect)


def sample_pixel(img: Image.Image, x: int, y: int) -> RGB:
    """读取图像内 (x, y) 的 RGB 像素。"""
    return tuple(img.getpixel((int(x), int(y))))[:3]


def sample_points(img: Image.Image, points: List[Point]) -> List[RGB]:
    """按图像内相对坐标批量采样。"""
    return [sample_pixel(img, x, y) for x, y in points]
