"""Phase 5 capability tests for the built-in file tools."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from agent_framework.execution.local import LocalExecutionBackend, LocalExecutionConfig
from agent_framework.tools.builtin.files import (
    BuiltinFileToolError,
    register_file_tools,
)
from agent_framework.tools.registry import ToolRegistry


def _make_backend(root: Path, *, allow_writes: bool = False) -> LocalExecutionBackend:
    return LocalExecutionBackend(
        LocalExecutionConfig(safe_root=root, allow_writes=allow_writes)
    )


def _registry_with_files(root: Path, *, allow_writes: bool = False) -> ToolRegistry:
    reg = ToolRegistry()
    register_file_tools(reg, _make_backend(root, allow_writes=allow_writes))
    return reg


def test_list_directory_lists_entries(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("hello")
    (tmp_path / "sub").mkdir()
    reg = _registry_with_files(tmp_path)
    fn = reg.get("builtin.file.list_directory")
    assert fn is not None
    out = json.loads(asyncio.run(fn(path=".")))
    names = {e["name"]: e for e in out["entries"] if "name" in e}
    assert set(names) == {"a.txt", "sub"}
    assert names["sub"]["type"] == "dir"
    assert names["a.txt"]["type"] == "file"


def test_list_directory_rejects_traversal(tmp_path: Path) -> None:
    reg = _registry_with_files(tmp_path)
    fn = reg.get("builtin.file.list_directory")
    assert fn is not None
    with pytest.raises(BuiltinFileToolError):
        asyncio.run(fn(path="../"))


def test_read_file_returns_content(tmp_path: Path) -> None:
    (tmp_path / "note.txt").write_text("data")
    reg = _registry_with_files(tmp_path)
    fn = reg.get("builtin.file.read_file")
    assert fn is not None
    payload = json.loads(asyncio.run(fn(path="note.txt")))
    assert payload["content"] == "data"
    assert payload["total_bytes"] == 4
    assert payload["truncated"] is False


def test_write_file_fails_closed_when_backend_disallows_writes(tmp_path: Path) -> None:
    reg = _registry_with_files(tmp_path, allow_writes=False)
    fn = reg.get("builtin.file.write_file")
    assert fn is not None
    with pytest.raises(BuiltinFileToolError):
        asyncio.run(fn(path="x.txt", content="y"))
    assert not (tmp_path / "x.txt").exists()


def test_write_file_writes_when_enabled(tmp_path: Path) -> None:
    reg = _registry_with_files(tmp_path, allow_writes=True)
    fn = reg.get("builtin.file.write_file")
    assert fn is not None
    asyncio.run(fn(path="x.txt", content="hello"))
    assert (tmp_path / "x.txt").read_text() == "hello"


def test_apply_patch_replaces_exact_occurrences(tmp_path: Path) -> None:
    target = tmp_path / "code.py"
    target.write_text("def foo():\n    return 1\n")
    reg = _registry_with_files(tmp_path, allow_writes=True)
    fn = reg.get("builtin.file.apply_patch")
    assert fn is not None
    asyncio.run(
        fn(path="code.py", old_text="return 1", new_text="return 42")
    )
    assert target.read_text() == "def foo():\n    return 42\n"


def test_apply_patch_rejects_ambiguous_match(tmp_path: Path) -> None:
    target = tmp_path / "code.py"
    target.write_text("x = 1\nx = 1\n")
    reg = _registry_with_files(tmp_path, allow_writes=True)
    fn = reg.get("builtin.file.apply_patch")
    assert fn is not None
    with pytest.raises(BuiltinFileToolError):
        asyncio.run(fn(path="code.py", old_text="x = 1", new_text="x = 2"))
    # File unchanged because the tool refused before writing.
    assert target.read_text() == "x = 1\nx = 1\n"


def test_apply_patch_rejects_no_match(tmp_path: Path) -> None:
    target = tmp_path / "code.py"
    target.write_text("nothing here")
    reg = _registry_with_files(tmp_path, allow_writes=True)
    fn = reg.get("builtin.file.apply_patch")
    assert fn is not None
    with pytest.raises(BuiltinFileToolError):
        asyncio.run(fn(path="code.py", old_text="missing", new_text="new"))


def test_apply_patch_denied_when_backend_readonly(tmp_path: Path) -> None:
    target = tmp_path / "code.py"
    target.write_text("hello")
    reg = _registry_with_files(tmp_path, allow_writes=False)
    fn = reg.get("builtin.file.apply_patch")
    assert fn is not None
    with pytest.raises(BuiltinFileToolError):
        asyncio.run(fn(path="code.py", old_text="hello", new_text="hi"))
    assert target.read_text() == "hello"
