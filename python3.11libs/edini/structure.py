"""Component structural analyzer: declare→verify closed loop.

Pure-logic core (lint + evaluator) is hou-free and unit-testable; the
hou-coupled extractor/orchestrator is lower in this module and lazy-imports hou.
See docs/superpowers/specs/2026-07-10-component-structure-analyzer-design.md.
"""
from __future__ import annotations
from typing import Any

# ── Declaration schema constants ──────────────────────────────────────────
_VALID_KINDS = {"radial", "planar", "repeated", "solid"}
_AXIS_TOKENS = {"X", "Y", "Z", "-X", "-Y", "-Z"}
_INSTANCING_METHODS = {"copytopoints", "foreach", "stamp", "copy"}
_SURFACING_METHODS = {"sweep", "polywire", "skin", "rails"}

# Node-type taxonomy (canonical home; harness keeps aliases — see Task 11).
MODULAR_NODE_TYPES = {
    "copytopoints", "copytopoints::2.0", "copy", "copystamp",
    "sweep", "sweep::2.0", "skin", "rails",
    "foreach::count", "foreach::piece", "foreach", "foreach_begin",
    "xformpieces", "transformpieces", "instanceto",
    "boolean", "boolean::2.0", "polyextrude", "polyextrude::2.0",
    "pack", "unpack",
}
INSTANCING_NODE_TYPES = {
    "copytopoints", "copytopoints::2.0", "copy", "copystamp",
    "foreach::count", "foreach::piece", "foreach", "foreach_begin",
    "xformpieces", "transformpieces", "instanceto",
}
_CURVE_PRIM_KEYWORDS = ("curve", "polyline", "nurbs", "bez", "span")

# Inferred-repeat heuristic: a Python SOP emitting this many prims with no
# instancing node likely hand-duplicated repeated sub-parts (deepseek wheels).
_INFERRED_REPEAT_MIN_PRIMS = 40


def lint_structure_decl(comp: dict) -> list[dict]:
    """Validate a component's `structure` declaration. Pure (no hou).

    Returns [] if the declaration is acceptable, else a list of
    {code, detail, schema_hint} dicts. Called by build_project_scaffold
    BEFORE any nodes are created — the shift-left refusal point.
    """
    cid = comp.get("id", "?")
    struct = comp.get("structure")
    if struct is None:
        return [{
            "code": "structure_missing",
            "detail": (f"component {cid!r} has no `structure` declaration. "
                       f"Declare kind + (for radial/planar) expected_axis + repeats."),
            "schema_hint": {"kind": "solid | radial | planar | repeated",
                            "expected_axis": "X|Y|Z (required for radial/planar)",
                            "repeats": [{"part": "spoke", "count": 28,
                                         "method": "copytopoints"}]},
        }]
    if not isinstance(struct, dict):
        return [{"code": "structure_not_dict", "detail": f"{cid!r}.structure must be a dict"}]

    errors: list[dict] = []
    kind = struct.get("kind")
    if kind not in _VALID_KINDS:
        errors.append({"code": "bad_kind",
                       "detail": f"{cid!r}.structure.kind={kind!r}; must be one of {sorted(_VALID_KINDS)}"})

    if kind in ("radial", "planar"):
        ax = struct.get("expected_axis")
        if ax not in _AXIS_TOKENS:
            errors.append({"code": "missing_axis",
                           "detail": f"{cid!r} kind={kind} requires expected_axis in {sorted(_AXIS_TOKENS)}"})

    repeats = struct.get("repeats") or []
    if kind == "repeated" and not repeats:
        errors.append({"code": "repeated_without_repeats",
                       "detail": f"{cid!r} kind=repeated requires a non-empty repeats[]"})
    for r in repeats:
        if not isinstance(r, dict):
            errors.append({"code": "bad_repeat_entry", "detail": f"{cid!r} repeat entry not a dict: {r!r}"})
            continue
        m = r.get("method")
        count = r.get("count")
        if m in _INSTANCING_METHODS and (not isinstance(count, int) or count < 2):
            errors.append({"code": "bad_repeat_count",
                           "detail": f"{cid!r} repeat {r.get('part')!r} method={m!r} needs integer count>=2 (got {count!r})"})
    return errors
