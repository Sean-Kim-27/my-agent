"""Tests for MCP subprocess env allowlist enforcement."""

from __future__ import annotations

from agent_framework.mcp.env import build_child_env


def test_allowlist_forwards_only_named_keys() -> None:
    parent = {
        "PATH": "/usr/bin",
        "OPENAI_API_KEY": "sk-secret",
        "HOME": "/home/x",
    }
    child = build_child_env(parent=parent, allowlist=("PATH",))
    assert child["PATH"] == "/usr/bin"
    assert "OPENAI_API_KEY" not in child
    assert "HOME" not in child


def test_empty_allowlist_returns_empty_env() -> None:
    parent = {"OPENAI_API_KEY": "sk-secret", "PATH": "/usr/bin"}
    child = build_child_env(parent=parent, allowlist=())
    assert child == {}


def test_extra_env_overrides_allowlist() -> None:
    parent = {"PATH": "/usr/bin"}
    child = build_child_env(
        parent=parent,
        allowlist=("PATH",),
        extra_env={"CUSTOM_VAR": "value", "PATH": "/opt/bin"},
    )
    assert child["PATH"] == "/opt/bin"
    assert child["CUSTOM_VAR"] == "value"


def test_extra_env_added_even_without_allowlist() -> None:
    child = build_child_env(parent={}, allowlist=(), extra_env={"K": "V"})
    assert child == {"K": "V"}
