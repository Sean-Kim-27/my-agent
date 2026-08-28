"""Unit tests for ToolRegistry."""

from agent_framework.tools.registry import ToolRegistry


def add_numbers(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


async def async_greet(name: str) -> str:
    """Greet someone asynchronously."""
    return f"Hello, {name}!"


def test_tool_registry_registration() -> None:
    """Test manual and decorator registration in ToolRegistry."""
    registry = ToolRegistry()
    assert len(registry.list_tools()) == 0

    # Direct registration
    tool_def1 = registry.register(add_numbers, description="Add two ints")
    assert tool_def1.name == "add_numbers"
    assert registry.has_tool("add_numbers") is True
    assert registry.get("add_numbers") is add_numbers

    # Decorator registration
    @registry.tool(name="greet_tool", description="Custom greeting tool")
    async def greet(name: str) -> str:
        return f"Greetings {name}"

    assert registry.has_tool("greet_tool") is True
    assert len(registry.list_tools()) == 2
    assert set(registry.list_tools()) == {"add_numbers", "greet_tool"}

    # Get definitions
    defs = registry.get_definitions()
    assert len(defs) == 2
    assert any(d.name == "greet_tool" for d in defs)


def test_tool_registry_unregistration_and_clear() -> None:
    """Test unregister and clear methods."""
    registry = ToolRegistry()
    registry.register(add_numbers)
    registry.register(async_greet)

    assert registry.has_tool("add_numbers") is True
    assert registry.unregister("add_numbers") is True
    assert registry.has_tool("add_numbers") is False
    assert registry.unregister("non_existent") is False

    registry.clear()
    assert len(registry.list_tools()) == 0
    assert len(registry.get_definitions()) == 0
