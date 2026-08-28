from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_framework.auth.base import NoAuth
from agent_framework.llm.base import LLMProvider
from agent_framework.llm.openai_compatible import OpenAICompatibleProvider
from agent_framework.models.events import StreamChunk
from agent_framework.models.message import Message
from agent_framework.models.response import LLMResponse
from agent_framework.models.tool import ToolDefinition


class CustomTestProvider(LLMProvider):
    """Provider testing default streaming generator implementation."""

    async def _generate_internal(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        return LLMResponse(content="Hello streamed world!")

    async def health_check(self) -> bool:
        return True


@pytest.mark.asyncio
async def test_base_provider_default_stream() -> None:
    """Test default LLMProvider generate_stream fallback."""
    provider = CustomTestProvider(name="test_provider", model="test_model")
    chunks: list[StreamChunk] = []

    async for chunk in provider.generate_stream([Message.user("Hi")]):
        chunks.append(chunk)

    assert len(chunks) == 2
    assert chunks[0].content == "Hello streamed world!"
    assert chunks[0].is_finished is False
    assert chunks[1].is_finished is True


@pytest.mark.asyncio
async def test_openai_compatible_native_streaming() -> None:
    """Test OpenAI-compatible native streaming chunks."""
    mock_client = AsyncMock()

    # Create mock chunk iterator
    chunk1 = MagicMock()
    chunk1.choices = [MagicMock(delta=MagicMock(content="Hello"))]

    chunk2 = MagicMock()
    chunk2.choices = [MagicMock(delta=MagicMock(content=" from stream!"))]

    async def mock_stream_generator() -> object:
        for c in [chunk1, chunk2]:
            yield c

    mock_client.chat.completions.create = AsyncMock(return_value=mock_stream_generator())

    provider = OpenAICompatibleProvider(
        name="test_openai",
        model="gpt-4o-mini",
        auth=NoAuth(),
        client=mock_client,
    )

    collected_text = ""
    is_finished = False

    async for chunk in provider.generate_stream([Message.user("Hello")]):
        collected_text += chunk.content
        if chunk.is_finished:
            is_finished = True

    assert collected_text == "Hello from stream!"
    assert is_finished is True
