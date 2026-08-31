"""Phase 5: verify register_builtin_tools wires all families onto the registry."""

from __future__ import annotations

from pathlib import Path

from agent_framework.execution.local import LocalExecutionBackend, LocalExecutionConfig
from agent_framework.tools.builtin import register_builtin_tools
from agent_framework.tools.registry import ToolRegistry


def test_register_builtin_tools_registers_expected_names(tmp_path: Path) -> None:
    backend = LocalExecutionBackend(LocalExecutionConfig(safe_root=tmp_path))
    reg = ToolRegistry()
    register_builtin_tools(reg, backend)

    tools = set(reg.list_tools())
    for expected in (
        "builtin.file.list_directory",
        "builtin.file.read_file",
        "builtin.file.write_file",
        "builtin.file.apply_patch",
        "builtin.terminal.run_command",
        "builtin.web.http_fetch",
        "builtin.web.http_fetch_text",
    ):
        assert expected in tools, f"missing {expected}"


def test_register_builtin_tools_respects_family_opt_out(tmp_path: Path) -> None:
    backend = LocalExecutionBackend(LocalExecutionConfig(safe_root=tmp_path))
    reg = ToolRegistry()
    register_builtin_tools(reg, backend, include_terminal=False, include_web=False)

    tools = set(reg.list_tools())
    assert "builtin.file.read_file" in tools
    assert "builtin.terminal.run_command" not in tools
    assert "builtin.web.http_fetch" not in tools
