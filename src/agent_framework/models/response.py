"""LLM response and capability data models."""

from typing import Any

from pydantic import BaseModel, Field

from agent_framework.models.message import Message, MessageRole
from agent_framework.models.tool import ToolCall


class TokenUsage(BaseModel):
    """Token consumption statistics for an LLM generation."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ProviderCapabilities(BaseModel):
    """Capability descriptor for an LLM provider."""

    tool_calling: bool = False
    streaming: bool = False
    vision: bool = False
    json_mode: bool = True
    system_prompt_supported: bool = True


class LLMResponse(BaseModel):
    """Standardized response from any LLM provider."""

    content: str | None = Field(default=None, description="Generated assistant text response")
    role: MessageRole | str = Field(default=MessageRole.ASSISTANT, description="Response role")
    tool_calls: list[ToolCall] = Field(
        default_factory=list,
        description="Tool invocations requested by the model",
    )
    usage: TokenUsage | None = Field(default=None, description="Token usage statistics")
    model: str = Field(default="unknown", description="Model name that generated the response")
    provider: str = Field(default="unknown", description="Provider identifier (e.g. openai, anthropic)")
    latency_ms: float = Field(default=0.0, description="End-to-end API response latency in milliseconds")
    finish_reason: str | None = Field(default=None, description="Reason for generation stop")
    raw_response: dict[str, Any] | None = Field(
        default=None,
        description="Optional raw payload from provider for debugging",
    )

    @property
    def has_tool_calls(self) -> bool:
        """Return True if model requested one or more tool calls."""
        return len(self.tool_calls) > 0

    def to_message(self) -> Message:
        """Convert LLMResponse to an assistant Message."""
        return Message.assistant(
            content=self.content,
            tool_calls=self.tool_calls if self.has_tool_calls else None,
            metadata={
                "provider": self.provider,
                "model": self.model,
                "latency_ms": self.latency_ms,
                "finish_reason": self.finish_reason,
            },
        )
