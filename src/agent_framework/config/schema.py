"""Versioned configuration mapping between TOML keys and runtime settings."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from agent_framework.config.settings import Settings

CONFIG_SCHEMA_VERSION = 1


class FieldKind(StrEnum):
    CONFIG = "config"
    SECRET = "secret"
    RUNTIME = "runtime"


@dataclass(frozen=True)
class FieldMapping:
    key: str
    kind: FieldKind = FieldKind.CONFIG


FIELD_MAPPINGS: dict[str, FieldMapping] = {
    "llm_provider": FieldMapping("agent.provider"),
    "agent_system_prompt": FieldMapping("agent.system_prompt"),
    "default_session_id": FieldMapping("agent.default_session"),
    "request_timeout_seconds": FieldMapping("providers.request_timeout_seconds"),
    "request_connect_timeout_seconds": FieldMapping("providers.connect_timeout_seconds"),
    "request_read_timeout_seconds": FieldMapping("providers.read_timeout_seconds"),
    "request_write_timeout_seconds": FieldMapping("providers.write_timeout_seconds"),
    "request_pool_timeout_seconds": FieldMapping("providers.pool_timeout_seconds"),
    "fallback_providers": FieldMapping("agent.fallback_providers"),
    "model_metadata": FieldMapping("providers.model_metadata"),
    "agent_max_steps": FieldMapping("agent.max_steps"),
    "agent_tool_timeout": FieldMapping("agent.tool_timeout"),
    "agent_max_retries": FieldMapping("agent.max_retries"),
    "execution_backend": FieldMapping("execution.backend"),
    "execution_safe_root": FieldMapping("execution.safe_root"),
    "execution_allow_writes": FieldMapping("execution.allow_writes"),
    "execution_allow_destructive": FieldMapping("execution.allow_destructive"),
    "execution_allow_subprocess": FieldMapping("execution.allow_subprocess"),
    "execution_env_allowlist": FieldMapping("execution.env_allowlist"),
    "execution_max_file_bytes": FieldMapping("execution.max_file_bytes"),
    "execution_max_output_bytes": FieldMapping("execution.max_output_bytes"),
    "execution_docker_image": FieldMapping("execution.docker_image"),
    "approval_default_ttl_seconds": FieldMapping("execution.approval_ttl_seconds"),
    "enable_builtin_tools": FieldMapping("tools.builtin.enabled"),
    "builtin_tools_include_files": FieldMapping("tools.builtin.include_files"),
    "builtin_tools_include_terminal": FieldMapping("tools.builtin.include_terminal"),
    "builtin_tools_include_web": FieldMapping("tools.builtin.include_web"),
    "enable_mcp": FieldMapping("mcp.enabled"),
    "mcp_config_path": FieldMapping("mcp.config_path"),
    "mcp_servers": FieldMapping("mcp.servers"),
    "context_manager_enabled": FieldMapping("context.enabled"),
    "context_strategy": FieldMapping("context.strategy"),
    "context_max_tokens": FieldMapping("context.max_tokens"),
    "context_headroom_ratio": FieldMapping("context.headroom_ratio"),
    "context_summary_max_tokens": FieldMapping("context.summary_max_tokens"),
    "memory_backend": FieldMapping("memory.backend"),
    "sqlite_memory_path": FieldMapping("memory.sqlite_path"),
    "memory_max_messages": FieldMapping("memory.max_messages"),
    "openai_api_key": FieldMapping("provider/openai/api-key", FieldKind.SECRET),
    "openai_model": FieldMapping("providers.openai.model"),
    "openai_base_url": FieldMapping("providers.openai.base_url"),
    "anthropic_api_key": FieldMapping("provider/anthropic/api-key", FieldKind.SECRET),
    "anthropic_model": FieldMapping("providers.anthropic.model"),
    "nvidia_nim_api_key": FieldMapping("provider/nvidia_nim/api-key", FieldKind.SECRET),
    "nvidia_nim_base_url": FieldMapping("providers.nvidia_nim.base_url"),
    "nvidia_nim_model": FieldMapping("providers.nvidia_nim.model"),
    "openai_compatible_api_key": FieldMapping(
        "provider/openai_compatible/api-key", FieldKind.SECRET
    ),
    "openai_compatible_base_url": FieldMapping("providers.openai_compatible.base_url"),
    "openai_compatible_model": FieldMapping("providers.openai_compatible.model"),
    "codex_auth_mode": FieldMapping("providers.codex.auth_mode"),
    "codex_model": FieldMapping("providers.codex.model"),
    "codex_access_token": FieldMapping("provider/codex/access-token", FieldKind.SECRET),
    "codex_refresh_token": FieldMapping("provider/codex/refresh-token", FieldKind.SECRET),
    "discord_bot_token": FieldMapping("integration/discord/bot-token", FieldKind.SECRET),
    "discord_allowed_channel_ids": FieldMapping("integrations.discord.allowed_channel_ids"),
    "discord_require_mention": FieldMapping("integrations.discord.require_mention"),
    "discord_max_queue_size": FieldMapping("integrations.discord.max_queue_size"),
    "discord_confirmation_timeout": FieldMapping("integrations.discord.confirmation_timeout"),
    "telegram_bot_token": FieldMapping("integration/telegram/bot-token", FieldKind.SECRET),
    "telegram_allowed_chat_ids": FieldMapping("integrations.telegram.allowed_chat_ids"),
    "telegram_require_mention": FieldMapping("integrations.telegram.require_mention"),
    "telegram_confirmation_timeout": FieldMapping("integrations.telegram.confirmation_timeout"),
    "json_logging": FieldMapping("logging.json", FieldKind.RUNTIME),
    "log_level": FieldMapping("logging.level", FieldKind.RUNTIME),
}


def validate_mapping_coverage() -> None:
    missing = set(Settings.model_fields) - set(FIELD_MAPPINGS)
    stale = set(FIELD_MAPPINGS) - set(Settings.model_fields)
    if missing or stale:
        raise RuntimeError(
            f"Settings mapping registry mismatch; missing={sorted(missing)}, stale={sorted(stale)}"
        )


validate_mapping_coverage()

__all__ = [
    "CONFIG_SCHEMA_VERSION",
    "FIELD_MAPPINGS",
    "FieldKind",
    "FieldMapping",
    "validate_mapping_coverage",
]
