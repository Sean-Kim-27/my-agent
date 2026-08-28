"""Tool execution engine handling synchronous/asynchronous execution, timeouts, and serialization."""

import asyncio
import inspect
import json
import time
from typing import Any

from pydantic import BaseModel

from agent_framework.logging.logger import get_logger
from agent_framework.models.tool import ToolCall, ToolCallResult
from agent_framework.tools.registry import ToolRegistry

logger = get_logger("agent_framework.tools.executor")


class ToolExecutor:
    """Executes registered tools safely with timeout and error containment."""

    def __init__(
        self,
        registry: ToolRegistry,
        default_timeout: float = 30.0,
    ) -> None:
        self.registry = registry
        self.default_timeout = default_timeout

    def _serialize_result(self, result: Any) -> str:
        """Serialize a tool execution result into a string."""
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

    async def execute(
        self,
        tool_call: ToolCall,
        timeout: float | None = None,
    ) -> ToolCallResult:
        """Execute a single ToolCall."""
        start_time = time.perf_counter()
        tool_name = tool_call.name
        tool_id = tool_call.id
        effective_timeout = timeout or self.default_timeout

        func = self.registry.get(tool_name)
        if func is None:
            logger.warning(f"Tool not found: '{tool_name}' (call_id: {tool_id})")
            return ToolCallResult(
                tool_call_id=tool_id,
                name=tool_name,
                content=f"Error: Tool '{tool_name}' is not registered.",
                is_error=True,
            )

        # Parse arguments
        raw_args = tool_call.arguments
        args_dict: dict[str, Any] = {}
        if isinstance(raw_args, str):
            try:
                args_dict = json.loads(raw_args) if raw_args.strip() else {}
            except Exception as exc:
                return ToolCallResult(
                    tool_call_id=tool_id,
                    name=tool_name,
                    content=f"Error: Failed to parse tool arguments JSON: {exc}",
                    is_error=True,
                )
        elif isinstance(raw_args, dict):
            args_dict = raw_args

        logger.info(f"Executing tool '{tool_name}' with args: {args_dict}")

        try:
            if inspect.iscoroutinefunction(func):
                result_coro = func(**args_dict)
                result = await asyncio.wait_for(result_coro, timeout=effective_timeout)
            else:
                # Synchronous function execution in worker thread
                result = await asyncio.wait_for(
                    asyncio.to_thread(func, **args_dict),
                    timeout=effective_timeout,
                )

            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            serialized = self._serialize_result(result)
            logger.info(f"Tool '{tool_name}' completed in {elapsed_ms:.2f}ms")

            return ToolCallResult(
                tool_call_id=tool_id,
                name=tool_name,
                content=serialized,
                is_error=False,
            )

        except TimeoutError:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            msg = f"Error: Tool '{tool_name}' timed out after {effective_timeout}s"
            logger.error(msg)
            return ToolCallResult(
                tool_call_id=tool_id,
                name=tool_name,
                content=msg,
                is_error=True,
            )
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            msg = f"Error executing tool '{tool_name}': {type(exc).__name__}: {exc}"
            logger.error(msg, exc_info=True)
            return ToolCallResult(
                tool_call_id=tool_id,
                name=tool_name,
                content=msg,
                is_error=True,
            )

    async def execute_all(
        self,
        tool_calls: list[ToolCall],
        timeout: float | None = None,
    ) -> list[ToolCallResult]:
        """Execute multiple tool calls concurrently."""
        tasks = [self.execute(tc, timeout=timeout) for tc in tool_calls]
        return await asyncio.gather(*tasks)
