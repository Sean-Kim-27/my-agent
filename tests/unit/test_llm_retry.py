"""Tests for the LLM retry/backoff wrapper."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from agent_framework.llm.retry import call_with_retry, is_retryable_error


class _FakeStatusError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"status={status_code}")
        self.status_code = status_code


class RateLimitError(Exception):
    pass


class APITimeoutError(Exception):
    pass


class AuthError(Exception):
    def __init__(self, status_code: int = 401) -> None:
        super().__init__("unauthorized")
        self.status_code = status_code


def test_is_retryable_error_classifies_transient_failures() -> None:
    assert is_retryable_error(TimeoutError()) is True
    assert is_retryable_error(RateLimitError()) is True
    assert is_retryable_error(APITimeoutError()) is True


def test_is_retryable_error_rejects_auth_failures() -> None:
    assert is_retryable_error(AuthError(401)) is False
    assert is_retryable_error(ValueError("bad input")) is False


async def test_call_with_retry_retries_and_succeeds() -> None:
    fn = AsyncMock(side_effect=[RateLimitError(), RateLimitError(), "ok"])
    result = await call_with_retry(fn, max_retries=3, initial_wait=0.01, max_wait=0.02)
    assert result == "ok"
    assert fn.call_count == 3


async def test_call_with_retry_propagates_non_retryable() -> None:
    fn = AsyncMock(side_effect=AuthError(401))
    with pytest.raises(AuthError):
        await call_with_retry(fn, max_retries=3, initial_wait=0.01, max_wait=0.02)
    assert fn.call_count == 1


async def test_call_with_retry_gives_up_after_max_attempts() -> None:
    fn = AsyncMock(side_effect=RateLimitError())
    with pytest.raises(RateLimitError):
        await call_with_retry(fn, max_retries=2, initial_wait=0.01, max_wait=0.02)
    assert fn.call_count == 3


async def test_call_with_retry_treats_5xx_as_retryable() -> None:
    err = _FakeStatusError(503)
    # Fake status errors need a recognized class name — patch via subclass
    class InternalServerError(_FakeStatusError):
        pass

    fn = AsyncMock(side_effect=[InternalServerError(500), "recovered"])
    result = await call_with_retry(fn, max_retries=2, initial_wait=0.01, max_wait=0.02)
    assert result == "recovered"
    assert fn.call_count == 2
    _ = err
