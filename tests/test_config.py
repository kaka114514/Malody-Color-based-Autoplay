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
        "window_size": [0, 0],
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


def test_window_size_round_trip(tmp_path: Path):
    path = tmp_path / "size.json"
    cfg = {"window_size": [820, 640]}
    save_config(path, cfg)
    assert load_config(path)["window_size"] == [820, 640]


def test_window_size_invalid_resets(tmp_path: Path):
    cfg = normalize_config({"window_size": [0, -5]})
    assert cfg["window_size"] == [0, 0]
