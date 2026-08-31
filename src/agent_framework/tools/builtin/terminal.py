"""Terminal (subprocess) built-in tool bound to an :class:`ExecutionBackend`.

``run_command`` never accepts a shell string — arguments must be a list —
so shell injection is impossible even if the model tries. All timeouts,
process-group cleanup, and output caps are inherited from the backend.
"""

from __future__ import annotations

import json

from agent_framework.execution.backend import (
    CommandSpec,
    ExecutionBackend,
    ExecutionDeniedError,
)
from agent_framework.models.tool import ToolRiskLevel
from agent_framework.tools.registry import ToolRegistry


class BuiltinTerminalToolError(Exception):
    """Raised when the terminal tool cannot execute the requested command."""


def register_terminal_tools(
    registry: ToolRegistry,
    backend: ExecutionBackend,
    *,
    toolset: str = "builtin.terminal",
    default_timeout: float = 30.0,
    max_timeout: float = 300.0,
) -> None:
    """Register the run_command tool bound to ``backend``."""

    async def run_command(
        argv: list[str],
        cwd: str | None = None,
        timeout: float | None = None,
    ) -> str:
        """Run a subprocess with an explicit argument list under the safe root.

        The command is passed straight to ``execve``-style spawning; shell
        strings are rejected up front to prevent injection.

        Args:
            argv: Argument list (e.g. ["python", "-V"]).
            cwd: Working directory relative to the safe root.
            timeout: Per-call timeout in seconds (default 30, max 300).
        """
        if not isinstance(argv, list) or not argv:
            raise BuiltinTerminalToolError("argv must be a non-empty list of strings.")
        if any(not isinstance(a, str) for a in argv):
            raise BuiltinTerminalToolError("Every entry in argv must be a string.")

        effective_timeout = default_timeout if timeout is None else float(timeout)
        if effective_timeout <= 0:
            raise BuiltinTerminalToolError("timeout must be positive.")
        if effective_timeout > max_timeout:
            raise BuiltinTerminalToolError(
                f"timeout {effective_timeout}s exceeds the built-in cap of {max_timeout}s."
            )

        spec = CommandSpec(argv=argv, cwd=cwd, timeout=effective_timeout)
        try:
            result = await backend.run_command(spec)
        except ExecutionDeniedError as exc:
            raise BuiltinTerminalToolError(str(exc)) from exc

        payload = {
            "argv": argv,
            "cwd": cwd,
            "exit_code": result.exit_code,
            "duration_ms": result.duration_ms,
            "timed_out": result.timed_out,
            "truncated": result.truncated,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
        return json.dumps(payload, ensure_ascii=False)

    registry.register(
        run_command,
        name="builtin.terminal.run_command",
        toolset=toolset,
        risk_level=ToolRiskLevel.HIGH,
        idempotent=False,
    )
