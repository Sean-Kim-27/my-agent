"""Safe arithmetic expression evaluator using AST parsing.

Replaces ``eval()``-based calculator implementations. Only literal numbers and a
whitelisted subset of binary / unary operators are accepted; anything else
(names, attribute access, function calls) raises ``ValueError``.
"""

from __future__ import annotations

import ast
import operator
from collections.abc import Callable

Number = int | float
BinaryOp = Callable[[Number, Number], Number]
UnaryOp = Callable[[Number], Number]

_BIN_OPS: dict[type[ast.operator], BinaryOp] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_UNARY_OPS: dict[type[ast.unaryop], UnaryOp] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

_MAX_POW_EXPONENT = 32


def _evaluate(node: ast.AST) -> Number:
    if isinstance(node, ast.Expression):
        return _evaluate(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise ValueError(f"Unsupported literal: {node.value!r}")
        return node.value
    if isinstance(node, ast.BinOp):
        bin_type = type(node.op)
        bin_op = _BIN_OPS.get(bin_type)
        if bin_op is None:
            raise ValueError(f"Unsupported binary operator: {bin_type.__name__}")
        left = _evaluate(node.left)
        right = _evaluate(node.right)
        if bin_type is ast.Pow and abs(right) > _MAX_POW_EXPONENT:
            raise ValueError("Exponent too large")
        return bin_op(left, right)
    if isinstance(node, ast.UnaryOp):
        unary_type = type(node.op)
        unary_op = _UNARY_OPS.get(unary_type)
        if unary_op is None:
            raise ValueError(f"Unsupported unary operator: {unary_type.__name__}")
        return unary_op(_evaluate(node.operand))
    raise ValueError(f"Unsupported expression node: {type(node).__name__}")


def safe_eval_math(expression: str) -> Number:
    """Safely evaluate an arithmetic expression.

    Supported: + - * / // % ** and parentheses over integer / float literals.
    Raises ``ValueError`` on any disallowed construct (names, calls, attrs, etc.).
    """
    if not expression or not expression.strip():
        raise ValueError("Expression is empty")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"Invalid arithmetic expression: {exc.msg}") from exc
    return _evaluate(tree)
