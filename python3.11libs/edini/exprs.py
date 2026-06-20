"""Safe arithmetic expression engine for recipe parameter linkage (A2-station).

Recipe authors reference asset-level parameters inside anchor position /
orient / pscale expressions, e.g.::

    "position_expr": ["wheelbase/2", "wheel_r", "0"]

These are evaluated at BUILD time (deterministic — the same value every
build for the same parameter set) into concrete coordinates. This module is
the sandboxed evaluator: it accepts a strict subset of Python expressions
(parameter names, arithmetic, a whitelist of ``math`` functions) and rejects
everything else (imports, attribute access, arbitrary calls, assignments).

Design constraints:
  - No ``hou`` dependency (pure-Python, unit-testable in isolation).
  - Failure is explicit: a bad expression raises ``ExprError`` with the
    expression and the reason, so the builder can surface it to the agent
    instead of producing silent NaNs.
  - The whitelist is deliberately small. If a recipe needs more (e.g.
    conditionals), extend ``_SAFE_FUNCS`` / the node allow-list — do not
    widen the eval policy.
"""
from __future__ import annotations

import ast
import math
import operator
from typing import Any, Mapping

__all__ = ["ExprError", "evaluate", "evaluate_tuple"]


class ExprError(ValueError):
    """Raised when an expression is unsafe or references an unknown param."""


# Whitelisted binary operators (the AST node -> callable mapping).
_BIN_OPS: dict[type, Any] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_UNARY_OPS: dict[type, Any] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

# Whitelisted ``math`` functions. Only pure functions (no I/O, no state).
# Keys are the names authors write; values are the callables.
_SAFE_FUNCS: dict[str, Any] = {
    "abs": abs,
    "min": min,
    "max": max,
    "round": round,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "asin": math.asin,
    "acos": math.acos,
    "atan": math.atan,
    "atan2": math.atan2,
    "sqrt": math.sqrt,
    "radians": math.radians,
    "degrees": math.degrees,
    "floor": math.floor,
    "ceil": math.ceil,
    "exp": math.exp,
    "log": math.log,
    "pow": pow,
    "hypot": math.hypot,
}

# Constants authors may use (alongside parameter names).
_SAFE_CONSTS: dict[str, float] = {
    "pi": math.pi,
    "e": math.e,
    "tau": math.tau,
}


def _eval_node(node: ast.AST, params: Mapping[str, float]) -> float:
    """Recursive AST evaluator. Raises ExprError on anything not whitelisted."""
    # Number / constant literal.
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise ExprError(f"unsupported literal {node.value!r}")
        return float(node.value)

    # Parameter name or whitelisted constant.
    if isinstance(node, ast.Name):
        name = node.id
        if name in params:
            val = params[name]
            try:
                return float(val)
            except (TypeError, ValueError):
                raise ExprError(
                    f"parameter {name!r} is not numeric (got {val!r})") from None
        if name in _SAFE_CONSTS:
            return float(_SAFE_CONSTS[name])
        raise ExprError(
            f"unknown name {name!r} (not a declared parameter or constant)")

    # Arithmetic: + - * / % **
    if isinstance(node, ast.BinOp):
        op_fn = _BIN_OPS.get(type(node.op))
        if op_fn is None:
            raise ExprError(f"operator {type(node.op).__name__} not allowed")
        left = _eval_node(node.left, params)
        right = _eval_node(node.right, params)
        try:
            return float(op_fn(left, right))
        except ZeroDivisionError:
            raise ExprError("division by zero in expression") from None

    # Unary + / -
    if isinstance(node, ast.UnaryOp):
        op_fn = _UNARY_OPS.get(type(node.op))
        if op_fn is None:
            raise ExprError(f"unary {type(node.op).__name__} not allowed")
        return float(op_fn(_eval_node(node.operand, params)))

    # Function call — only whitelisted names, positional args only.
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ExprError("only direct calls to whitelisted functions allowed")
        fname = node.func.id
        if fname not in _SAFE_FUNCS:
            raise ExprError(f"function {fname!r} is not allowed")
        if node.keywords:
            raise ExprError("keyword arguments not allowed in expressions")
        args = [_eval_node(a, params) for a in node.args]
        try:
            return float(_SAFE_FUNCS[fname](*args))
        except (ValueError, OverflowError, TypeError) as exc:
            raise ExprError(f"{fname}() failed: {exc}") from None

    # Anything else (Attribute, Subscript, Import, BoolOp, Compare, lambda,
    # comprehensions, ...) is rejected — this is the security boundary.
    raise ExprError(
        f"disallowed expression element: {type(node).__name__}")


def evaluate(expr: str, params: Mapping[str, float]) -> float:
    """Evaluate a single arithmetic expression against ``params``.

    Args:
        expr: e.g. ``"wheelbase/2"`` or ``"wheel_r * 2 + 0.05"``.
        params: declared asset parameters (name -> current value).

    Returns:
        The evaluated float.

    Raises:
        ExprError: if the expression is unsafe, references an unknown
            name, or errors at evaluation (e.g. division by zero).
    """
    if not isinstance(expr, str) or not expr.strip():
        raise ExprError("expression must be a non-empty string")
    try:
        tree = ast.parse(expr.strip(), mode="eval")
    except SyntaxError as exc:
        raise ExprError(f"expression syntax error: {exc.msg}") from None
    result = _eval_node(tree.body, params)
    if not math.isfinite(result):
        raise ExprError(f"expression evaluated to non-finite value: {result}")
    return result


def evaluate_tuple(
    exprs: Any,
    params: Mapping[str, float],
    *,
    length: int,
    what: str = "value",
) -> tuple[float, ...]:
    """Evaluate a list of expressions into a fixed-length float tuple.

    Accepts either a list of expression strings (evaluated against params)
    or a list of plain numbers (passed through). This lets anchor fields
    accept both ``"position_expr": ["wheelbase/2", "wheel_r", "0"]`` and
    legacy numeric lists where applicable.

    Args:
        exprs: list of strings/numbers, length must equal ``length``.
        params: declared asset parameters.
        length: expected tuple length (e.g. 3 for position, 4 for orient).
        what: field name for error messages (e.g. "position_expr").

    Returns:
        Tuple of ``length`` floats.
    """
    if not isinstance(exprs, (list, tuple)):
        raise ExprError(f"{what} must be a list of {length} values")
    if len(exprs) != length:
        raise ExprError(f"{what} must have exactly {length} values, got {len(exprs)}")
    out: list[float] = []
    for i, e in enumerate(exprs):
        if isinstance(e, str):
            out.append(evaluate(e, params))
        elif isinstance(e, bool) or not isinstance(e, (int, float)):
            raise ExprError(f"{what}[{i}] must be a number or expression string")
        else:
            val = float(e)
            if not math.isfinite(val):
                raise ExprError(f"{what}[{i}] is non-finite: {val}")
            out.append(val)
    return tuple(out)


# ── Reference extraction for dependency graph (Phase A6) ──────────

import re as _re

_REF_RE = _re.compile(r'([a-zA-Z_]\w*)')

_BUILTIN_NAMES: set[str] = {
    "sin", "cos", "tan", "abs", "min", "max", "sqrt", "pow",
    "radians", "degrees", "pi", "e", "tau", "and", "or", "not",
    "if", "else", "True", "False", "None",
}


def extract_refs(expr: str) -> list[str]:
    """Extract parameter references from a safe expression string.

    Examples:
        extract_refs("wheel_radius - bb_drop") -> ["bb_drop", "wheel_radius"]
        extract_refs("sin(radians(seat_angle)) + frame_scale * 0.5")
            -> ["frame_scale", "seat_angle"]

    Built-in function names and numeric literals are excluded.
    """
    refs: set[str] = set()
    for m in _REF_RE.finditer(expr):
        name = m.group(1)
        if name not in _BUILTIN_NAMES and not name[0].isdigit():
            refs.add(name)
    return sorted(refs)
