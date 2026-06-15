from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    allowed_user_ids: set[int]
    codex_model: str
    codex_sandbox: str
    codex_workdir: Path
    codex_timeout_seconds: float
    telegram_max_response_chars: int
    telegram_heartbeat_seconds: float
    sqlite_path: Path
    codex_cli_fallback: bool
    cgi_harness_enabled: bool = False
    cgi_harness_endpoint: str = "http://127.0.0.1:8000/api/chat"
    cgi_harness_mode: str = "balanced"
    cgi_harness_timeout_seconds: float = 60.0
    cgi_harness_max_report_chars: int = 8000


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_settings() -> Settings:
    load_dotenv()

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required")

    raw_allowed = os.getenv("TELEGRAM_ALLOWED_USER_IDS", "").strip()
    if not raw_allowed:
        raise RuntimeError("TELEGRAM_ALLOWED_USER_IDS is required")

    allowed_user_ids = {
        int(value.strip())
        for value in raw_allowed.split(",")
        if value.strip()
    }

    return Settings(
        telegram_bot_token=token,
        allowed_user_ids=allowed_user_ids,
        codex_model=os.getenv("CODEX_MODEL", "gpt-5.4").strip(),
        codex_sandbox=os.getenv("CODEX_SANDBOX", "workspace_write").strip(),
        codex_workdir=Path(os.getenv("CODEX_WORKDIR", os.getcwd())).expanduser(),
        codex_timeout_seconds=float(os.getenv("CODEX_TIMEOUT_SECONDS", "300")),
        telegram_max_response_chars=int(os.getenv("TELEGRAM_MAX_RESPONSE_CHARS", "3900")),
        telegram_heartbeat_seconds=float(os.getenv("TELEGRAM_HEARTBEAT_SECONDS", "30")),
        sqlite_path=Path(os.getenv("SQLITE_PATH", "./data/agent.sqlite3")).expanduser(),
        codex_cli_fallback=_env_bool("CODEX_CLI_FALLBACK", False),
        cgi_harness_enabled=_env_bool("CGI_HARNESS_ENABLED", False),
        cgi_harness_endpoint=os.getenv(
            "CGI_HARNESS_ENDPOINT",
            "http://127.0.0.1:8000/api/chat",
        ).strip(),
        cgi_harness_mode=os.getenv("CGI_HARNESS_MODE", "balanced").strip(),
        cgi_harness_timeout_seconds=float(os.getenv("CGI_HARNESS_TIMEOUT_SECONDS", "60")),
        cgi_harness_max_report_chars=int(os.getenv("CGI_HARNESS_MAX_REPORT_CHARS", "8000")),
    )

