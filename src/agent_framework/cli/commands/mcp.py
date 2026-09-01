"""Managed MCP server configuration and connectivity commands."""

from __future__ import annotations

from typing import Any

from agent_framework.bootstrap import bootstrap_mcp_servers
from agent_framework.cli.commands.config import update_config_value
from agent_framework.cli.exit_codes import ExitCode
from agent_framework.cli.output import OutputWriter
from agent_framework.config.secrets import SecretStore
from agent_framework.config.settings import Settings
from agent_framework.config.store import ConfigPaths
from agent_framework.mcp.config import MCPServerConfig
from agent_framework.tools.registry import ToolRegistry


def _pairs(values: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in values:
        key, separator, value = item.partition("=")
        if not separator or not key or not value:
            raise ValueError(f"Expected NAME=SECRET_REFERENCE, got {item!r}")
        result[key] = value
    return result


def _find(records: list[dict[str, Any]], name: str) -> tuple[int, dict[str, Any]]:
    for index, record in enumerate(records):
        if record.get("name") == name:
            return index, record
    raise ValueError(f"Unknown MCP server: {name}")


def _persist(
    records: list[dict[str, Any]],
    *,
    paths: ConfigPaths,
    secret_store: SecretStore,
) -> None:
    update_config_value(
        paths=paths,
        secret_store=secret_store,
        key="mcp.servers",
        value=records,
    )


async def run_mcp_command(
    args: Any,
    settings: Settings,
    output: OutputWriter,
    *,
    paths: ConfigPaths,
    secret_store: SecretStore,
) -> ExitCode:
    action = args.mcp_command
    records = [dict(record) for record in settings.mcp_servers]
    if action == "list":
        output.success(
            records,
            text="\n".join(
                f"{record['name']} ({record['transport']}, "
                f"{'enabled' if record.get('enabled', True) else 'disabled'})"
                for record in records
            ),
        )
        return ExitCode.OK
    if action == "show":
        _, record = _find(records, args.name)
        output.success(record, text=str(record))
        return ExitCode.OK
    if action == "add":
        if any(record.get("name") == args.name for record in records):
            raise ValueError(f"MCP server already exists: {args.name}")
        command = list(args.argv)
        if command and command[0] == "--":
            command = command[1:]
        if args.stdio:
            config = MCPServerConfig(
                name=args.name,
                transport="stdio",
                command=command,
                extra_env_secret_refs=_pairs(args.env_secret),
            )
        else:
            config = MCPServerConfig(
                name=args.name,
                transport="http",
                url=args.http,
                header_secret_refs=_pairs(args.header_secret),
            )
        serialized = config.model_dump(mode="json", exclude_none=True)
        records.append(serialized)
        _persist(records, paths=paths, secret_store=secret_store)
        update_config_value(
            paths=paths,
            secret_store=secret_store,
            key="mcp.enabled",
            value=True,
        )
        output.success(serialized, text=f"Added MCP server {args.name}")
        return ExitCode.OK
    if action in {"enable", "disable"}:
        index, record = _find(records, args.name)
        records[index] = {**record, "enabled": action == "enable"}
        _persist(records, paths=paths, secret_store=secret_store)
        output.success(records[index], text=f"{args.name}: {action}d")
        return ExitCode.OK
    if action == "remove":
        index, _ = _find(records, args.name)
        records.pop(index)
        _persist(records, paths=paths, secret_store=secret_store)
        output.success({"removed": args.name}, text=f"Removed MCP server {args.name}")
        return ExitCode.OK
    if action == "test":
        targets = records if args.all else [_find(records, args.name)[1]]
        configs = [MCPServerConfig.model_validate(record) for record in targets]
        registry = ToolRegistry()
        enabled_settings = settings.model_copy(update={"enable_mcp": True})
        manager = await bootstrap_mcp_servers(
            settings=enabled_settings,
            tool_registry=registry,
            configs=configs,
            secret_store=secret_store,
        )
        try:
            statuses = manager.all_status() if manager else []
            data = {
                status.name: {
                    "connected": status.connected,
                    "tools": status.registered_tools,
                }
                for status in statuses
            }
        finally:
            if manager is not None:
                await manager.shutdown()
        output.success(data, text="\n".join(f"{name}: {value['connected']}" for name, value in data.items()))
        return ExitCode.OK if all(item["connected"] for item in data.values()) else ExitCode.CONNECTION
    return ExitCode.USAGE


__all__ = ["run_mcp_command"]
