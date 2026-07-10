"""Orientation / parametric / robust verification + project status and finalize/plan gates.

Imports ``_vector_to_list`` from ``.geometry_inspect``.

Split out of node_utils.py in the Phase 4 refactor. Re-exported from
``edini.node_utils`` for backwards compatibility.
"""
from __future__ import annotations

import hashlib
import os
import json
import re
import traceback

try:
    import hou
except ImportError:  # offline / unit tests install a mock into sys.modules
    hou = None  # type: ignore[assignment]
from typing import Any

from .geometry_inspect import _vector_to_list  # noqa: F401



from edini.orientation_math import (
    AXIS_VECTORS as _AXIS_VECTORS,
    KIND_EIGEN_RANK as _KIND_EIGEN_RANK,
    compute_covariance as _compute_covariance,
    jacobi_eigen_3x3 as _jacobi_eigen_3x3,
    axis_angle_between as _axis_angle_between,
    dominant_axis_name as _dominant_axis_name,
    flip_to_hemisphere as _flip_to_hemisphere,
    dominant_axis_name as _axis_name_of,  # alias for construction-path reuse
)


def _ui_yield() -> None:
    """Let the Houdini UI breathe during a long main-thread sweep.

    Verification gates (verify_robust / project_finalize) run many recooks in a
    row on the main thread. Each cook is inherently main-thread work, but
    BETWEEN them we can pump the Qt event loop so the viewport repaints and the
    app stays responsive — instead of "Houdini frozen solid" while a finalize
    sweep churns through ~21 cooks. A no-op when PySide6 / a Qt app isn't
    available (headless tests, hython batch). Call only BETWEEN recook
    iterations, never inside a perturb/restore try/finally where param state
    must stay controlled.
    """
    try:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is not None:
            app.processEvents()
    except Exception:
        pass


def verify_orientation(
    node_path: str,
    checks: list[dict],
) -> dict[str, Any]:
    """Verify component orientations via PCA on point positions.

    Each check dict:
        {
            "component_id": "wheel_front",
            "kind": "radial" | "elongated" | "planar",
            "expected_axis": "X" | "Y" | "Z" | "-X" | "-Y" | "-Z",
            "tolerance_deg": 15,
            "signed": false
        }

    For each component:
      - Gather points where prim attribute `component_id` == check's component_id
      - Compute 3x3 position covariance + centroid
      - Jacobi eigendecomposition -> 3 eigenvectors (ascending eigenvalues)
      - Pick eigenvector by kind:
          radial / planar -> smallest eigenvalue's vector (symmetry axis / normal)
          elongated       -> largest eigenvalue's vector (long axis)
      - Compare to expected axis; emit pass/fail + fix quaternion

    Returns:
        {success, passed, failed, total, checks: [...]}
    """
    try:
        node = hou.node(node_path)
        if node is None:
            return {"success": False, "error": f"Node not found: {node_path}"}
        geo = node.geometry()
        if geo is None:
            return {"success": False, "error": f"No geometry on {node_path}"}

        comp_attr = geo.findPrimAttrib("component_id")
        if comp_attr is None:
            return {
                "success": False,
                "error": (
                    "Primitive attribute `component_id` not found. "
                    "Assign @component_id per component in the generator "
                    "(geo.addAttrib(hou.attribType.Prim, 'component_id', '') "
                    "before creating geometry)."
                ),
            }

        results: list[dict] = []
        passed = failed = 0

        for chk in checks:
            cid = chk.get("component_id")
            kind = chk.get("kind", "radial").lower()
            expected_axis = chk.get("expected_axis", "Y").upper()
            tol_deg = float(chk.get("tolerance_deg", 15.0))
            signed_kind = bool(chk.get("signed", False))

            entry: dict[str, Any] = {
                "component_id": cid,
                "kind": kind,
                "expected_axis": expected_axis,
                "tolerance_deg": tol_deg,
                "signed": signed_kind,
                "passed": False,
            }

            if kind not in _KIND_EIGEN_RANK:
                entry["error"] = f"Unknown kind: {kind}"
                results.append(entry); failed += 1; continue
            if expected_axis not in _AXIS_VECTORS:
                entry["error"] = f"Invalid expected_axis: {expected_axis}"
                results.append(entry); failed += 1; continue

            comp_prims = [
                p for p in geo.prims()
                if str(p.stringAttribValue("component_id")) == cid
            ]
            if not comp_prims:
                entry["error"] = (
                    f"No prims with component_id={cid!r}. "
                    f"Available: {sorted(set(str(p.stringAttribValue('component_id')) for p in geo.prims() if p.stringAttribValue('component_id')))[:10]}"
                )
                results.append(entry); failed += 1; continue

            seen_pts = set()
            pts: list[tuple[float, float, float]] = []
            for prim in comp_prims:
                for vtx in prim.vertices():
                    pt = vtx.point()
                    pid = pt.number()
                    if pid in seen_pts:
                        continue
                    seen_pts.add(pid)
                    pos = pt.position()
                    pts.append((float(pos[0]), float(pos[1]), float(pos[2])))

            # ── B-station: construction-axis fast path ──
            # If the builder baked `edini_world_axis` onto these prims
            # (deterministic derivation from construction_axis + anchor @orient),
            # read it directly and SKIP PCA. This is ground truth, not an
            # estimate, so it supersedes the point-distribution-based path.
            # We still run an OPTIONAL PCA crosscheck when enough points exist:
            # a large divergence means the agent's declared construction axis
            # disagrees with the geometry it actually emitted (caught here as a
            # WARNING, not a failure — PCA is noisy, the construction axis is
            # the authority).
            #
            # Round-3 Fix D2: an explicit per-check `construction_axis` token
            # (X/Y/Z/-X/-Y/-Z) OVERRIDES the baked attr for THIS check. This
            # honors the tool's documented parameter (which the backend
            # previously ignored when a bake existed — the session-3 L87 trap):
            # it lets the agent verify against a hypothetical without rebuilding,
            # and falls back to it when no bake is present either.
            world_axis_attr = geo.findPrimAttrib("edini_world_axis")
            has_world_axis = world_axis_attr is not None
            construction_vec: tuple[float, float, float] | None = None
            construction_source = None  # 'baked' | 'override' — for diagnostics
            # 1) Explicit per-check override takes precedence.
            override_axis = chk.get("construction_axis")
            if override_axis is not None and override_axis in _AXIS_VECTORS:
                construction_vec = _AXIS_VECTORS[override_axis]
                construction_source = "override"
            # 2) Otherwise read the baked prim attr (the scaffold's ground truth).
            if construction_vec is None and has_world_axis:
                try:
                    raw = comp_prims[0].floatListAttribValue("edini_world_axis") \
                        if hasattr(comp_prims[0], "floatListAttribValue") \
                        else None
                except Exception:
                    raw = None
                if raw is None or len(raw) < 3:
                    # Fallback: some mock/attrib backends expose tuple access.
                    try:
                        raw = comp_prims[0].attribValue("edini_world_axis")
                        if not isinstance(raw, (list, tuple)) or len(raw) < 3:
                            raw = None
                    except Exception:
                        raw = None
                if raw is not None:
                    construction_vec = (
                        float(raw[0]), float(raw[1]), float(raw[2]))
                    construction_source = "baked"

            if construction_vec is not None:
                # Deterministic construction path.
                detected_vec = construction_vec
                expected_vec = _AXIS_VECTORS[expected_axis]
                if not signed_kind:
                    detected_vec = _flip_to_hemisphere(detected_vec, expected_vec)
                detected_axis = _dominant_axis_name(detected_vec)
                angle_deg, fix_q = _axis_angle_between(
                    detected_vec, expected_vec, signed=signed_kind)
                passed_check = angle_deg <= tol_deg

                entry.update({
                    "method": "construction",
                    "point_count": len(pts),
                    "detected_axis": detected_axis,
                    "detected_vector": [round(c, 4) for c in detected_vec],
                    "world_axis_baked": [round(c, 4) for c in construction_vec],
                    "axis_source": construction_source,  # 'override' | 'baked'
                    "angle_error_deg": round(angle_deg, 2),
                    "passed": passed_check,
                })

                # Optional PCA crosscheck (warning-only). Catches the case
                # where the declared construction axis disagrees with the
                # actual emitted geometry — e.g. agent said construction_axis:Y
                # but the wheel code generates an X-symmetric ring.
                if len(pts) >= 4:
                    try:
                        cov, _ = _compute_covariance(pts)
                        eigs, vecs = _jacobi_eigen_3x3(cov)
                        pca_vec = vecs[_KIND_EIGEN_RANK[kind]]
                        if not signed_kind:
                            pca_vec = _flip_to_hemisphere(pca_vec, construction_vec)
                        pca_angle, _ = _axis_angle_between(
                            pca_vec, construction_vec, signed=False)
                        entry["pca_crosscheck"] = {
                            "pca_axis": _dominant_axis_name(pca_vec),
                            "divergence_deg": round(pca_angle, 2),
                        }
                        # 2x tolerance = clearly inconsistent, surface as warning.
                        if pca_angle > 2.0 * tol_deg:
                            entry["pca_crosscheck"]["warning"] = (
                                f"Declared construction axis ({detected_axis}) "
                                f"diverges from PCA estimate "
                                f"({_dominant_axis_name(pca_vec)}) by "
                                f"{round(pca_angle, 1)}°. The construction axis "
                                f"is authoritative (passed), but this suggests "
                                f"the component code emits geometry whose "
                                f"distribution disagrees with the declared axis. "
                                f"Verify the construction_axis value matches "
                                f"how the geometry is actually generated."
                            )
                    except Exception:
                        pass

                if not passed_check:
                    kind_hint = {
                        "radial": "rotational symmetry axis (axle)",
                        "planar": "surface normal",
                        "elongated": "long axis",
                    }[kind]
                    entry["hint"] = (
                        f"{cid} {kind_hint} baked as world axis {detected_axis} "
                        f"({[round(c,2) for c in detected_vec]}). "
                        f"Expected {expected_axis}. This is a deterministic "
                        f"construction-axis mismatch — fix the component's "
                        f"construction_axis or the anchor @orient in the recipe "
                        f"(do NOT apply a post-hoc quaternion; the bake is "
                        f"ground truth)."
                    )

                results.append(entry)
                if passed_check:
                    passed += 1
                else:
                    failed += 1
                continue

            # ── No edini_world_axis baked (PCA fallback REMOVED, decision 3) ──
            # The PCA estimation path was removed because it misclassifies
            # elongated cylinders (the hub 90° bug): PCA picks the inertia axis,
            # which for a radially-symmetric tube is the length axis, not the
            # radial axle the assert expects. With the fallback gone there is no
            # estimation path left, so a prim without a baked axis fails
            # outright and points the agent at the fix: the asset must be built
            # by a builder that bakes edini_world_axis from the declared
            # construction_axis, or, if the component genuinely has no
            # construction axis, the orientation_assert should be removed.
            entry.update({
                "method": "no_axis",
                "point_count": len(pts),
                "passed": False,
                "error": (
                    f"{cid} has no valid edini_world_axis prim attribute "
                    f"(a NON-ZERO 3-float unit vector, read as "
                    f"floatListAttribValue — NOT a string like \"y\"). "
                    f"Bake it with an attribwrangle (class=primitive): "
                    f"v@edini_world_axis = {{0,1,0}};  // construction axis. "
                    f"A builder is NOT required — any valid baked axis vector "
                    f"passes. Or remove this orientation_assert if the component "
                    f"has no meaningful construction axis."
                ),
            })
            results.append(entry)
            failed += 1

        return {
            "success": True,
            "node_path": node_path,
            "passed": passed,
            "failed": failed,
            "total": len(checks),
            "checks": results,
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"{e}\n{traceback.format_exc()}",
        }


def _point_position_hash(geo) -> str:
    """Deterministic signature of a geometry's point positions.

    Catches ANY real geometric change — including params that move points
    WITHOUT moving the bbox (bevel rounding, sticker coverage, edge insets) —
    which the bbox-only proxy in :func:`verify_parametric` used to
    false-negative as a 'dead param'. That false-negative is what drove agents
    to hand-edit ``__edini_state`` to shrink the verified param set (the
    2026-07-09 cube session). With this hash, a param that genuinely drives
    geometry is detected regardless of whether the bbox moves.

    Positions are quantized relative to the bbox diagonal (float-noise
    insensitive across model scales) and sorted (point-order insensitive). Two
    geometries whose points occupy the same locations hash equal; one moved
    point differs. O(n log n) in point count — cheap for the per-param
    perturbation verify_parametric runs.
    """
    bb = geo.boundingBox()
    diff = bb.maxvec() - bb.minvec()
    diag = diff.length()
    # Relative quantization: ~4 significant digits of model size. Guards
    # against float noise from recook without masking real movement. The
    # floor avoids divide-by-tiny for degenerate (zero-volume) geometry.
    quant = diag * 1e-4 if diag > 1e-9 else 1e-7
    quants = []
    for p in geo.points():
        pos = p.position()
        quants.append((round(pos[0] / quant),
                       round(pos[1] / quant),
                       round(pos[2] / quant)))
    quants.sort()
    return hashlib.md5(repr(quants).encode()).hexdigest()


def verify_parametric(
    node_path: str,
    core_path: str,
    param: str,
    new_value: float,
    expected_axis: str | None = None,
    min_relative_change: float = 0.05,
) -> dict[str, Any]:
    """Prove a design param actually drives the geometry (the LIVE guarantee).

    This is the cure for the "declare done prematurely" failure (session log 2,
    the road bike): the agent declared the model complete after `inspect_health`
    returned `overall_ok`, but never verified that changing a param actually
    moved the geometry. `overall_ok` only proves "not broken right now"; it does
    NOT prove "parametric". This tool proves parametric by PERTURBATION:

      1. Read the target node's current geometry (bbox size, point/prim count,
         and a point-position hash).
      2. Set the core's design param to ``new_value``.
      3. Force-recook the target node.
      4. Read the perturbed geometry.
      5. Assert: geometry non-empty, no new cook errors, and EITHER at least one
         bbox axis changed by >= ``min_relative_change`` OR the point-position
         hash changed (the param propagated to the geometry). The hash is the
         second probe: it catches params that move points WITHOUT moving the
         bbox (bevel rounding, sticker coverage) — the bbox-only proxy used to
         false-negative these as 'dead params'. If ``expected_axis`` is given
         (X/Y/Z), THAT axis MUST change (the hash does not satisfy an axis hint).
      6. ALWAYS restore the param to its original value (never mutate the user's
         scene as a side effect of a check).

    Args:
        node_path: the node whose geometry proves parametricity (usually the
            project's OUT node).
        core_path: the edini::project HDA core carrying the design param.
        param: design param name on the core (e.g. "length").
        new_value: the perturbation value (should be meaningfully different from
            the current value; a sanity check rejects no-op perturbations).
        expected_axis: optional "X"/"Y"/"Z" — if given, this axis MUST change
            (the point-hash probe does NOT satisfy an explicit axis expectation).
        min_relative_change: minimum |Δsize|/|size| for an axis to count as
            "changed" (default 5%, guards against float noise).

    Returns:
        {success, passed, param, original_value, new_value, restored,
         before:{sizes,points,prims,point_hash}, after:{...},
         axis_changes:{X,Y,Z}, point_hash_changed, reason}
    """
    try:
        node = hou.node(node_path)
        if node is None:
            return {"success": False, "error": f"Node not found: {node_path}"}
        core = hou.node(core_path)
        if core is None:
            return {"success": False, "error": f"Core not found: {core_path}"}
        parm = core.parm(param)
        if parm is None:
            return {"success": False,
                    "error": f"Param {param!r} not found on {core_path}"}

        def _snapshot():
            """Read bbox sizes (X/Y/Z), point count, prim count, and a point-
            position hash of `node`. The hash catches params that move points
            without moving the bbox (bevel, sticker_size) — see
            _point_position_hash."""
            g = node.geometry()
            if g is None:
                return None
            bb = g.boundingBox()
            mn = _vector_to_list(bb.minvec())
            mx = _vector_to_list(bb.maxvec())
            return {
                "sizes": [mx[0] - mn[0], mx[1] - mn[1], mx[2] - mn[2]],
                "points": len(g.points()),
                "prims": len(g.prims()),
                "point_hash": _point_position_hash(g),
            }

        original_value = parm.eval()
        # Reject a no-op perturbation — it would always "pass" vacuously and
        # teach the agent the wrong lesson.
        try:
            if abs(float(new_value) - float(original_value)) < 1e-9:
                return {"success": False,
                        "error": (f"new_value {new_value} equals the current "
                                  f"value {original_value}; pick a perturbation "
                                  f"that actually differs to prove parametricity")}
        except (TypeError, ValueError):
            return {"success": False,
                    "error": f"new_value must be numeric, got {new_value!r}"}

        before = _snapshot()
        if before is None:
            return {"success": False,
                    "error": f"No geometry on {node_path} before perturbation"}

        # ── Perturb + recook ──
        # The restore is GUARANTEED via try/finally: if cook/_snapshot/errors
        # raise, the finally still puts the param back. Without this, a cook
        # error mid-verification (the exact failure this tool exists to detect)
        # would silently mutate the user's scene — violating the docstring's
        # "ALWAYS restore" contract. (session-logs-analysis C2 audit.)
        # `_restored` is set ONLY when the finally has actually run, so the
        # outer except can report the param's true state to the agent.
        after = None
        errors: list[str] = []
        _restored = False
        try:
            parm.set(new_value)
            node.cook(force=True)
            after = _snapshot()
            # Capture errors AFTER the recook (this catches broken ch() chains
            # that silently produce zero geometry — the session-log "promote
            # returns 0 / nothing moves" failure).
            errors = list(node.errors() or [])
        finally:
            parm.set(original_value)
            node.cook(force=True)
            _restored = True

        if after is None:
            return {"success": True, "passed": False,
                    "param": param, "original_value": original_value,
                    "new_value": new_value, "restored": True,
                    "before": before, "after": None,
                    "reason": f"geometry vanished after perturbing {param}"}
        if errors:
            return {"success": True, "passed": False,
                    "param": param, "original_value": original_value,
                    "new_value": new_value, "restored": True,
                    "before": before, "after": after,
                    "errors": errors,
                    "reason": f"cook errors after perturbing {param}: {errors}"}
        if after["points"] == 0:
            return {"success": True, "passed": False,
                    "param": param, "original_value": original_value,
                    "new_value": new_value, "restored": True,
                    "before": before, "after": after,
                    "reason": f"zero points after perturbing {param}"}

        # ── Per-axis relative change ──
        axis_labels = ["X", "Y", "Z"]
        axis_changes: dict[str, float] = {}
        any_changed = False
        for i, lbl in enumerate(axis_labels):
            b = before["sizes"][i] or 1e-9   # guard divide-by-zero
            a = after["sizes"][i]
            rel = abs(a - b) / abs(b)
            axis_changes[lbl] = rel
            if rel >= min_relative_change:
                any_changed = True

        # ── Point-position hash: the second probe ──
        # Catches params that drive geometry WITHOUT moving the bbox (bevel
        # rounding, sticker coverage) — the bbox-only proxy false-negatived
        # these as 'dead params', which drove agents to hand-edit
        # __edini_state to pass the gate. Any real movement changes the hash.
        hash_changed = before.get("point_hash") != after.get("point_hash")
        if hash_changed:
            any_changed = True

        if not any_changed:
            return {"success": True, "passed": False,
                    "param": param, "original_value": original_value,
                    "new_value": new_value, "restored": True,
                    "before": before, "after": after,
                    "axis_changes": axis_changes,
                    "point_hash_changed": False,
                    "reason": (f"no bbox axis changed by >= {min_relative_change} "
                               f"AND point positions are identical when "
                               f"{param} {original_value}->{new_value}; the "
                               f"param does not reach the geometry (broken "
                               f"ch() chain?)")}

        # If an expected axis was named, it specifically must have changed.
        if expected_axis:
            ea = expected_axis.upper()
            if ea not in axis_labels:
                return {"success": False,
                        "error": f"expected_axis must be X/Y/Z, got {expected_axis!r}"}
            if axis_changes[ea] < min_relative_change:
                return {"success": True, "passed": False,
                        "param": param, "original_value": original_value,
                        "new_value": new_value, "restored": True,
                        "before": before, "after": after,
                        "axis_changes": axis_changes,
                        "reason": (f"expected axis {ea} did NOT change "
                                   f"({axis_changes[ea]:.4f} < {min_relative_change}) "
                                   f"when {param} changed; the param propagated "
                                   f"but not on the expected axis")}

        return {"success": True, "passed": True,
                "param": param, "original_value": original_value,
                "new_value": new_value, "restored": True,
                "before": before, "after": after,
                "axis_changes": axis_changes,
                "point_hash_changed": hash_changed,
                "reason": (f"PASS: {param} {original_value}->{new_value} moved "
                           f"the geometry"
                           + (f" on axis {expected_axis.upper()}" if expected_axis else "")
                           + (f" (via point positions; bbox unchanged — a shape "
                              f"param like bevel/sticker_size)" if hash_changed
                              and not any(c >= min_relative_change
                                          for c in axis_changes.values()) else "")
                           + f"; axis_changes={axis_changes}")}
    except Exception as e:
        # If the exception happened after perturbation, the inner finally has
        # already restored the param (_restored=True). If it happened before
        # (e.g. parm.eval / node lookup), no perturbation occurred. Either way,
        # report the param's true state so the agent knows the scene is clean.
        restored = locals().get("_restored", False)
        return {"success": False,
                "restored": restored,
                "error": f"{e}\n{traceback.format_exc()}"}


def verify_robust(
    node_path: str,
    core_path: str,
    params: list[str] | None = None,
    samples: str = "min_default_max",
) -> dict[str, Any]:
    """Prove the model holds across the FULL valid range of its design params
    (not just at one perturbation).

    The "stable correct" guarantee that point-in-time :func:`verify_parametric`
    cannot give alone: a model parametric at the default but broken (zero
    geometry / cook errors) at the extremes is fragile. For each design param,
    this samples at its declared min / default / max (configurable), recooks,
    and asserts the geometry stays non-degenerate + error-free at EVERY sample.

    Complementary to verify_parametric: that proves a param DRIVES the geometry
    (direction change at one point); this proves the model HOLDS across the
    range (no degenerate / errored samples at the extremes).

    Read-only across the whole sweep: params are isolated (each restored before
    sweeping the next) and all restored to their originals at the end
    (try/finally safety net), so the user's scene is never mutated.

    Args:
        node_path: node whose geometry proves robustness (usually the OUT node).
        core_path: the edini::project HDA core carrying the design params.
        params: list of design param names to sweep (default: all declared
            design_params).
        samples: ``"min_default_max"`` (default) samples each param's declared
            min/default/max; ``"min_max"`` samples only the extremes.

    Returns:
        ``{success, passed, project, params:[{name, passed, samples:[{value,
        passed, points, prims, sizes, errors, reason}]}], overall_reason}``.
    """
    try:
        node = hou.node(node_path)
        if node is None:
            return {"success": False, "error": f"Node not found: {node_path}"}
        core = hou.node(core_path)
        if core is None:
            return {"success": False, "error": f"Core not found: {core_path}"}
        from edini.project.state import load_declaration
        decl = load_declaration(core)
        decl_params = decl.get("design_params", []) or []
        if params:
            requested = set(params)
            decl_params = [p for p in decl_params if p.get("name") in requested]
            found = {p.get("name") for p in decl_params}
            missing = requested - found
            if missing:
                return {"success": False,
                        "error": f"params not found in declaration: {sorted(missing)}"}
        if not decl_params:
            return {"success": False,
                    "error": "no design_params declared on the core; nothing to sweep"}

        extremes_only = (samples == "min_max")

        def _samples_for(p: dict) -> list[float]:
            mn, df, mx = p.get("min"), p.get("default"), p.get("max")
            ordered = [mn, mx] if extremes_only else [mn, df, mx]
            vals: list[float] = []
            for v in ordered:
                try:
                    fv = float(v)
                except (TypeError, ValueError):
                    continue
                if fv not in vals:   # dedupe (e.g. min==default)
                    vals.append(fv)
            return vals

        def _snapshot() -> dict | None:
            g = node.geometry()
            if g is None:
                return None
            bb = g.boundingBox()
            mn = _vector_to_list(bb.minvec())
            mx = _vector_to_list(bb.maxvec())
            return {"sizes": [mx[0] - mn[0], mx[1] - mn[1], mx[2] - mn[2]],
                    "points": len(g.points()), "prims": len(g.prims())}

        original = {}
        for p in decl_params:
            parm = core.parm(p["name"])
            if parm is not None:
                original[p["name"]] = parm.eval()

        overall_pass = True
        per_param: list[dict] = []
        try:
            for p in decl_params:
                pname = p["name"]
                parm = core.parm(pname)
                if parm is None:
                    per_param.append({"name": pname, "passed": False,
                                      "samples": [],
                                      "reason": f"parm {pname!r} not found on core"})
                    overall_pass = False
                    continue
                sresults: list[dict] = []
                param_pass = True
                for v in _samples_for(p):
                    errs: list[str] = []
                    snap = None
                    try:
                        parm.set(v)
                        node.cook(force=True)
                        snap = _snapshot()
                        errs = list(node.errors() or [])
                    except Exception as e:
                        errs = [str(e)]
                    ok = (not errs) and snap is not None and snap["points"] > 0
                    if not ok:
                        param_pass = False
                    sresults.append({
                        "value": v, "passed": ok,
                        "points": snap["points"] if snap else 0,
                        "prims": snap["prims"] if snap else 0,
                        "sizes": snap["sizes"] if snap else None,
                        "errors": errs,
                        "reason": ("ok" if ok else
                                   (f"errors: {errs}" if errs
                                    else f"zero/empty geometry at {pname}={v}")),
                    })
                per_param.append({"name": pname, "passed": param_pass,
                                  "samples": sresults})
                if not param_pass:
                    overall_pass = False
                # Isolate params: restore this one before sweeping the next so
                # param B's sweep isn't taken with param A clamped at its max.
                if original.get(pname) is not None:
                    try:
                        parm.set(original[pname])
                        node.cook(force=True)
                    except Exception:
                        pass
                # Param restored + re-cooked to baseline → safe to let the UI
                # repaint before sweeping the next param (no perturbed state).
                _ui_yield()
        finally:
            # Safety net: restore ALL params to originals (exception mid-sweep).
            for pname, val in original.items():
                try:
                    core.parm(pname).set(val)
                except Exception:
                    pass
            try:
                node.cook(force=True)
            except Exception:
                pass

        return {
            "success": True, "passed": overall_pass, "project": core_path,
            "params": per_param,
            "overall_reason": (
                "all design params held non-degenerate + error-free across "
                "their sampled range" if overall_pass else
                "one or more samples produced zero geometry or cook errors — "
                "the model is fragile at the param extremes (fix the ch() "
                "chain or clamp the param range)"),
        }
    except Exception as e:
        return {"success": False, "error": f"{e}\n{traceback.format_exc()}"}


_CH_CALL_RE = re.compile(r'(hou\.)?ch\(\s*[\'"]([^\'"]+)[\'"]\s*\)')


def _relative_path_to_core(node_path: str, core_path: str) -> str | None:
    """Compute the relative ch() path from `node_path` up to `core_path`.

    Returns e.g. "../../" such that ch("../../<parm>") on `node_path` resolves
    to `core_path`'s parm. Returns None if `node_path` is not a descendant of
    `core_path` (cannot form a relative reference).

    Pure path-segment arithmetic — no hou needed, fully unit-testable.
    """
    node_parts = node_path.strip("/").split("/")
    core_parts = core_path.strip("/").split("/")
    # node must be strictly deeper than core and share core as a prefix.
    if len(node_parts) <= len(core_parts):
        return None
    if node_parts[:len(core_parts)] != core_parts:
        return None
    depth = len(node_parts) - len(core_parts)
    return "../" * depth


def repath_to_relative(core_path: str, component_id: str) -> dict[str, Any]:
    """Rewrite a component's absolute core ch() references to relative ones.

    This is the cure for the "absolute path → component not migratable" problem
    (Finding 4). Under the design_params path, geometry references core parms via
    absolute ``ch('/obj/.../project_core/<p>')``. That ties the component to its
    current project path — copy the subnet to another project and every ch()
    breaks. This tool rewrites those absolute references to relative ones
    (``ch("../../<p>")``, depth computed per-node), so the component references
    its core by POSITION rather than path. A migrated component then cooks
    anywhere a ``<project_core>`` node sits at the same relative depth (which the
    project HDA structure guarantees).

    Scope: ONE component subnet (on-demand, not whole-project). Rewrites every
    ``ch('.../project_core/<p>')`` and ``hou.ch('.../project_core/<p>')`` inside
    the component's subtree to ``ch('<relative>/<p>')``. Non-ch() expressions
    and references to other nodes are left untouched.

    Args:
        core_path: the edini::project HDA core path.
        component_id: the component subnet name (direct child of core).

    Returns:
        {success, component, rewritten:[{node, parm, before, after}], count,
         skipped, dry_run}
    """
    try:
        core = hou.node(core_path)
        if core is None:
            return {"success": False, "error": f"Core not found: {core_path}"}
        subnet = core.node(component_id)
        if subnet is None:
            return {"success": False,
                    "error": f"Component {component_id!r} not found under {core_path}"}

        core_path_norm = core_path.rstrip("/")
        rewritten: list[dict] = []
        skipped = 0

        # allSubChildren includes the subnet itself; iterate the subtree.
        nodes = list(subnet.allSubChildren()) + [subnet]
        for node in nodes:
            rel = _relative_path_to_core(node.path(), core_path_norm)
            if rel is None:
                continue   # node not a descendant of core (shouldn't happen)
            for parm in node.parms():
                try:
                    expr = parm.expression()
                except Exception:
                    expr = None
                if not expr:
                    continue
                # Does this expression reference the core via an absolute path?
                if core_path_norm not in expr:
                    continue
                new_expr = _CH_CALL_RE.sub(
                    _make_replacer(core_path_norm, rel), expr)
                if new_expr != expr:
                    rewritten.append({
                        "node": node.path(),
                        "parm": parm.name(),
                        "before": expr,
                        "after": new_expr,
                    })
                    try:
                        parm.setExpression(new_expr)
                    except Exception as e:
                        # Don't abort the whole repath on one parm failure —
                        # record and continue (the agent can see partial result).
                        rewritten[-1]["set_error"] = str(e)
                else:
                    skipped += 1

        # `count` counts ONLY successful rewrites. A failed setExpression
        # (recorded with `set_error` on the rewritten entry) does NOT count —
        # previously len(rewritten) over-reported, telling the agent "N refs
        # migrated" when some had silently failed. (session-logs-analysis audit.)
        failed = [r for r in rewritten if "set_error" in r]
        return {"success": True,
                "component": subnet.path(),
                "core": core_path_norm,
                "rewritten": rewritten,
                "count": len(rewritten) - len(failed),
                "failed": [{"node": r["node"], "parm": r["parm"],
                            "error": r["set_error"]} for r in failed],
                "skipped_no_change": skipped}
    except Exception as e:
        return {"success": False,
                "error": f"{e}\n{traceback.format_exc()}"}


def _make_replacer(core_path: str, rel: str):
    """Build a regex sub callback that rewrites ch('/abs/core/path/<p>') and
    hou.ch('/abs/core/path/<p>') to ch('<rel><p>') / hou.ch('<rel><p>').

    Only rewrites references whose path equals core_path or core_path + a parm
    tail (core_path/parm). Leaves other absolute references alone.
    """
    def repl(m: re.Match) -> str:
        fn = m.group(1) or ""    # "hou." or ""
        path = m.group(2)
        # Match exactly core_path or core_path/<parm>.
        if path == core_path:
            return f'{fn}ch("{rel[:-1] if rel != "../" else rel}")'
        if path.startswith(core_path + "/"):
            parm_tail = path[len(core_path) + 1:]
            # guard against deeper paths (core/something/else) — only one level.
            if "/" in parm_tail:
                return m.group(0)
            return f'{fn}ch("{rel}{parm_tail}")'
        return m.group(0)
    return repl


def _declared_anchor_names(comp: dict) -> list[str]:
    """The anchor @name list declared in a component's ports.out (the entry
    with kind=="anchors"). Empty if the component declares no anchor output
    (e.g. a leaf component that only emits geometry)."""
    names: list[str] = []
    for out_entry in (comp.get("ports", {}) or {}).get("out", []) or []:
        if out_entry.get("kind") == "anchors":
            for p in out_entry.get("points", []) or []:
                nm = p.get("name")
                if isinstance(nm, str):
                    names.append(nm)
    return names


def _coupling_advisories(components: list) -> list[dict]:
    """Non-blocking advisories about cross-component coupling.

    A multi-component model where NO component declares a ``ports.in``
    dependency is a set of independent parametric islands — each recomputes
    its own geometry from shared design params rather than tracking another
    component. The 2026-07-09 Rubik's-cube session was exactly this: ``cubies``
    + ``stickers`` both read ``grid_n/unit/gap`` but don't connect (no
    ports.in, zero anchors) — so stickers re-derive the face position by
    formula instead of measuring the cube. It works while both formulas stay
    identical, but is latently fragile and violates the 'measure, don't
    re-derive' principle. ``verify_parametric`` cannot detect this (it checks
    each param drives the MERGED bbox, not that B follows A), so we surface it
    here as advisory — never a hard gate, since legitimate independent
    components exist.
    """
    advisories: list[dict] = []
    if len(components) < 2:
        return advisories
    if any((comp.get("ports", {}) or {}).get("in") for comp in components):
        # At least one component consumes another's anchors → coupled.
        return advisories
    total_anchors = sum(len(_declared_anchor_names(c)) for c in components)
    advisories.append({
        "kind": "independent_components",
        "severity": "advisory",
        "component_count": len(components),
        "anchors_declared": total_anchors,
        "message": (
            f"{len(components)} components declared, but none consumes "
            f"another's anchors (no ports.in; {total_anchors} anchor(s) "
            f"declared). They are independent parametric islands — each "
            f"recomputes its geometry from shared params. If a component "
            f"should TRACK another (e.g. stickers following a body), declare "
            f"ports.in + measure anchors via project_add_anchors so it moves "
            f"with upstream; otherwise consider merging them into a single "
            f"component to avoid duplicated formulas drifting apart."
        ),
    })
    return advisories


def project_status(core_path: str) -> dict[str, Any]:
    """One-shot completion snapshot of every component in a Project HDA.

    Replaces the N-tool status-gathering loop (inspect_health + geometry_inventory
    + check_errors per component) with a single call. For each declared component
    reports:

      - ``geo_flow``: ``ok`` | ``empty`` | ``broken`` | ``no_scaffold`` |
        ``missing_subnet`` — does ``out_geometry`` have cooked geometry?
      - ``prim_count`` / ``point_count`` of that geometry.
      - ``anchors``: ``{declared, emitted, missing}`` — declared in ``ports.out``
        vs the ``anchor_<name>`` wrangles ``project_add_anchors`` created.
      - ``errors`` / ``warnings``: counts across the component's subtree.

    Plus an ``overall`` summary: components with geometry / with all anchors
    emitted / with errors, and an ``incomplete`` list (the agent's "what's left").

    Read-only — never cooks destructively or perturbs params. For the LIVE
    parametric guarantee use ``verify_parametric`` (deeper; perturbs + restores).

    Args:
        core_path: the edini::project SOP HDA instance path.
    """
    try:
        core = hou.node(core_path)
        if core is None:
            return {"success": False, "error": f"Core not found: {core_path}"}
        from edini.project.state import load_declaration
        from edini.project.ports import OUT_GEOMETRY_NODE
        decl = load_declaration(core)
        components = decl.get("components", []) or []

        out: list[dict] = []
        with_geo = with_all_anchors = with_errors = 0
        incomplete: list[str] = []
        for comp in components:
            cid = comp.get("id", "?")
            entry: dict[str, Any] = {"id": cid}
            subnet = core.node(cid)
            if subnet is None:
                entry["geo_flow"] = "missing_subnet"
                entry["prim_count"] = 0
                entry["point_count"] = 0
                entry["anchors"] = {"declared": 0, "emitted": 0, "missing": []}
                entry["errors"] = 0
                entry["warnings"] = 0
                incomplete.append(cid)
                out.append(entry)
                continue

            # ── geo flow: read out_geometry's cooked geometry ──
            prim_count = point_count = 0
            geo_flow = "empty"
            cook_error: str | None = None
            out_geo = subnet.node(OUT_GEOMETRY_NODE)
            if out_geo is None:
                geo_flow = "no_scaffold"   # out_geometry null missing (re-scaffold?)
            else:
                try:
                    geo = out_geo.geometry()
                    if geo is not None:
                        prim_count = int(geo.intrinsicValue("primitivecount"))
                        point_count = int(geo.intrinsicValue("pointcount"))
                        geo_flow = "ok" if prim_count > 0 else "empty"
                except Exception as e:
                    # A cook failure inside the component (broken ch(), bad
                    # VEX) surfaces here — the agent's signal to fix it.
                    geo_flow = "broken"
                    cook_error = str(e)
            entry["geo_flow"] = geo_flow
            entry["prim_count"] = prim_count
            entry["point_count"] = point_count
            if cook_error:
                entry["cook_error"] = cook_error

            # ── anchors: declared (ports.out) vs emitted (anchor_<name>) ──
            declared = _declared_anchor_names(comp)
            emitted = [n for n in declared
                       if subnet.node(f"anchor_{n}") is not None]
            missing = [n for n in declared if n not in emitted]
            entry["anchors"] = {"declared": len(declared),
                                "emitted": len(emitted), "missing": missing}

            # ── errors/warnings across the component subtree ──
            err_count = warn_count = 0
            for n in subnet.allSubChildren():
                try:
                    err_count += len(n.errors() or [])
                    warn_count += len(n.warnings() or [])
                except Exception:
                    pass
            entry["errors"] = err_count
            entry["warnings"] = warn_count

            # ── tally ──
            anchors_ok = (not declared) or (not missing)
            done = geo_flow == "ok" and anchors_ok and err_count == 0
            if geo_flow == "ok":
                with_geo += 1
            if anchors_ok:
                with_all_anchors += 1
            if err_count:
                with_errors += 1
            if not done:
                incomplete.append(cid)
            out.append(entry)

        return {
            "success": True,
            "project": core_path,
            "component_count": len(components),
            "components": out,
            "coupling_advisories": _coupling_advisories(components),
            "overall": {
                "with_geometry": with_geo,
                "with_all_anchors": with_all_anchors,
                "with_errors": with_errors,
                "complete": len(components) - len(incomplete),
                "incomplete": incomplete,
            },
        }
    except Exception as e:
        return {"success": False,
                "error": f"{e}\n{traceback.format_exc()}"}


def _finalize_perturbation(p: dict, current: float) -> float:
    """Pick a ``verify_parametric`` new_value for a design param: a value
    meaningfully different from its CURRENT value (so verify_parametric's
    no-op guard doesn't reject it), preferring the declared max, then min,
    then current*1.5 (or +1 if current is 0)."""
    try:
        cur = float(current)
    except (TypeError, ValueError):
        cur = 1.0
    for key in ("max", "min"):
        v = p.get(key)
        if v is None:
            continue
        try:
            fv = float(v)
        except (TypeError, ValueError):
            continue
        if abs(fv - cur) > 1e-9:
            return fv
    return cur * 1.5 if cur != 0 else 1.0


def project_finalize(
    core_path: str,
    acknowledge_skip: bool = False,
    skip_reason: str | None = None,
    samples: str = "min_default_max",
    structure_override: bool = False,
    structure_reason: str | None = None,
) -> dict[str, Any]:
    """Hard gate: refuse to mark a project complete until it passes verification.

    The structural enforcement of the "don't declare done prematurely" rule.
    ``verify_parametric`` / ``verify_robust`` are TOOLS the agent could skip
    (the road-bike session log did exactly that — declared done after
    ``inspect_health``'s ``overall_ok``, never verified parametricity).
    ``project_finalize`` is a GATE: it runs the verification itself and refuses
    to mark complete on failure. The only way past without passing is an
    explicit ``acknowledge_skip=True`` + non-empty ``skip_reason`` (audited to
    the declaration log) — the "open the right door" principle from
    pitfalls.md (refuse the wrong action, but leave a correct channel).

    **Gate 4 (structure) is immune to ``acknowledge_skip``**: a FATAL verdict
    from ``analyze_component_structure`` blocks finalize even when skip is
    requested. The only override is an audited
    ``structure_override=True`` + ``structure_reason``. This closes the
    2026-07-09 gap where 3/6 sessions shipped broken models via the skip hatch.

    Runs, in order:
      4. ``analyze_component_structure`` — structural-intent check (FATAL
         verdicts immune to ``acknowledge_skip``). Runs FIRST so a structural
         fatal blocks everything else, including the skip hatch.
      1. ``project_status`` — every declared component complete (geo_flow ok,
         no missing anchors, no errors)?
      2. ``verify_robust`` — the model holds (non-degenerate + error-free)
         across every design_param's min/default/max?
      3. ``verify_parametric`` per design_param — each param actually DRIVES
         the geometry (not a dead param that passes robust vacuously).

    If the project has NO design_params, steps 2-3 are N/A (a static model has
    nothing parametric to prove) and finalize proceeds on step 1 alone — this
    is NOT a skip and needs no ``acknowledge_skip``.

    Args:
        core_path: the edini::project SOP HDA instance path.
        acknowledge_skip: bypass running Gates 1-3 verification. Requires
            ``skip_reason``.  Does NOT bypass Gate 4 (structure) — a structural
            fatal blocks finalize regardless. Use only when verification
            genuinely can't run (e.g. an intentionally non-parametric study).
            The skip is audited to the declaration log.
        skip_reason: required when ``acknowledge_skip=True``; why verify is skipped.
        samples: passed through to ``verify_robust`` ("min_default_max" | "min_max").
        structure_override: the ONLY way past a Gate 4 structural fatal.
            Requires ``structure_reason``. The override is audited to the log.
        structure_reason: required when ``structure_override=True``; state WHY
            the structural fatal is being overridden.

    Returns:
        ``{success, finalized, core_path, checks:{structure, status, robust,
        parametric}, failures:[...], skipped, skip_reason}``.
        ``success=True`` iff finalized (all gates passed OR
        ``acknowledge_skip`` was used correctly AND Gate 4 passed/overridden).
        On a Gate 4 block: ``{structure_blocked: True, structure_fatal: [...]}``.
    """
    try:
        core = hou.node(core_path)
        if core is None:
            return {"success": False, "error": f"Core not found: {core_path}"}

        from edini.project.state import (load_declaration, save_declaration,
                                         append_log)

        failures: list[str] = []
        records: list[dict] = []  # structured FailureRecords → knowledge drafts (5a)
        checks: dict[str, Any] = {}

        # Closed-loop learning (5a): each gate failure is captured as a
        # structured FailureRecord so project_finalize can auto-draft it into
        # the knowledge store. The agent searches those drafts when it hits a
        # similar failure next time; a human promotes the useful ones.
        _FINALIZE_HINTS = {
            "incomplete": "用 project_status 查看 geo_flow/anchors,补建缺失几何或锚点",
            "cook_error": "用 check_errors 定位报错节点,按错误信息修复参数/表达式",
            "degenerate": "模型在区间端点坍缩 — 放宽 min/max 或修复极端尺寸下的几何",
            "dead_param": "参数未驱动几何 — 检查 ch() 引用是否断开,或 repath_to_relative 修复",
            "orientation": "朝向不符 — 检查组件 axis 声明或 anchor @orient",
            "missing_param": "设计参数在 core 上缺失 — 重新 project_build_scaffold",
            "structure": "结构不符声明 — 检查 repeats 方法/instancing 节点或 axis 朝向",
        }

        def _add_failure(category: str, message: str, **struct) -> None:
            """Append the human failure string (unchanged return shape) AND a
            structured record for auto-drafting."""
            failures.append(message)
            rec = {"category": category, "tool": "project_finalize",
                   "message": message, "hint": _FINALIZE_HINTS.get(category, "")}
            rec.update({k: v for k, v in struct.items() if v is not None})
            records.append(rec)

        decl = load_declaration(core)

        # ── Gate 4: structure (FATAL verdicts immune to acknowledge_skip) ──
        # Runs FIRST so that a structural fatal blocks everything else,
        # including the acknowledge_skip hatch. The only way past a structural
        # fatal is an audited structure_override + structure_reason.
        from edini.structure import analyze_component_structure
        struct = analyze_component_structure(core_path)
        fatal_struct = struct.get("fatal", []) if struct.get("success") else []
        if fatal_struct and not structure_override:
            if acknowledge_skip:
                return {"success": False, "finalized": False, "core_path": core_path,
                        "skipped": False, "structure_blocked": True,
                        "checks": {"structure": struct},
                        "failures": [f"Gate 4 (structure) fatal — not bypassable by "
                                     f"acknowledge_skip: {[f.get('rule') for f in fatal_struct]}"],
                        "structure_fatal": fatal_struct}
            _add_failure("structure",
                         f"Gate 4 structure fatal: {[f.get('rule') for f in fatal_struct]}",
                         components=[f.get("component") for f in fatal_struct])
        elif fatal_struct and structure_override:
            if not (structure_reason and structure_reason.strip()):
                return {"success": False, "error": (
                    "structure_override=True requires a non-empty structure_reason "
                    "(state WHY the structural fatal is being overridden).")}
            append_log(decl, kind="structure_override",
                       summary=f"structure fatal overridden: {structure_reason.strip()}",
                       payload={"fatal": [f.get("rule") for f in fatal_struct],
                                "reason": structure_reason.strip()}, result_ok=True)
            save_declaration(core, decl)
        checks["structure"] = struct

        # ── SKIP path: bypasses Gates 1-3 only (Gate 4 already ran above) ──
        if acknowledge_skip:
            if not (skip_reason and skip_reason.strip()):
                return {"success": False,
                        "error": ("acknowledge_skip=True requires a non-empty "
                                  "skip_reason (the 'right door' — state WHY "
                                  "verification is skipped). Note: Gate 4 "
                                  "(structure) is NOT bypassable by skip; use "
                                  "structure_override + structure_reason.")}
            append_log(decl, kind="finalize_skip",
                       summary=f"finalized without verification (Gates 1-3 skipped; "
                               f"Gate 4 structure passed): {skip_reason.strip()}",
                       payload={"skip_reason": skip_reason.strip()},
                       result_ok=True)
            save_declaration(core, decl)
            return {"success": True, "finalized": True, "skipped": True,
                    "skip_reason": skip_reason.strip(), "core_path": core_path,
                    "checks": checks, "failures": [],
                    "drafts_created": 0, "failure_records": []}

        # ── Gate 1: completeness (project_status) ──
        status = project_status(core_path)
        checks["status"] = status
        if not status.get("success"):
            _add_failure("incomplete",
                         f"project_status failed to run: {status.get('error')}")
        else:
            incomplete = status.get("overall", {}).get("incomplete", [])
            if incomplete:
                _add_failure("incomplete",
                             f"components not complete: {incomplete} (geo_flow/anchors/"
                             f"errors — see project_status). Build or fix them first.",
                             components=incomplete)
            elif status.get("overall", {}).get("with_errors", 0):
                _add_failure("cook_error",
                             "a component has cook errors (see project_status).",
                             components=status.get("overall", {}).get("incomplete", []))

        # ── Resolve the project OUT node (verify reads its geometry) ──
        out_node = core.node("OUT")
        if out_node is None:
            _add_failure("incomplete",
                         "project OUT node not found on the core "
                         "(re-run project_build_scaffold).")

        design_params = decl.get("design_params", []) or []

        # ── Gates 2 & 3: parametric verification (only if design params exist) ──
        if not design_params:
            checks["robust"] = None
            checks["parametric"] = None
            checks["note"] = ("no design_params declared — parametric gates "
                               "(robust/parametric) are N/A, not skipped.")
        elif out_node is not None:
            out_path = out_node.path()

            # Gate 2: robust across the declared range.
            robust = verify_robust(out_path, core_path, samples=samples)
            checks["robust"] = robust
            if not robust.get("success"):
                _add_failure("degenerate",
                             f"verify_robust did not run: {robust.get('error')}")
            elif not robust.get("passed"):
                bad = [p.get("name") for p in robust.get("params", [])
                       if not p.get("passed")]
                _add_failure("degenerate",
                             f"verify_robust FAILED for params: {bad} "
                             f"(model degenerates or errors across the range).",
                             param=bad)

            # Gate 3: each param actually drives the geometry (not a dead param).
            parametric_results: list[dict] = []
            for p in design_params:
                pname = p.get("name")
                parm = core.parm(pname) if pname else None
                if parm is None:
                    _add_failure("missing_param",
                                 f"design param {pname!r} not found on the core "
                                 f"(re-run project_build_scaffold).",
                                 param=pname)
                    continue
                new_value = _finalize_perturbation(p, parm.eval())
                pr = verify_parametric(out_path, core_path, pname, new_value)
                pr["_param"] = pname
                parametric_results.append(pr)
                if not pr.get("success"):
                    _add_failure("dead_param",
                                 f"verify_parametric did not run for "
                                 f"{pname!r}: {pr.get('error')}",
                                 param=pname)
                elif not pr.get("passed"):
                    _add_failure("dead_param",
                                 f"verify_parametric FAILED for {pname!r}: "
                                 f"param does not drive the geometry "
                                 f"(dead param? broken ch() ref?).",
                                 param=pname)
                # verify_parametric perturbs+restores one param per call; between
                # params is a safe, restored-baseline moment to let the UI repaint.
                _ui_yield()
            checks["parametric"] = parametric_results

        # ── Auto-draft failures into the knowledge store (5a closed loop) ──
        # Every project_finalize failure becomes a searchable draft the agent
        # can find next time. Wrapped so a knowledge-store hiccup can NEVER
        # break the gate itself — the failures are still returned regardless.
        drafts_created = 0
        if records:
            try:
                from edini.ui.knowledge_store import add_failure_drafts
                project_context = {
                    "goal": decl.get("project", {}).get("goal", ""),
                    "components": [c.get("id") for c in decl.get("components", [])],
                }
                drafts_created = add_failure_drafts(records, project_context)
            except Exception:
                drafts_created = 0

        # ── Coupling advisory (non-blocking) ──
        # Multi-component projects with no cross-component wiring are
        # independent islands (the cube cubies+stickers pattern). Never a
        # failure — surfaced so the agent/user can decide to couple or merge.
        advisories = _coupling_advisories(decl.get("components", []) or [])

        # ── Decide ──
        if failures:
            return {"success": False, "finalized": False, "core_path": core_path,
                    "checks": checks, "failures": failures, "skipped": False,
                    "advisories": advisories,
                    "drafts_created": drafts_created, "failure_records": records}

        # All green — audit the finalize to the log.
        decl = load_declaration(core)
        append_log(decl, kind="finalize",
                   summary=("passed all gates: structure + status complete"
                            + (f" + robust + parametric over {len(design_params)} "
                               f"param(s)" if design_params else " (no design_params)")),
                   payload={"design_params": [p.get("name") for p in design_params]},
                   result_ok=True)
        save_declaration(core, decl)
        return {"success": True, "finalized": True, "core_path": core_path,
                "checks": checks, "failures": [], "skipped": False,
                "advisories": advisories,
                "drafts_created": 0, "failure_records": []}
    except Exception as e:
        return {"success": False,
                "error": f"{e}\n{traceback.format_exc()}"}


def project_plan(core_path: str, goal: str,
                 success_criteria: list[str]) -> dict[str, Any]:
    """Capture the modeling intent (goal + success criteria) BEFORE scaffolding.

    The structural cure for upstream errors compounding downstream: forces the
    agent to articulate what 'done' means BEFORE building anything, with
    platform validation. The captured ``success_criteria`` is stored on the
    declaration (later cross-checkable by :func:`project_finalize`). Replaces
    the vague "inspect_health overall_ok = done" trap — overall_ok only proves
    "not broken right now", not "parametric + meets intent".

    Call right after ``project_create``, before ``project_build_scaffold``.

    Args:
        core_path: the edini::project SOP HDA instance path.
        goal: what the project will build, in natural language.
        success_criteria: a non-empty list of strings — the explicitly-stated
            conditions for "done".

    Returns ``{success, plan:{goal, success_criteria}, core_path}``.
    """
    try:
        core = hou.node(core_path)
        if core is None:
            return {"success": False, "error": f"Core not found: {core_path}"}
        if not (isinstance(goal, str) and goal.strip()):
            return {"success": False,
                    "error": "project_plan requires a non-empty 'goal' "
                             "(what the project will build)."}
        if not isinstance(success_criteria, list) or not success_criteria:
            return {"success": False,
                    "error": "project_plan requires 'success_criteria': a "
                             "non-empty list of strings (what 'done' means)."}
        cleaned = [c.strip() for c in success_criteria
                   if isinstance(c, str) and c.strip()]
        if not cleaned:
            return {"success": False,
                    "error": "success_criteria must be non-empty strings."}

        from edini.project.state import load_declaration, save_declaration
        decl = load_declaration(core)
        decl.setdefault("project", {})["goal"] = goal.strip()
        decl["success_criteria"] = cleaned
        save_declaration(core, decl)
        return {"success": True, "core_path": core_path,
                "plan": {"goal": goal.strip(), "success_criteria": cleaned}}
    except Exception as e:
        return {"success": False,
                "error": f"{e}\n{traceback.format_exc()}"}
