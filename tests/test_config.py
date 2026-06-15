from __future__ import annotations

from pathlib import Path

from personal_codex_agent.config import load_settings


def test_load_settings_reads_codex_timeout_seconds(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "123, 456")
    monkeypatch.setenv("CODEX_TIMEOUT_SECONDS", "45")
    monkeypatch.setenv("TELEGRAM_HEARTBEAT_SECONDS", "12.5")
    monkeypatch.setenv("CODEX_WORKDIR", str(tmp_path))
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "agent.sqlite3"))
    monkeypatch.setenv("CODEX_CLI_FALLBACK", "true")
    monkeypatch.setenv("CGI_HARNESS_ENABLED", "true")
    monkeypatch.setenv("CGI_HARNESS_ENDPOINT", "http://127.0.0.1:8000/api/compare/report")
    monkeypatch.setenv("CGI_HARNESS_MODE", "creative")
    monkeypatch.setenv("CGI_HARNESS_TIMEOUT_SECONDS", "22.5")
    monkeypatch.setenv("CGI_HARNESS_MAX_REPORT_CHARS", "12000")

    settings = load_settings()

    assert settings.codex_timeout_seconds == 45
    assert settings.telegram_heartbeat_seconds == 12.5
    assert settings.allowed_user_ids == {123, 456}
    assert settings.codex_workdir == tmp_path
    assert settings.sqlite_path == tmp_path / "agent.sqlite3"
    assert settings.codex_cli_fallback is True
    assert settings.cgi_harness_enabled is True
    assert settings.cgi_harness_endpoint == "http://127.0.0.1:8000/api/compare/report"
    assert settings.cgi_harness_mode == "creative"
    assert settings.cgi_harness_timeout_seconds == 22.5
    assert settings.cgi_harness_max_report_chars == 12000


def test_load_settings_defaults_cgi_harness_to_chat_endpoint(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "123")
    monkeypatch.setenv("CODEX_WORKDIR", str(tmp_path))
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "agent.sqlite3"))
    monkeypatch.delenv("CGI_HARNESS_ENDPOINT", raising=False)

    settings = load_settings()

    assert settings.cgi_harness_endpoint == "http://127.0.0.1:8000/api/chat"
