from dataclasses import replace
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient

from tts_service.app import create_app
from tts_service.config import load_config
from tts_service.dedupe import Deduper
from tts_service.pending import PendingStore
from tts_service.runtime import Runtime


class FakeEngine:
    loaded = True
    sample_rate = 24000

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


def test_auto_queues_filtered_prose(tmp_path: Path) -> None:
    rt = make_rt(tmp_path)
    with TestClient(create_app(rt)) as client:
        response = client.post("/speak", json={
            "text": "Hello **world**.",
            "session_id": "s1",
            "message_id": "m1",
            "source": "auto",
        })
    assert response.json()["action"] == "queued"
    assert rt.pipeline.jobs[0].text == "Hello world."
    assert rt.pipeline.jobs[0].source == "auto"


def test_muted_and_auto_read_off_are_silent(tmp_path: Path) -> None:
    rt = make_rt(tmp_path)
    rt.config = replace(rt.config, muted=True)
    with TestClient(create_app(rt)) as client:
        assert client.post("/speak", json={"text": "Hello.", "source": "auto"}).json()["action"] == "muted"
    rt.config = replace(rt.config, muted=False, auto_read=False)
    with TestClient(create_app(rt)) as client:
        assert client.post("/speak", json={"text": "Hello.", "source": "auto"}).json()["action"] == "muted"
    assert rt.pipeline.jobs == []


def test_markdown_is_held_without_queueing(tmp_path: Path) -> None:
    rt = make_rt(tmp_path)
    with TestClient(create_app(rt)) as client:
        response = client.post("/speak", json={
            "text": "# A\n\n# B\n\nshort",
            "session_id": "s1",
            "message_id": "m1",
            "source": "auto",
        })
    assert response.json()["action"] == "pending"
    assert response.json()["reason"] == "markdown"
    assert rt.pending.get("s1").reason == "markdown"
    assert rt.pipeline.jobs == []


def test_markdown_stays_held_when_notice_is_disabled(tmp_path: Path) -> None:
    rt = make_rt(tmp_path)
    rt.config = replace(rt.config, ask_markdown="none")
    with TestClient(create_app(rt)) as client:
        response = client.post("/speak", json={
            "text": "# A\n\n# B\n\nshort",
            "session_id": "s1",
            "message_id": "m1",
            "source": "auto",
        })
    assert response.json()["action"] == "pending"
    assert response.json()["reason"] == "markdown"
    assert rt.pending.count() == 1
    assert rt.pipeline.jobs == []


def test_long_reply_holds_and_speaks_notice(tmp_path: Path) -> None:
    rt = make_rt(tmp_path)
    text = " ".join(["word"] * 1501)
    with TestClient(create_app(rt)) as client:
        response = client.post("/speak", json={
            "text": text, "session_id": "s1", "message_id": "m1", "source": "auto",
        })
    assert response.json()["action"] == "pending"
    assert response.json()["reason"] == "long"
    assert rt.pending.get("s1").reason == "long"
    assert len(rt.pipeline.jobs) == 1
    assert rt.pipeline.jobs[0].source == "notice"
    assert rt.pipeline.jobs[0].text == (
        "This reply is 1501 words. It was not read aloud. "
        "Run the reader speak command to hear it."
    )


def test_duplicate_message_id_and_text_hash(tmp_path: Path) -> None:
    rt = make_rt(tmp_path)
    with TestClient(create_app(rt)) as client:
        first = client.post("/speak", json={"text": "Same reply.", "session_id": "s1", "message_id": "m1", "source": "auto"})
        second = client.post("/speak", json={"text": "Same reply.", "session_id": "s1", "message_id": "m1", "source": "auto"})
        third = client.post("/speak", json={"text": "Same reply.", "session_id": "s1", "message_id": "m2", "source": "auto"})
    assert first.json()["action"] == "queued"
    assert second.json()["action"] == "duplicate"
    assert third.json()["action"] == "duplicate"
    assert len(rt.pipeline.jobs) == 1


def test_force_bypasses_dedupe(tmp_path: Path) -> None:
    rt = make_rt(tmp_path)
    with TestClient(create_app(rt)) as client:
        client.post("/speak", json={"text": "Same reply.", "message_id": "m1", "source": "auto"})
        response = client.post("/speak", json={
            "text": "Same reply.", "message_id": "m1", "source": "auto", "force": True,
        })
    assert response.json()["action"] == "queued"
    assert len(rt.pipeline.jobs) == 2


def test_manual_ignores_mute_and_length(tmp_path: Path) -> None:
    rt = make_rt(tmp_path)
    rt.config = replace(rt.config, muted=True)
    text = " ".join(["word"] * 1501)
    with TestClient(create_app(rt)) as client:
        response = client.post("/speak", json={
            "text": text, "session_id": "s1", "message_id": "m1",
            "source": "manual", "force": True,
        })
    assert response.json()["action"] == "queued"
    assert len(rt.pipeline.jobs) == 1
    assert rt.pending.count() == 0


def test_manual_document_speaks(tmp_path: Path) -> None:
    rt = make_rt(tmp_path)
    with TestClient(create_app(rt)) as client:
        response = client.post("/speak", json={
            "text": "# A\n\n# B\n\nshort", "session_id": "s1",
            "source": "manual", "force": True,
        })
    assert response.json()["action"] == "queued"
    assert rt.pending.count() == 0


def test_code_only_is_empty(tmp_path: Path) -> None:
    rt = make_rt(tmp_path)
    with TestClient(create_app(rt)) as client:
        response = client.post("/speak", json={"text": "```\ncode\n```", "source": "auto"})
    assert response.json()["action"] == "empty"
    assert rt.pipeline.jobs == []


def test_queue_full(tmp_path: Path) -> None:
    rt = make_rt(tmp_path)
    rt.pipeline.full = True
    with TestClient(create_app(rt)) as client:
        response = client.post("/speak", json={"text": "Hello.", "source": "auto"})
    assert response.json()["action"] == "queue_full"


def test_voice_override_is_forwarded(tmp_path: Path) -> None:
    rt = make_rt(tmp_path)
    with TestClient(create_app(rt)) as client:
        client.post("/speak", json={"text": "Hello.", "source": "manual", "force": True, "voice": "Bruno"})
    assert rt.pipeline.jobs[0].voice == "Bruno"
