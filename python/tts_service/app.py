"""FastAPI app exposing the reader's local HTTP API."""

from __future__ import annotations

import hashlib
import io
import logging
import os
import signal
import threading
import time
from contextlib import asynccontextmanager
from dataclasses import fields, replace
from pathlib import Path
from typing import AsyncIterator
from uuid import uuid4

import soundfile as sf
from fastapi import BackgroundTasks, FastAPI, HTTPException, Response

from tts_service.config import Config, save_config
from tts_service.pending import PendingReply
from tts_service.pipeline import SpeechJob
from tts_service.protocol import (
    ConfigPatch,
    PreviewRequest,
    PreviewResponse,
    SpeakPendingRequest,
    SpeakRequest,
    SpeakResponse,
    SynthesizeRequest,
)
from tts_service.runtime import Runtime
from tts_service.text import Reason, classify

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


def _save_muted(runtime: Runtime, muted: bool) -> None:
    """Persist a new mute state and publish it on the runtime."""
    updated = replace(runtime.config, muted=muted)
    updated.validate()
    save_config(updated, runtime.config_path)
    runtime.config = updated
    logger.info("muted=%s", muted)


def _shutdown(runtime: Runtime) -> None:
    """Ask the owning process to exit after the HTTP response has flushed."""
    callback = runtime.shutdown_callback
    if callback is not None:
        callback()
        return
    time.sleep(0.2)
    os.kill(os.getpid(), signal.SIGTERM)


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

    @app.post("/speak", response_model=SpeakResponse)
    def speak(request: SpeakRequest) -> SpeakResponse:
        config = runtime.config

        if request.voice is not None and runtime.engine.loaded:
            if request.voice not in runtime.engine.list_voices():
                raise HTTPException(
                    status_code=400, detail=f"unknown voice: {request.voice}"
                )

        if request.source == "auto" and (config.muted or not config.auto_read):
            logger.info("speak muted source=auto")
            return SpeakResponse(action="muted", words=0)

        result = classify(
            request.text,
            turn_has_markdown_file=request.turn_has_markdown_file,
            config=config,
        )

        if not result.filtered.strip():
            if config.announce_skipped:
                runtime.pipeline.submit(
                    SpeechJob(
                        id=uuid4().hex,
                        text="Nothing to read aloud.",
                        voice=request.voice or config.voice,
                        session_id=request.session_id,
                        message_id=request.message_id,
                        source="notice",
                    )
                )
            logger.info(
                "speak empty source=%s message_id=%s", request.source, request.message_id
            )
            return SpeakResponse(action="empty", words=0)

        if request.source == "auto" and not request.force:
            text_hash = hashlib.sha256(result.filtered.encode("utf-8")).hexdigest()
            if runtime.deduper.seen_or_remember(request.message_id, text_hash):
                logger.info(
                    "speak duplicate message_id=%s words=%s",
                    request.message_id,
                    result.words,
                )
                return SpeakResponse(action="duplicate", words=result.words)

        if request.source == "auto" and result.reason is Reason.MARKDOWN:
            runtime.pending.put(
                PendingReply(
                    session_id=request.session_id,
                    message_id=request.message_id or "",
                    text=result.filtered,
                    reason=Reason.MARKDOWN.value,
                    words=result.words,
                    created_at=time.time(),
                )
            )
            logger.info(
                "speak pending reason=markdown message_id=%s words=%s",
                request.message_id,
                result.words,
            )
            return SpeakResponse(
                action="pending", reason="markdown", words=result.words
            )

        if request.source == "auto" and result.reason is Reason.LONG:
            runtime.pending.put(
                PendingReply(
                    session_id=request.session_id,
                    message_id=request.message_id or "",
                    text=result.filtered,
                    reason=Reason.LONG.value,
                    words=result.words,
                    created_at=time.time(),
                )
            )
            notice = (
                f"This reply is {result.words} words. It was not read aloud. "
                "Run the reader speak command to hear it."
            )
            if not runtime.pipeline.submit(
                SpeechJob(
                    id=uuid4().hex,
                    text=notice,
                    voice=request.voice or config.voice,
                    session_id=request.session_id,
                    message_id=request.message_id,
                    source="notice",
                )
            ):
                logger.warning(
                    "speak queue_full reason=long message_id=%s", request.message_id
                )
                return SpeakResponse(action="queue_full", words=result.words)
            logger.info(
                "speak pending reason=long message_id=%s words=%s",
                request.message_id,
                result.words,
            )
            return SpeakResponse(action="pending", reason="long", words=result.words)

        job = SpeechJob(
            id=uuid4().hex,
            text=result.filtered,
            voice=request.voice or config.voice,
            session_id=request.session_id,
            message_id=request.message_id,
            source=request.source,
        )
        if not runtime.pipeline.submit(job):
            logger.warning(
                "speak queue_full source=%s message_id=%s",
                request.source,
                request.message_id,
            )
            return SpeakResponse(action="queue_full", words=result.words)
        logger.info(
            "speak queued job_id=%s source=%s message_id=%s words=%s",
            job.id,
            request.source,
            request.message_id,
            result.words,
        )
        return SpeakResponse(action="queued", words=result.words, job_id=job.id)

    @app.post("/speak-pending", response_model=SpeakResponse)
    def speak_pending(request: SpeakPendingRequest) -> SpeakResponse:
        if (
            request.session_id is not None
            and runtime.pending.get(request.session_id) is None
        ):
            raise HTTPException(status_code=404, detail="no pending reply")
        reply = runtime.pending.pop(request.session_id)
        if reply is None:
            raise HTTPException(status_code=404, detail="no pending reply")
        if request.session_id is not None and reply.session_id != request.session_id:
            # A concurrent removal can make ``pop`` fall back to another session.
            runtime.pending.put(reply)
            raise HTTPException(status_code=404, detail="no pending reply")
        job = SpeechJob(
            id=uuid4().hex,
            text=reply.text,
            voice=runtime.config.voice,
            session_id=reply.session_id,
            message_id=reply.message_id,
            source="manual",
        )
        if not runtime.pipeline.submit(job):
            runtime.pending.put(reply)
            logger.warning(
                "speak-pending queue_full message_id=%s", reply.message_id
            )
            return SpeakResponse(action="queue_full", words=reply.words)
        logger.info(
            "speak-pending queued job_id=%s message_id=%s words=%s",
            job.id,
            reply.message_id,
            reply.words,
        )
        return SpeakResponse(action="queued", words=reply.words, job_id=job.id)

    @app.get("/pending")
    def pending(session_id: str | None = None) -> dict:
        replies = runtime.pending.list()
        if session_id is not None:
            replies = [reply for reply in replies if reply.session_id == session_id]
        return {
            "pending": [
                {
                    "session_id": reply.session_id,
                    "message_id": reply.message_id,
                    "reason": reply.reason,
                    "words": reply.words,
                    "created_at": reply.created_at,
                }
                for reply in replies
            ]
        }

    @app.post("/stop")
    def stop() -> dict:
        runtime.pipeline.stop()
        logger.info("speech stopped")
        return {"stopped": True}

    @app.post("/mute")
    def mute() -> dict:
        try:
            _save_muted(runtime, True)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        runtime.pipeline.stop()
        return {"muted": True}

    @app.post("/unmute")
    def unmute() -> dict:
        try:
            _save_muted(runtime, False)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"muted": False}

    @app.post("/synthesize")
    def synthesize(request: SynthesizeRequest) -> Response:
        if not runtime.engine.loaded:
            raise HTTPException(status_code=503, detail="engine not loaded")
        if (
            request.voice is not None
            and request.voice not in runtime.engine.list_voices()
        ):
            raise HTTPException(
                status_code=400, detail=f"unknown voice: {request.voice}"
            )
        audio, sample_rate = runtime.engine.synthesize(
            request.text, request.voice or runtime.config.voice
        )
        buffer = io.BytesIO()
        sf.write(buffer, audio, sample_rate, format="WAV", subtype="PCM_16")
        content = buffer.getvalue()
        logger.info("synthesize bytes=%s sample_rate=%s", len(content), sample_rate)
        return Response(content=content, media_type="audio/wav")

    @app.post("/shutdown")
    def shutdown(background_tasks: BackgroundTasks) -> dict:
        background_tasks.add_task(_shutdown, runtime)
        return {"shutting_down": True}

    return app
