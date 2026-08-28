"""CLI slash command parsing and session id conventions."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SlashCommand:
    """Parsed representation of an interactive CLI slash command."""

    name: str
    argument: str

    @property
    def is_exit(self) -> bool:
        return self.name in ("/exit", "/quit", "/q")


def parse_slash_command(user_input: str) -> SlashCommand | None:
    """Return a SlashCommand if the user input begins with '/', else None."""
    stripped = user_input.strip()
    if not stripped.startswith("/"):
        return None
    parts = stripped.split(maxsplit=1)
    name = parts[0].lower()
    argument = parts[1].strip() if len(parts) > 1 else ""
    return SlashCommand(name=name, argument=argument)


def default_cli_session_id() -> str:
    """Return the CLI session-id convention default."""
    return "cli:default"
