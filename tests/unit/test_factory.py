"""Unit tests for create_llm_provider factory function."""

import pytest

from agent_framework.auth.codex_oauth import CodexOAuthAuth
from agent_framework.config.settings import Settings
from agent_framework.exceptions import ConfigurationError
from agent_framework.llm.anthropic_provider import AnthropicProvider
from agent_framework.llm.factory import create_llm_provider, create_provider_runtime
from agent_framework.llm.nvidia_nim_provider import NvidiaNIMProvider
from agent_framework.llm.openai_compatible import OpenAICompatibleProvider
from agent_framework.llm.openai_provider import OpenAIProvider
from agent_framework.llm.runtime import ProviderRuntime
from agent_framework.models.response import ModelMetadata


def test_factory_creates_openai_provider(sample_settings: Settings) -> None:
    """Test factory instantiates OpenAIProvider."""
    provider = create_llm_provider(settings=sample_settings, provider_name="openai")
    assert isinstance(provider, OpenAIProvider)
    assert provider.name == "openai"
    assert provider.model == "gpt-4o-mini"


def test_factory_creates_anthropic_provider(sample_settings: Settings) -> None:
    """Test factory instantiates AnthropicProvider."""
    provider = create_llm_provider(settings=sample_settings, provider_name="anthropic")
    assert isinstance(provider, AnthropicProvider)
    assert provider.name == "anthropic"
    assert provider.model == "claude-3-5-sonnet-20241022"


def test_factory_creates_nvidia_nim_provider(sample_settings: Settings) -> None:
    """Test factory instantiates NvidiaNIMProvider."""
    provider = create_llm_provider(settings=sample_settings, provider_name="nvidia_nim")
    assert isinstance(provider, NvidiaNIMProvider)
    assert provider.name == "nvidia_nim"
    assert provider.base_url == "https://integrate.api.nvidia.com/v1"


def test_factory_creates_openai_compatible_provider(sample_settings: Settings) -> None:
    """Test factory instantiates OpenAICompatibleProvider for custom endpoints."""
    provider = create_llm_provider(settings=sample_settings, provider_name="openai_compatible")
    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.name == "openai_compatible"
    assert provider.base_url == "http://localhost:8000/v1"


def test_factory_creates_codex_provider(sample_settings: Settings) -> None:
    """Test factory instantiates OpenAIProvider with Codex OAuth auth."""
    provider = create_llm_provider(settings=sample_settings, provider_name="codex")
    assert isinstance(provider, OpenAIProvider)
    assert isinstance(provider.auth, CodexOAuthAuth)


def test_factory_unknown_provider_raises_error(sample_settings: Settings) -> None:
    """Test factory raises ConfigurationError for unsupported provider string."""
    with pytest.raises(ConfigurationError) as exc_info:
        create_llm_provider(settings=sample_settings, provider_name="nonexistent_provider")
    assert "Unsupported LLM provider" in str(exc_info.value)


def test_factory_applies_phase_timeouts_and_model_metadata(sample_settings: Settings) -> None:
    configured = sample_settings.model_copy(
        update={
            "request_connect_timeout_seconds": 1.0,
            "request_read_timeout_seconds": 2.0,
            "request_write_timeout_seconds": 3.0,
            "request_pool_timeout_seconds": 4.0,
            "model_metadata": {
                "openai:gpt-4o-mini": ModelMetadata(context_window=128_000, vision=False)
            },
        }
    )

    provider = create_llm_provider(configured, "openai")

    assert isinstance(provider, OpenAIProvider)
    assert provider.timeouts.connect == 1.0
    assert provider.timeouts.read == 2.0
    assert provider.timeouts.write == 3.0
    assert provider.timeouts.pool == 4.0
    assert provider.capabilities.context_window == 128_000
    assert provider.capabilities.vision is False


def test_factory_builds_ordered_fallback_runtime(sample_settings: Settings) -> None:
    configured = sample_settings.model_copy(
        update={"fallback_providers": ["anthropic", "openai_compatible"]}
    )

    runtime = create_provider_runtime(configured, "openai")

    assert isinstance(runtime, ProviderRuntime)
    assert [provider.name for provider in runtime.providers] == [
        "openai",
        "anthropic",
        "openai_compatible",
    ]


def test_factory_rejects_primary_in_fallbacks(sample_settings: Settings) -> None:
    configured = sample_settings.model_copy(update={"fallback_providers": ["openai"]})

    with pytest.raises(ConfigurationError):
        create_provider_runtime(configured, "openai")
