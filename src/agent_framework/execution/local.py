"""LocalExecutionBackend: safe-root, allowlist, and subprocess-controlled host execution.

By default this backend refuses:
* writes / destructive filesystem operations,
* subprocess execution,
* forwarding host environment variables to child processes.

Every capability is opt-in via ``LocalExecutionConfig`` so that "not
configured" always fails closed — matching the master plan's Phase 4
security-boundary requirements.
"""

from __future__ import annotations

import asyncio
import os
import signal
import time
from dataclasses import dataclass, field
from pathlib import Path

from agent_framework.execution.backend import (
    CommandResult,
    CommandSpec,
    ExecutionDeniedError,
    FileReadResult,
    FileReadSpec,
    FileWriteSpec,
)
from agent_framework.execution.paths import (
    PathSafetyError,
    open_beneath,
    resolve_safe_path,
    unlink_beneath,
)
from agent_framework.logging.logger import get_logger

logger = get_logger("agent_framework.execution.local")

_DEFAULT_MAX_FILE_BYTES = 1_048_576  # 1 MiB
_DEFAULT_MAX_OUTPUT_BYTES = 65_536


@dataclass(frozen=True)
class LocalExecutionConfig:
    """Configuration knobs for :class:`LocalExecutionBackend`."""

    safe_root: Path
    allow_writes: bool = False
    allow_destructive: bool = False
    allow_subprocess: bool = False
    env_allowlist: tuple[str, ...] = field(default_factory=tuple)
    max_file_bytes: int = _DEFAULT_MAX_FILE_BYTES
    max_output_bytes: int = _DEFAULT_MAX_OUTPUT_BYTES


class LocalExecutionBackend:
    """Direct host-process backend guarded by safe root + allowlists."""

    def __init__(self, config: LocalExecutionConfig) -> None:
        self._config = config
        safe_root = Path(config.safe_root).resolve()
        if not safe_root.exists() or not safe_root.is_dir():
            raise ExecutionDeniedError(
                f"Safe root '{safe_root}' does not exist or is not a directory."
            )
        self._safe_root = safe_root

    # ------------------------------------------------------------ Files

    def _resolve(self, path: str) -> Path:
        try:
            return resolve_safe_path(path, safe_root=self._safe_root)
        except PathSafetyError as exc:
            raise ExecutionDeniedError(str(exc)) from exc

    async def read_file(self, spec: FileReadSpec) -> FileReadResult:
        # Validate first so PathSafetyError surfaces consistently; then use
        # a descriptor-relative open so a concurrent symlink swap between
        # validation and the actual open cannot redirect the read.
        self._resolve(spec.path)
        limit = spec.max_bytes or self._config.max_file_bytes

        def _read() -> FileReadResult:
            try:
                fd = open_beneath(self._safe_root, spec.path, os.O_RDONLY)
            except PathSafetyError as exc:
                raise ExecutionDeniedError(str(exc)) from exc
            try:
                chunks: list[bytes] = []
                total = 0
                truncated = False
                while True:
                    chunk = os.read(fd, 65536)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > limit:
                        overflow = total - limit
                        chunks.append(chunk[: len(chunk) - overflow])
                        # Continue draining to report accurate total_bytes.
                        truncated = True
                        while True:
                            more = os.read(fd, 65536)
                            if not more:
                                break
                            total += len(more)
                        break
                    chunks.append(chunk)
            finally:
                os.close(fd)
            data = b"".join(chunks)
            return FileReadResult(
                text=data.decode(spec.encoding, errors="replace"),
                truncated=truncated,
                total_bytes=total,
            )

        return await asyncio.to_thread(_read)

    async def write_file(self, spec: FileWriteSpec) -> None:
        if not self._config.allow_writes:
            raise ExecutionDeniedError(
                "LocalExecutionBackend was not configured to allow writes."
            )
        self._resolve(spec.path)

        def _write() -> None:
            if spec.create_parents:
                # Parent creation still goes through the pathlib API, but the
                # resolved path is used only to compute the parent directory
                # — the write itself is descriptor-relative below.
                resolved_for_parent = resolve_safe_path(spec.path, safe_root=self._safe_root)
                resolved_for_parent.parent.mkdir(parents=True, exist_ok=True)
            try:
                fd = open_beneath(
                    self._safe_root,
                    spec.path,
                    os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                    mode=0o644,
                )
            except PathSafetyError as exc:
                raise ExecutionDeniedError(str(exc)) from exc
            try:
                data = spec.content.encode(spec.encoding)
                view = memoryview(data)
                while view:
                    written = os.write(fd, view)
                    if written <= 0:
                        break
                    view = view[written:]
            finally:
                os.close(fd)

        await asyncio.to_thread(_write)

    async def delete_file(self, path: str) -> None:
        if not self._config.allow_writes or not self._config.allow_destructive:
            raise ExecutionDeniedError(
                "LocalExecutionBackend was not configured to allow destructive operations."
            )
        self._resolve(path)

        def _delete() -> None:
            try:
                unlink_beneath(self._safe_root, path)
            except PathSafetyError as exc:
                raise ExecutionDeniedError(str(exc)) from exc

        await asyncio.to_thread(_delete)

    # ------------------------------------------------------------ Subprocess

    def _child_env(self, spec_env: dict[str, str]) -> dict[str, str]:
        env: dict[str, str] = {}
        for key in self._config.env_allowlist:
            value = os.environ.get(key)
            if value is not None:
                env[key] = value
        # Explicit per-call env overrides / extends the allowlist without
        # leaking anything from the host process.
        env.update(spec_env)
        return env

    async def run_command(self, spec: CommandSpec) -> CommandResult:
        if not self._config.allow_subprocess:
            raise ExecutionDeniedError(
                "LocalExecutionBackend was not configured to allow subprocess execution."
            )

        cwd = self._resolve(spec.cwd) if spec.cwd else self._safe_root
        if not cwd.is_dir():
            raise ExecutionDeniedError(f"Working directory is not a directory: {cwd}")

        env = self._child_env(spec.env)
        start = time.perf_counter()

        proc = await asyncio.create_subprocess_exec(
            *spec.argv,
            cwd=str(cwd),
            env=env,
            stdin=asyncio.subprocess.PIPE if spec.stdin is not None else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )

        timed_out = False
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(input=spec.stdin.encode() if spec.stdin else None),
                timeout=spec.timeout,
            )
        except TimeoutError:
            timed_out = True
            stdout_bytes, stderr_bytes = await self._terminate(proc)

        duration_ms = (time.perf_counter() - start) * 1000.0
        stdout, out_truncated = self._cap_output(stdout_bytes)
        stderr, err_truncated = self._cap_output(stderr_bytes)
        exit_code = proc.returncode if proc.returncode is not None else -1

        return CommandResult(
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            truncated=out_truncated or err_truncated,
            timed_out=timed_out,
            duration_ms=duration_ms,
        )

    async def _terminate(
        self, proc: asyncio.subprocess.Process
    ) -> tuple[bytes, bytes]:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            return await asyncio.wait_for(proc.communicate(), timeout=1.0)
        except TimeoutError:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                return await proc.communicate()
            except Exception:  # noqa: BLE001 - degrade gracefully
                return b"", b""

    def _cap_output(self, data: bytes) -> tuple[str, bool]:
        limit = self._config.max_output_bytes
        if len(data) <= limit:
            return data.decode("utf-8", errors="replace"), False
        return data[:limit].decode("utf-8", errors="replace"), True
