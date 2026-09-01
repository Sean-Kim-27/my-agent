"""SQLite-backed persistent implementation of ConversationMemory.

Uses the stdlib ``sqlite3`` module wrapped in ``asyncio.to_thread`` so blocking
I/O never freezes the event loop. All rows are namespaced by ``session_id``
which lets a single database file back many concurrent conversations.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path

from agent_framework.memory.base import ConversationMemory
from agent_framework.memory.sqlite_store import SQLiteSessionStore
from agent_framework.models.message import Message


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
        self._store = SQLiteSessionStore(self._db_path)

    def _ensure_schema_sync(self) -> None:
        self._store.ensure_schema()

    async def _ensure_schema(self) -> None:
        if self._initialized:
            return
        await asyncio.to_thread(self._ensure_schema_sync)
        self._initialized = True

    async def add(self, message: Message) -> None:
        await self.add_many([message])

    async def add_many(self, messages: list[Message]) -> None:
        await self._ensure_schema()
        async with self._lock:
            await asyncio.to_thread(
                self._store.append_messages,
                self._session_id,
                messages,
                max_messages=self._max_messages,
            )

    async def get_messages(self, limit: int | None = None) -> list[Message]:
        await self._ensure_schema()
        async with self._lock:
            return await asyncio.to_thread(self._store.messages, self._session_id, limit)

    async def get_last_message(self) -> Message | None:
        await self._ensure_schema()
        async with self._lock:
            messages = await asyncio.to_thread(self._store.messages, self._session_id, 1)
        return messages[-1] if messages else None

    async def count(self) -> int:
        await self._ensure_schema()
        async with self._lock:
            messages = await asyncio.to_thread(self._store.messages, self._session_id)
        return len(messages)

    async def clear(self) -> None:
        await self._ensure_schema()
        async with self._lock:
            await asyncio.to_thread(self._store.clear, self._session_id)


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
