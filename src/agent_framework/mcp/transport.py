"""Transport abstraction for the MCP integration layer.

The MCPManager depends only on this Protocol so tests can provide fake
transports without spawning subprocesses or opening sockets. Concrete
transports (stdio subprocess, streamable HTTP) implement the same contract.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class MCPToolInfo(BaseModel):
    """Metadata for a single tool discovered from an MCP server."""

    name: str = Field(..., min_length=1)
    description: str = Field(default="")
    input_schema: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class MCPTransport(Protocol):
    """Contract every MCP transport must satisfy.

    Lifecycle:
      1. ``connect(timeout)`` — establish the underlying channel.
      2. ``initialize(timeout)`` — perform MCP handshake (protocol version,
         capabilities, notifications/initialized).
      3. ``list_tools()`` — enumerate available tools.
      4. ``call_tool(name, arguments, timeout)`` — invoke a tool.
      5. ``close()`` — release channel and any child processes.
    """

    async def connect(self, timeout: float) -> None: ...

    async def initialize(self, timeout: float) -> None: ...

    async def list_tools(self) -> list[MCPToolInfo]: ...

    async def call_tool(
        self, name: str, arguments: dict[str, Any], timeout: float
    ) -> str: ...

    async def close(self) -> None: ...
