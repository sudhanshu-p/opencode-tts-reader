"""KittenTTS synthesis wrapper used by the reader pipeline."""

import threading

import numpy as np

from tts_service.config import Config

DEFAULT_SAMPLE_RATE = 24000


class TTSEngine:
    """Load the KittenTTS model lazily and synthesize speech with it."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self._model = None
        self._sample_rate = DEFAULT_SAMPLE_RATE
        self._lock = threading.Lock()

    @property
    def loaded(self) -> bool:
        """Return whether the underlying model has been loaded."""
        return self._model is not None

    @property
    def sample_rate(self) -> int:
        """Return the sample rate reported by the model."""
        return self._sample_rate

    def load(self) -> None:
        """Load the KittenTTS model, reusing an existing instance."""
        if self._model is not None:
            return
        from kittenml import KittenTTS

        cache_dir = self.config.model_cache_dir
        cache_dir.mkdir(parents=True, exist_ok=True)
        model = KittenTTS(
            self.config.model,
            cache_dir=str(cache_dir),
            backend=self.config.backend,
            weights=self.config.weights,
            device=self.config.device,
        )
        sample_rate = getattr(model, "sample_rate", None)
        if sample_rate is not None:
            self._sample_rate = int(sample_rate)
        self._model = model

    def list_voices(self) -> tuple[str, ...]:
        """Return the model's voice names sorted alphabetically."""
        if self._model is None:
            return ()
        voices = getattr(self._model, "available_voices", None)
        if voices is None:
            voices = getattr(self._model, "voices", None)
        if voices is None:
            return ()
        if callable(voices):
            voices = voices()
        return tuple(sorted(str(voice) for voice in voices))

    def synthesize(self, text: str, voice: str) -> tuple[np.ndarray, int]:
        """Generate float32 audio samples for ``text`` using ``voice``."""
        if self._model is None:
            raise RuntimeError("KittenTTS model is not loaded")
        if not text.strip():
            raise ValueError("text is empty")
        with self._lock:
            result = self._model.generate(text, voice=voice, normalize=True)
        if isinstance(result, tuple):
            audio, sample_rate = result
            sample_rate = int(sample_rate)
        else:
            audio = result
            sample_rate = self._sample_rate
        return np.asarray(audio, dtype=np.float32).reshape(-1), sample_rate
