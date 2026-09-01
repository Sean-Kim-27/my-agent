"""Argparse command router for the ``myagen`` executable."""

from __future__ import annotations

import argparse
import asyncio
import sys
import warnings
from collections.abc import Sequence
from typing import Any

from agent_framework import __version__
from agent_framework.cli.commands.auth import run_auth_command
from agent_framework.cli.commands.config import run_config_command
from agent_framework.cli.commands.doctor import run_doctor
from agent_framework.cli.commands.mcp import run_mcp_command
from agent_framework.cli.commands.runtime import (
    PROVIDER_NAMES,
    run_ask,
    run_model_command,
    run_provider_command,
    run_tools_command,
)
from agent_framework.cli.commands.session import run_session_command
from agent_framework.cli.completion import generate_completion
from agent_framework.cli.exit_codes import ExitCode
from agent_framework.cli.output import OutputWriter
from agent_framework.config.secrets import KeyringSecretStore, SecretStore, SecretStoreError
from agent_framework.config.settings import Settings
from agent_framework.config.sources import resolve_settings
from agent_framework.config.store import ConfigPaths
from agent_framework.exceptions import AgentFrameworkError
from agent_framework.lifecycle import ApplicationLifecycle


def build_parser(*, prog: str = "myagen") -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description="Myagen autonomous agent command line interface",
    )
    parser.add_argument("--json", action="store_true", help="Emit versioned JSON output")
    parser.add_argument("--provider", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--model", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--session", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--system-prompt", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--json-log", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--providers", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--check", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--discord", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--telegram", action="store_true", help=argparse.SUPPRESS)
    subparsers = parser.add_subparsers(dest="command")

    chat = subparsers.add_parser("chat", help="Start an interactive chat")
    chat.add_argument("--provider", default=None)
    chat.add_argument("--model", default=None)
    chat.add_argument("--session", default=None)
    chat.add_argument("--system-prompt", default=None)
    chat.add_argument("--json-log", action="store_true")

    ask = subparsers.add_parser("ask", help="Run one prompt and print the answer")
    ask.add_argument("prompt", nargs="?")
    ask.add_argument("--stdin", action="store_true", help="Read the prompt from stdin")
    ask.add_argument("--provider", default=None)
    ask.add_argument("--model", default=None)
    ask.add_argument("--session", default=None)
    ask.add_argument("--system-prompt", default=None)
    ask.add_argument("--json", action="store_true")
    subparsers.add_parser("version", help="Show package and config schema versions")
    subparsers.add_parser("doctor", help="Validate local configuration and runtime paths")

    config = subparsers.add_parser("config", help="Manage non-secret configuration")
    config_commands = config.add_subparsers(dest="config_command", required=True)
    config_init = config_commands.add_parser("init")
    config_init.add_argument("--scope", choices=("user", "project"), default="user")
    config_path = config_commands.add_parser("path")
    config_path.add_argument(
        "--scope", choices=("user", "project", "effective"), default="effective"
    )
    config_list = config_commands.add_parser("list")
    config_list.add_argument("--source", action="store_true")
    config_get = config_commands.add_parser("get")
    config_get.add_argument("key")
    config_get.add_argument("--source", action="store_true")
    config_set = config_commands.add_parser("set")
    config_set.add_argument("key")
    config_set.add_argument("value", nargs="?")
    config_set.add_argument("--scope", choices=("user", "project"), default="user")
    config_unset = config_commands.add_parser("unset")
    config_unset.add_argument("key")
    config_unset.add_argument("--scope", choices=("user", "project"), default="user")
    config_commands.add_parser("validate")
    config_import = config_commands.add_parser("import")
    config_import.add_argument("path")
    config_import.add_argument("--dry-run", action="store_true")
    config_export = config_commands.add_parser("export")
    config_export.add_argument("path")
    config_migrate = config_commands.add_parser("migrate-env")
    config_migrate.add_argument("path", nargs="?", default=".env")
    config_migrate.add_argument("--dry-run", action="store_true")

    auth = subparsers.add_parser("auth", help="Manage credentials in the OS keyring")
    auth_commands = auth.add_subparsers(dest="auth_command", required=True)
    auth_set = auth_commands.add_parser("set")
    auth_set.add_argument("provider")
    auth_set.add_argument("--stdin", action="store_true")
    auth_status = auth_commands.add_parser("status")
    auth_status.add_argument("provider", nargs="?")
    auth_logout = auth_commands.add_parser("logout")
    auth_logout.add_argument("provider")

    provider = subparsers.add_parser("provider", help="Inspect and configure providers")
    provider_commands = provider.add_subparsers(dest="provider_command", required=True)
    provider_commands.add_parser("list")
    provider_use = provider_commands.add_parser("use")
    provider_use.add_argument("name", choices=PROVIDER_NAMES)
    provider_show = provider_commands.add_parser("show")
    provider_show.add_argument("name", choices=PROVIDER_NAMES)
    provider_check = provider_commands.add_parser("check")
    provider_check.add_argument("name", nargs="?", choices=PROVIDER_NAMES)
    provider_check.add_argument("--all", action="store_true")
    provider_configure = provider_commands.add_parser("configure")
    provider_configure.add_argument("name", choices=PROVIDER_NAMES)
    provider_configure.add_argument("--model")
    provider_configure.add_argument("--base-url")
    fallback = provider_commands.add_parser("fallback")
    fallback_commands = fallback.add_subparsers(dest="fallback_command", required=True)
    fallback_commands.add_parser("list")
    for operation in ("add", "remove"):
        command = fallback_commands.add_parser(operation)
        command.add_argument("names", nargs=1, choices=PROVIDER_NAMES)
    fallback_reorder = fallback_commands.add_parser("reorder")
    fallback_reorder.add_argument("names", nargs="+", choices=PROVIDER_NAMES)

    model = subparsers.add_parser("model", help="Configure provider models")
    model_commands = model.add_subparsers(dest="model_command", required=True)
    model_set = model_commands.add_parser("set")
    model_set.add_argument("provider", choices=PROVIDER_NAMES)
    model_set.add_argument("model")

    tools = subparsers.add_parser("tools", help="Inspect and enable toolsets")
    tools_commands = tools.add_subparsers(dest="tools_command", required=True)
    tools_commands.add_parser("list")
    tools_commands.add_parser("permissions")
    for operation in ("enable", "disable"):
        command = tools_commands.add_parser(operation)
        command.add_argument("toolset", choices=("builtin", "files", "terminal", "web"))

    mcp = subparsers.add_parser("mcp", help="Manage MCP server connections")
    mcp_commands = mcp.add_subparsers(dest="mcp_command", required=True)
    mcp_commands.add_parser("list")
    mcp_show = mcp_commands.add_parser("show")
    mcp_show.add_argument("name")
    mcp_add = mcp_commands.add_parser("add")
    mcp_add.add_argument("name")
    transport = mcp_add.add_mutually_exclusive_group(required=True)
    transport.add_argument("--stdio", action="store_true")
    transport.add_argument("--http")
    mcp_add.add_argument("--header-secret", action="append", default=[])
    mcp_add.add_argument("--env-secret", action="append", default=[])
    mcp_add.add_argument("argv", nargs="*")
    for operation in ("enable", "disable", "remove"):
        command = mcp_commands.add_parser(operation)
        command.add_argument("name")
    mcp_test = mcp_commands.add_parser("test")
    mcp_test.add_argument("name", nargs="?")
    mcp_test.add_argument("--all", action="store_true")

    bot = subparsers.add_parser("bot", help="Start a messaging integration")
    bot_commands = bot.add_subparsers(dest="bot_platform", required=True)
    for platform in ("discord", "telegram"):
        platform_parser = bot_commands.add_parser(platform)
        platform_commands = platform_parser.add_subparsers(
            dest="bot_command", required=True
        )
        platform_commands.add_parser("start")

    session = subparsers.add_parser("session", help="Manage persistent sessions")
    session_commands = session.add_subparsers(dest="session_command", required=True)
    session_commands.add_parser("list")
    session_show = session_commands.add_parser("show")
    session_show.add_argument("id")
    session_resume = session_commands.add_parser("resume")
    session_resume.add_argument("id")
    session_search = session_commands.add_parser("search")
    session_search.add_argument("query")
    for operation in ("clear", "delete"):
        command = session_commands.add_parser(operation)
        command.add_argument("id")
        command.add_argument("--confirm", action="store_true")

    completion = subparsers.add_parser("completion", help="Print shell completion code")
    completion.add_argument("shell", choices=("bash", "zsh", "fish"))
    return parser


async def _run_chat(
    args: argparse.Namespace,
    settings: Settings,
    secret_store: SecretStore | None = None,
) -> ExitCode:
    if args.providers:
        from agent_framework.main import check_provider_health, print_provider_status

        health = await check_provider_health(settings) if args.check else None
        print_provider_status(settings, health)
        return ExitCode.OK

    async with ApplicationLifecycle(
        settings,
        provider_name=args.provider,
        model=args.model,
        system_prompt=args.system_prompt,
        default_session_id=args.session,
        secret_store=secret_store,
    ) as runtime:
        if args.discord:
            from agent_framework.integrations.discord.bot import start_discord_bot

            await start_discord_bot(agent=runtime.agent, settings=settings)
        elif args.telegram:
            from agent_framework.integrations.telegram.bot import start_telegram_bot

            await start_telegram_bot(agent=runtime.agent, settings=settings)
        else:
            from agent_framework.integrations.cli.bot import run_cli_session

            await run_cli_session(
                agent=runtime.agent,
                settings=settings,
                tool_registry=runtime.tool_registry,
                session_manager=runtime.session_manager,
                session_id=args.session or settings.default_session_id,
            )
    return ExitCode.OK


def run(
    argv: Sequence[str] | None = None,
    *,
    prog: str = "myagen",
    paths: ConfigPaths | None = None,
    secret_store: SecretStore | None = None,
    stdin: Any = None,
) -> int:
    raw_args = list(argv if argv is not None else sys.argv[1:])
    parser = build_parser(prog=prog)
    args = parser.parse_args(raw_args or ["chat"])
    output = OutputWriter(json_mode=bool(args.json))
    resolved_paths = paths or ConfigPaths.discover()
    secrets = secret_store or KeyringSecretStore()

    if args.command == "version":
        output.success(
            {"package_version": __version__, "config_schema_version": 1},
            text=f"myagen {__version__} (config schema 1)",
        )
        return int(ExitCode.OK)
    if args.command == "doctor":
        try:
            settings = resolve_settings(paths=resolved_paths, secret_store=secrets).settings
        except (ValueError, SecretStoreError) as exc:
            output.error("invalid_config", str(exc))
            return int(ExitCode.CONFIG)
        return int(run_doctor(settings, output))
    if args.command == "completion":
        output.success(generate_completion(args.shell), text=generate_completion(args.shell))
        return int(ExitCode.OK)
    if args.command == "config":
        return int(
            run_config_command(
                args,
                output,
                paths=resolved_paths,
                secret_store=secrets,
            )
        )
    if args.command == "auth":
        kwargs = {"stdin": stdin} if stdin is not None else {}
        return int(run_auth_command(args, output, secret_store=secrets, **kwargs))
    if args.command in {"ask", "provider", "model", "tools", "mcp", "bot", "session"}:
        try:
            cli_overrides = {
                "llm_provider": getattr(args, "provider", None),
                "default_session_id": getattr(args, "session", None),
                "agent_system_prompt": getattr(args, "system_prompt", None),
            }
            settings = resolve_settings(
                paths=resolved_paths,
                secret_store=secrets,
                cli_overrides=cli_overrides,
            ).settings
            if args.command == "ask":
                kwargs = {"stdin": stdin} if stdin is not None else {}
                return int(
                    asyncio.run(
                        run_ask(
                            args,
                            settings,
                            output,
                            secret_store=secrets,
                            **kwargs,
                        )
                    )
                )
            if args.command == "provider":
                return int(
                    asyncio.run(
                        run_provider_command(
                            args,
                            settings,
                            output,
                            paths=resolved_paths,
                            secret_store=secrets,
                        )
                    )
                )
            if args.command == "model":
                return int(
                    run_model_command(
                        args,
                        output,
                        paths=resolved_paths,
                        secret_store=secrets,
                    )
                )
            if args.command == "tools":
                return int(
                    asyncio.run(
                        run_tools_command(
                            args,
                            settings,
                            output,
                            paths=resolved_paths,
                            secret_store=secrets,
                        )
                    )
                )
            if args.command == "mcp":
                return int(
                    asyncio.run(
                        run_mcp_command(
                            args,
                            settings,
                            output,
                            paths=resolved_paths,
                            secret_store=secrets,
                        )
                    )
                )
            if args.command == "session":
                result = run_session_command(args, settings, output)
                if args.session_command != "resume" or result != ExitCode.OK:
                    return int(result)
                resume_args = argparse.Namespace(
                    providers=False,
                    check=False,
                    provider=None,
                    model=None,
                    session=args.id,
                    system_prompt=None,
                    json_log=False,
                    discord=False,
                    telegram=False,
                )
                return int(asyncio.run(_run_chat(resume_args, settings, secrets)))
            bot_args = argparse.Namespace(
                providers=False,
                check=False,
                provider=None,
                model=None,
                session=None,
                system_prompt=None,
                json_log=False,
                discord=args.bot_platform == "discord",
                telegram=args.bot_platform == "telegram",
            )
            return int(asyncio.run(_run_chat(bot_args, settings, secrets)))
        except (ValueError, SecretStoreError) as exc:
            output.error("invalid_config", str(exc))
            return int(ExitCode.CONFIG)
        except AgentFrameworkError as exc:
            output.error("runtime_error", type(exc).__name__, hint="Run 'myagen doctor'.")
            return int(ExitCode.CONNECTION)
        except Exception as exc:  # noqa: BLE001 - CLI boundary must not expose details
            output.error("unexpected_error", type(exc).__name__)
            return int(ExitCode.CONNECTION)
        except KeyboardInterrupt:
            return int(ExitCode.INTERRUPTED)
    if args.command in {None, "chat"}:
        try:
            overrides = {
                "llm_provider": args.provider,
                "default_session_id": args.session,
                "agent_system_prompt": args.system_prompt,
            }
            settings = resolve_settings(
                paths=resolved_paths,
                secret_store=secrets,
                cli_overrides=overrides,
            ).settings
            return int(asyncio.run(_run_chat(args, settings, secrets)))
        except (ValueError, SecretStoreError) as exc:
            output.error("invalid_config", str(exc))
            return int(ExitCode.CONFIG)
        except AgentFrameworkError as exc:
            output.error("runtime_error", type(exc).__name__, hint="Run 'myagen doctor'.")
            return int(ExitCode.CONNECTION)
        except Exception as exc:  # noqa: BLE001 - CLI boundary must not expose details
            output.error("unexpected_error", type(exc).__name__)
            return int(ExitCode.CONNECTION)
        except KeyboardInterrupt:
            return int(ExitCode.INTERRUPTED)

    parser.error("a command is required")
    return int(ExitCode.USAGE)


def main() -> None:
    """Installed ``myagen`` entry point."""
    raise SystemExit(run())


def legacy_main() -> None:
    """One-release compatibility alias for the former executable name."""
    warnings.warn(
        "'agent-framework' is deprecated; use 'myagen' instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    raise SystemExit(run(prog="agent-framework"))


if __name__ == "__main__":
    main()
