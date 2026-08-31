"""MCP (Model Context Protocol) integration package.

Public API exposes only the small surface the rest of the framework wires up:
configuration, manager, transport contract, and errors. Concrete transports
(stdio subprocess, HTTP) live in sibling modules and can be imported directly.
"""

from __future__ import annotations

from agent_framework.mcp.config import MCPServerConfig
from agent_framework.mcp.errors import (
    MCPConnectionError,
    MCPError,
    MCPProtocolError,
    MCPTimeoutError,
    MCPToolError,
)
from agent_framework.mcp.manager import MCPManager, MCPServerStatus
from agent_framework.mcp.transport import MCPToolInfo, MCPTransport

__all__ = [
    "MCPConnectionError",
    "MCPError",
    "MCPManager",
    "MCPProtocolError",
    "MCPServerConfig",
    "MCPServerStatus",
    "MCPTimeoutError",
    "MCPToolError",
    "MCPToolInfo",
    "MCPTransport",
]
