"""Unit tests for ReAct multi-step execution traces, callbacks, and self-correction."""

from typing import Any

import pytest

from agent_framework.agent.agent import Agent
from agent_framework.agent.events import AgentCallbackHandler, ConsoleCallbackHandler
from agent_framework.exceptions import AgentError
from agent_framework.models.message import Message
from agent_framework.models.response import LLMResponse
from agent_framework.models.tool import ToolCall
from agent_framework.tools.registry import ToolRegistry
from tests.conftest import MockLLMProvider


class EventTrackingCallback(AgentCallbackHandler):
    """Test callback collecting all lifecycle events."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    async def on_agent_start(self, session_id: str, prompt: str) -> None:
        self.events.append(("on_agent_start", {"session_id": session_id, "prompt": prompt}))

    async def on_llm_start(self, step: int, messages: list[Message]) -> None:
        self.events.append(("on_llm_start", {"step": step, "message_count": len(messages)}))

    async def on_llm_end(self, step: int, response: LLMResponse) -> None:
        self.events.append(("on_llm_end", {"step": step, "response": response}))

    async def on_thought(self, step: int, thought: str) -> None:
        self.events.append(("on_thought", {"step": step, "thought": thought}))

    async def on_tool_start(self, step: int, tool_name: str, arguments: dict[str, Any] | str) -> None:
        self.events.append(("on_tool_start", {"step": step, "tool_name": tool_name, "arguments": arguments}))

    async def on_tool_end(self, step: int, tool_name: str, result: str, is_error: bool) -> None:
        self.events.append(("on_tool_end", {"step": step, "tool_name": tool_name, "result": result, "is_error": is_error}))

    async def on_agent_finish(self, session_id: str, final_response: LLMResponse, total_steps: int) -> None:
        self.events.append(("on_agent_finish", {"session_id": session_id, "total_steps": total_steps}))

    async def on_agent_error(self, session_id: str, error: Exception) -> None:
        self.events.append(("on_agent_error", {"session_id": session_id, "error": error}))


@pytest.mark.asyncio
async def test_react_callback_and_trace_execution() -> None:
    """Test full callback event lifecycle and AgentRunResult step trajectory."""
    tool_registry = ToolRegistry()

    @tool_registry.tool(description="Multiply two numbers")
    def multiply(a: int, b: int) -> int:
        return a * b

    # Step 1: Model thinks and calls tool
    step1_resp = LLMResponse(
        content="<thought>I need to multiply 6 by 7.</thought>Let me calculate that.",
        tool_calls=[ToolCall(id="call_1", name="multiply", arguments={"a": 6, "b": 7})],
    )
    # Step 2: Model outputs final answer
    step2_resp = LLMResponse(
        content="The result of 6 multiplied by 7 is 42.",
        tool_calls=[],
    )

    mock_provider = MockLLMProvider()
    mock_provider.response_queue = [step1_resp, step2_resp]

    tracker = EventTrackingCallback()
    console_handler = ConsoleCallbackHandler()

    agent = Agent(
        provider=mock_provider,
        tool_registry=tool_registry,
        callbacks=[tracker, console_handler],
    )

    # Run with trace
    result = await agent.run_with_trace("What is 6 * 7?", session_id="test:session")

    assert result.content == "The result of 6 multiplied by 7 is 42."
    assert result.total_steps == 2
    assert result.session_id == "test:session"
    assert len(result.steps) == 2
    assert result.steps[0].thought == "I need to multiply 6 by 7."
    assert len(result.steps[0].tool_calls) == 1
    assert result.steps[0].tool_results[0].content == "42"
    assert result.steps[1].is_final is True

    # Verify callback event stream
    event_names = [e[0] for e in tracker.events]
    assert "on_agent_start" in event_names
    assert "on_llm_start" in event_names
    assert "on_thought" in event_names
    assert "on_tool_start" in event_names
    assert "on_tool_end" in event_names
    assert "on_agent_finish" in event_names


@pytest.mark.asyncio
async def test_react_tool_error_recovery_prompt_injection() -> None:
    """Test autonomous recovery prompt injection when a tool execution fails."""
    tool_registry = ToolRegistry()

    @tool_registry.tool(description="Divide two numbers")
    def divide(a: int, b: int) -> float:
        if b == 0:
            raise ZeroDivisionError("Cannot divide by zero.")
        return a / b

    # Step 1: Model calls tool with invalid argument (division by 0)
    step1_resp = LLMResponse(
        content="Dividing 10 by 0.",
        tool_calls=[ToolCall(id="call_err", name="divide", arguments={"a": 10, "b": 0})],
    )
    # Step 2: Model recovers and gives explanation
    step2_resp = LLMResponse(
        content="Division by zero is undefined mathematically.",
        tool_calls=[],
    )

    mock_provider = MockLLMProvider()
    mock_provider.response_queue = [step1_resp, step2_resp]

    agent = Agent(
        provider=mock_provider,
        tool_registry=tool_registry,
    )

    result = await agent.run_with_trace("Calculate 10 / 0", session_id="test:recovery")
    assert result.total_steps == 2

    # Verify history has recovery prompt recorded
    history = await agent.get_session_history("test:recovery")
    tool_messages = [m for m in history if m.role == "tool"]
    assert len(tool_messages) == 1
    assert tool_messages[0].content is not None
    assert "Please analyze what caused this error" in tool_messages[0].content
    assert tool_messages[0].metadata.get("is_error") is True


@pytest.mark.asyncio
async def test_react_max_steps_error_callback() -> None:
    """Test on_agent_error callback when max_steps is exceeded."""
    tool_registry = ToolRegistry()

    @tool_registry.tool(description="Looping dummy tool")
    def dummy() -> str:
        return "ok"

    # Continually emits tool calls to force max steps limit
    looping_resp = LLMResponse(
        content="Looping...",
        tool_calls=[ToolCall(id="c1", name="dummy", arguments={})],
    )

    mock_provider = MockLLMProvider()
    mock_provider.default_response_text = ""
    mock_provider.response_queue = [looping_resp, looping_resp, looping_resp, looping_resp]

    tracker = EventTrackingCallback()
    agent = Agent(
        provider=mock_provider,
        tool_registry=tool_registry,
        max_steps=2,
        callbacks=[tracker],
    )

    with pytest.raises(AgentError, match="exceeded maximum execution steps"):
        await agent.run("Loop forever")

    event_names = [e[0] for e in tracker.events]
    assert "on_agent_error" in event_names
