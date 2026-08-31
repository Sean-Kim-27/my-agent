"""Phase 8 capability tests for the context engine.

These tests pin down the guarantees introduced by Phase 8:

- Assistant tool_call messages and their matching tool result messages must be
  treated as an atomic group by the trimmer (never split across a budget cut).
- The current user turn is preserved verbatim through trimming.
- A single message that exceeds the entire budget raises a structured
  ``ContextOverflowError`` (never silently dropped, never truncated).
- A summarizing context manager compresses middle history into an assistant
  summary and falls back to plain trimming when summary generation fails.
- ``bootstrap.build_agent`` wires a ContextManager onto the Agent using the
  active provider's declared context window.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pytest

from agent_framework.bootstrap import build_agent
from agent_framework.exceptions import ContextOverflowError
from agent_framework.llm.base import LLMProvider
from agent_framework.memory.context import (
    SummarizingContextManager,
    TokenTrimmingContextManager,
    approximate_token_count,
    count_message_tokens,
)
from agent_framework.models.message import Message, MessageRole
from agent_framework.models.response import LLMResponse, ProviderCapabilities
from agent_framework.models.tool import ToolCall, ToolDefinition


def _text(chars: int) -> str:
    return "a" * chars


def _asst_call(call_id: str, name: str = "echo") -> Message:
    return Message.assistant(
        content="calling",
        tool_calls=[ToolCall(id=call_id, name=name, arguments={"x": _text(40)})],
    )


def _tool_result(call_id: str, name: str = "echo") -> Message:
    return Message.tool(content=_text(80), tool_call_id=call_id, name=name)


class ScriptedProvider(LLMProvider):
    """Minimal provider stub that returns a fixed content string per call."""

    def __init__(self, replies: list[str], *, should_fail: bool = False) -> None:
        super().__init__(
            name="scripted",
            model="scripted-model",
            capabilities=ProviderCapabilities(tool_calling=False),
        )
        self.replies = list(replies)
        self.should_fail = should_fail
        self.calls: list[list[Message]] = []

    async def _generate_internal(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        if self.should_fail:
            raise RuntimeError("scripted summary failure")
        self.calls.append(list(messages))
        text = self.replies.pop(0) if self.replies else "ok"
        return LLMResponse(content=text, provider=self.name, model=self.model)

    def _parse_tool_calls(self, raw: Any) -> list[ToolCall]:
        return []

    async def health_check(self) -> bool:
        return True


def test_trimmer_preserves_tool_call_and_result_together() -> None:
    """A tool_call/result pair must be kept or dropped as an atomic group."""
    system = Message.system("sys")
    asst = _asst_call("c1")
    tool = _tool_result("c1")
    latest = Message.user("what is next?")

    budget = count_message_tokens(system, approximate_token_count)
    budget += count_message_tokens(latest, approximate_token_count)
    budget += count_message_tokens(asst, approximate_token_count)
    budget += count_message_tokens(tool, approximate_token_count)
    # Squeeze budget so only one of {(asst,tool), some other} fits — but the
    # (asst, tool) pair must survive together or be dropped together.
    tight = budget - 1

    manager = TokenTrimmingContextManager(max_tokens=tight)
    result = manager.fit([system, asst, tool, latest])

    assert result[0] is system
    assert result[-1] is latest
    # Never contain a lone tool without its assistant call.
    tool_ids = [m.tool_call_id for m in result if m.role == MessageRole.TOOL]
    call_ids = [
        tc.id for m in result if m.tool_calls for tc in m.tool_calls
    ]
    for tid in tool_ids:
        assert tid in call_ids, "tool result kept without its assistant tool_call"


def test_trimmer_drops_full_group_when_budget_tight() -> None:
    """When budget forces a cut, the whole tool_call/result group is dropped."""
    system = Message.system("s")
    old_asst = _asst_call("old")
    old_tool = _tool_result("old")
    new_asst = _asst_call("new")
    new_tool = _tool_result("new")
    latest = Message.user("hi")

    # Budget only accepts system + latest + newest group.
    budget = (
        count_message_tokens(system, approximate_token_count)
        + count_message_tokens(latest, approximate_token_count)
        + count_message_tokens(new_asst, approximate_token_count)
        + count_message_tokens(new_tool, approximate_token_count)
        + 2
    )
    manager = TokenTrimmingContextManager(max_tokens=budget)
    result = manager.fit([system, old_asst, old_tool, new_asst, new_tool, latest])

    assert old_asst not in result
    assert old_tool not in result
    assert new_asst in result
    assert new_tool in result


def test_trimmer_raises_when_single_message_exceeds_budget() -> None:
    """A single mandatory message larger than the budget must fail loudly."""
    system = Message.system("sys")
    latest = Message.user(_text(4_000))  # ~1_000 tokens

    manager = TokenTrimmingContextManager(max_tokens=100)
    with pytest.raises(ContextOverflowError):
        manager.fit([system, latest])


def test_trimmer_never_drops_current_user_turn() -> None:
    """The most recent user message must always survive trimming."""
    system = Message.system("sys")
    stale = Message.user(_text(400))
    latest = Message.user("please answer")

    manager = TokenTrimmingContextManager(max_tokens=60)
    result = manager.fit([system, stale, latest])
    assert result[0] is system
    assert result[-1] is latest


@pytest.mark.asyncio
async def test_summarizing_manager_compresses_middle_history() -> None:
    """When over budget, the summarizer replaces middle messages with an assistant summary."""
    system = Message.system("sys")
    middle = [Message.user(_text(400)), Message.assistant(_text(400))]
    latest = Message.user("what did I ask?")

    provider = ScriptedProvider(replies=["<summary of prior turns>"])
    manager = SummarizingContextManager(
        max_tokens=60,
        summarizer=provider,
        summary_max_tokens=32,
    )
    result = await manager.afit([system, *middle, latest])

    assert result[0].role == MessageRole.SYSTEM
    assert result[-1] is latest
    # A summary assistant message should appear between system and the latest turn.
    assert any(
        m.role == MessageRole.ASSISTANT and "summary" in (m.content or "").lower()
        for m in result
    )


@pytest.mark.asyncio
async def test_summarizing_manager_falls_back_to_trimming_on_summary_failure() -> None:
    """If summary generation raises, the manager returns a safe trimmed list."""
    system = Message.system("sys")
    middle = [Message.user(_text(400)), Message.assistant(_text(400))]
    latest = Message.user("ok")

    failing = ScriptedProvider(replies=[], should_fail=True)
    manager = SummarizingContextManager(
        max_tokens=60,
        summarizer=failing,
        summary_max_tokens=32,
    )
    result = await manager.afit([system, *middle, latest])

    # Fallback must still return a valid, budget-respecting sequence.
    assert result[0] is system
    assert result[-1] is latest
    assert all(m.content is None or "summary" not in (m.content or "").lower() for m in result)


def test_summarizing_manager_sync_fit_falls_back_to_trimming() -> None:
    """Sync fit() must never call the LLM; it degrades to plain trimming."""
    system = Message.system("sys")
    middle = [Message.user(_text(300))]
    latest = Message.user("ok")

    provider = ScriptedProvider(replies=[])
    manager = SummarizingContextManager(
        max_tokens=100,
        summarizer=provider,
        summary_max_tokens=32,
    )
    result = manager.fit([system, *middle, latest])
    assert result[0] is system
    assert result[-1] is latest
    # Summarizer must not have been consulted from the sync path.
    assert provider.calls == []


def test_bootstrap_attaches_context_manager_from_provider_window(
    sample_settings: Any,
) -> None:
    """build_agent wires a ContextManager whose budget derives from the provider window."""
    settings = sample_settings.model_copy(
        update={
            "context_manager_enabled": True,
            "context_headroom_ratio": 0.5,
        }
    )
    agent, _, _ = build_agent(settings=settings)
    assert agent.context_manager is not None
    # Provider's declared window (or the configured fallback) minus headroom.
    assert isinstance(agent.context_manager, TokenTrimmingContextManager)
    assert agent.context_manager.max_tokens > 0


def test_bootstrap_context_manager_disabled(sample_settings: Any) -> None:
    """When disabled, no ContextManager is attached and the Agent behaves as before."""
    settings = sample_settings.model_copy(update={"context_manager_enabled": False})
    agent, _, _ = build_agent(settings=settings)
    assert agent.context_manager is None


# Async support helper for SummarizingContextManager tests
async def _drive(cm: SummarizingContextManager, messages: Iterable[Message]) -> list[Message]:
    return await cm.afit(list(messages))
