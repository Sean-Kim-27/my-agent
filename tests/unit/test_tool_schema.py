"""Unit tests for tool schema generation from Python functions."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from agent_framework.models.tool import ToolParameterSchema
from agent_framework.tools.schema import generate_tool_definition, python_type_to_json_schema


class CityEnum(StrEnum):
    SEOUL = "Seoul"
    TOKYO = "Tokyo"
    PARIS = "Paris"


class UserProfile(BaseModel):
    name: str = Field(..., description="User full name")
    age: int = Field(..., description="User age in years")
    email: str | None = Field(default=None, description="Email address")


def sample_function(
    city: str,
    count: int = 10,
    unit: Literal["celsius", "fahrenheit"] = "celsius",
    target_city: CityEnum | None = None,
) -> str:
    """Fetch weather data for a location.

    Args:
        city: The name of the target city.
        count: Number of forecast days.
        unit: Temperature unit of measurement.
        target_city: Pre-defined city enumeration.
    """
    return f"Weather for {city} in {unit}"


def test_python_type_to_json_schema_primitives() -> None:
    """Test primitive type to JSON schema mappings."""
    assert python_type_to_json_schema(str) == {"type": "string"}
    assert python_type_to_json_schema(int) == {"type": "integer"}
    assert python_type_to_json_schema(float) == {"type": "number"}
    assert python_type_to_json_schema(bool) == {"type": "boolean"}
    assert python_type_to_json_schema(list[str]) == {"type": "array", "items": {"type": "string"}}
    assert python_type_to_json_schema(dict) == {"type": "object"}


def test_python_type_to_json_schema_complex() -> None:
    """Test Enum, Literal, Optional, and Pydantic schema generation."""
    # Literal
    lit_schema = python_type_to_json_schema(Literal["a", "b", "c"])
    assert lit_schema == {"type": "string", "enum": ["a", "b", "c"]}

    # Enum
    enum_schema = python_type_to_json_schema(CityEnum)
    assert enum_schema == {"type": "string", "enum": ["Seoul", "Tokyo", "Paris"]}

    # Optional / Union
    opt_schema = python_type_to_json_schema(int | None)
    assert opt_schema == {"type": "integer"}

    # Pydantic Model
    pydantic_schema = python_type_to_json_schema(UserProfile)
    assert pydantic_schema["type"] == "object"
    assert "name" in pydantic_schema["properties"]
    assert "age" in pydantic_schema["properties"]


def test_generate_tool_definition() -> None:
    """Test comprehensive ToolDefinition generation from a typed function with docstring."""
    tool_def = generate_tool_definition(sample_function)

    assert tool_def.name == "sample_function"
    assert "Fetch weather data" in tool_def.description

    params = tool_def.parameters
    assert isinstance(params, ToolParameterSchema)
    props = params.properties if isinstance(params.properties, dict) else {}

    # Check city parameter
    assert "city" in props
    assert props["city"]["type"] == "string"
    assert "target city" in props["city"]["description"].lower()

    # Check count parameter
    assert "count" in props
    assert props["count"]["type"] == "integer"
    assert props["count"]["default"] == 10

    # Check unit parameter
    assert "unit" in props
    assert props["unit"]["type"] == "string"
    assert props["unit"]["enum"] == ["celsius", "fahrenheit"]

    # Check required list: city has no default so it must be required, count has default
    assert "city" in params.required
    assert "count" not in params.required
    assert "unit" not in params.required
