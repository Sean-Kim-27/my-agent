"""OpenAI LLM Provider implementation supporting API Key and Codex OAuth authentication."""

from openai import AsyncOpenAI

from agent_framework.auth.api_key import ApiKeyAuth
from agent_framework.auth.base import AuthenticationProvider
from agent_framework.llm.openai_compatible import OpenAICompatibleProvider
from agent_framework.models.response import ProviderCapabilities, ProviderTimeouts

# Publicly documented context windows for common OpenAI chat models. Used only
# when the caller does not supply an explicit ProviderCapabilities.
_OPENAI_CONTEXT_WINDOWS: dict[str, int] = {
    "gpt-4o": 128_000,
    "gpt-4o-mini": 128_000,
    "gpt-4-turbo": 128_000,
    "gpt-4": 8_192,
    "gpt-3.5-turbo": 16_385,
}


def _lookup_context_window(model: str, table: dict[str, int]) -> int | None:
    if model in table:
        return table[model]
    for prefix, window in table.items():
        if model.startswith(prefix):
            return window
    return None


class OpenAIProvider(OpenAICompatibleProvider):
    """LLM Provider for OpenAI API and Codex OAuth."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4o-mini",
        base_url: str = "https://api.openai.com/v1",
        auth: AuthenticationProvider | None = None,
        timeout: float | ProviderTimeouts = 60.0,
        extra_headers: dict[str, str] | None = None,
        capabilities: ProviderCapabilities | None = None,
        client: AsyncOpenAI | None = None,
    ) -> None:
        # If no auth provider was provided but api_key was, wrap it in ApiKeyAuth
        if auth is None and api_key is not None:
            auth = ApiKeyAuth(api_key=api_key, provider_name="openai")

        default_caps = capabilities or ProviderCapabilities(
            tool_calling=True,
            streaming=True,
            vision=True,
            json_mode=True,
            system_prompt_supported=True,
            context_window=_lookup_context_window(model, _OPENAI_CONTEXT_WINDOWS),
        )

        super().__init__(
            name="openai",
            model=model,
            base_url=base_url,
            auth=auth,
            timeout=timeout,
            extra_headers=extra_headers,
            capabilities=default_caps,
            client=client,
        )
