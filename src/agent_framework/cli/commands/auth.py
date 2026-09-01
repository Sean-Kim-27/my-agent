"""Credential management commands that never accept secrets in argv."""

from __future__ import annotations

import getpass
import sys
from typing import Any, TextIO

from agent_framework.cli.exit_codes import ExitCode
from agent_framework.cli.output import OutputWriter
from agent_framework.config.secrets import SecretStore, SecretStoreError

_PROVIDER_SECRET_KEYS = {
    "openai": "provider/openai/api-key",
    "anthropic": "provider/anthropic/api-key",
    "nvidia_nim": "provider/nvidia_nim/api-key",
    "openai_compatible": "provider/openai_compatible/api-key",
    "codex": "provider/codex/access-token",
    "discord": "integration/discord/bot-token",
    "telegram": "integration/telegram/bot-token",
}


def run_auth_command(
    args: Any,
    output: OutputWriter,
    *,
    secret_store: SecretStore,
    stdin: TextIO = sys.stdin,
) -> ExitCode:
    action = args.auth_command
    providers = [args.provider] if args.provider else sorted(_PROVIDER_SECRET_KEYS)
    unknown = [provider for provider in providers if provider not in _PROVIDER_SECRET_KEYS]
    if unknown:
        output.error("unknown_provider", f"Unknown credential target: {unknown[0]}")
        return ExitCode.USAGE

    try:
        if action == "set":
            provider = providers[0]
            value = stdin.readline().rstrip("\r\n") if args.stdin else getpass.getpass("Secret: ")
            if not value:
                output.error("empty_secret", "Secret value cannot be empty")
                return ExitCode.USAGE
            secret_store.set(_PROVIDER_SECRET_KEYS[provider], value)
            output.success({"provider": provider, "configured": True}, text=f"Stored {provider} credential.")
            return ExitCode.OK
        if action == "logout":
            provider = providers[0]
            removed = secret_store.delete(_PROVIDER_SECRET_KEYS[provider])
            output.success({"provider": provider, "removed": removed}, text=f"Removed {provider} credential: {removed}")
            return ExitCode.OK
        if action == "status":
            status = {
                provider: bool(secret_store.get(_PROVIDER_SECRET_KEYS[provider]))
                for provider in providers
            }
            output.success(status, text="\n".join(f"{name}: {'configured' if ready else 'missing'}" for name, ready in status.items()))
            return ExitCode.OK
    except SecretStoreError as exc:
        output.error("credential_backend_unavailable", str(exc))
        return ExitCode.CONFIG

    output.error("unsupported_auth_command", f"Unsupported auth command: {action}")
    return ExitCode.USAGE


__all__ = ["run_auth_command"]
