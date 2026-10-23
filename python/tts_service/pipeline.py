"""FIFO synthesis and playback pipeline for queued speech jobs."""

import logging
import queue
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from tts_service.audio import write_wav
from tts_service.config import Config

logger = logging.getLogger(__name__)

_PARAGRAPH_RE = re.compile(r"\n\s*\n")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
_ENGINE_POLL_INTERVAL_S = 0.1
_ENGINE_READY_TIMEOUT_S = 120.0


@dataclass(frozen=True)
class SpeechJob:
    """A single request to speak ``text`` with ``voice``."""

    id: str
    text: str
    voice: str
    session_id: str | None
    message_id: str | None
    source: str = "auto"


def split_chunks(text: str, max_chars: int = 260) -> list[str]:
    """Split ``text`` into speakable chunks no longer than ``max_chars``."""
    if max_chars <= 0:
        raise ValueError(f"max_chars must be positive, got {max_chars!r}")

    chunks: list[str] = []
    for paragraph in _PARAGRAPH_RE.split(text):
        sentences = [
            sentence.strip()
            for sentence in _SENTENCE_RE.split(paragraph)
            if sentence.strip()
        ]
        current = ""
        for sentence in sentences:
            candidate = f"{current} {sentence}" if current else sentence
            if len(candidate) <= max_chars:
                current = candidate
                continue
            if current:
                chunks.append(current)
                current = ""
            if len(sentence) <= max_chars:
                current = sentence
                continue
            pieces = _split_long(sentence, max_chars)
            chunks.extend(pieces[:-1])
            current = pieces[-1] if pieces else ""
        if current:
            chunks.append(current)

    return [chunk for chunk in chunks if chunk]


def _split_long(text: str, max_chars: int) -> list[str]:
    """Greedily pack words into chunks, hard-splitting oversized words."""
    pieces: list[str] = []
    current = ""
    for word in text.split():
        if len(word) > max_chars:
            if current:
                pieces.append(current)
                current = ""
            pieces.extend(
                word[start : start + max_chars]
                for start in range(0, len(word), max_chars)
            )
            continue
        candidate = f"{current} {word}" if current else word
        if len(candidate) <= max_chars:
            current = candidate
        else:
            pieces.append(current)
            current = word
    if current:
        pieces.append(current)
    return pieces


class SpeechPipeline:
    """Synthesize queued jobs in the background and play them in order."""

    def __init__(
        self,
        engine,
        player,
        config: Config,
        *,
        data_dir: Path | None = None,
    ) -> None:
        self.engine = engine
        self.player = player
        self.config = config
        self._audio_dir = Path(data_dir or config.data_dir) / "audio"
        self._jobs: queue.Queue[SpeechJob | None] = queue.Queue()
        self._play_queue: queue.Queue[tuple[int, Path] | None] = queue.Queue(maxsize=4)
        self._state_lock = threading.Lock()
        self._generation = 0
        self._current_job: str | None = None
        self._started = False
        self._synthesis_thread: threading.Thread | None = None
        self._playback_thread: threading.Thread | None = None

    def start(self) -> None:
        """Create the audio directory and start both worker threads."""
        with self._state_lock:
            if self._started:
                return
            self._started = True
        self._audio_dir.mkdir(parents=True, exist_ok=True)
        self._synthesis_thread = threading.Thread(
            target=self._synthesis_loop, name="tts-synthesis", daemon=True
        )
        self._playback_thread = threading.Thread(
            target=self._playback_loop, name="tts-playback", daemon=True
        )
        self._synthesis_thread.start()
        self._playback_thread.start()

    def submit(self, job: SpeechJob) -> bool:
        """Queue ``job`` for synthesis, returning ``False`` when rejected."""
        with self._state_lock:
            if not self._started:
                return False
        if self._jobs.qsize() >= self.config.max_queue:
            logger.warning(
                "queue full job_id=%s max_queue=%s", job.id, self.config.max_queue
            )
            return False
        self._jobs.put(job)
        return True

    def stop(self) -> None:
        """Cancel in-flight and queued speech without stopping the workers."""
        with self._state_lock:
            self._generation += 1
            self._current_job = None
        self._drain_jobs()
        self._drain_playback()
        self.player.stop()

    def shutdown(self) -> None:
        """Stop speech and wait for both worker threads to exit."""
        with self._state_lock:
            self._started = False
        self.stop()
        self._jobs.put(None)
        self._play_queue.put(None)
        for thread in (self._synthesis_thread, self._playback_thread):
            if thread is not None:
                thread.join(timeout=5)
        self._drain_playback()

    def status(self) -> dict:
        """Return the current queue depth, playback state, and job ID."""
        with self._state_lock:
            current_job = self._current_job
        return {
            "queue_depth": self._jobs.qsize() + self._play_queue.qsize(),
            "speaking": self.player.playing,
            "current_job": current_job,
        }

    def _synthesis_loop(self) -> None:
        while True:
            job = self._jobs.get()
            if job is None:
                self._jobs.task_done()
                return
            try:
                self._process_job(job)
            finally:
                self._jobs.task_done()

    def _process_job(self, job: SpeechJob) -> None:
        try:
            if not self._wait_for_engine(job):
                return
            with self._state_lock:
                self._current_job = job.id
                generation = self._generation
            logger.info("synthesis started job_id=%s", job.id)
            chunks = split_chunks(job.text, self.config.chunk_max_chars)
            for index, chunk in enumerate(chunks):
                if self._generation_changed(generation):
                    logger.info(
                        "synthesis cancelled job_id=%s reason=generation-changed",
                        job.id,
                    )
                    return
                audio, sample_rate = self.engine.synthesize(chunk, job.voice)
                path = self._audio_dir / f"{job.id}-{index}.wav"
                write_wav(path, audio, sample_rate)
                if not self._enqueue_playback(generation, path):
                    logger.info(
                        "synthesis cancelled job_id=%s reason=generation-changed",
                        job.id,
                    )
                    return
            logger.info("synthesis finished job_id=%s chunks=%s", job.id, len(chunks))
        except Exception:
            logger.exception("synthesis failed job_id=%s", job.id)
        finally:
            with self._state_lock:
                if self._current_job == job.id:
                    self._current_job = None

    def _wait_for_engine(self, job: SpeechJob) -> bool:
        with self._state_lock:
            generation = self._generation
        deadline = time.monotonic() + _ENGINE_READY_TIMEOUT_S
        while not self.engine.loaded:
            if self._generation_changed(generation):
                logger.warning(
                    "synthesis skipped job_id=%s reason=engine-not-ready", job.id
                )
                return False
            if time.monotonic() >= deadline:
                logger.warning(
                    "synthesis skipped job_id=%s reason=engine-not-ready", job.id
                )
                return False
            time.sleep(_ENGINE_POLL_INTERVAL_S)
        if self._generation_changed(generation):
            logger.warning(
                "synthesis skipped job_id=%s reason=engine-not-ready", job.id
            )
            return False
        return True

    def _enqueue_playback(self, generation: int, path: Path) -> bool:
        while True:
            if self._generation_changed(generation):
                self._unlink(path)
                return False
            try:
                self._play_queue.put(
                    (generation, path), timeout=_ENGINE_POLL_INTERVAL_S
                )
                return True
            except queue.Full:
                continue

    def _playback_loop(self) -> None:
        while True:
            item = self._play_queue.get()
            if item is None:
                self._play_queue.task_done()
                return
            generation, path = item
            try:
                if not self._generation_changed(generation):
                    self.player.play(path)
            except Exception:
                logger.exception("playback failed path=%s", path)
            finally:
                self._unlink(path)
                self._play_queue.task_done()

    def _generation_changed(self, generation: int) -> bool:
        with self._state_lock:
            return self._generation != generation

    def _drain_jobs(self) -> None:
        while True:
            try:
                job = self._jobs.get_nowait()
            except queue.Empty:
                return
            try:
                if job is not None:
                    logger.info("dropped queued job_id=%s reason=stopped", job.id)
            finally:
                self._jobs.task_done()

    def _drain_playback(self) -> None:
        while True:
            try:
                item = self._play_queue.get_nowait()
            except queue.Empty:
                return
            try:
                if item is not None:
                    _, path = item
                    self._unlink(path)
                    logger.info("dropped queued audio path=%s reason=stopped", path)
            finally:
                self._play_queue.task_done()

    @staticmethod
    def _unlink(path: Path) -> None:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        except OSError as exc:
            logger.warning("could not remove audio path=%s error=%s", path, exc)
