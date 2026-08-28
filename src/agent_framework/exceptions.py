"""Exception hierarchy for the Agent Framework."""

from typing import Any


class AgentFrameworkError(Exception):
    """Base exception for all agent framework errors."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __str__(self) -> str:
        if self.details:
            return f"{self.message} (details: {self.details})"
        return self.message


class AgentError(AgentFrameworkError):
    """Raised when an error occurs during Agent execution."""


class LLMProviderError(AgentFrameworkError):
    """Raised when an LLM provider encounters an error."""

    def __init__(
        self,
        message: str,
        provider: str = "unknown",
        model: str | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        merged_details = details or {}
        merged_details["provider"] = provider
        if model:
            merged_details["model"] = model
        if status_code is not None:
            merged_details["status_code"] = status_code
        super().__init__(message, details=merged_details)
        self.provider = provider
        self.model = model
        self.status_code = status_code


class ProviderUnavailableError(LLMProviderError):
    """Raised when the LLM provider service is unreachable or returns 502/503/504."""


class RateLimitError(LLMProviderError):
    """Raised when the LLM provider rate limit is exceeded."""


class ProviderTimeoutError(LLMProviderError):
    """Raised when a request to the LLM provider times out."""


class InvalidRequestError(LLMProviderError):
    """Raised when the LLM provider rejects the request payload."""


class AuthenticationError(AgentFrameworkError):
    """Raised when authentication fails (invalid API key, missing credentials)."""

    def __init__(
        self,
        message: str,
        auth_type: str = "unknown",
        details: dict[str, Any] | None = None,
    ) -> None:
        merged_details = details or {}
        merged_details["auth_type"] = auth_type
        super().__init__(message, details=merged_details)
        self.auth_type = auth_type


class OAuthAuthenticationError(AuthenticationError):
    """Raised when OAuth token retrieval, validation, or refresh fails."""


class MemoryError(AgentFrameworkError):
    """Raised when an error occurs in conversation memory storage or retrieval."""


class SessionError(AgentFrameworkError):
    """Raised when an error occurs in session management."""


class ConfigurationError(AgentFrameworkError):
    """Raised when required configuration settings are missing or invalid."""
