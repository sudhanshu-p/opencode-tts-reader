import subprocess
import threading
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from tts_service.audio import AudioPlayer, write_wav


def test_write_wav_uses_24khz_pcm16(tmp_path: Path) -> None:
    path = tmp_path / "a.wav"
    write_wav(path, np.zeros(2400, dtype=np.float32), 24000)
    data, sr = sf.read(path)
    assert sr == 24000
    assert len(data) == 2400


def test_play_uses_afplay_without_shell(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    class Proc:
        def wait(self) -> int:
            return 0

        def poll(self):
            return 0

    def fake_popen(argv, **kwargs):
        calls.append((argv, kwargs))
        return Proc()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    AudioPlayer().play(tmp_path / "a.wav")
    assert calls == [([ "afplay", str(tmp_path / "a.wav") ], {})]


def test_stop_terminates_running_afplay(monkeypatch: pytest.MonkeyPatch) -> None:
    events = []

    class Proc:
        def wait(self, timeout=None) -> int:
            return 0

        def poll(self):
            return None

        def terminate(self) -> None:
            events.append("terminate")

        def kill(self) -> None:
            events.append("kill")

    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: Proc())
    player = AudioPlayer()
    player._proc = Proc()  # simulate an in-flight playback
    player.stop()
    assert "terminate" in events


def test_stop_interrupts_blocking_play(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    started = threading.Event()
    released = threading.Event()
    events = []

    class Proc:
        def wait(self, timeout=None) -> int:
            if timeout is None:
                started.set()
                released.wait(2)
                return 0
            return 0

        def poll(self):
            return None

        def terminate(self) -> None:
            events.append("terminate")
            released.set()

        def kill(self) -> None:
            events.append("kill")
            released.set()

    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: Proc())
    player = AudioPlayer()
    thread = threading.Thread(target=player.play, args=(tmp_path / "a.wav",))
    thread.start()
    assert started.wait(1)
    player.stop()
    thread.join(2)
    assert not thread.is_alive()
    assert "terminate" in events


def test_nonzero_afplay_exit_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class Proc:
        def wait(self) -> int:
            return 1

        def poll(self):
            return 1

    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: Proc())
    with pytest.raises(RuntimeError, match="afplay"):
        AudioPlayer().play(tmp_path / "a.wav")
