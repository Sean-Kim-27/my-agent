"""Anthropic LLM Provider implementation."""

from typing import Any

import anthropic
from anthropic import AsyncAnthropic
from anthropic import Timeout as AnthropicTimeout

from agent_framework.auth.api_key import ApiKeyAuth
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
from agent_framework.models.message import Message, MessageRole
from agent_framework.models.response import (
    LLMResponse,
    ProviderCapabilities,
    ProviderTimeouts,
    TokenUsage,
)
from agent_framework.models.tool import ToolCall, ToolDefinition

_ANTHROPIC_CONTEXT_WINDOWS: dict[str, int] = {
    "claude-3-5-sonnet": 200_000,
    "claude-3-5-haiku": 200_000,
    "claude-3-opus": 200_000,
    "claude-3-sonnet": 200_000,
    "claude-3-haiku": 200_000,
    "claude-2.1": 200_000,
    "claude-2": 100_000,
}


def _lookup_anthropic_window(model: str) -> int | None:
    for prefix, window in _ANTHROPIC_CONTEXT_WINDOWS.items():
        if model.startswith(prefix):
            return window
    return None


class AnthropicProvider(LLMProvider):
    """LLM Provider for Anthropic Claude models."""

    DEFAULT_MODEL = "claude-3-5-sonnet-20241022"

    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        auth: AuthenticationProvider | None = None,
        timeout: float | ProviderTimeouts = 60.0,
        extra_headers: dict[str, str] | None = None,
        capabilities: ProviderCapabilities | None = None,
        client: AsyncAnthropic | None = None,
    ) -> None:
        if auth is None and api_key is not None:
            auth = ApiKeyAuth(
                api_key=api_key,
                header_name="x-api-key",
                header_prefix="",
                provider_name="anthropic",
            )

        default_caps = capabilities or ProviderCapabilities(
            tool_calling=True,
            streaming=True,
            vision=True,
            json_mode=True,
            system_prompt_supported=True,
            context_window=_lookup_anthropic_window(model),
        )

        super().__init__(name="anthropic", model=model, capabilities=default_caps)
        self.auth = auth
        self.timeouts = timeout if isinstance(timeout, ProviderTimeouts) else ProviderTimeouts.from_scalar(timeout)
        self.timeout = self.timeouts.read
        self.http_timeout = AnthropicTimeout(
            connect=self.timeouts.connect,
            read=self.timeouts.read,
            write=self.timeouts.write,
            pool=self.timeouts.pool,
        )
        self.extra_headers = extra_headers or {}
        self._client = client

    async def _get_client(self) -> AsyncAnthropic:
        """Lazily initialize or return the AsyncAnthropic client."""
        if self._client is not None:
            return self._client

        api_key = "none"
        if self.auth is not None:
            creds = await self.auth.get_credentials()
            api_key = creds.api_key or creds.token or "none"

        return AsyncAnthropic(
            api_key=api_key,
            timeout=self.http_timeout,
            default_headers=self.extra_headers,
            max_retries=0,
        )

    def _convert_messages(
        self, messages: list[Message]
    ) -> tuple[str | None, list[dict[str, Any]]]:
        """Separate top-level system prompt from user/assistant/tool messages for Anthropic."""
        system_prompts: list[str] = []
        anthropic_messages: list[dict[str, Any]] = []

        for msg in messages:
            role_str = msg.role.value if isinstance(msg.role, MessageRole) else str(msg.role)

            if role_str == "system":
                if msg.content:
                    system_prompts.append(msg.content)
            elif role_str == "tool":
                # Convert tool result to Anthropic tool_result block inside a user message
                anthropic_messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": msg.tool_call_id or "unknown",
                                "content": msg.content or "",
                            }
                        ],
                    }
                )
            elif role_str == "assistant":
                if msg.tool_calls:
                    content_blocks: list[dict[str, Any]] = []
                    if msg.content:
                        content_blocks.append({"type": "text", "text": msg.content})
                    for tc in msg.tool_calls:
                        args = tc.arguments if isinstance(tc.arguments, dict) else {}
                        content_blocks.append(
                            {
                                "type": "tool_use",
                                "id": tc.id,
                                "name": tc.name,
                                "input": args,
                            }
                        )
                    anthropic_messages.append({"role": "assistant", "content": content_blocks})
                else:
                    anthropic_messages.append(
                        {
                            "role": "assistant",
                            "content": msg.content or "",
                        }
                    )
            else:
                # Standard user message
                anthropic_messages.append(
                    {
                        "role": "user",
                        "content": msg.content or "",
                    }
                )

        system_prompt = "\n\n".join(system_prompts) if system_prompts else None
        return system_prompt, anthropic_messages

    def _convert_tools(
        self, tools: list[ToolDefinition] | None
    ) -> list[dict[str, Any]] | None:
        """Convert ToolDefinitions into Anthropic tool schema format."""
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
                    "name": t.name,
                    "description": t.description,
                    "input_schema": param_dict,
                }
            )
        return formatted_tools

    def _parse_tool_calls(self, raw: Any) -> list[ToolCall]:
        """Normalize an Anthropic Messages response into ``ToolCall`` list."""
        tool_calls: list[ToolCall] = []
        content = getattr(raw, "content", None) or []
        for block in content:
            if getattr(block, "type", None) != "tool_use":
                continue
            arguments = getattr(block, "input", {})
            if not isinstance(arguments, dict):
                arguments = {}
            tool_calls.append(
                ToolCall(
                    id=str(getattr(block, "id", "")),
                    name=str(getattr(block, "name", "")),
                    arguments=arguments,
                )
            )
        return tool_calls

    async def _generate_internal(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Call Anthropic Messages API."""
        client = await self._get_client()
        system_prompt, formatted_messages = self._convert_messages(messages)
        model = kwargs.pop("model", self.model)
        max_tokens = kwargs.pop("max_tokens", 4096)
        formatted_tools = self._convert_tools(tools)

        call_kwargs: dict[str, Any] = {
            "model": model,
            "messages": formatted_messages,
            "max_tokens": max_tokens,
            **kwargs,
        }
        if system_prompt:
            call_kwargs["system"] = system_prompt
        if formatted_tools:
            call_kwargs["tools"] = formatted_tools

        try:
            raw_response = await client.messages.create(**call_kwargs)
        except anthropic.AuthenticationError as exc:
            raise AuthenticationError(
                message=f"Authentication failed for Anthropic: {exc.message}",
                auth_type=self.auth.auth_type if self.auth else "unknown",
                details={"provider": "anthropic", "raw_error": str(exc)},
            ) from exc
        except anthropic.RateLimitError as exc:
            raise RateLimitError(
                message=f"Rate limit exceeded on Anthropic: {exc.message}",
                provider="anthropic",
                model=model,
                status_code=exc.status_code,
                details={"raw_error": str(exc)},
            ) from exc
        except anthropic.APITimeoutError as exc:
            raise ProviderTimeoutError(
                message=f"Request timed out for Anthropic after {self.timeout}s: {exc.message}",
                provider="anthropic",
                model=model,
                details={"raw_error": str(exc)},
            ) from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderUnavailableError(
                message=f"Failed to connect to Anthropic: {exc.message}",
                provider="anthropic",
                model=model,
                details={"raw_error": str(exc)},
            ) from exc
        except anthropic.BadRequestError as exc:
            raise InvalidRequestError(
                message=f"Invalid request to Anthropic: {exc.message}",
                provider="anthropic",
                model=model,
                status_code=exc.status_code,
                details={"raw_error": str(exc)},
            ) from exc
        except anthropic.APIStatusError as exc:
            raise LLMProviderError(
                message=f"Anthropic returned error status {exc.status_code}: {exc.message}",
                provider="anthropic",
                model=model,
                status_code=exc.status_code,
                details={"raw_error": str(exc)},
            ) from exc
        except Exception as exc:
            raise LLMProviderError(
                message=f"Unexpected error in Anthropic provider: {exc}",
                provider="anthropic",
                model=model,
                details={"raw_error": str(exc)},
            ) from exc

        # Parse text and tool_use blocks
        text_parts: list[str] = []
        for block in raw_response.content:
            block_type = getattr(block, "type", None)
            if block_type == "text":
                text_val = getattr(block, "text", "")
                if isinstance(text_val, str):
                    text_parts.append(text_val)
            elif block_type != "tool_use" and isinstance(getattr(block, "text", None), str):
                text_parts.append(block.text)

        tool_calls = self._parse_tool_calls(raw_response)

        combined_text = "".join(text_parts) if text_parts else None

        usage: TokenUsage | None = None
        if raw_response.usage:
            usage = TokenUsage(
                prompt_tokens=raw_response.usage.input_tokens,
                completion_tokens=raw_response.usage.output_tokens,
                total_tokens=raw_response.usage.input_tokens + raw_response.usage.output_tokens,
            )

        return LLMResponse(
            content=combined_text,
            role=MessageRole.ASSISTANT,
            tool_calls=tool_calls,
            usage=usage,
            model=raw_response.model or model,
            provider="anthropic",
            finish_reason=raw_response.stop_reason,
        )

    async def health_check(self) -> bool:
        """Check connection to Anthropic."""
        try:
            client = await self._get_client()
            health_timeouts = self.timeouts.capped(5.0)
            # Send a minimal 1-token test
            await client.messages.create(
                model=self.model,
                max_tokens=1,
                messages=[{"role": "user", "content": "ping"}],
                timeout=AnthropicTimeout(
                    connect=health_timeouts.connect,
                    read=health_timeouts.read,
                    write=health_timeouts.write,
                    pool=health_timeouts.pool,
                ),
            )
            return True
        except Exception:
            return False
