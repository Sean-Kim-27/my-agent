"""Execution boundary primitives: safe paths, backends, and approvals.

Phase 4 introduces the isolation and approval scaffolding that Phase 5's
real file, terminal, and web tools will run through. Nothing here executes
built-in tool code by itself — the modules are the surface that Phase 5
built-in tools will be required to route through.
"""

from agent_framework.execution.approval import (
    ApprovalDecision,
    ApprovalService,
    ApprovalState,
    ApprovalStatus,
)
from agent_framework.execution.backend import (
    CommandResult,
    CommandSpec,
    ExecutionBackend,
    ExecutionDeniedError,
    FileReadResult,
    FileReadSpec,
    FileWriteSpec,
)
from agent_framework.execution.docker import DockerExecutionBackend, DockerExecutionConfig
from agent_framework.execution.local import LocalExecutionBackend, LocalExecutionConfig
from agent_framework.execution.paths import PathSafetyError, resolve_safe_path

__all__ = [
    "ApprovalDecision",
    "ApprovalService",
    "ApprovalState",
    "ApprovalStatus",
    "CommandResult",
    "CommandSpec",
    "DockerExecutionBackend",
    "DockerExecutionConfig",
    "ExecutionBackend",
    "ExecutionDeniedError",
    "FileReadResult",
    "FileReadSpec",
    "FileWriteSpec",
    "LocalExecutionBackend",
    "LocalExecutionConfig",
    "PathSafetyError",
    "resolve_safe_path",
]
