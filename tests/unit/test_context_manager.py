"""Tests for the token-based ContextManager skeleton."""

from __future__ import annotations

from agent_framework.memory.context import (
    TokenTrimmingContextManager,
    approximate_token_count,
    count_message_tokens,
)
from agent_framework.models.message import Message, MessageRole
from agent_framework.models.tool import ToolCall


def _words(count: int, letter: str = "a") -> str:
    """Build a string of `count` 4-character tokens separated by spaces."""
    return " ".join(letter * 4 for _ in range(count))


def test_approximate_token_count_heuristic() -> None:
    assert approximate_token_count("") == 0
    assert approximate_token_count("a") == 1
    assert approximate_token_count("abcd") == 1
    assert approximate_token_count("abcde") == 2


def test_count_message_tokens_includes_tool_calls() -> None:
    msg = Message.assistant(
        content="hi",
        tool_calls=[ToolCall(id="1", name="search", arguments={"q": "python"})],
    )
    tokens = count_message_tokens(msg, approximate_token_count)
    assert tokens > count_message_tokens(Message.assistant("hi"), approximate_token_count)


def test_token_trimming_preserves_system_and_latest_message() -> None:
    system = Message.system(_words(1))
    old_user = Message.user(_words(20))
    mid_user = Message.user(_words(20))
    latest = Message.user(_words(2))

    manager = TokenTrimmingContextManager(max_tokens=30)
    result = manager.fit([system, old_user, mid_user, latest])

    # System and latest must always survive.
    assert result[0].role == MessageRole.SYSTEM
    assert result[-1] is latest
    # Old messages must be dropped once budget is exceeded.
    assert old_user not in result


def test_token_trimming_returns_all_when_within_budget() -> None:
    system = Message.system("hi")
    user = Message.user("hello")
    assistant = Message.assistant("world")

    manager = TokenTrimmingContextManager(max_tokens=1_000)
    result = manager.fit([system, user, assistant])
    assert result == [system, user, assistant]


def test_token_trimming_handles_empty() -> None:
    manager = TokenTrimmingContextManager(max_tokens=100)
    assert manager.fit([]) == []


def test_token_trimming_keeps_newest_older_message_first() -> None:
    """When budget only fits one older message, keep the most recent one."""
    system = Message.system("sys")
    older = Message.user(_words(3))
    newer = Message.assistant(_words(3))
    latest = Message.user(_words(2))

    # Budget: system(~5) + latest(~2 content + overhead) + one of the two.
    manager = TokenTrimmingContextManager(max_tokens=20)
    result = manager.fit([system, older, newer, latest])

    assert result[0] is system
    assert result[-1] is latest
    assert newer in result
    assert older not in result
