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
    # Graph validation only if structure is sound (avoid noisy cascades).
    if not any(e["code"].startswith("SKELETON_POINT_BAD") or
               e["code"] == "SKELETON_NOT_OBJECT"
               for e in errors):
        errors.extend(_validate_skeleton_graph(asset))

    # components are milestone 2; warn if absent but don't fail.
    if "components" not in asset:
        warnings.append({"code": "NO_COMPONENTS",
                         "message": "asset has no 'components' (milestone 2)"})

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
