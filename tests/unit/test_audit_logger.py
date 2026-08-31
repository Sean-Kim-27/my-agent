"""Audit logger tests (Phase 4)."""

from __future__ import annotations

import io
import json
import logging

from agent_framework.logging.audit import (
    AuditEvent,
    AuditEventKind,
    get_audit_logger,
)


def _capture_handler() -> tuple[logging.Handler, io.StringIO]:
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setLevel(logging.INFO)
    return handler, buf


def test_audit_logger_is_separate_from_application_logger() -> None:
    audit = get_audit_logger()
    application = logging.getLogger("agent_framework")
    underlying = audit.underlying
    assert underlying is not application
    assert underlying.name != application.name
    assert underlying.propagate is False


def test_audit_event_serialized_as_json() -> None:
    handler, buf = _capture_handler()
    audit = get_audit_logger(handler=handler)

    audit.record(
        AuditEvent(
            kind=AuditEventKind.TOOL_EXECUTION,
            tool_name="run_shell",
            actor="user:sean",
            decision="allowed",
            details={"argv": ["ls", "-la"]},
        )
    )

    handler.flush()
    line = buf.getvalue().strip().splitlines()[-1]
    payload = json.loads(line)
    assert payload["kind"] == "tool_execution"
    assert payload["tool_name"] == "run_shell"
    assert payload["decision"] == "allowed"


def test_audit_event_masks_secrets_in_details() -> None:
    handler, buf = _capture_handler()
    audit = get_audit_logger(handler=handler)

    audit.record(
        AuditEvent(
            kind=AuditEventKind.APPROVAL,
            tool_name="fetch_url",
            actor="user:sean",
            decision="approved",
            details={
                "url": "https://api.example.com/v1/x?api_key=sk-livesecrettoken1234567890",
                "authorization": "Bearer sk-livesecrettoken1234567890",
            },
        )
    )

    handler.flush()
    line = buf.getvalue().strip().splitlines()[-1]
    assert "sk-livesecrettoken1234567890" not in line
    assert "***MASKED" in line or "***MASKED_KEY***" in line
