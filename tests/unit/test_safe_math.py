"""Tests for the AST-based safe arithmetic evaluator."""

from __future__ import annotations

import pytest

from agent_framework.tools.safe_math import safe_eval_math


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("1 + 2", 3),
        ("25 * 48 + 12", 1212),
        ("(4 + 6) * 2", 20),
        ("2 ** 8", 256),
        ("10 / 4", 2.5),
        ("10 // 3", 3),
        ("17 % 5", 2),
        ("-3 + 5", 2),
        ("+7 - 2", 5),
    ],
)
def test_safe_eval_math_accepts_valid_arithmetic(expression: str, expected: float) -> None:
    assert safe_eval_math(expression) == expected


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os').system('ls')",
        "abs(-1)",
        "x + 1",
        "1 + 'a'",
        "open('/etc/passwd')",
        "().__class__",
    ],
)
def test_safe_eval_math_rejects_disallowed_expressions(expression: str) -> None:
    with pytest.raises(ValueError):
        safe_eval_math(expression)


def test_safe_eval_math_rejects_empty() -> None:
    with pytest.raises(ValueError):
        safe_eval_math("")


def test_safe_eval_math_rejects_boolean_literals() -> None:
    with pytest.raises(ValueError):
        safe_eval_math("True + 1")


def test_safe_eval_math_caps_giant_exponents() -> None:
    with pytest.raises(ValueError):
        safe_eval_math("2 ** 1000")
