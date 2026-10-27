# OpenCode TTS Reader

A fully local text-to-speech reader for OpenCode on Apple Silicon. It speaks only
the final prose of a completed reply, using KittenTTS 2 through MLX. There are no
API keys and no cloud speech service.

## What it does

- Reads the final answer prose from a top-level OpenCode turn.
- Never reads reasoning, tool output, code, diffs, tables, URLs, file paths, HTML,
  or LaTeX.
- Holds markdown/document replies until you explicitly run `/reader-speak`.
- Holds replies longer than the configured word limit and offers the same command.
- Plays queued replies one at a time, in completion order.
- Provides local controls for stop, mute, pending replies, logs, and voice choice.

## Requirements

- macOS on Apple Silicon (`Darwin arm64`)
- OpenCode 2.1.x
- [Bun](https://bun.sh/) 1.3+
- [uv](https://docs.astral.sh/uv/) and Python 3.12
- `afplay` (included with macOS)
- About 1 GB of free disk space for the first model download
- 16 GB RAM recommended

## Install

From this repository:

```bash
bash scripts/install.sh
```

The installer:

- syncs the Python environment with `uv`
- warms the KittenTTS 2 model (unless you pass `--skip-warmup`)
- installs Bun dependencies
- links the local plugin into `~/.config/opencode/plugins/opencode-tts`
- links the CLI into `~/.local/bin/opencode-tts`
- creates `~/.config/opencode/tts-reader.json` on first install

Restart OpenCode after installation. Confirm the reader plugin loads through the
TUI toast or the server log. `opencode plugin list` may omit auto-discovered local
plugins; absence from that list is not a failure.

Make sure `~/.local/bin` is on your `PATH` to use `opencode-tts`. Alternatively,
run the venv entrypoint directly:

```bash
python/.venv/bin/opencode-tts status
```

For a preview without changing anything:

```bash
bash scripts/install.sh --dry-run
```

## First run

The first warmup downloads and loads the model once:

```bash
opencode-tts status
```

Then ask OpenCode a short prompt, for example:

```text
Explain what a queue is in two short sentences.
```

The final two sentences should be spoken once.

## Config

The default configuration lives at `~/.config/opencode/tts-reader.json`. A full
example with every field and its default is below. Replace `/Users/you` with your
home directory if you customize the two path fields.

```json
{
  "host": "127.0.0.1",
  "port": 8765,
  "model": "KittenML/kitten-tts-2",
  "backend": "mlx",
  "weights": "packed",
  "device": "mps",
  "voice": "Bella",
  "auto_read": true,
  "muted": false,
  "include_subagents": false,
  "max_words": 1500,
  "document_headings": 2,
  "document_words": 400,
  "markdown_file_words": 200,
  "announce_code": false,
  "announce_skipped": false,
  "ask_markdown": "toast",
  "max_queue": 100,
  "chunk_max_chars": 260,
  "message_dedupe_ttl_s": 3600,
  "text_dedupe_ttl_s": 300,
  "model_cache_dir": "/Users/you/.cache/opencode-tts/models",
  "data_dir": "/Users/you/.local/share/opencode-tts",
  "log_level": "info"
}
```

Important fields:

- `auto_read` — speak final prose automatically when a top-level turn completes.
- `muted` — silence automatic reading; explicit `/reader-speak` still works.
- `max_words` — replies above this limit are held instead of read.
- `ask_markdown` — `toast`, `dialog`, or `none`; controls the held-reply notice.
- `include_subagents` — also consider child-session completions; off by default.
- `chunk_max_chars` — maximum characters per synthesized audio chunk.
- `document_headings` / `document_words` — shape-based document detection.
- `markdown_file_words` — word threshold for markdown-file turns.
- `announce_code` / `announce_skipped` — optional notices for code and skipped text.
- `max_queue` — maximum pending speech jobs before the service reports a full queue.
- `message_dedupe_ttl_s` / `text_dedupe_ttl_s` — duplicate suppression windows.

The Python service is authoritative for validation. Keep `host` at `127.0.0.1`;
the reader is intentionally localhost-only.

## Commands

OpenCode commands:

- `/reader-speak` — speak the reply held for this session.
- `/reader-stop` — stop playback and clear the queue.
- `/reader-mute` — mute automatic reading (also stops current audio).
- `/reader-unmute` — resume automatic reading.
- `/reader-voice` — choose and persist a KittenTTS voice.

CLI commands:

```bash
opencode-tts status
opencode-tts speak "Hello from the reader."
opencode-tts speak-file path/to/document.md
opencode-tts voice Bruno
opencode-tts voices
opencode-tts mute
opencode-tts unmute
opencode-tts pending
opencode-tts logs
opencode-tts stop
opencode-tts config
```

Use `opencode-tts --help` for the full command list.

## What gets read

- Only the final visible text after the last tool call in a top-level turn.
- Never code, diffs, tables, URLs, file paths, HTML, LaTeX, or reasoning.
- Markdown/document-shaped replies are held; a TUI notice explains how to read them.
- Replies above the word limit are held rather than truncated.
- Subagent sessions are skipped by default.
- The reply is filtered again by the Python service before synthesis.

## Privacy

- The service binds to `127.0.0.1` only.
- No API keys, accounts, telemetry, or cloud speech calls.
- Logs contain metadata and actions, not full reply prose.
- The network is used only for the first KittenTTS model download.
- Generated audio and model files stay under your local data/cache directories.

## Troubleshooting

Check service health and logs:

```bash
opencode-tts status
opencode-tts logs
tail -f ~/.local/share/opencode-tts/service.log
```

If playback is silent:

- Confirm `/usr/bin/afplay` exists and your output device is working.
- Run `opencode-tts speak "test"` and check `opencode-tts logs`.
- Make sure the service is running: `opencode-tts status`.
- Restart OpenCode after installing or changing the plugin.

If the first request is slow, the model may still be downloading/loading. The
service queues the request and waits for the engine rather than dropping it.

If a markdown/document reply is not spoken, that is intentional. Run
`/reader-speak` or `opencode-tts speak-file <path>`.

If the plugin does not load, restart OpenCode and inspect the server log for
`loading plugin ... entrypoint=.../index.ts`. `opencode plugin list` may not show
local plugins. As a documented fallback only, back up
`~/.config/opencode/opencode.jsonc` and add an explicit `plugins` entry pointing
at this repository, preserving any existing plugins such as `superpowers`. The
singular `plugin` key is deprecated in newer configs; do not remove it until both
plugins load.

## Uninstall

```bash
opencode-tts stop
rm -f ~/.config/opencode/plugins/opencode-tts
rm -f ~/.local/bin/opencode-tts
```

Optionally remove local data and the model cache:

```bash
rm -rf ~/.local/share/opencode-tts
rm -rf ~/.cache/opencode-tts
```

## Licenses

This repository's own code is licensed under Apache-2.0; see `LICENSE`.

KittenTTS 2 model weights are not vendored in this repository. They are downloaded
from `KittenML/kitten-tts-2` and remain under the Stellon Labs Community License.
Review that license before redistributing the weights.
