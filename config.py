"""配置的读取、归一化与保存。"""

import json
from pathlib import Path
from typing import Any


DEFAULT_CONFIG: dict = {
    "judgement_line_y": 0.78,          # 判定线相对高度 0~1
    "judgement_line_px": 0,            # 判定线像素高度（游戏窗口内；0=未设置）
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
    "key_color_count": 1,              # 按键颜色数量
    "window_size": [0, 0],             # 主窗口宽高；[0,0] 表示未设置
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

    try:
        cfg["judgement_line_px"] = max(0, int(cfg.get("judgement_line_px", 0)))
    except (TypeError, ValueError):
        cfg["judgement_line_px"] = 0

    try:
        cfg["key_color_count"] = max(1, int(cfg.get("key_color_count", 1)))
    except (TypeError, ValueError):
        cfg["key_color_count"] = 1

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

    size = cfg.get("window_size")
    if (
        isinstance(size, (list, tuple))
        and len(size) == 2
        and all(isinstance(v, (int, float)) and v > 0 for v in size)
    ):
        cfg["window_size"] = [int(size[0]), int(size[1])]
    else:
        cfg["window_size"] = [0, 0]

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
