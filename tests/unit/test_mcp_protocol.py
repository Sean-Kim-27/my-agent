"""Tests for the MCP protocol-version override."""

from __future__ import annotations

import pytest

from agent_framework.mcp.protocol import DEFAULT_PROTOCOL_VERSION, protocol_version


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
