"""Tool calling contracts and data models (extended in Phase 3 for risk/toolset/policy)."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class ToolRiskLevel(StrEnum):
    """Risk classification driving policy decisions.

    ``SAFE`` tools have no side effects and can always execute.
    ``LOW``/``MEDIUM`` are auto-approved unless a policy overrides.
    ``HIGH`` requires human confirmation before execution.
    ``DESTRUCTIVE`` requires human confirmation and cannot be auto-retried.
    """

    SAFE = "safe"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    DESTRUCTIVE = "destructive"


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
    """Contract describing a registered tool's signature, docs, and policy metadata."""

    name: str = Field(..., description="Unique tool name (may be namespaced, e.g. builtin.file.read)")
    description: str = Field(..., description="Human and LLM-readable description of the tool")
    parameters: dict[str, Any] | ToolParameterSchema = Field(
        default_factory=lambda: ToolParameterSchema().model_dump(),
        description="JSON Schema specification for tool parameters",
    )
    requires_confirmation: bool = Field(
        default=False,
        description="Legacy flag: force human confirmation regardless of risk level.",
    )

    # Phase 3 metadata --------------------------------------------------------
    risk_level: ToolRiskLevel = Field(
        default=ToolRiskLevel.SAFE,
        description="Risk level used by the policy engine to authorize execution.",
    )
    toolset: str = Field(
        default="default",
        description="Logical group used for enabling/disabling collections of tools.",
    )
    idempotent: bool = Field(
        default=True,
        description="Whether re-invoking with the same arguments is safe. False disables auto-retry.",
    )
    max_output_bytes: int | None = Field(
        default=None,
        description="Maximum serialized output size in bytes. Larger outputs are truncated and split into artifacts.",
    )
    max_concurrency: int | None = Field(
        default=None,
        description="Maximum concurrent executions of this tool. None means unlimited.",
    )

    @property
    def namespace(self) -> str:
        """Namespace prefix of the tool name (portion before the final ``.``)."""
        if "." in self.name:
            return self.name.rsplit(".", 1)[0]
        return ""

    @property
    def effective_requires_confirmation(self) -> bool:
        """True when policy or legacy flag mandates human confirmation."""
        return self.requires_confirmation or self.risk_level in (
            ToolRiskLevel.HIGH,
            ToolRiskLevel.DESTRUCTIVE,
        )


class ToolCall(BaseModel):
    """Standardized representation of an LLM-requested tool invocation."""

    id: str = Field(..., description="Unique identifier for the tool call")
    name: str = Field(..., description="Target tool name to invoke")
    arguments: dict[str, Any] | str = Field(
        default_factory=dict,
        description="Parsed tool arguments dictionary or raw JSON string",
    )


class ToolArtifact(BaseModel):
    """Reference to a large tool output that has been split from the summary content."""

    tool_call_id: str = Field(..., description="Owning ToolCall identifier")
    content_type: str = Field(default="text/plain", description="Artifact MIME type")
    total_bytes: int = Field(..., ge=0, description="Total size of the original output in bytes")
    truncated: bool = Field(default=True, description="Whether the summary was truncated")
    payload: str = Field(..., description="Full output payload separated from the summary")


class ToolCallResult(BaseModel):
    """Standardized representation of a tool execution outcome."""

    tool_call_id: str = Field(..., description="Corresponding ToolCall identifier")
    name: str = Field(..., description="Tool name that produced this result")
    content: str = Field(..., description="Serialized string output of the tool execution")
    is_error: bool = Field(default=False, description="Whether the tool execution failed with an error")
    artifact: ToolArtifact | None = Field(
        default=None,
        description="Overflow payload when the summary content was truncated for size.",
    )


class ToolExecutionContext(BaseModel):
    """Execution-scoped context passed to policy engine and executor.

    Carries identifiers the policy layer needs to make decisions without
    coupling the tool executor to the Agent runtime.
    """

    run_id: str = Field(..., description="Agent run identifier")
    step: int = Field(default=0, ge=0, description="Zero-based step within the current run")
    session_id: str | None = Field(default=None, description="Session identifier when available")
    actor: str | None = Field(default=None, description="Requesting actor (user id, service, etc.)")
    platform: str | None = Field(default=None, description="Platform preset context (e.g. cli, discord)")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Free-form policy metadata")


class ToolPolicyDecision(BaseModel):
    """Outcome of a policy evaluation performed before executing a tool."""

    allow: bool = Field(..., description="Whether execution may proceed at all")
    require_confirmation: bool = Field(
        default=False,
        description="Whether a human approval callback must succeed before execution.",
    )
    reason: str | None = Field(
        default=None,
        description="Human-readable reason surfaced when the decision denies or requires confirmation.",
    )

    @model_validator(mode="after")
    def _validate_confirmation_implies_allow(self) -> ToolPolicyDecision:
        if self.require_confirmation and not self.allow:
            raise ValueError("require_confirmation cannot be True when allow is False")
        return self
