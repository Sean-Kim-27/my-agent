"""Legacy dotenv migration, export, and completion tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_framework.cli.app import run
from agent_framework.config.secrets import MemorySecretStore
from agent_framework.config.store import ConfigPaths


def _paths(root: Path) -> ConfigPaths:
    return ConfigPaths(
        user_config=root / "user" / "config.toml",
        project_config=root / "project" / "config.toml",
        data_dir=root / "data",
        cache_dir=root / "cache",
    )


def test_migrate_env_dry_run_is_read_only_and_masks_secret(
    tmp_path: Path, capsys: Any
) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "LLM_PROVIDER=anthropic\nOPENAI_API_KEY=very-secret-value\n",
        encoding="utf-8",
    )
    paths = _paths(tmp_path)
    secrets = MemorySecretStore()

    assert run(
        ["config", "migrate-env", str(dotenv), "--dry-run"],
        paths=paths,
        secret_store=secrets,
    ) == 0

    captured = capsys.readouterr()
    assert "very-secret-value" not in captured.out + captured.err
    assert not paths.user_config.exists()
    assert secrets.values == {}


def test_migrate_env_writes_config_and_keyring_without_modifying_source(
    tmp_path: Path,
) -> None:
    dotenv = tmp_path / "legacy.env"
    original = "LLM_PROVIDER=anthropic\nOPENAI_API_KEY=very-secret-value\n"
    dotenv.write_text(original, encoding="utf-8")
    paths = _paths(tmp_path)
    secrets = MemorySecretStore()

    assert run(
        ["config", "migrate-env", str(dotenv)],
        paths=paths,
        secret_store=secrets,
    ) == 0

    config_text = paths.user_config.read_text(encoding="utf-8")
    assert 'provider = "anthropic"' in config_text
    assert "very-secret-value" not in config_text
    assert secrets.get("provider/openai/api-key") == "very-secret-value"
    assert dotenv.read_text(encoding="utf-8") == original


def test_completion_outputs_shell_script(capsys: Any) -> None:
    assert run(["completion", "bash"], secret_store=MemorySecretStore()) == 0
    assert "complete -F _myagen_complete myagen" in capsys.readouterr().out
