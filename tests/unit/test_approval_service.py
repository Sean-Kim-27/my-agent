"""ApprovalService state machine tests (Phase 4)."""

from __future__ import annotations

import time

import pytest
from pydantic import ValidationError

from agent_framework.execution.approval import (
    ApprovalService,
    ApprovalState,
    ApprovalStatus,
)


def test_approval_default_pending() -> None:
    service = ApprovalService(default_ttl_seconds=60)
    request = service.request(
        tool_name="run_shell",
        arguments={"argv": ["ls"]},
        actor="user:sean",
    )
    assert request.status is ApprovalStatus.PENDING
    fetched = service.get(request.id)
    assert fetched is not None
    assert fetched.status is ApprovalStatus.PENDING


def test_approve_moves_to_approved() -> None:
    service = ApprovalService(default_ttl_seconds=60)
    req = service.request(
        tool_name="run_shell", arguments={"argv": ["ls"]}, actor="a"
    )
    service.approve(req.id, approver="user:admin")
    state = service.get(req.id)
    assert state is not None
    assert state.status is ApprovalStatus.APPROVED
    assert state.approver == "user:admin"


def test_reject_moves_to_rejected() -> None:
    service = ApprovalService(default_ttl_seconds=60)
    req = service.request(
        tool_name="run_shell", arguments={"argv": ["rm"]}, actor="a"
    )
    service.reject(req.id, approver="user:admin", reason="dangerous")
    state = service.get(req.id)
    assert state is not None
    assert state.status is ApprovalStatus.REJECTED
    assert state.reason == "dangerous"


def test_expired_after_ttl() -> None:
    service = ApprovalService(default_ttl_seconds=0.05, clock=time.time)
    req = service.request(
        tool_name="run_shell", arguments={"argv": ["ls"]}, actor="a"
    )
    time.sleep(0.1)
    state = service.get(req.id)
    assert state is not None
    assert state.status is ApprovalStatus.EXPIRED


def test_argument_bound_check_matches() -> None:
    service = ApprovalService(default_ttl_seconds=60)
    req = service.request(
        tool_name="run_shell", arguments={"argv": ["ls", "-la"]}, actor="a"
    )
    service.approve(req.id, approver="user:admin")

    decision = service.check(
        tool_name="run_shell",
        arguments={"argv": ["ls", "-la"]},
        actor="a",
    )
    assert decision.status is ApprovalStatus.APPROVED
    assert decision.state is not None
    assert decision.state.id == req.id


def test_argument_bound_check_rejects_when_args_change() -> None:
    service = ApprovalService(default_ttl_seconds=60)
    req = service.request(
        tool_name="run_shell", arguments={"argv": ["ls", "-la"]}, actor="a"
    )
    service.approve(req.id, approver="user:admin")

    # Different args must NOT reuse the approval.
    decision = service.check(
        tool_name="run_shell",
        arguments={"argv": ["rm", "-rf", "/"]},
        actor="a",
    )
    assert decision.status is ApprovalStatus.PENDING
    assert decision.state is None


def test_rejected_approvals_cannot_be_reapproved() -> None:
    service = ApprovalService(default_ttl_seconds=60)
    req = service.request(
        tool_name="run_shell", arguments={"argv": ["ls"]}, actor="a"
    )
    service.reject(req.id, approver="admin")
    with pytest.raises(ValueError):
        service.approve(req.id, approver="admin")


def test_state_is_immutable_snapshot() -> None:
    service = ApprovalService(default_ttl_seconds=60)
    req = service.request(
        tool_name="run_shell", arguments={"argv": ["ls"]}, actor="a"
    )
    assert isinstance(req, ApprovalState)
    # Mutating the snapshot must not affect the service's internal store.
    with pytest.raises(ValidationError):
        req.status = ApprovalStatus.APPROVED  # type: ignore[misc]
