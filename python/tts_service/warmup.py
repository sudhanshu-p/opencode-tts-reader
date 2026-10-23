"""Download the model and generate a first WAV outside the request path."""

from __future__ import annotations

from tts_service.audio import write_wav
from tts_service.config import load_config
from tts_service.engine import TTSEngine

WARMUP_TEXT = "Hello from Kitten TTS."


def main() -> int:
    """Load the model, synthesize a sample, and print the WAV path."""
    config = load_config()
    engine = TTSEngine(config)
    engine.load()
    audio, sample_rate = engine.synthesize(WARMUP_TEXT, config.voice)
    path = config.data_dir / "warmup.wav"
    write_wav(path, audio, sample_rate)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
