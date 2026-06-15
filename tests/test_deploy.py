from __future__ import annotations

from pathlib import Path


SERVICE = Path("deploy/personal-codex-agent.service")


def test_systemd_service_has_practical_hardening_options() -> None:
    text = SERVICE.read_text()

    required_lines = {
        "NoNewPrivileges=true",
        "PrivateTmp=true",
        "ProtectSystem=full",
        "ProtectHome=read-only",
        "ReadWritePaths=/home/ubuntu/apps/my-agent /home/ubuntu/agent-workspace /home/ubuntu/.codex",
        "RestrictSUIDSGID=true",
        "LockPersonality=true",
        "MemoryDenyWriteExecute=true",
        "SystemCallArchitectures=native",
    }

    missing = [line for line in sorted(required_lines) if line not in text]
    assert missing == []


def test_systemd_service_limits_restart_spam() -> None:
    text = SERVICE.read_text()

    assert "StartLimitIntervalSec=300" in text
    assert "StartLimitBurst=5" in text
