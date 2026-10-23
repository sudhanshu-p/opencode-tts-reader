"""Suppress repeated speech requests within short time windows."""

import threading
import time


class Deduper:
    """Thread-safe duplicate suppression keyed by message ID and text hash."""

    def __init__(self, message_ttl_s: int = 3600, hash_ttl_s: int = 300) -> None:
        self.message_ttl_s = message_ttl_s
        self.hash_ttl_s = hash_ttl_s
        self._lock = threading.Lock()
        self._messages: dict[str, float] = {}
        self._hashes: dict[str, float] = {}

    def seen_or_remember(
        self, message_id: str | None, text_hash: str, *, now: float | None = None
    ) -> bool:
        """Return ``True`` when the request is a duplicate, else record it."""
        if now is None:
            now = time.monotonic()
        with self._lock:
            self._prune(self._messages, self.message_ttl_s, now)
            self._prune(self._hashes, self.hash_ttl_s, now)

            if message_id is not None and message_id in self._messages:
                return True
            if text_hash in self._hashes:
                return True

            if message_id is not None:
                self._messages[message_id] = now
            self._hashes[text_hash] = now
            return False

    @staticmethod
    def _prune(entries: dict[str, float], ttl_s: float, now: float) -> None:
        expired = [
            key for key, inserted_at in entries.items() if now - inserted_at >= ttl_s
        ]
        for key in expired:
            del entries[key]
