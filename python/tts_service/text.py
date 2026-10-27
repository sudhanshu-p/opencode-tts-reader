"""Filter Markdown and other noise out of assistant text before speech."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from .config import Config
from .currency import normalize_currency

_FENCED_BLOCK = re.compile(
    r"^[ \t]*(?P<quote>(?:>[ \t]?)*)[ \t]*(?P<fence>`{3,}|~{3,})[^\n]*\n"
    r".*?^[ \t]*(?P=quote)[ \t]*(?P=fence)[ \t]*$",
    re.MULTILINE | re.DOTALL,
)
_UNCLOSED_FENCE = re.compile(
    r"^[ \t]*(?:>[ \t]?)*[ \t]*(?:`{3,}|~{3,})[^\n]*(?:\n.*)?\Z",
    re.MULTILINE | re.DOTALL,
)
_TABLE_SEPARATOR = re.compile(r"^\s*\|?[\s:|-]+\|[\s:|-]*$")
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_HTML_TAG = re.compile(r"</?[A-Za-z][^>]*>")
_IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_INLINE_CODE = re.compile(r"(`+)(.+?)\1", re.DOTALL)
_LATEX_BLOCK = re.compile(r"\$\$.*?\$\$", re.DOTALL)
_LATEX_INLINE = re.compile(r"\$[^$\n]+\$")
_BARE_URL = re.compile(r"https?://[^\s<>\"'`]+")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_BACKTICKED_PATH = re.compile(r"`[^`\n]*[/\\][^`\n]*`")
_ABSOLUTE_PATH = re.compile(r"(?<![\w:/])~?/[^\s\"'`<>()\[\],;]+")
_FILENAME = re.compile(
    r"(?<![\w/.-])[\w.-]+\.(?:md|mdx|py|ts|tsx|js|json|toml|yaml|yml|sh|txt)\b"
)
_HEADING = re.compile(r"^[ \t]{0,3}#{1,6}[ \t]+", re.MULTILINE)
_BLOCKQUOTE = re.compile(r"^[ \t]*(?:>[ \t]?)+", re.MULTILINE)
_LIST_MARKER = re.compile(r"^[ \t]*(?:[-*+]|\d+[.)])[ \t]+", re.MULTILINE)
_TASK_CHECKBOX = re.compile(r"^[ \t]*\[[ xX]\][ \t]+", re.MULTILINE)
_HORIZONTAL_RULE = re.compile(r"^[ \t]*(?:[-*_][ \t]*){3,}$", re.MULTILINE)
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_UNDERSCORE_BOLD = re.compile(r"__(.+?)__")
_STRIKE = re.compile(r"~~(.+?)~~")
_ITALIC = re.compile(r"\*(.+?)\*")
_UNDERSCORE_ITALIC = re.compile(r"_(.+?)_")
_EMOJI = re.compile(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]")
_SPACES = re.compile(r"[ \t]+")
_NEWLINES = re.compile(r"\n{3,}")
_HEADING_LINE = re.compile(r"^\s{0,3}#{1,6}\s+\S", re.MULTILINE)


class Reason(str, Enum):
    """Why a reply was classified as requiring review before speech."""

    MARKDOWN = "markdown"
    LONG = "long"


@dataclass(frozen=True)
class Classification:
    """Speech filtering and hold decision for one assistant reply."""

    filtered: str
    words: int
    headings: int
    table_rows: int
    document_like: bool
    too_long: bool
    reason: Reason | None


def _append_table_run(run: list[str], blocks: list[list[str]]) -> None:
    if len(run) >= 2 and any(
        _TABLE_SEPARATOR.match(_BLOCKQUOTE.sub("", line)) for line in run
    ):
        blocks.append(run)


def find_table_blocks(raw: str) -> list[list[str]]:
    """Return contiguous pipe-bearing line runs that form Markdown tables."""
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    blocks: list[list[str]] = []
    run: list[str] = []
    for line in text.split("\n"):
        if "|" in line:
            run.append(line)
            continue
        _append_table_run(run, blocks)
        run = []
    _append_table_run(run, blocks)
    return blocks


def _remove_tables(text: str) -> str:
    for block in find_table_blocks(text):
        text = text.replace("\n".join(block), "\n\n", 1)
    return text


def _replace_path(match: re.Match[str]) -> str:
    value = match.group(0)
    trailing = ""
    while value and value[-1] in ".,;:!?":
        trailing = value[-1] + trailing
        value = value[:-1]
    if not value:
        return match.group(0)
    return f" a file {trailing}"


def _tidy(text: str) -> str:
    text = _SPACES.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = _NEWLINES.sub("\n\n", text)
    return text.strip()


def filter_for_speech(raw: str, *, announce_code: bool = False) -> str:
    """Return ``raw`` stripped of anything that should not be spoken."""
    text = raw.replace("\r\n", "\n").replace("\r", "\n")

    notice = "\n\nCode block omitted.\n\n" if announce_code else "\n\n"
    text = _FENCED_BLOCK.sub(notice, text)
    text = _UNCLOSED_FENCE.sub(notice, text)

    text = _remove_tables(text)
    text = _HTML_COMMENT.sub(" ", text)
    text = _HTML_TAG.sub(" ", text)
    text = _IMAGE.sub(lambda match: match.group(1), text)
    text = _LINK.sub(lambda match: match.group(1), text)
    text = _INLINE_CODE.sub(" ", text)
    text = normalize_currency(text)
    text = _LATEX_BLOCK.sub("", text)
    text = _LATEX_INLINE.sub("", text)
    text = _BARE_URL.sub(" ", text)
    text = _EMAIL.sub(" ", text)
    text = _BACKTICKED_PATH.sub(" ", text)
    text = _ABSOLUTE_PATH.sub(_replace_path, text)
    text = _FILENAME.sub("a file", text)

    text = _HEADING.sub("", text)
    text = _BLOCKQUOTE.sub("", text)
    text = _LIST_MARKER.sub("", text)
    text = _TASK_CHECKBOX.sub("", text)
    text = _HORIZONTAL_RULE.sub("", text)

    text = _BOLD.sub(r"\1", text)
    text = _UNDERSCORE_BOLD.sub(r"\1", text)
    text = _STRIKE.sub(r"\1", text)
    text = _ITALIC.sub(r"\1", text)
    text = _UNDERSCORE_ITALIC.sub(r"\1", text)
    text = _EMOJI.sub("", text)

    return _tidy(text)


def count_words(text: str) -> int:
    """Return the number of whitespace-separated words in ``text``."""
    return len(text.split())


def count_headings(raw: str) -> int:
    """Return the number of Markdown heading lines in ``raw``."""
    return len(_HEADING_LINE.findall(raw))


def count_table_rows(raw: str) -> int:
    """Return the number of Markdown table lines in ``raw``, headers included."""
    return sum(len(block) for block in find_table_blocks(raw))


def classify(
    raw: str, *, turn_has_markdown_file: bool, config: Config
) -> Classification:
    """Filter ``raw`` and decide whether it should be read automatically."""
    filtered = filter_for_speech(raw, announce_code=config.announce_code)
    words = count_words(filtered)
    headings = count_headings(raw)
    table_rows = count_table_rows(raw)

    document_like = (
        headings >= config.document_headings
        or (headings >= 1 and words > config.document_words)
        or table_rows >= 6
        or (turn_has_markdown_file and words > config.markdown_file_words)
    )
    too_long = words > config.max_words
    if document_like:
        reason: Reason | None = Reason.MARKDOWN
    elif too_long:
        reason = Reason.LONG
    else:
        reason = None

    return Classification(
        filtered=filtered,
        words=words,
        headings=headings,
        table_rows=table_rows,
        document_like=document_like,
        too_long=too_long,
        reason=reason,
    )
