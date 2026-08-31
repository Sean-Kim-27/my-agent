"""Phase 0 baseline eval scenarios.

Each scenario is a behavior-level regression test locking in a capability the
master plan promises. They are intentionally small, hermetic (no network), and
fast so they run inside the normal ``pytest -q`` gate.

The set mirrors the list in ``docs/master_plan.md`` (Phase 0 · 기본 eval 시나리오):

1. Plain chat
2. Single tool call
3. Two tool calls in a single response
4. Tool error + self-correction
5. Tool timeout surfaces as a tool error
6. Provider 429 retry succeeds
7. Max steps reached
8. Cross-session memory isolation
9. SQLite restart restores the conversation
10. Secret masking in logs
"""

from __future__ import annotations

import asyncio
import io
import logging
import tempfile
from pathlib import Path
from typing import Any

import pytest

from agent_framework.exceptions import AgentError
from agent_framework.llm.retry import call_with_retry
from agent_framework.logging.logger import SecretMaskingFormatter, mask_secrets
from agent_framework.memory.session import SessionManager
from agent_framework.memory.sqlite import SQLiteConversationMemory, sqlite_memory_factory
from agent_framework.models.message import Message, MessageRole
from agent_framework.models.response import LLMResponse
from agent_framework.models.tool import ToolCall
from agent_framework.tools.executor import ToolExecutor
from agent_framework.tools.registry import ToolRegistry
from tests.conftest import MockLLMProvider

# ---------------------------------------------------------------------------
# 1. Plain chat
# ---------------------------------------------------------------------------


async def test_plain_chat_single_turn(make_agent: Any) -> None:
    provider = MockLLMProvider(default_response_text="Hi there!")
    agent = make_agent(provider=provider)

    result = await agent.run_with_trace("hello", session_id="eval:chat")

    assert result.content == "Hi there!"
    assert result.total_steps == 1
    assert result.is_max_steps_reached is False


# ---------------------------------------------------------------------------
# 2. Single tool call
# ---------------------------------------------------------------------------


async def test_single_tool_call(make_agent: Any) -> None:
    registry = ToolRegistry()

    @registry.tool(description="Return a fixed string")
    def echo(value: str) -> str:
        return f"echo:{value}"

    provider = MockLLMProvider()
    provider.response_queue = [
        LLMResponse(
            content="",
            tool_calls=[ToolCall(id="c1", name="echo", arguments={"value": "hello"})],
        ),
        LLMResponse(content="done"),
    ]
    agent = make_agent(provider=provider, tool_registry=registry)

    result = await agent.run_with_trace("run echo", session_id="eval:tool")

    assert result.content == "done"
    assert result.total_steps == 2
    tool_step = result.steps[0]
    assert tool_step.tool_results is not None
    assert tool_step.tool_results[0].content == "echo:hello"
    assert tool_step.tool_results[0].is_error is False


# ---------------------------------------------------------------------------
# 3. Two tool calls in a single response
# ---------------------------------------------------------------------------


async def test_two_tool_calls_in_one_response(make_agent: Any) -> None:
    registry = ToolRegistry()

    @registry.tool(description="Increment")
    def inc(n: int) -> int:
        return n + 1

    @registry.tool(description="Double")
    def double(n: int) -> int:
        return n * 2

    provider = MockLLMProvider()
    provider.response_queue = [
        LLMResponse(
            content="",
            tool_calls=[
                ToolCall(id="a", name="inc", arguments={"n": 4}),
                ToolCall(id="b", name="double", arguments={"n": 4}),
            ],
        ),
        LLMResponse(content="5 and 8"),
    ]
    agent = make_agent(provider=provider, tool_registry=registry)

    result = await agent.run_with_trace("compute", session_id="eval:multi_tool")

    tool_step = result.steps[0]
    assert tool_step.tool_results is not None
    results_by_id = {r.tool_call_id: r.content for r in tool_step.tool_results}
    assert results_by_id == {"a": "5", "b": "8"}


# ---------------------------------------------------------------------------
# 4. Tool error + self-correction
# ---------------------------------------------------------------------------


async def test_tool_error_triggers_self_correction(make_agent: Any) -> None:
    registry = ToolRegistry()
    calls: list[int] = []

    @registry.tool(description="Fails on the first invocation, succeeds on retry")
    def flaky(n: int) -> int:
        calls.append(n)
        if len(calls) == 1:
            raise RuntimeError("boom")
        return n * 10

    provider = MockLLMProvider()
    provider.response_queue = [
        LLMResponse(
            content="",
            tool_calls=[ToolCall(id="x", name="flaky", arguments={"n": 3})],
        ),
        LLMResponse(
            content="",
            tool_calls=[ToolCall(id="y", name="flaky", arguments={"n": 3})],
        ),
        LLMResponse(content="final=30"),
    ]
    agent = make_agent(provider=provider, tool_registry=registry, max_steps=5)

    result = await agent.run_with_trace("try", session_id="eval:self_correct")

    assert result.content == "final=30"
    assert result.total_steps == 3
    first = result.steps[0].tool_results
    assert first is not None and first[0].is_error is True
    second = result.steps[1].tool_results
    assert second is not None and second[0].is_error is False


# ---------------------------------------------------------------------------
# 5. Tool timeout
# ---------------------------------------------------------------------------


async def test_tool_timeout_surfaces_as_error() -> None:
    registry = ToolRegistry()

    @registry.tool(description="Sleeps longer than the executor timeout")
    async def slow() -> str:
        await asyncio.sleep(0.5)
        return "never"

    executor = ToolExecutor(registry, default_timeout=0.05)
    result = await executor.execute(ToolCall(id="t", name="slow", arguments={}))

    assert result.is_error is True
    assert "timed out" in result.content


# ---------------------------------------------------------------------------
# 6. Provider 429 retry succeeds
# ---------------------------------------------------------------------------


class RateLimitError(Exception):
    """Stand-in matching the SDK class name recognised by ``is_retryable_error``."""


async def test_provider_rate_limit_retry_succeeds() -> None:
    attempts = {"n": 0}

    async def flaky() -> str:
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise RateLimitError("slow down")
        return "ok"

    out = await call_with_retry(flaky, max_retries=3, initial_wait=0.001, max_wait=0.002)

    assert out == "ok"
    assert attempts["n"] == 3


# ---------------------------------------------------------------------------
# 7. Max steps reached
# ---------------------------------------------------------------------------


async def test_max_steps_reached_raises(make_agent: Any) -> None:
    registry = ToolRegistry()

    @registry.tool(description="No-op tool")
    def noop() -> str:
        return "ok"

    provider = MockLLMProvider()
    # Always ask for another tool call so we never terminate naturally.
    provider.response_queue = [
        LLMResponse(
            content="",
            tool_calls=[ToolCall(id=f"c{i}", name="noop", arguments={})],
        )
        for i in range(10)
    ]
    agent = make_agent(provider=provider, tool_registry=registry, max_steps=3)

    with pytest.raises(AgentError) as exc:
        await agent.run_with_trace("loop", session_id="eval:max_steps")

    assert "maximum execution steps" in str(exc.value)


# ---------------------------------------------------------------------------
# 8. Cross-session memory isolation
# ---------------------------------------------------------------------------


async def test_cross_session_memory_is_isolated(make_agent: Any) -> None:
    provider = MockLLMProvider(default_response_text="reply")
    agent = make_agent(provider=provider)

    await agent.run_with_trace("hi from A", session_id="eval:iso:A")
    await agent.run_with_trace("hi from B", session_id="eval:iso:B")

    mem_a = await agent.session_manager.get_memory("eval:iso:A")
    mem_b = await agent.session_manager.get_memory("eval:iso:B")
    msgs_a = [m.content for m in await mem_a.get_messages()]
    msgs_b = [m.content for m in await mem_b.get_messages()]

    assert "hi from A" in msgs_a and "hi from B" not in msgs_a
    assert "hi from B" in msgs_b and "hi from A" not in msgs_b


# ---------------------------------------------------------------------------
# 9. SQLite restart restores the conversation
# ---------------------------------------------------------------------------


async def test_sqlite_memory_survives_process_restart() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "eval.sqlite"
        session_id = "eval:restart"

        # First "process": write two messages.
        mem1 = SQLiteConversationMemory(session_id=session_id, db_path=db_path)
        await mem1.add(Message.user("first"))
        await mem1.add(Message(role=MessageRole.ASSISTANT, content="second"))
        assert await mem1.count() == 2

        # Simulate restart by dropping the reference and opening a fresh
        # SessionManager backed by a factory identical to what bootstrap wires.
        factory = sqlite_memory_factory(db_path=str(db_path))
        manager = SessionManager(memory_factory=factory)
        mem2 = await manager.get_memory(session_id)

        restored = await mem2.get_messages()
        assert [m.content for m in restored] == ["first", "second"]


# ---------------------------------------------------------------------------
# 10. Secret masking in logs
# ---------------------------------------------------------------------------


def test_secret_masking_redacts_common_shapes() -> None:
    # Direct helper
    masked = mask_secrets("token=sk-ABCDEFGHIJKLMNOPQRSTUV bearer xyz")
    assert "sk-ABCDEFGHIJKLMNOPQRSTUV" not in masked

    # Formatter wired into a logger emits already-masked output
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(SecretMaskingFormatter())
    log = logging.getLogger("agent_framework.evals.masking")
    log.handlers.clear()
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    log.propagate = False

    log.info("using api key sk-SECRETVALUE1234567890 in request")
    handler.flush()

    assert "sk-SECRETVALUE1234567890" not in buf.getvalue()
