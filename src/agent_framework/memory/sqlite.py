"""SQLite-backed persistent implementation of ConversationMemory.

Uses the stdlib ``sqlite3`` module wrapped in ``asyncio.to_thread`` so blocking
I/O never freezes the event loop. All rows are namespaced by ``session_id``
which lets a single database file back many concurrent conversations.
"""

from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any

from agent_framework.memory.base import ConversationMemory
from agent_framework.models.message import Message

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS conversation_messages (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   TEXT    NOT NULL,
    payload_json TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_conversation_messages_session
    ON conversation_messages(session_id, id);
"""


class SQLiteConversationMemory(ConversationMemory):
    """Persistent conversation memory backed by SQLite.

    A single database file may back many sessions — each row is tagged with a
    session_id and messages are always filtered/ordered by that key.
    """

    def __init__(
        self,
        session_id: str,
        db_path: str | Path,
        max_messages: int | None = None,
    ) -> None:
        self._session_id = session_id
        self._db_path = str(db_path)
        self._max_messages = max_messages
        self._lock = asyncio.Lock()
        self._initialized = False

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, isolation_level=None)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _ensure_schema_sync(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA_SQL)

    async def _ensure_schema(self) -> None:
        if self._initialized:
            return
        await asyncio.to_thread(self._ensure_schema_sync)
        self._initialized = True

    def _insert_sync(self, payload: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO conversation_messages(session_id, payload_json) VALUES (?, ?)",
                (self._session_id, payload),
            )
            if self._max_messages is not None:
                conn.execute(
                    """
                    DELETE FROM conversation_messages
                    WHERE session_id = ?
                      AND id NOT IN (
                          SELECT id FROM conversation_messages
                          WHERE session_id = ?
                          ORDER BY id DESC
                          LIMIT ?
                      )
                    """,
                    (self._session_id, self._session_id, self._max_messages),
                )

    def _select_sync(self, limit: int | None) -> list[str]:
        with self._connect() as conn:
            if limit is None or limit <= 0:
                rows = conn.execute(
                    "SELECT payload_json FROM conversation_messages "
                    "WHERE session_id = ? ORDER BY id ASC",
                    (self._session_id,),
                ).fetchall()
                return [r[0] for r in rows]
            rows = conn.execute(
                "SELECT payload_json FROM conversation_messages "
                "WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                (self._session_id, limit),
            ).fetchall()
            return [r[0] for r in reversed(rows)]

    def _last_sync(self) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM conversation_messages "
                "WHERE session_id = ? ORDER BY id DESC LIMIT 1",
                (self._session_id,),
            ).fetchone()
        return row[0] if row else None

    def _count_sync(self) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM conversation_messages WHERE session_id = ?",
                (self._session_id,),
            ).fetchone()
        return int(row[0]) if row else 0

    def _clear_sync(self) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM conversation_messages WHERE session_id = ?",
                (self._session_id,),
            )

    async def add(self, message: Message) -> None:
        await self._ensure_schema()
        payload = message.model_dump_json()
        async with self._lock:
            await asyncio.to_thread(self._insert_sync, payload)

    async def get_messages(self, limit: int | None = None) -> list[Message]:
        await self._ensure_schema()
        async with self._lock:
            payloads = await asyncio.to_thread(self._select_sync, limit)
        return [Message.model_validate_json(p) for p in payloads]

    async def get_last_message(self) -> Message | None:
        await self._ensure_schema()
        async with self._lock:
            payload = await asyncio.to_thread(self._last_sync)
        return Message.model_validate_json(payload) if payload else None

    async def count(self) -> int:
        await self._ensure_schema()
        async with self._lock:
            return await asyncio.to_thread(self._count_sync)

    async def clear(self) -> None:
        await self._ensure_schema()
        async with self._lock:
            await asyncio.to_thread(self._clear_sync)


def sqlite_memory_factory(
    db_path: str | Path,
    max_messages: int | None = None,
) -> Callable[[str], SQLiteConversationMemory]:
    """Return a factory suitable for ``SessionManager(memory_factory=...)``."""

    def _factory(session_id: str) -> SQLiteConversationMemory:
        return SQLiteConversationMemory(
            session_id=session_id,
            db_path=db_path,
            max_messages=max_messages,
        )

    return _factory


__all__ = ["SQLiteConversationMemory", "sqlite_memory_factory"]


# Silence unused-import warnings for BaseException hints referenced in docstrings.
_ = Any
