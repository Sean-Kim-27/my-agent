from __future__ import annotations

from pathlib import Path

from personal_codex_agent.storage import ChatMetadata, SQLiteStorage


def test_sqlite_storage_saves_and_loads_chat_metadata(tmp_path: Path) -> None:
    storage = SQLiteStorage(tmp_path / "agent.sqlite3")
    storage.initialize()

    storage.upsert_chat(
        ChatMetadata(
            chat_id=123,
            mode="dev",
            codex_thread_id="thread-abc",
            last_user_message_id=77,
            last_response_chars=42,
        )
    )

    loaded = storage.get_chat(123)
    assert loaded == ChatMetadata(
        chat_id=123,
        mode="dev",
        codex_thread_id="thread-abc",
        last_user_message_id=77,
        last_response_chars=42,
    )


def test_sqlite_storage_reset_chat_clears_thread_but_keeps_mode(tmp_path: Path) -> None:
    storage = SQLiteStorage(tmp_path / "agent.sqlite3")
    storage.initialize()
    storage.upsert_chat(ChatMetadata(chat_id=123, mode="research", codex_thread_id="thread-abc"))

    storage.reset_chat(123)

    assert storage.get_chat(123) == ChatMetadata(chat_id=123, mode="research")


def test_sqlite_storage_records_message_metadata(tmp_path: Path) -> None:
    storage = SQLiteStorage(tmp_path / "agent.sqlite3")
    storage.initialize()

    storage.record_message(chat_id=123, telegram_message_id=50, direction="in", text_chars=5)
    storage.record_message(chat_id=123, telegram_message_id=51, direction="out", text_chars=10)

    assert storage.list_recent_messages(123, limit=2) == [
        {"telegram_message_id": 50, "direction": "in", "text_chars": 5},
        {"telegram_message_id": 51, "direction": "out", "text_chars": 10},
    ]
