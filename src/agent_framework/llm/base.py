"""Abstract LLM Provider interface and base provider abstractions."""

import time
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

from agent_framework.exceptions import ProviderCapabilityError
from agent_framework.llm.errors import normalize_provider_error
from agent_framework.llm.retry import call_with_retry
from agent_framework.models.events import StreamChunk
from agent_framework.models.message import Message
from agent_framework.models.response import LLMResponse, ProviderCapabilities
from agent_framework.models.tool import ToolCall, ToolDefinition


class LLMProvider(ABC):
    """Abstract interface for all LLM providers (OpenAI, Anthropic, NVIDIA NIM, etc.)."""

    def __init__(
        self,
        name: str,
        model: str,
        capabilities: ProviderCapabilities | None = None,
        max_retries: int = 3,
    ) -> None:
        self.name = name
        self.model = model
        self.capabilities = capabilities or ProviderCapabilities()
        self.max_retries = max_retries

    @abstractmethod
    async def _generate_internal(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Internal provider-specific generation logic."""

    @abstractmethod
    def _parse_tool_calls(self, raw: Any) -> list[ToolCall]:
        """Normalize a provider-specific raw response object into ``ToolCall`` list.

        Subclasses must implement this so ``ToolCall`` normalization is enforced
        by the type system rather than relying on convention. The concrete input
        type is provider-specific (e.g. an OpenAI ``ChatCompletion`` message or
        an Anthropic ``Message`` content-block list); returning an empty list is
        valid when no tool calls were requested.
        """

    async def generate(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Public generate method wrapping execution with latency tracking and retry."""
        self.validate_request(messages, tools=tools, **kwargs)
        start_time = time.perf_counter()

        async def _normalized_call() -> LLMResponse:
            try:
                return await self._generate_internal(messages, tools=tools, **kwargs)
            except Exception as exc:
                raise normalize_provider_error(
                    exc,
                    provider=self.name,
                    model=str(kwargs.get("model", self.model)),
                ) from exc

        response: LLMResponse = await call_with_retry(
            _normalized_call,
            max_retries=self.max_retries,
        )
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        # If the provider didn't set latency or set it to 0, populate it
        if response.latency_ms <= 0:
            response.latency_ms = round(elapsed_ms, 2)
        if response.provider == "unknown":
            response.provider = self.name
        if response.model == "unknown":
            response.model = self.model
        return response

    def validate_request(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> None:
        """Fail before network I/O when a request needs an unsupported capability."""
        missing: list[str] = []
        if tools and not self.capabilities.tool_calling:
            missing.append("tool_calling")
        if any(str(message.role) in {"system", "MessageRole.SYSTEM"} for message in messages):
            if not self.capabilities.system_prompt_supported:
                missing.append("system_prompt")
        if any(key in kwargs for key in ("response_format", "json_schema", "json_mode")):
            if not self.capabilities.json_mode:
                missing.append("json_mode")
        if missing:
            raise ProviderCapabilityError(
                message=(
                    f"Provider '{self.name}' model '{self.model}' does not support "
                    f"required capability/capabilities: {', '.join(missing)}"
                ),
                provider=self.name,
                model=self.model,
                details={"missing_capabilities": missing},
            )

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

    def validate_streaming(self) -> None:
        """Validate streaming support before an SDK request is created."""
        if not self.capabilities.streaming:
            raise ProviderCapabilityError(
                message=f"Provider '{self.name}' model '{self.model}' does not support streaming",
                provider=self.name,
                model=self.model,
                details={"missing_capabilities": ["streaming"]},
            )

    @abstractmethod
    async def health_check(self) -> bool:
        """Check whether the provider endpoint is healthy and accessible."""
