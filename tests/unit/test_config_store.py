"""Phase 9.2 versioned config, precedence, and secret-store coverage."""

from __future__ import annotations

import io
import os
from pathlib import Path
from typing import Any

from agent_framework.cli.app import run
from agent_framework.config.schema import FIELD_MAPPINGS, validate_mapping_coverage
from agent_framework.config.secrets import MemorySecretStore
from agent_framework.config.settings import Settings
from agent_framework.config.sources import resolve_settings
from agent_framework.config.store import ConfigPaths, ConfigStore


def _paths(root: Path) -> ConfigPaths:
    return ConfigPaths(
        user_config=root / "user" / "config.toml",
        project_config=root / "project" / "config.toml",
        data_dir=root / "data",
        cache_dir=root / "cache",
    )


def test_all_settings_fields_have_explicit_mapping() -> None:
    validate_mapping_coverage()
    assert set(FIELD_MAPPINGS) == set(Settings.model_fields)


def test_config_store_atomic_write_and_owner_permissions(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    store = ConfigStore(path)
    store.write({"agent": {"provider": "anthropic"}})

    assert store.read()["agent"]["provider"] == "anthropic"
    assert os.stat(path).st_mode & 0o777 == 0o600
    assert list(tmp_path.glob(".config.toml.*")) == []


def test_precedence_cli_env_project_user_default(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    ConfigStore(paths.user_config).write(
        {"agent": {"provider": "anthropic", "default_session": "user"}}
    )
    ConfigStore(paths.project_config).write(
        {"agent": {"provider": "openai_compatible", "default_session": "project"}}
    )

    effective = resolve_settings(
        paths=paths,
        secret_store=MemorySecretStore(),
        environ={"LLM_PROVIDER": "nvidia_nim", "DEFAULT_SESSION_ID": "env"},
        dotenv_path=tmp_path / "missing.env",
        cli_overrides={"default_session_id": "cli"},
    )

    assert effective.settings.llm_provider == "nvidia_nim"
    assert effective.sources["llm_provider"] == "environment"
    assert effective.settings.default_session_id == "cli"
    assert effective.sources["default_session_id"] == "cli"


def test_config_commands_persist_nonsecret_and_reject_secret(
    tmp_path: Path, capsys: Any
) -> None:
    paths = _paths(tmp_path)
    secrets = MemorySecretStore()

    assert run(
        ["config", "set", "agent.default_session", "work"],
        paths=paths,
        secret_store=secrets,
    ) == 0
    assert "work" in paths.user_config.read_text(encoding="utf-8")

    assert run(
        ["config", "set", "provider/openai/api-key", "should-not-store"],
        paths=paths,
        secret_store=secrets,
    ) == 2
    captured = capsys.readouterr()
    assert "should-not-store" not in captured.out + captured.err
    assert "should-not-store" not in paths.user_config.read_text(encoding="utf-8")


def test_auth_stdin_never_echoes_or_writes_secret(tmp_path: Path, capsys: Any) -> None:
    paths = _paths(tmp_path)
    secrets = MemorySecretStore()
    raw_secret = "super-secret-value"

    assert run(
        ["auth", "set", "openai", "--stdin"],
        paths=paths,
        secret_store=secrets,
        stdin=io.StringIO(raw_secret + "\n"),
    ) == 0

    captured = capsys.readouterr()
    assert raw_secret not in captured.out + captured.err
    assert secrets.get("provider/openai/api-key") == raw_secret
    assert not paths.user_config.exists()
