"""Built-in tools for real file, terminal, and web access.

All built-ins are thin adapters over an :class:`ExecutionBackend` so that
safe-root, write/subprocess allowlists, output caps, and audit logging
are enforced regardless of which tool the LLM calls.

The public entry point is :func:`register_builtin_tools`.
"""

from __future__ import annotations

from agent_framework.tools.builtin.files import register_file_tools
from agent_framework.tools.builtin.registry import register_builtin_tools
from agent_framework.tools.builtin.terminal import register_terminal_tools
from agent_framework.tools.builtin.web import (
    DEFAULT_WEB_TIMEOUT,
    WebFetchError,
    WebFetchResult,
    extract_text_from_html,
    register_web_tools,
)

__all__ = [
    "DEFAULT_WEB_TIMEOUT",
    "WebFetchError",
    "WebFetchResult",
    "extract_text_from_html",
    "register_builtin_tools",
    "register_file_tools",
    "register_terminal_tools",
    "register_web_tools",
]
