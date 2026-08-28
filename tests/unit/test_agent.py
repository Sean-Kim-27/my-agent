"""Unit tests for Agent orchestrator."""

import pytest

from agent_framework.agent.agent import Agent
from agent_framework.exceptions import AgentError, LLMProviderError
from agent_framework.models.message import MessageRole
from tests.conftest import MockLLMProvider


@pytest.mark.asyncio
async def test_agent_run_basic(mock_provider: MockLLMProvider) -> None:
    """Test standard single turn agent execution."""
    agent = Agent(
        provider=mock_provider,
        system_prompt="You are a helpful assistant.",
        default_session_id="test:1",
    )

    response = await agent.run("What is 2+2?")
    assert response.content == "Hello from mock provider!"

    # Verify context passed to provider
    assert len(mock_provider.calls) == 1
    call_messages = mock_provider.calls[0]
    assert len(call_messages) == 2
    assert call_messages[0].role == MessageRole.SYSTEM
    assert call_messages[0].content == "You are a helpful assistant."
    assert call_messages[1].role == MessageRole.USER
    assert call_messages[1].content == "What is 2+2?"

    # Verify memory contains user input and assistant response
    history = await agent.get_session_history("test:1")
    assert len(history) == 2
    assert history[0].role == MessageRole.USER
    assert history[0].content == "What is 2+2?"
    assert history[1].role == MessageRole.ASSISTANT
    assert history[1].content == "Hello from mock provider!"


@pytest.mark.asyncio
async def test_agent_multi_turn_memory(mock_provider: MockLLMProvider) -> None:
    """Test multi-turn conversation retains context across calls."""
    agent = Agent(
        provider=mock_provider,
        system_prompt="System instructions.",
        default_session_id="test:multiturn",
    )

    # Turn 1
    mock_provider.default_response_text = "Turn 1 answer"
    await agent.run("Turn 1 question")

    # Turn 2
    mock_provider.default_response_text = "Turn 2 answer"
    await agent.run("Turn 2 question")

    assert len(mock_provider.calls) == 2
    # In Turn 2, provider should receive system + turn1 user + turn1 asst + turn2 user
    turn2_messages = mock_provider.calls[1]
    assert len(turn2_messages) == 4
    assert turn2_messages[0].role == MessageRole.SYSTEM
    assert turn2_messages[1].content == "Turn 1 question"
    assert turn2_messages[2].content == "Turn 1 answer"
    assert turn2_messages[3].content == "Turn 2 question"


@pytest.mark.asyncio
async def test_agent_empty_input_rejected(mock_provider: MockLLMProvider) -> None:
    """Test that empty string input raises AgentError."""
    agent = Agent(provider=mock_provider)
    with pytest.raises(AgentError) as exc_info:
        await agent.run("   ")
    assert "User input cannot be empty" in str(exc_info.value)


@pytest.mark.asyncio
async def test_agent_provider_error_handling(mock_provider: MockLLMProvider) -> None:
    """Test that provider errors bubble up without crashing the agent instance."""
    mock_provider.should_fail_with = LLMProviderError("Upstream API is down", provider="mock")
    agent = Agent(provider=mock_provider)

    with pytest.raises(LLMProviderError) as exc_info:
        await agent.run("Hello")
    assert "Upstream API is down" in str(exc_info.value)


@pytest.mark.asyncio
async def test_agent_session_clear(mock_provider: MockLLMProvider) -> None:
    """Test clearing session history via agent."""
    agent = Agent(provider=mock_provider, default_session_id="test:clear")
    await agent.run("Test message")
    assert len(await agent.get_session_history()) == 2

    await agent.clear_session()
    assert len(await agent.get_session_history()) == 0
