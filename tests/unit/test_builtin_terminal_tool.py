"""Phase 5 capability tests for the built-in terminal tool."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

from agent_framework.execution.local import LocalExecutionBackend, LocalExecutionConfig
from agent_framework.tools.builtin.terminal import (
    BuiltinTerminalToolError,
    register_terminal_tools,
)
from agent_framework.tools.registry import ToolRegistry


def _backend(tmp_path: Path, *, allow_subprocess: bool = True) -> LocalExecutionBackend:
    return LocalExecutionBackend(
        LocalExecutionConfig(
            safe_root=tmp_path,
            allow_subprocess=allow_subprocess,
        )
    )


def test_run_command_executes_argv(tmp_path: Path) -> None:
    reg = ToolRegistry()
    register_terminal_tools(reg, _backend(tmp_path))
    fn = reg.get("builtin.terminal.run_command")
    assert fn is not None
    out = json.loads(asyncio.run(fn(argv=[sys.executable, "-c", "print('hi')"])))
    assert out["exit_code"] == 0
    assert "hi" in out["stdout"]


def test_run_command_fails_closed_when_subprocess_disabled(tmp_path: Path) -> None:
    reg = ToolRegistry()
    register_terminal_tools(reg, _backend(tmp_path, allow_subprocess=False))
    fn = reg.get("builtin.terminal.run_command")
    assert fn is not None
    with pytest.raises(BuiltinTerminalToolError):
        asyncio.run(fn(argv=[sys.executable, "-c", "print('x')"]))


def test_run_command_rejects_shell_string(tmp_path: Path) -> None:
    reg = ToolRegistry()
    register_terminal_tools(reg, _backend(tmp_path))
    fn = reg.get("builtin.terminal.run_command")
    assert fn is not None
    with pytest.raises(BuiltinTerminalToolError):
        asyncio.run(fn(argv="echo pwned"))  # type: ignore[arg-type]


def test_run_command_rejects_empty_argv(tmp_path: Path) -> None:
    reg = ToolRegistry()
    register_terminal_tools(reg, _backend(tmp_path))
    fn = reg.get("builtin.terminal.run_command")
    assert fn is not None
    with pytest.raises(BuiltinTerminalToolError):
        asyncio.run(fn(argv=[]))


def test_run_command_rejects_timeout_over_cap(tmp_path: Path) -> None:
    reg = ToolRegistry()
    register_terminal_tools(reg, _backend(tmp_path), max_timeout=1.0)
    fn = reg.get("builtin.terminal.run_command")
    assert fn is not None
    with pytest.raises(BuiltinTerminalToolError):
        asyncio.run(fn(argv=[sys.executable, "-V"], timeout=5.0))


def test_run_command_reports_timeout(tmp_path: Path) -> None:
    reg = ToolRegistry()
    register_terminal_tools(reg, _backend(tmp_path))
    fn = reg.get("builtin.terminal.run_command")
    assert fn is not None
    out = json.loads(
        asyncio.run(
            fn(
                argv=[sys.executable, "-c", "import time; time.sleep(3)"],
                timeout=0.2,
            )
        )
    )
    assert out["timed_out"] is True
