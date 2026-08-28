"""Factory for dynamic LLM provider instantiation based on configuration."""

from typing import Any

from agent_framework.auth.api_key import ApiKeyAuth
from agent_framework.auth.base import AuthenticationProvider, NoAuth
from agent_framework.auth.codex_oauth import CodexOAuthAuth, CodexOAuthToken
from agent_framework.config.settings import Settings, get_settings
from agent_framework.exceptions import ConfigurationError
from agent_framework.llm.anthropic_provider import AnthropicProvider
from agent_framework.llm.base import LLMProvider
from agent_framework.llm.nvidia_nim_provider import NvidiaNIMProvider
from agent_framework.llm.openai_compatible import OpenAICompatibleProvider
from agent_framework.llm.openai_provider import OpenAIProvider


def create_llm_provider(
    settings: Settings | None = None,
    provider_name: str | None = None,
    auth: AuthenticationProvider | None = None,
    **overrides: Any,
) -> LLMProvider:
    """Create and configure an LLMProvider based on settings.

    Args:
        settings: Application settings. If None, loaded from environment.
        provider_name: Explicit provider override (e.g. 'openai', 'anthropic', 'nvidia_nim', 'codex').
        auth: Optional explicit AuthenticationProvider instance.
        **overrides: Custom keyword overrides passed to the provider constructor.

    Returns:
        Configured LLMProvider instance.
    """
    cfg = settings or get_settings()
    target_provider = (provider_name or cfg.llm_provider).strip().lower()

    timeout = overrides.pop("timeout", cfg.request_timeout_seconds)

    if target_provider == "openai":
        provider_auth = auth or (ApiKeyAuth(cfg.openai_api_key, provider_name="openai") if cfg.openai_api_key else None)
        model = overrides.pop("model", cfg.openai_model)
        base_url = overrides.pop("base_url", cfg.openai_base_url)
        return OpenAIProvider(
            auth=provider_auth,
            model=model,
            base_url=base_url,
            timeout=timeout,
            **overrides,
        )

    if target_provider == "anthropic":
        provider_auth = auth or (
            ApiKeyAuth(cfg.anthropic_api_key, header_name="x-api-key", header_prefix="", provider_name="anthropic")
            if cfg.anthropic_api_key
            else None
        )
        model = overrides.pop("model", cfg.anthropic_model)
        return AnthropicProvider(
            auth=provider_auth,
            model=model,
            timeout=timeout,
            **overrides,
        )

    if target_provider == "nvidia_nim":
        provider_auth = auth or (
            ApiKeyAuth(cfg.nvidia_nim_api_key, provider_name="nvidia_nim")
            if cfg.nvidia_nim_api_key
            else None
        )
        model = overrides.pop("model", cfg.nvidia_nim_model)
        base_url = overrides.pop("base_url", cfg.nvidia_nim_base_url)
        return NvidiaNIMProvider(
            auth=provider_auth,
            model=model,
            base_url=base_url,
            timeout=timeout,
            **overrides,
        )

    if target_provider == "codex":
        # Codex OAuth provider configuration
        if auth is not None:
            oauth_auth = auth
        elif cfg.codex_access_token:
            token = CodexOAuthToken(
                access_token=cfg.codex_access_token,
                refresh_token=cfg.codex_refresh_token,
            )
            oauth_auth = CodexOAuthAuth(token=token)
        else:
            oauth_auth = CodexOAuthAuth()

        model = overrides.pop("model", cfg.codex_model)
        return OpenAIProvider(
            auth=oauth_auth,
            model=model,
            timeout=timeout,
            **overrides,
        )

    if target_provider in ("openai_compatible", "generic", "local", "vllm", "ollama"):
        provider_auth = auth or (
            ApiKeyAuth(cfg.openai_compatible_api_key, provider_name="openai_compatible")
            if cfg.openai_compatible_api_key
            else NoAuth()
        )
        model = overrides.pop("model", cfg.openai_compatible_model)
        base_url = overrides.pop("base_url", cfg.openai_compatible_base_url)
        return OpenAICompatibleProvider(
            name=target_provider,
            auth=provider_auth,
            model=model,
            base_url=base_url,
            timeout=timeout,
            **overrides,
        )

    raise ConfigurationError(
        message=f"Unsupported LLM provider: '{target_provider}'. "
        f"Supported providers are: 'openai', 'anthropic', 'nvidia_nim', 'codex', 'openai_compatible'.",
        details={"provider": target_provider},
    )
