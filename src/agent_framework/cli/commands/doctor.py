"""Read-only installation and effective-settings diagnostics."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_framework.cli.exit_codes import ExitCode
from agent_framework.cli.output import OutputWriter
from agent_framework.config.settings import Settings
from agent_framework.mcp.config import MCPServerConfig


def _provider_has_credentials(settings: Settings, provider: str) -> bool:
    if provider == "openai":
        return bool(settings.openai_api_key)
    if provider == "anthropic":
        return bool(settings.anthropic_api_key)
    if provider == "nvidia_nim":
        return bool(settings.nvidia_nim_api_key)
    if provider == "codex":
        return bool(settings.codex_access_token)
    return True


def run_doctor(settings: Settings, output: OutputWriter) -> ExitCode:
    checks: list[dict[str, Any]] = []
    provider_ok = _provider_has_credentials(settings, settings.llm_provider)
    checks.append(
        {
            "name": "provider_credentials",
            "ok": provider_ok,
            "detail": settings.llm_provider,
        }
    )

    safe_root = Path(settings.execution_safe_root).expanduser()
    checks.append(
        {
            "name": "execution_safe_root",
            "ok": safe_root.exists() and safe_root.is_dir(),
            "detail": str(safe_root),
        }
    )

    if settings.memory_backend == "sqlite":
        db_parent = Path(settings.sqlite_memory_path).expanduser().parent
        checks.append(
            {
                "name": "sqlite_parent",
                "ok": db_parent.exists() and db_parent.is_dir(),
                "detail": str(db_parent),
            }
        )

    if settings.enable_mcp:
        try:
            managed_valid = all(
                MCPServerConfig.model_validate(record).enabled
                or not bool(record.get("enabled", True))
                for record in settings.mcp_servers
            )
            mcp_ready = managed_valid and bool(
                settings.mcp_servers or settings.mcp_config_path
            )
        except ValueError:
            mcp_ready = False
        checks.append(
            {
                "name": "mcp_configuration",
                "ok": mcp_ready,
                "detail": f"{len(settings.mcp_servers)} managed server(s)",
            }
        )

    failed = [check for check in checks if not check["ok"]]
    if output.json_mode:
        output.success({"checks": checks, "healthy": not failed})
    else:
        for check in checks:
            marker = "PASS" if check["ok"] else "FAIL"
            output.success(text=f"[{marker}] {check['name']}: {check['detail']}")
    return ExitCode.OK if not failed else ExitCode.CONFIG


__all__ = ["run_doctor"]
