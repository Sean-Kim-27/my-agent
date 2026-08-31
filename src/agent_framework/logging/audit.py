"""Security audit logger — separate from the application logger.

The application logger (``agent_framework.*``) is optimized for developer
diagnostics. Audit records must survive log level changes, must not be
polluted by unrelated framework noise, and must always mask secrets. This
module provides a dedicated logger tree (``agent_framework.audit``) that
propagates NOWHERE, so operators can point it at its own sink.
"""

from __future__ import annotations

import json
import logging
import sys
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from agent_framework.logging.logger import mask_secrets


class AuditEventKind(StrEnum):
    TOOL_EXECUTION = "tool_execution"
    APPROVAL = "approval"
    PATH_DENIED = "path_denied"
    BACKEND_DENIED = "backend_denied"
    POLICY_DECISION = "policy_decision"


class AuditEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: AuditEventKind
    tool_name: str | None = None
    actor: str | None = None
    decision: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class AuditLogger:
    """Thin wrapper around a dedicated ``logging.Logger``."""

    def __init__(self, logger: logging.Logger) -> None:
        self._logger = logger

    @property
    def underlying(self) -> logging.Logger:
        return self._logger

    def record(self, event: AuditEvent) -> None:
        payload = event.model_dump(mode="json")
        payload["details"] = {
            key: mask_secrets(str(value)) if isinstance(value, str) else _mask_nested(value)
            for key, value in payload.get("details", {}).items()
        }
        self._logger.info(json.dumps(payload, ensure_ascii=False))


def _mask_nested(value: Any) -> Any:
    if isinstance(value, str):
        return mask_secrets(value)
    if isinstance(value, dict):
        return {k: _mask_nested(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_mask_nested(v) for v in value]
    return value


_AUDIT_NAME = "agent_framework.audit"


def get_audit_logger(
    *,
    handler: logging.Handler | None = None,
    level: int = logging.INFO,
) -> AuditLogger:
    """Return the singleton audit logger, optionally binding a handler."""
    logger = logging.getLogger(_AUDIT_NAME)
    logger.setLevel(level)
    logger.propagate = False

    if handler is not None:
        # Replace prior handlers so tests get a clean sink.
        for existing in list(logger.handlers):
            logger.removeHandler(existing)
        logger.addHandler(handler)
    elif not logger.handlers:
        default = logging.StreamHandler(sys.stdout)
        default.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(default)

    return AuditLogger(logger)
