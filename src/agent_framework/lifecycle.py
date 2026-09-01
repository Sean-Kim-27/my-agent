"""Application-owned Provider, MCP, Agent, and session lifecycle."""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from types import TracebackType

from agent_framework.agent.agent import Agent
from agent_framework.bootstrap import bootstrap_mcp_servers, build_agent, build_context_manager
from agent_framework.config.secrets import SecretStore
from agent_framework.config.settings import Settings
from agent_framework.llm.factory import create_provider_runtime
from agent_framework.mcp.manager import MCPManager
from agent_framework.memory.session import SessionManager
from agent_framework.tools.registry import ToolRegistry


@dataclass
class RuntimeResources:
    agent: Agent
    tool_registry: ToolRegistry
    session_manager: SessionManager
    mcp_manager: MCPManager | None = None


class ApplicationLifecycle(AbstractAsyncContextManager[RuntimeResources]):
    """Own and deterministically release all resources created for one command."""

    def __init__(
        self,
        settings: Settings,
        *,
        provider_name: str | None = None,
        model: str | None = None,
        system_prompt: str | None = None,
        default_session_id: str | None = None,
        secret_store: SecretStore | None = None,
    ) -> None:
        self.settings = settings
        self.provider_name = provider_name
        self.model = model
        self.system_prompt = system_prompt
        self.default_session_id = default_session_id
        self.secret_store = secret_store
        self.resources: RuntimeResources | None = None

    async def __aenter__(self) -> RuntimeResources:
        agent, registry, sessions = build_agent(
            settings=self.settings,
            provider_name=self.provider_name,
            model=self.model,
            system_prompt=self.system_prompt,
            default_session_id=self.default_session_id,
        )
        try:
            mcp_manager = await bootstrap_mcp_servers(
                settings=self.settings,
                tool_registry=registry,
                secret_store=self.secret_store,
            )
        except BaseException:
            await agent.provider.close()
            raise
        self.resources = RuntimeResources(
            agent=agent,
            tool_registry=registry,
            session_manager=sessions,
            mcp_manager=mcp_manager,
        )
        return self.resources

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        resources = self.resources
        self.resources = None
        if resources is None:
            return
        if resources.mcp_manager is not None:
            await resources.mcp_manager.shutdown()
        await resources.agent.provider.close()


async def replace_agent_provider(
    agent: Agent,
    settings: Settings,
    provider_name: str,
) -> None:
    """Atomically rebuild ProviderRuntime and ContextManager for an active REPL."""
    replacement = create_provider_runtime(settings, provider_name=provider_name)
    replacement_context = build_context_manager(settings, replacement)
    previous = agent.provider
    agent.provider = replacement
    agent.context_manager = replacement_context
    await previous.close()


__all__ = ["ApplicationLifecycle", "RuntimeResources", "replace_agent_provider"]
