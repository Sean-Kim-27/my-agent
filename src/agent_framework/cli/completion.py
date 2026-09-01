"""Dependency-free shell completion scripts for top-level commands."""

from __future__ import annotations

_COMMANDS = "ask auth bot chat completion config doctor mcp model provider session tools version"


def generate_completion(shell: str) -> str:
    if shell == "bash":
        return (
            "_myagen_complete() {\n"
            "  if [[ ${COMP_CWORD} -eq 1 ]]; then\n"
            f"    COMPREPLY=( $(compgen -W '{_COMMANDS}' -- \"${{COMP_WORDS[1]}}\") )\n"
            "  fi\n"
            "}\ncomplete -F _myagen_complete myagen\n"
        )
    if shell == "zsh":
        return f"#compdef myagen\n_arguments '1:command:({_COMMANDS.replace(' ', ' ')})'\n"
    if shell == "fish":
        return "\n".join(
            f"complete -c myagen -f -n '__fish_use_subcommand' -a {command}"
            for command in _COMMANDS.split()
        ) + "\n"
    raise ValueError(f"Unsupported shell: {shell}")


__all__ = ["generate_completion"]
