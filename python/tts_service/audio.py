"""WAV output and interruptible playback for synthesized speech."""

import subprocess
import threading
from pathlib import Path

import numpy as np
import soundfile as sf

CHUNK_GAP_S = 0.14
TRIM_KEEP_S = 0.02
TRIM_FADE_S = 0.008


def write_wav(path: Path, audio: np.ndarray, sample_rate: int) -> None:
    """Write ``audio`` to ``path`` as 16-bit PCM WAV, creating parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), audio, sample_rate, subtype="PCM_16")


def trim_silence(
    audio: np.ndarray,
    sample_rate: int,
    *,
    threshold_db: float = -45.0,
    keep_s: float = TRIM_KEEP_S,
) -> np.ndarray:
    """Trim leading and trailing silence from one generated segment."""
    audio = np.asarray(audio, dtype=np.float32).reshape(-1)
    if len(audio) == 0:
        return audio
    hop = max(1, int(sample_rate * 0.01))
    usable = len(audio) // hop * hop
    if usable == 0:
        return audio
    frames = audio[:usable].reshape(-1, hop)
    rms = np.sqrt((frames**2).mean(axis=1) + 1e-12)
    loud = np.nonzero(rms > 10 ** (threshold_db / 20.0))[0]
    if not len(loud):
        return audio
    keep = int(sample_rate * keep_s)
    start = max(0, int(loud[0]) * hop - keep)
    end = min(len(audio), (int(loud[-1]) + 1) * hop + keep)
    return audio[start:end].copy()


def prepare_chunk(
    audio: np.ndarray,
    sample_rate: int,
    *,
    gap_s: float = CHUNK_GAP_S,
) -> np.ndarray:
    """Trim a streamed segment, fade its edges, and append a short pause."""
    trimmed = trim_silence(audio, sample_rate)
    if len(trimmed) == 0:
        return trimmed
    fade = min(len(trimmed) // 2, int(sample_rate * TRIM_FADE_S))
    if fade > 0:
        ramp = np.linspace(0.0, 1.0, fade, dtype=np.float32)
        trimmed[:fade] *= ramp
        trimmed[-fade:] *= ramp[::-1]
    gap = np.zeros(max(0, int(sample_rate * gap_s)), dtype=np.float32)
    return np.concatenate([trimmed, gap])


class AudioPlayer:
    """Play a WAV file through ``afplay`` while allowing interruption."""

    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()

    @property
    def playing(self) -> bool:
        """Return whether a playback process is currently running."""
        with self._lock:
            proc = self._proc
        return proc is not None and proc.poll() is None

    def play(self, path: Path) -> None:
        """Play ``path`` and block until it finishes or ``stop`` interrupts it."""
        with self._lock:
            proc = subprocess.Popen(["afplay", str(path)])
            self._proc = proc
        try:
            code = proc.wait()
        finally:
            with self._lock:
                if self._proc is proc:
                    self._proc = None
        if code not in (0, -15, -9):
            raise RuntimeError(f"afplay failed with exit code {code}")

    def stop(self) -> None:
        """Interrupt the current playback, if any."""
        with self._lock:
            proc = self._proc
            self._proc = None
        if proc is None:
            return
        try:
            if proc.poll() is not None:
                return
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        except ProcessLookupError:
            pass
