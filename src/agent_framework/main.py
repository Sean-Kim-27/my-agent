"""Entrypoint for the Autonomous AI Agent Framework CLI.

This module handles argument parsing and dispatch to the appropriate adapter
(CLI, Discord, or Telegram). All adapter logic lives under
`agent_framework.integrations.*` — this file must not contain REPL loops,
slash command parsing, or bot startup logic beyond dispatching.
"""

import argparse
import asyncio

from agent_framework.bootstrap import build_agent
from agent_framework.config.settings import Settings, get_settings
from agent_framework.logging.logger import get_logger


def print_provider_status(settings: Settings) -> None:
    """Display authentication and configuration status for all supported providers."""
    print("\n=== AI Agent Framework Provider Status ===")

    openai_auth = "API Key (Configured)" if settings.openai_api_key else "API Key (Missing)"
    print("\n[OpenAI]")
    print(f"  Authentication : {openai_auth}")
    print(f"  Default Model  : {settings.openai_model}")
    print(f"  Base URL       : {settings.openai_base_url}")

    anthropic_auth = "API Key (Configured)" if settings.anthropic_api_key else "API Key (Missing)"
    print("\n[Anthropic]")
    print(f"  Authentication : {anthropic_auth}")
    print(f"  Default Model  : {settings.anthropic_model}")

    nim_auth = "API Key (Configured)" if settings.nvidia_nim_api_key else "API Key (Missing)"
    print("\n[NVIDIA NIM]")
    print(f"  Authentication : {nim_auth}")
    print(f"  Default Model  : {settings.nvidia_nim_model}")
    print(f"  Base URL       : {settings.nvidia_nim_base_url}")

    compat_auth = "API Key / Local" if settings.openai_compatible_api_key else "No Auth / Local"
    print("\n[OpenAI-Compatible (vLLM / Ollama / Local)]")
    print(f"  Authentication : {compat_auth}")
    print(f"  Default Model  : {settings.openai_compatible_model}")
    print(f"  Base URL       : {settings.openai_compatible_base_url}")

    codex_auth = (
        "OAuth Token (Configured)" if settings.codex_access_token else "OAuth (Requires Login / Token)"
    )
    print("\n[Codex]")
    print(f"  Authentication : {codex_auth}")
    print(f"  Default Model  : {settings.codex_model}")

    discord_auth = "Configured" if settings.discord_bot_token else "Missing Token"
    print("\n[Discord Bot Integration]")
    print(f"  Status         : {discord_auth}")
    print(f"  Require Mention: {settings.discord_require_mention}")
    print(f"  Allowed Channels: {settings.discord_allowed_channel_ids or 'All'}")

    telegram_auth = "Configured" if settings.telegram_bot_token else "Missing Token"
    print("\n[Telegram Bot Integration]")
    print(f"  Status         : {telegram_auth}")
    print(f"  Require Mention: {settings.telegram_require_mention}")
    print(f"  Allowed Chats   : {settings.telegram_allowed_chat_ids or 'All'}")
    print("\n==========================================\n")


async def dispatch(args: argparse.Namespace) -> None:
    """Route to the requested adapter (Discord / Telegram / CLI)."""
    settings = get_settings()

    if args.providers:
        print_provider_status(settings)
        return

    provider_name = args.provider or settings.llm_provider
    current_session = args.session or settings.default_session_id
    system_prompt = args.system_prompt or settings.agent_system_prompt

    logger = get_logger(
        "agent_framework.main",
        json_output=args.json_log or settings.json_logging,
    )
    logger.debug(
        f"Bootstrapping agent with provider '{provider_name}' and session '{current_session}'"
    )

    try:
        agent, tool_registry, session_manager = build_agent(
            settings=settings,
            provider_name=provider_name,
            model=args.model,
            system_prompt=system_prompt,
            default_session_id=current_session,
        )
    except Exception as exc:
        print(f"❌ Failed to initialize provider '{provider_name}': {exc}")
        print("Tip: Check your .env file or command-line parameters.")
        return

    if args.discord:
        from agent_framework.integrations.discord.bot import start_discord_bot

        print("🤖 Starting Discord Agent Bot...")
        try:
            await start_discord_bot(agent=agent, settings=settings)
        except Exception as exc:
            print(f"❌ Discord bot startup error: {exc}")
        return

    if args.telegram:
        from agent_framework.integrations.telegram.bot import start_telegram_bot

        print("🤖 Starting Telegram Agent Bot...")
        try:
            await start_telegram_bot(agent=agent, settings=settings)
        except Exception as exc:
            print(f"❌ Telegram bot startup error: {exc}")
        return

    from agent_framework.integrations.cli.bot import run_cli_session

    await run_cli_session(
        agent=agent,
        settings=settings,
        tool_registry=tool_registry,
        session_manager=session_manager,
        session_id=current_session,
    )


def main() -> None:
    """CLI entrypoint parsing arguments and starting event loop."""
    parser = argparse.ArgumentParser(description="Autonomous AI Agent Framework CLI")
    parser.add_argument(
        "--provider",
        type=str,
        help="LLM Provider (openai, anthropic, nvidia_nim, codex, openai_compatible)",
    )
    parser.add_argument("--model", type=str, help="Model name override")
    parser.add_argument(
        "--session", type=str, default="cli:default", help="Session ID (default: cli:default)"
    )
    parser.add_argument("--system-prompt", type=str, help="System prompt override")
    parser.add_argument(
        "--providers", action="store_true", help="List all supported providers and their auth status"
    )
    parser.add_argument("--discord", action="store_true", help="Launch the Discord Bot integration")
    parser.add_argument("--telegram", action="store_true", help="Launch the Telegram Bot integration")
    parser.add_argument("--json-log", action="store_true", help="Enable structured JSON log format")

    args = parser.parse_args()
    asyncio.run(dispatch(args))


if __name__ == "__main__":
    main()
