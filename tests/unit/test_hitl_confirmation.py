"""Tests for the Human-in-the-Loop tool confirmation gate."""

from __future__ import annotations

import pytest

from agent_framework.agent.agent import Agent
from agent_framework.agent.events import AgentCallbackHandler
from agent_framework.execution.approval import ApprovalService, ApprovalStatus
from agent_framework.models.response import LLMResponse
from agent_framework.models.tool import ToolCall, ToolRiskLevel
from agent_framework.tools.executor import ToolExecutor
from agent_framework.tools.registry import ToolRegistry
from tests.conftest import MockLLMProvider


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


async def test_executor_records_callback_decision_in_approval_service(
    registry_with_confirm_tool: tuple[ToolRegistry, list[str]],
) -> None:
    registry, _ = registry_with_confirm_tool
    approvals = ApprovalService(default_ttl_seconds=60)
    executor = ToolExecutor(registry, approval_service=approvals)

    async def approve(_: ToolCall) -> bool:
        return True

    await executor.execute(
        ToolCall(id="1", name="delete_all", arguments={"target": "prod"}),
        confirm=approve,
    )

    decision = approvals.check(
        tool_name="delete_all",
        arguments={"target": "prod"},
        actor="unknown",
    )
    assert decision.status is ApprovalStatus.APPROVED


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


async def test_agent_without_explicit_confirmation_handler_fails_closed() -> None:
    provider = MockLLMProvider()
    provider.response_queue.extend(
        [
            LLMResponse(
                content=None,
                provider=provider.name,
                model=provider.model,
                tool_calls=[
                    ToolCall(id="danger-1", name="danger", arguments={})
                ],
            ),
            LLMResponse(
                content="not executed",
                provider=provider.name,
                model=provider.model,
            ),
        ]
    )
    registry = ToolRegistry()
    calls: list[str] = []

    def danger() -> str:
        calls.append("called")
        return "done"

    registry.register(danger, risk_level=ToolRiskLevel.HIGH)
    agent = Agent(provider=provider, tool_registry=registry)

    result = await agent.run_with_trace("run it")

    assert result.content == "not executed"
    assert calls == []


async def test_confirmation_prompt_redacts_secret_fields_but_tool_receives_value() -> None:
    provider = MockLLMProvider()
    provider.response_queue.extend(
        [
            LLMResponse(
                content=None,
                provider=provider.name,
                model=provider.model,
                tool_calls=[
                    ToolCall(
                        id="secret-1",
                        name="use_secret",
                        arguments={"api_key": "raw-secret"},
                    )
                ],
            ),
            LLMResponse(content="done", provider=provider.name, model=provider.model),
        ]
    )
    registry = ToolRegistry()
    received: list[str] = []

    def use_secret(api_key: str) -> str:
        received.append(api_key)
        return "ok"

    registry.register(use_secret, risk_level=ToolRiskLevel.HIGH)

    class CaptureApproval(AgentCallbackHandler):
        def __init__(self) -> None:
            self.arguments: object = None

        async def on_tool_confirmation(
            self, step: int, tool_name: str, arguments: object
        ) -> bool:
            self.arguments = arguments
            return True

    handler = CaptureApproval()
    agent = Agent(provider=provider, tool_registry=registry, callbacks=[handler])

    await agent.run_with_trace("use it")

    assert handler.arguments == {"api_key": "***MASKED***"}
    assert received == ["raw-secret"]
