"""Runtime-facing ask, provider, model, and tool commands."""

from __future__ import annotations

import sys
from typing import Any, TextIO

from agent_framework.cli.commands.config import update_config_value
from agent_framework.cli.exit_codes import ExitCode
from agent_framework.cli.output import OutputWriter
from agent_framework.config.secrets import SecretStore
from agent_framework.config.settings import Settings
from agent_framework.config.store import ConfigPaths
from agent_framework.lifecycle import ApplicationLifecycle
from agent_framework.llm.factory import create_llm_provider

PROVIDER_NAMES = ("openai", "anthropic", "nvidia_nim", "openai_compatible", "codex")


async def run_ask(
    args: Any,
    settings: Settings,
    output: OutputWriter,
    *,
    stdin: TextIO = sys.stdin,
    secret_store: SecretStore | None = None,
) -> ExitCode:
    prompt = stdin.read() if args.stdin else args.prompt
    if not prompt or not prompt.strip():
        output.error("empty_prompt", "A prompt is required as an argument or via --stdin")
        return ExitCode.USAGE
    async with ApplicationLifecycle(
        settings,
        provider_name=args.provider,
        model=args.model,
        system_prompt=args.system_prompt,
        default_session_id=args.session,
        secret_store=secret_store,
    ) as runtime:
        result = await runtime.agent.run_with_trace(prompt, session_id=args.session)
    data = {
        "content": result.content,
        "session_id": result.session_id,
        "run_id": result.run_id,
        "state": result.state,
        "provider": result.llm_response.provider,
        "model": result.llm_response.model,
    }
    output.success(data, text=result.content)
    return ExitCode.OK


async def run_provider_command(
    args: Any,
    settings: Settings,
    output: OutputWriter,
    *,
    paths: ConfigPaths,
    secret_store: SecretStore,
) -> ExitCode:
    action = args.provider_command
    if action == "list":
        provider_list = [
            {"name": name, "active": name == settings.llm_provider}
            for name in PROVIDER_NAMES
        ]
        output.success(
            provider_list,
            text="\n".join(
                f"{'*' if item['active'] else ' '} {item['name']}" for item in provider_list
            ),
        )
        return ExitCode.OK
    if action == "use":
        update_config_value(
            paths=paths,
            secret_store=secret_store,
            key="agent.provider",
            value=args.name,
        )
        output.success({"provider": args.name}, text=f"Active provider: {args.name}")
        return ExitCode.OK
    if action == "show":
        provider = create_llm_provider(settings, provider_name=args.name)
        try:
            provider_data = {
                "name": provider.name,
                "model": provider.model,
                "capabilities": provider.capabilities.model_dump(),
            }
        finally:
            await provider.close()
        output.success(
            provider_data,
            text=f"{provider_data['name']}: {provider_data['model']}",
        )
        return ExitCode.OK
    if action == "check":
        targets = list(PROVIDER_NAMES) if args.all else [args.name or settings.llm_provider]
        health: dict[str, bool] = {}
        for name in targets:
            provider = create_llm_provider(settings, provider_name=name, max_retries=0)
            try:
                health[name] = await provider.health_check()
            finally:
                await provider.close()
        output.success(
            health,
            text="\n".join(f"{name}: {'healthy' if ok else 'unhealthy'}" for name, ok in health.items()),
        )
        return ExitCode.OK if all(health.values()) else ExitCode.CONNECTION
    if action == "configure":
        changed: list[str] = []
        if args.model:
            key = f"providers.{args.name}.model"
            update_config_value(paths=paths, secret_store=secret_store, key=key, value=args.model)
            changed.append(key)
        if args.base_url:
            key = f"providers.{args.name}.base_url"
            update_config_value(paths=paths, secret_store=secret_store, key=key, value=args.base_url)
            changed.append(key)
        output.success({"updated": changed}, text=f"Updated {', '.join(changed) or 'nothing'}")
        return ExitCode.OK
    if action == "fallback":
        current = list(settings.fallback_providers)
        if args.fallback_command == "list":
            output.success(current, text="\n".join(current))
            return ExitCode.OK
        if args.fallback_command == "add":
            if args.names[0] not in current:
                current.append(args.names[0])
        elif args.fallback_command == "remove":
            current = [name for name in current if name != args.names[0]]
        else:
            current = list(args.names)
        update_config_value(
            paths=paths,
            secret_store=secret_store,
            key="agent.fallback_providers",
            value=current,
        )
        output.success(current, text="Fallbacks: " + ", ".join(current))
        return ExitCode.OK
    return ExitCode.USAGE


def run_model_command(
    args: Any,
    output: OutputWriter,
    *,
    paths: ConfigPaths,
    secret_store: SecretStore,
) -> ExitCode:
    key = f"providers.{args.provider}.model"
    update_config_value(paths=paths, secret_store=secret_store, key=key, value=args.model)
    output.success({"key": key, "model": args.model}, text=f"Updated {key}")
    return ExitCode.OK


async def run_tools_command(
    args: Any,
    settings: Settings,
    output: OutputWriter,
    *,
    paths: ConfigPaths,
    secret_store: SecretStore,
) -> ExitCode:
    action = args.tools_command
    if action in {"enable", "disable"}:
        enabled = action == "enable"
        key = {
            "builtin": "tools.builtin.enabled",
            "files": "tools.builtin.include_files",
            "terminal": "tools.builtin.include_terminal",
            "web": "tools.builtin.include_web",
        }[args.toolset]
        update_config_value(paths=paths, secret_store=secret_store, key=key, value=enabled)
        output.success({"toolset": args.toolset, "enabled": enabled}, text=f"{args.toolset}: {enabled}")
        return ExitCode.OK
    async with ApplicationLifecycle(settings, secret_store=secret_store) as runtime:
        definitions = runtime.tool_registry.get_definitions()
    data: list[dict[str, Any]]
    if action == "permissions":
        data = [
            {
                "name": definition.name,
                "risk": definition.risk_level,
                "requires_confirmation": definition.effective_requires_confirmation,
            }
            for definition in definitions
        ]
    else:
        data = [definition.model_dump() for definition in definitions]
    output.success(data, text="\n".join(str(item["name"]) for item in data))
    return ExitCode.OK


__all__ = [
    "PROVIDER_NAMES",
    "run_ask",
    "run_model_command",
    "run_provider_command",
    "run_tools_command",
]
