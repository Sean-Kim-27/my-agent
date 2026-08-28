"""Unit tests for ToolExecutor."""

import asyncio

import pytest
from pydantic import BaseModel

from agent_framework.models.tool import ToolCall
from agent_framework.tools.executor import ToolExecutor
from agent_framework.tools.registry import ToolRegistry


class CalculationResult(BaseModel):
    operation: str
    result: float


def multiply_sync(x: float, y: float) -> CalculationResult:
    """Synchronous multiplication returning a Pydantic model."""
    return CalculationResult(operation="multiplication", result=x * y)


async def slow_async_op(delay: float) -> str:
    """Simulate slow async operation."""
    await asyncio.sleep(delay)
    return "completed"


def failing_func() -> str:
    """Function that raises an exception."""
    raise ValueError("Something went wrong inside the tool!")


@pytest.mark.asyncio
async def test_tool_executor_sync_function() -> None:
    """Test executing a synchronous function and serializing Pydantic output."""
    registry = ToolRegistry()
    registry.register(multiply_sync)
    executor = ToolExecutor(registry=registry)

    call = ToolCall(id="call_1", name="multiply_sync", arguments={"x": 3.0, "y": 4.0})
    result = await executor.execute(call)

    assert result.is_error is False
    assert result.tool_call_id == "call_1"
    assert "multiplication" in result.content
    assert "12.0" in result.content


@pytest.mark.asyncio
async def test_tool_executor_json_string_arguments() -> None:
    """Test arguments passed as JSON string instead of dict."""
    registry = ToolRegistry()
    registry.register(multiply_sync)
    executor = ToolExecutor(registry=registry)

    call = ToolCall(id="call_2", name="multiply_sync", arguments='{"x": 5, "y": 6}')
    result = await executor.execute(call)

    assert result.is_error is False
    assert "30" in result.content


@pytest.mark.asyncio
async def test_tool_executor_tool_not_found() -> None:
    """Test executing an unregistered tool returns an error result without crashing."""
    registry = ToolRegistry()
    executor = ToolExecutor(registry=registry)

    call = ToolCall(id="call_99", name="unknown_tool", arguments={})
    result = await executor.execute(call)

    assert result.is_error is True
    assert "not registered" in result.content


@pytest.mark.asyncio
async def test_tool_executor_timeout() -> None:
    """Test timeout enforcement during tool execution."""
    registry = ToolRegistry()
    registry.register(slow_async_op)
    executor = ToolExecutor(registry=registry, default_timeout=0.1)

    call = ToolCall(id="call_slow", name="slow_async_op", arguments={"delay": 0.5})
    result = await executor.execute(call)

    assert result.is_error is True
    assert "timed out" in result.content


@pytest.mark.asyncio
async def test_tool_executor_exception_handling() -> None:
    """Test error containment when a tool raises an unhandled exception."""
    registry = ToolRegistry()
    registry.register(failing_func)
    executor = ToolExecutor(registry=registry)

    call = ToolCall(id="call_fail", name="failing_func", arguments={})
    result = await executor.execute(call)

    assert result.is_error is True
    assert "ValueError" in result.content
    assert "Something went wrong inside the tool!" in result.content


@pytest.mark.asyncio
async def test_tool_executor_concurrent_execution() -> None:
    """Test execute_all running multiple tool calls concurrently."""
    registry = ToolRegistry()
    registry.register(multiply_sync)

    executor = ToolExecutor(registry=registry)
    calls = [
        ToolCall(id="c1", name="multiply_sync", arguments={"x": 2, "y": 3}),
        ToolCall(id="c2", name="multiply_sync", arguments={"x": 10, "y": 10}),
    ]

    results = await executor.execute_all(calls)
    assert len(results) == 2
    assert results[0].is_error is False
    assert "6" in results[0].content
    assert results[1].is_error is False
    assert "100" in results[1].content
