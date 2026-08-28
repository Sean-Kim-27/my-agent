"""Autonomous AI Agent Core orchestrator with advanced ReAct multi-step execution loop and lifecycle callbacks."""

import re
import time
from collections.abc import Callable
from typing import Any

from agent_framework.agent.events import AgentCallbackHandler
from agent_framework.exceptions import AgentError
from agent_framework.llm.base import LLMProvider
from agent_framework.logging.logger import get_logger
from agent_framework.memory.base import ConversationMemory
from agent_framework.memory.session import SessionManager
from agent_framework.models.events import AgentRunResult, AgentStep
from agent_framework.models.message import Message, MessageRole
from agent_framework.models.response import LLMResponse
from agent_framework.models.tool import ToolDefinition
from agent_framework.tools.executor import ToolExecutor
from agent_framework.tools.registry import ToolRegistry

logger = get_logger("agent_framework.agent")


class Agent:
    """Core Agent coordinating session memory, tools, and LLM provider execution.

    The Agent is decoupled from concrete LLM SDKs, authentication mechanisms,
    and messaging platforms via dependency inversion.
    """

    def __init__(
        self,
        provider: LLMProvider,
        session_manager: SessionManager | None = None,
        tool_registry: ToolRegistry | None = None,
        tool_executor: ToolExecutor | None = None,
        system_prompt: str | None = None,
        default_session_id: str = "cli:default",
        max_steps: int = 10,
        callbacks: list[AgentCallbackHandler] | None = None,
    ) -> None:
        self.provider = provider
        self.session_manager = session_manager or SessionManager()
        self.tool_registry = tool_registry
        self.tool_executor: ToolExecutor | None
        if tool_executor is not None:
            self.tool_executor = tool_executor
        elif self.tool_registry is not None:
            self.tool_executor = ToolExecutor(self.tool_registry)
        else:
            self.tool_executor = None

        self.system_prompt = system_prompt
        self.default_session_id = default_session_id
        self.max_steps = max_steps
        self.callbacks: list[AgentCallbackHandler] = callbacks or []

    def register_tool(
        self,
        func: Callable[..., Any],
        name: str | None = None,
        description: str | None = None,
        definition: ToolDefinition | None = None,
    ) -> ToolDefinition:
        """Register a tool directly on the agent."""
        if self.tool_registry is None:
            self.tool_registry = ToolRegistry()
            self.tool_executor = ToolExecutor(self.tool_registry)
        return self.tool_registry.register(func, name=name, description=description, definition=definition)

    def tool(
        self,
        name: str | None = None,
        description: str | None = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator for registering tools directly on the agent."""
        if self.tool_registry is None:
            self.tool_registry = ToolRegistry()
            self.tool_executor = ToolExecutor(self.tool_registry)
        return self.tool_registry.tool(name=name, description=description)

    def add_callback(self, handler: AgentCallbackHandler) -> None:
        """Register an event callback handler."""
        self.callbacks.append(handler)

    async def _prepare_messages(
        self,
        memory: ConversationMemory,
        new_user_message: Message,
    ) -> list[Message]:
        """Combine system prompt, session history, and incoming user message."""
        history = await memory.get_messages()
        messages: list[Message] = []

        # Ensure system prompt is prepended if defined and not already in history
        has_system = any(
            (msg.role == MessageRole.SYSTEM or msg.role == "system") for msg in history
        )
        if self.system_prompt and not has_system:
            messages.append(Message.system(self.system_prompt))

        messages.extend(history)
        messages.append(new_user_message)
        return messages

    def _extract_thought(self, content: str | None) -> str | None:
        """Extract thought / reasoning string if structured tags or formatting are used."""
        if not content:
            return None
        # Match <thought>...</thought> blocks
        thought_match = re.search(r"<thought>(.*?)</thought>", content, flags=re.DOTALL | re.IGNORECASE)
        if thought_match:
            return thought_match.group(1).strip()
        return None

    async def _dispatch_event(self, method_name: str, *args: Any, **kwargs: Any) -> None:
        """Safely dispatch an event to all registered callback handlers."""
        for handler in self.callbacks:
            try:
                method = getattr(handler, method_name, None)
                if method and callable(method):
                    await method(*args, **kwargs)
            except Exception as exc:
                logger.warning(f"Error in callback handler '{type(handler).__name__}.{method_name}': {exc}")

    async def run_with_trace(
        self,
        user_input: str,
        session_id: str | None = None,
        callbacks: list[AgentCallbackHandler] | None = None,
        **kwargs: Any,
    ) -> AgentRunResult:
        """Execute the multi-step ReAct agent loop and return the complete trajectory trace."""
        target_session = session_id or self.default_session_id
        if not user_input or not user_input.strip():
            raise AgentError("User input cannot be empty.")

        # Merge one-off callbacks with agent callbacks
        active_callbacks = list(self.callbacks)
        if callbacks:
            active_callbacks.extend(callbacks)

        logger.info(
            f"Agent starting ReAct run for session '{target_session}' with provider '{self.provider.name}'"
        )
        await self._dispatch_event("on_agent_start", session_id=target_session, prompt=user_input)

        memory = await self.session_manager.get_memory(target_session)
        user_message = Message.user(user_input)

        context_messages = await self._prepare_messages(memory, user_message)
        await memory.add(user_message)

        steps: list[AgentStep] = []
        start_time = time.perf_counter()
        step = 0

        try:
            while step < self.max_steps:
                step += 1
                step_start = time.perf_counter()
                tools = self.tool_registry.get_definitions() if self.tool_registry else None

                await self._dispatch_event("on_llm_start", step=step, messages=context_messages)

                try:
                    response = await self.provider.generate(
                        context_messages,
                        tools=tools,
                        **kwargs,
                    )
                except Exception as exc:
                    logger.error(
                        f"LLM generation failed for session '{target_session}' at step {step}: {exc}",
                        exc_info=True,
                    )
                    await self._dispatch_event("on_agent_error", session_id=target_session, error=exc)
                    raise

                await self._dispatch_event("on_llm_end", step=step, response=response)

                thought = self._extract_thought(response.content)
                if thought:
                    await self._dispatch_event("on_thought", step=step, thought=thought)

                step_latency = (time.perf_counter() - step_start) * 1000.0

                if not response.has_tool_calls:
                    # Final assistant answer reached
                    await memory.add(response.to_message())
                    total_latency = (time.perf_counter() - start_time) * 1000.0

                    final_step = AgentStep(
                        step_number=step,
                        thought=thought,
                        is_final=True,
                        latency_ms=round(step_latency, 2),
                    )
                    steps.append(final_step)

                    await self._dispatch_event(
                        "on_agent_finish",
                        session_id=target_session,
                        final_response=response,
                        total_steps=step,
                    )

                    return AgentRunResult(
                        content=response.content or "",
                        session_id=target_session,
                        steps=steps,
                        total_steps=step,
                        total_latency_ms=round(total_latency, 2),
                        is_max_steps_reached=False,
                        llm_response=response,
                    )

                # Tool calling branch
                if self.tool_executor is None or not self.tool_registry:
                    raise AgentError(
                        f"Provider requested tool calls {response.tool_calls}, but no ToolExecutor is configured."
                    )

                # Dispatch on_tool_start for each tool call
                for tc in response.tool_calls:
                    await self._dispatch_event(
                        "on_tool_start",
                        step=step,
                        tool_name=tc.name,
                        arguments=tc.arguments,
                    )

                # Append assistant tool call message to memory & context
                asst_tool_msg = response.to_message()
                context_messages.append(asst_tool_msg)
                await memory.add(asst_tool_msg)

                # Execute all tool calls
                tool_results = await self.tool_executor.execute_all(response.tool_calls)

                # Process results and inject recovery prompt feedback if an error occurred
                for res in tool_results:
                    await self._dispatch_event(
                        "on_tool_end",
                        step=step,
                        tool_name=res.name,
                        result=res.content,
                        is_error=res.is_error,
                    )

                    content_to_record = res.content
                    if res.is_error:
                        content_to_record = (
                            f"[Tool Error in '{res.name}']: {res.content}\n"
                            f"Please analyze what caused this error, adjust the arguments or tool choice, and try again."
                        )

                    tool_msg = Message.tool(
                        content=content_to_record,
                        tool_call_id=res.tool_call_id,
                        name=res.name,
                        is_error=res.is_error,
                    )
                    context_messages.append(tool_msg)
                    await memory.add(tool_msg)

                current_step = AgentStep(
                    step_number=step,
                    thought=thought,
                    tool_calls=response.tool_calls,
                    tool_results=tool_results,
                    is_final=False,
                    latency_ms=round(step_latency, 2),
                )
                steps.append(current_step)

            # Max steps exceeded
            err = AgentError(
                f"Agent exceeded maximum execution steps ({self.max_steps}) without producing a final answer."
            )
            await self._dispatch_event("on_agent_error", session_id=target_session, error=err)
            raise err

        except Exception as exc:
            await self._dispatch_event("on_agent_error", session_id=target_session, error=exc)
            raise

    async def run(
        self,
        user_input: str,
        session_id: str | None = None,
        callbacks: list[AgentCallbackHandler] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Process user input in an isolated session context and return LLMResponse."""
        result = await self.run_with_trace(
            user_input=user_input,
            session_id=session_id,
            callbacks=callbacks,
            **kwargs,
        )
        return result.llm_response

    async def get_session_history(self, session_id: str | None = None) -> list[Message]:
        """Retrieve conversation history for a specific session."""
        target_session = session_id or self.default_session_id
        memory = await self.session_manager.get_memory(target_session)
        return await memory.get_messages()

    async def clear_session(self, session_id: str | None = None) -> None:
        """Clear conversation history for a specific session."""
        target_session = session_id or self.default_session_id
        await self.session_manager.clear_session(target_session)
        logger.info(f"Cleared session history for '{target_session}'")
