"""Interactive terminal (REPL) adapter for the Agent framework."""

from __future__ import annotations

from agent_framework.agent.agent import Agent
from agent_framework.config.settings import Settings
from agent_framework.exceptions import AgentFrameworkError
from agent_framework.integrations.cli.callbacks import CLIConfirmationHandler
from agent_framework.integrations.cli.router import parse_slash_command
from agent_framework.llm.factory import create_llm_provider
from agent_framework.logging.logger import get_logger
from agent_framework.memory.session import SessionManager
from agent_framework.tools.registry import ToolRegistry

logger = get_logger("agent_framework.cli")


def _print_help() -> None:
    print("\nAvailable Commands:")
    print("  /clear         - Clear conversation history for active session")
    print("  /history       - Show message history for active session")
    print("  /tools         - List currently registered tools")
    print("  /session <id>  - Switch or inspect active session ID")
    print("  /provider <id> - Dynamically switch LLM provider")
    print("  /info          - Display current agent runtime state")
    print("  /exit, /quit   - Exit application\n")


async def _handle_slash_command(
    command_name: str,
    argument: str,
    *,
    agent: Agent,
    settings: Settings,
    tool_registry: ToolRegistry,
    session_manager: SessionManager,
    current_session: str,
) -> tuple[str, bool]:
    """Handle a slash command. Returns (new_session, should_exit)."""
    if command_name in ("/exit", "/quit", "/q"):
        print("👋 Goodbye!")
        return current_session, True

    if command_name == "/clear":
        await agent.clear_session(current_session)
        print(f"🧹 Cleared history for session '{current_session}'.")
        return current_session, False

    if command_name == "/tools":
        tools = tool_registry.get_definitions()
        print(f"\n--- Registered Tools ({len(tools)}) ---")
        for t in tools:
            print(f"  • {t.name}: {t.description}")
        print("------------------------------------\n")
        return current_session, False

    if command_name == "/session":
        if not argument:
            print(f"Current session: {current_session}")
            return current_session, False
        print(f"🔀 Switched session to: '{argument}'")
        return argument, False

    if command_name == "/history":
        history = await agent.get_session_history(current_session)
        print(f"\n--- History for {current_session} ({len(history)} messages) ---")
        for msg in history:
            print(f"[{msg.role.upper()}]: {msg.content}")
        print("------------------------------------------\n")
        return current_session, False

    if command_name == "/provider":
        if not argument:
            print(f"Current provider: {agent.provider.name} (model: {agent.provider.model})")
        else:
            try:
                new_provider = create_llm_provider(settings, provider_name=argument)
                agent.provider = new_provider
                print(f"🔄 Switched provider to: {new_provider.name} (model: {new_provider.model})")
            except Exception as exc:
                print(f"❌ Failed to switch provider: {exc}")
        return current_session, False

    if command_name == "/info":
        print("\nAgent Config:")
        print(f"  • Provider: {agent.provider.name}")
        print(f"  • Model: {agent.provider.model}")
        print(f"  • System Prompt: {agent.system_prompt}")
        print(f"  • Active Sessions: {await session_manager.list_sessions()}\n")
        return current_session, False

    if command_name == "/help":
        _print_help()
        return current_session, False

    print(f"Unknown command '{command_name}'. Type '/help' for options.")
    return current_session, False


async def run_cli_session(
    *,
    agent: Agent,
    settings: Settings,
    tool_registry: ToolRegistry,
    session_manager: SessionManager,
    session_id: str,
) -> None:
    """Run the interactive REPL loop until the user exits."""
    current_session = session_id

    if not any(isinstance(cb, CLIConfirmationHandler) for cb in agent.callbacks):
        agent.add_callback(CLIConfirmationHandler())

    print("=" * 60)
    print("  🚀 Autonomous AI Agent Framework (CLI)")
    print(f"  • Provider: {agent.provider.name}")
    print(f"  • Session : {current_session}")
    print("  • Type '/help' for commands, '/exit' or Ctrl+C to quit.")
    print("=" * 60 + "\n")

    while True:
        try:
            user_input = input(f"[{current_session}] User > ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n👋 Exiting Agent Framework. Goodbye!")
            break

        if not user_input:
            continue

        command = parse_slash_command(user_input)
        if command is not None:
            current_session, should_exit = await _handle_slash_command(
                command.name,
                command.argument,
                agent=agent,
                settings=settings,
                tool_registry=tool_registry,
                session_manager=session_manager,
                current_session=current_session,
            )
            if should_exit:
                break
            continue

        try:
            print("⏳ Agent thinking...", end="\r", flush=True)
            response = await agent.run(user_input, session_id=current_session)
            print(
                f"\rAssistant ({response.provider}:{response.model} | "
                f"{response.latency_ms}ms) >\n{response.content}\n"
            )
        except AgentFrameworkError as err:
            print(f"\n❌ [{type(err).__name__}]: {err}\n")
        except Exception as exc:
            print(f"\n❌ Unexpected error: {exc}\n")
