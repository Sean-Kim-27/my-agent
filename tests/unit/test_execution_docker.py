"""DockerExecutionBackend interface tests (Phase 4).

The Docker backend is a stub in Phase 4 — the real image/container lifecycle
is out of scope. We verify that (a) it satisfies the ExecutionBackend Protocol
and (b) it raises a clear NotImplementedError instead of silently falling
through to the Local backend.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from agent_framework.execution.backend import (
    CommandSpec,
    ExecutionBackend,
    FileReadSpec,
    FileWriteSpec,
)
from agent_framework.execution.docker import DockerExecutionBackend, DockerExecutionConfig


def _backend(tmp_path: Path) -> DockerExecutionBackend:
    return DockerExecutionBackend(
        DockerExecutionConfig(image="python:3.12", safe_root=tmp_path)
    )


def test_docker_backend_implements_protocol(tmp_path: Path) -> None:
    backend: ExecutionBackend = _backend(tmp_path)
    assert isinstance(backend, ExecutionBackend)


def test_docker_read_not_implemented(tmp_path: Path) -> None:
    backend = _backend(tmp_path)
    with pytest.raises(NotImplementedError):
        asyncio.run(backend.read_file(FileReadSpec(path="x")))


def test_docker_write_not_implemented(tmp_path: Path) -> None:
    backend = _backend(tmp_path)
    with pytest.raises(NotImplementedError):
        asyncio.run(backend.write_file(FileWriteSpec(path="x", content="y")))


def test_docker_run_not_implemented(tmp_path: Path) -> None:
    backend = _backend(tmp_path)
    with pytest.raises(NotImplementedError):
        asyncio.run(backend.run_command(CommandSpec(argv=["true"])))
