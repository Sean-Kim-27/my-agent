"""Conversation memory interface definition."""

from abc import ABC, abstractmethod

from agent_framework.models.message import Message


class ConversationMemory(ABC):
    """Abstract interface for storing and retrieving conversational context."""

    @abstractmethod
    async def add(self, message: Message) -> None:
        """Append a message to the conversation memory."""

    @abstractmethod
    async def get_messages(self, limit: int | None = None) -> list[Message]:
        """Retrieve stored messages in chronological order, optionally limited to the most recent N."""

    @abstractmethod
    async def clear(self) -> None:
        """Clear all messages in this conversation memory."""

    @abstractmethod
    async def get_last_message(self) -> Message | None:
        """Retrieve the most recent message, or None if empty."""

    @abstractmethod
    async def count(self) -> int:
        """Return total number of messages in memory."""
