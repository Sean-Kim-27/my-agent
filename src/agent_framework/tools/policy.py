"""Tool policy layer separating authorization from execution.

The policy engine decides — for every tool call — whether execution is
allowed and whether human confirmation is required. The executor only
performs execution mechanics (validation, timeout, serialization). This
mirrors the master plan's Phase 3 requirement that policy and execution
be decoupled and that agents cannot bypass the confirmation gate.
"""

from __future__ import annotations

from typing import Protocol

from agent_framework.exceptions import AgentFrameworkError
from agent_framework.models.tool import (
    ToolCall,
    ToolDefinition,
    ToolExecutionContext,
    ToolPolicyDecision,
    ToolRiskLevel,
)


class ToolPolicyError(AgentFrameworkError):
    """Raised when a tool policy cannot render a decision (misconfiguration)."""


class ToolPolicy(Protocol):
    """Interface for tool policy engines."""

    def evaluate(
        self,
        *,
        call: ToolCall,
        definition: ToolDefinition,
        context: ToolExecutionContext,
    ) -> ToolPolicyDecision:  # pragma: no cover - protocol
        ...


class DefaultToolPolicy:
    """Baseline policy driven by risk level and platform preset metadata.

    Rules:
      * ``SAFE`` / ``LOW`` / ``MEDIUM`` — allow without confirmation.
      * ``HIGH`` — allow only after human confirmation.
      * ``DESTRUCTIVE`` — allow only after human confirmation; caller must
        additionally treat the tool as non-idempotent (no auto retry).
      * Legacy ``requires_confirmation`` flag always forces confirmation.
      * ``platform`` metadata in the context may restrict destructive tools.
    """

    def __init__(
        self,
        *,
        deny_destructive_platforms: tuple[str, ...] = (),
    ) -> None:
        self._deny_destructive_platforms = set(deny_destructive_platforms)

    def evaluate(
        self,
        *,
        call: ToolCall,
        definition: ToolDefinition,
        context: ToolExecutionContext,
    ) -> ToolPolicyDecision:
        risk = definition.risk_level
        platform = context.platform

        if (
            risk is ToolRiskLevel.DESTRUCTIVE
            and platform is not None
            and platform in self._deny_destructive_platforms
        ):
            return ToolPolicyDecision(
                allow=False,
                require_confirmation=False,
                reason=(
                    f"Destructive tool '{definition.name}' is denied on platform '{platform}'."
                ),
            )

        require_confirmation = definition.effective_requires_confirmation
        reason = None
        if require_confirmation:
            reason = (
                f"Tool '{definition.name}' at risk level '{risk.value}' requires human confirmation."
            )
        return ToolPolicyDecision(
            allow=True,
            require_confirmation=require_confirmation,
            reason=reason,
        )


class AllowAllPolicy:
    """Escape hatch policy used only in tests or explicit trust boundaries."""

    def evaluate(
        self,
        *,
        call: ToolCall,
        definition: ToolDefinition,
        context: ToolExecutionContext,
    ) -> ToolPolicyDecision:
        return ToolPolicyDecision(allow=True, require_confirmation=False)
