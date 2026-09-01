"""Versioned SQLite session store with metadata, FTS5, and turn repair."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from pydantic import BaseModel

from agent_framework.models.message import Message

SQLITE_SCHEMA_VERSION = 2


class SessionSummary(BaseModel):
    session_id: str
    created_at: float
    updated_at: float
    message_count: int
    status: str
    repair_count: int


class SessionSearchHit(BaseModel):
    session_id: str
    message_id: int
    content: str
    rank: float


class SQLiteSessionStore:
    def __init__(self, db_path: str | Path, *, busy_timeout_ms: int = 5_000) -> None:
        self.db_path = str(db_path)
        self.busy_timeout_ms = busy_timeout_ms

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=self.busy_timeout_ms / 1000)
        conn.row_factory = sqlite3.Row
        conn.execute(f"PRAGMA busy_timeout={self.busy_timeout_ms}")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def ensure_schema(self) -> None:
        Path(self.db_path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            current_version = int(conn.execute("PRAGMA user_version").fetchone()[0])
            conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "version INTEGER PRIMARY KEY, applied_at REAL NOT NULL)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS conversation_messages ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "session_id TEXT NOT NULL, payload_json TEXT NOT NULL)"
            )
            columns = {
                str(row["name"])
                for row in conn.execute("PRAGMA table_info(conversation_messages)")
            }
            if "created_at" not in columns:
                conn.execute(
                    "ALTER TABLE conversation_messages "
                    "ADD COLUMN created_at REAL NOT NULL DEFAULT 0"
                )
            if "quarantined" not in columns:
                conn.execute(
                    "ALTER TABLE conversation_messages "
                    "ADD COLUMN quarantined INTEGER NOT NULL DEFAULT 0"
                )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_conversation_messages_session "
                "ON conversation_messages(session_id, id)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS conversation_sessions ("
                "session_id TEXT PRIMARY KEY, created_at REAL NOT NULL, "
                "updated_at REAL NOT NULL, status TEXT NOT NULL DEFAULT 'active', "
                "repair_count INTEGER NOT NULL DEFAULT 0)"
            )
            now = time.time()
            conn.execute(
                "INSERT OR IGNORE INTO conversation_sessions(session_id, created_at, updated_at) "
                "SELECT session_id, ?, ? FROM conversation_messages GROUP BY session_id",
                (now, now),
            )
            conn.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS conversation_messages_fts "
                "USING fts5(session_id UNINDEXED, content, message_id UNINDEXED)"
            )
            if current_version < SQLITE_SCHEMA_VERSION:
                conn.execute("DELETE FROM conversation_messages_fts")
                rows = conn.execute(
                    "SELECT id, session_id, payload_json FROM conversation_messages "
                    "WHERE quarantined = 0"
                ).fetchall()
                conn.executemany(
                    "INSERT INTO conversation_messages_fts(session_id, content, message_id) "
                    "VALUES (?, ?, ?)",
                    [
                        (
                            str(row["session_id"]),
                            str(json.loads(row["payload_json"]).get("content") or ""),
                            int(row["id"]),
                        )
                        for row in rows
                    ],
                )
            conn.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (SQLITE_SCHEMA_VERSION, now),
            )
            conn.execute(f"PRAGMA user_version={SQLITE_SCHEMA_VERSION}")
            conn.commit()

    def append_messages(
        self,
        session_id: str,
        messages: list[Message],
        *,
        max_messages: int | None = None,
    ) -> None:
        if not messages:
            return
        self.ensure_schema()
        now = time.time()
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "INSERT INTO conversation_sessions(session_id, created_at, updated_at) "
                "VALUES (?, ?, ?) ON CONFLICT(session_id) DO UPDATE SET "
                "updated_at=excluded.updated_at, status='active'",
                (session_id, now, now),
            )
            for message in messages:
                cursor = conn.execute(
                    "INSERT INTO conversation_messages("
                    "session_id, payload_json, created_at, quarantined) VALUES (?, ?, ?, 0)",
                    (session_id, message.model_dump_json(), now),
                )
                conn.execute(
                    "INSERT INTO conversation_messages_fts(session_id, content, message_id) "
                    "VALUES (?, ?, ?)",
                    (session_id, message.content or "", int(cursor.lastrowid or 0)),
                )
            if max_messages is not None:
                stale_ids = [
                    int(row["id"])
                    for row in conn.execute(
                        "SELECT id FROM conversation_messages WHERE session_id = ? "
                        "ORDER BY id DESC LIMIT -1 OFFSET ?",
                        (session_id, max_messages),
                    )
                ]
                if stale_ids:
                    placeholders = ",".join("?" for _ in stale_ids)
                    conn.execute(
                        f"DELETE FROM conversation_messages_fts WHERE message_id IN ({placeholders})",
                        stale_ids,
                    )
                    conn.execute(
                        f"DELETE FROM conversation_messages WHERE id IN ({placeholders})",
                        stale_ids,
                    )
            conn.commit()

    def repair_incomplete_turn(self, session_id: str) -> int:
        """Quarantine an unmatched assistant tool-call suffix from older runs."""
        self.ensure_schema()
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT id, payload_json FROM conversation_messages "
                "WHERE session_id = ? AND quarantined = 0 ORDER BY id",
                (session_id,),
            ).fetchall()
            pending_ids: set[str] = set()
            pending_start: int | None = None
            quarantine_start: int | None = None
            for row in rows:
                message = Message.model_validate_json(row["payload_json"])
                role = str(message.role.value if hasattr(message.role, "value") else message.role)
                if pending_ids:
                    if role == "tool" and message.tool_call_id in pending_ids:
                        pending_ids.remove(message.tool_call_id or "")
                        if not pending_ids:
                            pending_start = None
                        continue
                    quarantine_start = pending_start
                    break
                if role == "assistant" and message.tool_calls:
                    pending_ids = {call.id for call in message.tool_calls}
                    pending_start = int(row["id"])
            if quarantine_start is None and pending_ids:
                quarantine_start = pending_start
            if quarantine_start is None:
                return 0
            ids = [
                int(row["id"])
                for row in rows
                if int(row["id"]) >= quarantine_start
            ]
            placeholders = ",".join("?" for _ in ids)
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                f"UPDATE conversation_messages SET quarantined = 1 "
                f"WHERE id IN ({placeholders})",
                ids,
            )
            conn.execute(
                f"DELETE FROM conversation_messages_fts WHERE message_id IN ({placeholders})",
                ids,
            )
            conn.execute(
                "UPDATE conversation_sessions SET status='repaired', "
                "repair_count=repair_count + 1, updated_at=? WHERE session_id=?",
                (time.time(), session_id),
            )
            conn.commit()
            return len(ids)

    def messages(self, session_id: str, limit: int | None = None) -> list[Message]:
        self.repair_incomplete_turn(session_id)
        with self.connect() as conn:
            if limit is None or limit <= 0:
                rows = conn.execute(
                    "SELECT payload_json FROM conversation_messages "
                    "WHERE session_id=? AND quarantined=0 ORDER BY id",
                    (session_id,),
                ).fetchall()
            else:
                rows = list(
                    reversed(
                        conn.execute(
                            "SELECT payload_json FROM conversation_messages "
                            "WHERE session_id=? AND quarantined=0 ORDER BY id DESC LIMIT ?",
                            (session_id, limit),
                        ).fetchall()
                    )
                )
        return [Message.model_validate_json(row["payload_json"]) for row in rows]

    def list_sessions(self) -> list[SessionSummary]:
        self.ensure_schema()
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT s.session_id, s.created_at, s.updated_at, s.status, s.repair_count, "
                "COUNT(m.id) AS message_count FROM conversation_sessions s "
                "LEFT JOIN conversation_messages m ON m.session_id=s.session_id "
                "AND m.quarantined=0 GROUP BY s.session_id ORDER BY s.updated_at DESC"
            ).fetchall()
        return [SessionSummary.model_validate(dict(row)) for row in rows]

    def search(self, query: str, limit: int = 20) -> list[SessionSearchHit]:
        self.ensure_schema()
        phrase = '"' + query.replace('"', '""') + '"'
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT session_id, CAST(message_id AS INTEGER) AS message_id, content, "
                "bm25(conversation_messages_fts) AS rank FROM conversation_messages_fts "
                "WHERE conversation_messages_fts MATCH ? ORDER BY rank LIMIT ?",
                (phrase, limit),
            ).fetchall()
        return [SessionSearchHit.model_validate(dict(row)) for row in rows]

    def clear(self, session_id: str) -> bool:
        self.ensure_schema()
        with self.connect() as conn:
            exists = conn.execute(
                "SELECT 1 FROM conversation_sessions WHERE session_id=?", (session_id,)
            ).fetchone()
            if exists is None:
                return False
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "DELETE FROM conversation_messages_fts WHERE session_id=?", (session_id,)
            )
            conn.execute(
                "DELETE FROM conversation_messages WHERE session_id=?", (session_id,)
            )
            conn.execute(
                "UPDATE conversation_sessions SET updated_at=?, status='active' WHERE session_id=?",
                (time.time(), session_id),
            )
            conn.commit()
            return True

    def delete(self, session_id: str) -> bool:
        self.ensure_schema()
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "DELETE FROM conversation_messages_fts WHERE session_id=?", (session_id,)
            )
            conn.execute(
                "DELETE FROM conversation_messages WHERE session_id=?", (session_id,)
            )
            cursor = conn.execute(
                "DELETE FROM conversation_sessions WHERE session_id=?", (session_id,)
            )
            conn.commit()
            return cursor.rowcount > 0


__all__ = [
    "SQLITE_SCHEMA_VERSION",
    "SQLiteSessionStore",
    "SessionSearchHit",
    "SessionSummary",
]
