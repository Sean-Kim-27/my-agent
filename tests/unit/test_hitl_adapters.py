"""Adapter-level tests for the Human-in-the-Loop confirmation handlers."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_framework.integrations.discord.callbacks import DiscordConfirmationHandler
from agent_framework.integrations.telegram.callbacks import (
    _APPROVE_PREFIX,
    _REJECT_PREFIX,
    TelegramConfirmationBroker,
    TelegramConfirmationHandler,
)

# --------------------------------------------------------------------- Discord


def _make_discord_message(author_id: int = 111) -> MagicMock:
    prompt_msg = MagicMock()
    prompt_msg.id = 9001
    prompt_msg.add_reaction = AsyncMock()

    message = MagicMock()
    message.author = MagicMock(id=author_id)
    message.reply = AsyncMock(return_value=prompt_msg)
    return message


@pytest.mark.asyncio
async def test_discord_handler_returns_true_on_approve() -> None:
    client = MagicMock()
    message = _make_discord_message()

    approve_reaction = MagicMock()
    approve_reaction.emoji = "✅"
    approve_reaction.message.id = 9001

    async def fake_wait_for(event: str, timeout: float, check):
        assert event == "reaction_add"
        approver = MagicMock(id=message.author.id)
        assert check(approve_reaction, approver) is True
        return approve_reaction, approver

    client.wait_for = fake_wait_for

    handler = DiscordConfirmationHandler(client=client, message=message, timeout=5.0)
    approved = await handler.on_tool_confirmation(step=1, tool_name="rm", arguments={"path": "/"})

    assert approved is True
    assert message.reply.await_count == 1


@pytest.mark.asyncio
async def test_discord_handler_returns_false_on_reject() -> None:
    client = MagicMock()
    message = _make_discord_message()

    reject_reaction = MagicMock()
    reject_reaction.emoji = "❌"
    reject_reaction.message.id = 9001

    async def fake_wait_for(event: str, timeout: float, check):
        return reject_reaction, MagicMock(id=message.author.id)

    client.wait_for = fake_wait_for

    handler = DiscordConfirmationHandler(client=client, message=message, timeout=5.0)
    approved = await handler.on_tool_confirmation(step=1, tool_name="rm", arguments={})

    assert approved is False


@pytest.mark.asyncio
async def test_discord_handler_rejects_on_timeout() -> None:
    client = MagicMock()
    message = _make_discord_message()

    async def fake_wait_for(event: str, timeout: float, check):
        raise TimeoutError

    client.wait_for = fake_wait_for

    handler = DiscordConfirmationHandler(client=client, message=message, timeout=0.05)
    approved = await handler.on_tool_confirmation(step=1, tool_name="rm", arguments={})

    assert approved is False
    # Prompt is posted once, and a timeout notice is posted as a follow-up reply.
    assert message.reply.await_count == 2


@pytest.mark.asyncio
async def test_discord_handler_rejects_when_prompt_send_fails() -> None:
    client = MagicMock()
    message = MagicMock()
    message.author = MagicMock(id=111)
    message.reply = AsyncMock(side_effect=RuntimeError("boom"))

    handler = DiscordConfirmationHandler(client=client, message=message, timeout=5.0)
    approved = await handler.on_tool_confirmation(step=1, tool_name="rm", arguments={})

    assert approved is False


@pytest.mark.asyncio
async def test_discord_handler_check_rejects_other_user() -> None:
    """Only the original author may respond."""
    client = MagicMock()
    message = _make_discord_message(author_id=111)

    other_reaction = MagicMock()
    other_reaction.emoji = "✅"
    other_reaction.message.id = 9001

    captured_check: list = []

    async def fake_wait_for(event: str, timeout: float, check):
        captured_check.append(check)
        # Simulate discord.py filtering: it keeps polling and eventually times out
        # because no matching reaction arrives.
        raise TimeoutError

    client.wait_for = fake_wait_for

    handler = DiscordConfirmationHandler(client=client, message=message, timeout=0.05)
    await handler.on_tool_confirmation(step=1, tool_name="rm", arguments={})

    assert captured_check, "wait_for should have been called with a check"
    check = captured_check[0]
    stranger = MagicMock(id=222)
    assert check(other_reaction, stranger) is False


# -------------------------------------------------------------------- Telegram


@pytest.mark.asyncio
async def test_telegram_broker_resolves_future_on_approve() -> None:
    broker = TelegramConfirmationBroker()
    future = broker.register("req-1", user_id=42)

    query = MagicMock()
    query.data = f"{_APPROVE_PREFIX}req-1"
    query.from_user = MagicMock(id=42)
    query.answer = AsyncMock()
    query.edit_message_reply_markup = AsyncMock()

    update = MagicMock(callback_query=query)
    await broker.on_callback_query(update, MagicMock())

    assert future.done()
    assert future.result() is True
    query.answer.assert_awaited()


@pytest.mark.asyncio
async def test_telegram_broker_ignores_wrong_user() -> None:
    broker = TelegramConfirmationBroker()
    future = broker.register("req-2", user_id=42)

    query = MagicMock()
    query.data = f"{_APPROVE_PREFIX}req-2"
    query.from_user = MagicMock(id=999)  # different user
    query.answer = AsyncMock()

    update = MagicMock(callback_query=query)
    await broker.on_callback_query(update, MagicMock())

    assert not future.done()
    query.answer.assert_awaited_with(
        "Only the original requester may respond.", show_alert=True
    )
    broker.unregister("req-2")


@pytest.mark.asyncio
async def test_telegram_broker_ignores_unknown_request_id() -> None:
    broker = TelegramConfirmationBroker()

    query = MagicMock()
    query.data = f"{_REJECT_PREFIX}nonexistent"
    query.from_user = MagicMock(id=42)
    query.answer = AsyncMock()

    update = MagicMock(callback_query=query)
    await broker.on_callback_query(update, MagicMock())

    query.answer.assert_awaited_with("Request already resolved or expired.")


@pytest.mark.asyncio
async def test_telegram_handler_approve_flow() -> None:
    broker = TelegramConfirmationBroker()
    bot = MagicMock()
    bot.send_message = AsyncMock()

    handler = TelegramConfirmationHandler(
        broker=broker,
        chat_id=1001,
        user_id=42,
        bot=bot,
        timeout=5.0,
    )

    # Simulate the user pressing "Approve" shortly after the prompt is sent.
    async def approve_after_prompt() -> None:
        await asyncio.sleep(0.01)
        # Pull the pending request id from the broker's internal state.
        request_id = next(iter(broker._pending))
        query = MagicMock()
        query.data = f"{_APPROVE_PREFIX}{request_id}"
        query.from_user = MagicMock(id=42)
        query.answer = AsyncMock()
        query.edit_message_reply_markup = AsyncMock()
        await broker.on_callback_query(MagicMock(callback_query=query), MagicMock())

    approver = asyncio.create_task(approve_after_prompt())
    approved = await handler.on_tool_confirmation(
        step=1, tool_name="rm", arguments={"path": "/tmp"}
    )
    await approver

    assert approved is True
    bot.send_message.assert_awaited()


@pytest.mark.asyncio
async def test_telegram_handler_rejects_on_timeout() -> None:
    broker = TelegramConfirmationBroker()
    bot = MagicMock()
    bot.send_message = AsyncMock()

    handler = TelegramConfirmationHandler(
        broker=broker,
        chat_id=1001,
        user_id=42,
        bot=bot,
        timeout=0.05,
    )

    approved = await handler.on_tool_confirmation(step=1, tool_name="rm", arguments={})

    assert approved is False
    # Two messages: original prompt + timeout notice.
    assert bot.send_message.await_count == 2
    assert not broker._pending  # cleaned up on rejection


@pytest.mark.asyncio
async def test_telegram_handler_rejects_when_prompt_send_fails() -> None:
    broker = TelegramConfirmationBroker()
    bot = MagicMock()
    bot.send_message = AsyncMock(side_effect=RuntimeError("network down"))

    handler = TelegramConfirmationHandler(
        broker=broker,
        chat_id=1001,
        user_id=42,
        bot=bot,
        timeout=5.0,
    )

    approved = await handler.on_tool_confirmation(step=1, tool_name="rm", arguments={})

    assert approved is False
    assert not broker._pending
