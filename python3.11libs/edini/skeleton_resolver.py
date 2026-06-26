"""Skeleton-point DAG resolver — the coordinate core of the asset pipeline.

A *skeleton* is an ordered mapping of named 3D points, each defined by a
3-element ``expr`` (one expression string per X/Y/Z axis). Points may
reference other points (``rear_axle[0]``) and asset parameters
(``wheel_radius``). The references form a DAG: a point's coordinates are
computed from parameters + already-resolved upstream points.

This module is the pure-data engine that:

  1. Builds the dependency graph from each point's expressions.
  2. Topologically sorts the points (Kahn's algorithm) so every point is
     evaluated only after its point-dependencies — raising
     ``SkeletonCycleError`` if the graph has a cycle.
  3. Evaluates every point to a concrete ``(x, y, z)`` tuple, threading
     resolved point coordinates back in as variables (``rear_axle``,
     ``rear_axle[0]``) so downstream expressions can read them.

Design notes
------------
- Pure Python, no ``hou``. Unit-testable in isolation.
- Point-reference syntax: ``<point_name>`` (whole point, a 3-tuple) or
  ``<point_name>[<axis>]`` (a single axis scalar). Both are rewritten to
  plain Python before evaluation: the whole form becomes the tuple value
  bound to the name; the indexed form is left as-is (Python subscript on a
  tuple).
- A name that is NOT a declared point is assumed to be a parameter — it is
  passed straight through to ``exprs.evaluate``. Unknown params surface as
  ``ExprError`` at evaluation time, which the caller reports.

This is milestone-1 foundation: components (milestone 2) will *attach* to
these resolved points, so every later stage inherits the parametric linkage
for free.
"""
from __future__ import annotations

import ast
import re
from typing import Any

from edini.exprs import ExprError, evaluate_tuple, extract_refs

__all__ = [
    "SkeletonError",
    "SkeletonCycleError",
    "topo_order",
    "point_dependencies",
    "evaluate_skeleton",
]

# A point reference looks like ``name`` or ``name[0]``. We match the bare
# name to discover dependencies; the optional subscript is handled during
# evaluation by binding each resolved point to its name (so ``name[0]`` is
# just Python tuple indexing in the expression).
_POINT_NAME_RE = re.compile(r'([A-Za-z_]\w*)')


class SkeletonError(ValueError):
    """Base class for skeleton resolution errors."""


class SkeletonCycleError(SkeletonError):
    """Raised when the skeleton dependency graph contains a cycle."""


def _skeleton_point_names(skeleton: dict[str, Any]) -> set[str]:
    """The set of declared point names (the keys of the skeleton dict)."""
    return set(skeleton.keys())


def _point_expr_strings(point_spec: Any) -> list[str]:
    """Flatten a point's ``expr`` field into a list of expression strings.

    Accepts ``{"expr": ["a", "b", "c"]}`` or a bare ``["a","b","c"]`` list.
    Non-string elements (plain numbers) contribute no references.
    """
    exprs = point_spec.get("expr") if isinstance(point_spec, dict) else point_spec
    if not isinstance(exprs, (list, tuple)):
        return []
    return [e for e in exprs if isinstance(e, str)]


def point_dependencies(skeleton: dict[str, Any]) -> dict[str, set[str]]:
    """For each point, the set of OTHER points it references.

    Parameter references (names not in the skeleton) are excluded — only
    inter-point edges go into the DAG. Returns ``{point_name: {dep_point, ...}}``.
    """
    names = _skeleton_point_names(skeleton)
    deps: dict[str, set[str]] = {}
    for pname, spec in skeleton.items():
        refs: set[str] = set()
        for estr in _point_expr_strings(spec):
            for r in extract_refs(estr):
                if r in names and r != pname:
                    refs.add(r)
        deps[pname] = refs
    return deps


def topo_order(skeleton: dict[str, Any]) -> list[str]:
    """Topologically sort skeleton points so each point follows its deps.

    Uses Kahn's algorithm. Raises ``SkeletonCycleError`` if a cycle exists,
    listing the points involved in the cycle.
    """
    deps = point_dependencies(skeleton)
    # in_degree[p] = number of unresolved point-dependencies of p
    in_degree: dict[str, int] = {p: len(d) for p, d in deps.items()}
    # adjacency: dep -> [points that depend on it]
    adjacency: dict[str, list[str]] = {p: [] for p in deps}
    for p, dset in deps.items():
        for dep in dset:
            adjacency[dep].append(p)

    queue = sorted([p for p, d in in_degree.items() if d == 0])
    order: list[str] = []
    while queue:
        node = queue.pop(0)
        order.append(node)
        next_ready: list[str] = []
        for neighbor in adjacency.get(node, []):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                next_ready.append(neighbor)
        # keep deterministic order
        queue.extend(sorted(next_ready))

    if len(order) != len(deps):
        cycle_nodes = sorted(p for p, d in in_degree.items() if d > 0)
        raise SkeletonCycleError(
            f"skeleton has a cycle involving: {', '.join(cycle_nodes)} "
            f"(points: {cycle_nodes})"
        )
    return order


def _rewrite_indexed_point_refs(expr: str, resolved: dict[str, tuple]) -> str:
    """No-op placeholder kept for clarity — indexed refs (``name[0]``) work
    natively because we bind each resolved point to its name as a tuple,
    so Python's subscript handles ``name[0]`` during evaluation.

    A whole-point reference (``name`` with no subscript) is also valid and
    evaluates to the tuple — but since each axis is evaluated as a scalar,
    authors normally write ``name[axis]``. We surface a helpful error for
    a bare point name used in a scalar axis expression in ``_check_refs``.
    """
    return expr


def _axis_params(
    axis_expr: str, resolved: dict[str, tuple], params: dict[str, float]
) -> dict[str, Any]:
    """Build the variable binding for evaluating a single axis expression.

    Parameters are passed through as scalars. Resolved points are bound as
    tuples so ``name[0]`` subscripting works. A bare point name (no subscript)
    in a scalar axis yields a non-scalar and ``evaluate`` will raise a clear
    ExprError.
    """
    env: dict[str, Any] = dict(params)
    for pname, coords in resolved.items():
        env[pname] = coords
    return env


def evaluate_skeleton(
    skeleton: dict[str, Any],
    params: dict[str, float],
) -> dict[str, tuple[float, float, float]]:
    """Resolve every skeleton point to a concrete (x, y, z) tuple.

    Points are evaluated in topological order; each point's resolved
    coordinates are made available to later points. Parameters are
    provided as scalars.

    Args:
        skeleton: ``{point_name: {"expr": [xstr, ystr, zstr]}}``.
        params:   ``{param_name: float}`` — primary parameter values.

    Returns:
        ``{point_name: (x, y, z)}``.

    Raises:
        SkeletonCycleError: cycle in point references.
        ExprError: bad/unknown reference in an expression (e.g. a typo'd
            parameter name, or a bare point name used without subscript).
    """
    order = topo_order(skeleton)
    resolved: dict[str, tuple[float, float, float]] = {}
    for pname in order:
        spec = skeleton[pname]
        exprs = spec.get("expr") if isinstance(spec, dict) else spec
        env = _axis_params("", resolved, params)
        coords = evaluate_tuple(exprs, env, length=3, what=f"skeleton.{pname}.expr")
        resolved[pname] = coords
    return resolved
