"""Convenience helper wiring all Phase 5 built-in tools onto a registry."""

from __future__ import annotations

from agent_framework.execution.backend import ExecutionBackend
from agent_framework.tools.builtin.files import register_file_tools
from agent_framework.tools.builtin.terminal import register_terminal_tools
from agent_framework.tools.builtin.web import register_web_tools
from agent_framework.tools.registry import ToolRegistry


def register_builtin_tools(
    registry: ToolRegistry,
    backend: ExecutionBackend,
    *,
    include_files: bool = True,
    include_terminal: bool = True,
    include_web: bool = True,
) -> None:
    """Register the Phase 5 built-in tools on ``registry``.

    Each family can be opted out by the caller (e.g. Discord may want file
    tools but not terminal). All families share the backend so safe-root
    and allowlist enforcement is uniform.
    """
    if include_files:
        register_file_tools(registry, backend)
    if include_terminal:
        register_terminal_tools(registry, backend)
    if include_web:
        register_web_tools(registry)
