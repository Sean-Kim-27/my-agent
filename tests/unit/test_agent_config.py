"""Tests for the centralized AgentConfig / bootstrap wiring."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_framework.bootstrap import build_agent, build_memory_factory
from agent_framework.config.settings import AgentConfig, Settings
from agent_framework.memory.in_memory import InMemoryConversationMemory
from agent_framework.memory.sqlite import SQLiteConversationMemory


def _base_settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = {"openai_api_key": "sk-test"}
    defaults.update(overrides)
    return Settings.model_validate(defaults)


def test_agent_config_defaults() -> None:
    config = AgentConfig()
    assert config.max_steps == 10
    assert config.tool_timeout == 30.0
    assert config.max_retries == 3


def test_settings_agent_config_reflects_overrides() -> None:
    settings = _base_settings(
        agent_max_steps=5,
        agent_tool_timeout=12.5,
        agent_max_retries=7,
    )
    config = settings.agent_config()
    assert config.max_steps == 5
    assert config.tool_timeout == 12.5
    assert config.max_retries == 7


def test_build_agent_applies_config_end_to_end() -> None:
    settings = _base_settings(
        llm_provider="openai",
        agent_max_steps=4,
        agent_tool_timeout=8.0,
        agent_max_retries=1,
    )
    agent, _, _ = build_agent(settings=settings)
    assert agent.max_steps == 4
    assert agent.tool_executor is not None
    assert agent.tool_executor.default_timeout == 8.0
    assert agent.provider.max_retries == 1


def test_build_memory_factory_default_is_in_memory() -> None:
    factory = build_memory_factory(_base_settings())
    memory = factory()
    assert isinstance(memory, InMemoryConversationMemory)


def test_build_memory_factory_sqlite(tmp_path: Path) -> None:
    db = tmp_path / "agent.db"
    settings = _base_settings(memory_backend="sqlite", sqlite_memory_path=str(db))
    factory = build_memory_factory(settings)
    memory = factory("session-1")
    assert isinstance(memory, SQLiteConversationMemory)


def test_agent_config_rejects_invalid_values() -> None:
    with pytest.raises(ValueError):
        AgentConfig(max_steps=0)
    with pytest.raises(ValueError):
        AgentConfig(tool_timeout=0)
    with pytest.raises(ValueError):
        AgentConfig(max_retries=-1)
