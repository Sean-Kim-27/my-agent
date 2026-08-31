"""Tests for MCP server configuration parsing and defaults."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent_framework.mcp.config import MCPServerConfig
from agent_framework.models.tool import ToolRiskLevel


def test_stdio_config_requires_command() -> None:
    with pytest.raises(ValidationError):
        MCPServerConfig(name="local", transport="stdio")


def test_http_config_requires_url() -> None:
    with pytest.raises(ValidationError):
        MCPServerConfig(name="remote", transport="http")


def test_stdio_defaults_namespace_and_timeouts() -> None:
    cfg = MCPServerConfig(name="notes", transport="stdio", command=["node", "server.js"])
    assert cfg.effective_namespace == "mcp.notes"
    assert cfg.namespace is None
    assert cfg.connect_timeout > 0
    assert cfg.init_timeout > 0
    assert cfg.call_timeout > 0
    assert cfg.default_risk_level == ToolRiskLevel.MEDIUM
    assert cfg.env_allowlist == []


def test_explicit_namespace_overrides_default() -> None:
    cfg = MCPServerConfig(
        name="notes",
        transport="stdio",
        command=["srv"],
        namespace="custom.ns",
    )
    assert cfg.effective_namespace == "custom.ns"


def test_deny_wins_over_allow() -> None:
    cfg = MCPServerConfig(
        name="notes",
        transport="stdio",
        command=["srv"],
        allow_tools=["search", "read"],
        deny_tools=["search"],
    )
    assert cfg.is_tool_allowed("read") is True
    assert cfg.is_tool_allowed("search") is False
    assert cfg.is_tool_allowed("write") is False  # not in allowlist


def test_allowlist_none_permits_by_default() -> None:
    cfg = MCPServerConfig(name="notes", transport="stdio", command=["srv"])
    assert cfg.is_tool_allowed("anything") is True


def test_deny_only_blocks_specific_tools() -> None:
    cfg = MCPServerConfig(
        name="notes",
        transport="stdio",
        command=["srv"],
        deny_tools=["dangerous"],
    )
    assert cfg.is_tool_allowed("safe") is True
    assert cfg.is_tool_allowed("dangerous") is False
