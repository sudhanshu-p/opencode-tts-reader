import io
from dataclasses import replace
from pathlib import Path

import numpy as np
import soundfile as sf
from fastapi.testclient import TestClient

from tts_service.app import create_app
from tts_service.config import load_config
from tts_service.dedupe import Deduper
from tts_service.pending import PendingReply, PendingStore
from tts_service.runtime import Runtime


class FakeEngine:
    def __init__(self, loaded: bool = True) -> None:
        self.loaded = loaded
        self.sample_rate = 24000

    def load(self) -> None:
        pass

    def list_voices(self):
        return ("Bella", "Bruno")

    def synthesize(self, text: str, voice: str):
        return np.zeros(2400, dtype=np.float32), 24000


class FakePipeline:
    def __init__(self) -> None:
        self.jobs = []
        self.full = False
        self.stopped = False

    def start(self) -> None:
        pass

    def submit(self, job) -> bool:
        if self.full:
            return False
        self.jobs.append(job)
        return True

    def stop(self) -> None:
        self.stopped = True

    def shutdown(self) -> None:
        pass

    def status(self) -> dict:
        return {"queue_depth": len(self.jobs), "speaking": False, "current_job": None}


def make_rt(tmp_path: Path) -> Runtime:
    cfg = replace(load_config(tmp_path / "missing.json"), data_dir=tmp_path / "data")
    return Runtime(
        config=cfg,
        config_path=tmp_path / "config.json",
        engine=FakeEngine(),
        pipeline=FakePipeline(),
        pending=PendingStore(tmp_path / "pending.json"),
        deduper=Deduper(),
        loading=False,
    )


def add_pending(rt: Runtime) -> None:
    rt.pending.put(PendingReply(
        session_id="s1", message_id="m1", text="Hello.", reason="markdown",
        words=1, created_at=1.0,
    ))


def test_speak_pending_queues_and_clears(tmp_path: Path) -> None:
    rt = make_rt(tmp_path)
    add_pending(rt)
    with TestClient(create_app(rt)) as client:
        response = client.post("/speak-pending", json={"session_id": "s1"})
    assert response.json()["action"] == "queued"
    assert rt.pipeline.jobs[0].text == "Hello."
    assert rt.pending.count() == 0


def test_speak_pending_missing_is_404(tmp_path: Path) -> None:
    rt = make_rt(tmp_path)
    with TestClient(create_app(rt)) as client:
        assert client.post("/speak-pending", json={}).status_code == 404


def test_speak_pending_queue_full_keeps_reply(tmp_path: Path) -> None:
    rt = make_rt(tmp_path)
    add_pending(rt)
    rt.pipeline.full = True
    with TestClient(create_app(rt)) as client:
        response = client.post("/speak-pending", json={"session_id": "s1"})
    assert response.json()["action"] == "queue_full"
    assert rt.pending.count() == 1


def test_pending_metadata_has_no_text(tmp_path: Path) -> None:
    rt = make_rt(tmp_path)
    add_pending(rt)
    with TestClient(create_app(rt)) as client:
        response = client.get("/pending")
    item = response.json()["pending"][0]
    assert item["message_id"] == "m1"
    assert "text" not in item


def test_pending_filters_by_session(tmp_path: Path) -> None:
    rt = make_rt(tmp_path)
    add_pending(rt)
    rt.pending.put(PendingReply(
        session_id="s2", message_id="m2", text="Second.", reason="markdown",
        words=1, created_at=2.0,
    ))
    with TestClient(create_app(rt)) as client:
        response = client.get("/pending?session_id=s2")
    assert [item["session_id"] for item in response.json()["pending"]] == ["s2"]


def test_stop_calls_pipeline(tmp_path: Path) -> None:
    rt = make_rt(tmp_path)
    with TestClient(create_app(rt)) as client:
        assert client.post("/stop").json() == {"stopped": True}
    assert rt.pipeline.stopped is True


def test_mute_and_unmute_persist(tmp_path: Path) -> None:
    rt = make_rt(tmp_path)
    with TestClient(create_app(rt)) as client:
        assert client.post("/mute").json() == {"muted": True}
        assert load_config(rt.config_path).muted is True
        assert rt.pipeline.stopped is True
        assert client.post("/unmute").json() == {"muted": False}
        assert load_config(rt.config_path).muted is False


def test_synthesize_returns_wav(tmp_path: Path) -> None:
    rt = make_rt(tmp_path)
    with TestClient(create_app(rt)) as client:
        response = client.post("/synthesize", json={"text": "Hello.", "voice": "Bella"})
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert response.content[:4] == b"RIFF"
    data, sr = sf.read(io.BytesIO(response.content))
    assert sr == 24000
    assert len(data) == 2400


def test_synthesize_unavailable_engine_is_503(tmp_path: Path) -> None:
    rt = make_rt(tmp_path)
    rt.engine = FakeEngine(loaded=False)
    client = TestClient(create_app(rt))
    assert client.post("/synthesize", json={"text": "Hello."}).status_code == 503


def test_shutdown_calls_callback(tmp_path: Path) -> None:
    rt = make_rt(tmp_path)
    calls = []
    rt.shutdown_callback = lambda: calls.append(1)
    with TestClient(create_app(rt)) as client:
        assert client.post("/shutdown").json() == {"shutting_down": True}
    assert calls == [1]
