"""Tests for the MCP protocol-version override and negotiation helpers."""

from __future__ import annotations

import pytest

from agent_framework.mcp.errors import MCPProtocolError
from agent_framework.mcp.protocol import (
    DEFAULT_PROTOCOL_VERSION,
    SUPPORTED_PROTOCOL_VERSIONS,
    negotiate_protocol_version,
    protocol_version,
    requires_http_version_header,
)


def test_protocol_version_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MCP_PROTOCOL_VERSION", raising=False)
    assert protocol_version() == DEFAULT_PROTOCOL_VERSION


def test_protocol_version_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCP_PROTOCOL_VERSION", "2025-06-18")
    assert protocol_version() == "2025-06-18"


def test_protocol_version_strips_whitespace(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCP_PROTOCOL_VERSION", "  2025-03-26  ")
    assert protocol_version() == "2025-03-26"


def test_protocol_version_ignores_blank_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MCP_PROTOCOL_VERSION", "   ")
    assert protocol_version() == DEFAULT_PROTOCOL_VERSION


# ---------------------------------------------------------------- Phase 10


@pytest.mark.parametrize("version", SUPPORTED_PROTOCOL_VERSIONS)
def test_negotiate_accepts_every_supported_version(version: str) -> None:
    assert negotiate_protocol_version(version) == version


def test_negotiate_rejects_unsupported_version() -> None:
    with pytest.raises(MCPProtocolError):
        negotiate_protocol_version("1999-01-01")


def test_negotiate_rejects_missing_version() -> None:
    with pytest.raises(MCPProtocolError):
        negotiate_protocol_version(None)


def test_negotiate_rejects_non_string_version() -> None:
    with pytest.raises(MCPProtocolError):
        negotiate_protocol_version(20240101)


def test_negotiate_strips_whitespace() -> None:
    assert negotiate_protocol_version("  2025-03-26  ") == "2025-03-26"


def test_http_header_required_from_2025_03_26() -> None:
    assert requires_http_version_header("2024-11-05") is False
    assert requires_http_version_header("2025-03-26") is True
    assert requires_http_version_header("2025-06-18") is True
