"""Provider-neutral error normalization and retry metadata extraction."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

from agent_framework.exceptions import (
    AuthenticationError,
    FallbackExhaustedError,
    InvalidRequestError,
    LLMProviderError,
    ProviderAuthenticationError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    RateLimitError,
)
from agent_framework.logging.logger import mask_secrets


def _exception_chain(exc: BaseException) -> Iterator[BaseException]:
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def _status_code(exc: BaseException) -> int | None:
    for item in _exception_chain(exc):
        status = getattr(item, "status_code", None)
        if isinstance(status, int):
            return status
        response = getattr(item, "response", None)
        status = getattr(response, "status_code", None)
        if isinstance(status, int):
            return status
    return None


def _headers(exc: BaseException) -> Any:
    for item in _exception_chain(exc):
        response = getattr(item, "response", None)
        headers = getattr(response, "headers", None)
        if headers is not None:
            return headers
    return None


def retry_after_seconds(exc: BaseException, *, now: datetime | None = None) -> float | None:
    """Extract an HTTP Retry-After delta or date from an exception chain."""
    if isinstance(exc, LLMProviderError):
        configured = exc.details.get("retry_after_seconds")
        if isinstance(configured, (int, float)) and configured >= 0:
            return float(configured)

    headers = _headers(exc)
    if headers is None:
        return None
    raw = headers.get("retry-after") or headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        try:
            parsed = parsedate_to_datetime(str(raw))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            reference = now or datetime.now(UTC)
            return max(0.0, (parsed - reference).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return None


def timeout_phase(exc: BaseException) -> str | None:
    """Identify the HTTP timeout phase when an SDK preserves the transport cause."""
    phases = {
        "ConnectTimeout": "connect",
        "ReadTimeout": "read",
        "WriteTimeout": "write",
        "PoolTimeout": "pool",
    }
    for item in _exception_chain(exc):
        phase = phases.get(type(item).__name__)
        if phase is not None:
            return phase
    return None


def normalize_provider_error(
    exc: Exception,
    *,
    provider: str,
    model: str,
) -> LLMProviderError:
    """Map SDK, transport, auth, and unexpected failures to the common hierarchy."""
    if isinstance(exc, FallbackExhaustedError):
        return exc
    status = _status_code(exc)
    safe_message = mask_secrets(str(exc))
    details: dict[str, Any] = {"error_type": type(exc).__name__}
    retry_after = retry_after_seconds(exc)
    if retry_after is not None:
        details["retry_after_seconds"] = retry_after
    phase = timeout_phase(exc)
    if phase is not None:
        details["timeout_phase"] = phase

    if isinstance(exc, ProviderAuthenticationError):
        error_type: type[LLMProviderError] = ProviderAuthenticationError
    elif isinstance(exc, AuthenticationError) or status in {401, 403}:
        error_type = ProviderAuthenticationError
    elif isinstance(exc, InvalidRequestError) or (
        status is not None and 400 <= status < 500 and status not in {408, 429}
    ):
        error_type = InvalidRequestError
    elif isinstance(exc, RateLimitError) or status == 429:
        error_type = RateLimitError
    elif (
        isinstance(exc, ProviderTimeoutError)
        or status == 408
        or "Timeout" in type(exc).__name__
        or isinstance(exc, TimeoutError)
    ):
        error_type = ProviderTimeoutError
    elif isinstance(exc, ProviderUnavailableError) or status is not None and status >= 500:
        error_type = ProviderUnavailableError
    elif type(exc).__name__ in {"APIConnectionError", "ConnectError", "NetworkError"}:
        error_type = ProviderUnavailableError
    else:
        error_type = LLMProviderError

    return error_type(
        message=safe_message,
        provider=provider,
        model=model,
        status_code=status,
        details=details,
    )
