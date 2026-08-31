"""Environment variable allowlist for MCP subprocess transports.

Secrets like ``OPENAI_API_KEY`` must never leak into an MCP server subprocess
unless the operator has explicitly listed the variable in ``env_allowlist``.
The default behavior is fail-closed: an empty allowlist forwards no host
environment at all.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping


def build_child_env(
    *,
    parent: Mapping[str, str],
    allowlist: Iterable[str],
    extra_env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Compose a child-process environment from an allowlist plus explicit extras.

    - Only variables named in ``allowlist`` are forwarded from ``parent``.
    - ``extra_env`` values are added last and override the allowlisted ones,
      so operators can inject server-specific credentials without opening the
      full host environment.
    """

    allow = set(allowlist)
    child: dict[str, str] = {}
    for key in allow:
        if key in parent:
            child[key] = parent[key]
    if extra_env:
        for key, value in extra_env.items():
            child[key] = value
    return child
