"""Shared MCP protocol constants and negotiation helpers.

The framework advertises a preferred MCP protocol revision during
``initialize``. Since Phase 10 the transports also parse the version the
server responds with, honor per-revision rules (the ``MCP-Protocol-Version``
header required by 2025-03-26 and later), and reject unsupported revisions
fail-closed rather than silently rolling ahead on incompatible semantics.
"""

from __future__ import annotations

import os
from typing import Final

from agent_framework.mcp.errors import MCPProtocolError

DEFAULT_PROTOCOL_VERSION: Final[str] = "2024-11-05"

#: Protocol revisions this client can safely speak. Ordered oldest → newest.
SUPPORTED_PROTOCOL_VERSIONS: Final[tuple[str, ...]] = (
    "2024-11-05",
    "2025-03-26",
    "2025-06-18",
)

#: Revisions that require every subsequent HTTP request to include the
#: ``MCP-Protocol-Version`` header.
_HTTP_VERSION_HEADER_FROM: Final[str] = "2025-03-26"


def protocol_version() -> str:
    """Return the MCP protocol version to advertise during ``initialize``.

    Resolved at call time so tests and long-running processes pick up an
    updated ``MCP_PROTOCOL_VERSION`` without re-importing the module.
    """

    override = os.getenv("MCP_PROTOCOL_VERSION")
    if override is not None:
        stripped = override.strip()
        if stripped:
            return stripped
    return DEFAULT_PROTOCOL_VERSION


def negotiate_protocol_version(server_version: object) -> str:
    """Validate the ``protocolVersion`` returned by the server.

    Returns the negotiated version string when the server picked one this
    client supports. Raises :class:`MCPProtocolError` for missing or
    unsupported values so callers fail closed rather than proceed with
    incompatible transport rules.
    """

    if server_version is None:
        raise MCPProtocolError(
            "MCP server did not include a protocolVersion in initialize result."
        )
    if not isinstance(server_version, str) or not server_version.strip():
        raise MCPProtocolError(
            f"MCP server returned invalid protocolVersion: {server_version!r}"
        )
    normalized = server_version.strip()
    if normalized not in SUPPORTED_PROTOCOL_VERSIONS:
        raise MCPProtocolError(
            "MCP server advertised unsupported protocolVersion "
            f"{normalized!r}; supported: {SUPPORTED_PROTOCOL_VERSIONS}"
        )
    return normalized


def requires_http_version_header(negotiated_version: str) -> bool:
    """Return True when the HTTP transport must send ``MCP-Protocol-Version``.

    Per MCP revision 2025-03-26 and later, every request after ``initialize``
    must echo the negotiated protocol version so intermediaries can route
    correctly. The 2024-11-05 revision predates the header.
    """

    return negotiated_version >= _HTTP_VERSION_HEADER_FROM
