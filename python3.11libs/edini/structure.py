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
    ctp_present = any(n.startswith("copytopoints") for n in instancing)
    if ctp_present and not signals.get("ctp_target_has_orient"):
        fatal.append({"rule": "F4_ctp_no_orient", "component": cid,
            "detail": "Copy-to-Points target points have none of orient/N/up — copies inherit "
                      "identity orientation (candles/wheels pointing the wrong way)",
            "fix": "Set @orient (quaternion) or @N + @up on the target points "
                   "(attribwrangle or Scatter orient handle).",
            "suggested_tool": "houdini_set_param"})

    overall = "fatal" if fatal else ("advisory" if advisory else "clean")
    return {"fatal": fatal, "advisory": advisory, "overall": overall}


# ── hou-coupled section (lazy import) ─────────────────────────────────────
def _bare_type_name(node) -> str:
    try:
        return node.type().name()
    except Exception:
        return ""


def _classify_instancing(type_name: str) -> bool:
    t = (type_name or "").lower()
    return any(t == n or t.startswith(n + "::") for n in INSTANCING_NODE_TYPES)


def _ctp_target_has_orient(ctp_node) -> bool:
    """True if the Copy-to-Points TARGET-point input (input 1) carries point-level
    orient / N / up. The source/template input (0) is not checked — its normals
    don't orient the copies."""
    try:
        target = ctp_node.input(1)
        if target is None:
            return False
        geo = target.geometry()
        if geo is None:
            return False
        return any(geo.findPointAttrib(nm) is not None for nm in ("orient", "N", "up"))
    except Exception:
        return False


def _extract_component_signals(subnet, component_id: str) -> dict:
    """Walk a component subnet + its out_geometry, build the signal dict that
    evaluate_component_signals consumes. hou-coupled."""
    from edini.project.ports import OUT_GEOMETRY_NODE

    instancing_nodes: set[str] = set()
    python_emit_geometry = False
    ctp_target_has_orient = False
    try:
        children = list(subnet.allSubChildren())
    except Exception:
        children = []
    for child in children:
        tname = _bare_type_name(child)
        if _classify_instancing(tname):
            instancing_nodes.add(tname.split("::")[0])
            if tname.startswith("copytopoints"):
                if _ctp_target_has_orient(child):
                    ctp_target_has_orient = True
        if tname == "python":
            try:
                if child.geometry() is not None and len(child.geometry().prims()) > 0:
                    python_emit_geometry = True
            except Exception:
                pass

    # prim_types from the component's out_geometry (agent's raw output, pre-bake).
    prim_types: dict[str, int] = {}
    out_geo = subnet.node(OUT_GEOMETRY_NODE)
    out_prim_count = 0
    if out_geo is not None:
        try:
            geo = out_geo.geometry()
            if geo is not None:
                for prim in geo.prims():
                    tn = prim.type().name()
                    prim_types[tn] = prim_types.get(tn, 0) + 1
                out_prim_count = len(geo.prims())
        except Exception:
            pass

    inferred_repeats = (
        python_emit_geometry and not instancing_nodes
        and out_prim_count >= _INFERRED_REPEAT_MIN_PRIMS
    )
    return {"component_id": component_id, "prim_types": prim_types,
            "instancing_nodes": instancing_nodes,
            "python_emit_geometry": python_emit_geometry,
            "inferred_repeats": inferred_repeats,
            "ctp_target_has_orient": ctp_target_has_orient}


def analyze_component_structure(core_path: str, component_id: str | None = None) -> dict:
    """Analyze one or all components of a project core. hou-coupled.

    Returns {success, core_path, component_id, overall, fatal[], advisory[],
    signals_per_component}. F3 (axis) is computed here via verify_orientation
    (reuses the baked edini_world_axis ground truth).
    """
    try:
        import hou
        from edini.project.state import load_declaration
        from edini.verify import verify_orientation
    except ImportError:
        return {"success": False, "error": "hou not available"}

    core = hou.node(core_path)
    if core is None:
        return {"success": False, "error": f"Core not found: {core_path}"}
    decl = load_declaration(core)
    components = decl.get("components", []) or []
    if component_id is not None:
        components = [c for c in components if c.get("id") == component_id]
        if not components:
            return {"success": False, "error": f"component {component_id!r} not declared"}

    out_node = core.node("OUT")
    out_path = out_node.path() if out_node is not None else None

    all_fatal: list[dict] = []
    all_advisory: list[dict] = []
    signals_per: dict[str, dict] = {}

    for comp in components:
        cid = comp.get("id", "?")
        subnet = core.node(cid)
        if subnet is None:
            all_fatal.append({"rule": "missing_component_subnet", "component": cid,
                              "detail": f"component subnet {cid!r} not found on the core"})
            continue
        declared = comp.get("structure")
        signals = _extract_component_signals(subnet, cid)

        # ── F3: declared radial/planar axis vs baked edini_world_axis ──
        kind = (declared or {}).get("kind")
        expected_axis = (declared or {}).get("expected_axis")
        if kind in ("radial", "planar") and expected_axis and out_path is not None:
            vr = verify_orientation(out_path, [{"component_id": cid,
                                                "kind": kind,
                                                "expected_axis": expected_axis,
                                                "tolerance_deg": 15}])
            if vr.get("success") and vr.get("failed", 0) > 0:
                det = (vr.get("checks") or [{}])[0].get("detected_axis", "?")
                signals["baked_axis"] = det
                all_fatal.append({"rule": "F3_axis_mismatch", "component": cid,
                    "detail": f"declared axis {expected_axis!r} != baked/detected axis {det!r}",
                    "fix": "Rebuild the part so its construction axis matches, "
                           "or correct the declared expected_axis.",
                    "suggested_tool": "verify_orientation"})

        verdict = evaluate_component_signals(signals, declared)
        all_fatal.extend(verdict["fatal"])
        all_advisory.extend(verdict["advisory"])
        signals_per[cid] = signals

    overall = "fatal" if all_fatal else ("advisory" if all_advisory else "clean")
    return {"success": True, "core_path": core_path,
            "component_id": component_id, "overall": overall,
            "fatal": all_fatal, "advisory": all_advisory,
            "signals_per_component": signals_per}
