"""Configuration models for MCP server integration."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from agent_framework.models.tool import ToolRiskLevel


class MCPServerConfig(BaseModel):
    """Declarative configuration for a single MCP server.

    ``stdio`` transports spawn a subprocess whose environment is filtered
    through ``env_allowlist``. ``http`` transports POST JSON-RPC to ``url``.
    Timeouts are separated per lifecycle phase so a stuck ``call`` cannot
    consume the ``connect`` budget and vice versa.
    """

    name: str = Field(..., min_length=1, description="Unique MCP server identifier.")
    transport: Literal["stdio", "http"] = Field(...)
    enabled: bool = Field(default=True)

    # stdio transport
    command: list[str] | None = Field(
        default=None,
        description="argv for stdio transports (first entry is the executable).",
    )
    env_allowlist: list[str] = Field(
        default_factory=list,
        description="Host env variables forwarded to stdio subprocesses.",
    )
    extra_env: dict[str, str] = Field(
        default_factory=dict,
        description="Explicit env variables merged into the subprocess env.",
    )
    extra_env_secret_refs: dict[str, str] = Field(
        default_factory=dict,
        description="Environment variable names mapped to secret-store references.",
    )

    # http transport
    url: str | None = Field(
        default=None,
        description="Streamable HTTP endpoint for the MCP JSON-RPC server.",
    )
    headers: dict[str, str] = Field(
        default_factory=dict,
        description="HTTP headers sent with every MCP request.",
    )
    header_secret_refs: dict[str, str] = Field(
        default_factory=dict,
        description="HTTP header names mapped to secret-store references.",
    )

    # Namespacing and filtering
    namespace: str | None = Field(
        default=None,
        description="Tool namespace prefix. Defaults to 'mcp.<name>'.",
    )
    allow_tools: list[str] | None = Field(
        default=None,
        description="If set, only tool names in this list are registered.",
    )
    deny_tools: list[str] = Field(
        default_factory=list,
        description="Tool names that are never registered, even if allowlisted.",
    )

    # Timeouts (seconds)
    connect_timeout: float = Field(default=10.0, gt=0)
    init_timeout: float = Field(default=15.0, gt=0)
    call_timeout: float = Field(default=60.0, gt=0)

    # Policy defaults applied to every tool discovered from this server
    default_risk_level: ToolRiskLevel = Field(
        default=ToolRiskLevel.MEDIUM,
        description="Risk level assigned to every discovered tool.",
    )
    default_idempotent: bool = Field(
        default=False,
        description="Whether MCP tools are considered idempotent (retries safe).",
    )

    @model_validator(mode="after")
    def _validate_transport_fields(self) -> MCPServerConfig:
        if self.transport == "stdio":
            if not self.command:
                raise ValueError("stdio transport requires 'command'")
        elif self.transport == "http":
            if not self.url:
                raise ValueError("http transport requires 'url'")
        return self

    @property
    def effective_namespace(self) -> str:
        return self.namespace or f"mcp.{self.name}"

    def is_tool_allowed(self, tool_name: str) -> bool:
        if tool_name in self.deny_tools:
            return False
        if self.allow_tools is not None and tool_name not in self.allow_tools:
            return False
        return True
