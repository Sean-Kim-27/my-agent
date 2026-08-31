"""DockerExecutionBackend scaffolding.

Phase 4 introduces the *seam* for a container-isolated backend. Wiring
Docker in for real (image pulls, container lifecycle, volume mounts,
network policy) is intentionally deferred to a later phase. The stub
raises ``NotImplementedError`` for every operation so a mis-wired
production configuration fails loudly instead of silently degrading to
host-level execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agent_framework.execution.backend import (
    CommandResult,
    CommandSpec,
    FileReadResult,
    FileReadSpec,
    FileWriteSpec,
)


@dataclass(frozen=True)
class DockerExecutionConfig:
    """Configuration knobs for :class:`DockerExecutionBackend`."""

    image: str
    safe_root: Path
    network: str = "none"
    env_allowlist: tuple[str, ...] = ()
    max_output_bytes: int = 65_536


class DockerExecutionBackend:
    """Container-isolated backend (Phase 4 scaffold).

    See module docstring for the deliberate NotImplementedError policy.
    """

    def __init__(self, config: DockerExecutionConfig) -> None:
        self._config = config

    async def read_file(self, spec: FileReadSpec) -> FileReadResult:
        raise NotImplementedError(
            "DockerExecutionBackend.read_file is not implemented in this phase."
        )

    async def write_file(self, spec: FileWriteSpec) -> None:
        raise NotImplementedError(
            "DockerExecutionBackend.write_file is not implemented in this phase."
        )

    async def delete_file(self, path: str) -> None:
        raise NotImplementedError(
            "DockerExecutionBackend.delete_file is not implemented in this phase."
        )

    async def run_command(self, spec: CommandSpec) -> CommandResult:
        raise NotImplementedError(
            "DockerExecutionBackend.run_command is not implemented in this phase."
        )
