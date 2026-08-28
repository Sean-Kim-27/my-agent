"""Unit tests for Agent multi-step tool execution loop."""

import pytest

from agent_framework.agent.agent import Agent
from agent_framework.exceptions import AgentError
from agent_framework.models.message import MessageRole
from agent_framework.models.response import LLMResponse
from agent_framework.models.tool import ToolCall
from agent_framework.tools.registry import ToolRegistry
from tests.conftest import MockLLMProvider


@pytest.mark.asyncio
async def test_agent_single_step_tool_loop(mock_provider: MockLLMProvider) -> None:
    """Test user -> model calls tool -> tool executes -> model returns final answer."""
    registry = ToolRegistry()

    @registry.tool(description="Get current temperature for city")
    def get_weather(city: str) -> str:
        return f"{city} is 22C and sunny"

    # Step 1: Model requests get_weather tool
    tool_call_resp = LLMResponse(
        content="I will check the weather for Seoul.",
        role=MessageRole.ASSISTANT,
        tool_calls=[ToolCall(id="call_weather_1", name="get_weather", arguments={"city": "Seoul"})],
        finish_reason="tool_calls",
        provider=mock_provider.name,
        model=mock_provider.model,
    )
    # Step 2: Model gives final answer after receiving tool result
    final_resp = LLMResponse(
        content="The weather in Seoul is 22C and sunny.",
        role=MessageRole.ASSISTANT,
        tool_calls=[],
        finish_reason="stop",
        provider=mock_provider.name,
        model=mock_provider.model,
    )
    mock_provider.response_queue = [tool_call_resp, final_resp]

    agent = Agent(
        provider=mock_provider,
        tool_registry=registry,
        default_session_id="test:tool_loop",
    )

    response = await agent.run("What is the weather in Seoul?")

    assert response.content == "The weather in Seoul is 22C and sunny."
    assert len(mock_provider.calls) == 2

    # Verify message sequence in session memory:
    # 1. User: "What is the weather in Seoul?"
    # 2. Assistant: Tool call request
    # 3. Tool: Tool result
    # 4. Assistant: Final response
    history = await agent.get_session_history("test:tool_loop")
    assert len(history) == 4
    assert history[0].role == MessageRole.USER
    assert history[1].role == MessageRole.ASSISTANT
    assert history[1].tool_calls is not None
    assert history[1].tool_calls[0].name == "get_weather"
    assert history[2].role == MessageRole.TOOL
    assert "22C and sunny" in history[2].content  # type: ignore[operator]
    assert history[3].role == MessageRole.ASSISTANT
    assert history[3].content == "The weather in Seoul is 22C and sunny."


@pytest.mark.asyncio
async def test_agent_multi_step_tool_loop(mock_provider: MockLLMProvider) -> None:
    """Test multiple consecutive tool calls across multiple steps."""
    registry = ToolRegistry()

    @registry.tool()
    def get_city(country: str) -> str:
        return "Tokyo" if country == "Japan" else "Unknown"

    @registry.tool()
    def get_population(city: str) -> str:
        return "14 million" if city == "Tokyo" else "Unknown"

    # Step 1: LLM calls get_city
    step1_resp = LLMResponse(
        content="Looking up capital of Japan...",
        role=MessageRole.ASSISTANT,
        tool_calls=[ToolCall(id="tc_1", name="get_city", arguments={"country": "Japan"})],
        provider=mock_provider.name,
    )
    # Step 2: LLM calls get_population
    step2_resp = LLMResponse(
        content="Looking up population for Tokyo...",
        role=MessageRole.ASSISTANT,
        tool_calls=[ToolCall(id="tc_2", name="get_population", arguments={"city": "Tokyo"})],
        provider=mock_provider.name,
    )
    # Step 3: LLM final answer
    step3_resp = LLMResponse(
        content="The capital of Japan is Tokyo with a population of 14 million.",
        role=MessageRole.ASSISTANT,
        provider=mock_provider.name,
    )

    mock_provider.response_queue = [step1_resp, step2_resp, step3_resp]

    agent = Agent(
        provider=mock_provider,
        tool_registry=registry,
        default_session_id="test:multi_step",
    )

    response = await agent.run("What is the capital of Japan and its population?")
    assert "14 million" in response.content  # type: ignore[operator]
    assert len(mock_provider.calls) == 3

    history = await agent.get_session_history("test:multi_step")
    # History: User -> Asst(tc_1) -> Tool(res_1) -> Asst(tc_2) -> Tool(res_2) -> Asst(final)
    assert len(history) == 6


@pytest.mark.asyncio
async def test_agent_max_steps_exceeded(mock_provider: MockLLMProvider) -> None:
    """Test that agent raises AgentError when max_steps is exceeded."""
    registry = ToolRegistry()

    @registry.tool()
    def infinite_tool() -> str:
        return "looping"

    # Infinite loop of tool calls
    mock_provider.response_queue = [
        LLMResponse(
            content=f"Loop {i}",
            role=MessageRole.ASSISTANT,
            tool_calls=[ToolCall(id=f"tc_{i}", name="infinite_tool", arguments={})],
            provider=mock_provider.name,
        )
        for i in range(10)
    ]

    agent = Agent(
        provider=mock_provider,
        tool_registry=registry,
        max_steps=3,
        default_session_id="test:max_steps",
    )

    with pytest.raises(AgentError) as exc_info:
        await agent.run("Start infinite loop")
    assert "exceeded maximum execution steps" in str(exc_info.value)
