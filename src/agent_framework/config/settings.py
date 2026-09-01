"""Central configuration settings for Agent Framework."""

from typing import Any, Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from agent_framework.models.response import ModelMetadata, ProviderTimeouts


class AgentConfig(BaseModel):
    """Runtime safety knobs for the Agent orchestrator, tool executor, and LLM retries.

    Centralizes execution-safety configuration that previously lived as kwargs
    scattered across Agent, ToolExecutor, and each LLM provider.
    """

    max_steps: int = Field(
        default=10,
        ge=1,
        description="Maximum ReAct loop iterations before aborting a single agent run.",
    )
    tool_timeout: float = Field(
        default=30.0,
        gt=0,
        description="Per-tool execution timeout in seconds.",
    )
    max_retries: int = Field(
        default=3,
        ge=0,
        description="Retry attempts (beyond the initial call) for transient LLM API failures.",
    )


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
    request_connect_timeout_seconds: float | None = Field(default=None, gt=0)
    request_read_timeout_seconds: float | None = Field(default=None, gt=0)
    request_write_timeout_seconds: float | None = Field(default=None, gt=0)
    request_pool_timeout_seconds: float | None = Field(default=None, gt=0)
    fallback_providers: list[str] = Field(
        default_factory=list,
        description="Ordered provider names used when the active provider fails.",
    )
    model_metadata: dict[str, ModelMetadata] = Field(
        default_factory=dict,
        description="Per-model metadata keyed by model or provider:model.",
    )

    # Agent execution safety configuration
    agent_max_steps: int = Field(
        default=10,
        ge=1,
        description="Maximum ReAct loop iterations before aborting a single agent run.",
    )
    agent_tool_timeout: float = Field(
        default=30.0,
        gt=0,
        description="Per-tool execution timeout in seconds.",
    )
    agent_max_retries: int = Field(
        default=3,
        ge=0,
        description="Retry attempts (beyond the initial call) for transient LLM API failures.",
    )

    # Phase 4 execution boundary configuration
    execution_backend: Literal["local", "docker"] = Field(
        default="local",
        description="Execution backend for Phase 5 built-in tools.",
    )
    execution_safe_root: str = Field(
        default=".",
        description="Root directory that bounds all filesystem operations.",
    )
    execution_allow_writes: bool = Field(
        default=False,
        description="Allow the execution backend to perform write operations.",
    )
    execution_allow_destructive: bool = Field(
        default=False,
        description="Allow destructive operations (delete/overwrite) on the execution backend.",
    )
    execution_allow_subprocess: bool = Field(
        default=False,
        description="Allow the execution backend to spawn subprocesses.",
    )
    execution_env_allowlist: list[str] = Field(
        default_factory=list,
        description="Host environment variables that may be forwarded to subprocesses.",
    )
    execution_max_file_bytes: int = Field(
        default=1_048_576,
        gt=0,
        description="Maximum bytes read from a single file via the execution backend.",
    )
    execution_max_output_bytes: int = Field(
        default=65_536,
        gt=0,
        description="Maximum stdout/stderr bytes captured from a subprocess.",
    )
    execution_docker_image: str = Field(
        default="python:3.12-slim",
        description="Container image used by DockerExecutionBackend when selected.",
    )
    approval_default_ttl_seconds: float = Field(
        default=300.0,
        gt=0,
        description="Default TTL for command-approval records (seconds).",
    )

    # Phase 5 built-in tool wiring
    enable_builtin_tools: bool = Field(
        default=False,
        description="Register built-in file, terminal, and web tools on the shared registry.",
    )
    builtin_tools_include_files: bool = Field(
        default=True,
        description="When built-in tools are enabled, register file tools.",
    )
    builtin_tools_include_terminal: bool = Field(
        default=True,
        description="When built-in tools are enabled, register the terminal tool.",
    )
    builtin_tools_include_web: bool = Field(
        default=True,
        description="When built-in tools are enabled, register web fetch tools.",
    )

    # Phase 6 MCP integration
    enable_mcp: bool = Field(
        default=False,
        description="Enable MCP (Model Context Protocol) server integration.",
    )
    mcp_config_path: str | None = Field(
        default=None,
        description="Path to a JSON file listing MCP servers to register.",
    )
    mcp_servers: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Managed MCP server records stored by the myagen CLI.",
    )

    # Context engine (Phase 8) configuration
    context_manager_enabled: bool = Field(
        default=True,
        description="Attach a ContextManager to the Agent so history is fit to the provider window before each LLM call.",
    )
    context_strategy: Literal["trimming", "summarizing"] = Field(
        default="trimming",
        description="Strategy used to fit history: 'trimming' drops oldest atomic groups; 'summarizing' compresses middle turns via the active LLM provider.",
    )
    context_max_tokens: int | None = Field(
        default=None,
        gt=0,
        description="Fallback context budget in tokens when the provider does not advertise a context_window.",
    )
    context_headroom_ratio: float = Field(
        default=0.2,
        ge=0.0,
        lt=1.0,
        description="Fraction of the provider window reserved for the model's completion (0.2 => use 80%% of the window for prompt).",
    )
    context_summary_max_tokens: int = Field(
        default=512,
        gt=0,
        description="Cap on tokens requested when the summarizing strategy generates a compression note.",
    )

    # Persistent memory backend selection
    memory_backend: Literal["memory", "sqlite"] = Field(
        default="memory",
        description="Conversation memory backend: 'memory' (in-process) or 'sqlite' (persistent).",
    )
    sqlite_memory_path: str = Field(
        default="./agent_memory.db",
        description="SQLite database path used when memory_backend='sqlite'.",
    )
    memory_max_messages: int | None = Field(
        default=None,
        description="Optional cap on stored messages per session (applies to both backends).",
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
    discord_confirmation_timeout: float = Field(
        default=60.0,
        gt=0.0,
        description="Seconds to wait for a Discord reaction-based tool approval before rejecting.",
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
    telegram_confirmation_timeout: float = Field(
        default=60.0,
        gt=0.0,
        description="Seconds to wait for a Telegram inline-button tool approval before rejecting.",
    )

    # Logging Settings
    json_logging: bool = Field(default=False, description="Enable structured JSON log format")
    log_level: str = Field(default="INFO", description="Logging level (DEBUG, INFO, WARNING, ERROR)")

    def agent_config(self) -> AgentConfig:
        """Materialize a nested AgentConfig from the flat settings values."""
        return AgentConfig(
            max_steps=self.agent_max_steps,
            tool_timeout=self.agent_tool_timeout,
            max_retries=self.agent_max_retries,
        )

    def provider_timeouts(self) -> ProviderTimeouts:
        """Resolve phase-specific timeouts with the legacy scalar as fallback."""
        scalar = self.request_timeout_seconds
        return ProviderTimeouts(
            connect=self.request_connect_timeout_seconds or scalar,
            read=self.request_read_timeout_seconds or scalar,
            write=self.request_write_timeout_seconds or scalar,
            pool=self.request_pool_timeout_seconds or scalar,
        )


# Global settings singleton helper
_global_settings: Settings | None = None


def get_settings() -> Settings:
    """Retrieve or create the global Settings instance."""
    global _global_settings
    if _global_settings is None:
        _global_settings = Settings()
    return _global_settings
