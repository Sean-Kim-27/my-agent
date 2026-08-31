"""Tests for MCPManager: discovery, namespacing, policy propagation, lifecycle."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from agent_framework.mcp.config import MCPServerConfig
from agent_framework.mcp.errors import MCPConnectionError, MCPToolError
from agent_framework.mcp.manager import MCPManager
from agent_framework.mcp.transport import MCPToolInfo, MCPTransport
from agent_framework.models.tool import (
    ToolCall,
    ToolExecutionContext,
    ToolRiskLevel,
)
from agent_framework.tools.executor import ToolExecutor
from agent_framework.tools.registry import ToolRegistry


class FakeTransport(MCPTransport):
    """Deterministic transport for MCPManager tests."""

    def __init__(
        self,
        tools: list[MCPToolInfo] | None = None,
        *,
        fail_on_connect: Exception | None = None,
        fail_on_call: Exception | None = None,
        connect_delay: float = 0.0,
        init_delay: float = 0.0,
        call_delay: float = 0.0,
    ) -> None:
        self._tools = tools or []
        self.fail_on_connect = fail_on_connect
        self.fail_on_call = fail_on_call
        self.connect_delay = connect_delay
        self.init_delay = init_delay
        self.call_delay = call_delay
        self.connect_calls = 0
        self.initialize_calls = 0
        self.close_calls = 0
        self.call_log: list[tuple[str, dict[str, Any]]] = []
        self._connected = False

    async def connect(self, timeout: float) -> None:
        self.connect_calls += 1
        if self.connect_delay:
            await asyncio.sleep(self.connect_delay)
        if self.fail_on_connect is not None:
            raise self.fail_on_connect
        self._connected = True

    async def initialize(self, timeout: float) -> None:
        self.initialize_calls += 1
        if self.init_delay:
            await asyncio.sleep(self.init_delay)

    async def list_tools(self) -> list[MCPToolInfo]:
        return list(self._tools)

    async def call_tool(
        self, name: str, arguments: dict[str, Any], timeout: float
    ) -> str:
        self.call_log.append((name, arguments))
        if self.call_delay:
            await asyncio.sleep(self.call_delay)
        if self.fail_on_call is not None:
            raise self.fail_on_call
        return f"ok:{name}:{sorted(arguments.items())}"

    async def close(self) -> None:
        self.close_calls += 1
        self._connected = False


def _tool_info(name: str = "search") -> MCPToolInfo:
    return MCPToolInfo(
        name=name,
        description=f"tool {name}",
        input_schema={
            "type": "object",
            "properties": {"q": {"type": "string"}},
            "required": ["q"],
        },
    )


@pytest.mark.asyncio
async def test_connect_registers_namespaced_tool() -> None:
    registry = ToolRegistry()
    manager = MCPManager(registry=registry)
    transport = FakeTransport(tools=[_tool_info("search")])
    cfg = MCPServerConfig(name="notes", transport="stdio", command=["srv"])
    await manager.add_server(cfg, transport=transport)
    await manager.connect_all()
    try:
        assert "mcp.notes.search" in registry.list_tools()
        defn = registry.get_definition("mcp.notes.search")
        assert defn is not None
        assert defn.risk_level == ToolRiskLevel.MEDIUM  # default per config
        assert defn.toolset == "mcp.notes"
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_denied_tool_is_not_registered() -> None:
    registry = ToolRegistry()
    manager = MCPManager(registry=registry)
    transport = FakeTransport(tools=[_tool_info("read"), _tool_info("dangerous")])
    cfg = MCPServerConfig(
        name="fs",
        transport="stdio",
        command=["srv"],
        deny_tools=["dangerous"],
    )
    await manager.add_server(cfg, transport=transport)
    await manager.connect_all()
    try:
        names = registry.list_tools()
        assert "mcp.fs.read" in names
        assert "mcp.fs.dangerous" not in names
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_call_tool_dispatches_to_transport() -> None:
    registry = ToolRegistry()
    manager = MCPManager(registry=registry)
    transport = FakeTransport(tools=[_tool_info("search")])
    cfg = MCPServerConfig(name="notes", transport="stdio", command=["srv"])
    await manager.add_server(cfg, transport=transport)
    await manager.connect_all()
    try:
        executor = ToolExecutor(registry)
        result = await executor.execute(
            ToolCall(id="c1", name="mcp.notes.search", arguments={"q": "hello"}),
            context=ToolExecutionContext(run_id="r"),
        )
        assert result.is_error is False
        assert "ok:search" in result.content
        assert transport.call_log == [("search", {"q": "hello"})]
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_shutdown_closes_all_transports() -> None:
    registry = ToolRegistry()
    manager = MCPManager(registry=registry)
    t1 = FakeTransport(tools=[_tool_info("a")])
    t2 = FakeTransport(tools=[_tool_info("b")])
    await manager.add_server(
        MCPServerConfig(name="s1", transport="stdio", command=["srv"]),
        transport=t1,
    )
    await manager.add_server(
        MCPServerConfig(name="s2", transport="stdio", command=["srv"]),
        transport=t2,
    )
    await manager.connect_all()
    await manager.shutdown()
    assert t1.close_calls == 1
    assert t2.close_calls == 1


@pytest.mark.asyncio
async def test_server_failure_isolated_from_others() -> None:
    registry = ToolRegistry()
    manager = MCPManager(registry=registry)
    good = FakeTransport(tools=[_tool_info("good")])
    bad = FakeTransport(fail_on_connect=RuntimeError("boom"))
    await manager.add_server(
        MCPServerConfig(name="good", transport="stdio", command=["srv"]),
        transport=good,
    )
    await manager.add_server(
        MCPServerConfig(name="bad", transport="stdio", command=["srv"]),
        transport=bad,
    )
    await manager.connect_all()
    try:
        assert "mcp.good.good" in registry.list_tools()
        assert manager.status("bad").connected is False
        assert manager.status("bad").last_error is not None
        assert manager.status("good").connected is True
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_reconnect_does_not_duplicate_registration() -> None:
    registry = ToolRegistry()
    manager = MCPManager(registry=registry)
    transport = FakeTransport(tools=[_tool_info("search")])
    cfg = MCPServerConfig(name="notes", transport="stdio", command=["srv"])
    await manager.add_server(cfg, transport=transport)
    await manager.connect_all()
    await manager.reconnect("notes")
    try:
        # Only one entry despite two connect passes.
        names = [n for n in registry.list_tools() if n.startswith("mcp.notes.")]
        assert names == ["mcp.notes.search"]
        assert transport.connect_calls == 2
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_connect_timeout_is_enforced() -> None:
    registry = ToolRegistry()
    manager = MCPManager(registry=registry)
    transport = FakeTransport(tools=[_tool_info("a")], connect_delay=0.5)
    cfg = MCPServerConfig(
        name="slow",
        transport="stdio",
        command=["srv"],
        connect_timeout=0.05,
        init_timeout=1.0,
        call_timeout=1.0,
    )
    await manager.add_server(cfg, transport=transport)
    await manager.connect_all()
    try:
        status = manager.status("slow")
        assert status.connected is False
        assert isinstance(status.last_error, MCPConnectionError)
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_call_timeout_produces_tool_error() -> None:
    registry = ToolRegistry()
    manager = MCPManager(registry=registry)
    transport = FakeTransport(tools=[_tool_info("slow")], call_delay=0.5)
    cfg = MCPServerConfig(
        name="s",
        transport="stdio",
        command=["srv"],
        call_timeout=0.05,
    )
    await manager.add_server(cfg, transport=transport)
    await manager.connect_all()
    try:
        executor = ToolExecutor(registry, default_timeout=2.0)
        result = await executor.execute(
            ToolCall(id="c", name="mcp.s.slow", arguments={"q": "x"}),
            context=ToolExecutionContext(run_id="r"),
        )
        assert result.is_error is True
        assert "timed out" in result.content.lower() or "timeout" in result.content.lower()
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_default_risk_level_from_config_propagates() -> None:
    registry = ToolRegistry()
    manager = MCPManager(registry=registry)
    transport = FakeTransport(tools=[_tool_info("delete")])
    cfg = MCPServerConfig(
        name="danger",
        transport="stdio",
        command=["srv"],
        default_risk_level=ToolRiskLevel.HIGH,
    )
    await manager.add_server(cfg, transport=transport)
    await manager.connect_all()
    try:
        defn = registry.get_definition("mcp.danger.delete")
        assert defn is not None
        assert defn.risk_level == ToolRiskLevel.HIGH
        assert defn.effective_requires_confirmation is True
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_transport_error_becomes_tool_error() -> None:
    registry = ToolRegistry()
    manager = MCPManager(registry=registry)
    transport = FakeTransport(
        tools=[_tool_info("x")],
        fail_on_call=MCPToolError("bad tool call"),
    )
    cfg = MCPServerConfig(name="s", transport="stdio", command=["srv"])
    await manager.add_server(cfg, transport=transport)
    await manager.connect_all()
    try:
        executor = ToolExecutor(registry)
        result = await executor.execute(
            ToolCall(id="c", name="mcp.s.x", arguments={"q": "hi"}),
            context=ToolExecutionContext(run_id="r"),
        )
        assert result.is_error is True
        assert "bad tool call" in result.content
    finally:
        await manager.shutdown()
