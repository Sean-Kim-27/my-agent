"""Abstract LLM Provider interface and base provider abstractions."""

import time
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

from agent_framework.models.events import StreamChunk
from agent_framework.models.message import Message
from agent_framework.models.response import LLMResponse, ProviderCapabilities
from agent_framework.models.tool import ToolDefinition


class LLMProvider(ABC):
    """Abstract interface for all LLM providers (OpenAI, Anthropic, NVIDIA NIM, etc.)."""

    def __init__(
        self,
        name: str,
        model: str,
        capabilities: ProviderCapabilities | None = None,
    ) -> None:
        self.name = name
        self.model = model
        self.capabilities = capabilities or ProviderCapabilities()

    @abstractmethod
    async def _generate_internal(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Internal provider-specific generation logic."""

    async def generate(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Public generate method wrapping execution with latency tracking."""
        start_time = time.perf_counter()
        response = await self._generate_internal(messages, tools=tools, **kwargs)
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        # If the provider didn't set latency or set it to 0, populate it
        if response.latency_ms <= 0:
            response.latency_ms = round(elapsed_ms, 2)
        if response.provider == "unknown":
            response.provider = self.name
        if response.model == "unknown":
            response.model = self.model
        return response

    async def generate_stream(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        """Stream response tokens as an asynchronous generator.

        Default implementation falls back to non-streaming generate() yielding
        a content chunk followed by a finish marker. Subclasses can override
        for native token-by-token streaming.
        """
        response = await self.generate(messages, tools=tools, **kwargs)
        if response.content:
            yield StreamChunk(content=response.content, is_finished=False)
        yield StreamChunk(content="", is_finished=True)

    @abstractmethod
    async def health_check(self) -> bool:
        """Check whether the provider endpoint is healthy and accessible."""
