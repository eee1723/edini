"""Component structural analyzer: declare→verify closed loop.

Pure-logic core (lint + evaluator) is hou-free and unit-testable; the
hou-coupled extractor/orchestrator is lower in this module and lazy-imports hou.
See docs/superpowers/specs/2026-07-10-component-structure-analyzer-design.md.
"""
from __future__ import annotations

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
    {code, detail, schema_hint?} dicts (schema_hint present only where
    helpful). Called by build_project_scaffold BEFORE any nodes are created
    — the shift-left refusal point.
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


def _is_curve_prim_type(type_name: str) -> bool:
    t = (type_name or "").lower()
    return any(k in t for k in _CURVE_PRIM_KEYWORDS)


def evaluate_component_signals(signals: dict, declared: dict | None) -> dict:
    """Pure: map extracted signals + declared intent to fatal/advisory verdicts.

    F3 (axis) is NOT computed here — it needs cooked geometry math and is
    delegated to verify_orientation by the orchestrator. This function handles
    the node-graph/prim-type/CTP structure rules F1/F2/F4.

    signals keys: component_id, prim_types(dict name->count),
        instancing_nodes(set of method names present in subnet),
        python_emit_geometry(bool), inferred_repeats(bool),
        ctp_target_has_orient(bool).
    Returns {fatal:[...], advisory:[...], overall: 'fatal'|'advisory'|'clean'}.
    """
    cid = signals.get("component_id", "?")
    fatal: list[dict] = []
    advisory: list[dict] = []
    prim_types = signals.get("prim_types", {}) or {}
    instancing = set(signals.get("instancing_nodes", set()) or set())

    # ── F1: bare curve/surface prims at the component's out_geometry ──
    curve_types = sorted({t for t in prim_types if _is_curve_prim_type(t)})
    if curve_types:
        fatal.append({"rule": "F1_bare_curves_at_out", "component": cid,
            "detail": (f"out_geometry has curve prims {curve_types} — skeleton not "
                       f"surfaced, or OUT is wired to the curve instead of PolyWire/Sweep"),
            "fix": "Wire out_geometry through PolyWire/Sweep to thicken curves, "
                   "or Blast the construction curves.",
            "suggested_tool": "houdini_connect_nodes"})

    # ── F2: repeated part declared with instancing but no such node ──
    declared_repeats = ((declared or {}).get("repeats")) or []
    declared_instancing = {r.get("method") for r in declared_repeats
                           if isinstance(r, dict) and r.get("method") in _INSTANCING_METHODS}
    if declared_instancing and not (declared_instancing & instancing):
        fatal.append({"rule": "F2_repeat_no_instancing", "component": cid, "confidence": "declared",
            "detail": (f"declared instancing method(s) {sorted(declared_instancing)} but no such "
                       f"node in the component subnet — repeated sub-parts must be instanced, not "
                       f"hand-duplicated (even 2 instances)"),
            "fix": "Add a Copy-to-Points node: one template + target point cloud.",
            "suggested_tool": "houdini_create_node"})
    elif signals.get("inferred_repeats") and not instancing:
        # No declaration (legacy) — infer. False-positive risk ⇒ override-able.
        fatal.append({"rule": "F2_repeat_no_instancing", "component": cid, "confidence": "inferred",
            "detail": "repeated/radial sub-geometry detected with no instancing node — likely "
                      "hand-duplicated inside a Python SOP",
            "fix": "Add a Copy-to-Points node for the repeated sub-parts.",
            "suggested_tool": "houdini_create_node"})

    # ── F4: Copy-to-Points present but target points lack orient/N/up ──
    if instancing and not signals.get("ctp_target_has_orient"):
        fatal.append({"rule": "F4_ctp_no_orient", "component": cid,
            "detail": "Copy-to-Points target points have none of orient/N/up — copies inherit "
                      "identity orientation (candles/wheels pointing the wrong way)",
            "fix": "Set @orient (quaternion) or @N + @up on the target points "
                   "(attribwrangle or Scatter orient handle).",
            "suggested_tool": "houdini_set_param"})

    overall = "fatal" if fatal else ("advisory" if advisory else "clean")
    return {"fatal": fatal, "advisory": advisory, "overall": overall}
