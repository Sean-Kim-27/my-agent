"""MCPManager: connect servers, register tools, expose lifecycle to callers."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from agent_framework.logging.logger import get_logger
from agent_framework.mcp.config import MCPServerConfig
from agent_framework.mcp.errors import (
    MCPConnectionError,
    MCPError,
    MCPTimeoutError,
    MCPToolError,
)
from agent_framework.mcp.transport import MCPToolInfo, MCPTransport
from agent_framework.models.tool import ToolDefinition, ToolParameterSchema
from agent_framework.tools.registry import ToolRegistry

logger = get_logger("agent_framework.mcp.manager")


@dataclass
class MCPServerStatus:
    """Runtime status of an MCP server."""

    name: str
    connected: bool = False
    last_error: BaseException | None = None
    registered_tools: list[str] = field(default_factory=list)


@dataclass
class _ServerEntry:
    config: MCPServerConfig
    transport: MCPTransport
    status: MCPServerStatus


class MCPManager:
    """Owns one MCP transport per server and mirrors their tools into ``ToolRegistry``.

    MCP tools go through the same ``ToolExecutor``, ``ToolPolicy``, and
    approval gate as built-in tools — nothing MCP-specific bypasses the
    policy pipeline.
    """

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry
        self._servers: dict[str, _ServerEntry] = {}
        self._shutdown = False

    # ------------------------------------------------------------ Registration

    async def add_server(
        self,
        config: MCPServerConfig,
        *,
        transport: MCPTransport,
    ) -> None:
        """Register a server + transport pair. Connection happens in ``connect_all``."""
        if config.name in self._servers:
            raise ValueError(f"MCP server '{config.name}' already added")
        self._servers[config.name] = _ServerEntry(
            config=config,
            transport=transport,
            status=MCPServerStatus(name=config.name),
        )

    # ------------------------------------------------------------ Lifecycle

    async def connect_all(self) -> None:
        """Connect every registered server. Failures are isolated per server."""
        await asyncio.gather(
            *(self._connect_entry(entry) for entry in self._servers.values()),
            return_exceptions=False,
        )

    async def reconnect(self, name: str) -> None:
        """Reconnect a single server, replacing any stale tool registrations."""
        entry = self._require(name)
        await self._deregister_tools(entry)
        try:
            await entry.transport.close()
        except Exception as exc:  # noqa: BLE001 - transport may be already dead
            logger.debug("Ignoring close() error during reconnect of '%s': %s", name, exc)
        entry.status.connected = False
        entry.status.last_error = None
        await self._connect_entry(entry)

    async def shutdown(self) -> None:
        """Close every server transport and clear tool registrations."""
        self._shutdown = True
        for entry in self._servers.values():
            await self._deregister_tools(entry)
            try:
                await entry.transport.close()
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Error closing MCP server '%s': %s", entry.config.name, exc
                )
            entry.status.connected = False

    def status(self, name: str) -> MCPServerStatus:
        return self._require(name).status

    def all_status(self) -> list[MCPServerStatus]:
        return [entry.status for entry in self._servers.values()]

    # ------------------------------------------------------------ Internals

    def _require(self, name: str) -> _ServerEntry:
        entry = self._servers.get(name)
        if entry is None:
            raise KeyError(f"unknown MCP server '{name}'")
        return entry

    async def _connect_entry(self, entry: _ServerEntry) -> None:
        cfg = entry.config
        try:
            try:
                await asyncio.wait_for(
                    entry.transport.connect(cfg.connect_timeout),
                    timeout=cfg.connect_timeout,
                )
            except TimeoutError as exc:
                raise MCPConnectionError(
                    f"MCP server '{cfg.name}' connect timed out after {cfg.connect_timeout}s"
                ) from exc

            try:
                await asyncio.wait_for(
                    entry.transport.initialize(cfg.init_timeout),
                    timeout=cfg.init_timeout,
                )
            except TimeoutError as exc:
                raise MCPConnectionError(
                    f"MCP server '{cfg.name}' initialize timed out after {cfg.init_timeout}s"
                ) from exc

            tools = await entry.transport.list_tools()
            await self._register_tools(entry, tools)
            entry.status.connected = True
            entry.status.last_error = None
            logger.info(
                "MCP server '%s' connected with %d tool(s)",
                cfg.name,
                len(entry.status.registered_tools),
            )
        except MCPError as exc:
            entry.status.connected = False
            entry.status.last_error = exc
            logger.warning("MCP server '%s' failed to connect: %s", cfg.name, exc)
        except Exception as exc:  # noqa: BLE001 - convert to structured error
            wrapped = MCPConnectionError(
                f"MCP server '{cfg.name}' failed to connect: {exc}"
            )
            entry.status.connected = False
            entry.status.last_error = wrapped
            logger.warning("MCP server '%s' failed to connect: %s", cfg.name, exc)

    async def _register_tools(
        self, entry: _ServerEntry, tools: list[MCPToolInfo]
    ) -> None:
        cfg = entry.config
        namespace = cfg.effective_namespace
        for info in tools:
            if not cfg.is_tool_allowed(info.name):
                logger.info(
                    "MCP tool '%s.%s' skipped by allow/deny policy",
                    namespace,
                    info.name,
                )
                continue
            qualified = f"{namespace}.{info.name}"
            definition = self._make_definition(qualified, info, cfg)
            proxy = self._make_proxy(entry, info.name)
            # Fail-closed: reject re-registration silently by using replace=True
            # only when we own the previous entry. Fresh sessions must never
            # duplicate registrations.
            self._registry.register(
                proxy,
                definition=definition,
                replace=qualified in entry.status.registered_tools,
            )
            if qualified not in entry.status.registered_tools:
                entry.status.registered_tools.append(qualified)

    async def _deregister_tools(self, entry: _ServerEntry) -> None:
        for name in list(entry.status.registered_tools):
            self._registry.unregister(name)
        entry.status.registered_tools.clear()

    def _make_definition(
        self,
        qualified_name: str,
        info: MCPToolInfo,
        cfg: MCPServerConfig,
    ) -> ToolDefinition:
        schema = info.input_schema or {}
        params = ToolParameterSchema(
            type=str(schema.get("type", "object")),
            properties=dict(schema.get("properties", {}) or {}),
            required=list(schema.get("required", []) or []),
            additional_properties=bool(schema.get("additionalProperties", False)),
        )
        return ToolDefinition(
            name=qualified_name,
            description=info.description or f"MCP tool {qualified_name}",
            parameters=params,
            risk_level=cfg.default_risk_level,
            toolset=cfg.effective_namespace,
            idempotent=cfg.default_idempotent,
        )

    def _make_proxy(self, entry: _ServerEntry, remote_name: str) -> Any:
        cfg = entry.config
        transport = entry.transport

        async def _invoke(**kwargs: Any) -> str:
            try:
                return await asyncio.wait_for(
                    transport.call_tool(remote_name, kwargs, cfg.call_timeout),
                    timeout=cfg.call_timeout,
                )
            except TimeoutError as exc:
                raise MCPTimeoutError(
                    f"MCP tool '{cfg.effective_namespace}.{remote_name}' "
                    f"timed out after {cfg.call_timeout}s"
                ) from exc
            except MCPError:
                raise
            except Exception as exc:  # noqa: BLE001
                raise MCPToolError(
                    f"MCP tool '{cfg.effective_namespace}.{remote_name}' failed: {exc}"
                ) from exc

        _invoke.__name__ = remote_name
        _invoke.__doc__ = f"MCP proxy for {cfg.effective_namespace}.{remote_name}"
        return _invoke
