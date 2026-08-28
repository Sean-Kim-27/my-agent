"""Agent lifecycle event handlers, ReAct callbacks, and console logger."""

import sys
from typing import Any

from agent_framework.models.message import Message
from agent_framework.models.response import LLMResponse


class AgentCallbackHandler:
    """Base class for listening to Agent ReAct execution lifecycle events.

    Subclasses can override any subset of callback hooks.
    """

    async def on_agent_start(self, session_id: str, prompt: str) -> None:
        """Invoked when an agent run begins."""

    async def on_llm_start(self, step: int, messages: list[Message]) -> None:
        """Invoked immediately before sending a request to the LLM provider."""

    async def on_llm_end(self, step: int, response: LLMResponse) -> None:
        """Invoked upon receiving a response from the LLM provider."""

    async def on_thought(self, step: int, thought: str) -> None:
        """Invoked when model internal reasoning / thought is parsed."""

    async def on_tool_confirmation(
        self,
        step: int,
        tool_name: str,
        arguments: dict[str, Any] | str,
    ) -> bool:
        """Approval hook invoked before executing a tool with ``requires_confirmation=True``.

        Return ``True`` to allow the tool call, ``False`` to reject it. The default
        implementation approves every request — adapters (CLI, Discord, Telegram)
        should override this to prompt the human operator.
        """
        return True

    async def on_tool_start(self, step: int, tool_name: str, arguments: dict[str, Any] | str) -> None:
        """Invoked before a tool function is executed."""

    async def on_tool_end(self, step: int, tool_name: str, result: str, is_error: bool) -> None:
        """Invoked after tool execution completes."""

    async def on_agent_finish(self, session_id: str, final_response: LLMResponse, total_steps: int) -> None:
        """Invoked when the agent completes its multi-step loop."""

    async def on_agent_error(self, session_id: str, error: Exception) -> None:
        """Invoked when an unhandled error occurs during execution."""


class ConsoleCallbackHandler(AgentCallbackHandler):
    """Callback handler rendering formatted ReAct Thought / Action / Observation steps to stdout."""

    def __init__(self, show_llm_messages: bool = False) -> None:
        self.show_llm_messages = show_llm_messages

    async def on_agent_start(self, session_id: str, prompt: str) -> None:
        print(f"\n[Agent] 🚀 Starting session '{session_id}'...", file=sys.stderr)

    async def on_thought(self, step: int, thought: str) -> None:
        print(f"  [Step {step}] 💭 Thought: {thought}", file=sys.stderr)

    async def on_tool_start(self, step: int, tool_name: str, arguments: dict[str, Any] | str) -> None:
        print(f"  [Step {step}] 🛠️ Action: {tool_name}({arguments})", file=sys.stderr)

    async def on_tool_end(self, step: int, tool_name: str, result: str, is_error: bool) -> None:
        status_icon = "❌ Error" if is_error else "👁️ Observation"
        print(f"  [Step {step}] {status_icon}: {result}", file=sys.stderr)

    async def on_agent_finish(self, session_id: str, final_response: LLMResponse, total_steps: int) -> None:
        print(f"[Agent] ✨ Concluded in {total_steps} step(s) ({final_response.latency_ms:.1f}ms)\n", file=sys.stderr)

    async def on_agent_error(self, session_id: str, error: Exception) -> None:
        print(f"[Agent] ❌ Error in session '{session_id}': {error}", file=sys.stderr)
