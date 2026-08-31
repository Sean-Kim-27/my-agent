"""Command-approval state machine (Phase 4).

Introduces a durable, argument-bound approval concept on top of the
per-call confirmation callback used by :class:`ToolExecutor`.

Key invariants:
* Approvals move only forward: ``PENDING`` → {``APPROVED``, ``REJECTED``};
  either terminal state can silently promote to ``EXPIRED`` after TTL.
* An approval is bound to (tool_name, actor, canonical arguments). Reusing
  the record with different arguments must NOT be permitted.
* The service returns immutable snapshots so callers can't tamper with
  internal state.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from collections.abc import Callable
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class ApprovalState(BaseModel):
    """Immutable snapshot of a single approval record."""

    model_config = ConfigDict(frozen=True)

    id: str
    tool_name: str
    actor: str
    arguments_fingerprint: str
    status: ApprovalStatus
    created_at: float
    ttl_seconds: float
    approver: str | None = None
    reason: str | None = None


class ApprovalDecision(BaseModel):
    """Result of ``ApprovalService.check`` used by the policy layer."""

    model_config = ConfigDict(frozen=True)

    status: ApprovalStatus
    state: ApprovalState | None = None
    reason: str | None = None


def _fingerprint(arguments: dict[str, Any]) -> str:
    canonical = json.dumps(arguments, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class _Record:
    """Internal mutable representation kept behind the service."""

    __slots__ = (
        "id",
        "tool_name",
        "actor",
        "fingerprint",
        "status",
        "created_at",
        "ttl_seconds",
        "approver",
        "reason",
    )

    def __init__(
        self,
        *,
        record_id: str,
        tool_name: str,
        actor: str,
        fingerprint: str,
        created_at: float,
        ttl_seconds: float,
    ) -> None:
        self.id = record_id
        self.tool_name = tool_name
        self.actor = actor
        self.fingerprint = fingerprint
        self.status = ApprovalStatus.PENDING
        self.created_at = created_at
        self.ttl_seconds = ttl_seconds
        self.approver: str | None = None
        self.reason: str | None = None


class ApprovalService:
    """Manages command approvals with argument-bound state and TTL expiry."""

    def __init__(
        self,
        *,
        default_ttl_seconds: float = 300.0,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._default_ttl = default_ttl_seconds
        self._clock = clock or time.time
        self._records: dict[str, _Record] = {}

    # ------------------------------------------------------------ Requests

    def request(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        actor: str,
        ttl_seconds: float | None = None,
    ) -> ApprovalState:
        record = _Record(
            record_id=uuid.uuid4().hex,
            tool_name=tool_name,
            actor=actor,
            fingerprint=_fingerprint(arguments),
            created_at=self._clock(),
            ttl_seconds=ttl_seconds if ttl_seconds is not None else self._default_ttl,
        )
        self._records[record.id] = record
        return self._snapshot(record)

    def approve(self, approval_id: str, *, approver: str) -> ApprovalState:
        record = self._records.get(approval_id)
        if record is None:
            raise KeyError(f"Unknown approval id: {approval_id}")
        self._age_out(record)
        if record.status is not ApprovalStatus.PENDING:
            raise ValueError(
                f"Cannot approve '{approval_id}': already in status {record.status.value}."
            )
        record.status = ApprovalStatus.APPROVED
        record.approver = approver
        return self._snapshot(record)

    def reject(
        self,
        approval_id: str,
        *,
        approver: str,
        reason: str | None = None,
    ) -> ApprovalState:
        record = self._records.get(approval_id)
        if record is None:
            raise KeyError(f"Unknown approval id: {approval_id}")
        self._age_out(record)
        if record.status is not ApprovalStatus.PENDING:
            raise ValueError(
                f"Cannot reject '{approval_id}': already in status {record.status.value}."
            )
        record.status = ApprovalStatus.REJECTED
        record.approver = approver
        record.reason = reason
        return self._snapshot(record)

    # ------------------------------------------------------------ Queries

    def get(self, approval_id: str) -> ApprovalState | None:
        record = self._records.get(approval_id)
        if record is None:
            return None
        self._age_out(record)
        return self._snapshot(record)

    def check(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        actor: str,
    ) -> ApprovalDecision:
        """Return the effective approval status for the given call."""
        fingerprint = _fingerprint(arguments)
        for record in self._records.values():
            if (
                record.tool_name == tool_name
                and record.actor == actor
                and record.fingerprint == fingerprint
            ):
                self._age_out(record)
                if record.status is ApprovalStatus.APPROVED:
                    return ApprovalDecision(
                        status=ApprovalStatus.APPROVED,
                        state=self._snapshot(record),
                    )
                if record.status is ApprovalStatus.REJECTED:
                    return ApprovalDecision(
                        status=ApprovalStatus.REJECTED,
                        state=self._snapshot(record),
                        reason=record.reason,
                    )
                if record.status is ApprovalStatus.EXPIRED:
                    return ApprovalDecision(
                        status=ApprovalStatus.EXPIRED,
                        state=self._snapshot(record),
                    )
        return ApprovalDecision(status=ApprovalStatus.PENDING)

    # ------------------------------------------------------------ Internal

    def _age_out(self, record: _Record) -> None:
        if record.status is not ApprovalStatus.PENDING and record.status is not ApprovalStatus.APPROVED:
            return
        if self._clock() - record.created_at > record.ttl_seconds:
            record.status = ApprovalStatus.EXPIRED

    def _snapshot(self, record: _Record) -> ApprovalState:
        return ApprovalState(
            id=record.id,
            tool_name=record.tool_name,
            actor=record.actor,
            arguments_fingerprint=record.fingerprint,
            status=record.status,
            created_at=record.created_at,
            ttl_seconds=record.ttl_seconds,
            approver=record.approver,
            reason=record.reason,
        )
