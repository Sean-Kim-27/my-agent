"""Message data model for conversational agent interactions."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from agent_framework.models.tool import ToolCall


class MessageRole(StrEnum):
    """Supported roles in the message hierarchy."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class Message(BaseModel):
    """Standardized conversation message used across all providers and agent runtime."""

    role: MessageRole | str = Field(..., description="Message role: system, user, assistant, or tool")
    content: str | None = Field(default=None, description="Textual content of the message")
    name: str | None = Field(default=None, description="Optional name identifier for tool or author")
    tool_call_id: str | None = Field(
        default=None,
        description="ID of the tool call this message is responding to (role=tool)",
    )
    tool_calls: list[ToolCall] | None = Field(
        default=None,
        description="Tool calls requested by the assistant (role=assistant)",
    )
    metadata: dict[str, Any] = Field(default_factory=dict, description="Arbitrary metadata dictionary")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC timestamp when message was created",
    )

    @classmethod
    def system(
        cls,
        content: str,
        metadata: dict[str, Any] | None = None,
        **extra_metadata: Any,
    ) -> "Message":
        """Create a system message."""
        meta = dict(metadata or {})
        meta.update(extra_metadata)
        return cls(role=MessageRole.SYSTEM, content=content, metadata=meta)

    @classmethod
    def user(
        cls,
        content: str,
        metadata: dict[str, Any] | None = None,
        **extra_metadata: Any,
    ) -> "Message":
        """Create a user message."""
        meta = dict(metadata or {})
        meta.update(extra_metadata)
        return cls(role=MessageRole.USER, content=content, metadata=meta)

    @classmethod
    def assistant(
        cls,
        content: str | None = None,
        tool_calls: list[ToolCall] | None = None,
        metadata: dict[str, Any] | None = None,
        **extra_metadata: Any,
    ) -> "Message":
        """Create an assistant message."""
        meta = dict(metadata or {})
        meta.update(extra_metadata)
        return cls(
            role=MessageRole.ASSISTANT,
            content=content,
            tool_calls=tool_calls,
            metadata=meta,
        )

    @classmethod
    def tool(
        cls,
        content: str,
        tool_call_id: str,
        name: str | None = None,
        metadata: dict[str, Any] | None = None,
        **extra_metadata: Any,
    ) -> "Message":
        """Create a tool result message."""
        meta = dict(metadata or {})
        meta.update(extra_metadata)
        return cls(
            role=MessageRole.TOOL,
            content=content,
            tool_call_id=tool_call_id,
            name=name,
            metadata=meta,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize message to dictionary."""
        return self.model_dump(exclude_none=True)
