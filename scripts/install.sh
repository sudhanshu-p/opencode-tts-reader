#!/usr/bin/env bash
set -euo pipefail

DRY_RUN=0
SKIP_WARMUP=0

usage() {
  cat <<'EOF'
Usage: scripts/install.sh [--dry-run] [--skip-warmup]

Install the local OpenCode TTS reader for the current user:
  - sync the Python environment
  - warm the KittenTTS model unless --skip-warmup
  - install Bun dependencies
  - link the plugin and CLI into ~/.config and ~/.local/bin
  - create ~/.config/opencode/tts-reader.json on first install

--dry-run      print every planned action without changing the system
--skip-warmup  do not download/load the model during installation
EOF
}

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --skip-warmup) SKIP_WARMUP=1 ;;
    -h|--help) usage; exit 0 ;;
    *)
      echo "unknown option: $arg" >&2
      usage >&2
      exit 2
      ;;
  esac
done

say() {
  printf '%s\n' "$*"
}

run() {
  if [ "$DRY_RUN" -eq 1 ]; then
    say "DRY: $*"
  else
    "$@"
  fi
}

run_in_root() {
  if [ "$DRY_RUN" -eq 1 ]; then
    say "DRY: (cd $ROOT && $*)"
  else
    (cd "$ROOT" && "$@")
  fi
}

require_tool() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "missing required tool: $1" >&2
    exit 1
  fi
}

if [ "$(uname -s)" != "Darwin" ] || [ "$(uname -m)" != "arm64" ]; then
  echo "the reader requires macOS on Apple Silicon (Darwin arm64)" >&2
  exit 1
fi

for tool in uv bun afplay opencode; do
  require_tool "$tool"
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
CONFIG="$HOME/.config/opencode/tts-reader.json"
PLUGIN="$HOME/.config/opencode/plugins/opencode-tts"
BIN="$HOME/.local/bin/opencode-tts"
ENTRY="$ROOT/python/.venv/bin/opencode-tts"

for entrypoint in "$ROOT/index.ts" "$ROOT/tui.ts"; do
  if [ ! -f "$entrypoint" ]; then
    echo "missing local plugin entrypoint: $entrypoint" >&2
    exit 1
  fi
done

say "OpenCode TTS reader installer"
say "Repository: $ROOT"
say "Mode: $([ "$DRY_RUN" -eq 1 ] && echo 'dry run (no changes)' || echo 'install')"

run uv sync --project "$ROOT/python"

if [ "$SKIP_WARMUP" -eq 0 ]; then
  run uv run --project "$ROOT/python" python -m tts_service.warmup
else
  say "Skipping model warmup (--skip-warmup)."
fi

run_in_root bun install
run chmod +x "$ROOT/scripts/opencode-tts"
run mkdir -p "$HOME/.config/opencode/plugins" "$HOME/.local/bin"
run ln -sfn "$ROOT" "$PLUGIN"
run ln -sfn "$ENTRY" "$BIN"

if [ -f "$CONFIG" ]; then
  say "Keeping existing config: $CONFIG"
else
  if [ "$DRY_RUN" -eq 1 ]; then
    say "DRY: create $CONFIG from defaults"
  else
    "$ROOT/python/.venv/bin/python" -c \
      'from tts_service.config import config_path, load_config, save_config; save_config(load_config(), config_path())'
  fi
fi

say ""
say "Next steps:"
say "  1. Restart OpenCode so it discovers the local plugin."
say "  2. Confirm the reader loads (TUI toast or server log). 'opencode plugin list' may omit local plugins."
say "  3. Run: opencode-tts status"
say "  4. Make sure ~/.local/bin is on PATH, or run $ENTRY directly."
if [ "$DRY_RUN" -eq 1 ]; then
  say ""
  say "Dry run complete; no files, links, services, or packages were changed."
fi
