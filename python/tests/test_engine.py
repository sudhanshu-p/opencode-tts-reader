import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from tts_service.config import load_config
from tts_service.engine import TTSEngine


def make_config(tmp_path: Path):
    return replace(load_config(tmp_path / "missing.json"), model_cache_dir=tmp_path / "models")


def test_load_passes_mlx_options_and_synthesizes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict = {}

    class FakeKittenTTS:
        sample_rate = 24000
        available_voices = ["Bruno", "Bella"]

        def __init__(self, model: str, **kwargs) -> None:
            calls["model"] = model
            calls["kwargs"] = kwargs

        def generate(self, text: str, voice: str | None = None, normalize: bool = True):
            calls["generate"] = (text, voice, normalize)
            return np.zeros(24000, dtype=np.float32)

    monkeypatch.setitem(sys.modules, "kittenml", SimpleNamespace(KittenTTS=FakeKittenTTS))
    engine = TTSEngine(make_config(tmp_path))
    assert engine.loaded is False
    engine.load()
    assert engine.loaded is True
    assert calls["model"] == "KittenML/kitten-tts-2"
    assert calls["kwargs"] == {
        "cache_dir": str(tmp_path / "models"),
        "backend": "mlx",
        "weights": "packed",
        "device": "mps",
    }
    assert engine.list_voices() == ("Bella", "Bruno")
    audio, sr = engine.synthesize("Hello", "Bella")
    assert sr == 24000
    assert audio.size == 24000
    assert calls["generate"] == ("Hello", "Bella", True)


def test_synthesize_before_load_raises(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="not loaded"):
        TTSEngine(make_config(tmp_path)).synthesize("Hello", "Bella")


def test_empty_text_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeKittenTTS:
        sample_rate = 24000

        def __init__(self, *args, **kwargs) -> None:
            pass

    monkeypatch.setitem(sys.modules, "kittenml", SimpleNamespace(KittenTTS=FakeKittenTTS))
    engine = TTSEngine(make_config(tmp_path))
    engine.load()
    with pytest.raises(ValueError, match="empty"):
        engine.synthesize("   ", "Bella")
