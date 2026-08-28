"""Tool registry for registering and organizing callable agent tools."""

from collections.abc import Callable
from typing import Any

from agent_framework.models.tool import ToolDefinition
from agent_framework.tools.schema import generate_tool_definition


class ToolRegistry:
    """Registry maintaining registered Python functions and their schemas."""

    def __init__(self) -> None:
        self._tools: dict[str, Callable[..., Any]] = {}
        self._schemas: dict[str, ToolDefinition] = {}

    def register(
        self,
        func: Callable[..., Any],
        name: str | None = None,
        description: str | None = None,
        definition: ToolDefinition | None = None,
        requires_confirmation: bool = False,
    ) -> ToolDefinition:
        """Register a Python callable as a tool."""
        tool_def = definition or generate_tool_definition(
            func,
            name=name,
            description=description,
            requires_confirmation=requires_confirmation,
        )
        tool_name = tool_def.name

        self._tools[tool_name] = func
        self._schemas[tool_name] = tool_def
        return tool_def

    def tool(
        self,
        name: str | None = None,
        description: str | None = None,
        requires_confirmation: bool = False,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator for registering functions as tools."""

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self.register(
                func,
                name=name,
                description=description,
                requires_confirmation=requires_confirmation,
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

    def get(self, name: str) -> Callable[..., Any] | None:
        """Retrieve the callable for a tool name."""
        return self._tools.get(name)

    def get_definition(self, name: str) -> ToolDefinition | None:
        """Retrieve the ToolDefinition for a tool name."""
        return self._schemas.get(name)

    def get_definitions(self) -> list[ToolDefinition]:
        """Retrieve all registered ToolDefinitions."""
        return list(self._schemas.values())

    def list_tools(self) -> list[str]:
        """List names of all registered tools."""
        return list(self._tools.keys())

    def has_tool(self, name: str) -> bool:
        """Check if a tool is registered."""
        return name in self._tools

    def clear(self) -> None:
        """Clear all registered tools."""
        self._tools.clear()
        self._schemas.clear()
