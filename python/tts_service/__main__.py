"""Run the reader service under a single-process lock."""

from __future__ import annotations

import atexit
import fcntl
import json
import os
from pathlib import Path

import uvicorn

from tts_service.app import create_default_app
from tts_service.config import load_config

_lock_file = None


def _cleanup_pid(pid_path: Path) -> None:
    try:
        pid_path.unlink()
    except FileNotFoundError:
        pass


def main() -> int:
    """Start uvicorn, or report that another instance already holds the lock."""
    global _lock_file

    config = load_config()
    config.data_dir.mkdir(parents=True, exist_ok=True)

    lock_file = (config.data_dir / "service.lock").open("w")
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock_file.close()
        print(json.dumps({"started": False, "reason": "already running"}))
        return 0

    _lock_file = lock_file
    pid_path = config.data_dir / "service.pid"
    pid_path.write_text(f"{os.getpid()}\n", encoding="utf-8")
    atexit.register(_cleanup_pid, pid_path)
    atexit.register(lock_file.close)

    uvicorn.run(
        create_default_app(),
        host=config.host,
        port=config.port,
        log_level=config.log_level,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
