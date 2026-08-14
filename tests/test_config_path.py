from pathlib import Path

from app import resolve_config_path


def test_resolve_creates_config_dir(tmp_path: Path):
    cfg_dir = tmp_path / "configs"
    result = resolve_config_path(cfg_dir)
    assert cfg_dir.is_dir()
    assert result == cfg_dir / "config.json"


def test_resolve_prefers_last_saved(tmp_path: Path):
    cfg_dir = tmp_path / "configs"
    cfg_dir.mkdir()
    custom = cfg_dir / "我的配置.json"
    custom.write_text("{}", encoding="utf-8")
    (cfg_dir / ".last").write_text(str(custom), encoding="utf-8")
    assert resolve_config_path(cfg_dir) == custom


def test_resolve_ignores_missing_last(tmp_path: Path):
    cfg_dir = tmp_path / "configs"
    cfg_dir.mkdir()
    (cfg_dir / ".last").write_text(str(cfg_dir / "不存在.json"), encoding="utf-8")
    assert resolve_config_path(cfg_dir) == cfg_dir / "config.json"


def test_resolve_migrates_old_config(tmp_path: Path):
    old = tmp_path / "config.json"
    old.write_text('{"delay_ms": 12}', encoding="utf-8")
    result = resolve_config_path(tmp_path / "configs")
    assert result == tmp_path / "configs" / "config.json"
    assert result.exists()
