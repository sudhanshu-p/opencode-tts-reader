from tts_service.dedupe import Deduper


def test_message_id_is_duplicate_within_ttl() -> None:
    d = Deduper(message_ttl_s=10, hash_ttl_s=5)
    assert d.seen_or_remember("m1", "h1", now=0) is False
    assert d.seen_or_remember("m1", "h2", now=1) is True
    assert d.seen_or_remember("m1", "h3", now=10) is False


def test_text_hash_is_duplicate_within_ttl() -> None:
    d = Deduper(message_ttl_s=10, hash_ttl_s=5)
    assert d.seen_or_remember(None, "h1", now=0) is False
    assert d.seen_or_remember("m2", "h1", now=1) is True
    assert d.seen_or_remember(None, "h1", now=5) is False


def test_none_message_id_only_uses_hash() -> None:
    d = Deduper()
    assert d.seen_or_remember(None, "h1", now=0) is False
    assert d.seen_or_remember(None, "h2", now=0) is False
    assert d.seen_or_remember(None, "h1", now=0) is True
