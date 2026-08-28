"""Codex / ChatGPT OAuth authentication implementation.

Security and Design Notice:
    This module implements an official OAuth 2.0 credential lifecycle contract for
    OpenAI/Codex authentication. It adheres strictly to ethical and secure authentication
    principles:
    1. It NEVER attempts browser session cookie extraction or storage theft.
    2. It NEVER attempts unauthorized parsing of internal IDE configuration files.
    3. It NEVER calls unofficial or reverse-engineered OAuth endpoints.
    4. Credential tokens are handled in memory or retrieved via official credential providers.
"""

import time
from collections.abc import Awaitable, Callable

from pydantic import BaseModel, Field

from agent_framework.auth.base import AuthCredentials, AuthenticationProvider
from agent_framework.exceptions import OAuthAuthenticationError


class CodexOAuthToken(BaseModel):
    """Container for official Codex/OpenAI OAuth tokens."""

    access_token: str = Field(..., description="Active OAuth Bearer access token")
    refresh_token: str | None = Field(default=None, description="Optional OAuth refresh token")
    token_type: str = Field(default="Bearer", description="OAuth token type")
    expires_at: float | None = Field(default=None, description="Epoch timestamp when token expires")
    scope: str | None = Field(default=None, description="Authorized OAuth scopes")

    @property
    def is_expired(self) -> bool:
        """Check if the access token has expired with a 60-second safety margin."""
        if self.expires_at is None:
            return False
        return time.time() >= (self.expires_at - 60)


# Type alias for custom async token refresh callback
TokenRefreshCallback = Callable[[str], Awaitable[CodexOAuthToken]]


class CodexOAuthAuth(AuthenticationProvider):
    """Authentication provider for Codex / ChatGPT OAuth tokens.

    Supports in-memory token state, token expiration verification, and pluggable
    official OAuth refresh handlers.
    """

    def __init__(
        self,
        token: CodexOAuthToken | None = None,
        refresh_callback: TokenRefreshCallback | None = None,
    ) -> None:
        self._token = token
        self._refresh_callback = refresh_callback

    @property
    def auth_type(self) -> str:
        return "codex_oauth"

    @property
    def current_token(self) -> CodexOAuthToken | None:
        """Return the current token container."""
        return self._token

    def set_token(self, token: CodexOAuthToken) -> None:
        """Update the active OAuth token."""
        self._token = token

    async def is_authenticated(self) -> bool:
        """Check if a valid, non-expired access token is available."""
        if self._token is None or not self._token.access_token:
            return False
        return not self._token.is_expired

    async def refresh_if_needed(self) -> None:
        """Refresh the access token if expired and a refresh callback is registered."""
        if self._token is None:
            raise OAuthAuthenticationError(
                message="No Codex OAuth token configured",
                auth_type=self.auth_type,
            )

        if self._token.is_expired:
            if not self._token.refresh_token:
                raise OAuthAuthenticationError(
                    message="Codex OAuth token has expired and no refresh token is present",
                    auth_type=self.auth_type,
                )
            if self._refresh_callback is None:
                raise OAuthAuthenticationError(
                    message="Codex OAuth token is expired and no refresh callback is configured",
                    auth_type=self.auth_type,
                )
            try:
                refreshed = await self._refresh_callback(self._token.refresh_token)
                self._token = refreshed
            except Exception as exc:
                raise OAuthAuthenticationError(
                    message=f"Failed to refresh Codex OAuth token: {exc}",
                    auth_type=self.auth_type,
                    details={"error": str(exc)},
                ) from exc

    async def validate(self) -> None:
        """Validate token availability and freshness."""
        if self._token is None or not self._token.access_token.strip():
            raise OAuthAuthenticationError(
                message="Missing Codex OAuth access token. Please authenticate via official OAuth flow.",
                auth_type=self.auth_type,
            )
        await self.refresh_if_needed()

    async def get_credentials(self) -> AuthCredentials:
        """Return AuthCredentials containing the OAuth Bearer token."""
        await self.validate()
        assert self._token is not None
        return AuthCredentials(
            token=self._token.access_token,
            token_type=self._token.token_type,
            headers={
                "Authorization": f"{self._token.token_type} {self._token.access_token}",
            },
        )
