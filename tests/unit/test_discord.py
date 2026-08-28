"""Unit tests for Discord Bot integration, router, filtering, and safe chunking."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_framework.agent.agent import Agent
from agent_framework.config.settings import Settings
from agent_framework.integrations.discord.bot import DiscordAgentBot
from agent_framework.integrations.discord.router import (
    extract_clean_content,
    generate_session_id,
    should_process_message,
    split_message_content,
)
from tests.conftest import MockLLMProvider


def test_discord_session_id_generation() -> None:
    """Test session ID generation for DM, channel, and thread contexts."""
    # DM
    dm_session = generate_session_id(author_id=123, channel_id=456, is_dm=True)
    assert dm_session == "discord:dm:123"

    # Guild Channel
    channel_session = generate_session_id(
        author_id=123,
        channel_id=456,
        guild_id=789,
    )
    assert channel_session == "discord:guild:789:channel:456:user:123"

    # Guild Thread
    thread_session = generate_session_id(
        author_id=123,
        channel_id=456,
        guild_id=789,
        thread_id=999,
    )
    assert thread_session == "discord:guild:789:thread:999:user:123"


def test_extract_clean_content() -> None:
    """Test stripping mention tags from message content."""
    assert extract_clean_content("<@123456789> Hello agent!", bot_user_id=123456789) == "Hello agent!"
    assert extract_clean_content("<@!123456789> What time is it?", bot_user_id=123456789) == "What time is it?"
    assert extract_clean_content("Plain text without mention") == "Plain text without mention"


def test_should_process_message_filters() -> None:
    """Test filtering rules for Discord messages."""
    bot_id = 999
    user_id = 111
    channel_id = 222
    guild_id = 333

    # 1. Ignore if author is a bot
    assert should_process_message(
        author_id=user_id,
        is_bot=True,
        channel_id=channel_id,
        guild_id=guild_id,
        bot_user_id=bot_id,
        mentions_bot=True,
    ) is False

    # 2. Ignore if author is the bot itself
    assert should_process_message(
        author_id=bot_id,
        is_bot=False,
        channel_id=channel_id,
        guild_id=guild_id,
        bot_user_id=bot_id,
        mentions_bot=True,
    ) is False

    # 3. Channel whitelist filter
    assert should_process_message(
        author_id=user_id,
        is_bot=False,
        channel_id=channel_id,
        guild_id=guild_id,
        bot_user_id=bot_id,
        mentions_bot=True,
        allowed_channels=[888, 777],  # channel_id 222 not in list
    ) is False

    # 4. DM always processes without mention
    assert should_process_message(
        author_id=user_id,
        is_bot=False,
        channel_id=channel_id,
        guild_id=None,
        bot_user_id=bot_id,
        mentions_bot=False,
        is_dm=True,
    ) is True

    # 5. Guild message requires mention when require_mention=True
    assert should_process_message(
        author_id=user_id,
        is_bot=False,
        channel_id=channel_id,
        guild_id=guild_id,
        bot_user_id=bot_id,
        mentions_bot=False,
        require_mention=True,
    ) is False

    # 6. Guild message processes when mention is provided
    assert should_process_message(
        author_id=user_id,
        is_bot=False,
        channel_id=channel_id,
        guild_id=guild_id,
        bot_user_id=bot_id,
        mentions_bot=True,
        require_mention=True,
    ) is True


def test_split_message_content() -> None:
    """Test splitting long messages into <= 2000 character chunks."""
    # Short message
    short_text = "Hello world"
    assert split_message_content(short_text, max_chunk_size=2000) == [short_text]

    # Empty text
    assert split_message_content("") == []

    # Long message splitting
    long_para = "This is a sentence. " * 150  # ~3000 characters
    chunks = split_message_content(long_para, max_chunk_size=1000)
    assert len(chunks) >= 3
    assert all(len(c) <= 1000 for c in chunks)

    # Long message inside markdown code block
    code_block = "```python\n" + ("x = 1\n" * 100) + "```"  # ~700 characters
    code_chunks = split_message_content(code_block, max_chunk_size=300)
    assert len(code_chunks) >= 3
    # Verify first chunk closes with ``` and second chunk starts with ```python
    assert code_chunks[0].endswith("```")
    assert code_chunks[1].startswith("```python")


@pytest.mark.asyncio
async def test_discord_bot_on_message_and_queue_worker() -> None:
    """Test DiscordAgentBot message receiving, enqueuing, and async worker execution."""
    mock_provider = MockLLMProvider(default_response_text="Hello from Discord Agent!")
    agent = Agent(provider=mock_provider)
    settings = Settings(discord_require_mention=False)

    bot = DiscordAgentBot(agent=agent, settings=settings)

    # Mock user and channel
    mock_bot_user = MagicMock()
    mock_bot_user.id = 999
    mock_bot_user.name = "TestBot"
    bot._connection.user = mock_bot_user  # Set internal client user

    mock_channel = AsyncMock()
    mock_channel.id = 456
    mock_channel.typing = MagicMock()
    mock_channel.typing.return_value.__aenter__ = AsyncMock()
    mock_channel.typing.return_value.__aexit__ = AsyncMock()

    mock_message = AsyncMock()
    mock_message.author.id = 123
    mock_message.author.bot = False
    mock_message.guild = MagicMock(id=789)
    mock_message.channel = mock_channel
    mock_message.mentions = []
    mock_message.content = "What is the capital of France?"

    # Trigger on_message
    await bot.on_message(mock_message)
    assert bot._queue.qsize() == 1

    # Start setup hook to spawn worker
    await bot.setup_hook()

    # Wait briefly for worker to process queue
    await asyncio.sleep(0.1)

    assert bot._queue.qsize() == 0
    assert mock_message.reply.called
    reply_text = mock_message.reply.call_args[0][0]
    assert reply_text == "Hello from Discord Agent!"

    # Clean shutdown
    await bot.close()
