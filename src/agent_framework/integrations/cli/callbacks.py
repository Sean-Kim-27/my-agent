"""Interactive CLI callback handler providing Human-in-the-Loop tool approvals."""

from __future__ import annotations

import asyncio
from typing import Any

from agent_framework.agent.events import AgentCallbackHandler


class CLIConfirmationHandler(AgentCallbackHandler):
    """Prompts the human operator on stdin whenever the agent tries to invoke a
    tool flagged with ``requires_confirmation=True``.
    """

    def __init__(self, auto_approve: bool = False) -> None:
        self.auto_approve = auto_approve

    async def on_tool_confirmation(
        self,
        step: int,
        tool_name: str,
        arguments: dict[str, Any] | str,
    ) -> bool:
        if self.auto_approve:
            return True

        prompt = (
            f"\n⚠️  Tool '{tool_name}' requires confirmation.\n"
            f"    Arguments: {arguments}\n"
            f"    Approve execution? [y/N]: "
        )
        answer = await asyncio.to_thread(input, prompt)
        return answer.strip().lower() in {"y", "yes"}
