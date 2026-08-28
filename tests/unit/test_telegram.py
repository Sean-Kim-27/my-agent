"""Unit tests for Telegram Bot integration, router, MarkdownV2 escaping, and chunking."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram.constants import ParseMode

from agent_framework.agent.agent import Agent
from agent_framework.config.settings import Settings
from agent_framework.integrations.telegram.bot import TelegramAgentBot
from agent_framework.integrations.telegram.router import (
    escape_markdown_v2,
    extract_clean_telegram_text,
    generate_telegram_session_id,
    should_process_telegram_message,
    split_telegram_message,
)
from tests.conftest import MockLLMProvider


def test_telegram_session_id_generation() -> None:
    """Test session ID generation for private, group, and channel contexts."""
    # Private chat
    priv_session = generate_telegram_session_id(chat_id=1001, user_id=2002, chat_type="private")
    assert priv_session == "telegram:private:2002"

    # Group chat
    group_session = generate_telegram_session_id(chat_id=-100333, user_id=2002, chat_type="group")
    assert group_session == "telegram:group:-100333:user:2002"

    # Supergroup chat
    supergroup_session = generate_telegram_session_id(chat_id=-100444, user_id=2002, chat_type="supergroup")
    assert supergroup_session == "telegram:group:-100444:user:2002"

    # Channel
    channel_session = generate_telegram_session_id(chat_id=-100555, user_id=2002, chat_type="channel")
    assert channel_session == "telegram:channel:-100555"


def test_escape_markdown_v2() -> None:
    """Test escaping MarkdownV2 special characters while preserving code blocks."""
    # Plain text with reserved characters
    plain = "Hello! Version 1.0 (test) [ok] -> cost is $10 + $5 = $15."
    escaped = escape_markdown_v2(plain)
    assert r"\!" in escaped
    assert r"\." in escaped
    assert r"\(" in escaped
    assert r"\)" in escaped
    assert r"\[" in escaped
    assert r"\]" in escaped
    assert r"\+" in escaped
    assert r"\=" in escaped

    # Code block preservation: code inside ``` should NOT be escaped
    code_text = "Here is code:\n```python\nx = 1 + 2\nprint('hello!')\n```\nDone."
    escaped_code = escape_markdown_v2(code_text)
    assert "```python\nx = 1 + 2\nprint('hello!')\n```" in escaped_code
    assert r"Done\." in escaped_code

    # Inline code preservation
    inline_text = "Use `x = a + b` to add."
    escaped_inline = escape_markdown_v2(inline_text)
    assert "`x = a + b`" in escaped_inline
    assert r"add\." in escaped_inline


def test_extract_clean_telegram_text() -> None:
    """Test cleaning bot mentions and slash commands."""
    assert extract_clean_telegram_text("@MyBot Hello there!", bot_username="MyBot") == "Hello there!"
    assert extract_clean_telegram_text("/ask What is AI?", bot_username="MyBot") == "What is AI?"
    assert extract_clean_telegram_text("/start", bot_username="MyBot") == ""
    assert extract_clean_telegram_text("Regular question") == "Regular question"


def test_should_process_telegram_message_filters() -> None:
    """Test message filtering for Telegram chat types, bots, and whitelists."""
    bot_username = "AgentBot"

    # 1. Ignore if user is a bot
    assert should_process_telegram_message(
        is_bot=True,
        chat_id=123,
        chat_type="private",
        text="Hello",
        bot_username=bot_username,
    ) is False

    # 2. Check whitelist
    assert should_process_telegram_message(
        is_bot=False,
        chat_id=999,
        chat_type="private",
        text="Hello",
        allowed_chats=[111, 222],  # 999 not allowed
    ) is False

    # 3. Private DMs always processed
    assert should_process_telegram_message(
        is_bot=False,
        chat_id=123,
        chat_type="private",
        text="Hello",
        require_mention=True,
    ) is True

    # 4. Group without mention ignored if require_mention=True
    assert should_process_telegram_message(
        is_bot=False,
        chat_id=-1001,
        chat_type="group",
        text="Hello everyone",
        bot_username=bot_username,
        require_mention=True,
    ) is False

    # 5. Group with mention processed
    assert should_process_telegram_message(
        is_bot=False,
        chat_id=-1001,
        chat_type="group",
        text="Hello @AgentBot please help",
        bot_username=bot_username,
        require_mention=True,
    ) is True


def test_split_telegram_message() -> None:
    """Test chunking long messages into <= 4096 character blocks."""
    short = "Short message"
    assert split_telegram_message(short, max_chunk_size=4096) == [short]

    # Large message
    large_text = "Paragraph text. " * 300  # ~4800 chars
    chunks = split_telegram_message(large_text, max_chunk_size=2000)
    assert len(chunks) >= 3
    assert all(len(c) <= 2000 for c in chunks)

    # Large message inside code block
    code = "```python\n" + ("a = 1 + 2\n" * 150) + "```"
    chunks = split_telegram_message(code, max_chunk_size=500)
    assert len(chunks) >= 3
    assert chunks[0].endswith("```")
    assert chunks[1].startswith("```python")


@pytest.mark.asyncio
async def test_telegram_bot_handlers() -> None:
    """Test TelegramAgentBot commands and message handling."""
    mock_provider = MockLLMProvider(default_response_text="Hello from Telegram Agent!")
    agent = Agent(provider=mock_provider)
    settings = Settings(
        telegram_bot_token="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
        telegram_require_mention=False,
    )

    bot = TelegramAgentBot(agent=agent, settings=settings)
    bot.bot_username = "TestTelegramBot"

    # Mock Update and Context
    mock_chat = MagicMock(id=1001, type="private")
    mock_user = MagicMock(id=2002, is_bot=False)
    mock_message = AsyncMock(text="Tell me a joke", chat_id=1001)

    mock_update = MagicMock()
    mock_update.effective_chat = mock_chat
    mock_update.effective_user = mock_user
    mock_update.effective_message = mock_message

    mock_bot = AsyncMock()
    mock_context = MagicMock(bot=mock_bot)

    # Test /start
    await bot.cmd_start(mock_update, mock_context)
    assert mock_message.reply_text.called
    assert "autonomous AI Assistant" in mock_message.reply_text.call_args[0][0]

    # Test /help
    await bot.cmd_help(mock_update, mock_context)
    assert "Available Commands" in mock_message.reply_text.call_args[0][0]

    # Test handle_message
    mock_message.reply_text.reset_mock()
    await bot.handle_message(mock_update, mock_context)

    assert mock_bot.send_chat_action.called
    assert mock_message.reply_text.called
    reply_args = mock_message.reply_text.call_args
    assert r"Hello from Telegram Agent\!" in reply_args[0][0]
    assert reply_args[1]["parse_mode"] == ParseMode.MARKDOWN_V2

    # Test /clear
    mock_message.reply_text.reset_mock()
    await bot.cmd_clear(mock_update, mock_context)
    assert "Cleared conversation memory" in mock_message.reply_text.call_args[0][0]
