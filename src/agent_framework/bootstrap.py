"""Shared bootstrap helpers for wiring up the Agent, tools, and providers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent_framework.agent.agent import Agent
from agent_framework.config.secrets import SecretStore
from agent_framework.config.settings import AgentConfig, Settings
from agent_framework.execution.approval import ApprovalService
from agent_framework.execution.backend import ExecutionBackend
from agent_framework.execution.docker import DockerExecutionBackend, DockerExecutionConfig
from agent_framework.execution.local import LocalExecutionBackend, LocalExecutionConfig
from agent_framework.llm.base import LLMProvider
from agent_framework.llm.factory import create_provider_runtime
from agent_framework.llm.runtime import ProviderRuntime
from agent_framework.mcp.config import MCPServerConfig
from agent_framework.mcp.http import HttpMCPTransport
from agent_framework.mcp.manager import MCPManager
from agent_framework.mcp.stdio import StdioSubprocessTransport
from agent_framework.mcp.transport import MCPTransport
from agent_framework.memory.context import (
    ContextManager,
    SummarizingContextManager,
    TokenTrimmingContextManager,
)
from agent_framework.memory.in_memory import InMemoryConversationMemory
from agent_framework.memory.session import MemoryFactory, SessionManager
from agent_framework.memory.sqlite import sqlite_memory_factory
from agent_framework.tools.builtin import register_builtin_tools
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


def build_execution_backend(settings: Settings) -> ExecutionBackend:
    """Instantiate the execution backend selected by the current settings."""
    safe_root = Path(settings.execution_safe_root).resolve()
    if settings.execution_backend == "docker":
        return DockerExecutionBackend(
            DockerExecutionConfig(
                image=settings.execution_docker_image,
                safe_root=safe_root,
                env_allowlist=tuple(settings.execution_env_allowlist),
                max_output_bytes=settings.execution_max_output_bytes,
            )
        )
    return LocalExecutionBackend(
        LocalExecutionConfig(
            safe_root=safe_root,
            allow_writes=settings.execution_allow_writes,
            allow_destructive=settings.execution_allow_destructive,
            allow_subprocess=settings.execution_allow_subprocess,
            env_allowlist=tuple(settings.execution_env_allowlist),
            max_file_bytes=settings.execution_max_file_bytes,
            max_output_bytes=settings.execution_max_output_bytes,
        )
    )


def build_approval_service(settings: Settings) -> ApprovalService:
    """Instantiate the command-approval service using current settings."""
    return ApprovalService(default_ttl_seconds=settings.approval_default_ttl_seconds)


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


def _resolve_provider_context_window(provider: LLMProvider) -> int | None:
    """Return a conservative context window across a provider fallback chain."""
    if isinstance(provider, ProviderRuntime):
        windows = [
            concrete.capabilities.context_window
            for concrete in provider.providers
            if concrete.capabilities.context_window
        ]
        return min(windows) if windows else None
    return provider.capabilities.context_window


def build_context_manager(
    settings: Settings,
    provider: LLMProvider,
) -> ContextManager | None:
    """Construct a ContextManager consistent with settings and the active provider window."""
    if not settings.context_manager_enabled:
        return None

    provider_window = _resolve_provider_context_window(provider)
    raw_budget = provider_window or settings.context_max_tokens
    if raw_budget is None or raw_budget <= 0:
        # Neither the provider nor settings gave us a concrete budget; skip the
        # manager rather than guessing a value that could truncate real work.
        return None

    usable = int(raw_budget * (1.0 - settings.context_headroom_ratio))
    if usable <= 0:
        usable = raw_budget

    if settings.context_strategy == "summarizing":
        return SummarizingContextManager(
            max_tokens=usable,
            summarizer=provider,
            summary_max_tokens=settings.context_summary_max_tokens,
        )
    return TokenTrimmingContextManager(max_tokens=usable)


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

    provider = create_provider_runtime(
        settings=settings,
        provider_name=provider_name or settings.llm_provider,
        **provider_overrides,
    )
    if isinstance(provider, ProviderRuntime):
        for concrete_provider in provider.providers:
            concrete_provider.max_retries = config.max_retries
    else:
        provider.max_retries = config.max_retries

    session_manager = SessionManager(memory_factory=build_memory_factory(settings))
    tool_registry = ToolRegistry()
    register_default_tools(tool_registry)
    if settings.enable_builtin_tools:
        backend = build_execution_backend(settings)
        register_builtin_tools(
            tool_registry,
            backend,
            include_files=settings.builtin_tools_include_files,
            include_terminal=settings.builtin_tools_include_terminal,
            include_web=settings.builtin_tools_include_web,
        )
    tool_executor = ToolExecutor(
        tool_registry,
        default_timeout=config.tool_timeout,
        approval_service=build_approval_service(settings),
    )

    context_manager = build_context_manager(settings, provider)

    agent = Agent(
        provider=provider,
        session_manager=session_manager,
        tool_registry=tool_registry,
        tool_executor=tool_executor,
        system_prompt=system_prompt or settings.agent_system_prompt,
        default_session_id=default_session_id or settings.default_session_id,
        max_steps=config.max_steps,
        context_manager=context_manager,
    )

    return agent, tool_registry, session_manager


def load_mcp_server_configs(path: str | Path) -> list[MCPServerConfig]:
    """Load MCP server configs from a JSON file.

    The file must contain a JSON array of objects, each parseable by
    ``MCPServerConfig``. Invalid entries fail loudly rather than being skipped.
    """
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"MCP config at {path} must be a JSON array")
    return [MCPServerConfig.model_validate(entry) for entry in raw]


def _resolve_secret_refs(
    plain: dict[str, str],
    refs: dict[str, str],
    secret_store: SecretStore | None,
) -> dict[str, str]:
    resolved = dict(plain)
    for target, reference in refs.items():
        if secret_store is None:
            raise ValueError(f"MCP secret reference '{reference}' has no secret backend")
        value = secret_store.get(reference)
        if value is None:
            raise ValueError(f"MCP secret reference '{reference}' is not configured")
        resolved[target] = value
    return resolved


def _transport_for(
    config: MCPServerConfig,
    secret_store: SecretStore | None = None,
) -> MCPTransport:
    if config.transport == "stdio":
        assert config.command is not None  # enforced by MCPServerConfig validator
        return StdioSubprocessTransport(
            command=config.command,
            env_allowlist=tuple(config.env_allowlist),
            extra_env=_resolve_secret_refs(
                config.extra_env,
                config.extra_env_secret_refs,
                secret_store,
            ),
        )
    assert config.url is not None
    return HttpMCPTransport(
        url=config.url,
        headers=_resolve_secret_refs(
            config.headers,
            config.header_secret_refs,
            secret_store,
        ),
    )


async def bootstrap_mcp_servers(
    *,
    settings: Settings,
    tool_registry: ToolRegistry,
    configs: list[MCPServerConfig] | None = None,
    secret_store: SecretStore | None = None,
) -> MCPManager | None:
    """Wire up configured MCP servers onto an existing ToolRegistry.

    Returns the ``MCPManager`` so the caller can shut it down alongside the
    agent lifecycle, or ``None`` if MCP integration is disabled.
    """
    if not settings.enable_mcp:
        return None

    server_configs = configs
    if server_configs is None and settings.mcp_config_path:
        server_configs = load_mcp_server_configs(settings.mcp_config_path)
    if server_configs is None and settings.mcp_servers:
        server_configs = [
            MCPServerConfig.model_validate(record)
            for record in settings.mcp_servers
            if bool(record.get("enabled", True))
        ]
    if not server_configs:
        return None

    manager = MCPManager(registry=tool_registry)
    try:
        for cfg in server_configs:
            await manager.add_server(
                cfg,
                transport=_transport_for(cfg, secret_store),
            )
        await manager.connect_all()
        return manager
    except BaseException:
        await manager.shutdown()
        raise
