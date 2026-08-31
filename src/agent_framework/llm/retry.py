"""Retry policy for LLM provider calls.

Retries transient failures (network timeouts, 429 rate-limits, 5xx server errors)
with exponential backoff. Client errors like 4xx auth failures propagate immediately.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from typing import Any

from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception,
    stop_after_attempt,
)

from agent_framework.exceptions import (
    ProviderTimeoutError,
    ProviderUnavailableError,
    RateLimitError,
)
from agent_framework.llm.errors import retry_after_seconds
from agent_framework.logging.logger import get_logger

logger = get_logger("agent_framework.llm.retry")


def _http_status_code(exc: BaseException) -> int | None:
    """Best-effort extraction of an HTTP status code from a provider exception."""
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return status
    response = getattr(exc, "response", None)
    if response is not None:
        status = getattr(response, "status_code", None)
        if isinstance(status, int):
            return status
    return None


def is_retryable_error(exc: BaseException) -> bool:
    """Return True if the exception represents a transient LLM API failure."""
    # Timeouts and network-layer failures are always retryable.
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        return True
    if isinstance(exc, (ProviderTimeoutError, ProviderUnavailableError, RateLimitError)):
        return True

    exc_name = type(exc).__name__
    transient_names = {
        "APITimeoutError",
        "APIConnectionError",
        "RateLimitError",
        "InternalServerError",
        "ServiceUnavailableError",
        "APIStatusError",
    }
    if exc_name in transient_names:
        # For APIStatusError we still need to distinguish by status code below.
        status = _http_status_code(exc)
        if status is None:
            return exc_name != "APIStatusError"
        return status == 429 or status >= 500

    # Generic httpx errors
    module = type(exc).__module__
    if module.startswith("httpx"):
        if "Timeout" in exc_name or "ConnectError" in exc_name or "NetworkError" in exc_name:
            return True
        status = _http_status_code(exc)
        if status is not None:
            return status == 429 or status >= 500

    return False


class WaitRetryAfterOrExponentialJitter:
    """Tenacity wait strategy that prioritizes Retry-After over local backoff."""

    def __init__(self, initial_wait: float, max_wait: float, jitter: float) -> None:
        self.initial_wait = initial_wait
        self.max_wait = max_wait
        self.jitter = jitter

    def __call__(self, retry_state: Any) -> float:
        exc = retry_state.outcome.exception() if retry_state.outcome is not None else None
        if isinstance(exc, BaseException):
            retry_after = retry_after_seconds(exc)
            if retry_after is not None:
                return retry_after
        attempt_number = int(retry_state.attempt_number)
        exponent = max(0, attempt_number - 1)
        base = float(min(self.max_wait, self.initial_wait * (2**exponent)))
        return base + random.uniform(0.0, min(self.jitter, base))


async def call_with_retry(
    func: Any,
    /,
    *args: Any,
    max_retries: int = 3,
    initial_wait: float = 1.0,
    max_wait: float = 10.0,
    jitter: float = 1.0,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    **kwargs: Any,
) -> Any:
    """Invoke an async callable with exponential-backoff retry on transient errors."""
    attempts = max(1, max_retries + 1)
    try:
        async for attempt in AsyncRetrying(
            reraise=True,
            stop=stop_after_attempt(attempts),
            wait=WaitRetryAfterOrExponentialJitter(initial_wait, max_wait, jitter),
            retry=retry_if_exception(is_retryable_error),
            sleep=sleep,
        ):
            with attempt:
                if attempt.retry_state.attempt_number > 1:
                    logger.warning(
                        "Retrying LLM call "
                        f"(attempt {attempt.retry_state.attempt_number}/{attempts})"
                    )
                return await func(*args, **kwargs)
    except RetryError as exc:  # pragma: no cover - reraise=True prevents this
        last_exc = exc.last_attempt.exception()
        if isinstance(last_exc, BaseException):
            raise last_exc from exc
        raise
    raise RuntimeError("call_with_retry exited without producing a result")
