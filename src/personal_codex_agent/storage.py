from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class ChatMetadata:
    chat_id: int
    mode: str = "default"
    codex_thread_id: str | None = None
    last_user_message_id: int | None = None
    last_response_chars: int | None = None


class SQLiteStorage:
    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chats (
                    chat_id INTEGER PRIMARY KEY,
                    mode TEXT NOT NULL DEFAULT 'default',
                    codex_thread_id TEXT,
                    last_user_message_id INTEGER,
                    last_response_chars INTEGER,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    telegram_message_id INTEGER,
                    direction TEXT NOT NULL CHECK(direction IN ('in', 'out')),
                    text_chars INTEGER NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def upsert_chat(self, metadata: ChatMetadata) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO chats (
                    chat_id, mode, codex_thread_id, last_user_message_id, last_response_chars, updated_at
                ) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(chat_id) DO UPDATE SET
                    mode = excluded.mode,
                    codex_thread_id = excluded.codex_thread_id,
                    last_user_message_id = excluded.last_user_message_id,
                    last_response_chars = excluded.last_response_chars,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    metadata.chat_id,
                    metadata.mode,
                    metadata.codex_thread_id,
                    metadata.last_user_message_id,
                    metadata.last_response_chars,
                ),
            )

    def get_chat(self, chat_id: int) -> ChatMetadata | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT chat_id, mode, codex_thread_id, last_user_message_id, last_response_chars
                FROM chats
                WHERE chat_id = ?
                """,
                (chat_id,),
            ).fetchone()
        if row is None:
            return None
        return ChatMetadata(
            chat_id=int(row["chat_id"]),
            mode=str(row["mode"]),
            codex_thread_id=row["codex_thread_id"],
            last_user_message_id=row["last_user_message_id"],
            last_response_chars=row["last_response_chars"],
        )

    def reset_chat(self, chat_id: int) -> None:
        existing = self.get_chat(chat_id)
        self.upsert_chat(ChatMetadata(chat_id=chat_id, mode=existing.mode if existing else "default"))

    def set_mode(self, chat_id: int, mode: str) -> None:
        existing = self.get_chat(chat_id)
        self.upsert_chat(
            ChatMetadata(
                chat_id=chat_id,
                mode=mode,
                codex_thread_id=existing.codex_thread_id if existing else None,
                last_user_message_id=existing.last_user_message_id if existing else None,
                last_response_chars=existing.last_response_chars if existing else None,
            )
        )

    def record_message(
        self,
        chat_id: int,
        telegram_message_id: int | None,
        direction: Literal["in", "out"],
        text_chars: int,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO messages (chat_id, telegram_message_id, direction, text_chars)
                VALUES (?, ?, ?, ?)
                """,
                (chat_id, telegram_message_id, direction, text_chars),
            )

    def list_recent_messages(self, chat_id: int, limit: int = 10) -> list[dict[str, int | str | None]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT telegram_message_id, direction, text_chars
                FROM messages
                WHERE chat_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (chat_id, limit),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn
