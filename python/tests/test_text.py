from tts_service.text import count_words, filter_for_speech, find_table_blocks


def clean(raw: str) -> str:
    return " ".join(filter_for_speech(raw).split())


def test_fenced_code_is_removed() -> None:
    raw = "Before.\n```python\nprint('x')\n```\nAfter."
    assert clean(raw) == "Before. After."


def test_inline_code_does_not_merge_words() -> None:
    assert clean("Run `uv sync` before starting.") == "Run before starting."


def test_multi_backtick_inline_code_is_removed() -> None:
    assert clean("Run ``uv sync`` now.") == "Run now."


def test_diff_block_is_removed() -> None:
    raw = "Intro.\n```diff\n-old\n+new\n```\nOutro."
    assert clean(raw) == "Intro. Outro."


def test_table_is_removed() -> None:
    raw = "Intro.\n| a | b |\n|---|---|\n| 1 | 2 |\nOutro."
    assert clean(raw) == "Intro. Outro."
    assert len(find_table_blocks(raw)) == 1


def test_blockquoted_table_is_removed() -> None:
    raw = "> Intro.\n> | a | b |\n> |---|---|\n> | 1 | 2 |\nOutro."
    assert clean(raw) == "Intro. Outro."


def test_blockquoted_fenced_code_is_removed() -> None:
    raw = "> ```\n> print('secret')\n> ```\nAfter."
    out = clean(raw)
    assert out == "After."
    assert "secret" not in out


def test_blockquoted_unclosed_fence_is_removed() -> None:
    raw = "> ```python\n> print('secret')"
    out = clean(raw)
    assert out == ""
    assert "secret" not in out


def test_single_pipe_prose_is_kept() -> None:
    assert clean("Use a | b as a separator.") == "Use a | b as a separator."


def test_links_keep_anchor_text() -> None:
    assert clean("See [the docs](https://example.com).") == "See the docs."


def test_markdown_structure_is_stripped() -> None:
    raw = "# Title\n\n- one\n- two\n\n> quote"
    assert clean(raw) == "Title one two quote"


def test_urls_paths_latex_and_html_are_removed() -> None:
    raw = "Open https://example.com and /Users/a/PLAN.md; <b>bold</b> $x^2$."
    out = clean(raw)
    assert "https://" not in out
    assert "/Users" not in out
    assert "<b>" not in out
    assert "$" not in out


def test_code_only_becomes_empty() -> None:
    assert filter_for_speech("```\ncode\n```").strip() == ""


def test_unclosed_fence_is_removed() -> None:
    raw = "Before.\n```python\nprint('x')"
    assert clean(raw) == "Before."


def test_announce_code_inserts_notice() -> None:
    out = filter_for_speech("Before.\n```\ncode\n```", announce_code=True)
    assert "Code block omitted." in out


def test_emoji_is_removed() -> None:
    assert clean("Done 🚀") == "Done"


def test_count_words() -> None:
    assert count_words("one two three") == 3
    assert count_words("") == 0
