"""Discord approval callback for Human-in-the-Loop tool confirmations."""

from __future__ import annotations

from typing import Any

import discord
from agent_framework.agent.events import AgentCallbackHandler
from agent_framework.logging.logger import get_logger

logger = get_logger("agent_framework.discord.callbacks")

_APPROVE = "✅"
_REJECT = "❌"


class DiscordConfirmationHandler(AgentCallbackHandler):
    """Prompts the original Discord author via reactions before a gated tool runs.

    Only the author of the message that triggered the agent may respond, and the
    response must arrive before the configured timeout — otherwise the call is
    rejected (fail-closed).
    """

    def __init__(
        self,
        *,
        client: discord.Client,
        message: discord.Message,
        timeout: float = 60.0,
    ) -> None:
        self._client = client
        self._message = message
        self._timeout = timeout

    async def on_tool_confirmation(
        self,
        step: int,
        tool_name: str,
        arguments: dict[str, Any] | str,
    ) -> bool:
        prompt = (
            f"⚠️ Step {step}: Tool `{tool_name}` requires confirmation.\n"
            f"Arguments: `{arguments}`\n"
            f"React {_APPROVE} to approve or {_REJECT} to reject "
            f"(timeout: {int(self._timeout)}s)."
        )
        try:
            prompt_msg = await self._message.reply(prompt)
            await prompt_msg.add_reaction(_APPROVE)
            await prompt_msg.add_reaction(_REJECT)
        except Exception as exc:
            logger.error(
                "Failed to publish Discord confirmation prompt for '%s': %s — rejecting.",
                tool_name,
                exc,
            )
            return False

        expected_author = self._message.author.id
        expected_message_id = prompt_msg.id

        def _check(reaction: discord.Reaction, user: discord.abc.User) -> bool:
            return (
                reaction.message.id == expected_message_id
                and user.id == expected_author
                and str(reaction.emoji) in (_APPROVE, _REJECT)
            )

        try:
            reaction, _user = await self._client.wait_for(
                "reaction_add", timeout=self._timeout, check=_check
            )
            return str(reaction.emoji) == _APPROVE
        except TimeoutError:
            logger.warning(
                "Discord confirmation for '%s' timed out after %.1fs — rejecting.",
                tool_name,
                self._timeout,
            )
            try:
                await self._message.reply(
                    f"⏱️ Confirmation for `{tool_name}` timed out — rejected."
                )
            except Exception:
                pass
            return False
        except Exception as exc:
            logger.error(
                "Discord confirmation for '%s' failed: %s — rejecting.",
                tool_name,
                exc,
            )
            return False
