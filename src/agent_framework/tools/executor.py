"""Tool execution engine handling validation, policy, timeouts, retries, and serialization."""

from __future__ import annotations

import asyncio
import inspect
import json
import time
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel

from agent_framework.execution.approval import ApprovalService
from agent_framework.logging.logger import get_logger, redact_sensitive_data
from agent_framework.models.tool import (
    ToolArtifact,
    ToolCall,
    ToolCallResult,
    ToolDefinition,
    ToolExecutionContext,
    ToolRiskLevel,
)
from agent_framework.tools.policy import DefaultToolPolicy, ToolPolicy
from agent_framework.tools.registry import ToolRegistry
from agent_framework.tools.schema import validate_arguments

ConfirmationCallback = Callable[[ToolCall], Awaitable[bool]]

logger = get_logger("agent_framework.tools.executor")

_DEFAULT_MAX_OUTPUT_BYTES = 32_768


class ToolExecutor:
    """Executes registered tools safely with validation, policy, timeouts, and retries."""

    def __init__(
        self,
        registry: ToolRegistry,
        default_timeout: float = 30.0,
        *,
        policy: ToolPolicy | None = None,
        approval_service: ApprovalService | None = None,
        max_retries: int = 0,
        default_max_output_bytes: int | None = _DEFAULT_MAX_OUTPUT_BYTES,
    ) -> None:
        self.registry = registry
        self.default_timeout = default_timeout
        self.policy: ToolPolicy = policy or DefaultToolPolicy()
        self.approval_service = approval_service
        self.max_retries = max(0, max_retries)
        self.default_max_output_bytes = default_max_output_bytes
        self._semaphores: dict[str, asyncio.Semaphore] = {}
        self._sem_lock = asyncio.Lock()

    # ------------------------------------------------------------ Helpers

    def _error_result(
        self,
        *,
        tool_call: ToolCall,
        message: str,
    ) -> ToolCallResult:
        return ToolCallResult(
            tool_call_id=tool_call.id,
            name=tool_call.name,
            content=message,
            is_error=True,
        )

    def _serialize_result(self, result: Any) -> str:
        if result is None:
            return "Success (null output)"
        if isinstance(result, str):
            return result
        if isinstance(result, BaseModel):
            return result.model_dump_json()
        if isinstance(result, (dict, list, int, float, bool)):
            try:
                return json.dumps(result, ensure_ascii=False)
            except Exception:
                return str(result)
        return str(result)

    def _apply_output_cap(
        self,
        tool_call: ToolCall,
        definition: ToolDefinition | None,
        payload: str,
    ) -> tuple[str, ToolArtifact | None]:
        limit = (
            definition.max_output_bytes
            if definition is not None and definition.max_output_bytes is not None
            else self.default_max_output_bytes
        )
        if limit is None:
            return payload, None
        encoded = payload.encode("utf-8")
        if len(encoded) <= limit:
            return payload, None

        truncated = encoded[: max(0, limit - 32)].decode("utf-8", errors="ignore")
        total = len(encoded)
        summary = (
            f"{truncated}\n[...truncated, {total} bytes total; full output in artifact]"
        )
        artifact = ToolArtifact(
            tool_call_id=tool_call.id,
            content_type="text/plain",
            total_bytes=total,
            truncated=True,
            payload=payload,
        )
        return summary, artifact

    async def _get_semaphore(self, definition: ToolDefinition) -> asyncio.Semaphore | None:
        if definition.max_concurrency is None or definition.max_concurrency <= 0:
            return None
        async with self._sem_lock:
            sem = self._semaphores.get(definition.name)
            if sem is None:
                sem = asyncio.Semaphore(definition.max_concurrency)
                self._semaphores[definition.name] = sem
            return sem

    # ------------------------------------------------------------ Execute

    async def execute(
        self,
        tool_call: ToolCall,
        timeout: float | None = None,
        confirm: ConfirmationCallback | None = None,
        *,
        context: ToolExecutionContext | None = None,
    ) -> ToolCallResult:
        """Validate, authorize, and execute a single ToolCall."""
        start_time = time.perf_counter()
        tool_name = tool_call.name
        effective_timeout = timeout or self.default_timeout

        func = self.registry.get(tool_name)
        definition = self.registry.get_definition(tool_name)
        if func is None or definition is None:
            logger.warning("Tool not found or disabled: '%s'", tool_name)
            return self._error_result(
                tool_call=tool_call,
                message=f"Error: Tool '{tool_name}' is not registered or is disabled.",
            )

        # ---- Argument parsing ------------------------------------------------
        raw_args = tool_call.arguments
        args_dict: dict[str, Any] = {}
        if isinstance(raw_args, str):
            try:
                args_dict = json.loads(raw_args) if raw_args.strip() else {}
            except Exception as exc:
                return self._error_result(
                    tool_call=tool_call,
                    message=f"Error: Failed to parse tool arguments JSON: {exc}",
                )
        elif isinstance(raw_args, dict):
            args_dict = raw_args

        # ---- Argument validation (fail closed) -------------------------------
        cleaned_args, errors = validate_arguments(func, args_dict)
        if errors:
            joined = "; ".join(errors)
            logger.warning("Argument validation failed for '%s': %s", tool_name, joined)
            return self._error_result(
                tool_call=tool_call,
                message=f"Error: Invalid arguments for '{tool_name}': {joined}",
            )

        # ---- Policy evaluation -----------------------------------------------
        run_context = context or ToolExecutionContext(run_id="unknown", step=0)
        decision = self.policy.evaluate(
            call=tool_call,
            definition=definition,
            context=run_context,
        )
        if not decision.allow:
            reason = decision.reason or "denied by policy"
            logger.warning("Policy denied '%s': %s", tool_name, reason)
            return self._error_result(
                tool_call=tool_call,
                message=f"Error: Tool '{tool_name}' was denied by policy: {reason}",
            )

        if decision.require_confirmation:
            if confirm is None:
                return self._error_result(
                    tool_call=tool_call,
                    message=(
                        f"Error: Tool '{tool_name}' requires human confirmation, "
                        "but no confirmation handler is configured."
                    ),
                )
            approval_request = None
            actor = run_context.actor or run_context.session_id or "unknown"
            approval_service = self.approval_service
            if approval_service is not None:
                approval_request = approval_service.request(
                    tool_name=tool_name,
                    arguments=cleaned_args,
                    actor=actor,
                )
            try:
                approved = await confirm(tool_call)
            except Exception as exc:
                if approval_request is not None and approval_service is not None:
                    approval_service.reject(
                        approval_request.id,
                        approver=actor,
                        reason="confirmation handler failed",
                    )
                logger.error("Confirmation callback raised for '%s': %s", tool_name, exc)
                return self._error_result(
                    tool_call=tool_call,
                    message=f"Error: Confirmation handler raised {type(exc).__name__}: {exc}",
                )
            if not approved:
                if approval_request is not None and approval_service is not None:
                    approval_service.reject(
                        approval_request.id,
                        approver=actor,
                        reason="rejected by confirmation handler",
                    )
                return self._error_result(
                    tool_call=tool_call,
                    message=(
                        f"Error: Human operator rejected the '{tool_name}' call. "
                        "Adjust your plan or ask the user for guidance."
                        ),
                )
            if approval_request is not None and approval_service is not None:
                approval_service.approve(approval_request.id, approver=actor)

        # ---- Retry policy ----------------------------------------------------
        can_retry = (
            definition.idempotent and definition.risk_level is not ToolRiskLevel.DESTRUCTIVE
        )
        attempts_allowed = self.max_retries + 1 if can_retry else 1

        semaphore = await self._get_semaphore(definition)

        logger.info(
            "Executing tool '%s' args=%s risk=%s idempotent=%s",
            tool_name,
            redact_sensitive_data(cleaned_args),
            definition.risk_level.value,
            definition.idempotent,
        )

        last_error: BaseException | None = None
        for attempt in range(1, attempts_allowed + 1):
            try:
                if semaphore is not None:
                    async with semaphore:
                        payload = await self._invoke(func, cleaned_args, effective_timeout)
                else:
                    payload = await self._invoke(func, cleaned_args, effective_timeout)
            except TimeoutError as exc:
                last_error = exc
                logger.warning(
                    "Tool '%s' timed out after %.2fs (attempt %d/%d)",
                    tool_name,
                    effective_timeout,
                    attempt,
                    attempts_allowed,
                )
                if attempt < attempts_allowed:
                    continue
                return self._error_result(
                    tool_call=tool_call,
                    message=f"Error: Tool '{tool_name}' timed out after {effective_timeout}s",
                )
            except Exception as exc:
                last_error = exc
                logger.error(
                    "Tool '%s' raised %s on attempt %d/%d",
                    tool_name,
                    type(exc).__name__,
                    attempt,
                    attempts_allowed,
                    exc_info=True,
                )
                if attempt < attempts_allowed:
                    continue
                return self._error_result(
                    tool_call=tool_call,
                    message=f"Error executing tool '{tool_name}': {type(exc).__name__}: {exc}",
                )

            serialized = self._serialize_result(payload)
            summary, artifact = self._apply_output_cap(tool_call, definition, serialized)
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            logger.info("Tool '%s' completed in %.2fms", tool_name, elapsed_ms)
            return ToolCallResult(
                tool_call_id=tool_call.id,
                name=tool_call.name,
                content=summary,
                is_error=False,
                artifact=artifact,
            )

        # Unreachable: loop always returns; keep for type checker.
        return self._error_result(
            tool_call=tool_call,
            message=f"Error executing tool '{tool_name}': {last_error!r}",
        )

    async def _invoke(
        self,
        func: Callable[..., Any],
        cleaned_args: dict[str, Any],
        effective_timeout: float,
    ) -> Any:
        if inspect.iscoroutinefunction(func):
            return await asyncio.wait_for(func(**cleaned_args), timeout=effective_timeout)
        return await asyncio.wait_for(
            asyncio.to_thread(func, **cleaned_args),
            timeout=effective_timeout,
        )

    async def execute_all(
        self,
        tool_calls: list[ToolCall],
        timeout: float | None = None,
        confirm: ConfirmationCallback | None = None,
        *,
        context: ToolExecutionContext | None = None,
    ) -> list[ToolCallResult]:
        """Execute multiple tool calls concurrently."""
        tasks = [
            self.execute(tc, timeout=timeout, confirm=confirm, context=context)
            for tc in tool_calls
        ]
        return await asyncio.gather(*tasks)
