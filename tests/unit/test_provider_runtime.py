"""Phase 2 capability tests for the provider runtime boundary."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

from agent_framework.exceptions import (
    FallbackExhaustedError,
    LLMProviderError,
    ProviderCapabilityError,
    ProviderUnavailableError,
)
from agent_framework.llm.base import LLMProvider
from agent_framework.llm.errors import normalize_provider_error
from agent_framework.llm.openai_compatible import OpenAICompatibleProvider
from agent_framework.llm.runtime import ProviderRuntime
from agent_framework.models.events import StreamChunk
from agent_framework.models.message import Message
from agent_framework.models.response import LLMResponse, ProviderCapabilities, ProviderTimeouts
from agent_framework.models.tool import ToolCall, ToolDefinition


class ScriptedProvider(LLMProvider):
    def __init__(
        self,
        name: str,
        outcomes: list[LLMResponse | BaseException],
        *,
        capabilities: ProviderCapabilities | None = None,
    ) -> None:
        super().__init__(name=name, model=f"{name}-model", capabilities=capabilities, max_retries=0)
        self.outcomes = outcomes
        self.calls = 0

    async def _generate_internal(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    def _parse_tool_calls(self, raw: Any) -> list[ToolCall]:
        return []

    async def health_check(self) -> bool:
        return bool(self.outcomes)


def response(provider: str, content: str = "ok") -> LLMResponse:
    return LLMResponse(content=content, provider=provider, model=f"{provider}-model")


async def test_capability_validation_happens_before_provider_call() -> None:
    provider = ScriptedProvider(
        "limited",
        [response("limited")],
        capabilities=ProviderCapabilities(system_prompt_supported=False),
    )

    with pytest.raises(ProviderCapabilityError):
        await provider.generate([Message.system("rules"), Message.user("hello")])

    assert provider.calls == 0


async def test_all_provider_failures_are_normalized_and_secrets_are_masked() -> None:
    provider = ScriptedProvider("broken", [ValueError("bad sk-supersecret123456")])

    with pytest.raises(LLMProviderError) as caught:
        await provider.generate([Message.user("hello")])

    assert "sk-supersecret123456" not in str(caught.value)
    assert "MASKED" in str(caught.value)
    assert caught.value.provider == "broken"


async def test_runtime_falls_back_without_recalling_failed_primary() -> None:
    primary = ScriptedProvider(
        "primary",
        [ProviderUnavailableError("offline", provider="primary")],
    )
    fallback = ScriptedProvider("fallback", [response("fallback", "recovered")])
    runtime = ProviderRuntime(primary, [fallback])

    result = await runtime.generate([Message.user("hello")])

    assert result.content == "recovered"
    assert result.provider == "fallback"
    assert primary.calls == 1
    assert fallback.calls == 1


async def test_runtime_reports_exhausted_fallback_chain() -> None:
    primary = ScriptedProvider("primary", [ValueError("first")])
    fallback = ScriptedProvider("fallback", [ValueError("second")])
    runtime = ProviderRuntime(primary, [fallback])

    with pytest.raises(FallbackExhaustedError) as caught:
        await runtime.generate([Message.user("hello")])

    assert caught.value.attempted_providers == ("primary", "fallback")


async def test_streaming_capability_is_checked_before_streaming() -> None:
    provider = OpenAICompatibleProvider(
        capabilities=ProviderCapabilities(streaming=False),
    )

    stream: AsyncIterator[StreamChunk] = provider.generate_stream([Message.user("hello")])
    with pytest.raises(ProviderCapabilityError):
        await anext(stream)



def test_provider_timeouts_preserve_each_http_phase() -> None:
    configured = ProviderTimeouts(connect=1.0, read=2.0, write=3.0, pool=4.0)

    timeout = configured.to_httpx()

    assert timeout.connect == 1.0
    assert timeout.read == 2.0
    assert timeout.write == 3.0
    assert timeout.pool == 4.0


def test_timeout_error_records_transport_phase() -> None:
    error = normalize_provider_error(
        httpx.ReadTimeout("late response"),
        provider="test",
        model="test-model",
    )

    assert error.details["timeout_phase"] == "read"
