"""Autonomous AI Agent Core orchestrator with advanced ReAct multi-step execution loop and lifecycle callbacks."""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar

from agent_framework.agent.events import AgentCallbackHandler
from agent_framework.agent.runtime import RunContext, RunState
from agent_framework.exceptions import AgentError
from agent_framework.llm.base import LLMProvider
from agent_framework.logging.logger import get_logger
from agent_framework.memory.base import ConversationMemory
from agent_framework.memory.context import ContextManager
from agent_framework.memory.session import SessionManager
from agent_framework.models.events import AgentRunResult, AgentStep
from agent_framework.models.message import Message, MessageRole
from agent_framework.models.response import LLMResponse
from agent_framework.models.tool import (
    ToolCall,
    ToolCallResult,
    ToolDefinition,
    ToolExecutionContext,
)
from agent_framework.tools.executor import ToolExecutor
from agent_framework.tools.registry import ToolRegistry

logger = get_logger("agent_framework.agent")

_T = TypeVar("_T")


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
        context_manager: ContextManager | None = None,
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
        self.context_manager = context_manager

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

        has_system = any(
            (msg.role == MessageRole.SYSTEM or msg.role == "system") for msg in history
        )
        if self.system_prompt and not has_system:
            messages.append(Message.system(self.system_prompt))

        messages.extend(history)
        messages.append(new_user_message)
        return messages

    async def _fit_context(self, messages: list[Message]) -> list[Message]:
        """Apply the ContextManager (if any) to a message list before an LLM call.

        Managers that expose an async ``afit`` (e.g. summarizing strategies)
        are preferred so they can invoke the summarization LLM without
        blocking the event loop; otherwise the sync ``fit`` is used.
        """
        if self.context_manager is None:
            return messages
        afit = getattr(self.context_manager, "afit", None)
        if callable(afit):
            result: list[Message] = await afit(messages)
            return result
        return self.context_manager.fit(messages)

    def _extract_thought(self, content: str | None) -> str | None:
        """Extract thought / reasoning string if structured tags or formatting are used."""
        if not content:
            return None
        thought_match = re.search(r"<thought>(.*?)</thought>", content, flags=re.DOTALL | re.IGNORECASE)
        if thought_match:
            return thought_match.group(1).strip()
        return None

    async def _dispatch(
        self,
        callbacks: list[AgentCallbackHandler],
        method_name: str,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """Safely dispatch a lifecycle event to the given handlers.

        Handler exceptions are logged as structured warnings but never abort the run.
        """
        for handler in callbacks:
            try:
                method = getattr(handler, method_name, None)
                if method and callable(method):
                    await method(*args, **kwargs)
            except Exception as exc:
                logger.warning(
                    "Callback handler '%s.%s' raised: %s",
                    type(handler).__name__,
                    method_name,
                    exc,
                )

    @staticmethod
    async def _cancel_task(task: asyncio.Task[Any]) -> None:
        """Cancel and drain a task so it cannot leak into the background."""
        if task.done():
            if not task.cancelled():
                task.exception()
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

    async def _await_or_cancel(
        self,
        operation: Coroutine[Any, Any, _T],
        ctx: RunContext,
    ) -> _T:
        """Await an operation while honoring cooperative ``RunContext`` cancellation."""
        operation_task = asyncio.create_task(operation)
        cancel_waiter = asyncio.create_task(ctx.wait_cancelled())
        try:
            done, _ = await asyncio.wait(
                {operation_task, cancel_waiter},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if cancel_waiter in done:
                await self._cancel_task(operation_task)
                raise asyncio.CancelledError(f"Agent run '{ctx.run_id}' cancelled")
            return operation_task.result()
        finally:
            await self._cancel_task(cancel_waiter)
            await self._cancel_task(operation_task)

    def _validate_tool_pairing(
        self,
        tool_calls: list[ToolCall],
        tool_results: list[ToolCallResult],
    ) -> list[ToolCallResult]:
        """Ensure every tool_call has exactly one matching tool_result, ordered by call.

        Returns the results reordered to match the tool_call sequence. Raises
        :class:`AgentError` if the executor dropped any result (fail closed).
        """
        call_ids = [call.id for call in tool_calls]
        if len(call_ids) != len(set(call_ids)):
            raise AgentError("Provider returned duplicate tool call IDs; pairing is ambiguous.")

        results_by_id: dict[str, ToolCallResult] = {}
        for res in tool_results:
            if res.tool_call_id in results_by_id:
                raise AgentError(
                    f"Duplicate tool_call_id '{res.tool_call_id}' returned from ToolExecutor.",
                )
            results_by_id[res.tool_call_id] = res

        expected_ids = set(call_ids)
        unexpected = [result_id for result_id in results_by_id if result_id not in expected_ids]
        if unexpected:
            raise AgentError(
                f"ToolExecutor returned result(s) without a matching tool call: {unexpected}.",
            )

        ordered: list[ToolCallResult] = []
        missing: list[str] = []
        for call in tool_calls:
            matched_result = results_by_id.get(call.id)
            if matched_result is None:
                missing.append(call.id)
                continue
            if matched_result.name != call.name:
                raise AgentError(
                    f"Tool result '{call.id}' names '{matched_result.name}', expected '{call.name}'.",
                )
            ordered.append(matched_result)

        if missing:
            raise AgentError(
                f"ToolExecutor did not return a result for tool call(s): {missing}. "
                "Tool call and tool result must remain paired.",
            )
        return ordered

    async def run_with_trace(
        self,
        user_input: str,
        session_id: str | None = None,
        callbacks: list[AgentCallbackHandler] | None = None,
        run_context: RunContext | None = None,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> AgentRunResult:
        """Execute the multi-step ReAct agent loop and return the complete trajectory trace.

        Parameters:
            user_input: Utterance from the user for this turn.
            session_id: Session identifier; falls back to ``default_session_id``.
            callbacks: One-off callback handlers that will observe this run's
                lifecycle in addition to the handlers registered on the agent.
            run_context: Optional :class:`RunContext` that the caller can use to
                cancel the run and correlate logs. If ``None``, a fresh context
                is created for this call.
            timeout: Wall-clock budget (seconds) for the whole run. Overrides
                ``run_context.timeout_seconds`` when both are provided.
        """
        target_session = session_id or (
            run_context.session_id if run_context and run_context.session_id else self.default_session_id
        )
        if not user_input or not user_input.strip():
            raise AgentError("User input cannot be empty.")

        ctx = run_context or RunContext.create(session_id=target_session)
        if timeout is not None:
            ctx.timeout_seconds = timeout
        ctx.session_id = target_session

        active_callbacks: list[AgentCallbackHandler] = list(self.callbacks)
        if callbacks:
            active_callbacks.extend(callbacks)

        try:
            if ctx.timeout_seconds is not None and ctx.timeout_seconds > 0:
                return await asyncio.wait_for(
                    self._run_loop(user_input, target_session, active_callbacks, ctx, kwargs),
                    timeout=ctx.timeout_seconds,
                )
            return await self._run_loop(user_input, target_session, active_callbacks, ctx, kwargs)
        except TimeoutError as exc:
            ctx.state = RunState.CANCELLED
            logger.warning(
                "Agent run '%s' cancelled: timeout after %.3fs",
                ctx.run_id,
                ctx.timeout_seconds or 0.0,
            )
            await self._dispatch(active_callbacks, "on_agent_error", session_id=target_session, error=exc)
            raise asyncio.CancelledError(f"Agent run '{ctx.run_id}' timed out") from exc

    async def _run_loop(
        self,
        user_input: str,
        target_session: str,
        active_callbacks: list[AgentCallbackHandler],
        ctx: RunContext,
        provider_kwargs: dict[str, Any],
    ) -> AgentRunResult:
        """Core state machine. See :meth:`run_with_trace` for parameter docs."""
        steps: list[AgentStep] = []
        executed_tool_call_providers: dict[str, str] = {}
        step = 0

        try:
            ctx.mark_running()
            ctx.raise_if_cancelled()

            logger.info(
                "Agent run '%s' starting for session '%s' with provider '%s'",
                ctx.run_id,
                target_session,
                self.provider.name,
            )
            await self._dispatch(
                active_callbacks,
                "on_agent_start",
                session_id=target_session,
                prompt=user_input,
            )

            memory = await self.session_manager.get_memory(target_session)
            user_message = Message.user(user_input)

            context_messages = await self._prepare_messages(memory, user_message)
            await memory.add(user_message)

            while step < self.max_steps:
                ctx.raise_if_cancelled()
                step += 1
                step_start = time.perf_counter()
                tools = self.tool_registry.get_definitions() if self.tool_registry else None

                # Fit context immediately before every provider call so both the
                # initial invocation and every post-tool-result invocation
                # respect the configured token budget.
                context_messages = await self._fit_context(context_messages)

                await self._dispatch(active_callbacks, "on_llm_start", step=step, messages=context_messages)

                try:
                    response = await self._await_or_cancel(
                        self.provider.generate(
                            context_messages,
                            tools=tools,
                            **provider_kwargs,
                        ),
                        ctx,
                    )
                except Exception as exc:
                    step_latency = (time.perf_counter() - step_start) * 1000.0
                    steps.append(
                        AgentStep(
                            step_number=step,
                            is_final=False,
                            latency_ms=round(step_latency, 2),
                            provider=self.provider.name,
                            model=getattr(self.provider, "model", None),
                            error=f"{type(exc).__name__}: {exc}",
                        )
                    )
                    logger.error(
                        "LLM generation failed for run '%s' at step %d: %s",
                        ctx.run_id,
                        step,
                        exc,
                        exc_info=True,
                    )
                    raise

                await self._dispatch(active_callbacks, "on_llm_end", step=step, response=response)

                thought = self._extract_thought(response.content)
                if thought:
                    await self._dispatch(active_callbacks, "on_thought", step=step, thought=thought)

                step_latency = (time.perf_counter() - step_start) * 1000.0

                if not response.has_tool_calls:
                    await memory.add(response.to_message())
                    total_latency = (time.perf_counter() - ctx.started_at) * 1000.0

                    steps.append(
                        AgentStep(
                            step_number=step,
                            thought=thought,
                            is_final=True,
                            latency_ms=round(step_latency, 2),
                            token_usage=response.usage,
                            provider=response.provider,
                            model=response.model,
                        )
                    )

                    ctx.state = RunState.COMPLETED
                    await self._dispatch(
                        active_callbacks,
                        "on_agent_finish",
                        session_id=target_session,
                        final_response=response,
                        total_steps=step,
                    )

                    return AgentRunResult(
                        content=response.content or "",
                        session_id=target_session,
                        run_id=ctx.run_id,
                        state=RunState.COMPLETED,
                        steps=steps,
                        total_steps=step,
                        total_latency_ms=round(total_latency, 2),
                        is_max_steps_reached=False,
                        llm_response=response,
                    )

                if self.tool_executor is None or not self.tool_registry:
                    raise AgentError(
                        f"Provider requested tool calls {response.tool_calls}, "
                        "but no ToolExecutor is configured.",
                    )

                duplicate_call_ids = [
                    tool_call.id
                    for tool_call in response.tool_calls
                    if tool_call.id in executed_tool_call_providers
                    and executed_tool_call_providers[tool_call.id] != response.provider
                ]
                if duplicate_call_ids:
                    raise AgentError(
                        "Provider attempted to repeat tool call ID(s) after their side effects "
                        f"were already processed: {duplicate_call_ids}",
                    )

                for tc in response.tool_calls:
                    await self._dispatch(
                        active_callbacks,
                        "on_tool_start",
                        step=step,
                        tool_name=tc.name,
                        arguments=tc.arguments,
                    )

                asst_tool_msg = response.to_message()
                context_messages.append(asst_tool_msg)
                await memory.add(asst_tool_msg)

                async def _confirm(call: ToolCall, step_no: int = step) -> bool:
                    for handler in active_callbacks:
                        try:
                            approved = await handler.on_tool_confirmation(
                                step=step_no,
                                tool_name=call.name,
                                arguments=call.arguments,
                            )
                        except Exception as exc:
                            logger.warning(
                                "Callback handler '%s.on_tool_confirmation' raised: %s",
                                type(handler).__name__,
                                exc,
                            )
                            continue
                        if approved is False:
                            return False
                    return True

                # Run through the same cancellation boundary as provider calls.
                assert self.tool_executor is not None  # narrowed above
                exec_ctx = ToolExecutionContext(
                    run_id=ctx.run_id,
                    step=step,
                    session_id=target_session,
                )
                tool_results_raw = await self._await_or_cancel(
                    self.tool_executor.execute_all(
                        response.tool_calls,
                        confirm=_confirm,
                        context=exec_ctx,
                    ),
                    ctx,
                )

                tool_results = self._validate_tool_pairing(response.tool_calls, tool_results_raw)
                executed_tool_call_providers.update(
                    {tool_call.id: response.provider for tool_call in response.tool_calls}
                )

                for res in tool_results:
                    await self._dispatch(
                        active_callbacks,
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
                            "Please analyze what caused this error, adjust the arguments or tool choice, and try again."
                        )

                    tool_msg = Message.tool(
                        content=content_to_record,
                        tool_call_id=res.tool_call_id,
                        name=res.name,
                        is_error=res.is_error,
                    )
                    context_messages.append(tool_msg)
                    await memory.add(tool_msg)

                step_latency = (time.perf_counter() - step_start) * 1000.0
                steps.append(
                    AgentStep(
                        step_number=step,
                        thought=thought,
                        tool_calls=response.tool_calls,
                        tool_results=tool_results,
                        is_final=False,
                        latency_ms=round(step_latency, 2),
                        token_usage=response.usage,
                        provider=response.provider,
                        model=response.model,
                    )
                )

            raise AgentError(
                f"Agent run '{ctx.run_id}' exceeded maximum execution steps "
                f"(max_steps={self.max_steps}) without producing a final answer.",
            )

        except asyncio.CancelledError:
            ctx.state = RunState.CANCELLED
            logger.info("Agent run '%s' cancelled", ctx.run_id)
            raise
        except Exception as exc:
            ctx.state = RunState.FAILED
            await self._dispatch(active_callbacks, "on_agent_error", session_id=target_session, error=exc)
            raise

    async def run(
        self,
        user_input: str,
        session_id: str | None = None,
        callbacks: list[AgentCallbackHandler] | None = None,
        run_context: RunContext | None = None,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Process user input in an isolated session context and return LLMResponse."""
        result = await self.run_with_trace(
            user_input=user_input,
            session_id=session_id,
            callbacks=callbacks,
            run_context=run_context,
            timeout=timeout,
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
        logger.info("Cleared session history for '%s'", target_session)
