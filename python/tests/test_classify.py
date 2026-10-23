from dataclasses import replace
from pathlib import Path

import pytest

from tts_service.config import load_config
from tts_service.text import Reason, classify


@pytest.fixture
def cfg(tmp_path: Path):
    return load_config(tmp_path / "missing.json")


def words(n: int) -> str:
    return " ".join(["word"] * n)


def test_two_headings_is_document_like(cfg) -> None:
    result = classify("# A\n\n# B\n\nshort", turn_has_markdown_file=False, config=cfg)
    assert result.document_like is True
    assert result.reason == Reason.MARKDOWN


def test_one_heading_word_boundary(cfg) -> None:
    assert classify("# A\n\n" + words(400), turn_has_markdown_file=False, config=cfg).document_like is True
    assert classify("# A\n\n" + words(399), turn_has_markdown_file=False, config=cfg).document_like is False


def test_table_row_boundary(cfg) -> None:
    six = "\n".join(["| a | b |", "|---|---|"] + [f"| {i} | x |" for i in range(4)])
    five = "\n".join(["| a | b |", "|---|---|"] + [f"| {i} | x |" for i in range(3)])
    assert classify(six, turn_has_markdown_file=False, config=cfg).document_like is True
    assert classify(five, turn_has_markdown_file=False, config=cfg).document_like is False


def test_markdown_file_word_boundary(cfg) -> None:
    assert classify(words(201), turn_has_markdown_file=True, config=cfg).document_like is True
    assert classify(words(200), turn_has_markdown_file=True, config=cfg).document_like is False


def test_long_boundary(cfg) -> None:
    assert classify(words(1501), turn_has_markdown_file=False, config=cfg).reason == Reason.LONG
    assert classify(words(1500), turn_has_markdown_file=False, config=cfg).reason is None


def test_markdown_takes_precedence_over_long(cfg) -> None:
    result = classify("# A\n\n# B\n\n" + words(2000), turn_has_markdown_file=False, config=cfg)
    assert result.reason == Reason.MARKDOWN


def test_code_is_not_counted(cfg) -> None:
    raw = "Short answer.\n```\n" + words(5000) + "\n```"
    result = classify(raw, turn_has_markdown_file=False, config=cfg)
    assert result.words == 2
    assert result.document_like is False
    assert result.too_long is False


def test_announce_code_is_forwarded(cfg) -> None:
    cfg = replace(cfg, announce_code=True)
    result = classify(
        "Before.\n```\ncode\n```\nAfter.",
        turn_has_markdown_file=False,
        config=cfg,
    )
    assert "Code block omitted." in result.filtered
