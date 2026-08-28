"""Unit tests for InMemoryConversationMemory."""

import pytest

from agent_framework.memory.in_memory import InMemoryConversationMemory
from agent_framework.models.message import Message


@pytest.mark.asyncio
async def test_in_memory_add_and_get() -> None:
    """Test appending messages and retrieving them in order."""
    memory = InMemoryConversationMemory()
    assert await memory.count() == 0
    assert await memory.get_last_message() is None

    msg1 = Message.user("First message")
    msg2 = Message.assistant("First response")
    await memory.add(msg1)
    await memory.add(msg2)

    assert await memory.count() == 2
    messages = await memory.get_messages()
    assert len(messages) == 2
    assert messages[0].content == "First message"
    assert messages[1].content == "First response"

    last_msg = await memory.get_last_message()
    assert last_msg is not None
    assert last_msg.content == "First response"


@pytest.mark.asyncio
async def test_in_memory_limit() -> None:
    """Test retrieving messages with limit parameter."""
    memory = InMemoryConversationMemory()
    for i in range(5):
        await memory.add(Message.user(f"Message {i}"))

    assert await memory.count() == 5
    recent_two = await memory.get_messages(limit=2)
    assert len(recent_two) == 2
    assert recent_two[0].content == "Message 3"
    assert recent_two[1].content == "Message 4"


@pytest.mark.asyncio
async def test_in_memory_clear() -> None:
    """Test clearing all messages from memory."""
    memory = InMemoryConversationMemory()
    await memory.add(Message.user("Hello"))
    await memory.clear()

    assert await memory.count() == 0
    assert len(await memory.get_messages()) == 0
    assert await memory.get_last_message() is None


@pytest.mark.asyncio
async def test_in_memory_max_messages_trimming() -> None:
    """Test that max_messages trims older messages properly."""
    memory = InMemoryConversationMemory(max_messages=3)
    for i in range(5):
        await memory.add(Message.user(f"Message {i}"))

    assert await memory.count() == 3
    messages = await memory.get_messages()
    assert [m.content for m in messages] == ["Message 2", "Message 3", "Message 4"]
