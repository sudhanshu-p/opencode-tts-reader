import json
from pathlib import Path

import pytest

from tts_service.config import Config, config_path, load_config, save_config


def test_defaults_when_file_is_missing(tmp_path: Path) -> None:
    cfg = load_config(tmp_path / "missing.json")
    assert cfg.host == "127.0.0.1"
    assert cfg.port == 8765
    assert cfg.model == "KittenML/kitten-tts-2"
    assert cfg.backend == "mlx"
    assert cfg.weights == "packed"
    assert cfg.device == "mps"
    assert cfg.voice == "Bella"
    assert cfg.auto_read is True
    assert cfg.max_words == 1500


def test_partial_file_merges_defaults(tmp_path: Path) -> None:
    path = tmp_path / "tts-reader.json"
    path.write_text(json.dumps({"voice": "Bruno", "max_words": 100}), encoding="utf-8")
    cfg = load_config(path)
    assert cfg.voice == "Bruno"
    assert cfg.max_words == 100
    assert cfg.port == 8765


def test_save_is_atomic_and_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "tts-reader.json"
    cfg = load_config(path)
    save_config(cfg, path)
    assert json.loads(path.read_text(encoding="utf-8"))["port"] == 8765
    assert [p.name for p in tmp_path.iterdir() if p.suffix == ".tmp"] == []
    assert load_config(path) == cfg


def test_config_path_respects_xdg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert config_path() == tmp_path / "opencode" / "tts-reader.json"


def test_mlx_rejects_emb4(tmp_path: Path) -> None:
    path = tmp_path / "tts-reader.json"
    path.write_text(json.dumps({"backend": "mlx", "weights": "emb4"}), encoding="utf-8")
    with pytest.raises(ValueError, match="emb4"):
        load_config(path)


@pytest.mark.parametrize("patch", [{"host": "0.0.0.0"}, {"port": 0}, {"port": 70000}, {"ask_markdown": "sometimes"}])
def test_invalid_values_raise(tmp_path: Path, patch: dict) -> None:
    path = tmp_path / "tts-reader.json"
    path.write_text(json.dumps(patch), encoding="utf-8")
    with pytest.raises(ValueError):
        load_config(path)
