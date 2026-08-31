"""ExecutionBackend interface and shared data contracts.

The backend is the single choke point between the framework and the host
environment. Every real file, terminal, or web tool that Phase 5 adds must
route through an ``ExecutionBackend`` so that safe-root, environment
allowlist, and approval enforcement are guaranteed regardless of the tool
implementation.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, field_validator

from agent_framework.exceptions import AgentFrameworkError


class ExecutionDeniedError(AgentFrameworkError):
    """Raised when an ExecutionBackend refuses an operation policy-wise."""


class CommandSpec(BaseModel):
    """Argument-list based command specification (never a shell string)."""

    model_config = ConfigDict(frozen=True)

    argv: list[str] = Field(..., min_length=1)
    cwd: str | None = Field(default=None)
    env: dict[str, str] = Field(default_factory=dict)
    timeout: float = Field(default=30.0, gt=0)
    stdin: str | None = Field(default=None)

    @field_validator("argv", mode="before")
    @classmethod
    def _reject_shell_string(cls, value: object) -> object:
        if isinstance(value, str):
            raise TypeError(
                "CommandSpec.argv must be a list of strings, not a shell string; "
                "shell-string commands are forbidden to prevent injection."
            )
        return value


class CommandResult(BaseModel):
    """Result of a subprocess execution."""

    model_config = ConfigDict(frozen=True)

    exit_code: int
    stdout: str
    stderr: str
    truncated: bool = False
    timed_out: bool = False
    duration_ms: float = 0.0


class FileReadSpec(BaseModel):
    """Request to read a file relative to the backend's safe root."""

    model_config = ConfigDict(frozen=True)

    path: str
    max_bytes: int | None = Field(default=None, gt=0)
    encoding: str = "utf-8"


class FileWriteSpec(BaseModel):
    """Request to write a file relative to the backend's safe root."""

    model_config = ConfigDict(frozen=True)

    path: str
    content: str
    encoding: str = "utf-8"
    create_parents: bool = False


class FileReadResult(BaseModel):
    """Result of a file read operation."""

    model_config = ConfigDict(frozen=True)

    text: str
    truncated: bool = False
    total_bytes: int


@runtime_checkable
class ExecutionBackend(Protocol):
    """Interface every execution backend implements."""

    async def read_file(self, spec: FileReadSpec) -> FileReadResult:  # pragma: no cover - protocol
        ...

    async def write_file(self, spec: FileWriteSpec) -> None:  # pragma: no cover - protocol
        ...

    async def delete_file(self, path: str) -> None:  # pragma: no cover - protocol
        ...

    async def run_command(self, spec: CommandSpec) -> CommandResult:  # pragma: no cover - protocol
        ...
