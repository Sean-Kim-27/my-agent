"""Persistent SQLite session inspection and mutation commands."""

from __future__ import annotations

from typing import Any

from agent_framework.cli.exit_codes import ExitCode
from agent_framework.cli.output import OutputWriter
from agent_framework.config.settings import Settings
from agent_framework.logging.logger import mask_secrets
from agent_framework.memory.sqlite_store import SQLiteSessionStore


def run_session_command(
    args: Any,
    settings: Settings,
    output: OutputWriter,
) -> ExitCode:
    if settings.memory_backend != "sqlite":
        output.error(
            "persistent_memory_disabled",
            "Session commands require memory.backend = 'sqlite'.",
            hint="Run: myagen config set memory.backend sqlite",
        )
        return ExitCode.STORAGE
    store = SQLiteSessionStore(settings.sqlite_memory_path)
    action = args.session_command
    if action == "list":
        data = [item.model_dump() for item in store.list_sessions()]
        output.success(
            data,
            text="\n".join(
                f"{item['session_id']} ({item['message_count']} messages, {item['status']})"
                for item in data
            ),
        )
        return ExitCode.OK
    if action == "show":
        messages = store.messages(args.id)
        data = [
            {
                **message.model_dump(mode="json"),
                "content": mask_secrets(message.content or ""),
            }
            for message in messages
        ]
        if not data:
            output.error("session_not_found", f"Session not found or empty: {args.id}")
            return ExitCode.STORAGE
        output.success(
            data,
            text="\n".join(
                f"[{message['role']}] {message['content']}" for message in data
            ),
        )
        return ExitCode.OK
    if action == "search":
        data = [item.model_dump() for item in store.search(args.query)]
        for item in data:
            item["content"] = mask_secrets(str(item["content"]))
        output.success(
            data,
            text="\n".join(
                f"{item['session_id']}:{item['message_id']} {item['content']}"
                for item in data
            ),
        )
        return ExitCode.OK
    if action in {"clear", "delete"}:
        if not args.confirm:
            output.error(
                "confirmation_required",
                f"Refusing to {action} session without --confirm.",
            )
            return ExitCode.POLICY
        changed = store.clear(args.id) if action == "clear" else store.delete(args.id)
        if not changed:
            output.error("session_not_found", f"Unknown session: {args.id}")
            return ExitCode.STORAGE
        output.success({"session_id": args.id, "action": action}, text=f"{action}d {args.id}")
        return ExitCode.OK
    if action == "resume":
        if args.id not in {item.session_id for item in store.list_sessions()}:
            output.error("session_not_found", f"Unknown session: {args.id}")
            return ExitCode.STORAGE
        # The app router turns this validated intent into the interactive chat.
        return ExitCode.OK
    return ExitCode.USAGE


__all__ = ["run_session_command"]
