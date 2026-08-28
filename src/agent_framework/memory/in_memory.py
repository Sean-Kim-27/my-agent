"""In-memory implementation of ConversationMemory."""

import asyncio

from agent_framework.memory.base import ConversationMemory
from agent_framework.models.message import Message


class InMemoryConversationMemory(ConversationMemory):
    """Thread-safe and async-safe in-memory message storage."""

    def __init__(self, max_messages: int | None = None) -> None:
        self._messages: list[Message] = []
        self._max_messages = max_messages
        self._lock = asyncio.Lock()

    async def add(self, message: Message) -> None:
        """Add a message to the memory store."""
        async with self._lock:
            self._messages.append(message)
            if self._max_messages is not None and len(self._messages) > self._max_messages:
                # Trim oldest messages while preserving capacity
                self._messages = self._messages[-self._max_messages:]

    async def get_messages(self, limit: int | None = None) -> list[Message]:
        """Retrieve stored messages in chronological order."""
        async with self._lock:
            if limit is not None and limit > 0:
                return list(self._messages[-limit:])
            return list(self._messages)

    async def clear(self) -> None:
        """Clear all messages from memory."""
        async with self._lock:
            self._messages.clear()

    async def get_last_message(self) -> Message | None:
        """Retrieve the most recent message, or None if empty."""
        async with self._lock:
            if self._messages:
                return self._messages[-1]
            return None

    async def count(self) -> int:
        """Count total messages currently in memory."""
        async with self._lock:
            return len(self._messages)
