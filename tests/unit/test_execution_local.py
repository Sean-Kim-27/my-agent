"""LocalExecutionBackend capability tests (Phase 4)."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

from agent_framework.execution.backend import (
    CommandSpec,
    ExecutionDeniedError,
    FileReadSpec,
    FileWriteSpec,
)
from agent_framework.execution.local import LocalExecutionBackend, LocalExecutionConfig

# --------------------------------------------------------------------- Files


def test_local_backend_read_within_safe_root(tmp_path: Path) -> None:
    (tmp_path / "hello.txt").write_text("hi")
    backend = LocalExecutionBackend(LocalExecutionConfig(safe_root=tmp_path))
    result = asyncio.run(backend.read_file(FileReadSpec(path="hello.txt")))
    assert result.text == "hi"


def test_local_backend_read_rejects_traversal(tmp_path: Path) -> None:
    backend = LocalExecutionBackend(LocalExecutionConfig(safe_root=tmp_path))
    with pytest.raises(ExecutionDeniedError):
        asyncio.run(backend.read_file(FileReadSpec(path="../etc/passwd")))


def test_local_backend_denies_writes_by_default(tmp_path: Path) -> None:
    backend = LocalExecutionBackend(LocalExecutionConfig(safe_root=tmp_path))
    with pytest.raises(ExecutionDeniedError):
        asyncio.run(
            backend.write_file(FileWriteSpec(path="new.txt", content="x"))
        )


def test_local_backend_allows_writes_when_enabled(tmp_path: Path) -> None:
    backend = LocalExecutionBackend(
        LocalExecutionConfig(safe_root=tmp_path, allow_writes=True)
    )
    asyncio.run(backend.write_file(FileWriteSpec(path="new.txt", content="x")))
    assert (tmp_path / "new.txt").read_text() == "x"


def test_local_backend_denies_destructive_by_default(tmp_path: Path) -> None:
    (tmp_path / "victim.txt").write_text("x")
    backend = LocalExecutionBackend(
        LocalExecutionConfig(safe_root=tmp_path, allow_writes=True)
    )
    with pytest.raises(ExecutionDeniedError):
        asyncio.run(backend.delete_file("victim.txt"))
    assert (tmp_path / "victim.txt").exists()


def test_local_backend_allows_destructive_when_enabled(tmp_path: Path) -> None:
    (tmp_path / "victim.txt").write_text("x")
    backend = LocalExecutionBackend(
        LocalExecutionConfig(
            safe_root=tmp_path, allow_writes=True, allow_destructive=True
        )
    )
    asyncio.run(backend.delete_file("victim.txt"))
    assert not (tmp_path / "victim.txt").exists()


# --------------------------------------------------------------------- Subprocess


def test_subprocess_env_allowlist(tmp_path: Path) -> None:
    backend = LocalExecutionBackend(
        LocalExecutionConfig(
            safe_root=tmp_path,
            allow_subprocess=True,
            env_allowlist=("SAFE_FLAG",),
        )
    )
    os.environ["SAFE_FLAG"] = "green"
    os.environ["SECRET_KEY"] = "leak"
    try:
        result = asyncio.run(
            backend.run_command(
                CommandSpec(
                    argv=[
                        sys.executable,
                        "-c",
                        "import os; print(os.environ.get('SAFE_FLAG'), os.environ.get('SECRET_KEY'))",
                    ],
                    timeout=10.0,
                )
            )
        )
    finally:
        os.environ.pop("SAFE_FLAG", None)
        os.environ.pop("SECRET_KEY", None)

    assert result.exit_code == 0
    assert "green" in result.stdout
    assert "None" in result.stdout
    assert "leak" not in result.stdout


def test_subprocess_extra_env_via_spec(tmp_path: Path) -> None:
    backend = LocalExecutionBackend(
        LocalExecutionConfig(safe_root=tmp_path, allow_subprocess=True)
    )
    result = asyncio.run(
        backend.run_command(
            CommandSpec(
                argv=[
                    sys.executable,
                    "-c",
                    "import os; print(os.environ['EXTRA'])",
                ],
                env={"EXTRA": "value"},
                timeout=10.0,
            )
        )
    )
    assert result.exit_code == 0
    assert "value" in result.stdout


def test_subprocess_denied_when_disabled(tmp_path: Path) -> None:
    backend = LocalExecutionBackend(LocalExecutionConfig(safe_root=tmp_path))
    with pytest.raises(ExecutionDeniedError):
        asyncio.run(
            backend.run_command(
                CommandSpec(argv=[sys.executable, "-c", "print('hi')"], timeout=5.0)
            )
        )


def test_subprocess_rejects_shell_string(tmp_path: Path) -> None:
    # Constructing the backend proves the config still works; the assertion is
    # on the spec itself which must refuse shell-string argv to prevent injection.
    LocalExecutionBackend(
        LocalExecutionConfig(safe_root=tmp_path, allow_subprocess=True)
    )
    with pytest.raises(TypeError):
        CommandSpec(argv="echo hi", timeout=5.0)  # type: ignore[arg-type]


def test_subprocess_timeout_kills_process(tmp_path: Path) -> None:
    backend = LocalExecutionBackend(
        LocalExecutionConfig(safe_root=tmp_path, allow_subprocess=True)
    )
    result = asyncio.run(
        backend.run_command(
            CommandSpec(
                argv=[sys.executable, "-c", "import time; time.sleep(5)"],
                timeout=0.3,
            )
        )
    )
    assert result.timed_out is True
    assert result.exit_code != 0


def test_subprocess_output_capped(tmp_path: Path) -> None:
    backend = LocalExecutionBackend(
        LocalExecutionConfig(
            safe_root=tmp_path,
            allow_subprocess=True,
            max_output_bytes=32,
        )
    )
    result = asyncio.run(
        backend.run_command(
            CommandSpec(
                argv=[sys.executable, "-c", "print('A' * 1000)"],
                timeout=5.0,
            )
        )
    )
    assert result.truncated is True
    assert len(result.stdout.encode("utf-8")) <= 32
