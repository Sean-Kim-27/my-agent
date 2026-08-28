"""Generic OpenAI-compatible provider implementation.

Handles any endpoint following OpenAI's Chat Completions protocol (NVIDIA NIM,
vLLM, Ollama, Groq, OpenRouter, Together, LM Studio, etc.).
"""

import json
from collections.abc import AsyncIterator
from typing import Any

import openai
from openai import AsyncOpenAI

from agent_framework.auth.base import AuthenticationProvider
from agent_framework.exceptions import (
    AuthenticationError,
    InvalidRequestError,
    LLMProviderError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    RateLimitError,
)
from agent_framework.llm.base import LLMProvider
from agent_framework.models.events import StreamChunk
from agent_framework.models.message import Message, MessageRole
from agent_framework.models.response import LLMResponse, ProviderCapabilities, TokenUsage
from agent_framework.models.tool import ToolCall, ToolDefinition


class OpenAICompatibleProvider(LLMProvider):
    """Provider for OpenAI-compatible REST endpoints."""

    def __init__(
        self,
        name: str = "openai_compatible",
        model: str = "default-model",
        base_url: str = "http://localhost:8000/v1",
        auth: AuthenticationProvider | None = None,
        timeout: float = 60.0,
        extra_headers: dict[str, str] | None = None,
        capabilities: ProviderCapabilities | None = None,
        client: AsyncOpenAI | None = None,
    ) -> None:
        default_caps = capabilities or ProviderCapabilities(
            tool_calling=True,
            streaming=True,
            vision=False,
            json_mode=True,
        )
        super().__init__(name=name, model=model, capabilities=default_caps)
        self.base_url = base_url.rstrip("/")
        self.auth = auth
        self.timeout = timeout
        self.extra_headers = extra_headers or {}
        self._client = client

    async def _get_client(self) -> AsyncOpenAI:
        """Lazily initialize or return the AsyncOpenAI client with active credentials."""
        if self._client is not None:
            return self._client

        api_key = "none"
        headers = dict(self.extra_headers)

        if self.auth is not None:
            creds = await self.auth.get_credentials()
            if creds.api_key:
                api_key = creds.api_key
            elif creds.token:
                api_key = creds.token
            headers.update(creds.headers)

        return AsyncOpenAI(
            api_key=api_key,
            base_url=self.base_url,
            timeout=self.timeout,
            default_headers=headers,
        )

    def _convert_messages(self, messages: list[Message]) -> list[dict[str, Any]]:
        """Convert standard Message objects to OpenAI message dicts."""
        openai_messages: list[dict[str, Any]] = []

        for msg in messages:
            role_str = msg.role.value if isinstance(msg.role, MessageRole) else str(msg.role)
            item: dict[str, Any] = {
                "role": role_str,
                "content": msg.content or "",
            }

            if msg.name:
                item["name"] = msg.name

            if role_str == "tool" and msg.tool_call_id:
                item["tool_call_id"] = msg.tool_call_id

            if role_str == "assistant" and msg.tool_calls:
                item["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": (
                                json.dumps(tc.arguments)
                                if isinstance(tc.arguments, dict)
                                else str(tc.arguments)
                            ),
                        },
                    }
                    for tc in msg.tool_calls
                ]

            openai_messages.append(item)

        return openai_messages

    def _convert_tools(
        self, tools: list[ToolDefinition] | None
    ) -> list[dict[str, Any]] | None:
        """Convert ToolDefinitions into OpenAI function tool schema format."""
        if not tools:
            return None
        formatted_tools: list[dict[str, Any]] = []
        for t in tools:
            param_dict = (
                t.parameters.model_dump(by_alias=True, exclude_none=True)
                if hasattr(t.parameters, "model_dump")
                else t.parameters
            )
            formatted_tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": param_dict,
                    },
                }
            )
        return formatted_tools

    async def _generate_internal(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Call the OpenAI-compatible chat completion endpoint."""
        client = await self._get_client()
        formatted_messages = self._convert_messages(messages)
        model = kwargs.pop("model", self.model)
        formatted_tools = self._convert_tools(tools)

        call_kwargs: dict[str, Any] = {
            "model": model,
            "messages": formatted_messages,
            "timeout": self.timeout,
            **kwargs,
        }
        if formatted_tools:
            call_kwargs["tools"] = formatted_tools

        try:
            raw_response = await client.chat.completions.create(**call_kwargs)
        except openai.AuthenticationError as exc:
            raise AuthenticationError(
                message=f"Authentication failed for {self.name}: {exc.message}",
                auth_type=self.auth.auth_type if self.auth else "unknown",
                details={"provider": self.name, "raw_error": str(exc)},
            ) from exc
        except openai.RateLimitError as exc:
            raise RateLimitError(
                message=f"Rate limit exceeded on {self.name}: {exc.message}",
                provider=self.name,
                model=model,
                status_code=exc.status_code,
                details={"raw_error": str(exc)},
            ) from exc
        except openai.APITimeoutError as exc:
            raise ProviderTimeoutError(
                message=f"Request timed out for {self.name} after {self.timeout}s: {exc.message}",
                provider=self.name,
                model=model,
                details={"raw_error": str(exc)},
            ) from exc
        except openai.APIConnectionError as exc:
            raise ProviderUnavailableError(
                message=f"Failed to connect to {self.name} at {self.base_url}: {exc.message}",
                provider=self.name,
                model=model,
                details={"raw_error": str(exc)},
            ) from exc
        except openai.BadRequestError as exc:
            raise InvalidRequestError(
                message=f"Invalid request to {self.name}: {exc.message}",
                provider=self.name,
                model=model,
                status_code=exc.status_code,
                details={"raw_error": str(exc)},
            ) from exc
        except openai.APIStatusError as exc:
            raise LLMProviderError(
                message=f"{self.name} returned error status {exc.status_code}: {exc.message}",
                provider=self.name,
                model=model,
                status_code=exc.status_code,
                details={"raw_error": str(exc)},
            ) from exc
        except Exception as exc:
            raise LLMProviderError(
                message=f"Unexpected error in {self.name}: {exc}",
                provider=self.name,
                model=model,
                details={"raw_error": str(exc)},
            ) from exc

        # Extract choice content and tool calls
        choice = raw_response.choices[0]
        choice_msg = choice.message
        content = choice_msg.content

        tool_calls: list[ToolCall] = []
        if getattr(choice_msg, "tool_calls", None):
            for tc in choice_msg.tool_calls:
                fn = getattr(tc, "function", None)
                if fn is None:
                    continue
                raw_args = getattr(fn, "arguments", "{}")
                name = getattr(fn, "name", "unknown")
                arguments: dict[str, Any] | str = raw_args
                if isinstance(raw_args, str):
                    try:
                        arguments = json.loads(raw_args)
                    except Exception:
                        pass
                tool_calls.append(
                    ToolCall(
                        id=tc.id,
                        name=name,
                        arguments=arguments,
                    )
                )

        usage: TokenUsage | None = None
        if raw_response.usage:
            usage = TokenUsage(
                prompt_tokens=raw_response.usage.prompt_tokens,
                completion_tokens=raw_response.usage.completion_tokens,
                total_tokens=raw_response.usage.total_tokens,
            )

        return LLMResponse(
            content=content,
            role=MessageRole.ASSISTANT,
            tool_calls=tool_calls,
            usage=usage,
            model=raw_response.model or model,
            provider=self.name,
            finish_reason=choice.finish_reason,
        )

    async def generate_stream(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        """Stream tokens using OpenAI streaming completion protocol."""
        client = await self._get_client()
        formatted_messages = self._convert_messages(messages)
        model = kwargs.pop("model", self.model)
        formatted_tools = self._convert_tools(tools)

        call_kwargs: dict[str, Any] = {
            "model": model,
            "messages": formatted_messages,
            "timeout": self.timeout,
            "stream": True,
            **kwargs,
        }
        if formatted_tools:
            call_kwargs["tools"] = formatted_tools

        try:
            stream = await client.chat.completions.create(**call_kwargs)
            async for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                delta_content = getattr(delta, "content", None) or ""
                if delta_content:
                    yield StreamChunk(content=delta_content, is_finished=False)
            yield StreamChunk(content="", is_finished=True)
        except Exception:
            # Fallback to base generate_stream if streaming endpoint fails
            async for chunk in super().generate_stream(messages, tools=tools, **kwargs):
                yield chunk

    async def health_check(self) -> bool:
        """Perform a lightweight health check by querying the models endpoint."""
        try:
            client = await self._get_client()
            await client.models.list(timeout=min(self.timeout, 5.0))
            return True
        except Exception:
            return False
