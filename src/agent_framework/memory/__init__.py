"""Conversation memory and session management module."""

from agent_framework.memory.base import ConversationMemory
from agent_framework.memory.context import (
    ContextManager,
    SummarizingContextManager,
    TokenCounter,
    TokenTrimmingContextManager,
    approximate_token_count,
)
from agent_framework.memory.in_memory import InMemoryConversationMemory
from agent_framework.memory.session import SessionManager
from agent_framework.memory.sqlite import SQLiteConversationMemory, sqlite_memory_factory
from agent_framework.memory.sqlite_store import (
    SQLITE_SCHEMA_VERSION,
    SessionSearchHit,
    SessionSummary,
    SQLiteSessionStore,
)

__all__ = [
    "SQLITE_SCHEMA_VERSION",
    "ContextManager",
    "ConversationMemory",
    "InMemoryConversationMemory",
    "SQLiteConversationMemory",
    "SQLiteSessionStore",
    "SessionManager",
    "SessionSearchHit",
    "SessionSummary",
    "SummarizingContextManager",
    "TokenCounter",
    "TokenTrimmingContextManager",
    "approximate_token_count",
    "sqlite_memory_factory",
]
