"""Telegram approval callback for Human-in-the-Loop tool confirmations."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from agent_framework.agent.events import AgentCallbackHandler
from agent_framework.logging.logger import get_logger
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

logger = get_logger("agent_framework.telegram.callbacks")

_APPROVE_PREFIX = "hitl:approve:"
_REJECT_PREFIX = "hitl:reject:"


class TelegramConfirmationBroker:
    """Resolves inline-keyboard callback queries into per-request approval futures.

    A single broker instance is shared across the bot; each pending confirmation
    is tracked by an opaque request id and bound to the Telegram user that
    initiated the agent run. Only that user's response is honoured.
    """

    def __init__(self) -> None:
        self._pending: dict[str, tuple[int, asyncio.Future[bool]]] = {}

    def register(self, request_id: str, user_id: int) -> asyncio.Future[bool]:
        future: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = (user_id, future)
        return future

    def unregister(self, request_id: str) -> None:
        self._pending.pop(request_id, None)

    async def on_callback_query(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        query = update.callback_query
        if query is None or query.data is None:
            return
        data = query.data
        if data.startswith(_APPROVE_PREFIX):
            request_id = data[len(_APPROVE_PREFIX) :]
            approved = True
        elif data.startswith(_REJECT_PREFIX):
            request_id = data[len(_REJECT_PREFIX) :]
            approved = False
        else:
            return

        entry = self._pending.get(request_id)
        if entry is None:
            await query.answer("Request already resolved or expired.")
            return

        expected_user, future = entry
        if query.from_user is None or query.from_user.id != expected_user:
            await query.answer(
                "Only the original requester may respond.", show_alert=True
            )
            return

        if not future.done():
            future.set_result(approved)
        await query.answer("Approved ✅" if approved else "Rejected ❌")
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass


class TelegramConfirmationHandler(AgentCallbackHandler):
    """Sends an inline-keyboard prompt and awaits the user's approval."""

    def __init__(
        self,
        *,
        broker: TelegramConfirmationBroker,
        chat_id: int,
        user_id: int,
        bot: Any,
        timeout: float = 60.0,
    ) -> None:
        self._broker = broker
        self._chat_id = chat_id
        self._user_id = user_id
        self._bot = bot
        self._timeout = timeout

    async def on_tool_confirmation(
        self,
        step: int,
        tool_name: str,
        arguments: dict[str, Any] | str,
    ) -> bool:
        request_id = uuid.uuid4().hex[:12]
        future = self._broker.register(request_id, self._user_id)
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "✅ Approve", callback_data=f"{_APPROVE_PREFIX}{request_id}"
                    ),
                    InlineKeyboardButton(
                        "❌ Reject", callback_data=f"{_REJECT_PREFIX}{request_id}"
                    ),
                ]
            ]
        )
        prompt = (
            f"⚠️ Step {step}: Tool `{tool_name}` requires confirmation.\n"
            f"Arguments: `{arguments}`\n"
            f"(timeout: {int(self._timeout)}s)"
        )
        try:
            await self._bot.send_message(
                chat_id=self._chat_id, text=prompt, reply_markup=keyboard
            )
        except Exception as exc:
            logger.error(
                "Failed to send Telegram confirmation prompt for '%s': %s — rejecting.",
                tool_name,
                exc,
            )
            self._broker.unregister(request_id)
            return False

        try:
            return await asyncio.wait_for(future, timeout=self._timeout)
        except TimeoutError:
            logger.warning(
                "Telegram confirmation for '%s' timed out after %.1fs — rejecting.",
                tool_name,
                self._timeout,
            )
            try:
                await self._bot.send_message(
                    chat_id=self._chat_id,
                    text=f"⏱️ Confirmation for `{tool_name}` timed out — rejected.",
                )
            except Exception:
                pass
            return False
        except Exception as exc:
            logger.error(
                "Telegram confirmation for '%s' failed: %s — rejecting.",
                tool_name,
                exc,
            )
            return False
        finally:
            self._broker.unregister(request_id)
