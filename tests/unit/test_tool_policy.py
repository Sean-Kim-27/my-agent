"""Phase 3 capability tests for the tool policy layer, validation, and toolset controls."""

from __future__ import annotations

import asyncio

import pytest

from agent_framework.models.tool import (
    ToolCall,
    ToolExecutionContext,
    ToolPolicyDecision,
    ToolRiskLevel,
)
from agent_framework.tools.executor import ToolExecutor
from agent_framework.tools.policy import (
    DefaultToolPolicy,
    ToolPolicyError,
)
from agent_framework.tools.registry import ToolRegistry, ToolRegistryError

# ---------------------------------------------------------------------------
# Tool functions used in tests
# ---------------------------------------------------------------------------


def add(a: int, b: int) -> int:
    """Add two integers.

    Args:
        a: First addend.
        b: Second addend.
    """
    return a + b


def delete_row(row_id: int) -> str:
    """Delete a row (non-idempotent stub)."""
    return f"deleted {row_id}"


async def echo(message: str) -> str:
    """Return the input message."""
    return message


def big_output(size: int) -> str:
    """Return a string of ``size`` characters."""
    return "x" * size


# ---------------------------------------------------------------------------
# Registry — duplicate rejection + namespace support
# ---------------------------------------------------------------------------


def test_registry_rejects_duplicate_registration() -> None:
    registry = ToolRegistry()
    registry.register(add)
    with pytest.raises(ToolRegistryError):
        registry.register(add)


def test_registry_allow_replace_when_opted_in() -> None:
    registry = ToolRegistry()
    registry.register(add)
    registry.register(add, replace=True)
    assert registry.has_tool("add")


def test_registry_supports_namespaced_names() -> None:
    registry = ToolRegistry()
    registry.register(add, name="builtin.math.add")
    assert registry.has_tool("builtin.math.add")
    assert registry.get_definition("builtin.math.add").namespace == "builtin.math"


# ---------------------------------------------------------------------------
# Toolset enable / disable + presets
# ---------------------------------------------------------------------------


def test_toolset_disable_hides_tools_from_definitions() -> None:
    registry = ToolRegistry()
    registry.register(add, toolset="math")
    registry.register(delete_row, toolset="db", risk_level=ToolRiskLevel.DESTRUCTIVE)

    registry.disable_toolset("db")

    names = {d.name for d in registry.get_definitions()}
    assert "add" in names
    assert "delete_row" not in names
    assert registry.get_definition("delete_row") is None


def test_toolset_preset_limits_visible_tools() -> None:
    registry = ToolRegistry()
    registry.register(add, toolset="math")
    registry.register(delete_row, toolset="db", risk_level=ToolRiskLevel.DESTRUCTIVE)

    registry.apply_preset(allow_toolsets=("math",))

    names = {d.name for d in registry.get_definitions()}
    assert names == {"add"}


# ---------------------------------------------------------------------------
# Argument validation — fail closed BEFORE invocation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_executor_rejects_unknown_argument() -> None:
    registry = ToolRegistry()
    registry.register(add)
    executor = ToolExecutor(registry)

    call = ToolCall(id="c1", name="add", arguments={"a": 1, "b": 2, "c": 3})
    result = await executor.execute(call)

    assert result.is_error is True
    assert "unknown argument" in result.content.lower()


@pytest.mark.asyncio
async def test_executor_rejects_missing_required_argument() -> None:
    registry = ToolRegistry()
    registry.register(add)
    executor = ToolExecutor(registry)

    call = ToolCall(id="c2", name="add", arguments={"a": 1})
    result = await executor.execute(call)

    assert result.is_error is True
    assert "missing" in result.content.lower()


@pytest.mark.asyncio
async def test_executor_rejects_wrong_type() -> None:
    registry = ToolRegistry()
    registry.register(add)
    executor = ToolExecutor(registry)

    call = ToolCall(id="c3", name="add", arguments={"a": "foo", "b": 2})
    result = await executor.execute(call)

    assert result.is_error is True
    assert "type" in result.content.lower() or "invalid" in result.content.lower()


# ---------------------------------------------------------------------------
# Policy layer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_policy_denies_disabled_toolset() -> None:
    registry = ToolRegistry()
    registry.register(delete_row, toolset="db", risk_level=ToolRiskLevel.DESTRUCTIVE)
    registry.disable_toolset("db")

    policy = DefaultToolPolicy()
    executor = ToolExecutor(registry, policy=policy)

    call = ToolCall(id="c4", name="delete_row", arguments={"row_id": 1})
    ctx = ToolExecutionContext(run_id="run", step=1)
    result = await executor.execute(call, context=ctx)

    assert result.is_error is True
    assert "denied" in result.content.lower() or "not registered" in result.content.lower()


@pytest.mark.asyncio
async def test_policy_requires_confirmation_for_high_risk() -> None:
    registry = ToolRegistry()
    registry.register(
        delete_row,
        risk_level=ToolRiskLevel.HIGH,
    )

    policy = DefaultToolPolicy()
    executor = ToolExecutor(registry, policy=policy)

    approved: list[str] = []

    async def confirm(call: ToolCall) -> bool:
        approved.append(call.name)
        return True

    call = ToolCall(id="c5", name="delete_row", arguments={"row_id": 42})
    ctx = ToolExecutionContext(run_id="run", step=1)
    result = await executor.execute(call, context=ctx, confirm=confirm)

    assert result.is_error is False
    assert approved == ["delete_row"]


@pytest.mark.asyncio
async def test_policy_rejects_high_risk_without_confirm_callback() -> None:
    registry = ToolRegistry()
    registry.register(delete_row, risk_level=ToolRiskLevel.HIGH)

    executor = ToolExecutor(registry, policy=DefaultToolPolicy())

    call = ToolCall(id="c6", name="delete_row", arguments={"row_id": 42})
    ctx = ToolExecutionContext(run_id="run", step=1)
    result = await executor.execute(call, context=ctx)

    assert result.is_error is True
    assert "confirm" in result.content.lower()


def test_policy_decision_is_data_object() -> None:
    decision = ToolPolicyDecision(allow=True, require_confirmation=False)
    assert decision.allow is True
    assert decision.require_confirmation is False


def test_policy_error_is_public() -> None:
    with pytest.raises(ToolPolicyError):
        raise ToolPolicyError("boom")


# ---------------------------------------------------------------------------
# Output cap + artifact split
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_executor_caps_output_and_flags_truncation() -> None:
    registry = ToolRegistry()
    registry.register(big_output, max_output_bytes=64)
    executor = ToolExecutor(registry)

    call = ToolCall(id="c7", name="big_output", arguments={"size": 512})
    result = await executor.execute(call)

    assert result.is_error is False
    assert len(result.content) <= 512
    assert "truncated" in result.content.lower()
    assert result.artifact is not None
    assert result.artifact.total_bytes == 512


# ---------------------------------------------------------------------------
# Non-idempotent tools: no automatic retry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_executor_does_not_auto_retry_non_idempotent() -> None:
    calls = {"n": 0}

    def flaky() -> str:
        calls["n"] += 1
        raise RuntimeError("boom")

    registry = ToolRegistry()
    registry.register(flaky, idempotent=False)
    executor = ToolExecutor(registry, max_retries=3)

    call = ToolCall(id="c8", name="flaky", arguments={})
    result = await executor.execute(call)

    assert result.is_error is True
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_executor_retries_idempotent_tools_up_to_limit() -> None:
    calls = {"n": 0}

    def flaky_idempotent() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("try again")
        return "ok"

    registry = ToolRegistry()
    registry.register(flaky_idempotent, idempotent=True)
    executor = ToolExecutor(registry, max_retries=3)

    call = ToolCall(id="c9", name="flaky_idempotent", arguments={})
    result = await executor.execute(call)

    assert result.is_error is False
    assert calls["n"] == 3


# ---------------------------------------------------------------------------
# Per-tool concurrency
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_per_tool_concurrency_limit_serializes_execution() -> None:
    in_flight = {"cur": 0, "peak": 0}
    lock = asyncio.Lock()

    async def counted() -> str:
        async with lock:
            in_flight["cur"] += 1
            in_flight["peak"] = max(in_flight["peak"], in_flight["cur"])
        await asyncio.sleep(0.02)
        async with lock:
            in_flight["cur"] -= 1
        return "ok"

    registry = ToolRegistry()
    registry.register(counted, max_concurrency=1)
    executor = ToolExecutor(registry)

    calls = [
        ToolCall(id=f"cc-{i}", name="counted", arguments={}) for i in range(5)
    ]
    results = await executor.execute_all(calls)

    assert all(r.is_error is False for r in results)
    assert in_flight["peak"] == 1
