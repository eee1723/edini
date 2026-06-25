"""Procedural harness helpers for safer Houdini generation."""
from __future__ import annotations

import datetime as _dt
import io
import math
import re
import sys
import traceback
import uuid
from typing import Any

import hou


EXECUTION_MODE_LIVE = "live_sandbox"


def make_job_id(label: str = "job") -> str:
    safe = re.sub(r"[^A-Za-z0-9_]+", "_", label).strip("_").lower() or "job"
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{stamp}_{safe}_{uuid.uuid4().hex[:8]}"


def to_jsonable(value: Any, _seen: set[int] | None = None) -> Any:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)

    if _seen is None:
        _seen = set()
    value_id = id(value)
    if value_id in _seen:
        return f"<recursive {type(value).__name__}>"

    if isinstance(value, dict):
        _seen.add(value_id)
        try:
            result = {}
            for key, item in value.items():
                json_key = to_jsonable(key, _seen)
                if not isinstance(json_key, (str, int, float, bool)) and json_key is not None:
                    json_key = repr(json_key)
                result[json_key] = to_jsonable(item, _seen)
            return result
        finally:
            _seen.remove(value_id)

    if isinstance(value, (list, tuple)):
        _seen.add(value_id)
        try:
            return [to_jsonable(item, _seen) for item in value]
        finally:
            _seen.remove(value_id)

    if isinstance(value, set):
        _seen.add(value_id)
        try:
            return [to_jsonable(item, _seen) for item in sorted(value, key=repr)]
        finally:
            _seen.remove(value_id)

    path = getattr(value, "path", None)
    if callable(path):
        try:
            return to_jsonable(path(), _seen)
        except Exception:
            pass

    try:
        return repr(value)
    except Exception:
        return f"<unrepresentable {type(value).__name__}>"


def _vector_to_list(value) -> list[float]:
    try:
        return [float(value[0]), float(value[1]), float(value[2])]
    except Exception:
        return [float(value.x()), float(value.y()), float(value.z())]


def geometry_bounds(geo) -> dict[str, list[float]] | None:
    try:
        raw = geo.intrinsicValue("bounds")
        if raw is not None and len(raw) == 6:
            mn = [float(raw[0]), float(raw[2]), float(raw[4])]
            mx = [float(raw[1]), float(raw[3]), float(raw[5])]
            return {"min": mn, "max": mx, "size": [mx[0] - mn[0], mx[1] - mn[1], mx[2] - mn[2]]}
    except Exception:
        pass

    try:
        bbox = geo.boundingBox()
        if bbox is None:
            return None
        mn = _vector_to_list(bbox.minvec())
        mx = _vector_to_list(bbox.maxvec())
        return {"min": mn, "max": mx, "size": [mx[0] - mn[0], mx[1] - mn[1], mx[2] - mn[2]]}
    except Exception:
        return None


def geometry_stats(node_path: str) -> dict[str, Any] | None:
    node = hou.node(node_path)
    if node is None:
        return None
    # Only SopNodes (surface operators) carry a cookable .geometry(). A network
    # sandbox's root is a geo *container* (ObjNode) — calling .geometry() on it
    # raises AttributeError: 'ObjNode' object has no attribute 'geometry',
    # which used to nest a second traceback under the agent's real error. Guard
    # with hasattr so non-SOP paths degrade cleanly to None instead.
    if not hasattr(node, "geometry"):
        return None
    geo = node.geometry()
    if geo is None:
        return None
    return {
        "point_count": geo.intrinsicValue("pointcount"),
        "prim_count": geo.intrinsicValue("primitivecount"),
        "vertex_count": geo.intrinsicValue("vertexcount"),
        "bounds": geometry_bounds(geo),
    }


def _parm_record(parm) -> dict[str, Any]:
    try:
        name = parm.name()
    except Exception as exc:
        name = "<unknown>"
        name_error = str(exc)
    else:
        name_error = None

    try:
        label = parm.description()
    except Exception as exc:
        label = name
        label_error = str(exc)
    else:
        label_error = None

    record: dict[str, Any] = {"name": name, "label": label}
    if name_error is not None:
        record["name_error"] = name_error
    if label_error is not None:
        record["label_error"] = label_error

    try:
        record["value"] = to_jsonable(parm.eval())
    except Exception as exc:
        record["error"] = str(exc)

    return record


def collect_diagnostics(
    node_path: str,
    include_geometry: bool = True,
    include_parms: bool = False,
) -> dict[str, Any]:
    node = hou.node(node_path)
    if node is None:
        return {
            "success": False,
            "node_path": node_path,
            "error": f"Node not found: {node_path}",
        }

    result: dict[str, Any] = {
        "success": True,
        "node_path": node_path,
        "node_type": node.type().name(),
        "node_errors": list(node.errors() or []),
        "node_warnings": list(node.warnings() or []),
    }

    if include_geometry:
        result["geometry"] = geometry_stats(node_path)

    if include_parms:
        result["parameters"] = [_parm_record(p) for p in node.parms()]

    return result


def _safe_collect_diagnostics(
    node_path: str,
    include_geometry: bool = True,
    include_parms: bool = False,
) -> dict[str, Any]:
    try:
        return collect_diagnostics(
            node_path,
            include_geometry=include_geometry,
            include_parms=include_parms,
        )
    except Exception as e:
        return {
            "success": False,
            "node_path": to_jsonable(node_path),
            "error": f"Diagnostics failed: {e}",
            "traceback": traceback.format_exc(),
            "include_geometry": bool(include_geometry),
            "include_parms": bool(include_parms),
        }


def _node_path_for_diagnostics(value: Any, fallback: str) -> str:
    if isinstance(value, str):
        return value

    path = getattr(value, "path", None)
    if callable(path):
        try:
            path_value = path()
        except Exception:
            pass
        else:
            if isinstance(path_value, str):
                return path_value

    jsonable = to_jsonable(value)
    if isinstance(jsonable, str):
        return jsonable
    return fallback


def _check(name: str, passed: bool, actual, expected=None) -> dict[str, Any]:
    record = {
        "name": name,
        "passed": bool(passed),
        "actual": actual,
    }
    if expected is not None:
        record["expected"] = expected
    return record


def verify_asset(node_path: str, expected: dict[str, Any] | None = None) -> dict[str, Any]:
    expected = expected or {}
    try:
        stats = geometry_stats(node_path)
    except Exception as e:
        return {
            "success": False,
            "node_path": node_path,
            "geometry": None,
            "checks": [
                _check("geometry_stats", False, str(e), "geometry stats")
            ],
            "error": str(e),
            "traceback": traceback.format_exc(),
        }

    checks: list[dict[str, Any]] = [
        _check("geometry_exists", stats is not None, stats is not None, True)
    ]

    if stats is not None:
        if "min_points" in expected:
            point_count = stats.get("point_count")
            checks.append(
                _check(
                    "min_points",
                    point_count is not None and point_count >= expected["min_points"],
                    point_count,
                    expected["min_points"],
                )
            )
        if "min_prims" in expected:
            prim_count = stats.get("prim_count")
            checks.append(
                _check(
                    "min_prims",
                    prim_count is not None and prim_count >= expected["min_prims"],
                    prim_count,
                    expected["min_prims"],
                )
            )
        if expected.get("bounds_nonzero"):
            bounds = stats.get("bounds") or {}
            size = bounds.get("size")
            checks.append(
                _check(
                    "bounds_nonzero",
                    isinstance(size, list) and any(abs(component) > 1e-6 for component in size),
                    size,
                    True,
                )
            )

    diagnostics = _safe_collect_diagnostics(
        node_path,
        include_geometry=False,
        include_parms=False,
    )
    if diagnostics.get("success"):
        node_errors = list(diagnostics.get("node_errors") or [])
        checks.append(_check("node_errors", len(node_errors) == 0, node_errors, []))
    else:
        checks.append(
            _check(
                "diagnostics",
                False,
                diagnostics.get("error", "Diagnostics failed"),
                "success",
            )
        )

    return {
        "success": all(check["passed"] for check in checks),
        "node_path": node_path,
        "geometry": stats,
        "checks": checks,
    }


def discard_sandbox(sandbox_root_path: str) -> dict[str, Any]:
    node = hou.node(sandbox_root_path)
    if node is None:
        return {
            "success": False,
            "sandbox_root_path": sandbox_root_path,
            "discarded": False,
            "error": f"Sandbox root not found: {sandbox_root_path}",
        }

    try:
        node.destroy()
        return {
            "success": True,
            "sandbox_root_path": sandbox_root_path,
            "discarded": True,
        }
    except Exception as e:
        return {
            "success": False,
            "sandbox_root_path": sandbox_root_path,
            "discarded": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }


def commit_sandbox(
    sandbox_root_path: str,
    final_name: str,
    replace_existing: bool = False,
    orientation_checks: list[dict] | None = None,
    skip_orientation: bool = False,
    skip_structure_check: bool = False,
) -> dict[str, Any]:
    stripped_name = final_name.strip()
    if not stripped_name or "/" in final_name or "\\" in final_name or stripped_name == "..":
        return {
            "success": False,
            "sandbox_root_path": sandbox_root_path,
            "final_path": "",
            "committed": False,
            "error": f"Invalid final node name: {final_name!r}",
        }

    node = hou.node(sandbox_root_path)
    final_path = f"/obj/{final_name}"
    if node is None:
        return {
            "success": False,
            "sandbox_root_path": sandbox_root_path,
            "final_path": final_path,
            "committed": False,
            "error": f"Sandbox root not found: {sandbox_root_path}",
        }

    existing = hou.node(final_path)
    if existing is not None:
        same_node = existing is node or existing.path() == node.path()
        if same_node:
            pass
        elif not replace_existing:
            return {
                "success": False,
                "sandbox_root_path": sandbox_root_path,
                "final_path": final_path,
                "committed": False,
                "error": f"Final node already exists: {final_path}",
            }
        else:
            try:
                existing.destroy()
            except Exception as e:
                return {
                    "success": False,
                    "sandbox_root_path": sandbox_root_path,
                    "final_path": final_path,
                    "committed": False,
                    "error": f"Failed to replace existing node: {e}",
                    "traceback": traceback.format_exc(),
                }

    # ── G3a: bake gate (spec §4 G3a, decision 1+4) ──
    # The FIRST defense-in-depth layer. When the asset carries @component_id-
    # tagged prims (a real procedural asset), every such prim must also carry
    # a non-zero edini_world_axis — which only build_procedural_asset bakes.
    # A raw network_mode hand-written sandbox that emits component_id geometry
    # has no axis attribute → refused here, before any structure/orientation/
    # health work. Decision 12: the asset stays in the sandbox (no rename, no
    # discard) so the agent can fix and re-commit without rebuilding.
    #
    # Scope: only applies when component_id prims exist. Empty/scaffolding
    # geometry (no component_id) is not a procedural asset — there is nothing
    # to orientation-verify, so the gate passes (parity with the orientation
    # gate, which also no-ops without component_id).
    g3_target = None
    try:
        g3_target = _select_gate_target(node)
    except Exception:
        g3_target = None
    g3_has_component_prims = False
    if g3_target is not None:
        try:
            _g = g3_target.geometry()
            g3_has_component_prims = (
                _g is not None
                and _g.findPrimAttrib("component_id") is not None
                and _g.intrinsicValue("primitivecount") > 0
            )
        except Exception:
            g3_has_component_prims = False
    if g3_has_component_prims:
        g3_baked = True
        g3_missing: list[str] = []
        try:
            g3_baked, g3_missing, _detail = _verify_world_axes_baked(g3_target)
        except Exception as _e:
            g3_baked = False
            g3_missing = [f"<check error: {_e}>"]
        if not g3_baked:
            return {
                "success": False,
                "sandbox_root_path": sandbox_root_path,
                "final_path": final_path,
                "committed": False,
                "refused": True,
                "error": (
                    "G3_NOT_BAKED: asset did not go through "
                    "build_procedural_asset (no edini_world_axis on every "
                    "prim). Raw houdini_run_python_sandbox(network_mode) "
                    "builds cannot pass this gate — they bypass the "
                    f"deterministic axis bake. Missing on: {g3_missing}"
                ),
            }

    # ── Modular structure gate ──
    # Refuse to commit monolithic assets (single Python SOP emitting all
    # multi-component geometry with no Copy-to-Points/Sweep/foreach). This is
    # the structural equivalent of the orientation gate: a hard check that the
    # skill's modular-decomposition requirement is actually followed, not just
    # stated in prose. Empirically, prose-only mandates are ignored.
    structure_result = None
    if not skip_structure_check:
        structure_result = _run_structure_gate(sandbox_root_path)
        if structure_result is not None and not structure_result.get("passed"):
            return {
                "success": False,
                "sandbox_root_path": sandbox_root_path,
                "final_path": final_path,
                "committed": False,
                "error": (
                    "Modular structure check failed — refusing to commit a "
                    "monolithic asset. " + structure_result.get("reason", "") +
                    " Pass skip_structure_check=true ONLY for genuinely simple "
                    "single-piece assets (one fractal, one parametric surface) "
                    "with a documented reason."
                ),
                "structure": structure_result,
            }

    # ── G3b: Orientation gate ──
    # If the agent supplied orientation_checks OR the asset has a component_id
    # attribute, run verify_orientation and refuse to commit on failure.
    orientation_result = None
    if not skip_orientation:
        orientation_result = _run_orientation_gate(
            sandbox_root_path, orientation_checks
        )
        if orientation_result is not None and not orientation_result.get("passed_all"):
            return {
                "success": False,
                "sandbox_root_path": sandbox_root_path,
                "final_path": final_path,
                "committed": False,
                "error": (
                    "G3_ORIENTATION_FAILED: Orientation verification failed — "
                    "refusing to commit. Fix the defects below (each comes "
                    "with a fix quaternion), or pass skip_orientation=true "
                    "only if you have a documented reason."
                ),
                "orientation": orientation_result,
            }

    # ── G3c: geometry-health hard-error gate (decision 7) ──
    # inspect_geometry_health already classifies checks into BLOCKING
    # (orphan_points, open_curves) vs ADVISORY (degenerate/nonmanifold/
    # open_boundary/coincident). Only BLOCKING failures refuse commit;
    # advisory findings are recorded in the receipt but never block (overlapping
    # tubes produce nonmanifold edges + open boundaries that are accepted per
    # decision 2).
    health_result = None
    try:
        from edini.node_utils import inspect_geometry_health
        health_target = _select_gate_target(node)
        if health_target is not None:
            health_result = inspect_geometry_health(health_target.path())
    except Exception as _e:
        health_result = {"success": False, "error": str(_e)}
    if health_result is not None and health_result.get("success"):
        _hard, _soft = _health_hard_soft_summary(health_result)
        if _hard > 0:
            return {
                "success": False,
                "sandbox_root_path": sandbox_root_path,
                "final_path": final_path,
                "committed": False,
                "refused": True,
                "error": (
                    "G3_HEALTH_HARD_ERRORS: geometry health has blocking "
                    f"defects ({_hard} hard error(s), e.g. orphan points or "
                    "stray open curves). Fix them before committing. Advisory "
                    f"findings ({_soft}) are recorded but do not block."
                ),
                "health": health_result,
            }

    try:
        node.setName(final_name, unique_name=False)
    except Exception as e:
        return {
            "success": False,
            "sandbox_root_path": sandbox_root_path,
            "final_path": final_path,
            "committed": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }
    actual_final_path = node.path()

    try:
        node.setDisplayFlag(True)
    except Exception as e:
        return {
            "success": False,
            "sandbox_root_path": sandbox_root_path,
            "final_path": actual_final_path,
            "committed": True,
            "display_error": str(e),
            "display_traceback": traceback.format_exc(),
        }

    # ── Build the tamper-evident verification receipt (spec §5.2) ──
    # The agent's completion report must reference this receipt's fields
    # rather than re-counting geometry. It's a JSON object the tool returns,
    # so the agent cannot rewrite its numbers.
    components_detected: list[str] = []
    axes_baked = True
    try:
        receipt_target = _select_gate_target(node)
        if receipt_target is not None:
            axes_baked, _miss, _det = _verify_world_axes_baked(receipt_target)
            _geo = receipt_target.geometry()
            if _geo is not None:
                components_detected = sorted(_geometry_component_ids(_geo))
    except Exception:
        pass
    receipt = _build_verification_receipt(
        out_node=node,
        orientation=orientation_result,
        health=health_result,
        components_detected=components_detected,
        construction_axes_baked=axes_baked,
    )

    result = {
        "success": True,
        "sandbox_root_path": sandbox_root_path,
        "final_path": actual_final_path,
        "committed": True,
        "verification_receipt": receipt,
    }
    if orientation_result is not None:
        result["orientation"] = orientation_result
    if structure_result is not None:
        result["structure"] = structure_result
    if health_result is not None and health_result.get("success"):
        result["health"] = health_result
    return result


def _select_gate_target(root) -> Any:
    """Pick the SOP node to run orientation checks against.

    The previous implementation took the FIRST child with a non-None geometry
    out of ("edini_generate", "OUT", "out"). That is wrong when
    `edini_generate` is a dispatcher Python SOP that produces empty geometry
    (it builds the network but emits no prims itself) — it satisfies
    `geo is not None` and shadows the real `OUT` output. The gate then fails
    with "component_id not found" even though the verified asset is fine, and
    the agent is forced to pass `skip_orientation=true`.

    Correct selection: among all candidate SOPs under the sandbox root,
    prefer (in order):
      1. a node whose geometry carries the `component_id` prim attribute,
         breaking ties by largest prim count (the real asset output);
      2. else the explicitly-displayed child;
      3. else the child named OUT/out;
      4. else the root itself.
    """
    candidates: list[tuple[int, bool, Any]] = []  # (prim_count, has_cid, node)
    try:
        children = [c for c in root.allSubChildren() if hasattr(c, "geometry")]
    except Exception:
        children = []

    for sub in children:
        try:
            geo = sub.geometry()
            if geo is None:
                continue
        except Exception:
            continue
        try:
            prim_count = geo.intrinsicValue("primitivecount")
        except Exception:
            prim_count = 0
        has_cid = geo.findPrimAttrib("component_id") is not None
        candidates.append((prim_count or 0, bool(has_cid), sub))

    if candidates:
        # Prefer component_id-bearing nodes; within that group prefer the
        # terminal output node (OUT/out) or the *last* node in network order —
        # this is the baked output that actually ships, not an upstream source
        # (e.g. a variant Python SOP that has component_id but no
        # edini_world_axis because the bake happens downstream in idfix).
        with_cid = [c for c in candidates if c[1]]
        pool = with_cid if with_cid else candidates
        # Tier 1: an explicit OUT/out node with component_id.
        for _pc, _has, sub in pool:
            if sub.name().lower() in ("out",):
                return sub
        # Tier 2: prefer the downstream-most (highest creation/network order)
        # component_id node — nodes built later are closer to the output. We
        # approximate 'downstream' by the order in allSubChildren (a
        # depth-first traversal that visits later-built/displayed nodes later),
        # then break ties by prim count. This picks idfix/OUT over variant
        # source Python SOPs.
        if with_cid:
            # Stable index = position in the traversal.
            indexed = {id(sub): i for i, (_pc, _has, sub) in enumerate(candidates)}
            pool.sort(
                key=lambda c: (indexed.get(id(c[2]), 1 << 30), -c[0]))
            return pool[0][2]
        # No component_id anywhere — fall back to the highest-prim node.
        pool_sorted = sorted(pool, key=lambda c: c[0], reverse=True)
        return pool_sorted[0][2]

    # No geometry anywhere — return root (caller handles None geo).
    return root


def _verify_world_axes_baked(out_node) -> tuple[bool, list[str], list[str]]:
    """G2/G3 bake check: confirm every prim on the output carries a non-zero
    edini_world_axis (the deterministic construction axis the builder bakes).

    Decision 11: the zero vector (0,0,0) is the addAttrib default and the
    sentinel for 'not baked' — a legitimate axis always has unit length after
    rotation, so a zero can never be a real construction axis. A prim carrying
    a zero (or the attribute missing entirely) means the build path skipped
    the bake (raw network_mode, or a backend that forgot to wire the bake).

    Returns (all_baked, missing_component_ids, missing_detail):
      all_baked              — True iff every prim has a non-zero axis.
      missing_component_ids  — distinct component_ids whose prims have a zero /
                               absent axis (for the error message).
      missing_detail         — per-prim diagnostic strings (capped for size).
    """
    missing_cids: set[str] = set()
    detail: list[str] = []
    try:
        geo = out_node.geometry()
    except Exception:
        return False, ["<no geometry>"], ["could not read geometry"]
    if geo is None:
        return False, ["<no geometry>"], ["geometry is None"]

    attr = geo.findPrimAttrib("edini_world_axis")
    if attr is None:
        # Attribute missing entirely → every component is unbaked. List the
        # distinct component_ids so the error points at what to fix.
        try:
            for prim in geo.prims():
                cid = ""
                try:
                    cid = str(prim.stringAttribValue("component_id"))
                except Exception:
                    cid = f"prim#{prim.number()}"
                missing_cids.add(cid)
        except Exception:
            missing_cids.add("<unknown>")
        return False, sorted(missing_cids), ["edini_world_axis attribute missing entirely"]

    n_prims_scanned = 0
    for prim in geo.prims():
        n_prims_scanned += 1
        try:
            raw = prim.floatListAttribValue("edini_world_axis")
        except Exception:
            try:
                raw = prim.attribValue("edini_world_axis")
            except Exception:
                raw = None
        if raw is None or len(raw) < 3:
            axis = None
        else:
            axis = (float(raw[0]), float(raw[1]), float(raw[2]))
        if axis is None or axis == (0.0, 0.0, 0.0):
            try:
                cid = str(prim.stringAttribValue("component_id"))
            except Exception:
                cid = f"prim#{prim.number()}"
            missing_cids.add(cid)
            if len(detail) < 20:
                detail.append(f"{cid}: axis {axis}")
    return len(missing_cids) == 0, sorted(missing_cids), detail


def _health_hard_soft_summary(health: dict) -> tuple[int, int]:
    """Map inspect_geometry_health's two-tier output to (hard_errors_count,
    soft_warnings_count) for the verification receipt.

    inspect_geometry_health reports `overall_ok` (driven only by BLOCKING
    checks) plus per-check dicts carrying a `severity` field and a `count`.
    We do NOT change its signature (avoiding churn across 478 tests); the
    receipt just sums the counts by severity tier.

      hard_errors_count = sum of counts for BLOCKING checks that did NOT pass
                          (orphan_points, open_curves)
      soft_warnings     = sum of counts for ADVISORY checks
                          (degenerate, nonmanifold, open_boundary, coincident)
    """
    if not isinstance(health, dict) or not health.get("success"):
        # Health check itself failed -> treat as a hard error (conservative).
        return 1, 0
    checks = health.get("checks", {}) or {}
    hard = 0
    soft = 0
    for name, chk in checks.items():
        if not isinstance(chk, dict):
            continue
        severity = chk.get("severity", "blocking")
        count = int(chk.get("count", 0))
        if severity == "blocking":
            # Only count it as a hard error if it actually failed.
            if not chk.get("passed", False):
                hard += count if count > 0 else 1
        else:
            soft += count
    return hard, soft


def _build_verification_receipt(
    out_node,
    orientation: dict | None,
    health: dict | None,
    components_detected: list[str] | None = None,
    construction_axes_baked: bool = True,
    defaulted_axes: dict | None = None,
) -> dict[str, Any]:
    """Build a tamper-evident verification receipt (spec §5.2).

    The agent's completion report MUST reference fields from this receipt
    rather than re-counting geometry itself — the receipt is a JSON object
    returned by the tool, so the agent cannot rewrite its numbers. The agent
    can only choose to omit a failure, but the receipt stays complete in the
    tool result the user can see.
    """
    hard_errors, soft_warnings = _health_hard_soft_summary(health or {})
    ori = orientation or {}
    health_dict = health or {}
    ori_failed = ori.get("failed", 0)
    receipt = {
        "passed": (ori_failed == 0 and hard_errors == 0),
        "orientation": {
            "passed": ori.get("passed", 0),
            "failed": ori_failed,
            "total": ori.get("total", 0),
            "failures": [c for c in ori.get("checks", []) if not c.get("passed")],
        },
        "health": {
            "overall_ok": health_dict.get("overall_ok", False),
            "hard_errors_count": hard_errors,
            "soft_warnings": soft_warnings,
            "blocking_checks": health_dict.get("blocking_checks", []),
            "advisory_checks": health_dict.get("advisory_checks", []),
        },
        "components_detected": components_detected or [],
        "construction_axes_baked": construction_axes_baked,
        "defaulted_axes": defaulted_axes or {},
        "timestamp": _dt.datetime.now().isoformat(timespec="seconds"),
    }
    return receipt


# Presence of ANY of these means the asset uses proper modular patterns.
_MODULAR_NODE_TYPES = {
    "copytopoints", "copytopoints::2.0", "copy", "copystamp",
    "sweep", "sweep::2.0", "skin", "rails",
    "foreach::count", "foreach::piece", "foreach", "foreach_begin",
    "xformpieces", "transformpieces", "instanceto",
    "boolean", "boolean::2.0", "polyextrude", "polyextrude::2.0",
    # Variant-scatter chain: pack(packbyname) builds per-variant packed
    # prims; unpack restores per-prim geometry so idfix can write per-instance
    # component_id. Copy to Points dispatches by matching i@variant and
    # transfers target-point `id` via Apply Attributes.
    "pack", "unpack",
}

# SOP node types that are pure post-processing (don't count toward modularity).
_POSTPROCESS_NODE_TYPES = {
    "normal", "polybevel", "polybevel::3.0", "subdivide", "facet",
    "clean", "null", "merge", "blast", "group", "attribwrangle",
    "attribpromote", "attribcreate", "transform", "xform",
    "display", "output", "out", "edini_generate",
}


def _node_type_name(node) -> str:
    """Return the bare type name (without namespace/version suffix)."""
    try:
        return node.type().name()
    except Exception:
        return ""


def _node_type_components(node) -> str:
    """Return the type name with namespace, lowercased for matching."""
    try:
        # type().nameWithCategory() or the full type name including version
        return node.type().name().lower()
    except Exception:
        return ""


def _python_sop_code_line_count(node) -> int:
    """Count lines of the 'python' parm on a python SOP (0 if not python)."""
    try:
        if node.type().name() != "python":
            return 0
        code = node.evalParm("python") or ""
        return code.count("\n") + 1
    except Exception:
        return 0


def _geometry_component_ids(geo) -> set[str]:
    """Return the set of distinct component_id prim attribute values."""
    ids: set[str] = set()
    try:
        attr = geo.findPrimAttrib("component_id")
        if attr is None:
            return ids
        for prim in geo.prims():
            try:
                v = str(prim.stringAttribValue("component_id"))
                if v:
                    ids.add(v)
            except Exception:
                continue
    except Exception:
        pass
    return ids


def _check_modular_structure(root) -> dict[str, Any]:
    """Detect monolithic procedural assets that violate modular decomposition.

    A procedural asset is MONOLITHIC (a failure mode) when:
      - It has multiple distinct geometric components (component_id >= 3
        distinct values), AND
      - All of those components' geometry originates from a SINGLE Python SOP,
        AND
      - There are NO modular assembly nodes (copytopoints/sweep/foreach/
        boolean/polyextrude) in the network.

    This combination means the agent stuffed the entire asset into one big
    Python script instead of decomposing it into swappable sub-components
    connected via Copy-to-Points/Sweep — which the skill explicitly forbids
    ("No monolithic Python SOPs > 200 lines").

    Returns {is_monolithic, reason, suggestion, details}.
    `is_monolithic=False` means the structure is acceptable (either genuinely
    simple, or properly modular).
    """
    result: dict[str, Any] = {
        "is_monolithic": False,
        "reason": "",
        "suggestion": "",
        "details": {},
    }

    # Gather all child SOP nodes under the sandbox root
    try:
        children = [c for c in root.allSubChildren() if hasattr(c, "geometry")]
    except Exception:
        children = []

    python_sops = []
    modular_nodes = []
    generator_sops = []  # nodes that produce geometry (not post-process)
    type_counts: dict[str, int] = {}

    for child in children:
        tname = _node_type_name(child)
        tcomp = _node_type_components(child)
        type_counts[tcomp] = type_counts.get(tcomp, 0) + 1

        if tname == "python":
            python_sops.append(child)
        # Match modular types (bare name or namespaced)
        if any(tcomp == m or tcomp.startswith(m + "::") for m in _MODULAR_NODE_TYPES):
            modular_nodes.append(child)
        # Generator = produces geometry but isn't pure post-process
        if tcomp not in _POSTPROCESS_NODE_TYPES and tname not in ("",):
            # python SOPs are generators too (counted separately above)
            if tname != "python":
                generator_sops.append(child)

    # Find which Python SOP(s) actually emit the component_id geometry
    component_sources: dict[str, set[str]] = {}  # node_path -> set of cids
    all_cids: set[str] = set()
    for child in children:
        try:
            geo = child.geometry()
            if geo is None:
                continue
        except Exception:
            continue
        cids = _geometry_component_ids(geo)
        if cids:
            component_sources[child.path()] = cids
            all_cids |= cids

    result["details"] = {
        "python_sop_count": len(python_sops),
        "python_sop_max_lines": max(
            (_python_sop_code_line_count(p) for p in python_sops), default=0),
        "modular_node_count": len(modular_nodes),
        "modular_node_types": [n.type().name() for n in modular_nodes],
        "distinct_component_ids": len(all_cids),
        "component_source_count": len(component_sources),
        "node_type_counts": type_counts,
    }

    # ── Monolithic判定 ──
    # Condition set: multi-component + single source + no modular nodes
    multi_component = len(all_cids) >= 3
    single_python_source = (
        len([p for p in python_sops if p.path() in component_sources]) >= 1
        and len(component_sources) <= 2  # at most the generator + the merge/OUT passthrough
    )
    # The "single source" check: do all component_ids come from python SOPs
    # (rather than from separate copytopoints-driven component streams)?
    python_paths = {p.path() for p in python_sops}
    cids_from_python: set[str] = set()
    for src_path, cids in component_sources.items():
        if src_path in python_paths:
            cids_from_python |= cids
    all_cids_from_one_python = (
        len(python_sops) >= 1
        and len(cids_from_python) >= 3
        and len(all_cids - cids_from_python) == 0
    )
    no_modular = len(modular_nodes) == 0

    big_python = result["details"]["python_sop_max_lines"] > 200

    if multi_component and all_cids_from_one_python and no_modular:
        result["is_monolithic"] = True
        result["reason"] = (
            f"Asset has {len(all_cids)} distinct components (component_id) but "
            f"all geometry originates from a single Python SOP "
            f"(max {result['details']['python_sop_max_lines']} lines), with no "
            f"modular assembly nodes (copytopoints/sweep/foreach/boolean). "
            f"This is a monolithic structure — the skill requires modular "
            f"decomposition for multi-component assets."
        )
        result["suggestion"] = (
            "Decompose into separate component generators connected via "
            "Copy-to-Points: (1) a body_generate Python SOP that outputs anchor "
            "points with @component_id/@orient/@pscale, (2) separate Python SOPs "
            "for each swappable sub-component (wheel, saddle, handlebar), "
            "(3) Copy-to-Points nodes to instance sub-components onto anchors, "
            "(4) merge + OUT. For tube/frame shapes, use Sweep 2.0 with profile "
            "curves instead of hand-building every face in Python. "
            "Pass skip_structure_check=true ONLY for genuinely simple single-piece "
            "assets (one fractal, one parametric surface)."
        )
    elif big_python and multi_component and no_modular:
        # Softer signal: big python SOP even if cid sourcing is ambiguous
        result["is_monolithic"] = True
        result["reason"] = (
            f"Single Python SOP of {result['details']['python_sop_max_lines']} "
            f"lines producing a {len(all_cids)}-component asset with no modular "
            f"assembly nodes. Decompose per the modular pattern."
        )
        result["suggestion"] = (
            "Split into body_generate + per-component generators + Copy-to-Points.")

    return result


def _run_structure_gate(
    sandbox_root_path: str,
) -> dict[str, Any] | None:
    """Run the modular-structure check against the sandbox.

    Returns None if the sandbox can't be analyzed. Otherwise returns a dict
    with `passed` (True = structure OK, False = monolithic) and the check
    details + fix guidance.
    """
    root = hou.node(sandbox_root_path)
    if root is None:
        return None

    check = _check_modular_structure(root)
    return {
        "passed": not check["is_monolithic"],
        "is_monolithic": check["is_monolithic"],
        "reason": check["reason"],
        "suggestion": check["suggestion"],
        "details": check["details"],
    }


def _run_orientation_gate(
    sandbox_root_path: str,
    orientation_checks: list[dict] | None,
) -> dict[str, Any] | None:
    """Run verify_orientation against the sandbox display node.

    Returns None if no checks are available (no `component_id` attribute and
    no explicit `orientation_checks` supplied). Otherwise returns the
    verification summary with `passed_all` set.
    """
    from edini.node_utils import verify_orientation

    # Find the actual cook output — sandbox_root_path is a container; the
    # display node inside is typically `edini_generate` or the root itself.
    root = hou.node(sandbox_root_path)
    if root is None:
        return None

    target = _select_gate_target(root)

    try:
        geo = target.geometry()
    except Exception:
        return None
    if geo is None:
        return None

    has_component_id = geo.findPrimAttrib("component_id") is not None
    if not orientation_checks and not has_component_id:
        # No checks to run; agent didn't declare any, asset has no component_id
        return None

    checks = orientation_checks or []
    if not checks:
        # Asset has component_id but agent didn't declare expected axes.
        # Don't block commit silently — return an advisory result.
        avail = sorted(set(
            str(p.stringAttribValue("component_id"))
            for p in geo.prims()
            if p.stringAttribValue("component_id")
        ))[:20]
        return {
            "passed_all": True,
            "advisory": (
                "Asset has @component_id attribute but no orientation_checks "
                "were supplied to commit_sandbox. Add orientation_checks for: "
                f"{avail}. Set skip_orientation=true to silence this advisory."
            ),
            "available_component_ids": avail,
        }

    result = verify_orientation(target.path(), checks)
    if not result.get("success"):
        return {
            "passed_all": False,
            "error": result.get("error", "verify_orientation failed"),
            "details": result,
        }

    return {
        "passed_all": result.get("failed", 1) == 0,
        "passed": result.get("passed", 0),
        "failed": result.get("failed", 0),
        "total": result.get("total", 0),
        "checks": result.get("checks", []),
    }


def _create_sandbox_root(sandbox_name: str) -> tuple[str, str]:
    job_id = make_job_id(sandbox_name)
    root_name = f"edini_sandbox_{job_id}"
    obj = hou.node("/obj")
    if obj is None:
        raise RuntimeError("No /obj context")
    root = obj.createNode("geo", root_name)
    return job_id, root.path()


def _destroy_node(path: str) -> None:
    node = hou.node(path)
    if node is not None:
        node.destroy()


def _safe_getvalue(stream) -> str:
    try:
        return stream.getvalue()
    except Exception as e:
        return f"<capture unavailable: {e}>"


def _bounds_nonzero(geo_stats: dict[str, Any]) -> bool:
    """True if the geometry's bounding box has a non-zero size.

    Defensive against `bounds` being None / missing (e.g. empty geometry),
    which the bare `.get("bounds", {}).get("size")` expression chokes on when
    the key exists but maps to None.
    """
    bounds = geo_stats.get("bounds") or {}
    size = bounds.get("size")
    return isinstance(size, list) and any(abs(c) > 1e-6 for c in size)


def _resolve_output_node(sandbox_root, prefer_names=("OUT", "out")) -> Any:
    """Pick the cooked output node for a network-mode sandbox.

    Priority:
      1. A node named OUT/out (the conventional merge target).
      2. The node carrying the @component_id prim attribute with the most prims
         (the real merged asset output).
      3. The sandbox_root itself.
    """
    try:
        children = [c for c in sandbox_root.allSubChildren() if hasattr(c, "geometry")]
    except Exception:
        children = []

    for pref in prefer_names:
        for sub in children:
            if sub.name() == pref:
                return sub

    best = None
    best_score = -1
    for sub in children:
        try:
            geo = sub.geometry()
            if geo is None:
                continue
        except Exception:
            continue
        try:
            prim_count = geo.intrinsicValue("primitivecount") or 0
        except Exception:
            prim_count = 0
        try:
            has_cid = geo.findPrimAttrib("component_id") is not None
        except Exception:
            has_cid = False
        score = prim_count + (1000000 if has_cid else 0)
        if score > best_score:
            best, best_score = sub, score
    return best if best is not None else sandbox_root


def run_python_sandbox(
    code: str,
    sandbox_name: str = "procedural",
    commit_on_success: bool = False,
    delete_on_failure: bool = False,
    network_mode: bool = False,
    output_node_name: str | None = None,
) -> dict[str, Any]:
    """Run Python in a procedural sandbox and return diagnostics + structure.

    Two execution modes:

    - **Single-SOP mode (default, ``network_mode=False``):** the code runs as
      the cook body of a single ``edini_generate`` Python SOP. The code body
      can only call ``geo.createPoint()`` / ``geo.createPolygon()`` on the
      cooking node's own geometry — it MUST NOT create child SOPs, because
      cooking a node that creates network nodes triggers Houdini's
      "Infinite recursion in evaluation" guard. Use this for single-piece
      generators (one fractal, one parametric surface) or short scripts.

    - **Network mode (``network_mode=True``):** the code runs directly in the
      sandbox geo container (``hou.node(root_path)``) — NOT inside a Python
      SOP cook. This lets the code build a multi-node modular network
      (``container.createNode("python", "body_generate")``,
      ``container.createNode("copytopoints", ...)``) and wire them up exactly
      as the modular pattern requires. After the build runs, the harness
      locates the OUT node (an explicit ``output_node_name``, else a node
      named ``OUT``/``out``, else the largest component_id-bearing node) and
      cooks it. This is the mode that lets modular assets go through the
      sandbox → commit structure/orientation gates.

    In network mode, ``hou.pwd()`` returns the sandbox root geo, and the
    helper variable ``sandbox_root`` is the geo container node.
    """
    job_id, root_path = _create_sandbox_root(sandbox_name)

    sandbox_root = hou.node(root_path)

    if network_mode:
        # Build a multi-node network by running the code in the container
        # context. The code is expected to create children of sandbox_root
        # (e.g. body_generate, wheel_component, copytopoints, merge, OUT)
        # and return control. We then find + cook the OUT node.
        output_node_path = ""
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = stdout_capture
        sys.stderr = stderr_capture

        try:
            namespace: dict[str, Any] = {
                "hou": hou,
                "sandbox_root": sandbox_root,
                "sandbox_root_path": root_path,
                "job_id": job_id,
                "result": {},  # convenience capture dict (parity with single-SOP mock)
            }
            # Set hou.pwd() so existing recipes that use hou.pwd() land in the
            # sandbox container rather than the top-level hou.node("/obj").
            try:
                old_pwd = hou.pwd()
            except Exception:
                old_pwd = None
            try:
                if hasattr(hou, "_set_pwd"):
                    hou._set_pwd(sandbox_root)
                else:
                    hou._pwd_path = root_path  # type: ignore[attr-defined]
            except Exception:
                pass

            try:
                exec(code, namespace)
            finally:
                # Restore pwd
                try:
                    if hasattr(hou, "_set_pwd"):
                        hou._set_pwd(old_pwd)
                    else:
                        if old_pwd is None:
                            hou._pwd_path = ""  # type: ignore[attr-defined]
                        else:
                            hou._pwd_path = old_pwd.path()  # type: ignore[attr-defined]
                except Exception:
                    pass

            # Locate the output node to cook + diagnose.
            if output_node_name:
                target = hou.node(f"{root_path}/{output_node_name}")
                if target is None:
                    # Fall back to a subchild search by name.
                    target = hou.node(output_node_name) if output_node_name.startswith("/") else None
            else:
                target = None
            if target is None:
                target = _resolve_output_node(sandbox_root)
            output_node_path = target.path()

            # Cook the output node so geometry/structure gates see real data.
            target.cook(force=True)
            cook_errors = list(target.errors() or [])
            cook_warnings = list(target.warnings() or [])
            if cook_errors:
                raise RuntimeError("; ".join(cook_errors))

            # Layout the built network so it's readable in the network editor.
            try:
                sandbox_root.layoutChildren()
            except Exception:
                pass

            diag = _safe_collect_diagnostics(
                output_node_path,
                include_geometry=True,
                include_parms=False,
            )
            geo_stats = diag.get("geometry") or {}
            structural_checks = {
                "has_geometry": geo_stats.get("point_count", 0) > 0,
                "point_count": geo_stats.get("point_count", 0),
                "prim_count": geo_stats.get("prim_count", 0),
                "bounds_nonzero": _bounds_nonzero(geo_stats),
            }

            response = {
                "success": True,
                "job_id": job_id,
                "execution_mode": EXECUTION_MODE_LIVE,
                "sandbox_mode": "network",
                "root_path": root_path,
                "output_node": output_node_path,
                "output": _safe_getvalue(stdout_capture) or "(no output)",
                "stderr": _safe_getvalue(stderr_capture),
                "diagnostics": diag,
                "structural_checks": structural_checks,
                "commit_requested": bool(commit_on_success),
                "committed": False,
            }

            try:
                struct_check = _run_structure_gate(root_path)
                if struct_check is not None:
                    response["structure_advisory"] = struct_check
            except Exception:
                pass

            if commit_on_success:
                commit_result = commit_sandbox(root_path, sandbox_name)
                response["committed"] = commit_result.get("committed", False)
                if commit_result.get("success"):
                    response["final_path"] = commit_result.get("final_path", "")
                else:
                    response["commit_error"] = commit_result.get("error", "")

            return response

        except Exception as e:
            execution_traceback = traceback.format_exc()
            # On failure, output_node_path is often still "" (the assignment at
            # line 1281 hasn't run yet). Falling back to root_path diagnoses the
            # geo *container* (an ObjNode), whose .geometry() call used to raise
            # a second AttributeError nested under the agent's real traceback.
            # Instead, try to resolve the most-downstream SOP already built so
            # the agent sees partial geometry diagnostics; only if none exists
            # do we fall through to root_path (and geometry_stats now handles
            # that ObjNode case gracefully via the hasattr guard).
            diag_path = output_node_path
            if not diag_path:
                resolved = _resolve_output_node(sandbox_root)
                diag_path = (
                    resolved.path() if resolved is not sandbox_root else root_path
                )
            diagnostics = _safe_collect_diagnostics(
                diag_path,
                include_geometry=True,
                include_parms=False,
            )
            geo_stats = diagnostics.get("geometry") or {}
            structural_checks = {
                "has_geometry": geo_stats.get("point_count", 0) > 0,
                "point_count": geo_stats.get("point_count", 0),
                "prim_count": geo_stats.get("prim_count", 0),
                "bounds_nonzero": False,
            }

            deleted = False
            delete_error = None
            delete_traceback = None
            if delete_on_failure:
                try:
                    _destroy_node(root_path)
                    deleted = True
                except Exception as cleanup_exc:
                    delete_error = str(cleanup_exc)
                    delete_traceback = traceback.format_exc()

            response = {
                "success": False,
                "job_id": job_id,
                "execution_mode": EXECUTION_MODE_LIVE,
                "sandbox_mode": "network",
                "root_path": root_path,
                "output_node": output_node_path,
                "error": str(e),
                "output": _safe_getvalue(stdout_capture),
                "stderr": _safe_getvalue(stderr_capture),
                "traceback": execution_traceback,
                "diagnostics": diagnostics,
                "structural_checks": structural_checks,
                "preserved": not deleted,
                "deleted": deleted,
                "commit_requested": bool(commit_on_success),
                "committed": False,
            }
            if delete_error is not None:
                response["delete_error"] = delete_error
                response["delete_traceback"] = delete_traceback
            return response
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

    # ── Default: single-SOP mode ──
    # Create Python SOP inside sandbox
    py_sop = sandbox_root.createNode("python", "edini_generate")
    py_sop.parm("python").set(code)
    output_node_path = py_sop.path()

    # Capture stdout/stderr from cooking
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    sys.stdout = stdout_capture
    sys.stderr = stderr_capture

    try:
        py_sop.cook(force=True)
        cook_errors = list(py_sop.errors() or [])
        cook_warnings = list(py_sop.warnings() or [])

        if cook_errors:
            raise RuntimeError("; ".join(cook_errors))

        # Build diagnostics (always, for both success and failure)
        diag = _safe_collect_diagnostics(
            output_node_path,
            include_geometry=True,
            include_parms=False,
        )

        # Build structural checks summary
        geo_stats = diag.get("geometry") or {}
        structural_checks = {
            "has_geometry": geo_stats.get("point_count", 0) > 0,
            "point_count": geo_stats.get("point_count", 0),
            "prim_count": geo_stats.get("prim_count", 0),
            "bounds_nonzero": _bounds_nonzero(geo_stats),
        }

        response = {
            "success": True,
            "job_id": job_id,
            "execution_mode": EXECUTION_MODE_LIVE,
            "sandbox_mode": "single_sop",
            "root_path": root_path,
            "output_node": output_node_path,
            "output": _safe_getvalue(stdout_capture) or "(no output)",
            "stderr": _safe_getvalue(stderr_capture),
            "diagnostics": diag,
            "structural_checks": structural_checks,
            "commit_requested": bool(commit_on_success),
            "committed": False,
        }

        # Surface the modular-structure advisory early so the agent can fix a
        # monolithic build BEFORE attempting to commit (the commit gate would
        # otherwise reject it). This is advisory — it doesn't block the sandbox.
        try:
            struct_check = _run_structure_gate(root_path)
            if struct_check is not None:
                response["structure_advisory"] = struct_check
        except Exception:
            pass

        if commit_on_success:
            commit_result = commit_sandbox(root_path, sandbox_name)
            response["committed"] = commit_result.get("committed", False)
            if commit_result.get("success"):
                response["final_path"] = commit_result.get("final_path", "")
            else:
                response["commit_error"] = commit_result.get("error", "")

        return response

    except Exception as e:
        execution_traceback = traceback.format_exc()
        diagnostics = _safe_collect_diagnostics(
            output_node_path, include_geometry=True, include_parms=False,
        )
        geo_stats = diagnostics.get("geometry") or {}
        structural_checks = {
            "has_geometry": geo_stats.get("point_count", 0) > 0,
            "point_count": geo_stats.get("point_count", 0),
            "prim_count": geo_stats.get("prim_count", 0),
            "bounds_nonzero": False,
        }

        deleted = False
        delete_error = None
        delete_traceback = None
        if delete_on_failure:
            try:
                _destroy_node(root_path)
                deleted = True
            except Exception as cleanup_exc:
                delete_error = str(cleanup_exc)
                delete_traceback = traceback.format_exc()

        response = {
            "success": False,
            "job_id": job_id,
            "execution_mode": EXECUTION_MODE_LIVE,
            "sandbox_mode": "single_sop",
            "root_path": root_path,
            "output_node": output_node_path,
            "error": str(e),
            "output": _safe_getvalue(stdout_capture),
            "stderr": _safe_getvalue(stderr_capture),
            "traceback": execution_traceback,
            "diagnostics": diagnostics,
            "structural_checks": structural_checks,
            "preserved": not deleted,
            "deleted": deleted,
            "commit_requested": bool(commit_on_success),
            "committed": False,
        }
        if delete_error is not None:
            response["delete_error"] = delete_error
            response["delete_traceback"] = delete_traceback
        return response
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr


# ─────────────────────────────────────────────────────────────────────────────
# Declarative recipe builder (A-station)
#
# The builder turns a JSON recipe (component list + anchor list + per-component
# pure-geometry python code) into a deterministic multi-node modular network.
# The agent never writes createNode / setInput / wiring / blockpath — it only
# authors the geometry-generating code for each component. This removes the
# whole class of imperative-Houdini-API errors (infinite recursion in cook,
# foreach blockpath mis-wires, parm-name guesses) that dominated the bicycle
# run log.
#
# The built network reuses the existing sandbox lifecycle + gates unchanged:
#   - OUT is downstream of the merge → _select_gate_target auto-finds it
#   - every component prim carries component_id (Prim) → verify_orientation
#     + _check_modular_structure run on commit without any gate changes
# ─────────────────────────────────────────────────────────────────────────────


def _build_float_parm_template(
    hou_module,
    name: str,
    label: str,
    default: float,
    min_v: float,
    max_v: float,
) -> Any:
    """Construct a hou.FloatParmTemplate across H18-H21 signature variance.

    The default_value argument is the pain point: it is typed as
    ``std::vector<double>`` in SWIG, and H21 rejects a single-element tuple
    ``(d,)`` with a confusing "argument 4 of type std::vector" error. The
    reliable forms are a flat ``vector<double>`` (a Python list ``[d]``) for
    the positional default, or the keyword ``default_value`` form. We try the
    documented keyword signature first (most stable), then positional forms
    known to work on each major version, then set min/max after construction.
    """
    # Candidate constructors, most-documented first. Each returns a template
    # or raises; the caller picks the first that succeeds.
    candidates = (
        # H20/H21 documented keyword form (default_value expects vector<double>).
        lambda: hou_module.FloatParmTemplate(
            name, label, 1,
            default_value=[default],
            min=min_v, max=max_v,
            min_str=str(min_v), max_str=str(max_v),
            naming_scheme=hou_module.parmNamingScheme.Base1,
            look=hou_module.parmLook.Regular,
            naming=hou_module.parmNaming.Base1),
        # positional vector default (H19/H20/H21 all accept a list).
        lambda: hou_module.FloatParmTemplate(name, label, 1, [default], min_v, max_v),
        # positional with default only (set bounds after).
        lambda: hou_module.FloatParmTemplate(name, label, 1, [default]),
        # bare name/label/components (oldest form).
        lambda: hou_module.FloatParmTemplate(name, label, 1),
    )
    tmpl = None
    last_exc = None
    for ctor in candidates:
        try:
            tmpl = ctor()
            break
        except Exception as e:
            last_exc = e
            continue
    if tmpl is None:
        raise RuntimeError(
            f"FloatParmTemplate({name!r}) could not be constructed on this "
            f"Houdini build; last error: {last_exc}")
    # Ensure bounds regardless of which ctor path won (some forms ignore
    # min/max on construction and need explicit setters).
    try:
        tmpl.setMin(min_v)
        tmpl.setMax(max_v)
        tmpl.setMinValueStr(str(min_v))
        tmpl.setMaxValueStr(str(max_v))
    except Exception:
        pass
    return tmpl


def _install_params_via_template_group(
    root: Any, hou_module: Any, templates: list[Any],
    grouping: list[tuple[str, str, bool]] | None = None,
) -> bool:
    """Install templates as merge folder(s) on root via setParmTemplateGroup.

    Uses the Houdini-official read-merge pattern: read the node's existing
    ParmTemplateGroup (preserving the geo's default Transform etc. folders),
    add the templates inside FolderParmTemplate(s), then write it back.
    This is H21-compatible on a non-HDA geo container, unlike
    setSpareParmGroup which is restricted there. Returns True on success.

    Args:
        templates: ordered FloatParmTemplate list.
        grouping: optional parallel list of ``(parm_name, group, is_derived)``
            tuples, same length/order as ``templates``. When provided, parms
            are placed into per-group folders (a folder per distinct group
            name). Derived params go into a dedicated folder whose label is
            suffixed "(auto)" so the user knows not to edit them. When None
            (legacy callers), everything lands in one ``edini_params`` folder.

    Note: this is a REPLACE-style API at the hou level, but because we read
    the current group first and only append our folder, it is merge-safe —
    pre-existing folders and parms are preserved.
    """
    ptg = root.parmTemplateGroup()
    if grouping is not None and len(grouping) == len(templates):
        # Build folders: primary groups in declared order, then a trailing
        # "(auto)" folder for derived params so they're visually separated
        # and the main controls stay uncluttered.
        primary_order: list[str] = []
        seen: set[str] = set()
        derived_group = "Derived (auto)"
        buckets: dict[str, list[Any]] = {}
        for (pname, group, is_derived), tmpl in zip(grouping, templates):
            g = derived_group if is_derived else (group or "Parameters")
            if is_derived:
                g = derived_group
            if g not in seen:
                seen.add(g)
                if not is_derived:
                    primary_order.append(g)
                buckets[g] = []
            buckets[g].append(tmpl)
        # Append primary folders first (in first-seen order), derived last.
        ordered_groups = primary_order + (
            [derived_group] if derived_group in buckets else [])
        for g in ordered_groups:
            folder = hou_module.FolderParmTemplate(
                f"edini_{_sanitize_folder_name(g)}", g,
                folder_type=getattr(hou_module.folderType, "Tabs", 0),
            )
            for tmpl in buckets[g]:
                folder.addParmTemplate(tmpl)
            ptg.append(folder)
    else:
        folder = hou_module.FolderParmTemplate(
            "edini_params", "Parameters",
            folder_type=getattr(hou_module.folderType, "Tabs", 0),
        )
        for tmpl in templates:
            folder.addParmTemplate(tmpl)
        ptg.append(folder)
    root.setParmTemplateGroup(ptg)
    return True


def add_parm(
    node_path: str,
    name: str,
    type: str = "float",
    default: float = 0.0,
    min: float = 0.0,
    max: float = 10.0,
    label: str = "",
) -> dict[str, Any]:
    """Add a spare parameter to any Houdini node.

    Creates a FloatParmTemplate on the target node using the H21-compatible
    read-merge pattern. Returns the channel path so component code can
    reference it via hou.ch().

    Args:
        node_path: Absolute path like "/obj/road_bike_phase1"
        name: Parameter name (e.g. "wheel_radius")
        type: "float" (only float supported currently)
        default: Default value
        min: Minimum slider value
        max: Maximum slider value
        label: UI label (defaults to name)

    Returns:
        {"success": True, "channel_path": "/obj/.../wheel_radius",
         "node_path": "...", "parm_name": "...", "value": 0.5}
    """
    import hou as _hou
    node = _hou.node(node_path)
    if node is None:
        return {"success": False, "error": f"Node not found: {node_path}"}
    if not name or not name.strip():
        return {"success": False, "error": "name must be a non-empty string"}
    name = name.strip()
    lbl = label.strip() if label else name
    try:
        # Check if parm already exists
        existing = node.parm(name)
        if existing is not None:
            return {
                "success": True,
                "already_exists": True,
                "node_path": node_path,
                "parm_name": name,
                "channel_path": f"{node_path}/{name}",
                "value": existing.eval(),
            }
        # Build template
        tmpl = _build_float_parm_template(_hou, name, lbl, float(default), float(min), float(max))
        installed = _install_params_via_template_group(node, _hou, [tmpl])
        if not installed:
            # Fall back to legacy spare parm group
            try:
                grp = _hou.ParmTemplateGroup()
                grp.appendToFolder("Spare", tmpl)
                node.setSpareParmGroup(grp)
                installed = True
            except Exception:
                pass
        if not installed:
            return {"success": False, "error": f"Could not install parm '{name}' on {node_path}"}
        # Set expression to None (use raw value)
        p = node.parm(name)
        if p is not None:
            p.set(float(default))
        return {
            "success": True,
            "node_path": node_path,
            "parm_name": name,
            "channel_path": f"{node_path}/{name}",
            "value": float(default),
            "label": lbl,
        }
    except Exception as e:
        return {"success": False, "error": f"add_parm('{name}') failed: {e}"}


def _sanitize_folder_name(label: str) -> str:
    """Sanitize a UI group label into a legal FolderParmTemplate symbol name.

    Folder symbol names (the first FolderParmTemplate arg) must be identifiers;
    the label (second arg) can be any display text. We sanitize the symbol so
    group names like "Wheels & Frame" become a stable ``edini_Wheels___Frame``.
    """
    import re
    return re.sub(r"[^A-Za-z0-9_]", "_", label)


# ── Parm Catalog ────────────────────────────────────────────

def dump_parm_catalog(
    output_path: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Generate (or load cached) the Houdini parm catalog.

    Called once per session/project. Phase A validation uses this catalog
    as ground truth — no cook required.

    Args:
        output_path: Where to write the catalog JSON. Defaults to
                     <edini>/python3.11libs/edini/data/parm-catalog.json
        force: If True, regenerate even if cached catalog exists.
    Returns:
        {"success": true, "path": "...", "sop_count": N, "version": "21.0.440"}
    """
    import json
    import os

    if output_path is None:
        output_path = os.path.join(
            os.path.dirname(__file__), "data", "parm-catalog.json"
        )
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    if not force and os.path.exists(output_path):
        existing = _try_load_catalog(output_path)
        if existing:
            return {"success": True, "path": output_path, "regenerated": False, **existing}

    catalog = _generate_and_save_catalog(output_path)
    return {"success": True, "path": output_path, "regenerated": True, **catalog}


def _try_load_catalog(path: str) -> dict | None:
    import json
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        sop_count = sum(1 for _ in data.get("Sop", {}))
        return {"sop_count": sop_count, "version": data.get("houdini_version")}
    except Exception:
        return None


def _generate_and_save_catalog(output_path: str) -> dict:
    import json
    from edini.parm_catalog import ParmCatalog

    raw = ParmCatalog.generate_catalog()
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(raw, f, indent=2, ensure_ascii=False)
    sop_count = sum(1 for _ in raw.get("Sop", {}))
    return {"sop_count": sop_count, "version": raw.get("houdini_version")}


