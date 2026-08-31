"""Tool registry for registering and organizing callable agent tools."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from agent_framework.exceptions import AgentFrameworkError
from agent_framework.models.tool import ToolDefinition, ToolRiskLevel
from agent_framework.tools.schema import generate_tool_definition


class ToolRegistryError(AgentFrameworkError):
    """Raised for tool registration policy violations (e.g. duplicate names)."""


class ToolRegistry:
    """Registry maintaining registered Python functions, their schemas, and toolset gates."""

    def __init__(self) -> None:
        self._tools: dict[str, Callable[..., Any]] = {}
        self._schemas: dict[str, ToolDefinition] = {}
        self._toolset_disabled: set[str] = set()
        self._toolset_allowlist: set[str] | None = None

    # ------------------------------------------------------------------ API

    def register(
        self,
        func: Callable[..., Any],
        name: str | None = None,
        description: str | None = None,
        definition: ToolDefinition | None = None,
        requires_confirmation: bool = False,
        *,
        risk_level: ToolRiskLevel | None = None,
        toolset: str = "default",
        idempotent: bool = True,
        max_output_bytes: int | None = None,
        max_concurrency: int | None = None,
        replace: bool = False,
    ) -> ToolDefinition:
        """Register a Python callable as a tool.

        Duplicate names are rejected by default (fail-closed). Pass ``replace=True``
        to overwrite an existing registration explicitly.
        """
        tool_def = definition or generate_tool_definition(
            func,
            name=name,
            description=description,
            requires_confirmation=requires_confirmation,
            risk_level=risk_level,
            toolset=toolset,
            idempotent=idempotent,
            max_output_bytes=max_output_bytes,
            max_concurrency=max_concurrency,
        )
        tool_name = tool_def.name

        if tool_name in self._tools and not replace:
            raise ToolRegistryError(
                f"Tool '{tool_name}' is already registered. Pass replace=True to overwrite."
            )

        self._tools[tool_name] = func
        self._schemas[tool_name] = tool_def
        return tool_def

    def tool(
        self,
        name: str | None = None,
        description: str | None = None,
        requires_confirmation: bool = False,
        *,
        risk_level: ToolRiskLevel | None = None,
        toolset: str = "default",
        idempotent: bool = True,
        max_output_bytes: int | None = None,
        max_concurrency: int | None = None,
        replace: bool = False,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator for registering functions as tools."""

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self.register(
                func,
                name=name,
                description=description,
                requires_confirmation=requires_confirmation,
                risk_level=risk_level,
                toolset=toolset,
                idempotent=idempotent,
                max_output_bytes=max_output_bytes,
                max_concurrency=max_concurrency,
                replace=replace,
            )
            return func

        return decorator

    def unregister(self, name: str) -> bool:
        """Remove a tool by name."""
        if name in self._tools:
            del self._tools[name]
            self._schemas.pop(name, None)
            return True
        return False

    # ------------------------------------------------------------ Lookups

    def _is_enabled(self, definition: ToolDefinition) -> bool:
        if definition.toolset in self._toolset_disabled:
            return False
        if self._toolset_allowlist is not None and definition.toolset not in self._toolset_allowlist:
            return False
        return True

    def get(self, name: str) -> Callable[..., Any] | None:
        """Retrieve the callable for a tool name, respecting toolset gating."""
        func = self._tools.get(name)
        if func is None:
            return None
        definition = self._schemas.get(name)
        if definition is not None and not self._is_enabled(definition):
            return None
        return func

    def get_definition(self, name: str) -> ToolDefinition | None:
        """Retrieve the ToolDefinition for a tool name (None if hidden by toolset gating)."""
        definition = self._schemas.get(name)
        if definition is None:
            return None
        if not self._is_enabled(definition):
            return None
        return definition

    def get_definitions(self) -> list[ToolDefinition]:
        """Retrieve all registered ToolDefinitions that are currently enabled."""
        return [d for d in self._schemas.values() if self._is_enabled(d)]

    def list_tools(self) -> list[str]:
        """List names of currently enabled tools."""
        return [name for name, d in self._schemas.items() if self._is_enabled(d)]

    def has_tool(self, name: str) -> bool:
        """Check if a tool is registered and currently enabled."""
        definition = self._schemas.get(name)
        return definition is not None and self._is_enabled(definition)

    def clear(self) -> None:
        """Clear all registered tools and gating state."""
        self._tools.clear()
        self._schemas.clear()
        self._toolset_disabled.clear()
        self._toolset_allowlist = None

    # ------------------------------------------------------------ Toolsets

    def disable_toolset(self, name: str) -> None:
        """Disable a toolset. All tools in the toolset become invisible to consumers."""
        self._toolset_disabled.add(name)

    def enable_toolset(self, name: str) -> None:
        """Undo a previous ``disable_toolset`` call."""
        self._toolset_disabled.discard(name)

    def apply_preset(self, *, allow_toolsets: Iterable[str]) -> None:
        """Restrict visible tools to the given toolset allowlist. Pass an empty iterable to reset."""
        toolsets = set(allow_toolsets)
        self._toolset_allowlist = toolsets or None

    def reset_preset(self) -> None:
        """Remove any active toolset allowlist."""
        self._toolset_allowlist = None

    def toolset_of(self, name: str) -> str | None:
        """Return the toolset name of a registered tool, ignoring enablement."""
        definition = self._schemas.get(name)
        return definition.toolset if definition else None
