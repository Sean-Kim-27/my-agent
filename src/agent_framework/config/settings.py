"""Central configuration settings for Agent Framework."""

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Active Provider Selection
    llm_provider: Literal["openai", "anthropic", "nvidia_nim", "codex", "openai_compatible"] = Field(
        default="openai",
        description="Active LLM provider name",
    )

    # Global Agent Settings
    agent_system_prompt: str = Field(
        default="You are a helpful, precise, and autonomous AI assistant.",
        description="Default system prompt applied to conversation context",
    )
    default_session_id: str = Field(
        default="cli:default",
        description="Default session identifier",
    )
    request_timeout_seconds: float = Field(
        default=60.0,
        description="HTTP request timeout in seconds for LLM providers",
    )

    # OpenAI Settings
    openai_api_key: str | None = Field(default=None, description="OpenAI API Key")
    openai_model: str = Field(default="gpt-4o-mini", description="Default OpenAI model")
    openai_base_url: str = Field(default="https://api.openai.com/v1", description="OpenAI API base URL")

    # Anthropic Settings
    anthropic_api_key: str | None = Field(default=None, description="Anthropic API Key")
    anthropic_model: str = Field(
        default="claude-3-5-sonnet-20241022",
        description="Default Anthropic model",
    )

    # NVIDIA NIM Settings
    nvidia_nim_api_key: str | None = Field(default=None, description="NVIDIA NIM API Key")
    nvidia_nim_base_url: str = Field(
        default="https://integrate.api.nvidia.com/v1",
        description="NVIDIA NIM base URL",
    )
    nvidia_nim_model: str = Field(
        default="meta/llama-3.1-70b-instruct",
        description="Default NVIDIA NIM model",
    )

    # Generic OpenAI-Compatible Settings (vLLM, Ollama, Groq, OpenRouter, etc.)
    openai_compatible_api_key: str | None = Field(
        default=None,
        description="API key for custom OpenAI-compatible server",
    )
    openai_compatible_base_url: str = Field(
        default="http://localhost:8000/v1",
        description="Base URL for custom OpenAI-compatible server",
    )
    openai_compatible_model: str = Field(
        default="default-model",
        description="Model name for custom OpenAI-compatible server",
    )

    # Codex OAuth Settings
    codex_auth_mode: str = Field(default="oauth", description="Codex authentication mode")
    codex_model: str = Field(default="gpt-4o", description="Model for Codex execution")
    codex_access_token: str | None = Field(default=None, description="Official OAuth access token if supplied via environment")
    codex_refresh_token: str | None = Field(default=None, description="Official OAuth refresh token if supplied via environment")

    # Discord Integration Settings
    discord_bot_token: str | None = Field(default=None, description="Discord Bot Token")
    discord_allowed_channel_ids: list[int] = Field(
        default_factory=list,
        description="Allowed channel IDs for bot processing. If empty, all accessible channels are allowed.",
    )
    discord_require_mention: bool = Field(
        default=True,
        description="Whether bot must be mentioned in guild channels to trigger a response",
    )
    discord_max_queue_size: int = Field(
        default=100,
        description="Maximum capacity of asynchronous message processing queue",
    )

    # Telegram Integration Settings
    telegram_bot_token: str | None = Field(default=None, description="Telegram Bot Token")
    telegram_allowed_chat_ids: list[int] = Field(
        default_factory=list,
        description="Allowed chat IDs for bot processing. If empty, all accessible chats are allowed.",
    )
    telegram_require_mention: bool = Field(
        default=True,
        description="Whether bot must be mentioned in group/supergroup chats to trigger a response",
    )

    # Logging Settings
    json_logging: bool = Field(default=False, description="Enable structured JSON log format")
    log_level: str = Field(default="INFO", description="Logging level (DEBUG, INFO, WARNING, ERROR)")


# Global settings singleton helper
_global_settings: Settings | None = None


def get_settings() -> Settings:
    """Retrieve or create the global Settings instance."""
    global _global_settings
    if _global_settings is None:
        _global_settings = Settings()
    return _global_settings
