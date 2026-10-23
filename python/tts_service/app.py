"""FastAPI app exposing the reader's local HTTP API."""

from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager
from dataclasses import fields, replace
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException

from tts_service.config import Config, save_config
from tts_service.protocol import (
    ConfigPatch,
    PreviewRequest,
    PreviewResponse,
)
from tts_service.runtime import Runtime
from tts_service.text import classify

logger = logging.getLogger(__name__)


def _load_engine(runtime: Runtime) -> None:
    """Load the engine in the background, recording any failure."""
    try:
        runtime.engine.load()
    except Exception as exc:
        runtime.load_error = str(exc)
        logger.exception("engine load failed")
    finally:
        runtime.loading = False


def _config_payload(config: Config) -> dict:
    """Return every config field as JSON-serializable values."""
    payload: dict = {}
    for field in fields(config):
        value = getattr(config, field.name)
        payload[field.name] = str(value) if isinstance(value, Path) else value
    return payload


def create_app(runtime: Runtime) -> FastAPI:
    """Build the HTTP app around an already-constructed runtime."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        runtime.pipeline.start()
        if not runtime.engine.loaded:
            runtime.loading = True
            threading.Thread(
                target=_load_engine,
                args=(runtime,),
                name="tts-engine-load",
                daemon=True,
            ).start()
        try:
            yield
        finally:
            runtime.pipeline.shutdown()

    app = FastAPI(title="OpenCode TTS Reader", lifespan=lifespan)

    @app.get("/health")
    def health() -> dict:
        status = runtime.pipeline.status()
        config = runtime.config
        return {
            "ok": runtime.load_error is None,
            "loading": runtime.loading,
            "load_error": runtime.load_error,
            "model": config.model,
            "backend": config.backend,
            "voice": config.voice,
            "muted": config.muted,
            "auto_read": config.auto_read,
            "queue_depth": status.get("queue_depth", 0),
            "speaking": status.get("speaking", False),
            "pending_count": runtime.pending.count(),
        }

    @app.get("/config")
    def get_config() -> dict:
        return _config_payload(runtime.config)

    @app.patch("/config")
    def patch_config(patch: ConfigPatch) -> dict:
        changes = patch.model_dump(exclude_unset=True, exclude_none=True)
        try:
            updated = replace(runtime.config, **changes)
            updated.validate()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if runtime.engine.loaded and "voice" in changes:
            if updated.voice not in runtime.engine.list_voices():
                raise HTTPException(
                    status_code=400, detail=f"unknown voice: {updated.voice}"
                )
        save_config(updated, runtime.config_path)
        runtime.config = updated
        logger.info("config updated fields=%s", ",".join(sorted(changes)))
        return _config_payload(updated)

    @app.get("/voices")
    def voices() -> dict:
        if not runtime.engine.loaded:
            return {"voices": [], "loading": True}
        return {
            "voices": list(runtime.engine.list_voices()),
            "loading": runtime.loading,
        }

    @app.post("/preview", response_model=PreviewResponse)
    def preview(request: PreviewRequest) -> PreviewResponse:
        result = classify(
            request.text,
            turn_has_markdown_file=request.turn_has_markdown_file,
            config=runtime.config,
        )
        logger.info("preview words=%s headings=%s", result.words, result.headings)
        return PreviewResponse(
            filtered=result.filtered,
            words=result.words,
            headings=result.headings,
            table_rows=result.table_rows,
            document_like=result.document_like,
            too_long=result.too_long,
            reason=result.reason.value if result.reason is not None else None,
        )

    return app
