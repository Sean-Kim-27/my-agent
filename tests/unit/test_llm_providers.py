"""Unit tests for LLM providers (OpenAI, Anthropic, NVIDIA NIM, OpenAI-Compatible)."""

from unittest.mock import AsyncMock, MagicMock

import openai
import pytest

from agent_framework.auth.api_key import ApiKeyAuth
from agent_framework.auth.codex_oauth import CodexOAuthAuth, CodexOAuthToken
from agent_framework.exceptions import (
    RateLimitError,
)
from agent_framework.llm.anthropic_provider import AnthropicProvider
from agent_framework.llm.nvidia_nim_provider import NvidiaNIMProvider
from agent_framework.llm.openai_compatible import OpenAICompatibleProvider
from agent_framework.llm.openai_provider import OpenAIProvider
from agent_framework.models.message import Message
from agent_framework.models.tool import ToolCall


@pytest.mark.asyncio
async def test_openai_compatible_message_conversion() -> None:
    """Test standard Message conversion to OpenAI format."""
    provider = OpenAICompatibleProvider(
        name="test_compat",
        base_url="http://localhost:8000/v1",
        auth=ApiKeyAuth("test-key"),
    )

    messages = [
        Message.system("You are a helpful assistant."),
        Message.user("Hello!"),
        Message.assistant(
            content=None,
            tool_calls=[ToolCall(id="call_1", name="search", arguments={"q": "news"})],
        ),
        Message.tool(content="News items", tool_call_id="call_1"),
    ]

    converted = provider._convert_messages(messages)
    assert len(converted) == 4
    assert converted[0] == {"role": "system", "content": "You are a helpful assistant."}
    assert converted[1] == {"role": "user", "content": "Hello!"}
    assert converted[2]["role"] == "assistant"
    assert converted[2]["tool_calls"][0]["function"]["name"] == "search"
    assert converted[3] == {"role": "tool", "content": "News items", "tool_call_id": "call_1"}


@pytest.mark.asyncio
async def test_openai_compatible_successful_generation() -> None:
    """Test successful generation and response parsing with mocked AsyncOpenAI."""
    mock_client = AsyncMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "OpenAI response text"
    mock_choice.message.role = "assistant"
    mock_choice.message.tool_calls = None
    mock_choice.finish_reason = "stop"

    mock_raw_resp = MagicMock()
    mock_raw_resp.choices = [mock_choice]
    mock_raw_resp.model = "gpt-4o-mini"
    mock_raw_resp.usage.prompt_tokens = 12
    mock_raw_resp.usage.completion_tokens = 6
    mock_raw_resp.usage.total_tokens = 18

    mock_client.chat.completions.create.return_value = mock_raw_resp

    provider = OpenAICompatibleProvider(
        name="openai_compat",
        model="gpt-4o-mini",
        client=mock_client,
    )

    response = await provider.generate([Message.user("Hello")])
    assert response.content == "OpenAI response text"
    assert response.provider == "openai_compat"
    assert response.model == "gpt-4o-mini"
    assert response.usage is not None
    assert response.usage.total_tokens == 18
    assert response.latency_ms > 0


@pytest.mark.asyncio
async def test_openai_compatible_error_wrapping() -> None:
    """Test that raw OpenAI SDK exceptions are wrapped in framework exceptions."""
    mock_client = AsyncMock()
    mock_client.chat.completions.create.side_effect = openai.RateLimitError(
        message="Rate limit reached",
        response=MagicMock(status_code=429, headers={}),
        body=None,
    )

    provider = OpenAICompatibleProvider(client=mock_client)

    with pytest.raises(RateLimitError) as exc_info:
        await provider.generate([Message.user("Hello")])
    assert "Rate limit" in str(exc_info.value)
    assert exc_info.value.status_code == 429


@pytest.mark.asyncio
async def test_openai_provider_with_oauth() -> None:
    """Test OpenAIProvider configuration with Codex OAuth."""
    token = CodexOAuthToken(access_token="codex_token_123")
    auth = CodexOAuthAuth(token=token)
    provider = OpenAIProvider(auth=auth, model="gpt-4o")

    assert provider.name == "openai"
    assert provider.model == "gpt-4o"
    assert provider.auth == auth


@pytest.mark.asyncio
async def test_nvidia_nim_provider_defaults() -> None:
    """Test NvidiaNIMProvider default configurations."""
    provider = NvidiaNIMProvider(api_key="nvapi-test-key")
    assert provider.name == "nvidia_nim"
    assert provider.base_url == "https://integrate.api.nvidia.com/v1"
    assert provider.model == "meta/llama-3.1-70b-instruct"


@pytest.mark.asyncio
async def test_anthropic_message_conversion() -> None:
    """Test Anthropic message formatting with system prompt extraction."""
    provider = AnthropicProvider(api_key="sk-ant-test")
    messages = [
        Message.system("Be concise."),
        Message.user("What is Python?"),
        Message.assistant("A programming language."),
    ]

    system_prompt, formatted = provider._convert_messages(messages)
    assert system_prompt == "Be concise."
    assert len(formatted) == 2
    assert formatted[0] == {"role": "user", "content": "What is Python?"}
    assert formatted[1] == {"role": "assistant", "content": "A programming language."}


@pytest.mark.asyncio
async def test_anthropic_successful_generation() -> None:
    """Test successful Anthropic response parsing with mocked AsyncAnthropic."""
    mock_client = AsyncMock()
    mock_text_block = MagicMock()
    mock_text_block.type = "text"
    mock_text_block.text = "Hello from Claude!"

    mock_raw_resp = MagicMock()
    mock_raw_resp.content = [mock_text_block]
    mock_raw_resp.model = "claude-3-5-sonnet-20241022"
    mock_raw_resp.stop_reason = "end_turn"
    mock_raw_resp.usage.input_tokens = 15
    mock_raw_resp.usage.output_tokens = 8

    mock_client.messages.create.return_value = mock_raw_resp

    provider = AnthropicProvider(
        api_key="sk-ant-test",
        client=mock_client,
    )

    response = await provider.generate([Message.user("Hello")])
    assert response.content == "Hello from Claude!"
    assert response.provider == "anthropic"
    assert response.model == "claude-3-5-sonnet-20241022"
    assert response.usage is not None
    assert response.usage.total_tokens == 23


@pytest.mark.asyncio
async def test_openai_tool_conversion_and_parsing() -> None:
    """Test OpenAI tools parameter formatting and tool_calls response parsing."""
    from agent_framework.models.tool import ToolDefinition, ToolParameterSchema

    mock_client = AsyncMock()
    mock_choice = MagicMock()
    mock_choice.message.content = None
    mock_choice.message.role = "assistant"

    mock_tool_call = MagicMock()
    mock_tool_call.id = "call_abc123"
    mock_tool_call.function.name = "get_weather"
    mock_tool_call.function.arguments = '{"city": "Paris"}'

    mock_choice.message.tool_calls = [mock_tool_call]
    mock_choice.finish_reason = "tool_calls"

    mock_raw_resp = MagicMock()
    mock_raw_resp.choices = [mock_choice]
    mock_raw_resp.model = "gpt-4o-mini"
    mock_raw_resp.usage = None

    mock_client.chat.completions.create.return_value = mock_raw_resp

    provider = OpenAICompatibleProvider(client=mock_client)
    tool_def = ToolDefinition(
        name="get_weather",
        description="Get city weather",
        parameters=ToolParameterSchema(
            properties={"city": {"type": "string"}},
            required=["city"],
        ),
    )

    response = await provider.generate(
        [Message.user("Weather in Paris?")],
        tools=[tool_def],
    )

    assert response.has_tool_calls is True
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].id == "call_abc123"
    assert response.tool_calls[0].name == "get_weather"
    assert response.tool_calls[0].arguments == {"city": "Paris"}

    # Verify tools was passed to client call
    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert "tools" in call_kwargs
    assert call_kwargs["tools"][0]["function"]["name"] == "get_weather"


@pytest.mark.asyncio
async def test_anthropic_tool_conversion_and_parsing() -> None:
    """Test Anthropic tools parameter formatting and tool_use response parsing."""
    from agent_framework.models.tool import ToolDefinition, ToolParameterSchema

    mock_client = AsyncMock()
    mock_tool_block = MagicMock()
    mock_tool_block.type = "tool_use"
    mock_tool_block.id = "toolu_123"
    mock_tool_block.name = "calculate"
    mock_tool_block.input = {"expression": "2+2"}

    mock_raw_resp = MagicMock()
    mock_raw_resp.content = [mock_tool_block]
    mock_raw_resp.model = "claude-3-5-sonnet-20241022"
    mock_raw_resp.stop_reason = "tool_use"
    mock_raw_resp.usage = None

    mock_client.messages.create.return_value = mock_raw_resp

    provider = AnthropicProvider(api_key="sk-ant-test", client=mock_client)
    tool_def = ToolDefinition(
        name="calculate",
        description="Evaluate math",
        parameters=ToolParameterSchema(
            properties={"expression": {"type": "string"}},
            required=["expression"],
        ),
    )

    response = await provider.generate(
        [Message.user("Calculate 2+2")],
        tools=[tool_def],
    )

    assert response.has_tool_calls is True
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].id == "toolu_123"
    assert response.tool_calls[0].name == "calculate"
    assert response.tool_calls[0].arguments == {"expression": "2+2"}

    # Verify tools was passed to client call
    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert "tools" in call_kwargs
    assert call_kwargs["tools"][0]["name"] == "calculate"
    assert call_kwargs["tools"][0]["input_schema"]["type"] == "object"
