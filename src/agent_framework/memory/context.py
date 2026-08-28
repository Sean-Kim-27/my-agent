"""Context window management primitives.

This module provides the ``ContextManager`` interface used by the agent to
constrain conversation history to fit within a token budget before it is sent
to an LLM. The default ``TokenTrimmingContextManager`` drops the oldest
non-system messages first; more sophisticated implementations (e.g. rolling
summaries) may plug in later without changing the ``ConversationMemory``
storage layer.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import Protocol

from agent_framework.models.message import Message, MessageRole


class TokenCounter(Protocol):
    """Callable returning an estimated token count for a text string."""

    def __call__(self, text: str) -> int: ...


def approximate_token_count(text: str) -> int:
    """Cheap heuristic: ~4 characters per token, minimum 1 token per non-empty string.

    Sufficient for context-window budgeting where a small overestimate is safer
    than an exact tokenizer dependency. Providers that need higher accuracy can
    inject their own ``TokenCounter``.
    """
    if not text:
        return 0
    # Round up so that a 1-char message still costs at least 1 token.
    return max(1, (len(text) + 3) // 4)


def count_message_tokens(message: Message, counter: TokenCounter) -> int:
    """Estimate tokens for a Message including tool-call payloads."""
    total = counter(message.content or "")
    if message.name:
        total += counter(message.name)
    if message.tool_call_id:
        total += counter(message.tool_call_id)
    if message.tool_calls:
        for call in message.tool_calls:
            total += counter(call.name)
            if isinstance(call.arguments, str):
                total += counter(call.arguments)
            else:
                try:
                    total += counter(json.dumps(call.arguments))
                except (TypeError, ValueError):
                    total += counter(str(call.arguments))
    # Small per-message role overhead (matches most chat-format conventions).
    return total + 4


class ContextManager(ABC):
    """Strategy for shaping conversation history into a fixed context window."""

    @abstractmethod
    def fit(self, messages: Iterable[Message]) -> list[Message]:
        """Return a trimmed message list guaranteed to fit within the manager's budget."""

    @abstractmethod
    def count_tokens(self, messages: Iterable[Message]) -> int:
        """Estimate the total token count for the given messages."""


class TokenTrimmingContextManager(ContextManager):
    """Drop the oldest non-system messages until the sequence fits within ``max_tokens``.

    Preserves ordering, always keeps system messages (they carry the standing
    instructions), and never drops the most recent message so the current turn
    always makes it into the request.
    """

    def __init__(
        self,
        max_tokens: int,
        token_counter: TokenCounter | None = None,
    ) -> None:
        if max_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        self.max_tokens = max_tokens
        self._counter: TokenCounter = token_counter or approximate_token_count

    def count_tokens(self, messages: Iterable[Message]) -> int:
        return sum(count_message_tokens(m, self._counter) for m in messages)

    def fit(self, messages: Iterable[Message]) -> list[Message]:
        ordered = list(messages)
        if not ordered:
            return ordered

        system_msgs = [
            m for m in ordered if m.role == MessageRole.SYSTEM or m.role == "system"
        ]
        other_msgs = [
            m for m in ordered if not (m.role == MessageRole.SYSTEM or m.role == "system")
        ]

        # Always keep the most recent non-system message so the current turn survives.
        anchor = other_msgs[-1:] if other_msgs else []
        older = other_msgs[:-1]

        # Start with system + anchor, then re-add older messages from newest to oldest
        # while we stay under budget.
        kept_reversed: list[Message] = []
        current_tokens = self.count_tokens(system_msgs + anchor)
        for msg in reversed(older):
            cost = count_message_tokens(msg, self._counter)
            if current_tokens + cost > self.max_tokens:
                break
            kept_reversed.append(msg)
            current_tokens += cost

        kept_older = list(reversed(kept_reversed))
        return system_msgs + kept_older + anchor


__all__ = [
    "ContextManager",
    "TokenCounter",
    "TokenTrimmingContextManager",
    "approximate_token_count",
    "count_message_tokens",
]
