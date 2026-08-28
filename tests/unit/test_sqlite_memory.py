"""Tests for the SQLite persistent conversation memory backend."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_framework.memory.session import SessionManager
from agent_framework.memory.sqlite import (
    SQLiteConversationMemory,
    sqlite_memory_factory,
)
from agent_framework.models.message import Message, MessageRole


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "agent.db"


async def test_sqlite_memory_roundtrip(db_path: Path) -> None:
    memory = SQLiteConversationMemory(session_id="s1", db_path=db_path)
    await memory.add(Message.user("hi"))
    await memory.add(Message.assistant("hello"))

    messages = await memory.get_messages()
    assert [m.role for m in messages] == [MessageRole.USER, MessageRole.ASSISTANT]
    assert [m.content for m in messages] == ["hi", "hello"]
    assert await memory.count() == 2

    last = await memory.get_last_message()
    assert last is not None
    assert last.content == "hello"


async def test_sqlite_memory_survives_reopen(db_path: Path) -> None:
    memory = SQLiteConversationMemory(session_id="s1", db_path=db_path)
    await memory.add(Message.user("persisted"))

    reopened = SQLiteConversationMemory(session_id="s1", db_path=db_path)
    messages = await reopened.get_messages()
    assert [m.content for m in messages] == ["persisted"]


async def test_sqlite_memory_isolates_sessions(db_path: Path) -> None:
    a = SQLiteConversationMemory(session_id="alice", db_path=db_path)
    b = SQLiteConversationMemory(session_id="bob", db_path=db_path)

    await a.add(Message.user("alice-hi"))
    await b.add(Message.user("bob-hi"))

    a_msgs = await a.get_messages()
    b_msgs = await b.get_messages()
    assert [m.content for m in a_msgs] == ["alice-hi"]
    assert [m.content for m in b_msgs] == ["bob-hi"]


async def test_sqlite_memory_trims_to_max_messages(db_path: Path) -> None:
    memory = SQLiteConversationMemory(session_id="s1", db_path=db_path, max_messages=2)
    for i in range(4):
        await memory.add(Message.user(f"msg-{i}"))

    messages = await memory.get_messages()
    assert [m.content for m in messages] == ["msg-2", "msg-3"]
    assert await memory.count() == 2


async def test_sqlite_memory_clear(db_path: Path) -> None:
    memory = SQLiteConversationMemory(session_id="s1", db_path=db_path)
    await memory.add(Message.user("gone"))
    await memory.clear()
    assert await memory.count() == 0
    assert await memory.get_last_message() is None


async def test_session_manager_wires_sqlite_factory(db_path: Path) -> None:
    manager = SessionManager(memory_factory=sqlite_memory_factory(db_path))

    m1 = await manager.get_or_create_memory("chan:1")
    m2 = await manager.get_or_create_memory("chan:2")
    assert isinstance(m1, SQLiteConversationMemory)
    assert m1 is not m2

    await m1.add(Message.user("hello 1"))
    await m2.add(Message.user("hello 2"))
    assert (await m1.count()) == 1
    assert (await m2.count()) == 1

    # A fresh manager should see the persisted messages
    manager2 = SessionManager(memory_factory=sqlite_memory_factory(db_path))
    reloaded = await manager2.get_or_create_memory("chan:1")
    assert [m.content for m in await reloaded.get_messages()] == ["hello 1"]
