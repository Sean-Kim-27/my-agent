"""Unit tests for authentication providers (API Key, Codex OAuth, NoAuth)."""

import time

import pytest

from agent_framework.auth.api_key import ApiKeyAuth
from agent_framework.auth.base import NoAuth
from agent_framework.auth.codex_oauth import CodexOAuthAuth, CodexOAuthToken
from agent_framework.exceptions import AuthenticationError, OAuthAuthenticationError


@pytest.mark.asyncio
async def test_api_key_auth_valid() -> None:
    """Test ApiKeyAuth with valid API key."""
    auth = ApiKeyAuth(api_key="sk-1234567890abcdef", provider_name="openai")
    assert await auth.is_authenticated() is True
    assert auth.masked_key == "sk-1...cdef"

    creds = await auth.get_credentials()
    assert creds.api_key == "sk-1234567890abcdef"
    assert creds.headers == {"Authorization": "Bearer sk-1234567890abcdef"}
    assert creds.get_authorization_header() == "Bearer sk-1234567890abcdef"


@pytest.mark.asyncio
async def test_api_key_auth_missing() -> None:
    """Test ApiKeyAuth with missing API key."""
    auth = ApiKeyAuth(api_key=None, provider_name="anthropic")
    assert await auth.is_authenticated() is False
    assert auth.masked_key == "<none>"

    with pytest.raises(AuthenticationError) as exc_info:
        await auth.get_credentials()
    assert "Missing or empty API key" in str(exc_info.value)


@pytest.mark.asyncio
async def test_api_key_auth_custom_header() -> None:
    """Test ApiKeyAuth with custom headers (e.g. Anthropic x-api-key)."""
    auth = ApiKeyAuth(
        api_key="my-secret-key",
        header_name="x-api-key",
        header_prefix="",
        provider_name="anthropic",
    )
    creds = await auth.get_credentials()
    assert creds.headers == {"x-api-key": "my-secret-key"}


@pytest.mark.asyncio
async def test_no_auth() -> None:
    """Test unauthenticated provider."""
    auth = NoAuth()
    assert auth.auth_type == "none"
    assert await auth.is_authenticated() is True
    await auth.validate()
    creds = await auth.get_credentials()
    assert creds.api_key is None
    assert creds.token is None


@pytest.mark.asyncio
async def test_codex_oauth_valid_token() -> None:
    """Test Codex OAuth provider with valid token."""
    future_time = time.time() + 3600  # Expires in 1 hour
    token = CodexOAuthToken(
        access_token="valid_codex_access_token_123",
        refresh_token="valid_refresh_token_456",
        expires_at=future_time,
    )
    auth = CodexOAuthAuth(token=token)

    assert await auth.is_authenticated() is True
    creds = await auth.get_credentials()
    assert creds.token == "valid_codex_access_token_123"
    assert creds.headers == {"Authorization": "Bearer valid_codex_access_token_123"}


@pytest.mark.asyncio
async def test_codex_oauth_missing_token() -> None:
    """Test Codex OAuth provider with missing token."""
    auth = CodexOAuthAuth(token=None)
    assert await auth.is_authenticated() is False

    with pytest.raises(OAuthAuthenticationError) as exc_info:
        await auth.validate()
    assert "Missing Codex OAuth access token" in str(exc_info.value)


@pytest.mark.asyncio
async def test_codex_oauth_expired_with_refresh() -> None:
    """Test Codex OAuth token expiration and automatic refresh callback."""
    past_time = time.time() - 100  # Expired
    expired_token = CodexOAuthToken(
        access_token="expired_token",
        refresh_token="ref_123",
        expires_at=past_time,
    )

    async def mock_refresh(ref_tok: str) -> CodexOAuthToken:
        assert ref_tok == "ref_123"
        return CodexOAuthToken(
            access_token="new_refreshed_access_token",
            refresh_token="new_ref_456",
            expires_at=time.time() + 3600,
        )

    auth = CodexOAuthAuth(token=expired_token, refresh_callback=mock_refresh)
    assert await auth.is_authenticated() is False

    # Calling get_credentials triggers refresh
    creds = await auth.get_credentials()
    assert creds.token == "new_refreshed_access_token"
    assert await auth.is_authenticated() is True
