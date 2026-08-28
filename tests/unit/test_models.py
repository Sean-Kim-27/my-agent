"""Unit tests for models package (Message, LLMResponse, Tool contracts)."""


from agent_framework.models.message import Message, MessageRole
from agent_framework.models.response import LLMResponse, TokenUsage
from agent_framework.models.tool import (
    ToolCall,
    ToolCallResult,
    ToolDefinition,
    ToolParameterSchema,
)


def test_message_creation_factories() -> None:
    """Test standard factory methods for Message creation."""
    sys_msg = Message.system("System prompt instructions")
    assert sys_msg.role == MessageRole.SYSTEM
    assert sys_msg.content == "System prompt instructions"

    user_msg = Message.user("Hello world")
    assert user_msg.role == MessageRole.USER
    assert user_msg.content == "Hello world"

    asst_msg = Message.assistant("Hello user")
    assert asst_msg.role == MessageRole.ASSISTANT
    assert asst_msg.content == "Hello user"

    tool_msg = Message.tool(content="25C Sunny", tool_call_id="call_123", name="get_weather")
    assert tool_msg.role == MessageRole.TOOL
    assert tool_msg.content == "25C Sunny"
    assert tool_msg.tool_call_id == "call_123"
    assert tool_msg.name == "get_weather"


def test_message_serialization() -> None:
    """Test model serialization to dict."""
    msg = Message.user("Test message", user_id="123")
    dumped = msg.to_dict()
    assert dumped["role"] == "user"
    assert dumped["content"] == "Test message"
    assert dumped["metadata"] == {"user_id": "123"}
    assert "created_at" in dumped


def test_llm_response_conversion_to_message() -> None:
    """Test converting an LLMResponse into an assistant Message."""
    tool_call = ToolCall(id="tc_1", name="search", arguments={"query": "python"})
    resp = LLMResponse(
        content="I will search for python.",
        role=MessageRole.ASSISTANT,
        tool_calls=[tool_call],
        usage=TokenUsage(prompt_tokens=10, completion_tokens=8, total_tokens=18),
        model="test-model",
        provider="mock",
        latency_ms=120.5,
        finish_reason="tool_calls",
    )

    assert resp.has_tool_calls is True
    assert len(resp.tool_calls) == 1

    msg = resp.to_message()
    assert msg.role == MessageRole.ASSISTANT
    assert msg.content == "I will search for python."
    assert msg.tool_calls is not None
    assert len(msg.tool_calls) == 1
    assert msg.tool_calls[0].name == "search"
    assert msg.metadata["provider"] == "mock"
    assert msg.metadata["latency_ms"] == 120.5


def test_tool_definition_contract() -> None:
    """Test ToolDefinition schema creation for Phase 0 contract."""
    param_schema = ToolParameterSchema(
        properties={"city": {"type": "string", "description": "City name"}},
        required=["city"],
    )
    tool_def = ToolDefinition(
        name="get_weather",
        description="Fetch current weather for a city",
        parameters=param_schema,
    )

    assert tool_def.name == "get_weather"
    assert tool_def.description == "Fetch current weather for a city"
    assert isinstance(tool_def.parameters, ToolParameterSchema)
    assert "city" in tool_def.parameters.properties

    # Tool call and result contracts
    call = ToolCall(id="call_99", name="get_weather", arguments={"city": "Seoul"})
    assert call.id == "call_99"
    assert call.arguments == {"city": "Seoul"}

    result = ToolCallResult(tool_call_id="call_99", name="get_weather", content="18C Clear")
    assert result.is_error is False
    assert result.content == "18C Clear"
