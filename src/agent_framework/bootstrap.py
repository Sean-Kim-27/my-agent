"""Shared bootstrap helpers for wiring up the Agent, tools, and providers."""

from __future__ import annotations

from typing import Any

from agent_framework.agent.agent import Agent
from agent_framework.config.settings import AgentConfig, Settings
from agent_framework.llm.factory import create_llm_provider
from agent_framework.memory.in_memory import InMemoryConversationMemory
from agent_framework.memory.session import MemoryFactory, SessionManager
from agent_framework.memory.sqlite import sqlite_memory_factory
from agent_framework.tools.executor import ToolExecutor
from agent_framework.tools.registry import ToolRegistry
from agent_framework.tools.safe_math import safe_eval_math


def register_default_tools(registry: ToolRegistry) -> None:
    """Register the framework's default demo tools onto a ToolRegistry."""

    @registry.tool(description="Get the current date and time in UTC or local timezone.")
    def get_current_time(timezone: str = "UTC") -> str:
        """Get current date and time.
        Args:
            timezone: Target timezone name (e.g. UTC, Asia/Seoul).
        """
        import datetime

        now = datetime.datetime.now(datetime.UTC)
        return f"Current time in {timezone}: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}"

    @registry.tool(description="Safely evaluate a basic mathematical arithmetic expression.")
    def calculate(expression: str) -> str:
        """Evaluate mathematical expression.
        Args:
            expression: Math expression to compute (e.g. '25 * 48 + 12').
        """
        try:
            return f"Result: {safe_eval_math(expression)}"
        except ValueError as exc:
            return f"Error evaluating expression: {exc}"

    @registry.tool(description="Fetch simulated current weather information for a specified city.")
    def get_weather(city: str) -> str:
        """Fetch current weather for a city.
        Args:
            city: City name (e.g. Seoul, Tokyo, New York).
        """
        sample_weather = {
            "seoul": "18°C, Clear Sky, Humidity: 45%",
            "tokyo": "20°C, Partly Cloudy, Humidity: 55%",
            "new york": "15°C, Light Rain, Humidity: 70%",
            "london": "12°C, Overcast, Humidity: 80%",
            "paris": "16°C, Sunny, Humidity: 50%",
        }
        return sample_weather.get(city.lower(), f"Weather in {city}: 21°C, Mild, Clear")


def build_memory_factory(settings: Settings) -> MemoryFactory:
    """Return the ConversationMemory factory implied by the current settings."""
    if settings.memory_backend == "sqlite":
        return sqlite_memory_factory(
            settings.sqlite_memory_path,
            max_messages=settings.memory_max_messages,
        )
    max_messages = settings.memory_max_messages

    def _factory() -> InMemoryConversationMemory:
        return InMemoryConversationMemory(max_messages=max_messages)

    return _factory


def build_agent(
    *,
    settings: Settings,
    provider_name: str | None = None,
    model: str | None = None,
    system_prompt: str | None = None,
    default_session_id: str | None = None,
    agent_config: AgentConfig | None = None,
) -> tuple[Agent, ToolRegistry, SessionManager]:
    """Construct a fully-wired Agent with default tools registered."""
    config = agent_config or settings.agent_config()

    provider_overrides: dict[str, Any] = {}
    if model:
        provider_overrides["model"] = model

    provider = create_llm_provider(
        settings=settings,
        provider_name=provider_name or settings.llm_provider,
        **provider_overrides,
    )
    provider.max_retries = config.max_retries

    session_manager = SessionManager(memory_factory=build_memory_factory(settings))
    tool_registry = ToolRegistry()
    register_default_tools(tool_registry)
    tool_executor = ToolExecutor(tool_registry, default_timeout=config.tool_timeout)

    agent = Agent(
        provider=provider,
        session_manager=session_manager,
        tool_registry=tool_registry,
        tool_executor=tool_executor,
        system_prompt=system_prompt or settings.agent_system_prompt,
        default_session_id=default_session_id or settings.default_session_id,
        max_steps=config.max_steps,
    )

    return agent, tool_registry, session_manager
