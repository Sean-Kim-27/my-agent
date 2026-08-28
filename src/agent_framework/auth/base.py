"""Authentication provider abstractions and credential models."""

from abc import ABC, abstractmethod

from pydantic import BaseModel, Field


class AuthCredentials(BaseModel):
    """Standardized credential container for LLM provider authentication."""

    api_key: str | None = Field(default=None, description="Raw API key if using key-based authentication")
    token: str | None = Field(default=None, description="OAuth or Bearer access token")
    token_type: str = Field(default="Bearer", description="HTTP authorization token scheme")
    headers: dict[str, str] = Field(default_factory=dict, description="Pre-computed HTTP request headers")

    def get_authorization_header(self) -> str | None:
        """Construct the standard Authorization header value."""
        if self.token:
            return f"{self.token_type} {self.token}".strip()
        if self.api_key:
            return f"Bearer {self.api_key}"
        return None


class AuthenticationProvider(ABC):
    """Abstract interface for credential providers."""

    @property
    @abstractmethod
    def auth_type(self) -> str:
        """Return the unique identifier for this authentication method."""

    @abstractmethod
    async def get_credentials(self) -> AuthCredentials:
        """Retrieve active credentials for outbound LLM requests."""

    @abstractmethod
    async def is_authenticated(self) -> bool:
        """Check whether valid authentication credentials are available."""

    @abstractmethod
    async def validate(self) -> None:
        """Validate credentials, raising AuthenticationError if invalid or missing."""


class NoAuth(AuthenticationProvider):
    """Authentication provider for local or unauthenticated endpoints (e.g. local Ollama)."""

    @property
    def auth_type(self) -> str:
        return "none"

    async def get_credentials(self) -> AuthCredentials:
        return AuthCredentials()

    async def is_authenticated(self) -> bool:
        return True

    async def validate(self) -> None:
        return None
