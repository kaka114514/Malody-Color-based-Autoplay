"""颜色集合匹配：RGB 欧氏距离 + 容差。"""

from typing import List, Tuple


RGB = Tuple[int, int, int]


def _distance(a: RGB, b: RGB) -> float:
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


class ColorMatcher:
    def __init__(self, tolerance: int = 40):
        self._tolerance = max(0, int(tolerance))
        self._backgrounds: List[RGB] = []
        self._keys: List[RGB] = []

    def set_tolerance(self, tol: int) -> None:
        self._tolerance = max(0, int(tol))

    def add_background(self, rgb: RGB) -> None:
        rgb = tuple(rgb)
        if rgb not in self._backgrounds:
            self._backgrounds.append(rgb)

    def remove_background(self, rgb: RGB) -> bool:
        rgb = tuple(rgb)
        if rgb in self._backgrounds:
            self._backgrounds.remove(rgb)
            return True
        return False

    def add_key(self, rgb: RGB) -> None:
        rgb = tuple(rgb)
        if rgb not in self._keys:
            self._keys.append(rgb)

    def remove_key(self, rgb: RGB) -> bool:
        rgb = tuple(rgb)
        if rgb in self._keys:
            self._keys.remove(rgb)
            return True
        return False

    def is_background(self, rgb: RGB) -> bool:
        return any(_distance(rgb, c) <= self._tolerance for c in self._backgrounds)

    def is_key(self, rgb: RGB) -> bool:
        return any(_distance(rgb, c) <= self._tolerance for c in self._keys)

    def classify(self, rgb: RGB) -> str:
        """优先级：按键色 > 背景色 > unknown。"""
        if self.is_key(rgb):
            return "key"
        if self.is_background(rgb):
            return "background"
        return "unknown"

    @property
    def tolerance(self) -> int:
        return self._tolerance

    @property
    def background_colors(self) -> List[RGB]:
        return list(self._backgrounds)

    @property
    def key_colors(self) -> List[RGB]:
        return list(self._keys)
