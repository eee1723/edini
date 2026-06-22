"""Phase A: Pure validation of procedural asset recipes.

Zero Houdini operations. All checks are deterministic data validation
against the parm catalog and expression engine.
"""

import math
import re
from typing import Any

# ParmCatalog is imported lazily — it requires hou module (Houdini runtime).
# A1, A4, A5, A6 stages run without it; A2/A3 need the catalog.
_ParmCatalog: Any = None

def _get_catalog(catalog_path: str | None) -> Any:
    """Lazy-load ParmCatalog. Returns None if not available."""
    global _ParmCatalog
    if _ParmCatalog is None and catalog_path:
        try:
            from edini.parm_catalog import ParmCatalog as PC
            _ParmCatalog = PC
        except Exception:
            return None
    if _ParmCatalog and catalog_path:
        try:
            return _ParmCatalog.load(catalog_path)
        except Exception:
            _ParmCatalog = None  # reset — catalog might be broken
            return None
    return None

# ── Constants ───────────────────────────────────────────────

VALID_BACKENDS = {"python", "vex_skeleton", "native_chain"}
LOCAL_AXIS_VECTORS = {
    "X": (1.0, 0.0, 0.0),
    "Y": (0.0, 1.0, 0.0),
    "Z": (0.0, 0.0, 1.0),
}


def _error(code: str, message: str, location: dict) -> dict:
    return {
        "stage": code,
        "severity": "BLOCKING" if "WARNING" not in code else "WARNING",
        "message": message,
        "location": location,
    }


# ═══════════════════════════════════════════════════════════════
#  A1 — Schema Validation
# ═══════════════════════════════════════════════════════════════

def _validate_a1_schema(recipe: dict) -> list[dict]:
    """Validate recipe JSON structure. Returns list of error dicts."""
    errors: list[dict] = []

    if not isinstance(recipe, dict):
        return [_error("A1_SCHEMA", "recipe must be a JSON object", {})]

    # ── components ──
    components = recipe.get("components")
    if not isinstance(components, list) or not components:
        errors.append(_error(
            "A1_SCHEMA",
            "recipe.components must be a non-empty list",
            {"field": "components"}
        ))
        return errors

    seen_ids: set[str] = set()
    for i, comp in enumerate(components):
        loc: dict[str, Any] = {"component_index": i}
        if not isinstance(comp, dict):
            errors.append(_error("A1_SCHEMA", f"components[{i}] must be an object", loc))
            continue
        cid = comp.get("id")
        if not isinstance(cid, str) or not cid.strip():
            errors.append(_error("A1_SCHEMA", f"components[{i}].id must be a non-empty string", loc))
        elif cid in seen_ids:
            errors.append(_error("A1_SCHEMA", f"components[{i}].id '{cid}' duplicates", loc))
        else:
            seen_ids.add(cid)
        loc["component_id"] = cid

        backend = comp.get("backend", "python")
        if backend not in VALID_BACKENDS:
            errors.append(_error(
                "A1_SCHEMA",
                f"components[{i}].backend '{backend}' must be one of {sorted(VALID_BACKENDS)}",
                loc
            ))

        if backend != "native_chain":
            code = comp.get("code", "")
            if not isinstance(code, str) or not code.strip():
                errors.append(_error(
                    "A1_SCHEMA",
                    f"components[{i}].code must be a non-empty string (backend={backend})",
                    loc
                ))

        if backend == "vex_skeleton":
            form = comp.get("form_node")
            if not isinstance(form, dict):
                errors.append(_error(
                    "A1_SCHEMA",
                    f"components[{i}] (vex_skeleton) requires form_node object",
                    loc
                ))
            else:
                fn_type = form.get("type")
                if not isinstance(fn_type, str) or not fn_type.strip():
                    errors.append(_error(
                        "A1_SCHEMA",
                        f"components[{i}].form_node.type must be a non-empty SOP type",
                        {**loc, "field": "form_node.type"}
                    ))

        if backend == "native_chain":
            nodes = comp.get("nodes")
            if not isinstance(nodes, list):
                errors.append(_error(
                    "A1_SCHEMA",
                    f"components[{i}] (native_chain) requires nodes list",
                    loc
                ))
            else:
                for ni, node in enumerate(nodes):
                    nloc = {**loc, "node_index": ni}
                    if not isinstance(node.get("type"), str) or not node["type"].strip():
                        errors.append(_error(
                            "A1_SCHEMA",
                            f"components[{i}].nodes[{ni}].type must be a non-empty string",
                            nloc
                        ))

    # ── params ──
    params = recipe.get("params")
    if params is not None:
        if not isinstance(params, dict):
            errors.append(_error("A1_SCHEMA", "recipe.params must be an object if present", {}))
        else:
            for pname, pspec in params.items():
                ploc: dict[str, Any] = {"param_name": pname}
                if not isinstance(pspec, dict):
                    errors.append(_error("A1_SCHEMA", f"params['{pname}'] must be an object", ploc))
                    continue
                kind = pspec.get("kind", "primary")
                if kind not in ("primary", "derived", "constrained"):
                    errors.append(_error(
                        "A1_SCHEMA",
                        f"params['{pname}'].kind '{kind}' must be primary|derived|constrained",
                        ploc
                    ))
                if "default" not in pspec and kind == "primary":
                    errors.append(_error(
                        "A1_SCHEMA",
                        f"params['{pname}'] (primary) requires 'default'",
                        ploc
                    ))
                if kind == "derived" and "from" not in pspec:
                    errors.append(_error(
                        "A1_SCHEMA",
                        f"params['{pname}'] (derived) requires 'from' expression",
                        ploc
                    ))
                if kind == "constrained":
                    constraints = pspec.get("constraints")
                    if not isinstance(constraints, list):
                        errors.append(_error(
                            "A1_SCHEMA",
                            f"params['{pname}'] (constrained) requires 'constraints' list",
                            ploc
                        ))
    return errors


# ═══════════════════════════════════════════════════════════════
#  A2 — Parm Name Cross-Validation
# ═══════════════════════════════════════════════════════════════

def _validate_a2_parm_names(recipe: dict, catalog: Any) -> list[dict]:
    """Cross-check all SOP parm names against the catalog."""
    if catalog is None:
        return []
    errors: list[dict] = []

    for i, comp in enumerate(recipe.get("components", [])):
        cid = comp.get("id", f"@index_{i}")
        loc: dict[str, Any] = {"component_index": i, "component_id": cid}

        if comp.get("backend") == "native_chain":
            for ni, node in enumerate(comp.get("nodes", [])):
                ntype = node.get("type", "")
                nloc: dict[str, Any] = {**loc, "node_index": ni, "node_type": ntype}
                canonical = catalog.resolve_alias(ntype)
                if ntype != canonical:
                    nloc["node_type"] = canonical
                params = node.get("params", {})
                for pname, pvalue in params.items():
                    nloc_p = {**nloc, "parm_name": pname}
                    err = catalog.validate_parm(canonical, pname, pvalue)
                    if err:
                        errors.append(_error("A2_PARAM_NAME", err, nloc_p))

        elif comp.get("backend") == "vex_skeleton":
            form = comp.get("form_node", {})
            fn_type = form.get("type", "")
            canonical = catalog.resolve_alias(fn_type)
            floc: dict[str, Any] = {**loc, "field": "form_node", "node_type": canonical}
            for pname, pvalue in form.get("params", {}).items():
                floc_p = {**floc, "parm_name": pname}
                err = catalog.validate_parm(canonical, pname, pvalue)
                if err:
                    errors.append(_error("A2_PARAM_NAME", err, floc_p))

    # ── postprocess parms ──
    for pi, step in enumerate(recipe.get("postprocess", [])):
        stype = step.get("type", "")
        canonical = catalog.resolve_alias(stype)
        ploc: dict[str, Any] = {"postprocess_index": pi, "node_type": canonical}
        for pname, pvalue in step.get("params", {}).items():
            ploc_p = {**ploc, "parm_name": pname}
            err = catalog.validate_parm(canonical, pname, pvalue)
            if err:
                errors.append(_error("A2_PARAM_NAME", err, ploc_p))

    return errors


# ═══════════════════════════════════════════════════════════════
#  A3 — Node Type Validation
# ═══════════════════════════════════════════════════════════════

def _validate_a3_node_types(recipe: dict, catalog: Any) -> list[dict]:
    """Verify all node type names exist in the catalog (or have an alias)."""
    if catalog is None:
        return []
    errors: list[dict] = []

    for i, comp in enumerate(recipe.get("components", [])):
        cid = comp.get("id", f"@index_{i}")
        loc: dict[str, Any] = {"component_index": i, "component_id": cid}

        if comp.get("backend") == "native_chain":
            for ni, node in enumerate(comp.get("nodes", [])):
                ntype = node.get("type", "")
                nloc: dict[str, Any] = {**loc, "node_index": ni, "node_type": ntype}
                canonical = catalog.resolve_alias(ntype)
                if canonical != ntype:
                    nloc["canonical_type"] = canonical
                if not catalog.has_node_type(canonical):
                    errors.append(_error(
                        "A3_NODE_TYPE",
                        f"node type '{ntype}' not found in Houdini {catalog._data.get('houdini_version')}",
                        nloc
                    ))

        if comp.get("backend") == "vex_skeleton":
            fn_type = comp.get("form_node", {}).get("type", "")
            canonical = catalog.resolve_alias(fn_type)
            floc: dict[str, Any] = {**loc, "field": "form_node.type", "node_type": fn_type}
            if not catalog.has_node_type(canonical):
                errors.append(_error(
                    "A3_NODE_TYPE",
                    f"form_node type '{fn_type}' not found",
                    floc
                ))

    for pi, step in enumerate(recipe.get("postprocess", [])):
        ntype = step.get("type", "")
        canonical = catalog.resolve_alias(ntype)
        ploc: dict[str, Any] = {"postprocess_index": pi, "node_type": ntype}
        if not catalog.has_node_type(canonical):
            errors.append(_error("A3_NODE_TYPE", f"postprocess type '{ntype}' not found", ploc))

    return errors


# ═══════════════════════════════════════════════════════════════
#  A4 — VEX Lint (heuristic, not a compiler)
# ═══════════════════════════════════════════════════════════════

_VEX_BLOCKING_PATTERNS = [
    (
        "A4_VEX_PERCENT",
        re.compile(r'%(?:\w+)%'),
        "Python-style string formatting '%...%' is not valid VEX. Use chf('name') with plain string.",
    ),
    (
        "A4_VEX_POLY",
        re.compile(r'addprim\s*\(\s*(?:\w+\s*,\s*)?\s*"poly"\s*\)'),
        "Manually creating poly prim in VEX is forbidden. Emit skeletons (polylines) only; form_node (Sweep/PolyExtrude) closes the geometry.",
    ),
    (
        "A4_VEX_FUNCTION",
        re.compile(r'^\s*(?:void|int\[\]|float\[\]|vector\[\]|string\[\]|matrix)\s+\w+\s*\(', re.MULTILINE),
        "Function definitions (including 'void xxx()') are not supported in VEX wrangle snippets. Causes 'unexpected identifier' compiler error. Use inline code blocks { ... } instead of functions.",
    ),
]

_VEX_WARNING_PATTERNS = [
    (
        "A4_VEX_NO_DETAIL_WARNING",
        re.compile(r'addpoint\b'),
        "Code contains addpoint() but no '// Run Over: Detail' marker. If this runs in Point mode, geometry explodes by N².",
    ),
]


def _validate_a4_vex_lint(recipe: dict) -> list[dict]:
    errors: list[dict] = []

    for i, comp in enumerate(recipe.get("components", [])):
        cid = comp.get("id", f"@index_{i}")
        loc: dict[str, Any] = {"component_index": i, "component_id": cid}

        if comp.get("backend") != "vex_skeleton":
            continue
        code = comp.get("code", "")
        if not code:
            continue

        for code_id, pattern, message in _VEX_BLOCKING_PATTERNS:
            m = pattern.search(code)
            if m:
                lineno = code[:m.start()].count("\n") + 1
                errors.append(_error(code_id, f"Line {lineno}: {message}", {
                    **loc, "line": lineno, "match": m.group()
                }))

        for code_id, pattern, message in _VEX_WARNING_PATTERNS:
            m = pattern.search(code)
            if m:
                if "Run Over: Detail" not in code and "run over: detail" not in code.lower():
                    lineno = code[:m.start()].count("\n") + 1
                    errors.append(_error(code_id, f"Line {lineno}: {message}", {
                        **loc, "line": lineno
                    }))

    return errors


# VEX ch() reference extraction for A4_VEX_UNDEF_PARAM
_VEX_CH_RE = re.compile(r'\b(ch[fi]\s*\(\s*"([^"]+)"\s*\))')


def _validate_a4_vex_refs(recipe: dict, declared_params: set[str]) -> list[dict]:
    """Check every ch()/chf()/chi() ref in VEX code references a declared param."""
    errors: list[dict] = []
    for i, comp in enumerate(recipe.get("components", [])):
        cid = comp.get("id", f"@index_{i}")
        if comp.get("backend") != "vex_skeleton":
            continue
        code = comp.get("code", "")
        reads = set(comp.get("reads", []))
        for m in _VEX_CH_RE.finditer(code):
            refname = m.group(2)
            if refname in declared_params:
                continue
            if refname in reads:
                continue
            lineno = code[:m.start()].count("\n") + 1
            errors.append(_error(
                "A4_VEX_UNDEF_PARAM",
                f"VEX ch() ref '{refname}' (line {lineno}) not in declared params or component reads",
                {"component_id": cid, "line": lineno, "ref": refname}
            ))
    return errors


# ═══════════════════════════════════════════════════════════════
#  A5 — Construction Axis Consistency
# ═══════════════════════════════════════════════════════════════

def _validate_a5_construction_axis(recipe: dict) -> list[dict]:
    """Validate construction_axis → anchor.orient → expected_axis consistency.

    Pure math — no Houdini call. Rotates construction_axis by anchor orient
    and checks the result matches expected_axis within tolerance.
    """
    errors: list[dict] = []
    asserts = recipe.get("orientation_asserts", [])
    if not asserts:
        return errors

    # Build component map for anchor lookup
    comps_map: dict[str, dict] = {}
    anchors_map: dict[str, dict] = {}
    for comp in recipe.get("components", []):
        cid = comp.get("id", "")
        if cid:
            comps_map[cid] = comp
        for ai, anc in enumerate(comp.get("anchors", [])):
            ac_id = anc.get("component_id", f"{cid}_anchor_{ai}")
            anchors_map[ac_id] = anc

    for a in asserts:
        cid = a.get("component_id", "")
        caxis_str = (a.get("construction_axis") or "").upper()
        if not caxis_str or caxis_str not in LOCAL_AXIS_VECTORS:
            continue  # no construction_axis → PCA path, skip

        local_vec = LOCAL_AXIS_VECTORS[caxis_str]

        # Direct-merge components: orient = identity
        orient = (0.0, 0.0, 0.0, 1.0)

        if cid in anchors_map:
            anc = anchors_map[cid]
            orient = anc.get("orient", (0.0, 0.0, 0.0, 1.0))
        elif cid in comps_map and comps_map[cid].get("anchors"):
            anc0 = comps_map[cid]["anchors"][0]
            orient = anc0.get("orient", (0.0, 0.0, 0.0, 1.0))

        # Rotate construction_axis by anchor orient → world axis
        world_vec = _rotate_vector_by_quaternion(local_vec, orient)

        # Compare with expected_axis
        exp_str = (a.get("expected_axis") or "").upper()
        if exp_str not in LOCAL_AXIS_VECTORS:
            continue
        exp_vec = LOCAL_AXIS_VECTORS[exp_str]

        angle = _angle_between(world_vec, exp_vec)
        tol = a.get("tolerance_deg", 15)
        if angle > tol:
            errors.append(_error(
                "A5_CONSTRUCTION",
                f"construction_axis {caxis_str} rotated by orient {orient} "
                f"projects to world axis {_vec_label(world_vec)} "
                f"({angle:.1f}° from expected {exp_str}, tolerance {tol}°)",
                {"component_id": cid, "angle_deg": round(angle, 1)}
            ))
    return errors


def _rotate_vector_by_quaternion(v, q):
    """Rotate vector v by quaternion q = (x,y,z,w). Pure math."""
    qx, qy, qz, qw = q
    vx, vy, vz = v
    t = (2 * (qy * vz - qz * vy),
         2 * (qz * vx - qx * vz),
         2 * (qx * vy - qy * vx))
    return (vx + qw * t[0] + (qy * t[2] - qz * t[1]),
            vy + qw * t[1] + (qz * t[0] - qx * t[2]),
            vz + qw * t[2] + (qx * t[1] - qy * t[0]))


def _angle_between(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    ma = math.sqrt(sum(x * x for x in a))
    mb = math.sqrt(sum(x * x for x in b))
    if ma < 1e-10 or mb < 1e-10:
        return 0
    dot = max(-1, min(1, dot / (ma * mb)))
    return math.degrees(math.acos(dot))


def _vec_label(v):
    for label, vec in LOCAL_AXIS_VECTORS.items():
        if all(abs(a - b) < 0.001 for a, b in zip(v, vec)):
            return label
    return f"[{v[0]:.2f},{v[1]:.2f},{v[2]:.2f}]"


# ═══════════════════════════════════════════════════════════════
#  A6 — Param Dependency Graph Validation
# ═══════════════════════════════════════════════════════════════

def _validate_a6_dependency_graph(recipe: dict) -> tuple[list[dict], dict | None]:
    """Validate the param dependency graph.

    Returns (errors, dependency_graph).
    dependency_graph: {param_name: {"depends_on": [...], "kind": "primary"|"derived"|"constrained"}}
    """
    from edini.exprs import extract_refs

    errors: list[dict] = []
    params = recipe.get("params", {})
    if not params:
        return errors, None

    graph: dict[str, dict] = {}
    for pname, pspec in params.items():
        kind = pspec.get("kind", "primary")
        deps: list[str] = []
        if kind == "derived":
            from_expr = pspec.get("from", "")
            deps = extract_refs(from_expr)
        elif kind == "constrained":
            for c in pspec.get("constraints", []):
                check_expr = c.get("check", "")
                if check_expr:
                    deps.extend(extract_refs(check_expr))
        graph[pname] = {"depends_on": list(set(deps)), "kind": kind}

    # ── Detect cycles (Kahn's algorithm) ──
    in_degree = {k: len(v["depends_on"]) for k, v in graph.items()}
    queue = [k for k, d in in_degree.items() if d == 0]
    sorted_nodes: list[str] = []
    adjacency: dict[str, list[str]] = {k: [] for k in graph}
    for k, v in graph.items():
        for dep in v["depends_on"]:
            if dep in adjacency:
                adjacency[dep].append(k)

    while queue:
        node = queue.pop(0)
        sorted_nodes.append(node)
        for neighbor in adjacency.get(node, []):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(sorted_nodes) != len(graph):
        cycle_nodes = [k for k in graph if in_degree[k] > 0]
        errors.append(_error(
            "A6_DAG_CYCLE",
            f"Cycle detected involving: {', '.join(sorted(cycle_nodes))}",
            {"cycle_nodes": cycle_nodes}
        ))

    # ── Detect dangling refs ──
    for pname, info in graph.items():
        for dep in info["depends_on"]:
            if dep not in graph:
                errors.append(_error(
                    "A6_DAG_DANGLE",
                    f"Param '{pname}' references undeclared param '{dep}'",
                    {"param": pname, "missing_ref": dep}
                ))

    # ── Detect orphan primaries ──
    all_consumer_refs: set[str] = set()
    for info in graph.values():
        all_consumer_refs.update(info["depends_on"])
    for comp in recipe.get("components", []):
        all_consumer_refs.update(comp.get("reads", []))

    for pname, info in graph.items():
        if info["kind"] == "primary" and pname not in all_consumer_refs:
            errors.append(_error(
                "A6_DAG_ORPHAN_WARNING",
                f"Primary param '{pname}' is not consumed by any component or derived param. "
                f"It will have no effect on the asset.",
                {"param": pname}
            ))

    return errors, graph


# ═══════════════════════════════════════════════════════════════
#  A7 — Backend Appropriateness (Heuristic)
# ═══════════════════════════════════════════════════════════════

# Patterns in Python code that indicate the wrong backend was chosen
_TUBE_PATTERNS = [
    # math.cos/math.sin in a loop with createPoint/createPolygon → tube/cylinder code
    # that should use vex_skeleton or native_chain
    re.compile(r'for\s+\w+\s+in\s+range.*?math\.(?:cos|sin)', re.DOTALL),
]

_SIMPLE_SOLID_PATTERNS = [
    # for loop creating quads via createPolygon + createPoint pattern
    # → simple geometric shape that should use native_chain template
    re.compile(r'createPolygon\s*\(\s*\)\s*;', re.DOTALL),
]

_LOOP_GEOMETRY_PATTERNS = [
    # for i in range(N) creating geometry inside → likely repeated part
    # that should use CTP
    re.compile(r'for\s+\w+\s+in\s+range\s*\([^)]+\)\s*:.*?(?:createPolygon|createPoint|addVertex)', re.DOTALL),
]

# Geometry type hints from component_id naming conventions
_TUBE_COMPONENT_NAMES = re.compile(r'(tube|fork|handlebar|stem|seatpost|cable|pipe|bar|rail|beam)', re.IGNORECASE)
_SIMPLE_COMPONENT_NAMES = re.compile(r'(hub|pedal|brake|crank|cassette|chainring|gear|disc|cylinder|box|spoke)', re.IGNORECASE)


def _validate_a7_backend_appropriateness(recipe: dict) -> list[dict]:
    """Heuristic check: detect Python components that should use vex_skeleton or native_chain.

    This is NOT a hard compiler check — it is a heuristic. But it catches the
    most common violation: building tubes/hubs/bicycle frames entirely in Python.
    """
    errors: list[dict] = []

    total_python = 0
    total_components = 0

    for i, comp in enumerate(recipe.get("components", [])):
        cid = comp.get("id", f"@index_{i}")
        backend = comp.get("backend", "python")
        code = comp.get("code", "")
        loc: dict[str, Any] = {"component_index": i, "component_id": cid, "backend": backend}
        total_components += 1

        if backend != "python" or not code:
            continue

        total_python += 1

        # ── Check 1: Component name suggests tube → should be vex_skeleton ──
        if _TUBE_COMPONENT_NAMES.search(cid):
            errors.append(_error(
                "A7_BACKEND_WARNING",
                f"Component '{cid}' name suggests tube/pipe/bar geometry. "
                f"Tube geometry MUST use vex_skeleton, not python. "
                f"See component-building skill: Backend 红线.",
                {**loc, "hint": "Use vex_skeleton backend for this component"}
            ))

        # ── Check 2: Component name suggests simple solid → should be native_chain ──
        if _SIMPLE_COMPONENT_NAMES.search(cid):
            errors.append(_error(
                "A7_BACKEND_WARNING",
                f"Component '{cid}' name suggests simple geometric shape (hub/brake/pedal/etc). "
                f"Simple geometry MUST use native_chain templates, not python. "
                f"See prebuilt-templates.md for ready-to-use templates.",
                {**loc, "hint": "Use native_chain backend with a prebuilt template for this component"}
            ))

        # ── Check 3: Code contains math.cos/sin in a loop → tube-like generation ──
        for pattern in _TUBE_PATTERNS:
            if pattern.search(code):
                errors.append(_error(
                    "A7_BACKEND_WARNING",
                    f"Component '{cid}' code contains math.cos/math.sin in a loop — "
                    f"likely generating tube/cylinder geometry by hand. "
                    f"Tube/path geometry MUST use vex_skeleton + sweep::2.0. "
                    f"Simple cylinders/hubs MUST use native_chain (tube SOP template).",
                    {**loc, "hint": "Replace Python loop with vex_skeleton (tube) or native_chain template (hub/cylinder)"}
                ))

        # ── Check 4: Code has for-loop generating geometry → repeated part ──
        for pattern in _LOOP_GEOMETRY_PATTERNS:
            if pattern.search(code):
                errors.append(_error(
                    "A7_BACKEND_WARNING",
                    f"Component '{cid}' code contains a loop that generates geometry — "
                    f"likely a repeated part that should use CTP (Copy-to-Points). "
                    f"Repeated geometry ≥2 copies MUST use native_chain template + CTP anchors, "
                    f"not Python for-loops.",
                    {**loc, "hint": "Use native_chain template + CTP anchors instead of for-loop"}
                ))

    # ── Global Python gate: >20% python components → warning ──
    if total_components > 0 and total_python / total_components > 0.2:
        errors.append(_error(
            "A7_PYTHON_GATE_WARNING",
            f"{total_python}/{total_components} components ({total_python/total_components:.0%}) use python backend. "
            f"The iron law allows python for at most 20% of components (organic surfaces only). "
            f"Review: can any python components be converted to vex_skeleton (tubes) or native_chain (simple shapes)?",
            {"python_count": total_python, "total_count": total_components,
             "python_ratio": round(total_python / total_components, 2)}
        ))

    return errors


# ═══════════════════════════════════════════════════════════════
#  A8 — Mandatory construction_axis on orientation_asserts
# ═══════════════════════════════════════════════════════════════

# Decision 3 (single-path design): PCA estimation is disabled because it
# misclassifies elongated cylinders (the hub 90° bug). Every orientation_assert
# must therefore declare its deterministic construction_axis. An empty asserts
# array is an explicit opt-out (decision 6).
VALID_CONSTRUCTION_AXES = {"X", "Y", "Z", "-X", "-Y", "-Z"}


def _validate_a8_construction_axis(recipe: dict) -> list[dict]:
    """A8: every non-empty orientation_assert must carry a valid construction_axis.

    Rationale: with the PCA fallback branch removed (Stage 5), there is no
    estimation path left — a component without a baked edini_world_axis fails
    orientation verification outright. construction_axis is what makes the
    builder bake that axis deterministically. Allowing asserts without it
    would let an asset reach commit only to be refused at G3 with a confusing
    'edini_world_axis missing' error; A8 surfaces the real fix (declare the
    axis) at validation time, before any cook.
    """
    errors: list[dict] = []
    asserts = recipe.get("orientation_asserts") or []
    if not asserts:
        # Empty array (or absent) = explicit opt-out (decision 6). No check.
        return errors

    for i, a in enumerate(asserts):
        if not isinstance(a, dict):
            continue  # A1 schema already flags malformed entries
        loc: dict[str, Any] = {
            "orientation_assert_index": i,
            "component_id": a.get("component_id", "?"),
        }
        caxis = a.get("construction_axis")
        if caxis is None:
            errors.append(_error(
                "A8_MISSING_CONSTRUCTION_AXIS",
                f"orientation_asserts[{i}] for '{a.get('component_id', '?')}' "
                f"has no construction_axis. Declare one of "
                f"{sorted(VALID_CONSTRUCTION_AXES)} — the local-space axis the "
                f"component is generated around. PCA estimation is disabled "
                f"(it misclassifies elongated cylinders, the hub 90° bug), so "
                f"the axis must be declared, not estimated. To skip orientation "
                f"verification entirely, pass an empty orientation_asserts "
                f"array (decision 6 explicit opt-out).",
                loc,
            ))
        elif not isinstance(caxis, str) or caxis.upper() not in VALID_CONSTRUCTION_AXES:
            errors.append(_error(
                "A8_BAD_CONSTRUCTION_AXIS",
                f"orientation_asserts[{i}].construction_axis {caxis!r} must be "
                f"one of {sorted(VALID_CONSTRUCTION_AXES)}.",
                loc,
            ))
    return errors


# ═══════════════════════════════════════════════════════════════
#  A9 — Hardcoded size guard
# ═══════════════════════════════════════════════════════════════

# Decision 13: a size variable assigned a numeric literal in component code,
# when that variable is NOT declared in recipe.params and NOT in the
# component's reads list, is a hardcoded dimension — the opposite of the
# parametric system. Catch the canonical antipattern `wheelbase = 1.0` that
# drove the road_bike session's "change a param, nothing moves" failures.
#
# Heuristic (Pareto, not exhaustive): only flags assignments whose LHS name
# contains a size hint. `i = 0` loop counters pass through unmolested.
SIZE_VAR_PATTERN = re.compile(
    r'^\s*(\w+)\s*=\s*([-+]?\d*\.?\d+)\s*(?:#|$)',
    re.MULTILINE,
)
SIZE_NAME_HINTS = (
    "wheelbase", "wheel_r", "width", "height", "length", "radius",
    "bb_", "seat_", "stem_", "fork_", "crank", "tire", "spacing",
)


def _validate_a9_hardcoded_size(recipe: dict) -> list[dict]:
    """A9: reject hardcoded dimension literals in component code (BLOCKING).

    A variable named like a size (`wheelbase`, `radius`, `bb_height`, ...)
    assigned a bare numeric literal, where the variable is neither a declared
    recipe param nor listed in the component's `reads`, is a hardcoded
    dimension. The fix is to move it into recipe.params (so it becomes a real
    spare parm with cross-component linkage) or add it to the component's
    reads list (if it's a local alias of a param the component reads via
    hou.ch).

    This is BLOCKING because hardcoded sizes are the root cause of "change a
    param, nothing moves" — the agent edits the asset-level parm but the
    geometry was baked from a literal. The parameter system (primary/derived/
    constrained) exists precisely to make every dimension driven by a channel.
    """
    errors: list[dict] = []
    declared_params = set((recipe.get("params") or {}).keys())

    for i, comp in enumerate(recipe.get("components", [])):
        if not isinstance(comp, dict):
            continue
        cid = comp.get("id", f"@index_{i}")
        backend = comp.get("backend", "python")
        # native_chain has no free-form code (geometry comes from SOP parms);
        # vex_skeleton code is VEX, not Python — assignment syntax differs and
        # sizes there are typically ch() refs already (A4 covers undef refs).
        if backend == "native_chain":
            continue
        code = comp.get("code", "") or ""
        if not isinstance(code, str) or not code:
            continue
        reads = set(comp.get("reads") or [])
        allowed = declared_params | reads
        loc: dict[str, Any] = {"component_index": i, "component_id": cid}

        for m in SIZE_VAR_PATTERN.finditer(code):
            varname, literal = m.group(1), m.group(2)
            if not any(h in varname.lower() for h in SIZE_NAME_HINTS):
                continue  # not a size-named variable; leave alone
            if varname in allowed:
                continue  # declared param or explicit read — legit
            lineno = code[:m.start()].count("\n") + 1
            errors.append(_error(
                "A9_HARDCODED_SIZE",
                f"component '{cid}' assigns {varname} = {literal} as a hardcoded "
                f"literal (line {lineno}). Dimensions must live in recipe.params "
                f"and be read via hou.ch('../{varname}') so editing the asset "
                f"parm actually re-cooks the geometry. Either add "
                f"'{varname}' to recipe.params (e.g. "
                f'"{varname}": {{"default": {literal}}}) or to this '
                f"component's reads list if it's a local alias.",
                {**loc, "line": lineno, "variable": varname, "literal": literal},
            ))
    return errors


# ═══════════════════════════════════════════════════════════════
#  Main entry point
# ═══════════════════════════════════════════════════════════════

def validate_recipe(
    recipe: dict,
    catalog_path: str | None = None,
) -> dict[str, Any]:
    """Phase A: validate a procedural asset recipe without any Houdini operations.

    Returns a ValidationReport dict with:
        passed: bool — True if all BLOCKING checks passed
        stages: dict — per-stage {passed, error_count, warning_count}
        errors: list — all BLOCKING validation errors
        warnings: list — all WARNING-level items
        dependency_graph: dict | None — param DAG (if params declared)
        component_manifest: list — {component_id, backend} for every component
    """
    catalog = _get_catalog(catalog_path) if catalog_path else None

    all_errors: list[dict] = []

    # Run all stages, collecting errors
    all_errors.extend(_validate_a1_schema(recipe))

    if catalog:
        all_errors.extend(_validate_a2_parm_names(recipe, catalog))
        all_errors.extend(_validate_a3_node_types(recipe, catalog))

    all_errors.extend(_validate_a4_vex_lint(recipe))

    declared_params = set((recipe.get("params") or {}).keys())
    all_errors.extend(_validate_a4_vex_refs(recipe, declared_params))

    all_errors.extend(_validate_a5_construction_axis(recipe))

    dep_errors, dep_graph = _validate_a6_dependency_graph(recipe)
    all_errors.extend(dep_errors)

    all_errors.extend(_validate_a7_backend_appropriateness(recipe))

    all_errors.extend(_validate_a8_construction_axis(recipe))
    all_errors.extend(_validate_a9_hardcoded_size(recipe))

    # ── Summarize ──
    blocking = [e for e in all_errors if e["severity"] == "BLOCKING"]
    warnings = [e for e in all_errors if e["severity"] == "WARNING"]

    stage_summary: dict[str, dict] = {}
    for err in all_errors:
        stage = err["stage"]
        entry = stage_summary.setdefault(stage, {"error_count": 0, "warning_count": 0})
        if err["severity"] == "BLOCKING":
            entry["error_count"] += 1
        else:
            entry["warning_count"] += 1
    for _stage, counts in stage_summary.items():
        counts["passed"] = counts["error_count"] == 0

    # ── Build component manifest ──
    manifest = []
    for comp in recipe.get("components", []):
        manifest.append({
            "component_id": comp.get("id"),
            "backend": comp.get("backend", "python"),
            "has_anchors": bool(comp.get("anchors")),
            "exposes": comp.get("exposes", []),
        })

    return {
        "passed": len(blocking) == 0,
        "stages": stage_summary,
        "errors": blocking,
        "warnings": warnings,
        "error_count": len(blocking),
        "warning_count": len(warnings),
        "dependency_graph": dep_graph,
        "component_manifest": manifest,
    }
