"""Provider orchestration boundary for retry-safe fallback and health reporting."""

from __future__ import annotations

from typing import Any

from agent_framework.exceptions import FallbackExhaustedError, LLMProviderError
from agent_framework.llm.base import LLMProvider
from agent_framework.models.message import Message
from agent_framework.models.response import LLMResponse, ProviderCapabilities
from agent_framework.models.tool import ToolCall, ToolDefinition


class ProviderRuntime(LLMProvider):
    """Try a primary provider and configured fallbacks for one generation boundary.

    The runtime never restarts an Agent run and never executes tools. A provider
    response is returned once; only the Agent owns subsequent tool execution.
    """

    def __init__(self, primary: LLMProvider, fallbacks: list[LLMProvider] | None = None) -> None:
        providers = [primary, *(fallbacks or [])]
        if len({provider.name for provider in providers}) != len(providers):
            raise ValueError("Provider fallback chain cannot contain duplicate provider names")
        self.providers = tuple(providers)
        combined = ProviderCapabilities(
            tool_calling=any(p.capabilities.tool_calling for p in providers),
            streaming=any(p.capabilities.streaming for p in providers),
            vision=any(p.capabilities.vision for p in providers),
            json_mode=any(p.capabilities.json_mode for p in providers),
            system_prompt_supported=any(p.capabilities.system_prompt_supported for p in providers),
            context_window=max(
                (p.capabilities.context_window or 0 for p in providers),
                default=0,
            )
            or None,
        )
        super().__init__(
            name="provider_runtime",
            model=primary.model,
            capabilities=combined,
            max_retries=0,
        )

    @property
    def primary(self) -> LLMProvider:
        return self.providers[0]

    async def _generate_internal(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        errors: list[tuple[str, LLMProviderError]] = []
        for provider in self.providers:
            try:
                return await provider.generate(messages, tools=tools, **kwargs)
            except LLMProviderError as exc:
                errors.append((provider.name, exc))

        attempted = tuple(name for name, _ in errors)
        summaries = [f"{name}: {type(error).__name__}" for name, error in errors]
        raise FallbackExhaustedError(
            "All configured LLM providers failed: " + ", ".join(summaries),
            attempted_providers=attempted,
        )

    def _parse_tool_calls(self, raw: Any) -> list[ToolCall]:
        return []

    async def health_check(self) -> bool:
        results = [await provider.health_check() for provider in self.providers]
        return any(results)

    async def health_report(self) -> dict[str, bool]:
        """Return a concrete provider-by-provider health snapshot."""
        return {
            provider.name: await provider.health_check()
            for provider in self.providers
        }
