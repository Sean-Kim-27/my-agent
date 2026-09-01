"""Context window management primitives.

This module provides the ``ContextManager`` interface used by the agent to
constrain conversation history to fit within a token budget before it is sent
to an LLM. Two concrete strategies ship out of the box:

* :class:`TokenTrimmingContextManager` drops the oldest non-system atomic
  groups until the sequence fits.
* :class:`SummarizingContextManager` compresses the middle of the
  conversation into an assistant summary message and falls back to plain
  trimming on failure.

The trimmer treats an assistant ``tool_calls`` message together with each of
its matching tool-result messages as a single **atomic group**: budget cuts
are made at group boundaries so a tool call is never split from its result.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from agent_framework.exceptions import ContextOverflowError
from agent_framework.models.message import Message, MessageRole

if TYPE_CHECKING:
    from agent_framework.llm.base import LLMProvider


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
    return total + 4


def _is_system(message: Message) -> bool:
    return message.role == MessageRole.SYSTEM or message.role == "system"


def _is_tool(message: Message) -> bool:
    return message.role == MessageRole.TOOL or message.role == "tool"


@dataclass(frozen=True)
class MessageGroup:
    """A trim-atomic block of messages.

    Groups exist so an assistant ``tool_calls`` message and each of its
    matching tool-result messages are dropped together, preserving the
    invariant enforced by :meth:`Agent._validate_tool_pairing`.
    """

    messages: tuple[Message, ...]

    @property
    def tokens(self) -> int:
        return sum(count_message_tokens(m, approximate_token_count) for m in self.messages)


def build_groups(messages: Sequence[Message]) -> list[MessageGroup]:
    """Partition a message list into trim-atomic groups.

    - Every system message is its own group (system messages are kept as-is).
    - An assistant message carrying ``tool_calls`` swallows all subsequent
      tool-role messages whose ``tool_call_id`` matches one of its calls.
    - Any other message is its own group.
    """
    groups: list[MessageGroup] = []
    index = 0
    while index < len(messages):
        msg = messages[index]
        if msg.tool_calls:
            expected_ids = {call.id for call in msg.tool_calls}
            block: list[Message] = [msg]
            probe = index + 1
            while probe < len(messages):
                candidate = messages[probe]
                if _is_tool(candidate) and candidate.tool_call_id in expected_ids:
                    block.append(candidate)
                    expected_ids.discard(candidate.tool_call_id or "")
                    probe += 1
                    continue
                break
            groups.append(MessageGroup(tuple(block)))
            index = probe
        else:
            groups.append(MessageGroup((msg,)))
            index += 1
    return groups


class ContextManager(ABC):
    """Strategy for shaping conversation history into a fixed context window."""

    @abstractmethod
    def fit(self, messages: Iterable[Message]) -> list[Message]:
        """Return a trimmed message list guaranteed to fit within the manager's budget."""

    @abstractmethod
    def count_tokens(self, messages: Iterable[Message]) -> int:
        """Estimate the total token count for the given messages."""


class TokenTrimmingContextManager(ContextManager):
    """Drop the oldest non-system atomic groups until the sequence fits within ``max_tokens``.

    Guarantees:

    - System messages are always preserved.
    - The most recent non-system group (the current turn) is always preserved.
    - Assistant tool_call + tool_result messages are treated as an atomic
      group and never split by trimming.
    - If system + current-turn alone exceed the budget, raises
      :class:`ContextOverflowError` (fail closed — never truncate a mandatory
      message).
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

    def _group_tokens(self, group: MessageGroup) -> int:
        return sum(count_message_tokens(m, self._counter) for m in group.messages)

    def fit(self, messages: Iterable[Message]) -> list[Message]:
        ordered = list(messages)
        if not ordered:
            return ordered

        groups = build_groups(ordered)
        system_groups = [g for g in groups if all(_is_system(m) for m in g.messages)]
        other_groups = [g for g in groups if not all(_is_system(m) for m in g.messages)]

        if not other_groups:
            base_tokens = sum(self._group_tokens(g) for g in system_groups)
            if base_tokens > self.max_tokens:
                raise ContextOverflowError(
                    "System messages alone exceed the configured context budget.",
                    required_tokens=base_tokens,
                    max_tokens=self.max_tokens,
                )
            return [m for g in system_groups for m in g.messages]

        anchor_group = other_groups[-1]
        older_groups = other_groups[:-1]

        base_tokens = sum(self._group_tokens(g) for g in system_groups)
        anchor_tokens = self._group_tokens(anchor_group)
        required = base_tokens + anchor_tokens
        if required > self.max_tokens:
            raise ContextOverflowError(
                "System messages plus the current turn exceed the configured context "
                "budget. Split the input, raise 'context_max_tokens', or select a model "
                "with a larger window.",
                required_tokens=required,
                max_tokens=self.max_tokens,
            )

        kept_reversed: list[MessageGroup] = []
        current = required
        for group in reversed(older_groups):
            cost = self._group_tokens(group)
            if current + cost > self.max_tokens:
                break
            kept_reversed.append(group)
            current += cost

        kept_older = list(reversed(kept_reversed))
        selected = system_groups + kept_older + [anchor_group]
        return [m for g in selected for m in g.messages]


class SummarizingContextManager(ContextManager):
    """Compress middle-history into an assistant summary before falling back to trimming.

    Uses ``fit`` (sync) for the safe trimming path so callers can invoke it
    without an event loop; :meth:`afit` performs the LLM-assisted compression
    and gracefully falls back to trimming if the summarizer raises.
    """

    _SUMMARY_ROLE_MARKER = "context.summary"

    def __init__(
        self,
        max_tokens: int,
        summarizer: LLMProvider,
        summary_max_tokens: int = 512,
        token_counter: TokenCounter | None = None,
        summary_prompt: str | None = None,
    ) -> None:
        if summary_max_tokens <= 0:
            raise ValueError("summary_max_tokens must be positive")
        self._trimmer = TokenTrimmingContextManager(
            max_tokens=max_tokens, token_counter=token_counter
        )
        self.max_tokens = max_tokens
        self.summarizer = summarizer
        self.summary_max_tokens = summary_max_tokens
        self._prompt = summary_prompt or (
            "Summarize the following prior conversation turns into a concise "
            "assistant-authored note that preserves task-relevant facts, "
            "user preferences, and outstanding TODOs. Do not invent details."
        )

    def count_tokens(self, messages: Iterable[Message]) -> int:
        return self._trimmer.count_tokens(messages)

    def fit(self, messages: Iterable[Message]) -> list[Message]:
        """Synchronous fit degrades to plain trimming (no LLM I/O)."""
        return self._trimmer.fit(messages)

    async def afit(self, messages: Iterable[Message]) -> list[Message]:
        """Async fit: summarize the middle if over budget, else trim.

        On summarizer failure the manager returns a plain trimmed sequence so
        the caller always sees a budget-respecting message list.
        """
        ordered = list(messages)
        if self._trimmer.count_tokens(ordered) <= self.max_tokens:
            return ordered

        groups = build_groups(ordered)
        system_groups = [g for g in groups if all(_is_system(m) for m in g.messages)]
        other_groups = [g for g in groups if not all(_is_system(m) for m in g.messages)]
        if len(other_groups) < 2:
            return self._trimmer.fit(ordered)

        anchor = other_groups[-1]
        middle_messages = [m for g in other_groups[:-1] for m in g.messages]
        if not middle_messages:
            return self._trimmer.fit(ordered)

        try:
            summary = await self._summarize(middle_messages)
        except Exception:
            return self._trimmer.fit(ordered)

        assembled: list[Message] = []
        for g in system_groups:
            assembled.extend(g.messages)
        assembled.append(summary)
        assembled.extend(anchor.messages)

        if self._trimmer.count_tokens(assembled) <= self.max_tokens:
            return assembled
        return self._trimmer.fit(assembled)

    async def _summarize(self, middle: list[Message]) -> Message:
        transcript_lines: list[str] = []
        for msg in middle:
            role = str(msg.role)
            content = msg.content or ""
            if msg.tool_calls:
                content = f"[tool_calls: {[tc.name for tc in msg.tool_calls]}] {content}"
            transcript_lines.append(f"{role}: {content}")
        transcript = "\n".join(transcript_lines)
        request = [
            Message.system(self._prompt),
            Message.user(transcript),
        ]
        response = await self.summarizer.generate(
            request,
            max_tokens=self.summary_max_tokens,
        )
        summary_text = (response.content or "").strip()
        if not summary_text:
            raise RuntimeError("summarizer returned empty content")
        return Message.assistant(
            content=f"[summary of prior conversation]\n{summary_text}",
            metadata={"origin": self._SUMMARY_ROLE_MARKER},
        )


__all__ = [
    "ContextManager",
    "MessageGroup",
    "SummarizingContextManager",
    "TokenCounter",
    "TokenTrimmingContextManager",
    "approximate_token_count",
    "build_groups",
    "count_message_tokens",
]
