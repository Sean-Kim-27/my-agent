"""File-oriented built-in tools bound to an :class:`ExecutionBackend`.

Every callable created here closes over a single ``ExecutionBackend``
instance so all filesystem access inherits the backend's safe-root,
allow_writes, and allow_destructive gates. Nothing in this module touches
``open``/``os`` directly.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from agent_framework.execution.backend import (
    ExecutionBackend,
    ExecutionDeniedError,
    FileReadSpec,
    FileWriteSpec,
)
from agent_framework.execution.local import LocalExecutionBackend
from agent_framework.execution.paths import PathSafetyError, resolve_safe_path
from agent_framework.models.tool import ToolRiskLevel
from agent_framework.tools.registry import ToolRegistry


class BuiltinFileToolError(Exception):
    """Raised when a built-in file tool cannot satisfy the request."""


def _safe_root_for(backend: ExecutionBackend) -> Path | None:
    """Best-effort discovery of the backend's safe root for tools that must
    enumerate directories. Returns ``None`` when the backend does not expose it.
    """
    root = getattr(backend, "_safe_root", None)
    if isinstance(root, Path):
        return root
    return None


def register_file_tools(
    registry: ToolRegistry,
    backend: ExecutionBackend,
    *,
    toolset: str = "builtin.file",
    max_list_entries: int = 500,
) -> None:
    """Register list_directory, read_file, write_file, and apply_patch tools."""

    async def list_directory(path: str = ".") -> str:
        """List entries inside a directory under the execution safe root.

        Args:
            path: Directory path relative to the safe root (defaults to root).
        """
        root = _safe_root_for(backend)
        if root is None:
            raise BuiltinFileToolError(
                "list_directory requires a backend that exposes a safe root."
            )
        try:
            resolved = resolve_safe_path(path, safe_root=root)
        except PathSafetyError as exc:
            raise BuiltinFileToolError(str(exc)) from exc
        if not resolved.exists():
            raise BuiltinFileToolError(f"Path does not exist: {path}")
        if not resolved.is_dir():
            raise BuiltinFileToolError(f"Path is not a directory: {path}")

        entries: list[dict[str, object]] = []
        for i, entry in enumerate(sorted(resolved.iterdir(), key=lambda p: p.name)):
            if i >= max_list_entries:
                entries.append({"truncated": True, "remaining": True})
                break
            try:
                stat = entry.stat()
                size = stat.st_size if entry.is_file() else None
            except OSError:
                size = None
            entries.append(
                {
                    "name": entry.name,
                    "type": "dir" if entry.is_dir() else "file",
                    "size": size,
                }
            )
        return json.dumps({"path": path, "entries": entries}, ensure_ascii=False)

    async def read_file(path: str, max_bytes: int | None = None) -> str:
        """Read a text file under the execution safe root.

        Args:
            path: File path relative to the safe root.
            max_bytes: Optional maximum bytes to read (backend cap still applies).
        """
        spec = FileReadSpec(path=path, max_bytes=max_bytes)
        try:
            result = await backend.read_file(spec)
        except ExecutionDeniedError as exc:
            raise BuiltinFileToolError(str(exc)) from exc
        payload = {
            "path": path,
            "total_bytes": result.total_bytes,
            "truncated": result.truncated,
            "content": result.text,
        }
        return json.dumps(payload, ensure_ascii=False)

    async def write_file(path: str, content: str, create_parents: bool = False) -> str:
        """Write text to a file under the execution safe root.

        Args:
            path: File path relative to the safe root.
            content: Text content to write (existing file is overwritten).
            create_parents: When True, create missing parent directories.
        """
        spec = FileWriteSpec(path=path, content=content, create_parents=create_parents)
        try:
            await backend.write_file(spec)
        except ExecutionDeniedError as exc:
            raise BuiltinFileToolError(str(exc)) from exc
        return json.dumps({"path": path, "bytes_written": len(content.encode("utf-8"))})

    async def apply_patch(
        path: str,
        old_text: str,
        new_text: str,
        expected_occurrences: int = 1,
    ) -> str:
        """Apply an exact find/replace edit to a file under the safe root.

        The tool fails when ``old_text`` does not appear exactly
        ``expected_occurrences`` times, so the LLM cannot accidentally
        corrupt files by matching too little context.

        Args:
            path: File path relative to the safe root.
            old_text: Exact substring that must be present in the file.
            new_text: Replacement text.
            expected_occurrences: Required match count (default 1). Use a
                higher number when the edit intentionally replaces many
                occurrences.
        """
        if expected_occurrences < 1:
            raise BuiltinFileToolError("expected_occurrences must be >= 1.")
        if old_text == new_text:
            raise BuiltinFileToolError("old_text and new_text are identical.")

        read = await backend.read_file(FileReadSpec(path=path))
        if read.truncated:
            raise BuiltinFileToolError(
                "Refusing to patch a file that exceeded the backend read cap."
            )
        original = read.text
        actual = original.count(old_text)
        if actual != expected_occurrences:
            raise BuiltinFileToolError(
                f"Expected {expected_occurrences} occurrence(s) of old_text, "
                f"found {actual}."
            )
        patched = original.replace(old_text, new_text)
        try:
            await backend.write_file(
                FileWriteSpec(path=path, content=patched, create_parents=False)
            )
        except ExecutionDeniedError as exc:
            raise BuiltinFileToolError(str(exc)) from exc
        return json.dumps(
            {
                "path": path,
                "replacements": expected_occurrences,
                "bytes_written": len(patched.encode("utf-8")),
            }
        )

    registry.register(
        list_directory,
        name="builtin.file.list_directory",
        toolset=toolset,
        risk_level=ToolRiskLevel.SAFE,
        idempotent=True,
    )
    registry.register(
        read_file,
        name="builtin.file.read_file",
        toolset=toolset,
        risk_level=ToolRiskLevel.SAFE,
        idempotent=True,
    )
    _write_allowed, _destructive_allowed = _write_flags(backend)
    registry.register(
        write_file,
        name="builtin.file.write_file",
        toolset=toolset,
        risk_level=ToolRiskLevel.HIGH if _write_allowed else ToolRiskLevel.DESTRUCTIVE,
        idempotent=False,
    )
    registry.register(
        apply_patch,
        name="builtin.file.apply_patch",
        toolset=toolset,
        risk_level=ToolRiskLevel.HIGH,
        idempotent=False,
    )

    # Silence unused-var warnings for the "not allowed" branch — the risk
    # level itself does not gate execution; the backend does.
    _ = _destructive_allowed
    _ = os  # kept import for future stat-mode extensions


def _write_flags(backend: ExecutionBackend) -> tuple[bool, bool]:
    if isinstance(backend, LocalExecutionBackend):
        cfg = backend._config  # noqa: SLF001 - reading own package internal
        return bool(cfg.allow_writes), bool(cfg.allow_destructive)
    return True, True
