from dataclasses import replace
from pathlib import Path

import pytest

from tts_service.config import default_model_cache_dir, load_config
from tts_service.engine import TTSEngine


@pytest.mark.integration
@pytest.mark.timeout(1800)
def test_real_model_synthesizes(tmp_path: Path) -> None:
    # Reuse the product's local cache so the real weights are downloaded only once.
    cfg = replace(
        load_config(tmp_path / "missing.json"),
        model_cache_dir=default_model_cache_dir(),
    )
    engine = TTSEngine(cfg)
    engine.load()
    audio, sr = engine.synthesize("Hello from Kitten TTS.", "Bella")
    assert sr == 24000
    assert audio.size > 0
