"""Runtime wiring shared by the HTTP app and its lifecycle hooks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

import numpy as np

from tts_service.audio import AudioPlayer
from tts_service.config import Config, config_path as default_config_path, load_config
from tts_service.dedupe import Deduper
from tts_service.engine import TTSEngine
from tts_service.pending import PendingStore
from tts_service.pipeline import SpeechJob, SpeechPipeline


class EngineLike(Protocol):
    """Synthesis backend used by the pipeline and the HTTP app."""

    loaded: bool

    def load(self) -> None: ...

    def list_voices(self) -> tuple[str, ...]: ...

    def synthesize(self, text: str, voice: str) -> tuple[np.ndarray, int]: ...


class PipelineLike(Protocol):
    """Queue and playback backend driven by the HTTP app."""

    def start(self) -> None: ...

    def submit(self, job: SpeechJob) -> bool: ...

    def stop(self) -> None: ...

    def shutdown(self) -> None: ...

    def status(self) -> dict: ...


@dataclass
class Runtime:
    """Everything the HTTP app needs, assembled once at startup."""

    config: Config
    config_path: Path
    engine: EngineLike
    pipeline: PipelineLike
    pending: PendingStore
    deduper: Deduper
    loading: bool = False
    load_error: str | None = None
    shutdown_callback: Callable[[], None] | None = None


def build_runtime(config_path: Path | None = None) -> Runtime:
    """Load configuration and construct the default runtime."""
    target = config_path or default_config_path()
    config = load_config(target)
    engine = TTSEngine(config)
    player = AudioPlayer()
    pipeline = SpeechPipeline(engine, player, config, data_dir=config.data_dir)
    return Runtime(
        config=config,
        config_path=target,
        engine=engine,
        pipeline=pipeline,
        pending=PendingStore(config.data_dir / "pending.json"),
        deduper=Deduper(config.message_dedupe_ttl_s, config.text_dedupe_ttl_s),
    )
