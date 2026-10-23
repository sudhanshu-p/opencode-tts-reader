"""Local configuration for the OpenCode TTS reader."""

import json
import os
import tempfile
from dataclasses import dataclass, field, fields
from pathlib import Path


def _xdg_base(env_var: str, fallback: tuple[str, ...]) -> Path:
    value = os.environ.get(env_var)
    if value:
        return Path(value)
    return Path.home().joinpath(*fallback)


def default_model_cache_dir() -> Path:
    """Return the directory used to cache downloaded models."""
    return _xdg_base("XDG_CACHE_HOME", (".cache",)) / "opencode-tts" / "models"


def default_data_dir() -> Path:
    """Return the directory used for generated reader data."""
    return _xdg_base("XDG_DATA_HOME", (".local", "share")) / "opencode-tts"


@dataclass(frozen=True)
class Config:
    host: str = "127.0.0.1"
    port: int = 8765
    model: str = "KittenML/kitten-tts-2"
    backend: str = "mlx"
    weights: str = "packed"
    device: str = "mps"
    voice: str = "Bella"
    auto_read: bool = True
    muted: bool = False
    include_subagents: bool = False
    max_words: int = 1500
    document_headings: int = 2
    document_words: int = 400
    markdown_file_words: int = 200
    announce_code: bool = False
    announce_skipped: bool = False
    ask_markdown: str = "toast"  # toast | dialog | none
    max_queue: int = 100
    chunk_max_chars: int = 260
    message_dedupe_ttl_s: int = 3600
    text_dedupe_ttl_s: int = 300
    model_cache_dir: Path = field(default_factory=default_model_cache_dir)
    data_dir: Path = field(default_factory=default_data_dir)
    log_level: str = "info"

    def validate(self) -> None:
        """Raise ``ValueError`` when any field holds an unsupported value."""
        if self.host != "127.0.0.1":
            raise ValueError(f"host must be 127.0.0.1, got {self.host!r}")
        if not 1 <= self.port <= 65535:
            raise ValueError(f"port must be between 1 and 65535, got {self.port!r}")
        if self.backend not in ("mlx", "cpu", "auto"):
            raise ValueError(f"backend must be mlx, cpu, or auto, got {self.backend!r}")
        if self.weights not in ("packed", "emb4"):
            raise ValueError(f"weights must be packed or emb4, got {self.weights!r}")
        if self.backend == "mlx" and self.weights == "emb4":
            raise ValueError("emb4 weights are not supported by the mlx backend")
        if not self.voice.strip():
            raise ValueError("voice must not be empty")
        if self.ask_markdown not in ("toast", "dialog", "none"):
            raise ValueError(
                f"ask_markdown must be toast, dialog, or none, got {self.ask_markdown!r}"
            )
        for name in (
            "max_words",
            "document_headings",
            "document_words",
            "markdown_file_words",
            "max_queue",
            "chunk_max_chars",
            "message_dedupe_ttl_s",
            "text_dedupe_ttl_s",
        ):
            value = getattr(self, name)
            if value <= 0:
                raise ValueError(f"{name} must be positive, got {value!r}")


_FIELD_NAMES = frozenset(f.name for f in fields(Config))
_PATH_FIELD_NAMES = frozenset(f.name for f in fields(Config) if f.type is Path)


def config_path() -> Path:
    """Return the location of the reader configuration file."""
    return _xdg_base("XDG_CONFIG_HOME", (".config",)) / "opencode" / "tts-reader.json"


def load_config(path: Path | None = None) -> Config:
    """Load configuration, merging a partial JSON file over the defaults."""
    target = config_path() if path is None else path
    data: dict[str, object] = {}
    if target.exists():
        loaded = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError(f"configuration must be a JSON object: {target}")
        data = loaded
    values = {key: value for key, value in data.items() if key in _FIELD_NAMES}
    for name in _PATH_FIELD_NAMES & values.keys():
        values[name] = Path(str(values[name]))
    config = Config(**values)
    config.validate()
    return config


def save_config(config: Config, path: Path | None = None) -> None:
    """Write configuration atomically to ``path``."""
    target = config_path() if path is None else path
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {}
    for f in fields(Config):
        value = getattr(config, f.name)
        payload[f.name] = str(value) if f.type is Path else value
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
        os.replace(tmp_name, target)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise
