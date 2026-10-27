import subprocess
import threading
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from tts_service.audio import AudioPlayer, prepare_chunk, write_wav


def test_write_wav_uses_24khz_pcm16(tmp_path: Path) -> None:
    path = tmp_path / "a.wav"
    write_wav(path, np.zeros(2400, dtype=np.float32), 24000)
    data, sr = sf.read(path)
    assert sr == 24000
    assert len(data) == 2400


def test_prepare_chunk_trims_silence_and_appends_pause() -> None:
    sample_rate = 24000
    speech = np.full(2400, 0.5, dtype=np.float32)
    padded = np.concatenate(
        [np.zeros(12000, dtype=np.float32), speech, np.zeros(12000, dtype=np.float32)]
    )
    prepared = prepare_chunk(padded, sample_rate, gap_s=0.1)

    loud = np.nonzero(np.abs(prepared) > 0.01)[0]
    assert len(loud) > 0
    assert loud[0] / sample_rate < 0.05
    assert (len(prepared) - loud[-1]) / sample_rate >= 0.09
    assert len(prepared) < len(padded)


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


def test_interrupted_afplay_exit_does_not_raise(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Proc:
        def wait(self) -> int:
            return -15

        def poll(self):
            return -15

    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: Proc())
    AudioPlayer().play(tmp_path / "a.wav")
