"""WAV output and interruptible playback for synthesized speech."""

import subprocess
import threading
from pathlib import Path

import numpy as np
import soundfile as sf


def write_wav(path: Path, audio: np.ndarray, sample_rate: int) -> None:
    """Write ``audio`` to ``path`` as 16-bit PCM WAV, creating parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), audio, sample_rate, subtype="PCM_16")


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
        if code != 0:
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
