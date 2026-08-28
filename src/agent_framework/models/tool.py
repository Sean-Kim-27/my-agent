"""Phase 0 Tool calling contracts and data models."""

from typing import Any

from pydantic import BaseModel, Field


class ToolParameterSchema(BaseModel):
    """Schema describing tool arguments."""

    type: str = "object"
    properties: dict[str, Any] = Field(default_factory=dict)
    required: list[str] = Field(default_factory=list)
    additional_properties: bool = Field(
        default=False,
        serialization_alias="additionalProperties",
    )


class ToolDefinition(BaseModel):
    """Contract describing a registered tool's signature and documentation."""

    name: str = Field(..., description="Unique tool name")
    description: str = Field(..., description="Human and LLM-readable description of the tool")
    parameters: dict[str, Any] | ToolParameterSchema = Field(
        default_factory=lambda: ToolParameterSchema().model_dump(),
        description="JSON Schema specification for tool parameters",
    )


class ToolCall(BaseModel):
    """Standardized representation of an LLM-requested tool invocation."""

    id: str = Field(..., description="Unique identifier for the tool call")
    name: str = Field(..., description="Target tool name to invoke")
    arguments: dict[str, Any] | str = Field(
        default_factory=dict,
        description="Parsed tool arguments dictionary or raw JSON string",
    )


class ToolCallResult(BaseModel):
    """Standardized representation of a tool execution outcome."""

    tool_call_id: str = Field(..., description="Corresponding ToolCall identifier")
    name: str = Field(..., description="Tool name that produced this result")
    content: str = Field(..., description="Serialized string output of the tool execution")
    is_error: bool = Field(default=False, description="Whether the tool execution failed with an error")
