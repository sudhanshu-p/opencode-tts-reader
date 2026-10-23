"""Persist held replies so they can be read once the user asks for them."""

import json
import logging
import os
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_GLOBAL_KEY = "__global__"
_VERSION = 1


@dataclass(frozen=True)
class PendingReply:
    session_id: str | None
    message_id: str
    text: str
    reason: str
    words: int
    created_at: float


def _session_key(session_id: str | None) -> str:
    return _GLOBAL_KEY if session_id is None else session_id


class PendingStore:
    """Thread-safe on-disk store of the latest held reply per session."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._replies = self._load()

    def put(self, reply: PendingReply) -> None:
        """Store ``reply``, replacing any existing reply for its session."""
        with self._lock:
            self._replies[_session_key(reply.session_id)] = reply
            self._save()

    def get(self, session_id: str | None = None) -> PendingReply | None:
        """Return the session's reply, or the latest reply when ``None``."""
        with self._lock:
            if session_id is not None:
                return self._replies.get(_session_key(session_id))
            latest = self._latest_key()
            return None if latest is None else self._replies[latest]

    def pop(self, session_id: str | None = None) -> PendingReply | None:
        """Remove the session's reply, falling back to the latest reply."""
        with self._lock:
            key = _session_key(session_id)
            if key not in self._replies:
                key = self._latest_key()
            if key is None:
                return None
            reply = self._replies.pop(key)
            self._save()
            return reply

    def list(self) -> list[PendingReply]:
        """Return every held reply, oldest first."""
        with self._lock:
            return sorted(self._replies.values(), key=lambda reply: reply.created_at)

    def count(self) -> int:
        """Return the number of held replies."""
        with self._lock:
            return len(self._replies)

    def clear(self) -> None:
        """Remove every held reply."""
        with self._lock:
            self._replies.clear()
            self._save()

    def _latest_key(self) -> str | None:
        if not self._replies:
            return None
        return max(self._replies, key=lambda key: self._replies[key].created_at)

    def _load(self) -> dict[str, PendingReply]:
        if not self.path.exists():
            logger.warning("pending store %s is missing; starting empty", self.path)
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            entries = raw["replies"]
            if not isinstance(entries, dict):
                raise ValueError("replies must be a JSON object")
            replies: dict[str, PendingReply] = {}
            for key, item in entries.items():
                replies[key] = PendingReply(
                    session_id=None if key == _GLOBAL_KEY else item["session_id"],
                    message_id=item["message_id"],
                    text=item["text"],
                    reason=item["reason"],
                    words=int(item["words"]),
                    created_at=float(item["created_at"]),
                )
            return replies
        except (OSError, TypeError, ValueError, KeyError) as exc:
            logger.warning(
                "pending store %s is unreadable (%s); starting empty", self.path, exc
            )
            return {}

    def _save(self) -> None:
        payload = {
            "version": _VERSION,
            "replies": {
                key: {
                    "session_id": reply.session_id,
                    "message_id": reply.message_id,
                    "text": reply.text,
                    "reason": reply.reason,
                    "words": reply.words,
                    "created_at": reply.created_at,
                }
                for key, reply in self._replies.items()
            },
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
                handle.write("\n")
            os.replace(tmp_name, self.path)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except FileNotFoundError:
                pass
            raise
