import threading
import time
from dataclasses import replace
from pathlib import Path

import numpy as np

from tts_service.config import load_config
from tts_service.pipeline import SpeechJob, SpeechPipeline, split_chunks


def wait_until(predicate, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("timed out waiting for condition")


class FakeEngine:
    loaded = True
    sample_rate = 24000

    def __init__(self) -> None:
        self.generated: list[str] = []

    def synthesize(self, text: str, voice: str):
        self.generated.append(text)
        return np.zeros(2400, dtype=np.float32), 24000


class RecordingPlayer:
    def __init__(self) -> None:
        self.played: list[str] = []

    def play(self, path: Path) -> None:
        self.played.append(Path(path).name)

    def stop(self) -> None:
        pass

    @property
    def playing(self) -> bool:
        return False


def make_pipeline(tmp_path: Path, engine=None, player=None, **changes):
    cfg = replace(load_config(tmp_path / "missing.json"), **changes)
    engine = engine or FakeEngine()
    player = player or RecordingPlayer()
    pipeline = SpeechPipeline(engine, player, cfg, data_dir=tmp_path)
    return pipeline, engine, player


def test_split_chunks_groups_sentences() -> None:
    assert split_chunks("One. Two! Three?", 12) == ["One. Two!", "Three?"]
    assert split_chunks("Para one.\n\nPara two.", 260) == ["Para one.", "Para two."]
    assert all(len(chunk) <= 20 for chunk in split_chunks("word " * 20, 20))


def test_plays_jobs_in_fifo_order(tmp_path: Path) -> None:
    pipeline, engine, player = make_pipeline(tmp_path, chunk_max_chars=12)
    pipeline.start()
    try:
        assert pipeline.submit(SpeechJob("j1", "First.", "Bella", "s", "m1"))
        assert pipeline.submit(SpeechJob("j2", "Second.", "Bella", "s", "m2"))
        wait_until(lambda: len(player.played) == 2)
        assert engine.generated == ["First.", "Second."]
        assert player.played == ["j1-0.wav", "j2-0.wav"]
    finally:
        pipeline.shutdown()


def test_waits_for_engine_ready(tmp_path: Path) -> None:
    class SlowEngine(FakeEngine):
        def __init__(self) -> None:
            super().__init__()
            self.loaded = False

    engine = SlowEngine()
    pipeline, _, player = make_pipeline(tmp_path, engine=engine)
    pipeline.start()
    try:
        pipeline.submit(SpeechJob("j1", "Hello.", "Bella", "s", "m1"))
        time.sleep(0.2)
        assert player.played == []
        engine.loaded = True
        wait_until(lambda: len(player.played) == 1)
        assert engine.generated == ["Hello."]
    finally:
        pipeline.shutdown()


def test_stop_during_synthesis_prevents_playback(tmp_path: Path) -> None:
    class BlockingEngine(FakeEngine):
        def __init__(self) -> None:
            super().__init__()
            self.started = threading.Event()
            self.release = threading.Event()

        def synthesize(self, text: str, voice: str):
            self.started.set()
            self.release.wait(2)
            return super().synthesize(text, voice)

    engine = BlockingEngine()
    pipeline, _, player = make_pipeline(tmp_path, engine=engine)
    pipeline.start()
    try:
        pipeline.submit(SpeechJob("j1", "Hello.", "Bella", "s", "m1"))
        assert engine.started.wait(2)
        pipeline.stop()
        engine.release.set()
        time.sleep(0.2)
        assert player.played == []
    finally:
        engine.release.set()
        pipeline.shutdown()


def test_stop_drops_queued_playback(tmp_path: Path) -> None:
    class BlockingPlayer(RecordingPlayer):
        def __init__(self) -> None:
            super().__init__()
            self.started = threading.Event()
            self.release = threading.Event()

        def play(self, path: Path) -> None:
            self.played.append(Path(path).name)
            self.started.set()
            self.release.wait(2)

        def stop(self) -> None:
            self.release.set()

    player = BlockingPlayer()
    pipeline, _, _ = make_pipeline(tmp_path, player=player)
    pipeline.start()
    try:
        pipeline.submit(SpeechJob("j1", "First.", "Bella", "s", "m1"))
        pipeline.submit(SpeechJob("j2", "Second.", "Bella", "s", "m2"))
        assert player.started.wait(2)
        pipeline.stop()
        time.sleep(0.2)
        assert player.played == ["j1-0.wav"]
    finally:
        player.release.set()
        pipeline.shutdown()


class StopAfterWaitPipeline(SpeechPipeline):
    def _wait_for_engine(self, job, *args):
        result = super()._wait_for_engine(job, *args)
        if result:
            self.stop()
        return result


class StopBeforeWaitPipeline(SpeechPipeline):
    def _wait_for_engine(self, job, *args):
        self.stop()
        return super()._wait_for_engine(job, *args)


def test_stop_after_engine_wait_prevents_playback(tmp_path: Path) -> None:
    cfg = replace(load_config(tmp_path / "missing.json"), chunk_max_chars=12)
    engine = FakeEngine()
    player = RecordingPlayer()
    pipeline = StopAfterWaitPipeline(engine, player, cfg, data_dir=tmp_path)
    pipeline.start()
    try:
        assert pipeline.submit(SpeechJob("j1", "Hello.", "Bella", "s", "m1"))
        wait_until(lambda: pipeline._jobs.unfinished_tasks == 0)
        assert engine.generated == []
        assert player.played == []
    finally:
        pipeline.shutdown()


def test_stop_before_engine_wait_prevents_playback(tmp_path: Path) -> None:
    cfg = replace(load_config(tmp_path / "missing.json"), chunk_max_chars=12)
    engine = FakeEngine()
    player = RecordingPlayer()
    pipeline = StopBeforeWaitPipeline(engine, player, cfg, data_dir=tmp_path)
    pipeline.start()
    try:
        assert pipeline.submit(SpeechJob("j1", "Hello.", "Bella", "s", "m1"))
        wait_until(lambda: pipeline._jobs.unfinished_tasks == 0)
        assert engine.generated == []
        assert player.played == []
    finally:
        pipeline.shutdown()
