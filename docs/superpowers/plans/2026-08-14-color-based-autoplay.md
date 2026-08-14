# 基于颜色检测的 Malody 自动游玩工具 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现一个带 tkinter 交互界面的 Malody 自动游玩工具：选择游戏窗口并绘制覆盖层，设置判定线与列检测点，吸取背景/按键颜色，以 ≥100 次/秒的频率检测判定点颜色变化并自动按键。

**Architecture:** tkinter 提供控制界面与透明覆盖层；独立检测线程通过 GDI 截屏（Pillow ImageGrab）读取蓝点中心像素，颜色匹配后由调度器按延迟注入按键（SendInput）；pywin32 提供窗口追踪与全局键盘钩子。模块间通过明确的类接口解耦，核心逻辑（颜色匹配、配置、调度）可单测。

**Tech Stack:** Python 3.11（tkinter 标准库）、pywin32、Pillow、pytest

**Spec:** [docs/superpowers/specs/2026-08-14-color-based-autoplay-design.md](../specs/2026-08-14-color-based-autoplay-design.md)

## Global Constraints

- 项目根目录：`D:\App\Game\color-based Autoplay`（下文所有路径相对于此）
- Python 版本：3.11（仅标准库 + `pywin32>=306`、`Pillow>=10.0`、`pytest>=7`）
- 覆盖层：黄框 10px、红线 3px、蓝点为空心圆环（中心透明 ≥6px），红线在蓝点处断开 ±6px
- 延迟语义：正数 = 推后 N ms 按下；负数等效为 0（`delay = max(0, delay_ms)`）
- 检测：仅读取蓝点中心像素；检测线程独立；单帧 ≤10ms，目标 ≥100 次/秒
- 判定优先级：命中按键色 > 命中背景色 > 保持上一帧状态
- 配置保存到程序根目录 `config.json`（UTF-8）；判定线与列存相对比例（0~1）；不保存游戏窗口
- 全局热键：设置模式 `1/2/3`，运行/任意模式 `4`=延迟-5ms、`5`=延迟+5ms，吸管模式 `1`=激活吸管
- 游戏以普通权限运行；本工具默认普通权限，注入失败时提示以管理员启动
- 每个任务先写失败测试 → 验证失败 → 实现 → 验证通过 → commit
- 所有交互文案使用中文

---

### Task 1: 项目初始化与 config 模块

**Files:**
- Create: `requirements.txt`
- Create: `requirements-dev.txt`
- Create: `.gitignore`
- Create: `config.py`
- Create: `tests/test_config.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `config.DEFAULT_CONFIG: dict`
  - `config.load_config(path: Path) -> dict`
  - `config.save_config(path: Path, cfg: dict) -> None`
  - `config.normalize_config(raw: dict) -> dict`
  - `tests/` 目录存在，pytest 可运行

- [ ] **Step 1: 初始化 git 仓库与依赖文件**

运行（项目根目录）：

```bash
git init
```

创建 `requirements.txt`：

```text
pywin32>=306
Pillow>=10.0
```

创建 `requirements-dev.txt`：

```text
-r requirements.txt
pytest>=7
```

创建 `.gitignore`：

```text
__pycache__/
*.pyc
.pytest_cache/
*.spec
build/
dist/
```

- [ ] **Step 2: 写失败的测试**

创建 `tests/test_config.py`：

```python
import json
from pathlib import Path

import pytest

from config import DEFAULT_CONFIG, load_config, save_config, normalize_config


def test_default_config_fields(tmp_path: Path):
    cfg = load_config(tmp_path / "missing.json")
    assert cfg["judgement_line_y"] == DEFAULT_CONFIG["judgement_line_y"]
    assert isinstance(cfg["delay_ms"], int)
    assert isinstance(cfg["tolerance"], int)
    assert isinstance(cfg["columns"], list)


def test_round_trip(tmp_path: Path):
    path = tmp_path / "cfg.json"
    cfg = {
        "judgement_line_y": 0.75,
        "column_count": 4,
        "key_string": "DFJK",
        "columns": [
            {"x": 0.2, "key": "D"},
            {"x": 0.4, "key": "F"},
            {"x": 0.6, "key": "J"},
            {"x": 0.8, "key": "K"},
        ],
        "background_colors": [[10, 10, 15]],
        "key_colors": [[240, 80, 90], [255, 200, 60]],
        "delay_ms": -5,
        "tolerance": 40,
    }
    save_config(path, cfg)
    loaded = load_config(path)
    assert loaded == cfg


def test_corrupted_json_returns_defaults(tmp_path: Path):
    path = tmp_path / "broken.json"
    path.write_text("{not valid json", encoding="utf-8")
    cfg = load_config(path)
    assert cfg["delay_ms"] == DEFAULT_CONFIG["delay_ms"]


def test_normalize_fills_missing_and_keeps_valid(tmp_path: Path):
    raw = {"delay_ms": 20}
    cfg = normalize_config(raw)
    assert cfg["delay_ms"] == 20
    assert cfg["tolerance"] == DEFAULT_CONFIG["tolerance"]


def test_normalize_clamps_bad_types(tmp_path: Path):
    raw = {"delay_ms": "abc", "tolerance": "x", "judgement_line_y": 99}
    cfg = normalize_config(raw)
    assert cfg["delay_ms"] == DEFAULT_CONFIG["delay_ms"]
    assert cfg["tolerance"] == DEFAULT_CONFIG["tolerance"]
    assert 0.0 <= cfg["judgement_line_y"] <= 1.0
```

- [ ] **Step 3: 运行测试验证失败**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'config'`）

- [ ] **Step 4: 实现 config 模块**

创建 `config.py`：

```python
"""配置的读取、归一化与保存。"""

import json
from pathlib import Path
from typing import Any


DEFAULT_CONFIG: dict = {
    "judgement_line_y": 0.78,          # 判定线相对高度 0~1
    "column_count": 4,                 # 列数
    "key_string": "DFJK",              # 按键绑定原始字符串
    "columns": [                       # 每列：相对 x 与按键
        {"x": 0.2, "key": "D"},
        {"x": 0.4, "key": "F"},
        {"x": 0.6, "key": "J"},
        {"x": 0.8, "key": "K"},
    ],
    "background_colors": [],           # [ [r,g,b], ... ]
    "key_colors": [],                  # [ [r,g,b], ... ]
    "delay_ms": 0,                     # 允许负数，运行时按 max(0, v) 处理
    "tolerance": 40,                   # 颜色欧氏距离容差 0~255
}


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _norm_color(raw: Any) -> list | None:
    """校验并归一化单个 [r,g,b]；非法返回 None。"""
    if not isinstance(raw, (list, tuple)) or len(raw) != 3:
        return None
    try:
        vals = [int(round(float(c))) for c in raw]
    except (TypeError, ValueError):
        return None
    if any(v < 0 or v > 255 for v in vals):
        return None
    return vals


def normalize_config(raw: dict) -> dict:
    """用默认值补全缺失字段，修正非法类型，返回完整配置。"""
    cfg = dict(DEFAULT_CONFIG)
    cfg.update(raw if isinstance(raw, dict) else {})

    try:
        cfg["judgement_line_y"] = _clamp(float(cfg["judgement_line_y"]), 0.0, 1.0)
    except (TypeError, ValueError):
        cfg["judgement_line_y"] = DEFAULT_CONFIG["judgement_line_y"]

    for field in ("delay_ms", "tolerance", "column_count"):
        try:
            value = int(cfg[field])
            if field == "column_count" and value < 1:
                value = DEFAULT_CONFIG["column_count"]
            cfg[field] = value
        except (TypeError, ValueError):
            cfg[field] = DEFAULT_CONFIG[field]

    if not isinstance(cfg["key_string"], str):
        cfg["key_string"] = DEFAULT_CONFIG["key_string"]

    columns = []
    if isinstance(cfg["columns"], list):
        for item in cfg["columns"]:
            if not isinstance(item, dict):
                continue
            try:
                x = _clamp(float(item.get("x", 0.5)), 0.0, 1.0)
            except (TypeError, ValueError):
                continue
            key = str(item.get("key", "A")) or "A"
            columns.append({"x": x, "key": key})
    cfg["columns"] = columns

    for field in ("background_colors", "key_colors"):
        colors = []
        if isinstance(cfg[field], list):
            for item in cfg[field]:
                c = _norm_color(item)
                if c is not None:
                    colors.append(c)
        cfg[field] = colors

    return cfg


def load_config(path: Path) -> dict:
    """读取配置；文件缺失或损坏时返回默认配置。"""
    if not Path(path).exists():
        return dict(DEFAULT_CONFIG)
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULT_CONFIG)
    return normalize_config(raw)


def save_config(path: Path, cfg: dict) -> None:
    """保存配置（UTF-8，缩进 2）。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(normalize_config(cfg), ensure_ascii=False, indent=2), encoding="utf-8")
```

- [ ] **Step 5: 运行测试验证通过**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 6: Commit**

```bash
git add requirements.txt requirements-dev.txt .gitignore config.py tests/test_config.py
git commit -m "feat: 初始化项目并实现配置模块"
```

---

### Task 2: color_matcher 颜色匹配模块

**Files:**
- Create: `color_matcher.py`
- Create: `tests/test_color_matcher.py`

**Interfaces:**
- Consumes: 无（纯逻辑）
- Produces:
  - `class ColorMatcher`：
    - `__init__(self, tolerance: int = 40)`
    - `set_tolerance(self, tol: int) -> None`
    - `add_background(self, rgb: tuple) -> None` / `remove_background(self, rgb: tuple) -> bool`
    - `add_key(self, rgb: tuple) -> None` / `remove_key(self, rgb: tuple) -> bool`
    - `is_background(self, rgb: tuple) -> bool` / `is_key(self, rgb: tuple) -> bool`
    - `classify(self, rgb: tuple) -> str`（返回 `"key"` / `"background"` / `"unknown"`）
    - 属性：`background_colors: list[tuple]`、`key_colors: list[tuple]`

- [ ] **Step 1: 写失败的测试**

创建 `tests/test_color_matcher.py`：

```python
from color_matcher import ColorMatcher


def test_exact_match():
    m = ColorMatcher(tolerance=0)
    m.add_background((10, 10, 15))
    m.add_key((240, 80, 90))
    assert m.is_background((10, 10, 15))
    assert m.is_key((240, 80, 90))
    assert m.classify((10, 10, 15)) == "background"
    assert m.classify((240, 80, 90)) == "key"


def test_tolerance_boundary():
    m = ColorMatcher(tolerance=10)
    m.add_key((100, 100, 100))
    assert m.is_key((105, 100, 100))       # 距离 5 <= 10
    assert not m.is_key((130, 100, 100))   # 距离 30 > 10


def test_key_wins_over_background():
    m = ColorMatcher(tolerance=200)
    m.add_background((10, 10, 15))
    m.add_key((20, 20, 25))
    assert m.classify((15, 15, 20)) == "key"


def test_unknown_when_no_match():
    m = ColorMatcher(tolerance=0)
    m.add_background((0, 0, 0))
    assert m.classify((255, 255, 255)) == "unknown"


def test_remove():
    m = ColorMatcher(tolerance=0)
    m.add_key((1, 2, 3))
    assert m.remove_key((1, 2, 3)) is True
    assert not m.is_key((1, 2, 3))
    assert m.remove_key((9, 9, 9)) is False


def test_empty_matcher_is_unknown():
    m = ColorMatcher()
    assert m.classify((0, 0, 0)) == "unknown"
    assert m.background_colors == []
    assert m.key_colors == []


def test_no_duplicates():
    m = ColorMatcher(tolerance=0)
    m.add_key((1, 2, 3))
    m.add_key((1, 2, 3))
    assert len(m.key_colors) == 1
```

- [ ] **Step 2: 运行测试验证失败**

Run: `python -m pytest tests/test_color_matcher.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'color_matcher'`）

- [ ] **Step 3: 实现 color_matcher**

创建 `color_matcher.py`：

```python
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
```

- [ ] **Step 4: 运行测试验证通过**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add color_matcher.py tests/test_color_matcher.py
git commit -m "feat: 实现颜色集合匹配模块"
```

---

### Task 3: window_utils 窗口工具

**Files:**
- Create: `window_utils.py`
- Create: `tests/test_window_utils.py`

**Interfaces:**
- Consumes: 无（依赖 pywin32）
- Produces:
  - `set_process_dpi_aware() -> None`
  - `find_window_at_point(x: int, y: int) -> int | None`
  - `get_window_rect(hwnd: int) -> tuple[int, int, int, int]`（`(left, top, right, bottom)` 屏幕坐标）
  - `set_foreground(hwnd: int) -> bool`
  - `is_minimized(hwnd: int) -> bool`

- [ ] **Step 1: 写失败的测试**

创建 `tests/test_window_utils.py`：

```python
import tkinter as tk
import time

import pytest

import window_utils as wu


def test_find_window_at_point_and_rect():
    """创建一个小窗口，点击其中心应返回该窗口句柄，矩形应包含该点。"""
    root = tk.Tk()
    root.geometry("240x120+200+200")
    root.update_idletasks()
    root.update()
    time.sleep(0.2)
    hwnd = wu.find_window_at_point(320, 260)  # 窗口中心（不含标题栏偏移）
    assert hwnd is not None
    rect = wu.get_window_rect(hwnd)
    left, top, right, bottom = rect
    assert left <= 320 <= right
    assert top <= 260 <= bottom
    root.destroy()


def test_rect_shape():
    hwnd = wu.find_window_at_point(320, 260)
    if hwnd is None:
        pytest.skip("no window found")
    rect = wu.get_window_rect(hwnd)
    assert len(rect) == 4
    assert rect[2] > rect[0]
    assert rect[3] > rect[1]


def test_is_minimized_after_iconify():
    root = tk.Tk()
    root.geometry("240x120+200+200")
    root.update_idletasks()
    root.update()
    time.sleep(0.2)
    hwnd = wu.find_window_at_point(320, 260)
    assert hwnd is not None
    root.iconify()
    root.update()
    time.sleep(0.2)
    assert wu.is_minimized(hwnd) is True
    root.destroy()
```

- [ ] **Step 2: 运行测试验证失败**

Run: `python -m pytest tests/test_window_utils.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'window_utils'`）

- [ ] **Step 3: 实现 window_utils**

创建 `window_utils.py`：

```python
"""Windows 窗口操作：选取、矩形、置前、可见性。"""

import ctypes
from typing import Optional, Tuple

import win32gui
import win32con


Rect = Tuple[int, int, int, int]


def set_process_dpi_aware() -> None:
    """让进程感知 DPI，保证屏幕坐标一致。失败时静默忽略。"""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # PROCESS_PER_MONITOR_DPI_AWARE
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def find_window_at_point(x: int, y: int) -> Optional[int]:
    """返回屏幕上 (x, y) 处最顶层窗口句柄；无窗口返回 None。"""
    hwnd = win32gui.WindowFromPoint((x, y))
    return int(hwnd) if hwnd else None


def get_window_rect(hwnd: int) -> Rect:
    """返回窗口屏幕矩形 (left, top, right, bottom)。"""
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    return int(left), int(top), int(right), int(bottom)


def set_foreground(hwnd: int) -> bool:
    """将窗口置为前台。"""
    try:
        win32gui.SetForegroundWindow(hwnd)
        return True
    except win32gui.error:
        return False


def is_minimized(hwnd: int) -> bool:
    """窗口是否最小化。"""
    return bool(win32gui.IsIconic(hwnd))


def is_visible(hwnd: int) -> bool:
    return bool(win32gui.IsWindowVisible(hwnd))
```

- [ ] **Step 4: 运行测试验证通过**

Run: `python -m pytest tests/test_window_utils.py -v`
Expected: 全部 PASS（窗口会短暂闪现，正常）

- [ ] **Step 5: Commit**

```bash
git add window_utils.py tests/test_window_utils.py
git commit -m "feat: 实现窗口工具模块"
```

---

### Task 4: capture 截屏模块

**Files:**
- Create: `capture.py`
- Create: `tests/test_capture.py`

**Interfaces:**
- Consumes: 无（依赖 Pillow）
- Produces:
  - `grab_rect(rect: tuple[int,int,int,int]) -> Image.Image`（屏幕坐标矩形截屏）
  - `make_bbox(points: list[tuple[int,int]], pad: int = 2) -> tuple[int,int,int,int]`
  - `sample_pixel(img: Image.Image, x: int, y: int) -> tuple[int,int,int]`
  - `sample_points(img: Image.Image, points: list[tuple[int,int]]) -> list[tuple[int,int,int]]`

- [ ] **Step 1: 写失败的测试**

创建 `tests/test_capture.py`：

```python
from PIL import Image

from capture import make_bbox, sample_pixel, sample_points


def test_make_bbox_pads_points():
    bbox = make_bbox([(10, 20), (30, 40)], pad=2)
    assert bbox == (8, 18, 32, 42)


def test_make_bbox_single_point():
    bbox = make_bbox([(100, 100)], pad=0)
    assert bbox == (100, 100, 101, 101)


def test_sample_pixel():
    img = Image.new("RGB", (4, 4), (1, 2, 3))
    assert sample_pixel(img, 2, 2) == (1, 2, 3)


def test_sample_points_relative():
    img = Image.new("RGB", (10, 10), (0, 0, 0))
    img.putpixel((2, 3), (255, 0, 0))
    img.putpixel((5, 6), (0, 255, 0))
    colors = sample_points(img, [(2, 3), (5, 6)])
    assert colors == [(255, 0, 0), (0, 255, 0)]
```

- [ ] **Step 2: 运行测试验证失败**

Run: `python -m pytest tests/test_capture.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'capture'`）

- [ ] **Step 3: 实现 capture**

创建 `capture.py`：

```python
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
```

- [ ] **Step 4: 运行测试验证通过**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add capture.py tests/test_capture.py
git commit -m "feat: 实现截屏与像素采样模块"
```

---

### Task 5: overlay 透明覆盖层

**Files:**
- Create: `overlay.py`
- Create: `tests/test_overlay.py`

**Interfaces:**
- Consumes: tkinter（Tk 实例由调用方创建）
- Produces:
  - `class Overlay`：
    - `__init__(self, root: tk.Tk)`
    - `set_game_rect(self, rect: tuple[int,int,int,int]) -> None`（屏幕坐标）
    - `set_judgement_y(self, rel_y: float) -> None`
    - `set_columns(self, rel_xs: list[float], selected: int = -1) -> None`
    - `clear_columns(self) -> None`
    - `show(self) / hide(self)`

绘制规则：黄框 10px（`#FFD800`）、红线 3px（`#FF3B30`）在蓝点 x 处左右各断 6px、蓝点空心圆环（外径 5px 线宽 2px，`#3B82F6`），透明色 `#010203`。

- [ ] **Step 1: 写失败的测试**

创建 `tests/test_overlay.py`：

```python
import tkinter as tk
import time

from overlay import Overlay


def _make_overlay():
    root = tk.Tk()
    ov = Overlay(root)
    ov.set_game_rect((100, 100, 500, 400))
    ov.set_judgement_y(0.5)
    ov.set_columns([0.25, 0.5, 0.75], selected=0)
    root.update_idletasks()
    root.update()
    time.sleep(0.1)
    return root, ov


def test_overlay_creates_drawings():
    root, ov = _make_overlay()
    canvas = ov._canvas
    n_before = len(canvas.find_all())
    assert n_before > 0
    root.destroy()


def test_overlay_hide_show():
    root, ov = _make_overlay()
    ov.hide()
    root.update()
    assert not ov._window.winfo_ismapped()
    ov.show()
    root.update()
    assert ov._window.winfo_ismapped()
    root.destroy()


def test_overlay_clear_columns():
    root, ov = _make_overlay()
    ov.clear_columns()
    root.update()
    root.destroy()
```

- [ ] **Step 2: 运行测试验证失败**

Run: `python -m pytest tests/test_overlay.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'overlay'`）

- [ ] **Step 3: 实现 overlay**

创建 `overlay.py`：

```python
"""透明覆盖层：黄框、红线、蓝点。点击穿透、置顶、不抢焦点。"""

import tkinter as tk
from typing import List, Optional, Tuple

import win32gui
import win32con


TRANSPARENT_KEY = "#010203"   # tkinter 透明色
YELLOW = "#FFD800"
RED = "#FF3B30"
BLUE = "#3B82F6"
FRAME_WIDTH = 10              # 黄框线宽
LINE_WIDTH = 3                # 红线线宽
NOTCH = 6                     # 红线在蓝点处断开半径
RING_RADIUS = 5               # 蓝点外径
RING_WIDTH = 2


class Overlay:
    def __init__(self, root: tk.Tk):
        self._root = root
        self._window = tk.Toplevel(root)
        self._window.overrideredirect(True)
        self._window.attributes("-topmost", True)
        self._window.attributes("-transparentcolor", TRANSPARENT_KEY)
        self._canvas = tk.Canvas(
            self._window,
            bg=TRANSPARENT_KEY,
            highlightthickness=0,
            bd=0,
        )
        self._canvas.pack(fill="both", expand=True)
        self._rect: Optional[Tuple[int, int, int, int]] = None
        self._rel_y = 0.5
        self._rel_xs: List[float] = []
        self._selected = -1
        self._apply_click_through()

    def _apply_click_through(self) -> None:
        """加扩展样式：分层、点击穿透、工具窗口、不激活。"""
        hwnd = int(self._window.winfo_id())
        style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
        style |= (
            win32con.WS_EX_LAYERED
            | win32con.WS_EX_TRANSPARENT
            | win32con.WS_EX_TOOLWINDOW
            | win32con.WS_EX_NOACTIVATE
        )
        win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, style)

    def set_game_rect(self, rect: Tuple[int, int, int, int]) -> None:
        """定位覆盖层到游戏窗口矩形并重绘。"""
        left, top, right, bottom = rect
        width = max(1, right - left)
        height = max(1, bottom - top)
        self._rect = rect
        self._window.geometry(f"{width}x{height}+{left}+{top}")
        self._canvas.configure(width=width, height=height)
        self._redraw()

    def set_judgement_y(self, rel_y: float) -> None:
        self._rel_y = max(0.0, min(1.0, rel_y))
        self._redraw()

    def set_columns(self, rel_xs: List[float], selected: int = -1) -> None:
        self._rel_xs = list(rel_xs)
        self._selected = selected
        self._redraw()

    def clear_columns(self) -> None:
        self._rel_xs = []
        self._selected = -1
        self._redraw()

    def show(self) -> None:
        self._window.deiconify()
        self._window.lift()

    def hide(self) -> None:
        self._window.withdraw()

    def _redraw(self) -> None:
        c = self._canvas
        c.delete("all")
        if self._rect is None:
            return
        width = int(c.cget("width"))
        height = int(c.cget("height"))

        # 黄框（窗口边缘，10px）
        c.create_rectangle(
            0, 0, width - 1, height - 1,
            outline=YELLOW, width=FRAME_WIDTH,
        )

        # 红线（3px，在蓝点 x 处断开 ±NOTCH）
        y = self._rel_y * height
        xs = [rel_x * width for rel_x in self._rel_xs]
        segments = []
        prev = 0
        for cx in sorted(xs):
            a = max(prev, cx - NOTCH)
            b = cx + NOTCH
            if a > prev:
                segments.append((prev, a))
            prev = b
        if prev < width:
            segments.append((prev, width))
        for a, b in segments:
            c.create_line(a, y, b, y, fill=RED, width=LINE_WIDTH)

        # 蓝点：空心圆环（中心透明，供检测取色）
        for i, rel_x in enumerate(self._rel_xs):
            cx = rel_x * width
            outline = BLUE
            if i == self._selected:
                outline = "#00D0FF"
            c.create_oval(
                cx - RING_RADIUS, y - RING_RADIUS,
                cx + RING_RADIUS, y + RING_RADIUS,
                outline=outline, width=RING_WIDTH, fill=TRANSPARENT_KEY,
            )
```

- [ ] **Step 4: 运行测试验证通过**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS（测试窗口会短暂闪现）

- [ ] **Step 5: Commit**

```bash
git add overlay.py tests/test_overlay.py
git commit -m "feat: 实现透明覆盖层"
```

---

### Task 6: input_hook 全局钩子与吸管光标

**Files:**
- Create: `input_hook.py`
- Create: `cursor_make.py`
- Create: `cursor.cur`（由 `cursor_make.py` 生成）
- Create: `tests/test_input_hook.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `map_vk_to_hotkey(vk: int) -> str | None`（只返回 `"1"`~`"5"`）
  - `class GlobalKeyHook`：`__init__(self, callback: Callable[[str], None])`、`start() -> None`、`stop() -> None`
  - `class MouseReader`：`left_pressed() -> bool`、`cursor_pos() -> tuple[int,int]`
  - `set_global_cursor(cur_path: Path) -> None`、`restore_system_cursor() -> None`
  - `generate_cursor(path: Path) -> None`（Pillow 绘制吸管图标并保存 .cur）

- [ ] **Step 1: 写失败的测试**

创建 `tests/test_input_hook.py`：

```python
from pathlib import Path

from PIL import Image

import cursor_make
from input_hook import GlobalKeyHook, MouseReader, map_vk_to_hotkey


def test_map_vk_to_hotkey():
    assert map_vk_to_hotkey(0x31) == "1"
    assert map_vk_to_hotkey(0x35) == "5"
    assert map_vk_to_hotkey(0x41) is None  # 'A'
    assert map_vk_to_hotkey(0) is None


def test_cursor_generated(tmp_path: Path):
    path = tmp_path / "cursor.cur"
    cursor_make.generate_cursor(path)
    assert path.exists()
    img = Image.open(path)
    assert img.size[0] == 32


def test_hook_start_stop():
    events = []
    hook = GlobalKeyHook(events.append)
    hook.start()
    hook.stop()


def test_mouse_reader_cursor_pos():
    x, y = MouseReader.cursor_pos()
    assert isinstance(x, int)
    assert isinstance(y, int)
```

- [ ] **Step 2: 运行测试验证失败**

Run: `python -m pytest tests/test_input_hook.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'input_hook'`）

- [ ] **Step 3: 实现 input_hook 与光标生成**

创建 `input_hook.py`：

```python
"""全局键盘低级钩子与鼠标状态读取。"""

import ctypes
import ctypes.wintypes
import threading
from pathlib import Path
from typing import Callable, Optional, Tuple

import win32con


WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
VK_NUMPAD_BASE = 0x60


def map_vk_to_hotkey(vk: int) -> Optional[str]:
    """数字键 1~5（含小键盘）→ "1".."5"；其它返回 None。"""
    if 0x31 <= vk <= 0x35:
        return chr(vk)
    if VK_NUMPAD_BASE + 1 <= vk <= VK_NUMPAD_BASE + 5:
        return chr(vk - VK_NUMPAD_BASE)
    return None


class GlobalKeyHook:
    """低级键盘钩子，在独立线程运行，把 1~5 数字键回调给调用方。"""

    def __init__(self, callback: Callable[[str], None]):
        self._callback = callback
        self._hook = None
        self._thread: Optional[threading.Thread] = None
        self._running = False

    def _proc(self, n_code, w_param, l_param) -> int:
        if n_code >= 0 and w_param in (WM_KEYDOWN, WM_SYSKEYDOWN):
            vk = ctypes.cast(l_param, ctypes.POINTER(ctypes.c_long)).contents.value & 0xFF
            key = map_vk_to_hotkey(vk)
            if key is not None:
                try:
                    self._callback(key)
                except Exception:
                    pass
        return ctypes.windll.user32.CallNextHookEx(self._hook, n_code, w_param, l_param)

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        self._hook = ctypes.windll.user32.SetWindowsHookExW(
            WH_KEYBOARD_LL, self._proc, None, 0
        )
        if not self._hook:
            self._running = False
            return
        msg = ctypes.wintypes.MSG()
        while self._running and ctypes.windll.user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            ctypes.windll.user32.TranslateMessage(ctypes.byref(msg))
            ctypes.windll.user32.DispatchMessageW(ctypes.byref(msg))
        ctypes.windll.user32.UnhookWindowsHookEx(self._hook)
        self._hook = None

    def stop(self) -> None:
        self._running = False
        if self._hook:
            ctypes.windll.user32.PostThreadMessageW(
                self._thread.ident, 0x0012, 0, 0  # WM_QUIT
            )
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)


class MouseReader:
    """轮询式鼠标状态（不依赖钩子）。"""

    VK_LBUTTON = 0x01

    @staticmethod
    def left_pressed() -> bool:
        state = ctypes.windll.user32.GetAsyncKeyState(MouseReader.VK_LBUTTON)
        return bool(state & 0x8000)

    @staticmethod
    def cursor_pos() -> Tuple[int, int]:
        pt = ctypes.wintypes.POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
        return int(pt.x), int(pt.y)


def set_global_cursor(cur_path: Path) -> None:
    """把系统箭头临时替换为吸管光标（取色结束后必须恢复）。"""
    hcur = ctypes.windll.user32.LoadImageW(
        None, str(cur_path), 2, 0, 0, 0x0010  # IMAGE_CURSOR, LR_LOADFROMFILE
    )
    if hcur:
        ctypes.windll.user32.SetSystemCursor(hcur, 32512)  # OCR_NORMAL


def restore_system_cursor() -> None:
    """恢复系统默认箭头光标。"""
    hcur = ctypes.windll.user32.LoadCursorW(None, 32512)  # IDC_ARROW
    if hcur:
        ctypes.windll.user32.SetSystemCursor(hcur, 32512)
```

创建 `cursor_make.py`：

```python
"""用 Pillow 生成一个 32x32 吸管光标（.cur）。"""

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
    img.save(path, format="CUR")


if __name__ == "__main__":
    import sys
    generate_cursor(Path(sys.argv[1]))
```

生成光标文件：

```bash
python cursor_make.py cursor.cur
```

- [ ] **Step 4: 运行测试验证通过**

Run: `python -m pytest tests/test_input_hook.py -v`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add input_hook.py cursor_make.py cursor.cur tests/test_input_hook.py
git commit -m "feat: 实现全局钩子与吸管光标"
```

---

### Task 7: autoplay 自动游玩引擎

**Files:**
- Create: `autoplay.py`
- Create: `tests/test_autoplay.py`

**Interfaces:**
- Consumes: `color_matcher.ColorMatcher`、`window_utils`、`capture`（见 Task 2/3/4）
- Produces:
  - `_vk_for(key: str) -> int`
  - `class KeySender`：`press(key)`、`release(key)`、`release_all()`（SendInput）
  - `class KeyScheduler`：`__init__(sender, keys, delay_ms)`、`set_delay(ms)`、`set_count(n)`、`update(i, desired, now_ms)`、`tick(now_ms)`、`reset()`
  - `class AutoplayEngine`：`__init__(matcher, hwnd, keys, rel_points, delay_ms, on_log=None, on_stopped=None)`、`start()`、`stop()`、`set_delay(ms)`、`running` 属性

调度语义：`delay = max(0, delay_ms)`；按下沿在 `now + delay` 触发（届时仍为按下期望才执行）；松开沿立即执行；中途取消未执行按下。

- [ ] **Step 1: 写失败的测试**

创建 `tests/test_autoplay.py`：

```python
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


def test_cancel_pending_press():
    s = make_scheduler(delay=50)
    s.update(0, True, 0)
    s.update(0, False, 10)  # 未执行前变回背景，取消
    s.tick(50)
    assert s._sender.events == []


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
```

- [ ] **Step 2: 运行测试验证失败**

Run: `python -m pytest tests/test_autoplay.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'autoplay'`）

- [ ] **Step 3: 实现 autoplay**

创建 `autoplay.py`：

```python
"""自动游玩引擎：识别循环 + 延迟调度 + SendInput 按键。"""

import ctypes
import threading
import time
from typing import Callable, Dict, List, Optional, Tuple

import window_utils as wu
from capture import grab_rect, make_bbox, sample_points
from color_matcher import ColorMatcher


VK_MAP = {
    "space": 0x20, "enter": 0x0D, "tab": 0x09,
    "shift": 0x10, "ctrl": 0x11, "alt": 0x12,
    "esc": 0x1B, "backspace": 0x08,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
}


def _vk_for(key: str) -> int:
    k = key.strip().lower()
    if k in VK_MAP:
        return VK_MAP[k]
    if len(k) == 1 and k.isprintable():
        return ord(k.upper())
    raise ValueError(f"无法识别按键: {key}")


class KeySender:
    """通过 SendInput 注入键盘事件。"""

    KEYEVENTF_KEYUP = 0x0002
    INPUT_KEYBOARD = 1

    def __init__(self) -> None:
        self._pressed: set = set()
        self._lock = threading.Lock()

    def press(self, key: str) -> None:
        self._send(key, down=True)
        with self._lock:
            self._pressed.add(key)

    def release(self, key: str) -> None:
        self._send(key, down=False)
        with self._lock:
            self._pressed.discard(key)

    def release_all(self) -> None:
        with self._lock:
            keys = list(self._pressed)
            self._pressed.clear()
        for key in keys:
            self._send(key, down=False)

    def _send(self, key: str, down: bool) -> None:
        vk = _vk_for(key)
        flags = 0 if down else self.KEYEVENTF_KEYUP

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [
                ("wVk", ctypes.c_ushort),
                ("wScan", ctypes.c_ushort),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", ctypes.c_ulonglong),
            ]

        class INPUT(ctypes.Structure):
            _fields_ = [
                ("type", ctypes.c_ulong),
                ("ki", KEYBDINPUT),
            ]

        inp = INPUT(self.INPUT_KEYBOARD, KEYBDINPUT(vk, 0, flags, 0, 0))
        ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


class KeyScheduler:
    """按键调度：按下沿带延迟、松开沿立即；纯逻辑，便于测试。"""

    def __init__(self, sender, keys: List[str], delay_ms: int = 0) -> None:
        self._sender = sender
        self._keys = list(keys)
        self._delay = max(0, int(delay_ms))
        self._desired: List[bool] = []
        self._pressed: List[bool] = []
        self._pending_at: Dict[int, float] = {}

    def set_delay(self, ms: int) -> None:
        self._delay = max(0, int(ms))

    def set_count(self, n: int) -> None:
        self._desired = [False] * n
        self._pressed = [False] * n
        self._pending_at.clear()

    def update(self, i: int, desired: bool, now_ms: float) -> None:
        while len(self._desired) <= i:
            self._desired.append(False)
            self._pressed.append(False)
        self._desired[i] = desired
        if desired:
            if not self._pressed[i] and i not in self._pending_at:
                self._pending_at[i] = now_ms + self._delay
        else:
            self._pending_at.pop(i, None)  # 取消未执行的按下
            if self._pressed[i]:
                self._pressed[i] = False
                self._sender.release(self._keys[i])

    def tick(self, now_ms: float) -> None:
        for i in list(self._pending_at):
            if self._pending_at[i] <= now_ms and self._desired[i] and not self._pressed[i]:
                self._pending_at.pop(i)
                self._pressed[i] = True
                self._sender.press(self._keys[i])

    def reset(self) -> None:
        self._pending_at.clear()
        self._sender.release_all()
        self._pressed = [False] * len(self._pressed)


class AutoplayEngine:
    """检测线程：截屏 → 颜色分类 → 调度按键。"""

    def __init__(
        self,
        matcher: ColorMatcher,
        hwnd: int,
        keys: List[str],
        rel_points: List[Tuple[float, float]],
        delay_ms: int = 0,
        on_log: Optional[Callable[[str], None]] = None,
        on_stopped: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._matcher = matcher
        self._hwnd = hwnd
        self._keys = list(keys)
        self._rel_points = [(float(x), float(y)) for x, y in rel_points]
        self._sender = KeySender()
        self._scheduler = KeyScheduler(self._sender, self._keys, delay_ms)
        self._on_log = on_log or (lambda msg: None)
        self._on_stopped = on_stopped
        self._running = False
        self._thread: Optional[threading.Thread] = None

    @property
    def running(self) -> bool:
        return self._running

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._scheduler.set_count(len(self._keys))
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        self._scheduler.reset()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def set_delay(self, ms: int) -> None:
        self._scheduler.set_delay(ms)

    def _loop(self) -> None:
        frames = 0
        last_log = time.perf_counter()
        while self._running:
            if wu.is_minimized(self._hwnd) or not wu.is_visible(self._hwnd):
                self._running = False
                self._sender.release_all()
                if self._on_stopped:
                    self._on_stopped("游戏窗口不可见，已自动暂停")
                return

            rect = wu.get_window_rect(self._hwnd)
            width = max(1, rect[2] - rect[0])
            height = max(1, rect[3] - rect[1])
            screen_points = [
                (rect[0] + int(x * width), rect[1] + int(y * height))
                for x, y in self._rel_points
            ]
            bbox = make_bbox(screen_points, pad=2)
            try:
                img = grab_rect(bbox)
            except Exception as exc:
                self._on_log(f"截屏失败: {exc}")
                time.sleep(0.01)
                continue

            local_points = [(p[0] - bbox[0], p[1] - bbox[1]) for p in screen_points]
            colors = sample_points(img, local_points)
            now_ms = time.perf_counter() * 1000.0

            for i, color in enumerate(colors):
                cls = self._matcher.classify(color)
                if cls == "key":
                    self._scheduler.update(i, True, now_ms)
                elif cls == "background":
                    self._scheduler.update(i, False, now_ms)
                # "unknown"：保持上一帧状态，避免闪烁
            self._scheduler.tick(now_ms)

            frames += 1
            now_real = time.perf_counter()
            if now_real - last_log >= 1.0:
                fps = frames / (now_real - last_log)
                self._on_log(f"检测频率: {fps:.0f} 次/秒")
                frames = 0
                last_log = now_real
```

- [ ] **Step 4: 运行测试验证通过**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add autoplay.py tests/test_autoplay.py
git commit -m "feat: 实现自动游玩引擎与按键调度"
```

---

### Task 8: app 主控制界面

**Files:**
- Create: `app.py`

**Interfaces:**
- Consumes: Task 1~7 的全部模块（`config`、`color_matcher`、`window_utils`、`capture`、`overlay`、`input_hook`、`autoplay`）
- Produces:
  - `class App`：`__init__(self, root: tk.Tk)`；方法 `on_hotkey(key)`、`on_close()`、`status(msg)`
  - 主窗口标题「Malody 颜色自动游玩」，状态栏显示检测频率与操作提示

界面布局（纵向，每个功能一行）：

```text
[选择游戏窗口（点击后点游戏窗口）]
判定线高度 [输入框] [设置(1上/2下/3结束)]
列数 [输入框]  按键 [输入框]  [设置列(左键添加/选中)]
背景颜色 [吸色(按1激活,左键取色)] [色块...]
按键颜色数量 [输入框] [吸色(按1激活,左键取色)] [色块...]
延迟(ms) [输入框]   （运行中 4=提前5ms 5=推后5ms）
[运行] [暂停] [保存]
状态栏
```

- [ ] **Step 1: 实现 app.py**

创建 `app.py`（完整代码）：

```python
"""主控制界面：布局、模式状态机、线程协调。"""

import queue
import tkinter as tk
from pathlib import Path
from tkinter import messagebox
from typing import List, Optional, Tuple

import window_utils as wu
from autoplay import AutoplayEngine
from capture import grab_rect, sample_pixel
from color_matcher import ColorMatcher
from config import load_config, save_config
from input_hook import GlobalKeyHook, MouseReader, restore_system_cursor, set_global_cursor
from overlay import Overlay


BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
CURSOR_PATH = BASE_DIR / "cursor.cur"


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Malody 颜色自动游玩")
        self.root.resizable(False, False)

        self.cfg = load_config(CONFIG_PATH)
        self.rel_y = float(self.cfg["judgement_line_y"])
        self.column_xs: List[float] = [c["x"] for c in self.cfg["columns"]]
        self.keys: List[str] = [c["key"] for c in self.cfg["columns"]]
        self.delay_ms = int(self.cfg["delay_ms"])
        self.matcher = ColorMatcher(tolerance=int(self.cfg["tolerance"]))

        self.game_hwnd: Optional[int] = None
        self.game_rect: Optional[Tuple[int, int, int, int]] = None
        self.mode = "idle"
        self.eyedrop_active = False
        self.selected_col = -1
        self.engine: Optional[AutoplayEngine] = None
        self._last_left = False
        self._closing = False
        self._msg_queue: queue.Queue = queue.Queue(maxsize=100)

        self.overlay = Overlay(root)
        self.overlay.hide()

        self._build_ui()
        self._restore_matcher()
        self._refresh_swatches()

        self._hook = GlobalKeyHook(self.on_hotkey)
        self._hook.start()

        self.root.after(100, self._tick_tracking)
        self.root.after(30, self._tick_mouse)
        self.root.after(50, self._tick_messages)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.status("就绪：先选择游戏窗口")

    # ---------- 界面构建 ----------
    def _build_ui(self) -> None:
        pad = dict(padx=8, pady=4)
        f = tk.Frame(self.root)
        f.pack(fill="x")

        tk.Button(f, text="选择游戏窗口（点击后点游戏窗口）", command=self.on_select_window).pack(fill="x", **pad)

        row = tk.Frame(f)
        row.pack(fill="x", **pad)
        tk.Label(row, text="判定线高度").pack(side="left")
        self.judgement_var = tk.StringVar(value=str(int(self.rel_y * 1000)))
        ent = tk.Entry(row, textvariable=self.judgement_var, width=8)
        ent.pack(side="left", padx=4)
        ent.bind("<Return>", lambda _e: self.apply_judgement_entry())
        tk.Button(row, text="设置(1上/2下/3结束)", command=self.on_judgement).pack(side="left", padx=4)

        row = tk.Frame(f)
        row.pack(fill="x", **pad)
        tk.Label(row, text="列数").pack(side="left")
        self.col_count_var = tk.StringVar(value=str(len(self.column_xs) or 4))
        tk.Entry(row, textvariable=self.col_count_var, width=5).pack(side="left", padx=4)
        tk.Label(row, text="按键").pack(side="left")
        self.key_string_var = tk.StringVar(value=str(self.cfg.get("key_string", "")))
        ent = tk.Entry(row, textvariable=self.key_string_var, width=14)
        ent.pack(side="left", padx=4)
        ent.bind("<Return>", lambda _e: self.apply_key_string())
        tk.Button(row, text="设置列(左键添加/选中)", command=self.on_columns).pack(side="left", padx=4)

        row = tk.Frame(f)
        row.pack(fill="x", **pad)
        tk.Label(row, text="背景颜色").pack(side="left")
        tk.Button(row, text="吸色(按1激活,左键取色)", command=self.on_eyedrop_bg).pack(side="left", padx=4)
        self.bg_swatch_frame = tk.Frame(row)
        self.bg_swatch_frame.pack(side="left", padx=4)

        row = tk.Frame(f)
        row.pack(fill="x", **pad)
        tk.Label(row, text="按键颜色数量").pack(side="left")
        self.key_count_var = tk.StringVar(value="1")
        tk.Entry(row, textvariable=self.key_count_var, width=4).pack(side="left", padx=4)
        tk.Button(row, text="吸色(按1激活,左键取色)", command=self.on_eyedrop_key).pack(side="left", padx=4)
        self.key_swatch_frame = tk.Frame(row)
        self.key_swatch_frame.pack(side="left", padx=4)

        row = tk.Frame(f)
        row.pack(fill="x", **pad)
        tk.Label(row, text="延迟(ms)").pack(side="left")
        self.delay_var = tk.StringVar(value=str(self.delay_ms))
        ent = tk.Entry(row, textvariable=self.delay_var, width=8)
        ent.pack(side="left", padx=4)
        ent.bind("<Return>", lambda _e: self.apply_delay_entry())
        tk.Label(row, text="运行中 4=提前5ms 5=推后5ms").pack(side="left")

        row = tk.Frame(f)
        row.pack(fill="x", pady=6)
        self.run_btn = tk.Button(row, text="运行", command=self.on_run, width=8)
        self.run_btn.pack(side="left", padx=8)
        self.pause_btn = tk.Button(row, text="暂停", command=self.on_pause, width=8, state="disabled")
        self.pause_btn.pack(side="left", padx=8)
        tk.Button(row, text="保存", command=self.on_save, width=8).pack(side="left", padx=8)

        self.status_var = tk.StringVar(value="")
        tk.Label(f, textvariable=self.status_var, anchor="w").pack(fill="x", **pad)

    def status(self, msg: str) -> None:
        """线程安全的状态栏更新（经消息队列转发到主线程）。"""
        try:
            self._msg_queue.put_nowait(("status", msg))
        except queue.Full:
            pass

    def _tick_messages(self) -> None:
        try:
            while True:
                kind, payload = self._msg_queue.get_nowait()
                if kind == "status":
                    self.status_var.set(payload)
                elif kind == "hotkey":
                    self._handle_hotkey(payload)
                elif kind == "engine_stopped":
                    self.engine = None
                    self._reset_buttons()
                    self.status_var.set(payload)
        except queue.Empty:
            pass
        if not self._closing:
            self.root.after(50, self._tick_messages)

    # ---------- 配置恢复 ----------
    def _restore_matcher(self) -> None:
        for c in self.cfg.get("background_colors", []):
            self.matcher.add_background(tuple(c))
        for c in self.cfg.get("key_colors", []):
            self.matcher.add_key(tuple(c))

    def _refresh_swatches(self) -> None:
        for frame in (self.bg_swatch_frame, self.key_swatch_frame):
            for w in frame.winfo_children():
                w.destroy()
        for i, c in enumerate(self.matcher.background_colors):
            tk.Button(
                self.bg_swatch_frame, bg="#%02x%02x%02x" % c, width=4,
                command=lambda idx=i: self._remove_bg(idx),
            ).pack(side="left", padx=1)
        for i, c in enumerate(self.matcher.key_colors):
            tk.Button(
                self.key_swatch_frame, bg="#%02x%02x%02x" % c, width=4,
                command=lambda idx=i: self._remove_key(idx),
            ).pack(side="left", padx=1)

    def _remove_bg(self, idx: int) -> None:
        self.matcher.remove_background(self.matcher.background_colors[idx])
        self._refresh_swatches()

    def _remove_key(self, idx: int) -> None:
        self.matcher.remove_key(self.matcher.key_colors[idx])
        self._refresh_swatches()

    # ---------- 窗口 ----------
    def on_select_window(self) -> None:
        self.mode = "select_window"
        self.status("请在游戏窗口上点击左键")

    def select_game_window(self, hwnd: int) -> None:
        self.game_hwnd = hwnd
        self._refresh_tracking()
        self.mode = "idle"
        self.status("已选择游戏窗口（黄色线框）")

    def _refresh_tracking(self) -> None:
        if not self.game_hwnd:
            return
        if wu.is_minimized(self.game_hwnd) or not wu.is_visible(self.game_hwnd):
            self.overlay.hide()
            return
        self.game_rect = wu.get_window_rect(self.game_hwnd)
        self.overlay.set_game_rect(self.game_rect)
        self.overlay.set_judgement_y(self.rel_y)
        self.overlay.set_columns(self.column_xs, self.selected_col)
        self.overlay.show()

    # ---------- 判定线 ----------
    def on_judgement(self) -> None:
        if not self.game_hwnd:
            messagebox.showwarning("提示", "请先选择游戏窗口")
            return
        self.mode = "judgement"
        self._refresh_tracking()
        self.status("判定线设置：1上移 2下移 左键选高度 3结束")

    def apply_judgement_entry(self) -> None:
        try:
            y = int(self.judgement_var.get())
        except ValueError:
            self.status("判定线高度请输入数字")
            return
        self._set_judgement_px(y)

    def _set_judgement_px(self, px: int) -> None:
        if not self.game_rect:
            return
        h = max(1, self.game_rect[3] - self.game_rect[1])
        self.rel_y = max(0.0, min(1.0, px / h))
        self.judgement_var.set(str(px))
        self.overlay.set_judgement_y(self.rel_y)

    def nudge_judgement(self, delta_px: int) -> None:
        if not self.game_rect:
            return
        h = max(1, self.game_rect[3] - self.game_rect[1])
        self.rel_y = max(0.0, min(1.0, self.rel_y + delta_px / h))
        self.judgement_var.set(str(int(self.rel_y * h)))
        self.overlay.set_judgement_y(self.rel_y)

    # ---------- 列 ----------
    def on_columns(self) -> None:
        if not self.game_hwnd:
            messagebox.showwarning("提示", "请先选择游戏窗口")
            return
        if len(self.column_xs) == 0:
            self.column_xs = [0.5]
        self.mode = "columns"
        self.selected_col = max(0, len(self.column_xs) - 1)
        self._refresh_tracking()
        self.status("列设置：左键添加/选中 1左移 2右移 3结束")

    def apply_key_string(self) -> None:
        self.keys = self._parse_keys()
        if len(self.keys) != len(self.column_xs):
            self.status(f"按键数量({len(self.keys)})与列数({len(self.column_xs)})不匹配，已忽略")
            self.keys = []
        else:
            self.status("按键绑定已更新")

    def _parse_keys(self) -> List[str]:
        s = self.key_string_var.get().strip()
        if not s:
            return []
        if len(s) == len(self.column_xs):
            return list(s.upper())
        return [part.strip() for part in s.split() if part.strip()]

    def nudge_column(self, delta_px: int) -> None:
        if self.selected_col < 0 or not self.game_rect:
            return
        w = max(1, self.game_rect[2] - self.game_rect[0])
        self.column_xs[self.selected_col] = max(
            0.0, min(1.0, self.column_xs[self.selected_col] + delta_px / w)
        )
        self._refresh_tracking()

    # ---------- 吸色 ----------
    def on_eyedrop_bg(self) -> None:
        self.mode = "eyedrop_bg"
        self.status("吸管模式：按 1 激活，左键取色")

    def on_eyedrop_key(self) -> None:
        self.mode = "eyedrop_key"
        self.status("吸管模式：按 1 激活，左键取色")

    def activate_eyedrop(self) -> None:
        if self.eyedrop_active:
            return
        self.eyedrop_active = True
        if CURSOR_PATH.exists():
            set_global_cursor(CURSOR_PATH)
        self.status("吸管已激活，左键取色")

    def _pick_color(self) -> None:
        x, y = MouseReader.cursor_pos()
        try:
            img = grab_rect((x, y, x + 1, y + 1))
            color = sample_pixel(img, 0, 0)
        except Exception as exc:
            self.status(f"取色失败: {exc}")
            return
        if self.mode == "eyedrop_bg":
            self.matcher.add_background(color)
        else:
            try:
                limit = max(1, int(self.key_count_var.get()))
            except ValueError:
                limit = 1
            if len(self.matcher.key_colors) >= limit:
                self.status(f"按键颜色已达上限 {limit}，可点击色块删除")
                return
            self.matcher.add_key(color)
        self.eyedrop_active = False
        restore_system_cursor()
        self._refresh_swatches()
        self.status(f"已吸取 RGB{tuple(color)}，按 1 继续吸色")

    # ---------- 延迟 ----------
    def apply_delay_entry(self) -> None:
        try:
            self.delay_ms = int(self.delay_var.get())
        except ValueError:
            self.status("延迟请输入整数")
            return
        if self.engine:
            self.engine.set_delay(self.delay_ms)
        self.status(f"延迟已设为 {self.delay_ms} ms")

    def nudge_delay(self, delta_ms: int) -> None:
        self.delay_ms = self.delay_ms + delta_ms
        self.delay_var.set(str(self.delay_ms))
        if self.engine:
            self.engine.set_delay(self.delay_ms)
        self.status(f"延迟 {self.delay_ms} ms")

    # ---------- 运行 / 暂停 / 保存 ----------
    def _sorted_columns(self) -> List[Tuple[float, str]]:
        pairs = sorted(zip(self.column_xs, self.keys or self._parse_keys()))
        return [(x, k) for x, k in pairs if k]

    def on_run(self) -> None:
        errors = []
        if not self.game_hwnd:
            errors.append("请先选择游戏窗口")
        if not self.column_xs:
            errors.append("请先设置列")
        if not self._sorted_columns():
            errors.append("请设置按键绑定（与列数匹配）")
        if not self.matcher.background_colors:
            errors.append("请先吸取背景颜色")
        if not self.matcher.key_colors:
            errors.append("请先吸取按键颜色")
        if errors:
            messagebox.showwarning("提示", "\n".join(errors))
            return

        wu.set_foreground(self.game_hwnd)
        rel_points = [(x, self.rel_y) for x, _ in self._sorted_columns()]
        keys = [k for _, k in self._sorted_columns()]
        self.engine = AutoplayEngine(
            self.matcher, self.game_hwnd, keys, rel_points,
            self.delay_ms, on_log=self.status, on_stopped=self._on_engine_stopped,
        )
        self.engine.start()
        self.run_btn.config(state="disabled")
        self.pause_btn.config(state="normal")
        self._refresh_tracking()
        self.status("运行中…（按4/5调延迟）")

    def on_pause(self) -> None:
        if self.engine:
            self.engine.stop()
            self.engine = None
        self.run_btn.config(state="normal")
        self.pause_btn.config(state="disabled")
        self.overlay.show()
        self._refresh_tracking()
        self.status("已暂停")

    def _on_engine_stopped(self, msg: str) -> None:
        """检测线程回调：入队后由主线程恢复界面。"""
        try:
            self._msg_queue.put_nowait(("engine_stopped", msg))
        except queue.Full:
            pass

    def _reset_buttons(self) -> None:
        self.run_btn.config(state="normal")
        self.pause_btn.config(state="disabled")

    def on_save(self) -> None:
        sorted_cols = self._sorted_columns()
        if sorted_cols:
            columns = [{"x": x, "key": k} for x, k in sorted_cols]
        else:
            columns = [{"x": x, "key": k} for x, k in zip(self.column_xs, self.keys)]
        cfg = {
            "judgement_line_y": self.rel_y,
            "column_count": len(columns),
            "key_string": self.key_string_var.get().strip(),
            "columns": columns,
            "background_colors": [list(c) for c in self.matcher.background_colors],
            "key_colors": [list(c) for c in self.matcher.key_colors],
            "delay_ms": self.delay_ms,
            "tolerance": self.matcher.tolerance,
        }
        save_config(CONFIG_PATH, cfg)
        self.status("设置已保存到 config.json")

    # ---------- 全局输入 ----------
    def on_hotkey(self, key: str) -> None:
        """钩子线程回调：入队后由主线程处理。"""
        if self._closing:
            return
        try:
            self._msg_queue.put_nowait(("hotkey", key))
        except queue.Full:
            pass

    def _handle_hotkey(self, key: str) -> None:
        if key in ("4", "5"):
            # 延迟调整在任何模式下都生效
            self.nudge_delay(-5 if key == "4" else 5)
            return
        if self.mode == "judgement":
            if key == "1":
                self.nudge_judgement(-1)
            elif key == "2":
                self.nudge_judgement(1)
            elif key == "3":
                self.mode = "idle"
                self.status("判定线设置结束")
            return
        if self.mode == "columns":
            if key == "1":
                self.nudge_column(-1)
            elif key == "2":
                self.nudge_column(1)
            elif key == "3":
                self.mode = "idle"
                self.status("列设置结束")
            return
        if self.mode in ("eyedrop_bg", "eyedrop_key") and key == "1":
            self.activate_eyedrop()
            return

    # ---------- 轮询 ----------
    def _tick_tracking(self) -> None:
        if not self._closing:
            # 运行中与设置模式下都保持覆盖层跟随窗口
            self._refresh_tracking()
            self.root.after(100, self._tick_tracking)

    def _tick_mouse(self) -> None:
        pressed = MouseReader.left_pressed()
        if pressed and not self._last_left:
            self._on_left_click()
        self._last_left = pressed
        if not self._closing:
            self.root.after(30, self._tick_mouse)

    def _on_left_click(self) -> None:
        x, y = MouseReader.cursor_pos()
        if self.mode == "select_window":
            hwnd = wu.find_window_at_point(x, y)
            own = {int(self.root.winfo_id()), int(self.overlay._window.winfo_id())}
            if hwnd and hwnd not in own:
                self.select_game_window(hwnd)
        elif self.mode == "judgement":
            rel = self._rel_point(x, y)
            if rel:
                h = max(1, self.game_rect[3] - self.game_rect[1])
                self._set_judgement_px(int(rel[1] * h))
        elif self.mode == "columns":
            self._click_column(x, y)
        elif self.mode in ("eyedrop_bg", "eyedrop_key") and self.eyedrop_active:
            self._pick_color()

    def _rel_point(self, sx: int, sy: int) -> Optional[Tuple[float, float]]:
        if not self.game_rect:
            return None
        left, top, right, bottom = self.game_rect
        if not (left <= sx < right and top <= sy < bottom):
            return None
        return (
            (sx - left) / max(1, right - left),
            (sy - top) / max(1, bottom - top),
        )

    def _click_column(self, sx: int, sy: int) -> None:
        rel = self._rel_point(sx, sy)
        if rel is None:
            return
        rx, _ = rel
        for i, x in enumerate(self.column_xs):
            if abs(x - rx) < 0.01:
                self.selected_col = i
                self._refresh_tracking()
                self.status(f"选中第 {i + 1} 列，1左移 2右移")
                return
        try:
            count = max(1, int(self.col_count_var.get()))
        except ValueError:
            count = 1
        if len(self.column_xs) >= count:
            self.status(f"列数已满（{count}），可点击蓝点重新选中")
            return
        self.column_xs.append(rx)
        self.keys = self._parse_keys()
        self.selected_col = len(self.column_xs) - 1
        self._refresh_tracking()
        self.status(f"已添加第 {len(self.column_xs)} 列，1左移 2右移")

    # ---------- 关闭 ----------
    def on_close(self) -> None:
        self._closing = True
        if self.engine:
            self.engine.stop()
        self._hook.stop()
        restore_system_cursor()
        self.root.destroy()
```

- [ ] **Step 2: 静态检查**

Run: `python -m py_compile app.py`
Expected: 无语法错误

- [ ] **Step 3: 运行全部测试**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS（app 未参与单测，靠手动验收）

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "feat: 实现主控制界面"
```

---

### Task 9: 入口、启动脚本与端到端验收

**Files:**
- Create: `main.py`
- Create: `start.bat`

**Interfaces:**
- Consumes: `app.App`、`window_utils.set_process_dpi_aware`
- Produces: 可双击启动的 `start.bat`，以及可运行的 `main.py`

- [ ] **Step 1: 创建入口与启动脚本**

创建 `main.py`：

```python
"""程序入口。"""

import tkinter as tk

import window_utils as wu
from app import App


def main() -> None:
    wu.set_process_dpi_aware()
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
```

创建 `start.bat`：

```bat
@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
    echo 未找到 Python，请先安装 Python 3.11
    pause
    exit /b 1
)
python -m pip install -r requirements.txt
python main.py
```

- [ ] **Step 2: 运行全部测试**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 3: 启动冒烟测试**

Run: `python main.py`，确认窗口出现、无异常输出，然后关闭窗口。
Expected: 界面正常显示，关闭后进程退出

- [ ] **Step 4: 手动验收清单（逐项通过）**

1. **选择窗口**：启动 Malody，点「选择游戏窗口」再点 Malody 窗口 → 出现 5px 黄框；拖动 Malody 窗口黄框跟随；最小化后黄框隐藏，还原后恢复。
2. **判定线**：点「设置」→ 出现 3px 红线（窗口垂直中间）；按 1 上移、按 2 下移（焦点在 Malody 上也生效）；左键点击游戏窗口内 → 红线跳到点击高度；输入框输入数字回车 → 红线更新；按 3 结束，红线保留。
3. **列**：列数输入 4、按键输入 DFJK；点「设置列」→ 左键点 4 个位置生成空心蓝点；按 1/2 微调当前列；点已有蓝点重新选中；按 3 结束，蓝点保留。
4. **吸背景色**：点吸色按钮 → 按 1 → 鼠标变吸管图标 → 左键点游戏背景 → 出现色块；点色块删除。
5. **吸按键色**：数量输入 2 → 吸两个颜色 → 两个色块；点色块删除；达到数量上限时提示。
6. **延迟**：输入 -10/0/50 回车均生效；运行中按 4 减 5、按 5 加 5，输入框同步。
7. **运行**：点「运行」→ Malody 自动置前；note 落到判定线蓝点位置时对应按键触发；note 过去后松开；长按音符持续按住；状态栏显示「检测频率: NNN 次/秒」，N ≥ 100。
8. **暂停**：点「暂停」→ 识别停止、按键全部松开、蓝点恢复显示。
9. **保存**：点「保存」→ 程序目录生成 `config.json`；关闭程序重新启动 → 全部设置自动加载（窗口需重新选择）。
10. **异常**：未选窗口/未设列/未吸色时点运行 → 弹窗提示缺失项。

- [ ] **Step 5: Commit**

```bash
git add main.py start.bat
git commit -m "feat: 添加入口与启动脚本，完成验收"
```

---

## 后续（不在本期）

- PyInstaller 打包：`pip install pyinstaller && pyinstaller --onefile --windowed main.py --add-data "cursor.cur;."`
- 打包后再次执行 Task 9 验收清单。
