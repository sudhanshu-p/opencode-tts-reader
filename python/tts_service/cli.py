"""Command-line controls for the local OpenCode TTS reader service."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import fields
from pathlib import Path
from typing import Any

import httpx

from tts_service.config import Config, config_path as default_config_path, load_config

START_TIMEOUT_S = 120.0
HEALTH_INTERVAL_S = 0.5
LOG_LINES = 100

_COMMANDS = {
    "start": "Start the reader service in the background",
    "stop": "Stop the reader service",
    "restart": "Restart the reader service",
    "status": "Print the service health status",
    "speak": "Speak the given words",
    "speak-file": "Speak a markdown file",
    "voice": "Change the configured voice",
    "voices": "List the available voices",
    "mute": "Mute automatic reading",
    "unmute": "Unmute automatic reading",
    "pending": "List replies held for an explicit read",
    "logs": "Print the last service log lines",
    "config": "Print the config path and values",
}


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser with every supported subcommand."""
    parser = argparse.ArgumentParser(
        prog="opencode-tts",
        description="Control the local OpenCode TTS reader service.",
    )
    subparsers = parser.add_subparsers(dest="command")
    for name, help_text in _COMMANDS.items():
        subparser = subparsers.add_parser(name, help=help_text)
        subparser.set_defaults(command=name)
    speak = subparsers.choices["speak"]
    speak.add_argument("text", nargs="+", help="Words to speak")
    speak_file = subparsers.choices["speak-file"]
    speak_file.add_argument("path", type=Path, help="Markdown file to speak")
    voice = subparsers.choices["voice"]
    voice.add_argument("name", help="Voice name to configure")
    return parser


def _print_json(payload: Any) -> None:
    print(json.dumps(payload))


def _response_json(response: httpx.Response) -> Any:
    response.raise_for_status()
    return response.json()


def _config_payload(config: Config) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for field in fields(config):
        value = getattr(config, field.name)
        payload[field.name] = str(value) if isinstance(value, Path) else value
    return payload


def _healthy(client: httpx.Client) -> bool:
    try:
        response = client.get("/health")
    except httpx.HTTPError:
        return False
    return response.status_code == 200


def _read_pid(pid_path: Path) -> int | None:
    try:
        return int(pid_path.read_text(encoding="utf-8").strip())
    except (FileNotFoundError, ValueError):
        return None


def _start(config: Config, client: httpx.Client) -> int:
    if _healthy(client):
        _print_json({"started": False})
        return 0

    config.data_dir.mkdir(parents=True, exist_ok=True)
    log_path = config.data_dir / "service.log"
    python_dir = Path(__file__).resolve().parent.parent
    with log_path.open("ab") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "tts_service"],
            cwd=str(python_dir),
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            start_new_session=True,
        )

    pid_path = config.data_dir / "service.pid"
    pid_path.write_text(f"{process.pid}\n", encoding="utf-8")

    deadline = time.monotonic() + START_TIMEOUT_S
    while time.monotonic() < deadline:
        if _healthy(client):
            _print_json({"started": True, "pid": process.pid})
            return 0
        if process.poll() is not None:
            _print_json({"started": False, "reason": "exited"})
            return 1
        time.sleep(HEALTH_INTERVAL_S)

    _print_json({"started": False, "reason": "timeout"})
    return 1


def _stop(config: Config, client: httpx.Client) -> dict[str, Any]:
    pid_path = config.data_dir / "service.pid"
    try:
        payload = _response_json(client.post("/shutdown"))
    except httpx.HTTPError:
        pid = _read_pid(pid_path)
        if pid is not None:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
        payload = {"stopped": True}
    pid_path.unlink(missing_ok=True)
    return payload


def _restart(config: Config, client: httpx.Client) -> int:
    _stop(config, client)
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline and _healthy(client):
        time.sleep(HEALTH_INTERVAL_S)
    return _start(config, client)


def _speak_body(text: str) -> dict[str, Any]:
    return {"text": text, "source": "manual", "force": True}


def _dispatch(args: argparse.Namespace, config: Config, client: httpx.Client) -> int:
    command = args.command

    if command == "start":
        return _start(config, client)
    if command == "stop":
        _print_json(_stop(config, client))
        return 0
    if command == "restart":
        return _restart(config, client)
    if command == "status":
        _print_json(_response_json(client.get("/health")))
        return 0
    if command == "speak":
        _print_json(_response_json(client.post("/speak", json=_speak_body(" ".join(args.text)))))
        return 0
    if command == "speak-file":
        try:
            text = args.path.read_text(encoding="utf-8")
        except OSError as exc:
            print(json.dumps({"error": str(exc)}), file=sys.stderr)
            return 1
        _print_json(_response_json(client.post("/speak", json=_speak_body(text))))
        return 0
    if command == "voice":
        _print_json(_response_json(client.patch("/config", json={"voice": args.name})))
        return 0
    if command == "voices":
        _print_json(_response_json(client.get("/voices")))
        return 0
    if command == "mute":
        _print_json(_response_json(client.post("/mute")))
        return 0
    if command == "unmute":
        _print_json(_response_json(client.post("/unmute")))
        return 0
    if command == "pending":
        _print_json(_response_json(client.get("/pending")))
        return 0
    if command == "logs":
        log_path = config.data_dir / "service.log"
        try:
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except FileNotFoundError:
            lines = []
        print("\n".join(lines[-LOG_LINES:]))
        return 0
    if command == "config":
        print(default_config_path())
        print(json.dumps(_config_payload(config), indent=2))
        return 0

    return 2


def main(argv: list[str] | None = None, client: httpx.Client | None = None) -> int:
    """Run one CLI command, returning a shell-style exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_usage(sys.stderr)
        return 2

    config = load_config()
    owns_client = client is None
    if client is None:
        client = httpx.Client(
            base_url=f"http://127.0.0.1:{config.port}",
            timeout=10,
        )
    try:
        return _dispatch(args, config, client)
    except httpx.HTTPError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1
    finally:
        if owns_client:
            client.close()


if __name__ == "__main__":
    raise SystemExit(main())
