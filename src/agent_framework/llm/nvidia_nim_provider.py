"""NVIDIA NIM Provider implementation.

Leverages the OpenAI-compatible transport with NVIDIA NIM specific defaults,
endpoints (https://integrate.api.nvidia.com/v1), and authentication.
"""

from openai import AsyncOpenAI

from agent_framework.auth.api_key import ApiKeyAuth
from agent_framework.auth.base import AuthenticationProvider
from agent_framework.llm.openai_compatible import OpenAICompatibleProvider
from agent_framework.models.response import ProviderCapabilities


class NvidiaNIMProvider(OpenAICompatibleProvider):
    """LLM Provider for NVIDIA NIM hosted and self-hosted microservices."""

    DEFAULT_BASE_URL = "https://integrate.api.nvidia.com/v1"
    DEFAULT_MODEL = "meta/llama-3.1-70b-instruct"

    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
        auth: AuthenticationProvider | None = None,
        timeout: float = 60.0,
        extra_headers: dict[str, str] | None = None,
        capabilities: ProviderCapabilities | None = None,
        client: AsyncOpenAI | None = None,
    ) -> None:
        if auth is None and api_key is not None:
            auth = ApiKeyAuth(api_key=api_key, provider_name="nvidia_nim")

        default_caps = capabilities or ProviderCapabilities(
            tool_calling=True,
            streaming=True,
            vision=False,
            json_mode=True,
            system_prompt_supported=True,
        )

        super().__init__(
            name="nvidia_nim",
            model=model,
            base_url=base_url,
            auth=auth,
            timeout=timeout,
            extra_headers=extra_headers,
            capabilities=default_caps,
            client=client,
        )
