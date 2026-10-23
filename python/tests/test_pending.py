from pathlib import Path

from tts_service.pending import PendingReply, PendingStore


def reply(session: str | None, message: str, created: float, reason: str = "markdown") -> PendingReply:
    return PendingReply(
        session_id=session,
        message_id=message,
        text=f"text-{message}",
        reason=reason,
        words=10,
        created_at=created,
    )


def test_put_replaces_same_session(tmp_path: Path) -> None:
    store = PendingStore(tmp_path / "pending.json")
    store.put(reply("s1", "m1", 1))
    store.put(reply("s1", "m2", 2))
    assert store.count() == 1
    assert store.get("s1").message_id == "m2"


def test_get_none_returns_latest_globally(tmp_path: Path) -> None:
    store = PendingStore(tmp_path / "pending.json")
    store.put(reply("s1", "m1", 1))
    store.put(reply("s2", "m2", 2))
    assert store.get(None).message_id == "m2"
    assert store.get("s1").message_id == "m1"


def test_pop_falls_back_to_latest(tmp_path: Path) -> None:
    store = PendingStore(tmp_path / "pending.json")
    store.put(reply("s1", "m1", 1))
    store.put(reply("s2", "m2", 2))
    assert store.pop("missing").message_id == "m2"
    assert store.count() == 1


def test_persists_across_instances(tmp_path: Path) -> None:
    path = tmp_path / "pending.json"
    PendingStore(path).put(reply("s1", "m1", 1))
    assert PendingStore(path).get("s1").message_id == "m1"


def test_corrupt_file_starts_empty(tmp_path: Path) -> None:
    path = tmp_path / "pending.json"
    path.write_text("{", encoding="utf-8")
    assert PendingStore(path).count() == 0


def test_list_is_sorted_by_created_at(tmp_path: Path) -> None:
    store = PendingStore(tmp_path / "pending.json")
    store.put(reply("s2", "m2", 20))
    store.put(reply("s1", "m1", 10))
    assert [item.message_id for item in store.list()] == ["m1", "m2"]
