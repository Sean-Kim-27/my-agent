"""Unit tests for create_llm_provider factory function."""

import pytest

from agent_framework.auth.codex_oauth import CodexOAuthAuth
from agent_framework.config.settings import Settings
from agent_framework.exceptions import ConfigurationError
from agent_framework.llm.anthropic_provider import AnthropicProvider
from agent_framework.llm.factory import create_llm_provider
from agent_framework.llm.nvidia_nim_provider import NvidiaNIMProvider
from agent_framework.llm.openai_compatible import OpenAICompatibleProvider
from agent_framework.llm.openai_provider import OpenAIProvider


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
