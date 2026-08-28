"""Session management for isolating conversation contexts across users and channels."""

import asyncio
import inspect
from collections.abc import Callable
from typing import Any

from agent_framework.memory.base import ConversationMemory
from agent_framework.memory.in_memory import InMemoryConversationMemory

MemoryFactory = Callable[..., ConversationMemory]


class SessionManager:
    """Manages isolated conversation memories indexed by unique session keys.

    Examples of session keys:
        - cli:default
        - discord:guild:123:user:456
        - discord:thread:789
        - telegram:chat:1001:user:2002

    The memory_factory may accept zero arguments or a single ``session_id`` positional
    argument — this lets persistent backends namespace rows by session while keeping
    the in-memory factory concise.
    """

    def __init__(
        self,
        memory_factory: MemoryFactory | None = None,
    ) -> None:
        self._memory_factory: MemoryFactory = memory_factory or (
            lambda: InMemoryConversationMemory()
        )
        self._factory_accepts_session_id = self._factory_takes_session_id(self._memory_factory)
        self._sessions: dict[str, ConversationMemory] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def _factory_takes_session_id(factory: MemoryFactory) -> bool:
        try:
            sig = inspect.signature(factory)
        except (TypeError, ValueError):
            return False
        positional = [
            p
            for p in sig.parameters.values()
            if p.kind
            in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            )
        ]
        required = [p for p in positional if p.default is inspect.Parameter.empty]
        return bool(required) or any(
            p.kind == inspect.Parameter.VAR_POSITIONAL for p in sig.parameters.values()
        )

    def _instantiate(self, session_id: str) -> ConversationMemory:
        args: tuple[Any, ...] = (session_id,) if self._factory_accepts_session_id else ()
        return self._memory_factory(*args)

    async def get_or_create_memory(self, session_id: str) -> ConversationMemory:
        """Retrieve the ConversationMemory for a session, creating a new one if it does not exist."""
        async with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = self._instantiate(session_id)
            return self._sessions[session_id]

    async def get_memory(self, session_id: str) -> ConversationMemory:
        """Alias for get_or_create_memory."""
        return await self.get_or_create_memory(session_id)

    async def has_session(self, session_id: str) -> bool:
        """Check whether a session currently exists in the manager."""
        async with self._lock:
            return session_id in self._sessions

    async def list_sessions(self) -> list[str]:
        """List all currently active session IDs."""
        async with self._lock:
            return list(self._sessions.keys())

    async def clear_session(self, session_id: str) -> None:
        """Clear message contents of a specific session without removing the session entry."""
        async with self._lock:
            memory = self._sessions.get(session_id)
        if memory is not None:
            await memory.clear()

    async def delete_session(self, session_id: str) -> bool:
        """Delete a session entirely from the manager."""
        async with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                return True
            return False

    async def clear_all_sessions(self) -> None:
        """Delete all managed sessions."""
        async with self._lock:
            self._sessions.clear()
