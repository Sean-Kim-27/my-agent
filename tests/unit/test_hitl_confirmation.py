"""Tests for the Human-in-the-Loop tool confirmation gate."""

from __future__ import annotations

import pytest

from agent_framework.models.tool import ToolCall
from agent_framework.tools.executor import ToolExecutor
from agent_framework.tools.registry import ToolRegistry


@pytest.fixture()
def registry_with_confirm_tool() -> tuple[ToolRegistry, list[str]]:
    registry = ToolRegistry()
    calls: list[str] = []

    def delete_all(target: str) -> str:
        """Destructive fake tool.
        Args:
            target: What to wipe.
        """
        calls.append(target)
        return f"deleted {target}"

    registry.register(delete_all, requires_confirmation=True)
    return registry, calls


async def test_tool_definition_carries_confirmation_flag(
    registry_with_confirm_tool: tuple[ToolRegistry, list[str]],
) -> None:
    registry, _ = registry_with_confirm_tool
    definition = registry.get_definition("delete_all")
    assert definition is not None
    assert definition.requires_confirmation is True


async def test_executor_rejects_without_confirm_callback(
    registry_with_confirm_tool: tuple[ToolRegistry, list[str]],
) -> None:
    registry, calls = registry_with_confirm_tool
    executor = ToolExecutor(registry)
    result = await executor.execute(
        ToolCall(id="1", name="delete_all", arguments={"target": "prod"}),
    )
    assert result.is_error is True
    assert "requires human confirmation" in result.content
    assert calls == []


async def test_executor_runs_when_confirmation_approved(
    registry_with_confirm_tool: tuple[ToolRegistry, list[str]],
) -> None:
    registry, calls = registry_with_confirm_tool
    executor = ToolExecutor(registry)

    async def approve(_: ToolCall) -> bool:
        return True

    result = await executor.execute(
        ToolCall(id="1", name="delete_all", arguments={"target": "prod"}),
        confirm=approve,
    )
    assert result.is_error is False
    assert result.content == "deleted prod"
    assert calls == ["prod"]


async def test_executor_reports_rejection(
    registry_with_confirm_tool: tuple[ToolRegistry, list[str]],
) -> None:
    registry, calls = registry_with_confirm_tool
    executor = ToolExecutor(registry)

    async def deny(_: ToolCall) -> bool:
        return False

    result = await executor.execute(
        ToolCall(id="1", name="delete_all", arguments={"target": "prod"}),
        confirm=deny,
    )
    assert result.is_error is True
    assert "rejected" in result.content
    assert calls == []


async def test_executor_ignores_confirm_for_safe_tools() -> None:
    registry = ToolRegistry()
    calls: list[str] = []

    def echo(msg: str) -> str:
        """Simple echo tool.
        Args:
            msg: what to echo back.
        """
        calls.append(msg)
        return msg

    registry.register(echo)  # No requires_confirmation flag
    executor = ToolExecutor(registry)

    async def deny(_: ToolCall) -> bool:
        return False

    result = await executor.execute(
        ToolCall(id="1", name="echo", arguments={"msg": "hi"}),
        confirm=deny,
    )
    assert result.is_error is False
    assert calls == ["hi"]
