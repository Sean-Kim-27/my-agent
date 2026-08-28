"""API Key authentication implementation."""

from agent_framework.auth.base import AuthCredentials, AuthenticationProvider
from agent_framework.exceptions import AuthenticationError


class ApiKeyAuth(AuthenticationProvider):
    """Authentication provider using an API Key."""

    def __init__(
        self,
        api_key: str | None,
        header_name: str = "Authorization",
        header_prefix: str = "Bearer ",
        provider_name: str = "generic",
    ) -> None:
        self._api_key = api_key
        self._header_name = header_name
        self._header_prefix = header_prefix
        self._provider_name = provider_name

    @property
    def auth_type(self) -> str:
        return "api_key"

    @property
    def api_key(self) -> str | None:
        """Return raw API key."""
        return self._api_key

    @property
    def masked_key(self) -> str:
        """Return a safely masked representation of the API key."""
        if not self._api_key:
            return "<none>"
        if len(self._api_key) <= 8:
            return "***"
        return f"{self._api_key[:4]}...{self._api_key[-4:]}"

    async def is_authenticated(self) -> bool:
        """Check if an API key is present."""
        return bool(self._api_key and self._api_key.strip())

    async def validate(self) -> None:
        """Validate API key presence."""
        if not await self.is_authenticated():
            raise AuthenticationError(
                message=f"Missing or empty API key for provider '{self._provider_name}'",
                auth_type=self.auth_type,
                details={"provider": self._provider_name},
            )

    async def get_credentials(self) -> AuthCredentials:
        """Return formatted credentials for request headers."""
        await self.validate()
        assert self._api_key is not None
        if self._header_name.lower() == "authorization" and self._header_prefix.startswith("Bearer"):
            return AuthCredentials(
                api_key=self._api_key,
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
        return AuthCredentials(
            api_key=self._api_key,
            headers={self._header_name: f"{self._header_prefix}{self._api_key}"},
        )
