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
        self.stopped = False

    def start(self) -> None:
        pass

    def submit(self, job) -> bool:
        self.jobs.append(job)
        return True

    def stop(self) -> None:
        self.stopped = True

    def shutdown(self) -> None:
        pass

    def status(self) -> dict:
        return {"queue_depth": len(self.jobs), "speaking": False, "current_job": None}


def make_runtime(tmp_path: Path) -> Runtime:
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


def test_health_and_config(tmp_path: Path) -> None:
    rt = make_runtime(tmp_path)
    with TestClient(create_app(rt)) as client:
        health = client.get("/health")
        config = client.get("/config")
    assert health.status_code == 200
    assert health.json()["voice"] == "Bella"
    assert health.json()["pending_count"] == 0
    assert config.json()["backend"] == "mlx"
    assert config.json()["port"] == 8765


def test_preview_filters_code(tmp_path: Path) -> None:
    rt = make_runtime(tmp_path)
    with TestClient(create_app(rt)) as client:
        response = client.post(
            "/preview",
            json={"text": "Before.\n```python\nprint('x')\n```\nAfter."},
        )
    assert response.status_code == 200
    assert response.json()["filtered"].split() == ["Before.", "After."]
    assert response.json()["reason"] is None


def test_voices(tmp_path: Path) -> None:
    rt = make_runtime(tmp_path)
    with TestClient(create_app(rt)) as client:
        response = client.get("/voices")
    assert response.json() == {"voices": ["Bella", "Bruno"], "loading": False}


def test_patch_persists_and_updates_runtime(tmp_path: Path) -> None:
    rt = make_runtime(tmp_path)
    with TestClient(create_app(rt)) as client:
        response = client.patch("/config", json={"voice": "Bruno", "muted": True})
    assert response.status_code == 200
    assert rt.config.voice == "Bruno"
    assert rt.config.muted is True
    assert load_config(rt.config_path).voice == "Bruno"


def test_patch_rejects_unknown_voice(tmp_path: Path) -> None:
    rt = make_runtime(tmp_path)
    with TestClient(create_app(rt)) as client:
        response = client.patch("/config", json={"voice": "Nobody"})
    assert response.status_code == 400
