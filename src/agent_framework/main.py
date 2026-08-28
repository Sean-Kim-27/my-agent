"""Interactive CLI for the Autonomous AI Agent Framework."""

import argparse
import asyncio
from typing import Any

from agent_framework.agent.agent import Agent
from agent_framework.config.settings import Settings, get_settings
from agent_framework.exceptions import AgentFrameworkError
from agent_framework.llm.factory import create_llm_provider
from agent_framework.logging.logger import get_logger
from agent_framework.memory.session import SessionManager
from agent_framework.tools.registry import ToolRegistry


def print_provider_status(settings: Settings) -> None:
    """Display authentication and configuration status for all supported providers."""
    print("\n=== AI Agent Framework Provider Status ===")

    # OpenAI
    openai_auth = "API Key (Configured)" if settings.openai_api_key else "API Key (Missing)"
    print("\n[OpenAI]")
    print(f"  Authentication : {openai_auth}")
    print(f"  Default Model  : {settings.openai_model}")
    print(f"  Base URL       : {settings.openai_base_url}")

    # Anthropic
    anthropic_auth = "API Key (Configured)" if settings.anthropic_api_key else "API Key (Missing)"
    print("\n[Anthropic]")
    print(f"  Authentication : {anthropic_auth}")
    print(f"  Default Model  : {settings.anthropic_model}")

    # NVIDIA NIM
    nim_auth = "API Key (Configured)" if settings.nvidia_nim_api_key else "API Key (Missing)"
    print("\n[NVIDIA NIM]")
    print(f"  Authentication : {nim_auth}")
    print(f"  Default Model  : {settings.nvidia_nim_model}")
    print(f"  Base URL       : {settings.nvidia_nim_base_url}")

    # OpenAI-Compatible
    compat_auth = "API Key / Local" if settings.openai_compatible_api_key else "No Auth / Local"
    print("\n[OpenAI-Compatible (vLLM / Ollama / Local)]")
    print(f"  Authentication : {compat_auth}")
    print(f"  Default Model  : {settings.openai_compatible_model}")
    print(f"  Base URL       : {settings.openai_compatible_base_url}")

    # Codex OAuth
    codex_auth = "OAuth Token (Configured)" if settings.codex_access_token else "OAuth (Requires Login / Token)"
    print("\n[Codex]")
    print(f"  Authentication : {codex_auth}")
    print(f"  Default Model  : {settings.codex_model}")

    # Discord Integration
    discord_auth = "Configured" if settings.discord_bot_token else "Missing Token"
    print("\n[Discord Bot Integration]")
    print(f"  Status         : {discord_auth}")
    print(f"  Require Mention: {settings.discord_require_mention}")
    print(f"  Allowed Channels: {settings.discord_allowed_channel_ids or 'All'}")

    # Telegram Integration
    telegram_auth = "Configured" if settings.telegram_bot_token else "Missing Token"
    print("\n[Telegram Bot Integration]")
    print(f"  Status         : {telegram_auth}")
    print(f"  Require Mention: {settings.telegram_require_mention}")
    print(f"  Allowed Chats   : {settings.telegram_allowed_chat_ids or 'All'}")
    print("\n==========================================\n")


async def run_cli(args: argparse.Namespace) -> None:
    """Run interactive terminal session with the agent."""
    settings = get_settings()

    if args.providers:
        print_provider_status(settings)
        return

    provider_name = args.provider or settings.llm_provider
    model = args.model
    current_session = args.session or settings.default_session_id
    system_prompt = args.system_prompt or settings.agent_system_prompt

    logger = get_logger(
        "agent_framework.cli",
        json_output=args.json_log or settings.json_logging,
    )
    logger.debug(f"Starting CLI with provider '{provider_name}' and session '{current_session}'")

    print("=" * 60)
    print("  🚀 Autonomous AI Agent Framework (Phase 1 CLI)")
    print(f"  • Provider: {provider_name}")
    print(f"  • Session : {current_session}")
    print("  • Type '/help' for commands, '/exit' or Ctrl+C to quit.")
    print("=" * 60 + "\n")

    try:
        provider_overrides: dict[str, Any] = {}
        if model:
            provider_overrides["model"] = model

        provider = create_llm_provider(
            settings=settings,
            provider_name=provider_name,
            **provider_overrides,
        )
    except Exception as exc:
        print(f"❌ Failed to initialize provider '{provider_name}': {exc}")
        print("Tip: Check your .env file or command-line parameters.")
        return

    session_manager = SessionManager()
    tool_registry = ToolRegistry()

    @tool_registry.tool(description="Get the current date and time in UTC or local timezone.")
    def get_current_time(timezone: str = "UTC") -> str:
        """Get current date and time.
        Args:
            timezone: Target timezone name (e.g. UTC, Asia/Seoul).
        """
        import datetime
        now = datetime.datetime.now(datetime.UTC)
        return f"Current time in {timezone}: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}"

    @tool_registry.tool(description="Safely evaluate a basic mathematical arithmetic expression.")
    def calculate(expression: str) -> str:
        """Evaluate mathematical expression.
        Args:
            expression: Math expression to compute (e.g. '25 * 48 + 12').
        """
        allowed = set("0123456789+-*/(). %")
        if not all(c in allowed for c in expression):
            return "Error: Expression contains disallowed characters."
        try:
            # Safe eval of arithmetic only
            result = eval(expression, {"__builtins__": None}, {})  # noqa: S307
            return f"Result: {result}"
        except Exception as exc:
            return f"Error evaluating expression: {exc}"

    @tool_registry.tool(description="Fetch simulated current weather information for a specified city.")
    def get_weather(city: str) -> str:
        """Fetch current weather for a city.
        Args:
            city: City name (e.g. Seoul, Tokyo, New York).
        """
        sample_weather = {
            "seoul": "18°C, Clear Sky, Humidity: 45%",
            "tokyo": "20°C, Partly Cloudy, Humidity: 55%",
            "new york": "15°C, Light Rain, Humidity: 70%",
            "london": "12°C, Overcast, Humidity: 80%",
            "paris": "16°C, Sunny, Humidity: 50%",
        }
        return sample_weather.get(city.lower(), f"Weather in {city}: 21°C, Mild, Clear")

    agent = Agent(
        provider=provider,
        session_manager=session_manager,
        tool_registry=tool_registry,
        system_prompt=system_prompt,
        default_session_id=current_session,
    )

    if getattr(args, "discord", False):
        from agent_framework.integrations.discord.bot import start_discord_bot
        print("🤖 Starting Discord Agent Bot...")
        try:
            await start_discord_bot(agent=agent, settings=settings)
        except Exception as exc:
            print(f"❌ Discord bot startup error: {exc}")
        return

    if getattr(args, "telegram", False):
        from agent_framework.integrations.telegram.bot import start_telegram_bot
        print("🤖 Starting Telegram Agent Bot...")
        try:
            await start_telegram_bot(agent=agent, settings=settings)
        except Exception as exc:
            print(f"❌ Telegram bot startup error: {exc}")
        return

    while True:
        try:
            user_input = input(f"[{current_session}] User > ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n👋 Exiting Agent Framework. Goodbye!")
            break

        if not user_input:
            continue

        # Handle slash commands
        if user_input.startswith("/"):
            parts = user_input.split(maxsplit=1)
            cmd = parts[0].lower()
            arg = parts[1].strip() if len(parts) > 1 else ""

            if cmd in ("/exit", "/quit", "/q"):
                print("👋 Goodbye!")
                break
            elif cmd == "/clear":
                await agent.clear_session(current_session)
                print(f"🧹 Cleared history for session '{current_session}'.")
                continue
            elif cmd == "/tools":
                tools = tool_registry.get_definitions()
                print(f"\n--- Registered Tools ({len(tools)}) ---")
                for t in tools:
                    print(f"  • {t.name}: {t.description}")
                print("------------------------------------\n")
                continue
            elif cmd == "/session":
                if not arg:
                    print(f"Current session: {current_session}")
                else:
                    current_session = arg
                    print(f"🔀 Switched session to: '{current_session}'")
                continue
            elif cmd == "/history":
                history = await agent.get_session_history(current_session)
                print(f"\n--- History for {current_session} ({len(history)} messages) ---")
                for msg in history:
                    print(f"[{msg.role.upper()}]: {msg.content}")
                print("------------------------------------------\n")
                continue
            elif cmd == "/provider":
                if not arg:
                    print(f"Current provider: {agent.provider.name} (model: {agent.provider.model})")
                else:
                    try:
                        new_provider = create_llm_provider(settings, provider_name=arg)
                        agent.provider = new_provider
                        print(f"🔄 Switched provider to: {new_provider.name} (model: {new_provider.model})")
                    except Exception as exc:
                        print(f"❌ Failed to switch provider: {exc}")
                continue
            elif cmd == "/info":
                print("\nAgent Config:")
                print(f"  • Provider: {agent.provider.name}")
                print(f"  • Model: {agent.provider.model}")
                print(f"  • System Prompt: {agent.system_prompt}")
                print(f"  • Active Sessions: {await session_manager.list_sessions()}\n")
                continue
            elif cmd == "/help":
                print("\nAvailable Commands:")
                print("  /clear         - Clear conversation history for active session")
                print("  /history       - Show message history for active session")
                print("  /session <id>  - Switch or inspect active session ID")
                print("  /provider <id> - Dynamically switch LLM provider")
                print("  /info          - Display current agent runtime state")
                print("  /exit, /quit   - Exit application\n")
                continue
            else:
                print(f"Unknown command '{cmd}'. Type '/help' for options.")
                continue

        # Execute agent request
        try:
            print("⏳ Agent thinking...", end="\r", flush=True)
            response = await agent.run(user_input, session_id=current_session)
            print(f"\rAssistant ({response.provider}:{response.model} | {response.latency_ms}ms) >\n{response.content}\n")
        except AgentFrameworkError as err:
            print(f"\n❌ [{type(err).__name__}]: {err}\n")
        except Exception as exc:
            print(f"\n❌ Unexpected error: {exc}\n")


def main() -> None:
    """CLI entrypoint parsing arguments and starting event loop."""
    parser = argparse.ArgumentParser(description="Autonomous AI Agent Framework CLI")
    parser.add_argument("--provider", type=str, help="LLM Provider (openai, anthropic, nvidia_nim, codex, openai_compatible)")
    parser.add_argument("--model", type=str, help="Model name override")
    parser.add_argument("--session", type=str, default="cli:default", help="Session ID (default: cli:default)")
    parser.add_argument("--system-prompt", type=str, help="System prompt override")
    parser.add_argument("--providers", action="store_true", help="List all supported providers and their auth status")
    parser.add_argument("--discord", action="store_true", help="Launch the Discord Bot integration")
    parser.add_argument("--telegram", action="store_true", help="Launch the Telegram Bot integration")
    parser.add_argument("--json-log", action="store_true", help="Enable structured JSON log format")

    args = parser.parse_args()
    asyncio.run(run_cli(args))


if __name__ == "__main__":
    main()
