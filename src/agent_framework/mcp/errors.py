"""Exception hierarchy for the MCP integration layer."""

from __future__ import annotations

from agent_framework.exceptions import AgentFrameworkError


class MCPError(AgentFrameworkError):
    """Base error for MCP integration failures."""


class MCPConnectionError(MCPError):
    """Raised when an MCP transport fails to connect or initialize."""


class MCPToolError(MCPError):
    """Raised when an MCP tool invocation fails on the server side."""


class MCPTimeoutError(MCPError):
    """Raised when an MCP call exceeds its configured timeout."""


class MCPProtocolError(MCPError):
    """Raised when the MCP peer returns a malformed or unexpected payload."""
