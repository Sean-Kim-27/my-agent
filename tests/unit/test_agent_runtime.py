"""Phase 1 capability tests for the Agent run-loop state machine.

These tests pin down the guarantees introduced by Phase 1: exactly-once
error dispatch, one-off callback participation, per-iteration context
re-fitting, tool call/result pairing and ordering, structured max_steps
termination, RunContext cancellation and timeout, and per-step usage/provider
/model/error metadata.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from typing import Any

import pytest

from agent_framework.agent.agent import Agent
from agent_framework.agent.events import AgentCallbackHandler
from agent_framework.agent.runtime import RunContext, RunState
from agent_framework.exceptions import AgentError
from agent_framework.memory.context import ContextManager
from agent_framework.memory.session import SessionManager
from agent_framework.models.message import Message
from agent_framework.models.response import LLMResponse, TokenUsage
from agent_framework.models.tool import ToolCall, ToolCallResult
from agent_framework.tools.executor import ToolExecutor
from agent_framework.tools.registry import ToolRegistry
from tests.conftest import MockLLMProvider


class RecordingCallback(AgentCallbackHandler):
    """Callback that records every method invocation as a tuple."""

    def __init__(self, label: str = "cb") -> None:
        self.label = label
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def on_agent_start(self, session_id: str, prompt: str) -> None:
        self.calls.append(("on_agent_start", {"session_id": session_id}))

    async def on_llm_start(self, step: int, messages: list[Message]) -> None:
        self.calls.append(("on_llm_start", {"step": step, "n": len(messages)}))

    async def on_llm_end(self, step: int, response: LLMResponse) -> None:
        self.calls.append(("on_llm_end", {"step": step}))

    async def on_tool_start(self, step: int, tool_name: str, arguments: dict[str, Any] | str) -> None:
        self.calls.append(("on_tool_start", {"tool": tool_name}))

    async def on_tool_end(self, step: int, tool_name: str, result: str, is_error: bool) -> None:
        self.calls.append(("on_tool_end", {"tool": tool_name, "is_error": is_error}))

    async def on_agent_finish(self, session_id: str, final_response: LLMResponse, total_steps: int) -> None:
        self.calls.append(("on_agent_finish", {"session_id": session_id, "steps": total_steps}))

    async def on_agent_error(self, session_id: str, error: Exception) -> None:
        self.calls.append(("on_agent_error", {"session_id": session_id, "error_type": type(error).__name__}))


class CountingContextManager(ContextManager):
    """ContextManager stub that counts how many times ``fit`` is called."""

    def __init__(self) -> None:
        self.fit_calls = 0

    def fit(self, messages: Iterable[Message]) -> list[Message]:
        self.fit_calls += 1
        return list(messages)

    def count_tokens(self, messages: Iterable[Message]) -> int:
        return 0


@pytest.mark.asyncio
async def test_on_agent_error_fires_exactly_once_on_provider_failure(mock_provider: MockLLMProvider) -> None:
    """A single provider failure must produce exactly one on_agent_error dispatch."""
    mock_provider.should_fail_with = AgentError("boom")
    tracker = RecordingCallback()

    agent = Agent(provider=mock_provider, callbacks=[tracker])

    with pytest.raises(AgentError):
        await agent.run("hello")

    error_events = [c for c in tracker.calls if c[0] == "on_agent_error"]
    assert len(error_events) == 1


@pytest.mark.asyncio
async def test_one_off_callbacks_receive_lifecycle_events(mock_provider: MockLLMProvider) -> None:
    """Callbacks passed to run_with_trace must observe lifecycle events, not only confirmations."""
    one_off = RecordingCallback(label="one-off")
    agent = Agent(provider=mock_provider)

    await agent.run_with_trace("hi", callbacks=[one_off])

    names = [c[0] for c in one_off.calls]
    assert "on_agent_start" in names
    assert "on_llm_start" in names
    assert "on_llm_end" in names
    assert "on_agent_finish" in names


@pytest.mark.asyncio
async def test_context_manager_fits_on_every_iteration() -> None:
    """ContextManager.fit must run before each provider call (initial + after tool result)."""
    registry = ToolRegistry()

    @registry.tool(description="echo")
    def echo(x: str) -> str:
        return x

    step1 = LLMResponse(
        content="Calling tool",
        tool_calls=[ToolCall(id="c1", name="echo", arguments={"x": "hi"})],
    )
    step2 = LLMResponse(content="done", tool_calls=[])

    provider = MockLLMProvider()
    provider.response_queue = [step1, step2]

    cm = CountingContextManager()
    agent = Agent(provider=provider, tool_registry=registry, context_manager=cm)

    await agent.run_with_trace("go")

    assert cm.fit_calls >= 2


@pytest.mark.asyncio
async def test_tool_result_order_matches_tool_call_order() -> None:
    """When the model requests multiple tool calls, results are recorded in call order."""
    registry = ToolRegistry()

    @registry.tool(description="slow")
    async def slow() -> str:
        await asyncio.sleep(0.02)
        return "slow-done"

    @registry.tool(description="fast")
    async def fast() -> str:
        return "fast-done"

    step1 = LLMResponse(
        content="two tools",
        tool_calls=[
            ToolCall(id="a", name="slow", arguments={}),
            ToolCall(id="b", name="fast", arguments={}),
        ],
    )
    step2 = LLMResponse(content="ok", tool_calls=[])

    provider = MockLLMProvider()
    provider.response_queue = [step1, step2]

    agent = Agent(provider=provider, tool_registry=registry)
    result = await agent.run_with_trace("go")

    first_step = result.steps[0]
    assert [r.tool_call_id for r in first_step.tool_results] == ["a", "b"]
    assert first_step.tool_results[0].content == "slow-done"
    assert first_step.tool_results[1].content == "fast-done"


@pytest.mark.asyncio
async def test_tool_call_result_pairing_validated() -> None:
    """If a tool call has no matching result, the agent must fail structurally (not silently drop)."""
    registry = ToolRegistry()

    @registry.tool(description="ok")
    def ok() -> str:
        return "fine"

    class DroppingExecutor(ToolExecutor):
        async def execute_all(self, tool_calls, timeout=None, confirm=None, *, context=None):  # type: ignore[override]
            return []  # drop all results

    step1 = LLMResponse(
        content="call",
        tool_calls=[ToolCall(id="only", name="ok", arguments={})],
    )
    provider = MockLLMProvider()
    provider.response_queue = [step1]

    agent = Agent(
        provider=provider,
        tool_registry=registry,
        tool_executor=DroppingExecutor(registry),
    )

    with pytest.raises(AgentError, match="tool call"):
        await agent.run_with_trace("go")


@pytest.mark.asyncio
async def test_unexpected_tool_result_is_rejected() -> None:
    """A result without a matching tool call must fail closed instead of entering history."""
    registry = ToolRegistry()

    @registry.tool(description="ok")
    def ok() -> str:
        return "fine"

    class UnexpectedResultExecutor(ToolExecutor):
        async def execute_all(self, tool_calls, timeout=None, confirm=None, *, context=None):  # type: ignore[override]
            call = tool_calls[0]
            return [
                ToolCallResult(tool_call_id=call.id, name=call.name, content="fine"),
                ToolCallResult(tool_call_id="unexpected", name="ok", content="extra"),
            ]

    provider = MockLLMProvider()
    provider.response_queue = [
        LLMResponse(
            content="call",
            tool_calls=[ToolCall(id="expected", name="ok", arguments={})],
        )
    ]
    agent = Agent(
        provider=provider,
        tool_registry=registry,
        tool_executor=UnexpectedResultExecutor(registry),
    )

    with pytest.raises(AgentError, match="matching tool call"):
        await agent.run_with_trace("go")


@pytest.mark.asyncio
async def test_run_context_cancellation_stops_agent() -> None:
    """Setting RunContext.cancel() while the agent is running terminates it as CANCELLED."""
    registry = ToolRegistry()

    @registry.tool(description="hang")
    async def hang() -> str:
        await asyncio.sleep(1.0)
        return "never"

    step1 = LLMResponse(
        content="calling hang",
        tool_calls=[ToolCall(id="h", name="hang", arguments={})],
    )
    provider = MockLLMProvider()
    provider.response_queue = [step1]

    agent = Agent(provider=provider, tool_registry=registry)
    ctx = RunContext.create(session_id="cancel:test")

    async def canceller() -> None:
        await asyncio.sleep(0.05)
        ctx.cancel()

    with pytest.raises(asyncio.CancelledError):
        await asyncio.gather(
            agent.run_with_trace("go", run_context=ctx),
            canceller(),
        )
    assert ctx.state == RunState.CANCELLED


@pytest.mark.asyncio
async def test_run_context_cancellation_interrupts_provider_call() -> None:
    """Cooperative cancellation must not wait for an in-flight provider call to return."""

    class BlockingProvider(MockLLMProvider):
        def __init__(self) -> None:
            super().__init__()
            self.started = asyncio.Event()
            self.cancelled = asyncio.Event()

        async def _generate_internal(self, messages, tools=None, **kwargs):  # type: ignore[override]
            self.started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.cancelled.set()
                raise
            raise AssertionError("unreachable")

    provider = BlockingProvider()
    agent = Agent(provider=provider)
    ctx = RunContext.create(session_id="provider-cancel:test")
    run_task = asyncio.create_task(agent.run_with_trace("go", run_context=ctx))

    await provider.started.wait()
    ctx.cancel()
    done, _ = await asyncio.wait({run_task}, timeout=0.2)
    try:
        assert run_task in done
        with pytest.raises(asyncio.CancelledError):
            await run_task
        assert provider.cancelled.is_set()
        assert ctx.state == RunState.CANCELLED
    finally:
        if not run_task.done():
            run_task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await run_task


@pytest.mark.asyncio
async def test_run_timeout_terminates_as_cancelled() -> None:
    """A configured timeout must terminate the run and mark state as CANCELLED."""
    registry = ToolRegistry()

    @registry.tool(description="hang")
    async def hang() -> str:
        await asyncio.sleep(1.0)
        return "never"

    step1 = LLMResponse(
        content="calling hang",
        tool_calls=[ToolCall(id="h", name="hang", arguments={})],
    )
    provider = MockLLMProvider()
    provider.response_queue = [step1]

    agent = Agent(provider=provider, tool_registry=registry)
    ctx = RunContext.create(session_id="timeout:test", timeout_seconds=0.05)

    with pytest.raises(asyncio.CancelledError):
        await agent.run_with_trace("go", run_context=ctx)
    assert ctx.state == RunState.CANCELLED


@pytest.mark.asyncio
async def test_run_context_session_id_selects_actual_session(mock_provider: MockLLMProvider) -> None:
    """A context-provided session ID must match the memory and result used by the run."""
    manager = SessionManager()
    agent = Agent(
        provider=mock_provider,
        session_manager=manager,
        default_session_id="default:test",
    )
    ctx = RunContext.create(session_id="context:test")

    result = await agent.run_with_trace("hello", run_context=ctx)

    assert result.session_id == "context:test"
    assert ctx.session_id == "context:test"
    assert await manager.has_session("context:test")
    assert not await manager.has_session("default:test")


@pytest.mark.asyncio
async def test_setup_failure_marks_run_failed_and_dispatches_once(
    mock_provider: MockLLMProvider,
) -> None:
    """Failures before the first provider call must still leave a terminal, observable run."""

    class FailingSessionManager(SessionManager):
        async def get_memory(self, session_id: str):  # type: ignore[override]
            raise RuntimeError("memory unavailable")

    tracker = RecordingCallback()
    ctx = RunContext.create(session_id="setup-failure:test")
    agent = Agent(
        provider=mock_provider,
        session_manager=FailingSessionManager(),
        callbacks=[tracker],
    )

    with pytest.raises(RuntimeError, match="memory unavailable"):
        await agent.run_with_trace("hello", run_context=ctx)

    assert ctx.state == RunState.FAILED
    error_events = [call for call in tracker.calls if call[0] == "on_agent_error"]
    assert len(error_events) == 1


@pytest.mark.asyncio
async def test_max_steps_termination_is_structured() -> None:
    """max_steps must produce a structured, terminal FAILED state via AgentError."""
    registry = ToolRegistry()

    @registry.tool(description="loop")
    def loop() -> str:
        return "x"

    looping = LLMResponse(
        content="loop",
        tool_calls=[ToolCall(id="c", name="loop", arguments={})],
    )
    provider = MockLLMProvider()
    provider.response_queue = [looping, looping, looping, looping]

    tracker = RecordingCallback()
    agent = Agent(provider=provider, tool_registry=registry, max_steps=2, callbacks=[tracker])
    ctx = RunContext.create(session_id="ms:test")

    with pytest.raises(AgentError, match="max_steps"):
        await agent.run_with_trace("go", run_context=ctx)
    assert ctx.state == RunState.FAILED
    error_events = [c for c in tracker.calls if c[0] == "on_agent_error"]
    assert len(error_events) == 1


@pytest.mark.asyncio
async def test_step_records_provider_model_and_usage() -> None:
    """Each AgentStep records the provider, model and token usage that produced it."""
    step1 = LLMResponse(
        content="hello",
        usage=TokenUsage(prompt_tokens=11, completion_tokens=3, total_tokens=14),
        provider="mock_provider",
        model="mock-model-v1",
    )
    provider = MockLLMProvider()
    provider.response_queue = [step1]

    agent = Agent(provider=provider)
    result = await agent.run_with_trace("hi")

    assert result.state == RunState.COMPLETED
    assert result.run_id
    assert len(result.steps) == 1
    step = result.steps[0]
    assert step.provider == "mock_provider"
    assert step.model == "mock-model-v1"
    assert step.token_usage is not None
    assert step.token_usage.total_tokens == 14
    assert step.error is None


@pytest.mark.asyncio
async def test_callback_failure_does_not_stop_run(mock_provider: MockLLMProvider) -> None:
    """A callback raising must be logged but must not fail the agent run."""

    class BrokenCallback(AgentCallbackHandler):
        async def on_agent_start(self, session_id: str, prompt: str) -> None:
            raise RuntimeError("callback exploded")

    agent = Agent(provider=mock_provider, callbacks=[BrokenCallback()])
    result = await agent.run_with_trace("hi")
    assert result.state == RunState.COMPLETED
