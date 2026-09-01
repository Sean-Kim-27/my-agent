"""Application resource ownership and runtime replacement tests."""

from __future__ import annotations

from typing import Any

import pytest

from agent_framework.agent.agent import Agent
from agent_framework.config.settings import Settings
from agent_framework.lifecycle import ApplicationLifecycle, replace_agent_provider
from agent_framework.memory.session import SessionManager
from agent_framework.tools.registry import ToolRegistry
from tests.conftest import MockLLMProvider


class ClosableProvider(MockLLMProvider):
    def __init__(self, name: str = "closable") -> None:
        super().__init__(name=name)
        self.closed = False

    async def close(self) -> None:
        self.closed = True


async def test_lifecycle_closes_provider_on_normal_exit(monkeypatch: Any) -> None:
    provider = ClosableProvider()
    agent = Agent(provider=provider)
    registry = ToolRegistry()
    sessions = SessionManager()

    monkeypatch.setattr(
        "agent_framework.lifecycle.build_agent",
        lambda **_: (agent, registry, sessions),
    )
    monkeypatch.setattr(
        "agent_framework.lifecycle.bootstrap_mcp_servers",
        _return_none,
    )

    async with ApplicationLifecycle(Settings(_env_file=None)) as resources:
        assert resources.agent is agent

    assert provider.closed is True


async def _return_none(**_: Any) -> None:
    return None


async def _raise_startup(**_: Any) -> None:
    raise RuntimeError("MCP failed")


async def test_lifecycle_closes_provider_when_mcp_startup_fails(monkeypatch: Any) -> None:
    provider = ClosableProvider()
    monkeypatch.setattr(
        "agent_framework.lifecycle.build_agent",
        lambda **_: (Agent(provider=provider), ToolRegistry(), SessionManager()),
    )
    monkeypatch.setattr(
        "agent_framework.lifecycle.bootstrap_mcp_servers",
        _raise_startup,
    )

    with pytest.raises(RuntimeError, match="MCP failed"):
        async with ApplicationLifecycle(Settings(_env_file=None)):
            pass

    assert provider.closed is True


async def test_provider_switch_rebuilds_context_and_closes_previous(monkeypatch: Any) -> None:
    previous = ClosableProvider("previous")
    replacement = ClosableProvider("replacement")
    context_marker = object()
    agent = Agent(provider=previous)

    monkeypatch.setattr(
        "agent_framework.lifecycle.create_provider_runtime",
        lambda *_args, **_kwargs: replacement,
    )
    monkeypatch.setattr(
        "agent_framework.lifecycle.build_context_manager",
        lambda *_args, **_kwargs: context_marker,
    )

    await replace_agent_provider(agent, Settings(_env_file=None), "anthropic")

    assert agent.provider is replacement
    assert agent.context_manager is context_marker
    assert previous.closed is True
