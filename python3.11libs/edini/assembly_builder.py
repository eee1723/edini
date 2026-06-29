"""Assembly builder — the Root → Measure → Mount → Shape construction layer.

This is the heart of the **rooted-modeling** skill. Unlike the archived
declarative-asset pipeline (where every position came from a param/skeleton
expression DAG), here a leaf's placement is derived by *measuring the root's
already-cooked geometry*. So when the root changes shape, the leaves move
with it automatically — no human re-syncs coordinates. That is the whole
point of the redesign.

The four roles
--------------
- **Root**  — the foundational component, built first. Its real, cooked
  geometry is the single source of truth for everything below it. In M0 it
  is a native-SOP box (a vehicle platform, a keyboard tray, a building mass).
- **Mount** — a {position, orient, scale} derived ENTIRELY from measurements
  taken off the root (or off another already-placed leaf). Never a hardcoded
  coordinate. Position comes from e.g. ``bbox_corner``; orient comes from a
  measured direction; scale is an expression over params.
- **Shape** — a self-contained leaf asset (a wheel, a keycap, a door). Its
  *form* is independent of the root; only its *placement* is derived.
- **Leaf** — a Shape placed onto a Mount (optionally many leaves per shape).

Data flow is strictly one-way and re-entrant:

    params ──▶ Root(cook) ──▶ measure ──▶ Mounts ──▶ place Leaves

A leaf may itself become a root for the next level (bike frame → fork →
handlebar) — M3 territory; M0 supports a single root level only.

M0 scope: native-SOP shapes (box/tube/torus/sphere), bbox-based position
mounts, direction-based orient mounts, and expression-based scale/size. The
measurement primitives live in :mod:`edini.measure`; this module orchestrates.
"""
from __future__ import annotations

import math
import re
from typing import Any

try:
    import hou
except ImportError:
    # Offline / unit tests install a mock into sys.modules before import.
    hou = None  # type: ignore[assignment]

from edini.exprs import ExprError, evaluate
from edini import measure as M


# ── Validation (pure data — no Houdini, runs before any node is made) ──


class AssemblyError(ValueError):
    """Raised when an assembly description is invalid or unbuildable."""


# Native SOP shapes supported as roots/leaves, with their REAL Houdini 21 size
# parm names (verified against hython 21.0.440). NOTE: 'cylinder' is NOT a SOP
# in H21 (use 'tube'); 'torus' uses independent radx/rady parms (not a rad
# parmTuple); 'sphere' uses radx/rady/radz; 'box'/'tube' use size/rad+height.
_VALID_SHAPES = {"box", "tube", "torus", "sphere"}


def validate_assembly(assembly: dict) -> dict[str, Any]:
    """Pure-data validation of an assembly description.

    Checks schema shape, that params are numeric, that every mount references
    a known source node and a known measurement kind, that every leaf names a
    declared mount + shape, and that shape param expressions reference only
    declared params. Returns ``{success, errors, summary}``. No Houdini.
    """
    errors: list[dict] = []
    if not isinstance(assembly, dict):
        return {"success": False, "errors": [{"code": "NOT_OBJECT",
                "message": "assembly must be an object"}], "summary": {}}

    if not assembly.get("id"):
        errors.append({"code": "NO_ID", "message": "assembly needs an 'id'"})

    params = assembly.get("params", {}) or {}
    if not isinstance(params, dict):
        errors.append({"code": "PARAMS_NOT_OBJECT", "message": "params must be an object"})
        params = {}
    param_names = set(params.keys())
    # Param values: a number (fixed default) or {default, min, max}.
    for pn, pv in params.items():
        if isinstance(pv, (int, float)) and not isinstance(pv, bool):
            continue
        if isinstance(pv, dict) and isinstance(pv.get("default"), (int, float)):
            continue
        errors.append({"code": "PARAM_BAD", "message":
            f"param {pn!r} must be a number or {{default,...}}, got {pv!r}"})

    # Root is required.
    root = assembly.get("root")
    if not isinstance(root, dict):
        errors.append({"code": "NO_ROOT", "message": "assembly needs a 'root' object"})
        root = {}
    else:
        rshape = root.get("shape")
        if not isinstance(rshape, dict) or rshape.get("type") not in _VALID_SHAPES:
            errors.append({"code": "ROOT_BAD_SHAPE", "message":
                f"root.shape.type must be one of {sorted(_VALID_SHAPES)}, "
                f"got {rshape.get('type') if isinstance(rshape, dict) else rshape!r}"})
        _check_param_refs(rshape.get("params"), param_names, "root.shape", errors)

    # Mounts reference a source node ('root' for M0) + a measurement kind.
    mounts = assembly.get("mounts", []) or []
    known_sources = {"root"}
    mount_ids: set[str] = set()
    if not isinstance(mounts, list):
        errors.append({"code": "MOUNTS_NOT_LIST", "message": "mounts must be a list"})
        mounts = []
    for mi, mt in enumerate(mounts):
        if not isinstance(mt, dict) or not mt.get("id"):
            errors.append({"code": "MOUNT_NO_ID", "message":
                f"mounts[{mi}] needs a non-empty 'id'"})
            continue
        mid = mt["id"]
        if mid in mount_ids:
            errors.append({"code": "MOUNT_DUP_ID", "message": f"duplicate mount id {mid!r}"})
        mount_ids.add(mid)

        pos = mt.get("position", {})
        if not isinstance(pos, dict):
            errors.append({"code": "MOUNT_BAD_POSITION", "message":
                f"mount {mid!r} position must be an object"})
            pos = {}
        else:
            src = pos.get("from", "root")
            if src not in known_sources:
                errors.append({"code": "MOUNT_BAD_SOURCE", "message":
                    f"mount {mid!r} position.from {src!r} is not a known source "
                    f"(M0: only 'root')"})
            kind = pos.get("measure")
            if kind not in ("bbox_corner", "bbox_face_center", "bbox_center",
                            "point_on_edge", "grid_on_face", "array"):
                errors.append({"code": "MOUNT_BAD_MEASURE", "message":
                    f"mount {mid!r} position.measure {kind!r} unsupported"})
            # Required axis/edge fields per measure kind.
            if kind == "bbox_corner" and not _is_axis_str(pos.get("axes")):
                errors.append({"code": "MOUNT_BAD_AXES", "message":
                    f"mount {mid!r} position.axes must be a 6-char sign string "
                    f"like '+X-Y+Z'"})
            elif kind == "bbox_face_center" and not _is_face_str(pos.get("face")):
                errors.append({"code": "MOUNT_BAD_FACE", "message":
                    f"mount {mid!r} position.face must be a 2-char string like '+Y'"})
            elif kind == "point_on_edge":
                if not (_is_axis_str(pos.get("axes_a")) and _is_axis_str(pos.get("axes_b"))):
                    errors.append({"code": "MOUNT_BAD_EDGE", "message":
                        f"mount {mid!r} position needs axes_a + axes_b (6-char each)"})
            elif kind == "grid_on_face":
                if not _is_face_str(pos.get("face")):
                    errors.append({"code": "MOUNT_BAD_FACE", "message":
                        f"mount {mid!r} position.face must be a 2-char string like '+Y'"})
                rc = pos.get("rows"), pos.get("cols")
                if not (isinstance(rc[0], int) and isinstance(rc[1], int)
                        and rc[0] >= 1 and rc[1] >= 1):
                    errors.append({"code": "MOUNT_BAD_GRID", "message":
                        f"mount {mid!r} grid_on_face needs integer rows>=1, cols>=1"})
            elif kind == "array":
                cnt = pos.get("count")
                stp = pos.get("step")
                if not (isinstance(cnt, list) and len(cnt) == 3
                        and all(isinstance(c, int) and c >= 1 for c in cnt)):
                    errors.append({"code": "MOUNT_BAD_ARRAY", "message":
                        f"mount {mid!r} array.count must be 3 integers >= 1"})
                if not (isinstance(stp, list) and len(stp) == 3
                        and all(isinstance(s, list) and len(s) == 3 for s in stp)):
                    errors.append({"code": "MOUNT_BAD_ARRAY", "message":
                        f"mount {mid!r} array.step must be 3 three-vectors"})

        # Orient: optional. If present, derive from a measured direction.
        orient = mt.get("orient")
        if orient is not None:
            if not isinstance(orient, dict):
                errors.append({"code": "MOUNT_BAD_ORIENT", "message":
                    f"mount {mid!r} orient must be an object"})
            else:
                osource = orient.get("from", "root")
                if osource not in known_sources:
                    errors.append({"code": "MOUNT_BAD_SOURCE", "message":
                        f"mount {mid!r} orient.from {osource!r} unknown"})
                oalign = orient.get("align_axis")
                if oalign is not None and oalign not in (
                        "+X", "-X", "+Y", "-Y", "+Z", "-Z"):
                    errors.append({"code": "MOUNT_BAD_ALIGN_AXIS", "message":
                        f"mount {mid!r} orient.align_axis must be one of "
                        f"+X/-X/+Y/-Y/+Z/-Z, got {oalign!r}"})

    # Leaves reference a declared mount + a shape.
    leaves = assembly.get("leaves", []) or []
    if not isinstance(leaves, list):
        errors.append({"code": "LEAVES_NOT_LIST", "message": "leaves must be a list"})
        leaves = []
    for li, lf in enumerate(leaves):
        if not isinstance(lf, dict):
            errors.append({"code": "LEAF_BAD", "message": f"leaves[{li}] must be an object"})
            continue
        lmount = lf.get("mount")
        if lmount not in mount_ids:
            errors.append({"code": "LEAF_BAD_MOUNT", "message":
                f"leaves[{li}] mount {lmount!r} is not a declared mount "
                f"(known: {sorted(mount_ids)})"})
        lshape = lf.get("shape")
        if not isinstance(lshape, dict) or lshape.get("type") not in _VALID_SHAPES:
            errors.append({"code": "LEAF_BAD_SHAPE", "message":
                f"leaves[{li}] shape.type must be one of {sorted(_VALID_SHAPES)}"})
        _check_param_refs(lshape.get("params"), param_names, f"leaves[{li}].shape", errors)
        # scale (optional): expression over params.
        if "scale" in lf and isinstance(lf["scale"], str):
            _check_expr_refs(lf["scale"], param_names, f"leaves[{li}].scale", errors)
        # origin (optional): normalize leaf pose before copy.
        origin = lf.get("origin")
        if origin is not None:
            if not isinstance(origin, dict):
                errors.append({"code": "LEAF_BAD_ORIGIN", "message":
                    f"leaves[{li}] origin must be an object"})
            else:
                anchor = origin.get("anchor", "bbox_center")
                valid_anchor = (
                    (isinstance(anchor, str)
                     and (anchor == "bbox_center"
                          or (anchor.startswith("bbox_face:")
                              and anchor[len("bbox_face:"):] in
                              ("+X", "-X", "+Y", "-Y", "+Z", "-Z"))))
                    or (isinstance(anchor, (list, tuple)) and len(anchor) == 3))
                if not valid_anchor:
                    errors.append({"code": "LEAF_BAD_ORIGIN", "message":
                        f"leaves[{li}] origin.anchor must be 'bbox_center', "
                        f"'bbox_face:<±XYZ>', or a 3-list, got {anchor!r}"})
                off = origin.get("offset")
                if off is not None:
                    if not (isinstance(off, (list, tuple)) and len(off) == 3):
                        errors.append({"code": "LEAF_BAD_ORIGIN", "message":
                            f"leaves[{li}] origin.offset must be a 3-list"})
                    else:
                        for c in off:
                            if isinstance(c, str):
                                _check_expr_refs(c, param_names,
                                                 f"leaves[{li}].origin.offset", errors)

    return {
        "success": len(errors) == 0,
        "errors": errors,
        "summary": {
            "param_count": len(params),
            "mount_count": len(mounts),
            "leaf_count": len(leaves),
        },
    }


def _is_axis_str(v: Any) -> bool:
    return isinstance(v, str) and len(v) == 6


def _is_face_str(v: Any) -> bool:
    return isinstance(v, str) and len(v) == 2


def _check_param_refs(shape_params: Any, known: set[str], where: str,
                      errors: list[dict]) -> None:
    """A shape's param values may be numbers or param-expression strings."""
    if shape_params is None:
        return
    if not isinstance(shape_params, dict):
        errors.append({"code": "SHAPE_PARAMS_BAD", "message":
            f"{where}.params must be an object"})
        return
    for pname, pval in shape_params.items():
        for ref in _value_refs(pval):
            if ref not in known:
                errors.append({"code": "PARAM_REF_DANGLING", "message":
                    f"{where}.params.{pname} references unknown param {ref!r}"})


def _check_expr_refs(expr: str, known: set[str], where: str,
                     errors: list[dict]) -> None:
    from edini.exprs import extract_refs
    for ref in extract_refs(expr):
        if ref not in known:
            errors.append({"code": "PARAM_REF_DANGLING", "message":
                f"{where} references unknown param {ref!r}"})


def _value_refs(value: Any) -> list[str]:
    from edini.exprs import extract_refs
    if isinstance(value, bool) or isinstance(value, (int, float)):
        return []
    if isinstance(value, str):
        return extract_refs(value)
    if isinstance(value, (list, tuple)):
        out: list[str] = []
        for el in value:
            out.extend(_value_refs(el))
        return out
    return []


# ── Resolution: params → root geometry → measured mounts ────────────


def _resolve_params(assembly: dict) -> dict[str, float]:
    """Resolve every param to a concrete float. A param may be a bare number
    (fixed default) or an object with ``default``."""
    out: dict[str, float] = {}
    for name, spec in (assembly.get("params") or {}).items():
        if isinstance(spec, (int, float)) and not isinstance(spec, bool):
            out[name] = float(spec)
        elif isinstance(spec, dict) and isinstance(spec.get("default"), (int, float)):
            out[name] = float(spec["default"])
        else:
            raise AssemblyError(f"param {name!r} is not numeric")
    return out


def _resolve_align_axis(value: Any) -> str:
    """Validate + return an align_axis sign-string (default '+Y').

    Legal values: '+X','-X','+Y','-Y','+Z','-Z'. This is the leaf axis that the
    orient quaternion maps onto the measured direction. Torus wheels pass '+Z'
    (their symmetry axis); +Y-grown shapes keep the default.
    """
    if value is None:
        return "+Y"
    if not isinstance(value, str) or value not in ("+X", "-X", "+Y", "-Y", "+Z", "-Z"):
        raise AssemblyError(
            f"align_axis must be one of +X/-X/+Y/-Y/+Z/-Z, got {value!r}")
    return value


def _hashable(v: Any) -> Any:
    """Deep-freeze a value for use as a dict key: lists → tuples (recursively),
    dicts → sorted tuple of (k, frozen-v) pairs, scalars/strings pass through.
    Two values with the same structure produce equal frozen keys regardless of
    key insertion order (dicts are sorted) or list-vs-tuple form."""
    if isinstance(v, dict):
        return tuple(sorted(((str(k), _hashable(val))
                             for k, val in v.items()), key=lambda kv: kv[0]))
    if isinstance(v, (list, tuple)):
        return tuple(_hashable(el) for el in v)
    return v


def _leaf_group_key(lf: dict, mount: dict) -> tuple:
    """A stable key identifying leaves that produce byte-identical stamped
    output (modulo mount position) and so can share one shape + one CTP.

    Two leaves group iff: same shape type+params, same scale, same origin spec.
    Mount position/orient do NOT enter the key (they vary per mount — that's
    the whole point of grouping). Resolved align_axis is NOT part of the key
    because orient lives on the MOUNT, not the leaf — all leaves sharing a
    mount already share its orient.

    Param/origin values may be lists (e.g. box ``size`` or origin ``offset``);
    they are deep-frozen via :func:`_hashable` so the key is hashable and
    order-insensitive for dict-valued components."""
    shape = lf.get("shape", {})
    shape_key = (shape.get("type"),
                 _hashable(shape.get("params") or {}))
    scale = lf.get("scale")
    origin = lf.get("origin")
    origin_key = _hashable(origin) if isinstance(origin, dict) else None
    return (shape_key, _hashable(scale), origin_key)


def _group_leaves(leaves: list[dict], mounts_by_id: dict[str, dict]) -> list[dict]:
    """Group leaves by _leaf_group_key, preserving declaration order.

    Returns a list of groups, each:
      {key, leaves: [lf, ...], mount_ids: [mid, ...]}
    Leaves in a group share one shape+CTP and stamp onto the merged cloud of
    all the group's mounts. A singleton group is the current (pre-grouping)
    behavior.
    """
    groups: list[dict] = []
    by_key: dict[tuple, int] = {}
    for lf in leaves:
        mid = lf["mount"]
        mount = mounts_by_id.get(mid, {})
        k = _leaf_group_key(lf, mount)
        if k in by_key:
            g = groups[by_key[k]]
            g["leaves"].append(lf)
            g["mount_ids"].append(mid)
        else:
            by_key[k] = len(groups)
            groups.append({"key": k, "leaves": [lf], "mount_ids": [mid]})
    return groups


def _eval_shape_params(shape_params: dict | None, params: dict[str, float]) -> dict:
    """Resolve a shape's param values: numbers pass through, strings are
    evaluated against the param library.

    NOTE (M2): used for VALIDATION and leaf-shape numeric resolution. The ROOT
    shape no longer goes through this — see :func:`_build_shape_live`, which
    keeps the root's size parametric by referencing spare parms via ``ch()``
    expressions so changing a param recooks the bbox live. Leaf shapes still
    resolve to numbers here because their FORM is independent of the root
    (only their PLACEMENT is live, via the CTP point cloud)."""
    out: dict[str, Any] = {}
    for k, v in (shape_params or {}).items():
        if isinstance(v, bool) or isinstance(v, (int, float)):
            out[k] = v
        elif isinstance(v, str):
            out[k] = evaluate(v, params)
        elif isinstance(v, (list, tuple)):
            out[k] = [evaluate(el, params) if isinstance(el, str) else el for el in v]
        else:
            out[k] = v
    return out


def _install_param_spares(container, params: dict[str, float]) -> None:
    """Create a float spare parm for every assembly param on the sandbox geo
    container, so a user (or the live test) can change a param in the Houdini
    UI and have the whole model recook.

    Each param becomes a spare parm named after itself on the container. The
    root shape's size references these via ``ch("../<name>")`` (see
    :func:`_build_shape_live`), so the linkage is param → container spare →
    root size → bbox → mount wrangle → CTP copies, all live.

    Uses the real hou.ParmTemplateGroup API (each parm = a 1-component
    FloatParmTemplate). Fails soft on mocks (mocks have no spare support); the
    live test runs under hython where this works."""
    try:
        ptg = container.parmTemplateGroup()
    except Exception:
        return
    # Positional ctor (H21): name, label, num_components, default_value tuple.
    # Avoids kwarg-name drift across versions.
    for name, value in params.items():
        if ptg.find(name) is not None:
            continue
        try:
            tmpl = hou.FloatParmTemplate(name, name, 1, (float(value),))
            ptg.append(tmpl)
        except Exception:
            continue
    try:
        container.setParmTemplateGroup(ptg)
    except Exception:
        pass
    # Set the values now that the spares exist.
    for name, value in params.items():
        try:
            container.parm(name).set(float(value))
        except Exception:
            pass


def _root_param_ref_expr(value: Any, shape_node) -> Any:
    """For the ROOT shape only: turn a param-name string into a ``ch()``
    expression referencing the container's spare parm, so the root size stays
    parametric and recooks live. A bare number passes through unchanged.

    The root shape lives one level below the container that holds the spare
    parms, hence ``ch("../<name>")``. Multi-component values (a size vector)
    produce a list of ch() expressions — Houdini's parmTuple accepts these."""
    if isinstance(value, str):
        # A param name or param-expression. If it's a bare name, reference the
        # spare directly; if it's an expression, substitute names → ch() refs.
        from edini.exprs import extract_refs
        refs = extract_refs(value)
        expr = value
        for ref in refs:
            expr = expr.replace(ref, f'ch("../{ref}")')
        return expr
    if isinstance(value, (list, tuple)):
        return [_root_param_ref_expr(el, shape_node) for el in value]
    return value


def _maybe_eval(value, params: dict[str, float]):
    """Resolve a value that may be a number or a param-expression string."""
    if isinstance(value, str):
        return evaluate(value, params)
    return value


# ── Live build helpers (M2): VEX wrangle per mount + Copy-to-Points ──
#
# The M2 build is LIVE: it does NOT measure the root once and bake coordinates.
# Instead each mount becomes an attribwrangle whose VEX reads the root's bbox
# via getbbox_min/max on every cook. A leaf's shape is stamped onto the
# wrangle's points by a copytopoints node. Change a root param → the bbox
# re-cooks → the wrangle re-runs → the points move → the copies re-stamp. Zero
# baked coordinates anywhere.


def _install_wrangle_parms(wrangle, snippet: str, parms: dict,
                           params: dict[str, float]) -> str:
    """Install a mount wrangle's scalar spare parms and inline its vector values
    into the VEX. Returns the (possibly modified) snippet.

    - SCALAR selectors (cx/cy/cz, rows, cols, margin, t, face_axis, face_sign,
      countx..) become float spare parms via the real ParmTemplateGroup API;
      the VEX ``ch()``/``chi()`` calls resolve against them on every cook.
    - VECTOR specs (_origin, _step0..) are build-time constants (array step is
      not a root-shape param), so they are INLINED as ``{x,y,z}`` literals into
      the snippet rather than installed as live chv() spares. (M2 scope: only
      root-shape params are live; mount internals are baked at build.)

    Both scalar and vector handling fail soft on mocks (no spare/geometry
    support); the live test runs under hython where this works.
    """
    # Resolve vector specs first, inline them into the snippet.
    vec_values: dict[str, tuple] = {}
    if "_origin" in parms:
        vec_values["origin"] = tuple(_resolve_origin(parms["_origin"], params))
    if "_step0" in parms:
        for i in range(3):
            vec_values[f"step{i}"] = tuple(
                _maybe_eval(c, params) for c in parms[f"_step{i}"])
    out_snippet = snippet
    import re as _re
    for vname, vval in vec_values.items():
        literal = "{" + ",".join(repr(float(c)) for c in vval) + "}"
        out_snippet = _re.sub(r'chv\("' + vname + r'"\)', literal, out_snippet)

    # Install scalar spares via ParmTemplateGroup.
    try:
        ptg = wrangle.parmTemplateGroup()
    except Exception:
        ptg = None
    scalar_parms = {k: v for k, v in parms.items()
                    if not k.startswith("_") and k not in vec_values}
    if ptg is not None:
        for pname, pval in scalar_parms.items():
            if ptg.find(pname) is not None:
                continue
            try:
                ptg.append(hou.FloatParmTemplate(pname, pname, 1, (float(pval),)))
            except Exception:
                continue
        try:
            wrangle.setParmTemplateGroup(ptg)
        except Exception:
            pass
    # Set scalar values (works whether spares installed or pre-existing).
    for pname, pval in scalar_parms.items():
        try:
            wrangle.parm(pname).set(float(pval))
        except Exception:
            pass
    return out_snippet


def _resolve_origin(origin_spec, params: dict[str, float]):
    """Resolve an array origin to a concrete [x,y,z]. For the live build the
    origin is currently a literal [x,y,z] (possibly param-exprs); a measured
    origin (a bbox feature) would require a second wrangle feeding the array
    wrangle, deferred to a later milestone."""
    if isinstance(origin_spec, (list, tuple)) and len(origin_spec) == 3:
        return [_maybe_eval(c, params) for c in origin_spec]
    # Default origin: 0,0,0 (the array's lattice is centered here).
    return [0.0, 0.0, 0.0]


# ── Node construction (Houdini) ─────────────────────────────────────


def _create_node(parent_path: str, node_type: str, name: str):
    """Create a node under parent, resolving namespace variants (mirrors the
    archived asset_builder helper)."""
    parent = hou.node(parent_path)
    if parent is None:
        raise AssemblyError(f"parent not found: {parent_path}")
    try:
        return parent.createNode(node_type, name)
    except Exception:
        for cat in (hou.sopNodeTypeCategory(), hou.objNodeTypeCategory()):
            try:
                nt = hou.nodeType(cat, node_type)
            except Exception:
                nt = None
            if nt is None:
                continue
            for variant in nt.namespaceOrder():
                try:
                    return parent.createNode(variant, name)
                except Exception:
                    continue
        raise


def _looks_like_expr(value: Any) -> bool:
    """True if a value is a ch()/expression string (for the live root build)."""
    return isinstance(value, str) and ("ch(" in value)


def _set_parm(node, pname: str, value: Any) -> None:
    """Set a parm, decomposing multi-component values via parmTuple.

    Expression strings (produced by the live root build, e.g.
    ``ch("../length")``) are set via ``setExpression`` — a numeric parm can't
    be ``.set()`` to a string. A vector holding expression strings sets each
    component sub-parm's expression individually."""
    # Multi-component vector (e.g. box size = [expr, expr, expr]).
    if isinstance(value, (list, tuple)) and len(value) > 1:
        pt = node.parmTuple(pname)
        if pt is not None:
            if any(_looks_like_expr(v) for v in value):
                # Set per-component expressions (live path).
                for sub, v in zip(pt, value):
                    if _looks_like_expr(v):
                        try:
                            sub.setExpression(v, language=hou.exprLanguage.Hscript)
                        except (AttributeError, TypeError):
                            sub.setExpression(v)
                    else:
                        sub.set(v)
                return
            pt.set(tuple(value))
            return
    # Scalar.
    p = node.parm(pname)
    if p is None:
        raise AssemblyError(f"parm {pname!r} not found on {node.path()}")
    if _looks_like_expr(value):
        try:
            p.setExpression(value, language=hou.exprLanguage.Hscript)
        except (AttributeError, TypeError):
            # Mocks / older Houdini: setExpression without explicit language.
            p.setExpression(value)
    else:
        p.set(value)


def _build_shape(parent_path: str, shape: dict, params: dict[str, float],
                 name: str, *, is_root: bool = False):
    """Build ONE native-SOP shape (box/tube/torus/sphere) and return the node.

    For the ROOT shape (``is_root=True``), param-name values become ``ch()``
    expressions referencing the container's spare parms — so the root size
    stays parametric and recooks live when a param changes. For leaf shapes,
    values resolve to numbers (the leaf's form is independent of the root;
    only its placement via CTP is live). (cylinder is not a SOP in H21 — use
    tube.)"""
    stype = shape.get("type")
    node = _create_node(parent_path, stype, name)
    # tube defaults to 'Primitive' type on H21 → a single degenerate prim;
    # procedural workflows want Polygon (type=1).
    if stype == "tube" and "type" not in (shape.get("params") or {}):
        try:
            node.parm("type").set(1)
        except Exception:
            pass
    if is_root:
        # Keep size parametric: reference the container's spares via ch().
        resolved = {pname: _root_param_ref_expr(pval, node)
                    for pname, pval in (shape.get("params") or {}).items()}
    else:
        resolved = _eval_shape_params(shape.get("params"), params)
    for pname, pval in resolved.items():
        _set_parm(node, pname, pval)
    return node


def _build_origin_normalize(root_path: str, origin_spec: dict,
                            params: dict[str, float], name: str):
    """Build the ``<leaf>_normalize`` wrangle that moves a leaf's chosen anchor
    point to the origin (+ optional offset) before copytopoints, so the leaf
    lands clear of the root.

    anchor forms:
      - ``"bbox_center"``       → subtract geometry bbox center
      - ``"bbox_face:<±XYZ>"``  → subtract that face's center
      - ``[x, y, z]``           → subtract the explicit point

    offset (optional ``[x,y,z]``, may be param exprs) is added after, wired as a
    ``chv("offset")`` spare so it stays editable.

    Returns the wrangle node. The wrangle runs over POINT (it only moves ``@P``).
    """
    anchor = origin_spec.get("anchor", "bbox_center")
    offset = origin_spec.get("offset", [0.0, 0.0, 0.0])
    wr = _create_node(root_path, "attribwrangle", name)
    try:
        wr.parm("class").set("point")
    except Exception:
        pass

    if isinstance(anchor, str) and anchor == "bbox_center":
        body = r'vector __c = getbbox_center(0); @P -= __c;'
    elif isinstance(anchor, str) and anchor.startswith("bbox_face:"):
        face = anchor[len("bbox_face:"):]
        from edini.vex_strategies import _face_selector
        sa = _face_selector(face)  # {face_axis, face_sign}
        fa, fs = sa["face_axis"], sa["face_sign"]
        body = (
            f'vector __mn = getbbox_min(0); vector __mx = getbbox_max(0); '
            f'vector __c = getbbox_center(0); '
            f'__c[{fa}] = ({fs} > 0) ? __mx[{fa}] : __mn[{fa}]; '
            f'@P -= __c;')
    elif isinstance(anchor, (list, tuple)) and len(anchor) == 3:
        ax, ay, az = (_maybe_eval(c, params) for c in anchor)
        body = f'@P -= set({float(ax)}, {float(ay)}, {float(az)});'
    else:
        raise AssemblyError(f"origin.anchor unrecognized: {anchor!r}")

    body += ' @P += chv("offset");'

    # Install offset as a vector spare (three float spares: offsetx/y/z), set
    # to the resolved offset values.
    try:
        ptg = wr.parmTemplateGroup()
    except Exception:
        ptg = None
    ox = _maybe_eval(offset[0], params) if len(offset) > 0 else 0.0
    oy = _maybe_eval(offset[1], params) if len(offset) > 1 else 0.0
    oz = _maybe_eval(offset[2], params) if len(offset) > 2 else 0.0
    if ptg is not None:
        for sname, sval in (("offsetx", float(ox)), ("offsety", float(oy)),
                            ("offsetz", float(oz))):
            if ptg.find(sname) is None:
                try:
                    ptg.append(hou.FloatParmTemplate(sname, sname, 1, (sval,)))
                except Exception:
                    continue
        try:
            wr.setParmTemplateGroup(ptg)
        except Exception:
            pass
    for sname, sval in (("offsetx", float(ox)), ("offsety", float(oy)),
                        ("offsetz", float(oz))):
        try:
            wr.parm(sname).set(sval)
        except Exception:
            pass

    try:
        wr.parm("snippet").set(body)
    except Exception as e:
        raise AssemblyError(f"{name} set snippet failed: {e}") from None
    return wr


# ── The build entry point ───────────────────────────────────────────


def build_assembly(
    assembly: dict,
    root_path: str,
    *,
    root_geometry_provider=None,
) -> dict[str, Any]:
    """Build a validated assembly under ``root_path`` as a LIVE Houdini network.

    The M2 flow is live: a leaf's placement is NOT a baked coordinate on a
    Transform node. Instead each mount is an ``attribwrangle`` whose VEX reads
    the root's bbox via ``getbbox_min/max`` on every cook, emitting point(s)
    with ``@P``/``p@orient``/``@pscale``. Each leaf's shape is stamped onto
    those points by a ``copytopoints`` node. Change a root param → bbox
    re-cooks → wrangle re-runs → points move → copies re-stamp. Zero baked
    coordinates anywhere; this is the defining property of the live build.

    Flow:
      1. validate (shift-left — rejects bad assemblies before any node).
      2. resolve params.
      3. build the Root shape (a native SOP whose size reads from params —
         already live).
      4. for each Mount: an attribwrangle downstream of the root, running the
         matching VEX strategy (vex_strategies.build_mount_vex), with its
         selector parms installed. Each emits the mount's point(s).
      5. group leaves by structural identity (shape+scale+origin); merge each
         group's mounts into a sub-cloud.
      6. for each Leaf GROUP: build the shared shape node (once), then one
         copytopoints that stamps the shape onto the group's sub-cloud. (A leaf
         whose scale != 1 stamps a uniform @pscale onto its mount's points
         first.) N identical leaves collapse to ONE shape + ONE CTP.
      7. merge all copytopoints → display-flagged OUT.

    ``root_geometry_provider`` is retained as a test seam for the mock (the
    mock can't execute VEX or synthesize geometry, so mock tests assert the
    NETWORK STRUCTURE — root + N wrangles + per-group CTPs + OUT — while the
    VEX correctness is verified by hython against the Python oracle).
    """
    result = validate_assembly(assembly)
    if not result["success"]:
        return {"success": False, "error": "assembly failed validation: " + "; ".join(
            e.get("message", e.get("code", "?")) for e in result["errors"]),
            "validation_errors": result["errors"]}

    try:
        root_node = hou.node(root_path)
        if root_node is None:
            raise AssemblyError(f"sandbox root not found: {root_path}")
        params = _resolve_params(assembly)

        # 3a. Install every param as a spare parm on the container, so a user
        # (or the live test) can change a param and have the model recook. The
        # root shape references these via ch("../<name>") expressions below.
        _install_param_spares(root_node, params)

        # 3b. Build the root shape with is_root=True so its size stays
        # parametric (ch() refs to the spares) — the root bbox is the live
        # source every mount wrangle reads.
        root_shape = assembly["root"]["shape"]
        root_sop = _build_shape(root_path, root_shape, params, "root_shape", is_root=True)

        # 4. One attribwrangle per mount, downstream of the root. Each runs the
        # matching VEX strategy and emits the mount's point(s) live.
        from edini.vex_strategies import build_mount_vex, _orient_fragment, VexStrategyError
        mount_nodes: dict[str, Any] = {}
        for mt in (assembly.get("mounts") or []):
            mid = mt["id"]
            pos_spec = mt.get("position", {})
            try:
                snippet, mparms = build_mount_vex(pos_spec)
            except VexStrategyError as e:
                raise AssemblyError(f"mount {mid!r}: {e}") from None
            # Append the orient fragment (sets p@orient on every emitted point)
            # when the mount declares an orient spec.
            orient_spec = mt.get("orient")
            if isinstance(orient_spec, dict):
                # align_axis lives on the orient spec (default +Y). Resolved
                # per-leaf override is applied when the leaf picks its mount;
                # here the mount's own value seeds the shared orient fragment.
                align_axis = _resolve_align_axis(orient_spec.get("align_axis"))
                frag = _orient_fragment(orient_spec, align_axis=align_axis)
                if frag:
                    snippet = snippet + "\n" + frag
            wr = _create_node(root_path, "attribwrangle", f"mount_{mid}")
            wr.setInput(0, root_sop)
            try:
                wr.parm("class").set("detail")
            except Exception:
                pass
            # Install scalar spares + inline vector values; returns the final
            # snippet (with chv() resolved to {x,y,z} literals for arrays).
            snippet = _install_wrangle_parms(wr, snippet, mparms, params)
            try:
                wr.parm("snippet").set(snippet)
            except Exception as e:
                raise AssemblyError(f"mount {mid!r} set snippet failed: {e}") from None
            mount_nodes[mid] = wr

        # 5+6. Group structurally-identical leaves so they share ONE shape +
        # ONE CTP (4 identical wheels → 1 shape + 1 CTP stamping the merged
        # cloud of all their mounts). The grouping key is exact: shape+scale+
        # origin must match. Singleton groups behave exactly as the old per-
        # leaf build. The old global mounts_cloud is superseded by per-group
        # sub-clouds below.
        leaf_outputs: list = []
        leaves = assembly.get("leaves") or []
        if not leaves:
            # No leaves: the OUT is just the root (still a valid, if minimal, model).
            leaf_outputs = [root_sop]
        else:
            mounts_by_id = {mt["id"]: mt for mt in (assembly.get("mounts") or [])}
            groups = _group_leaves(leaves, mounts_by_id)
            for group in groups:
                lf0 = group["leaves"][0]      # representative for shape/scale/origin
                lid0 = lf0["id"]
                group_mounts = group["mount_ids"]

                shape_in = _build_shape(root_path, lf0["shape"], params, f"{lid0}_geoshape")
                shape_node = shape_in
                # Origin normalization (optional, applied to the group's shared shape).
                origin_spec = lf0.get("origin")
                if isinstance(origin_spec, dict):
                    norm = _build_origin_normalize(
                        root_path, origin_spec, params, f"{lid0}_normalize")
                    norm.setInput(0, shape_in)
                    shape_node = norm

                # Scale: stamp @pscale onto the group's mount points via a wrangle.
                scale = lf0.get("scale")
                scale_nodes: list = []
                for mid in group_mounts:
                    mount_wr = mount_nodes.get(mid)
                    if mount_wr is None:
                        raise AssemblyError(
                            f"leaf group {lid0!r} mount {mid!r} not declared")
                    if scale is not None:
                        scale_val = (evaluate(scale, params)
                                     if isinstance(scale, str) else float(scale))
                        sw = _create_node(root_path, "attribwrangle",
                                          f"{lid0}_{mid}_pscale")
                        sw.setInput(0, mount_wr)
                        try:
                            sw.parm("class").set("point")
                        except Exception:
                            pass
                        try:
                            sw.parm("snippet").set(f"f@pscale = {float(scale_val)};")
                        except Exception:
                            pass
                        scale_nodes.append(sw)
                    else:
                        scale_nodes.append(mount_wr)

                # Merge the group's mount outputs into one sub-cloud.
                if len(scale_nodes) > 1:
                    sub_cloud = _create_node(root_path, "merge", f"{lid0}_cloud")
                    for idx, n in enumerate(scale_nodes):
                        sub_cloud.setInput(idx, n)
                else:
                    sub_cloud = scale_nodes[0]

                ctp = _create_node(root_path, "copytopoints", f"{lid0}_ctp")
                ctp.setInput(0, shape_node)
                ctp.setInput(1, sub_cloud)
                try:
                    from edini.node_utils import _init_copytopoints_attribs
                    _init_copytopoints_attribs(ctp)
                except Exception:
                    pass
                leaf_outputs.append(ctp)

        # 7. Merge all copytopoints → OUT.
        if len(leaf_outputs) > 1:
            merge = _create_node(root_path, "merge", "merge_all")
            for idx, node in enumerate(leaf_outputs):
                merge.setInput(idx, node)
            final = merge
        else:
            final = leaf_outputs[0]
        out = _create_node(root_path, "null", "OUT")
        out.setInput(0, final)
        try:
            out.setDisplayFlag(True)
        except Exception:
            pass
        try:
            root_node.layoutChildren()
        except Exception:
            pass

        return {
            "success": True,
            "out_path": out.path(),
            "sandbox_root": root_path,
            "live": True,  # signal: this is the live (VEX+CTP) build, not baked
            "mount_ids": list(mount_nodes.keys()),
            "leaf_ids": [lf["id"] for lf in leaves],
        }
    except (AssemblyError, ExprError) as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        import traceback
        return {"success": False, "error": str(e),
                "traceback": traceback.format_exc()}
