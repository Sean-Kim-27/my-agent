"""Automated JSON Schema generation and argument validation for Python tools."""

from __future__ import annotations

import inspect
import types
from collections.abc import Callable
from enum import Enum
from typing import Any, Literal, Union, get_args, get_origin

from pydantic import BaseModel

from agent_framework.models.tool import (
    ToolDefinition,
    ToolParameterSchema,
    ToolRiskLevel,
)


def _parse_docstring_param_descriptions(docstring: str | None) -> tuple[str, dict[str, str]]:
    """Extract tool description and parameter descriptions from docstrings."""
    if not docstring:
        return "No description provided.", {}

    lines = [line.strip() for line in docstring.strip().splitlines()]
    main_desc_lines: list[str] = []
    param_docs: dict[str, str] = {}

    current_param: str | None = None
    in_args_section = False

    for line in lines:
        if not line:
            continue
        lower_line = line.lower()
        if lower_line in ("args:", "parameters:", "params:", "arguments:"):
            in_args_section = True
            current_param = None
            continue
        if lower_line in ("returns:", "raises:", "yields:", "example:", "examples:"):
            in_args_section = False
            current_param = None
            continue

        if in_args_section:
            if ":" in line:
                parts = line.split(":", 1)
                pname = parts[0].strip().split()[0].strip("*")
                pdesc = parts[1].strip()
                param_docs[pname] = pdesc
                current_param = pname
            elif current_param:
                param_docs[current_param] += f" {line.strip()}"
        else:
            main_desc_lines.append(line)

    main_description = " ".join(main_desc_lines).strip() or "No description provided."
    return main_description, param_docs


def python_type_to_json_schema(py_type: Any) -> dict[str, Any]:
    """Convert a Python type or typing annotation to a standard JSON Schema dictionary."""
    if py_type is inspect.Parameter.empty or py_type is Any:
        return {"type": "string"}

    if isinstance(py_type, type) and issubclass(py_type, BaseModel):
        schema = py_type.model_json_schema()
        return {
            "type": "object",
            "properties": schema.get("properties", {}),
            "required": schema.get("required", []),
            "description": schema.get("description", ""),
        }

    if isinstance(py_type, type) and issubclass(py_type, Enum):
        enum_values = [e.value for e in py_type]
        enum_type = "string" if all(isinstance(v, str) for v in enum_values) else "integer"
        return {"type": enum_type, "enum": enum_values}

    origin = get_origin(py_type)
    args = get_args(py_type)

    if origin is Literal:
        values = list(args)
        val_type = "string" if all(isinstance(v, str) for v in values) else "integer"
        return {"type": val_type, "enum": values}

    if origin in (Union, types.UnionType):
        non_none_args = [a for a in args if a is not type(None)]
        if len(non_none_args) == 1:
            return python_type_to_json_schema(non_none_args[0])
        return {"anyOf": [python_type_to_json_schema(a) for a in non_none_args]}

    if origin in (list, tuple, set) or py_type in (list, tuple, set):
        item_type = args[0] if args else Any
        return {
            "type": "array",
            "items": python_type_to_json_schema(item_type),
        }

    if origin is dict or py_type is dict:
        return {"type": "object"}

    if py_type is str:
        return {"type": "string"}
    if py_type is int:
        return {"type": "integer"}
    if py_type is float:
        return {"type": "number"}
    if py_type is bool:
        return {"type": "boolean"}

    return {"type": "string"}


def _python_type_matches(value: Any, py_type: Any) -> bool:
    """Best-effort JSON-Schema-style type matching without pulling jsonschema."""
    if py_type is inspect.Parameter.empty or py_type is Any:
        return True

    origin = get_origin(py_type)
    args = get_args(py_type)

    if origin in (Union, types.UnionType):
        return any(_python_type_matches(value, a) for a in args)

    if py_type is type(None):
        return value is None

    if origin is Literal:
        return value in args

    if isinstance(py_type, type) and issubclass(py_type, BaseModel):
        if isinstance(value, py_type):
            return True
        if isinstance(value, dict):
            try:
                py_type.model_validate(value)
            except Exception:
                return False
            return True
        return False

    if isinstance(py_type, type) and issubclass(py_type, Enum):
        try:
            py_type(value)
        except Exception:
            return False
        return True

    if origin in (list, tuple, set) or py_type in (list, tuple, set):
        if not isinstance(value, list):
            return False
        item_type = args[0] if args else Any
        return all(_python_type_matches(v, item_type) for v in value)

    if origin is dict or py_type is dict:
        return isinstance(value, dict)

    if py_type is bool:
        return isinstance(value, bool)
    if py_type is int:
        return isinstance(value, int) and not isinstance(value, bool)
    if py_type is float:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if py_type is str:
        return isinstance(value, str)

    if isinstance(py_type, type):
        return isinstance(value, py_type)

    return True


def validate_arguments(
    func: Callable[..., Any],
    args: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """Validate ``args`` against ``func``'s signature.

    Returns a ``(cleaned_args, errors)`` tuple. If ``errors`` is non-empty the caller
    MUST refuse to invoke the tool (fail closed). Unknown arguments, missing required
    parameters, and mismatched types all produce errors.
    """
    sig = inspect.signature(func)
    try:
        type_hints = inspect.get_annotations(func, eval_str=True)
    except Exception:
        type_hints = getattr(func, "__annotations__", {})

    accepts_var_kwargs = any(
        p.kind is inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
    )

    allowed: dict[str, inspect.Parameter] = {}
    required: list[str] = []
    for name, param in sig.parameters.items():
        if name in ("self", "cls"):
            continue
        if param.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue
        allowed[name] = param
        if param.default is inspect.Parameter.empty:
            py_type = type_hints.get(name, param.annotation)
            origin = get_origin(py_type)
            type_args = get_args(py_type)
            is_optional = origin in (Union, types.UnionType) and type(None) in type_args
            if not is_optional:
                required.append(name)

    errors: list[str] = []
    cleaned: dict[str, Any] = {}

    if not accepts_var_kwargs:
        for key in args:
            if key not in allowed:
                errors.append(f"unknown argument '{key}'")

    for name in required:
        if name not in args:
            errors.append(f"missing required argument '{name}'")

    for name, param in allowed.items():
        if name not in args:
            continue
        value = args[name]
        py_type = type_hints.get(name, param.annotation)
        if not _python_type_matches(value, py_type):
            errors.append(
                f"invalid type for '{name}': expected {getattr(py_type, '__name__', str(py_type))}"
            )
        cleaned[name] = value

    if accepts_var_kwargs:
        for key, value in args.items():
            if key not in allowed:
                cleaned[key] = value

    return cleaned, errors


def generate_tool_definition(
    func: Callable[..., Any],
    name: str | None = None,
    description: str | None = None,
    requires_confirmation: bool = False,
    *,
    risk_level: ToolRiskLevel | None = None,
    toolset: str = "default",
    idempotent: bool = True,
    max_output_bytes: int | None = None,
    max_concurrency: int | None = None,
) -> ToolDefinition:
    """Generate a ToolDefinition from a Python callable using reflection."""
    tool_name = name or getattr(func, "__name__", "unnamed_tool")
    raw_doc = getattr(func, "__doc__", None)
    extracted_desc, param_docs = _parse_docstring_param_descriptions(raw_doc)
    tool_desc = description or extracted_desc

    sig = inspect.signature(func)
    type_hints: dict[str, Any] = {}
    try:
        type_hints = inspect.get_annotations(func, eval_str=True)
    except Exception:
        type_hints = getattr(func, "__annotations__", {})

    properties: dict[str, Any] = {}
    required: list[str] = []

    for param_name, param in sig.parameters.items():
        if param_name in ("self", "cls") or param.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue

        param_type = type_hints.get(param_name, param.annotation)
        param_schema = python_type_to_json_schema(param_type)

        if param_name in param_docs:
            param_schema["description"] = param_docs[param_name]

        if param.default is inspect.Parameter.empty:
            origin = get_origin(param_type)
            args = get_args(param_type)
            is_optional = origin in (Union, types.UnionType) and type(None) in args
            if not is_optional:
                required.append(param_name)
        else:
            param_schema["default"] = param.default

        properties[param_name] = param_schema

    schema = ToolParameterSchema(
        type="object",
        properties=properties,
        required=required,
        additional_properties=False,
    )

    resolved_risk = risk_level or (
        ToolRiskLevel.HIGH if requires_confirmation else ToolRiskLevel.SAFE
    )

    return ToolDefinition(
        name=tool_name,
        description=tool_desc,
        parameters=schema,
        requires_confirmation=requires_confirmation,
        risk_level=resolved_risk,
        toolset=toolset,
        idempotent=idempotent,
        max_output_bytes=max_output_bytes,
        max_concurrency=max_concurrency,
    )
