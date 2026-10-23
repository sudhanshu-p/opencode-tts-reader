import json
from pathlib import Path

import httpx

from tts_service.cli import build_parser, main


def mock_client(handler) -> httpx.Client:
    return httpx.Client(base_url="http://127.0.0.1:8765", transport=httpx.MockTransport(handler))


def test_parser_has_all_commands() -> None:
    parser = build_parser()
    for name in ["start", "stop", "restart", "status", "speak", "speak-file", "voice",
                 "voices", "mute", "unmute", "pending", "logs", "config"]:
        assert parser.parse_args([name] if name not in {"speak", "speak-file", "voice"} else {
            "speak": ["speak", "hi"], "speak-file": ["speak-file", "x.md"], "voice": ["voice", "Bella"],
        }[name]).command == name


def test_speak_file_posts_manual_force(tmp_path: Path) -> None:
    path = tmp_path / "note.md"
    path.write_text("# Title\n\nHello.", encoding="utf-8")
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"action": "queued"})

    assert main(["speak-file", str(path)], client=mock_client(handler)) == 0
    body = json.loads(seen[0].content)
    assert body["source"] == "manual"
    assert body["force"] is True
    assert "Hello." in body["text"]


def test_voice_patches_config() -> None:
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"voice": "Bruno"})

    assert main(["voice", "Bruno"], client=mock_client(handler)) == 0
    assert seen[0].method == "PATCH"
    assert json.loads(seen[0].content) == {"voice": "Bruno"}


def test_status_prints_json(capsys) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True, "voice": "Bella"})

    assert main(["status"], client=mock_client(handler)) == 0
    assert json.loads(capsys.readouterr().out)["voice"] == "Bella"


def test_speak_joins_words() -> None:
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"action": "queued"})

    assert main(["speak", "hello", "world"], client=mock_client(handler)) == 0
    assert json.loads(seen[0].content)["text"] == "hello world"
