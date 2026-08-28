"""Unit tests for SessionManager and multi-session isolation."""

import pytest

from agent_framework.memory.session import SessionManager
from agent_framework.models.message import Message


@pytest.mark.asyncio
async def test_session_isolation() -> None:
    """Test that two separate sessions do not leak messages into each other."""
    manager = SessionManager()

    mem_user_a = await manager.get_memory("discord:user:100")
    mem_user_b = await manager.get_memory("discord:user:200")

    await mem_user_a.add(Message.user("Hello from User A"))
    await mem_user_b.add(Message.user("Hello from User B"))

    msgs_a = await mem_user_a.get_messages()
    msgs_b = await mem_user_b.get_messages()

    assert len(msgs_a) == 1
    assert msgs_a[0].content == "Hello from User A"

    assert len(msgs_b) == 1
    assert msgs_b[0].content == "Hello from User B"


@pytest.mark.asyncio
async def test_session_manager_lifecycle() -> None:
    """Test session discovery, deletion, and clearing operations."""
    manager = SessionManager()

    session_cli = "cli:default"
    session_tg = "telegram:chat:555"

    assert await manager.has_session(session_cli) is False

    mem_cli = await manager.get_memory(session_cli)
    await mem_cli.add(Message.user("CLI ping"))

    assert await manager.has_session(session_cli) is True
    assert set(await manager.list_sessions()) == {session_cli}

    # Add second session
    mem_tg = await manager.get_memory(session_tg)
    await mem_tg.add(Message.user("TG ping"))
    assert set(await manager.list_sessions()) == {session_cli, session_tg}

    # Clear first session content
    await manager.clear_session(session_cli)
    assert await mem_cli.count() == 0
    assert await manager.has_session(session_cli) is True

    # Delete session
    deleted = await manager.delete_session(session_cli)
    assert deleted is True
    assert await manager.has_session(session_cli) is False
    assert set(await manager.list_sessions()) == {session_tg}

    # Clear all
    await manager.clear_all_sessions()
    assert len(await manager.list_sessions()) == 0
