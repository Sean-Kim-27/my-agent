"""Pytest fixtures and test helpers."""

from typing import Any

import pytest

from agent_framework.config.settings import Settings
from agent_framework.llm.base import LLMProvider
from agent_framework.models.message import Message
from agent_framework.models.response import LLMResponse, ProviderCapabilities, TokenUsage
from agent_framework.models.tool import ToolCall, ToolDefinition


class MockLLMProvider(LLMProvider):
    """Mock LLM Provider for unit testing without live API network calls."""

    def __init__(
        self,
        name: str = "mock_provider",
        model: str = "mock-model-v1",
        default_response_text: str = "Hello from mock provider!",
        capabilities: ProviderCapabilities | None = None,
    ) -> None:
        super().__init__(
            name=name,
            model=model,
            capabilities=capabilities
            or ProviderCapabilities(tool_calling=True, streaming=True),
        )
        self.default_response_text = default_response_text
        self.calls: list[list[Message]] = []
        self.tools_received: list[list[ToolDefinition] | None] = []
        self.response_queue: list[LLMResponse] = []
        self.should_fail_with: Exception | None = None

    async def _generate_internal(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        self.calls.append(list(messages))
        self.tools_received.append(tools)
        if self.should_fail_with is not None:
            raise self.should_fail_with

        if self.response_queue:
            return self.response_queue.pop(0)

        return LLMResponse(
            content=self.default_response_text,
            role="assistant",
            usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            model=self.model,
            provider=self.name,
            finish_reason="stop",
        )

    def _parse_tool_calls(self, raw: Any) -> list[ToolCall]:
        if isinstance(raw, list):
            return list(raw)
        return []

    async def health_check(self) -> bool:
        return self.should_fail_with is None


@pytest.fixture
def mock_provider() -> MockLLMProvider:
    """Fixture providing a clean MockLLMProvider instance."""
    return MockLLMProvider()


@pytest.fixture
def sample_settings() -> Settings:
    """Fixture providing isolated Settings with mock keys."""
    return Settings(
        llm_provider="openai",
        openai_api_key="sk-test-openai-1234567890",
        openai_model="gpt-4o-mini",
        anthropic_api_key="sk-ant-test-1234567890",
        anthropic_model="claude-3-5-sonnet-20241022",
        nvidia_nim_api_key="nvapi-test-1234567890",
        nvidia_nim_model="meta/llama-3.1-70b-instruct",
        openai_compatible_api_key="test-key",
        openai_compatible_base_url="http://localhost:8000/v1",
        openai_compatible_model="test-compat-model",
        agent_system_prompt="You are a test assistant.",
        default_session_id="test:session:1",
        request_timeout_seconds=5.0,
    )
