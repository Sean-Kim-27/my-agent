"""Versioned persistent session metadata, FTS, and repair tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from agent_framework.cli.app import run
from agent_framework.config.secrets import MemorySecretStore
from agent_framework.config.store import ConfigPaths, ConfigStore
from agent_framework.memory.sqlite_store import SQLITE_SCHEMA_VERSION, SQLiteSessionStore
from agent_framework.models.message import Message
from agent_framework.models.tool import ToolCall


def _paths(root: Path) -> ConfigPaths:
    return ConfigPaths(
        user_config=root / "user" / "config.toml",
        project_config=root / "project" / "config.toml",
        data_dir=root / "data",
        cache_dir=root / "cache",
    )


def test_schema_migrates_legacy_database_and_records_version(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "CREATE TABLE conversation_messages ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, "
            "payload_json TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO conversation_messages(session_id, payload_json) VALUES (?, ?)",
            ("legacy", Message.user("old message").model_dump_json()),
        )

    store = SQLiteSessionStore(db_path)
    sessions = store.list_sessions()

    assert sessions[0].session_id == "legacy"
    assert sessions[0].message_count == 1
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SQLITE_SCHEMA_VERSION


def test_restart_list_search_resume_clear_delete_semantics(tmp_path: Path) -> None:
    db_path = tmp_path / "sessions.db"
    store = SQLiteSessionStore(db_path)
    store.append_messages("work", [Message.user("unique searchable phrase")])

    reopened = SQLiteSessionStore(db_path)
    assert [item.session_id for item in reopened.list_sessions()] == ["work"]
    assert reopened.search("unique searchable phrase")[0].session_id == "work"
    assert reopened.clear("work") is True
    assert reopened.messages("work") == []
    assert reopened.delete("work") is True
    assert reopened.list_sessions() == []


def test_incomplete_tool_turn_is_quarantined(tmp_path: Path) -> None:
    store = SQLiteSessionStore(tmp_path / "repair.db")
    store.append_messages(
        "broken",
        [
            Message.user("do it"),
            Message.assistant(
                tool_calls=[ToolCall(id="call-1", name="danger", arguments={})]
            ),
        ],
    )

    visible = store.messages("broken")
    summary = store.list_sessions()[0]

    assert [message.content for message in visible] == ["do it"]
    assert summary.status == "repaired"
    assert summary.repair_count == 1


def test_session_cli_operates_on_persisted_rows(tmp_path: Path, capsys: Any) -> None:
    paths = _paths(tmp_path)
    db_path = tmp_path / "cli.db"
    ConfigStore(paths.user_config).write(
        {"memory": {"backend": "sqlite", "sqlite_path": str(db_path)}}
    )
    SQLiteSessionStore(db_path).append_messages("cli:work", [Message.user("hello")])
    secrets = MemorySecretStore()

    assert run(["session", "list"], paths=paths, secret_store=secrets) == 0
    assert "cli:work" in capsys.readouterr().out
    assert run(
        ["session", "delete", "cli:work"], paths=paths, secret_store=secrets
    ) == 5
    assert run(
        ["session", "delete", "cli:work", "--confirm"],
        paths=paths,
        secret_store=secrets,
    ) == 0
    assert SQLiteSessionStore(db_path).list_sessions() == []
