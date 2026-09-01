"""Shared MCP protocol constants.

The framework advertises a fixed MCP protocol revision during ``initialize``.
Third-party servers that require a different revision can override the value
via the ``MCP_PROTOCOL_VERSION`` environment variable without a code change.
Automatic response-based negotiation is a larger effort tracked in
``docs/remaining_risks.md``.
"""

from __future__ import annotations

import os

DEFAULT_PROTOCOL_VERSION = "2024-11-05"


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
