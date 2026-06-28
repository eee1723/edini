"""Asset model — the declarative description of a procedural asset.

An *asset* is the design intent for a multi-component procedural object (a
bicycle, a chair, a pipe assembly). It is NOT a captured network snapshot
(see ``recipe_library`` for that) — it is a hand/LLM-authored JSON that
describes WHAT to build before any geometry exists:

    {
      "asset_schema_version": 1,
      "id": "bicycle",
      "params":   { <param_name>: {kind, default, min, max} },
      "skeleton": { <point_name>: {expr: [xstr, ystr, zstr]} },
      "components": [ ... ]   # milestone 2; left empty for now
    }

Three properties make this the single source of truth:

1. **Params (the library)** — every number the asset uses lives here. The
   rule (enforced downstream) is: no component may hardcode a dimension; it
   must read from this library. Parameters are added incrementally as the
   asset is authored (``kind: primary`` for user-facing, ``derived`` for
   computed-from-others).

2. **Skeleton (the linkage DAG)** — named 3D points whose coordinates are
   expressions over params and other points. Components attach to these
   points, so changing one param moves everything that depends on it. This
   is the cure for the "baked coordinates" defect (D3).

3. **Components** — filled in milestone 2; each attaches to a skeleton
   point and reads its size from the param library.

This module is pure-data: schema validation, param/skeleton validation, and
skeleton resolution. No ``hou`` dependency — it runs anywhere, including in
the ``validate_asset`` tool before any Houdini node is touched (the
"validation shift-left" principle).
"""
from __future__ import annotations

import os
from typing import Any

from edini.exprs import ExprError, evaluate
from edini.skeleton_resolver import (
    SkeletonCycleError,
    SkeletonError,
    evaluate_skeleton,
    point_dependencies,
    topo_order,
)

ASSET_SCHEMA_VERSION = 1

# ── (De)serialization — reuse recipe_library's atomic I/O ───────────


def _atomic_write_json(path: str, data: Any) -> None:
    """Atomic JSON write (write .tmp, os.replace). Mirrors recipe_library."""
    import json
    tmp = path + ".tmp"
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    os.replace(tmp, path)


def _safe_read_json(path: str) -> Any:
    """Read JSON, returning None on missing/corrupt (mirrors recipe_library)."""
    import json
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def load_asset(path: str) -> dict | None:
    """Load an asset JSON file. Returns None if missing/corrupt."""
    data = _safe_read_json(path)
    if not isinstance(data, dict):
        return None
    return data


def save_asset(path: str, asset: dict) -> None:
    """Write an asset JSON atomically."""
    _atomic_write_json(path, asset)


# ── Validation ─────────────────────────────────────────────────────


def _err(code: str, message: str, location: dict | None = None) -> dict:
    """Standardized error record (mirrors the A-station convention)."""
    e = {"code": code, "message": message}
    if location:
        e["location"] = location
    return e


def _validate_params(asset: dict) -> list[dict]:
    """Validate the params library: structure + kinds + numeric defaults."""
    errors: list[dict] = []
    params = asset.get("params", {})
    if params is None:
        return errors
    if not isinstance(params, dict):
        return [_err("PARAMS_NOT_OBJECT", "params must be an object")]
    for pname, pspec in params.items():
        if not isinstance(pspec, dict):
            errors.append(_err("PARAM_SPEC_NOT_OBJECT",
                               f"param {pname!r} spec must be an object",
                               {"param": pname}))
            continue
        kind = pspec.get("kind", "primary")
        if kind not in ("primary", "derived", "constrained"):
            errors.append(_err("PARAM_BAD_KIND",
                               f"param {pname!r} kind {kind!r} must be "
                               f"primary/derived/constrained",
                               {"param": pname}))
        if "default" not in pspec and kind != "derived":
            errors.append(_err("PARAM_NO_DEFAULT",
                               f"param {pname!r} (kind={kind}) needs a 'default'",
                               {"param": pname}))
        # derived params must have a 'from' expression
        if kind == "derived" and not pspec.get("from"):
            errors.append(_err("PARAM_DERIVED_NO_FROM",
                               f"derived param {pname!r} needs a 'from' expression",
                               {"param": pname}))
        if "default" in pspec:
            try:
                float(pspec["default"])
            except (TypeError, ValueError):
                errors.append(_err("PARAM_DEFAULT_NON_NUMERIC",
                                   f"param {pname!r} default must be numeric",
                                   {"param": pname}))
    return errors


def _validate_skeleton_structure(asset: dict) -> list[dict]:
    """Validate skeleton shape: each point has a 3-element expr list."""
    errors: list[dict] = []
    skeleton = asset.get("skeleton", {})
    if skeleton is None:
        return errors
    if not isinstance(skeleton, dict):
        return [_err("SKELETON_NOT_OBJECT", "skeleton must be an object")]
    for pname, spec in skeleton.items():
        exprs = spec.get("expr") if isinstance(spec, dict) else spec
        if not isinstance(exprs, (list, tuple)) or len(exprs) != 3:
            errors.append(_err("SKELETON_POINT_BAD_EXPR",
                               f"skeleton point {pname!r} must have an 'expr' "
                               f"list of exactly 3 elements (x, y, z)",
                               {"point": pname}))
            continue
        for i, e in enumerate(exprs):
            if isinstance(e, bool) or (
                not isinstance(e, str) and not isinstance(e, (int, float))
            ):
                errors.append(_err("SKELETON_AXIS_BAD_TYPE",
                                   f"skeleton {pname!r}[{i}] must be a number "
                                   f"or expression string",
                                   {"point": pname, "axis": i}))
    return errors


def _validate_skeleton_graph(asset: dict) -> list[dict]:
    """Validate the skeleton DAG: cycles, dangling refs, expression syntax.

    Runs only if the skeleton passed structural validation. Catches the
    expensive failure modes (cycle, typo'd param/point name) before any
    geometry is built.
    """
    errors: list[dict] = []
    skeleton = asset.get("skeleton", {})
    params = asset.get("params", {}) or {}
    param_names = set(params.keys())
    point_names = set(skeleton.keys())
    if not isinstance(skeleton, dict) or not skeleton:
        return errors

    # 1. Cycle detection (topological sort).
    try:
        topo_order(skeleton)
    except SkeletonCycleError as e:
        errors.append(_err("SKELETON_CYCLE", str(e)))
        # A cycle makes further point-ref analysis unreliable, but we still
        # report dangling param refs below since those are independent.

    # 2. Dangling references: every referenced name must be a known point or
    #    a declared parameter. (Functions/constants are excluded by extract_refs.)
    from edini.exprs import extract_refs
    from edini.skeleton_resolver import _point_expr_strings
    for pname, spec in skeleton.items():
        for estr in _point_expr_strings(spec):
            for ref in extract_refs(estr):
                if ref not in point_names and ref not in param_names:
                    errors.append(_err(
                        "SKELETON_DANGLING_REF",
                        f"skeleton {pname!r} references unknown name {ref!r} "
                        f"(not a point, not a parameter)",
                        {"point": pname, "ref": ref}))

    # 3. Expression pre-check: confirm every axis expression parses and (for
    #    pure-param expressions, no point refs) evaluates against the param
    #    defaults. Point-referencing expressions can't be evaluated in isolation
    #    here (need the full topo resolution), so we just ast-parse them.
    import ast
    # Names that count as "known" for the dangling-ref check above already
    # cover points + all param names (primary AND derived). For the optional
    # pre-evaluation we can only seed concrete values for primary params;
    # derived params are resolved at build time. So a pure-param expression
    # that references a derived param can't be pre-evaluated here — skip it
    # (its correctness is confirmed by resolve_skeleton, not by this lint).
    primary_defaults = {n: float(s.get("default", 0.0))
                        for n, s in params.items()
                        if isinstance(s, dict)
                        and s.get("kind", "primary") != "derived"
                        and _is_numeric(s.get("default"))}
    deps = point_dependencies(skeleton)
    for pname, spec in skeleton.items():
        exprs = spec.get("expr") if isinstance(spec, dict) else spec
        if not isinstance(exprs, (list, tuple)):
            continue
        has_point_ref = bool(deps.get(pname))
        for axi, axexpr in enumerate(exprs):
            if not isinstance(axexpr, str):
                continue
            # Syntax check (always).
            try:
                ast.parse(axexpr.strip(), mode="eval")
            except SyntaxError as exc:
                errors.append(_err(
                    "SKELETON_EXPR_SYNTAX",
                    f"skeleton {pname!r}[{axi}] syntax error: {exc.msg}",
                    {"point": pname, "axis": axi}))
                continue
            # Eval check only when the axis references NO points AND NO derived
            # params (pure primary-param/constant). Otherwise it needs resolved
            # values and is validated by the full resolve at build time.
            refs = set(extract_refs(axexpr))
            refs_derived = refs & {n for n, s in params.items()
                                   if isinstance(s, dict)
                                   and s.get("kind") == "derived"}
            if not has_point_ref and not refs_derived:
                try:
                    evaluate(axexpr, primary_defaults)
                except ExprError as exc:
                    errors.append(_err(
                        "SKELETON_EXPR_EVAL",
                        f"skeleton {pname!r}[{axi}] evaluation error: {exc}",
                        {"point": pname, "axis": axi}))
    return errors


def _is_numeric(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


# ── Component validation (milestone 2) ──────────────────────────────
#
# A component attaches to a skeleton point BY NAME (not a private position
# expression) and reads its dimensions from the param library. This is the
# milestone-2 contract that replaces the old anchor/position_expr mechanism:
# components no longer carry their own coordinates, so two components can never
# disagree about where a shared feature sits.

_VALID_BACKENDS = ("native_chain", "vex_skeleton", "python")
_DEFAULT_BACKEND = "native_chain"


def _validate_orient(orient: Any, cid: str, loc: dict | None) -> list[dict]:
    """Validate an orient field: [rx, ry, rz] Euler angles in DEGREES.

    Optional everywhere it appears (attach.orient, instance.orient). When
    present it MUST be a 3-element list of numbers — otherwise the builder
    would silently drop the rotation (the chair real-world test caught this:
    orient was ignored with no error). Surface a clear code instead.
    """
    errs: list[dict] = []
    if isinstance(orient, (list, tuple)):
        if len(orient) != 3:
            errs.append(_err(
                "COMPONENT_BAD_ORIENT",
                f"component {cid!r} orient must be 3 numbers [rx,ry,rz] degrees, "
                f"got {len(orient)}", loc))
        elif not all(_is_numeric(a) for a in orient):
            errs.append(_err(
                "COMPONENT_BAD_ORIENT",
                f"component {cid!r} orient must be 3 numbers, got non-numeric "
                f"value in {list(orient)!r}", loc))
    else:
        errs.append(_err(
            "COMPONENT_BAD_ORIENT",
            f"component {cid!r} orient must be a list of 3 numbers [rx,ry,rz] "
            f"degrees, got {type(orient).__name__}", loc))
    return errs


def _validate_components(asset: dict) -> list[dict]:
    """Validate the ``components`` list: ids, backends, node shapes, attach
    references, and param references. Assumes skeleton + params already passed
    structural validation (the caller gates this)."""
    errors: list[dict] = []
    components = asset.get("components")
    if not isinstance(components, list):
        return errors  # malformed-list case handled by the caller

    skeleton = asset.get("skeleton", {}) or {}
    point_names = set(skeleton.keys()) if isinstance(skeleton, dict) else set()
    params = asset.get("params", {}) or {}
    param_names = set(params.keys()) if isinstance(params, dict) else set()

    seen_ids: set[str] = set()
    for comp in components:
        if not isinstance(comp, dict):
            errors.append(_err("COMPONENT_NOT_OBJECT",
                               "each component must be an object"))
            continue

        # ── id ──
        cid = comp.get("id")
        if not cid or not isinstance(cid, str):
            errors.append(_err("COMPONENT_NO_ID",
                               "component needs a non-empty string 'id'"))
            cid = None
        elif cid in seen_ids:
            errors.append(_err("COMPONENT_DUPLICATE_ID",
                               f"duplicate component id {cid!r}",
                               {"component": cid}))
        else:
            seen_ids.add(cid)
        loc = {"component": cid} if cid else None

        # ── backend ──
        backend = comp.get("backend", _DEFAULT_BACKEND)
        if backend not in _VALID_BACKENDS:
            errors.append(_err("COMPONENT_BAD_BACKEND",
                               f"component {cid!r} backend {backend!r} must be "
                               f"one of {list(_VALID_BACKENDS)}", loc))

        # ── nodes (native_chain requires a non-empty node list) ──
        nodes = comp.get("nodes")
        if backend == "native_chain":
            if not isinstance(nodes, list) or not nodes:
                errors.append(_err("COMPONENT_NO_NODES",
                                   f"component {cid!r} (native_chain) needs a "
                                   f"non-empty 'nodes' list", loc))
            else:
                for ni, node in enumerate(nodes):
                    if not isinstance(node, dict) or not node.get("type"):
                        errors.append(_err(
                            "COMPONENT_NODE_NO_TYPE",
                            f"component {cid!r} nodes[{ni}] must have a "
                            f"non-empty 'type'", {**((loc or {})),
                                                  "node_index": ni}))

        # ── code (python backend requires a Python SOP cook body) ──
        if backend == "python":
            code = comp.get("code")
            if not isinstance(code, str) or not code.strip():
                errors.append(_err("COMPONENT_NO_CODE",
                                   f"component {cid!r} (python) needs a "
                                   f"non-empty 'code' string", loc))
            else:
                # Syntax-check the cook body so a typo surfaces here, not as
                # an opaque cook error in Houdini.
                import ast
                try:
                    ast.parse(code)
                except SyntaxError as exc:
                    errors.append(_err(
                        "COMPONENT_CODE_SYNTAX",
                        f"component {cid!r} code syntax error: {exc.msg} "
                        f"(line {exc.lineno})", loc))

        # ── placement: attach (single instance) OR instances[] (multi) ──
        # A component hangs off skeleton point(s) BY NAME. Two forms:
        #   - attach.position: one instance at one point (the simple case).
        #   - instances[]: N instances, each at its own point with its own id.
        #     The geometry is defined ONCE; each instance is a transform copy.
        # Both forms name skeleton points (never private coordinates) — this is
        # the milestone-2 contract that replaced the old anchor mechanism.
        attach = comp.get("attach")
        instances = comp.get("instances")
        has_attach = isinstance(attach, dict)
        has_instances = isinstance(instances, list)

        if has_attach and has_instances:
            errors.append(_err(
                "COMPONENT_INSTANCES_AND_ATTACH_CONFLICT",
                f"component {cid!r} has both 'attach' and 'instances' — use one "
                f"(attach for a single instance, instances[] for many)", loc))
        elif has_instances:
            # Multi-instance: validate each instance's id + point reference.
            for ii, inst in enumerate(instances):
                if not isinstance(inst, dict):
                    errors.append(_err(
                        "COMPONENT_INSTANCE_NO_ID",
                        f"component {cid!r} instances[{ii}] must be an object",
                        {**((loc or {})), "instance_index": ii}))
                    continue
                inst_id = inst.get("id")
                if not inst_id or not isinstance(inst_id, str):
                    errors.append(_err(
                        "COMPONENT_INSTANCE_NO_ID",
                        f"component {cid!r} instances[{ii}] needs a non-empty "
                        f"string 'id'", {**((loc or {})), "instance_index": ii}))
                    inst_id = None
                elif inst_id in seen_ids:
                    # instance ids are the real component_ids (they enter the
                    # merge + gates), so they must be globally unique across
                    # all components AND instances.
                    errors.append(_err(
                        "COMPONENT_INSTANCE_DUPLICATE_ID",
                        f"duplicate id {inst_id!r} (instance of {cid!r}) — every "
                        f"component/instance id must be unique",
                        {**((loc or {})), "instance_id": inst_id}))
                else:
                    seen_ids.add(inst_id)
                inst_pos = inst.get("position")
                if not inst_pos or not isinstance(inst_pos, str):
                    errors.append(_err(
                        "COMPONENT_INSTANCE_BAD_POINT",
                        f"component {cid!r} instance {inst_id!r} needs a "
                        f"'position' skeleton-point name",
                        {**((loc or {})), "instance_id": inst_id}))
                elif inst_pos not in point_names:
                    errors.append(_err(
                        "COMPONENT_INSTANCE_BAD_POINT",
                        f"component {cid!r} instance {inst_id!r} attaches to "
                        f"{inst_pos!r} which is not a declared skeleton point "
                        f"(known: {sorted(point_names)})",
                        {**((loc or {})), "instance_id": inst_id,
                         "point": inst_pos}))
        elif not has_attach:
            # Neither attach nor instances: a component must declare where it
            # lives. (An empty components list is allowed at the asset level;
            # this fires only for a present-but-placement-less component.)
            errors.append(_err("COMPONENT_NO_ATTACH",
                               f"component {cid!r} needs an 'attach' object "
                               f"(single instance) or an 'instances' list "
                               f"(multi-instance)", loc))
        else:
            # Single-instance attach.position: validate the point reference.
            position = attach.get("position")
            if not position or not isinstance(position, str):
                errors.append(_err("COMPONENT_NO_ATTACH",
                                   f"component {cid!r} attach.position must be a "
                                   f"skeleton-point name", loc))
            elif position not in point_names:
                errors.append(_err(
                    "COMPONENT_ATTACH_BAD_POINT",
                    f"component {cid!r} attaches to {position!r} which is not "
                    f"a declared skeleton point (known: {sorted(point_names)})",
                    {**((loc or {})), "point": position}))
            # attach.orient (optional): Euler-angle rotation [rx,ry,rz] degrees.
            # Validate shape so a typo doesn't silently disable rotation.
            if "orient" in attach:
                errors.extend(_validate_orient(attach["orient"], cid, loc))

        # Multi-instance orient: validated per-instance alongside the point.
        if has_instances and isinstance(instances, list):
            for ii, inst in enumerate(instances):
                if isinstance(inst, dict) and "orient" in inst:
                    inst_loc = {**((loc or {})), "instance_index": ii}
                    inst_id_ref = inst.get("id")
                    if inst_id_ref:
                        inst_loc["instance_id"] = inst_id_ref
                    errors.extend(_validate_orient(
                        inst["orient"], cid, inst_loc))

        # ── param references: a node param value that is a STRING is treated
        # as an expression over the param library (evaluated at build time by
        # exprs.evaluate). Every name it references must be a declared param —
        # otherwise the build fails with an opaque ExprError. This closes a hole
        # the old design never checked (reads were never validated). ──
        if isinstance(nodes, list):
            from edini.exprs import extract_refs
            for ni, node in enumerate(nodes):
                if not isinstance(node, dict):
                    continue
                node_params = node.get("params")
                if not isinstance(node_params, dict):
                    continue
                for pname, pvalue in node_params.items():
                    refs = _param_value_refs(pvalue, extract_refs)
                    for ref in refs:
                        if ref not in param_names:
                            errors.append(_err(
                                "COMPONENT_PARAM_REF_DANGLING",
                                f"component {cid!r} nodes[{ni}].{pname} "
                                f"references unknown param {ref!r}",
                                {**((loc or {})), "node_index": ni,
                                 "param": pname, "ref": ref}))
    return errors


def _param_value_refs(value: Any, extract_refs) -> list[str]:
    """Extract param references from a node param value.

    A numeric value contributes none. A string value is an expression → its
    refs. A list/tuple value (e.g. a vector ``["a", 0.04, "b"]``) contributes
    the union of refs from each element — this is how a box ``size`` of
    ``["top_size", "top_thickness", "top_size"]`` resolves.
    """
    if isinstance(value, bool) or isinstance(value, (int, float)):
        return []
    if isinstance(value, str):
        return extract_refs(value)
    if isinstance(value, (list, tuple)):
        refs: list[str] = []
        for el in value:
            refs.extend(_param_value_refs(el, extract_refs))
        return refs
    return []


def validate_asset(asset: dict) -> dict:
    """Validate a complete asset description.

    Returns ``{success, errors, warnings, summary}``. ``success`` is True
    only when ``errors`` is empty. Pure data — no Houdini, no file writes.
    """
    errors: list[dict] = []
    warnings: list[dict] = []

    if not isinstance(asset, dict):
        return {"success": False, "errors": [_err("ASSET_NOT_OBJECT",
                "asset must be a JSON object")], "warnings": [], "summary": {}}

    # Top-level schema.
    if asset.get("asset_schema_version") != ASSET_SCHEMA_VERSION:
        errors.append(_err("ASSET_SCHEMA_VERSION",
                           f"asset_schema_version must be {ASSET_SCHEMA_VERSION}"))
    if not asset.get("id"):
        errors.append(_err("ASSET_NO_ID", "asset needs an 'id'"))

    errors.extend(_validate_params(asset))
    errors.extend(_validate_skeleton_structure(asset))
    # Graph validation only if the params + skeleton are structurally sound
    # (avoid noisy cascades AND a crash: _validate_skeleton_graph indexes
    # params.keys() / skeleton.items(), which raises if either is non-dict).
    structural_errors = (
        "SKELETON_POINT_BAD", "SKELETON_NOT_OBJECT",
        "PARAMS_NOT_OBJECT", "PARAM_SPEC_NOT_OBJECT",
    )
    if not any(e["code"] in structural_errors for e in errors):
        errors.extend(_validate_skeleton_graph(asset))

    # components (milestone 2): validate each against the skeleton + param
    # library. An absent components list is still only a warning (an asset
    # may be a pure skeleton preview), but a present list is fully checked.
    components = asset.get("components")
    if not isinstance(components, list):
        if "components" in asset:
            errors.append(_err("COMPONENTS_NOT_LIST",
                               "components must be a list"))
        else:
            warnings.append({"code": "NO_COMPONENTS",
                             "message": "asset has no 'components' (milestone 2)"})
    else:
        # Component attach/param-ref checks depend on the skeleton + param
        # names; only run them once those layers are structurally sound.
        if not any(e["code"] in structural_errors for e in errors):
            errors.extend(_validate_components(asset))

    return {
        "success": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "summary": {
            "param_count": len(asset.get("params", {}) or {}),
            "skeleton_point_count": len(asset.get("skeleton", {}) or {}),
            "component_count": len(asset.get("components", []) or []),
        },
    }


def resolve_params(asset: dict) -> dict[str, float]:
    """Resolve every parameter to a concrete float value.

    Primary/constrained params use their ``default``. Derived params are
    evaluated in topological order against the already-resolved primaries
    and other derived params (their ``from`` expression references those).
    This closes the gap between the param library and the skeleton: the
    skeleton only ever sees concrete scalar values.

    Raises ExprError (bad expression / unknown ref) or SkeletonCycleError
    (a derived param references itself directly or transitively). Call
    validate_asset first to surface friendly errors.
    """
    params = asset.get("params", {}) or {}
    values: dict[str, float] = {}
    # Seed with non-derived params that have numeric defaults.
    for name, spec in params.items():
        if not isinstance(spec, dict):
            continue
        if spec.get("kind", "primary") != "derived" and _is_numeric(spec.get("default")):
            values[name] = float(spec["default"])

    # Resolve derived params in dependency order. A derived param's `from`
    # may reference primaries (already in `values`) or other derived params
    # (resolved earlier in the order). We loop to a fixed point: each pass
    # resolves any derived whose deps are all known, until none progress.
    derived = {n: s for n, s in params.items()
               if isinstance(s, dict) and s.get("kind") == "derived" and n not in values}
    from edini.exprs import evaluate, extract_refs
    remaining = dict(derived)
    progressed = True
    while remaining and progressed:
        progressed = False
        for name in list(remaining):
            from_expr = remaining[name].get("from", "")
            refs = set(extract_refs(from_expr))
            unresolved = refs - set(values.keys())
            if not unresolved:
                values[name] = evaluate(from_expr, values)
                del remaining[name]
                progressed = True
    if remaining:
        # Whatever is left has a cycle or a dangling ref. Distinguish them.
        all_refs = set()
        for name, spec in remaining.items():
            all_refs |= set(extract_refs(spec.get("from", "")))
        dangling = all_refs - set(params.keys())
        if dangling:
            raise ExprError(
                f"derived params reference unknown params: {sorted(dangling)}")
        raise SkeletonCycleError(
            f"cyclic dependency among derived params: {sorted(remaining)}")
    return values


def resolve_skeleton(asset: dict) -> dict[str, tuple[float, float, float]]:
    """Resolve all skeleton points to concrete coordinates.

    Resolves primary AND derived parameters first (via resolve_params), then
    evaluates the skeleton point DAG against those concrete scalars. Raises
    ExprError / SkeletonCycleError on failure — call validate_asset first.
    """
    param_values = resolve_params(asset)
    skeleton = asset.get("skeleton", {}) or {}
    return evaluate_skeleton(skeleton, param_values)
