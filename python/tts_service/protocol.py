"""Request and response models shared by the reader's HTTP API."""

from typing import Literal

from pydantic import BaseModel, Field

Reason = Literal["markdown", "long"]


class PreviewRequest(BaseModel):
    """Text submitted for classification without speaking it."""

    text: str = Field(min_length=1, max_length=1_000_000)
    turn_has_markdown_file: bool = False


class PreviewResponse(BaseModel):
    """Filtered text and the classification that produced it."""

    filtered: str
    words: int
    headings: int
    table_rows: int
    document_like: bool
    too_long: bool
    reason: Reason | None


class SpeakRequest(PreviewRequest):
    """Text submitted for speech, optionally tied to a session message."""

    session_id: str | None = None
    message_id: str | None = None
    source: Literal["auto", "manual", "notice"] = "auto"
    force: bool = False
    voice: str | None = None


class SpeakResponse(BaseModel):
    """Outcome of a speech request."""

    action: Literal["queued", "pending", "muted", "duplicate", "empty", "queue_full"]
    reason: Reason | None = None
    words: int = 0
    job_id: str | None = None


class ConfigPatch(BaseModel):
    """Partial configuration update; omitted fields keep their value."""

    voice: str | None = None
    auto_read: bool | None = None
    muted: bool | None = None
    max_words: int | None = Field(default=None, ge=1)
    ask_markdown: Literal["toast", "dialog", "none"] | None = None
    announce_code: bool | None = None
    announce_skipped: bool | None = None
    include_subagents: bool | None = None


class PendingItem(BaseModel):
    """A held reply awaiting an explicit read request."""

    session_id: str | None = None
    message_id: str
    reason: Reason
    words: int
    created_at: float


class SpeakPendingRequest(BaseModel):
    """A request to speak a held reply, optionally scoped to a session."""

    session_id: str | None = None


class SynthesizeRequest(BaseModel):
    """Text to synthesize to WAV without queueing or playing it."""

    text: str = Field(min_length=1, max_length=1_000_000)
    voice: str | None = None
