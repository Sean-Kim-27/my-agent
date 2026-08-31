"""Fixtures shared across the baseline eval scenarios.

Everything runs against the in-repo ``MockLLMProvider`` from ``tests/conftest.py``
so the evals are fully hermetic (no network) and can be executed inside CI.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from agent_framework.agent.agent import Agent
from agent_framework.memory.in_memory import InMemoryConversationMemory
from agent_framework.memory.session import SessionManager
from agent_framework.tools.registry import ToolRegistry
from tests.conftest import MockLLMProvider

AgentFactory = Callable[..., Agent]


@pytest.fixture
def make_agent() -> AgentFactory:
    """Return a factory that builds fresh agents wired to the mock provider.

    Each invocation returns an isolated ``Agent`` with its own in-memory session
    store so scenarios do not leak state into each other.
    """

    def _factory(
        *,
        provider: MockLLMProvider | None = None,
        tool_registry: ToolRegistry | None = None,
        max_steps: int = 5,
        default_session_id: str = "eval:default",
    ) -> Agent:
        mock = provider or MockLLMProvider()
        return Agent(
            provider=mock,
            session_manager=SessionManager(memory_factory=lambda: InMemoryConversationMemory()),
            tool_registry=tool_registry,
            max_steps=max_steps,
            default_session_id=default_session_id,
        )

    return _factory
