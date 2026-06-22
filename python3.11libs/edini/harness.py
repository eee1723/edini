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
            diagnostics = _safe_collect_diagnostics(
                output_node_path or root_path,
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


def _validate_recipe(recipe: Any) -> list[str]:
    """Return a list of human-readable errors for an invalid recipe (empty = OK).

    Validates structure only — not geometry (that is checked post-cook by the
    component_id presence check).
    """
    errors: list[str] = []
    if not isinstance(recipe, dict):
        return ["recipe must be a JSON object"]

    components = recipe.get("components")
    if not isinstance(components, list) or not components:
        errors.append("recipe.components must be a non-empty list")
        return errors

    # ▬ Asset-level shared parameters (A2-station, optional) ▬
    # params: {name: {default, min?, max?, label?}}. When present, the builder
    # installs them as spare parms on the sandbox root so a change to any one
    # propagates to every component that reads it (true asset linkage).
    param_names: set[str] = set()
    params = recipe.get("params")
    if params is not None:
        if not isinstance(params, dict):
            errors.append("recipe.params must be an object if present")
        elif params:  # non-empty dict → validate entries
            for pname, pspec in params.items():
                if not isinstance(pname, str) or not pname.strip():
                    errors.append(f"recipe.params key {pname!r} must be a non-empty string")
                    continue
                if pname in param_names:
                    errors.append(f"recipe.params key {pname!r} duplicates")
                    continue
                param_names.add(pname)
                if not isinstance(pspec, dict):
                    errors.append(f"recipe.params[{pname!r}] must be an object")
                    continue
                kind = pspec.get("kind", "primary")
                if kind != "derived":
                    if "default" not in pspec or not isinstance(pspec["default"], (int, float)) \
                            or isinstance(pspec["default"], bool):
                        errors.append(
                            f"recipe.params[{pname!r}].default must be a number")
                else:
                    if "from" not in pspec or not isinstance(pspec["from"], str) \
                            or not pspec["from"].strip():
                        errors.append(
                            f"recipe.params[{pname!r}] (derived) requires 'from' expression")
                for bound in ("min", "max"):
                    if bound in pspec and (not isinstance(pspec[bound], (int, float))
                                           or isinstance(pspec[bound], bool)):
                        errors.append(
                            f"recipe.params[{pname!r}].{bound} must be a number if present")

    seen_ids: set[str] = set()
    for i, comp in enumerate(components):
        if not isinstance(comp, dict):
            errors.append(f"components[{i}] must be an object")
            continue
        cid = comp.get("id")
        if not isinstance(cid, str) or not cid.strip():
            errors.append(f"components[{i}].id must be a non-empty string")
        elif cid in seen_ids:
            errors.append(f"components[{i}].id {cid!r} duplicates an earlier component")
        else:
            seen_ids.add(cid)
        if not isinstance(comp.get("code"), str) or not comp["code"].strip():
            # native_chain backend uses nodes[] not code
            if comp.get("backend") != "native_chain":
                errors.append(f"components[{i}].code must be a non-empty string")

        # reads: optional list of param names this component references
        # (via hou.ch in its code). Validated against declared params so a typo
        # is caught at build, not when the channel reference silently returns 0.
        reads = comp.get("reads")
        if reads is not None:
            if not isinstance(reads, list):
                errors.append(f"components[{i}].reads must be a list if present")
            else:
                for r in reads:
                    if not isinstance(r, str):
                        errors.append(
                            f"components[{i}].reads entries must be strings")
                        break
                    if r not in param_names:
                        errors.append(
                            f"components[{i}].reads references unknown param {r!r}"
                            + (f" (declared params: {sorted(param_names)})"
                               if param_names else " (no params declared)"))

        anchors = comp.get("anchors", [])
        if anchors is None:
            anchors = []
        if not isinstance(anchors, list):
            errors.append(f"components[{i}].anchors must be a list if present")
        else:
            for j, anc in enumerate(anchors):
                if not isinstance(anc, dict):
                    errors.append(f"components[{i}].anchors[{j}] must be an object")
                    continue
                # position: either static [x,y,z] numbers OR position_expr
                # [str/num, str/num, str/num]. The expr form is evaluated at
                # build time against asset params (A2-station).
                has_pos = "position" in anc
                has_pos_expr = "position_expr" in anc
                if has_pos and has_pos_expr:
                    errors.append(
                        f"components[{i}].anchors[{j}]: specify position OR "
                        f"position_expr, not both")
                elif not has_pos and not has_pos_expr:
                    errors.append(
                        f"components[{i}].anchors[{j}] needs position [x,y,z] "
                        f"or position_expr [3 values]")
                elif has_pos:
                    pos = anc.get("position")
                    if not (isinstance(pos, (list, tuple)) and len(pos) == 3):
                        errors.append(
                            f"components[{i}].anchors[{j}].position must be [x,y,z]")
                else:  # has_pos_expr
                    pe = anc.get("position_expr")
                    if not (isinstance(pe, (list, tuple)) and len(pe) == 3):
                        errors.append(
                            f"components[{i}].anchors[{j}].position_expr must be "
                            f"a list of 3 values (numbers or expression strings)")
                # orient_expr / pscale_expr are optional; validated for shape
                # only (eval at build time).
                if "orient_expr" in anc:
                    oe = anc.get("orient_expr")
                    if not (isinstance(oe, (list, tuple)) and len(oe) == 4):
                        errors.append(
                            f"components[{i}].anchors[{j}].orient_expr must be "
                            f"a list of 4 values (quaternion)")
                if "pscale_expr" in anc:
                    pse = anc.get("pscale_expr")
                    if not isinstance(pse, (str, int, float)) or isinstance(pse, bool):
                        errors.append(
                            f"components[{i}].anchors[{j}].pscale_expr must be "
                            f"a number or expression string")
                if not isinstance(anc.get("component_id"), str):
                    errors.append(
                        f"components[{i}].anchors[{j}].component_id must be a string")

    # orientation_asserts (optional, but if present must be well-formed)
    asserts = recipe.get("orientation_asserts", [])
    if asserts is None:
        asserts = []
    if not isinstance(asserts, list):
        errors.append("recipe.orientation_asserts must be a list if present")
    else:
        valid_kinds = {"radial", "elongated", "planar"}
        valid_axes = {"X", "Y", "Z", "-X", "-Y", "-Z"}
        for i, a in enumerate(asserts):
            if not isinstance(a, dict):
                errors.append(f"orientation_asserts[{i}] must be an object")
                continue
            if not isinstance(a.get("component_id"), str):
                errors.append(f"orientation_asserts[{i}].component_id must be a string")
            if a.get("kind", "radial") not in valid_kinds:
                errors.append(
                    f"orientation_asserts[{i}].kind must be radial|elongated|planar")
            ax = a.get("expected_axis", "Y")
            if isinstance(ax, str):
                ax = ax.upper()
            if ax not in valid_axes:
                errors.append(
                    f"orientation_asserts[{i}].expected_axis must be one of {sorted(valid_axes)}")
            # construction_axis (B-station, optional): the local-space axis the
            # component declares as its symmetry/long/normal axis. When present,
            # the builder deterministically derives the world axis from the
            # anchor's @orient quaternion instead of relying on PCA. Must be a
            # valid axis specifier; "signed"/"tolerance_deg" still apply.
            cax = a.get("construction_axis")
            if cax is not None:
                if isinstance(cax, str):
                    cax_norm = cax.upper()
                else:
                    cax_norm = None
                if cax_norm not in valid_axes:
                    errors.append(
                        f"orientation_asserts[{i}].construction_axis must be one "
                        f"of {sorted(valid_axes)} if present")

    post = recipe.get("postprocess", [])
    if post is None:
        post = []
    if not isinstance(post, list):
        errors.append("recipe.postprocess must be a list if present")
    else:
        for i, pp in enumerate(post):
            if not isinstance(pp, dict):
                errors.append(f"postprocess[{i}] must be an object")
                continue
            if not isinstance(pp.get("type"), str) or not pp["type"].strip():
                errors.append(f"postprocess[{i}].type must be a non-empty string")
            if "params" in pp and not isinstance(pp["params"], dict):
                errors.append(f"postprocess[{i}].params must be an object if present")

        # Parm-name validity precheck (C-station): for each postprocess node
        # whose type IS in the bundled manifest, reject parm names that don't
        # exist on that node type — BEFORE any node is created, so the agent
        # gets a hard, actionable error instead of a silent build-time warning.
        # Soft-degrade: if the manifest or the node type is absent, skip the
        # check (never block a build just because the manifest is incomplete).
        from edini.node_utils import manifest_parm_names
        for i, pp in enumerate(post):
            if not isinstance(pp, dict):
                continue
            pp_type = pp.get("type")
            pp_params = pp.get("params") or {}
            if not isinstance(pp_type, str) or not isinstance(pp_params, dict):
                continue
            valid = manifest_parm_names(pp_type)
            if valid is None:
                continue  # manifest/type unknown -> soft degrade, don't block
            unknown = [k for k in pp_params if k not in valid]
            if unknown:
                errors.append(
                    f"postprocess[{i}] '{pp_type}' has unknown parm(s) "
                    f"{unknown} (valid: {sorted(valid)})")

    return errors


def _anchor_generator_code(anchors: list[dict], component_id: str) -> str:
    """Generate a single-SOP python cook body that emits the given anchor points.

    Each emitted point carries @P, @orient (quaternion), @pscale, and a
    point-level @component_id (the per-instance id, e.g. 'wheel_fl'). This is
    the second input to Copy-to-Points; the prim-level component_id on the
    stamped instances is overwritten downstream by _component_id_overwrite_vex.
    """
    lines = [
        "node = hou.pwd()",
        "geo = node.geometry()",
        "geo.clear()",
        "geo.addAttrib(hou.attribType.Point, 'orient', (0.0, 0.0, 0.0, 1.0))",
        "geo.addAttrib(hou.attribType.Point, 'pscale', 1.0)",
        "geo.addAttrib(hou.attribType.Point, 'component_id', '')",
    ]
    for anc in anchors:
        pos = anc.get("position", [0.0, 0.0, 0.0])
        orient = anc.get("orient", [0.0, 0.0, 0.0, 1.0])
        pscale = anc.get("pscale", 1.0)
        cid = anc.get("component_id", component_id)
        # Emit as explicit tuple literals to survive JSON->parm->exec.
        pos_t = "(" + ", ".join(repr(float(p)) for p in pos) + ")"
        orient_t = "(" + ", ".join(repr(float(v)) for v in orient) + ")"
        lines.append(
            f"_pt = geo.createPoint(); _pt.setPosition({pos_t}); "
            f"_pt.setAttribValue('orient', {orient_t}); "
            f"_pt.setAttribValue('pscale', {float(pscale)!r}); "
            f"_pt.setAttribValue('component_id', {str(cid)!r})"
        )
    return "\n".join(lines)


def _component_id_overwrite_snippet(anchor_component_ids: list[str]) -> str:
    """Generate a single-SOP python cook body that overwrites the prim-level
    component_id on stamped instances, so each instance carries its anchor's
    per-instance id (e.g. wheel_fl) instead of the template id (wheel).

    Copy-to-Points produces `n_anchors` consecutive copies of the source
    geometry; the i-th copy's prims get component_id = anchor_component_ids[i].
    We detect copy boundaries by counting prims per copy (source prim count).
    Runs on the copytopoints output.
    """
    # Emit a python list literal of the anchor ids.
    ids_repr = "[" + ", ".join(repr(c) for c in anchor_component_ids) + "]"
    return (
        "node = hou.pwd()\n"
        "geo = node.geometry()\n"
        "anchor_ids = " + ids_repr + "\n"
        "n_anchors = len(anchor_ids)\n"
        "prims = geo.prims()\n"
        "total = len(prims)\n"
        "if n_anchors > 0 and total > 0:\n"
        "    per_copy = total // n_anchors\n"
        "    if per_copy > 0:\n"
        "        for i, prim in enumerate(prims):\n"
        "            copy_index = min(i // per_copy, n_anchors - 1)\n"
        "            prim.setAttribValue('component_id', anchor_ids[copy_index])\n"
    )


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
) -> bool:
    """Install templates as a merge folder on root via setParmTemplateGroup.

    Uses the Houdini-official read-merge pattern: read the node's existing
    ParmTemplateGroup (preserving the geo's default Transform etc. folders),
    add the templates inside a fresh FolderParmTemplate, then write it back.
    This is H21-compatible on a non-HDA geo container, unlike
    setSpareParmGroup which is restricted there. Returns True on success.

    Note: this is a REPLACE-style API at the hou level, but because we read
    the current group first and only append our folder, it is merge-safe —
    pre-existing folders and parms are preserved.
    """
    ptg = root.parmTemplateGroup()
    folder = hou_module.FolderParmTemplate(
        "edini_params", "Parameters",
        folder_type=getattr(hou_module.folderType, "Tabs", 0),
    )
    for tmpl in templates:
        folder.addParmTemplate(tmpl)
    ptg.append(folder)
    root.setParmTemplateGroup(ptg)
    return True


def _install_spare_params(
    root: Any,
    params_spec: dict[str, dict],
    derived_values: dict[str, dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    """Install asset-level params (primary + derived) on the sandbox root.

    All params are collected into ONE template batch and installed in a single
    ``_install_params_via_template_group`` call, producing a single
    ``edini_params`` folder. (Previously each derived param was installed in
    its own folder, making the parameter UI unusable — N derived = N folders.)

    Args:
        root: sandbox root geo container
        params_spec: {name: {default?, min?, max?, label?, kind?, from?}}.
            Primary params (kind != "derived") need a default.
        derived_values: pre-computed derived values
            {name: {value, label, min, max}} from ``_evaluate_derived_params``.
            None or {} means no derived params.

    Each parm lands on the sandbox root (the /obj/<sandbox> geo container), so
    a component python SOP reads them via hou.ch("../<name>") — it sits ONE
    level below the root, so `..` resolves to the root and changing any one
    parm re-cooks every dependent component (true linkage).

    Installation strategy (in order, first success wins):
      1. Read-merge folder params via setParmTemplateGroup + FolderParmTemplate
         (H21-compatible on a non-HDA geo container — the documented pattern).
      2. Legacy setSpareParmGroup (older Houdini where it is not restricted).
      3. Give up: installed stays False; the caller warns that channel refs
         will not bind. Resolved default values are still returned so anchor
         expression evaluation proceeds regardless.

    Returns {name: {"value", "channel_path", "label?", "installed"}}.
    """
    import hou as _hou
    derived_values = derived_values or {}
    result: dict[str, dict[str, Any]] = {}
    if not params_spec and not derived_values:
        return result
    templates: list[Any] = []
    # Primary params (skip derived — handled below from derived_values).
    for name, spec in params_spec.items():
        if spec.get("kind") == "derived":
            continue
        default = float(spec.get("default", 0.0))
        mn = spec.get("min")
        mx = spec.get("max")
        label = spec.get("label", name)
        min_v = float(mn) if mn is not None else 0.0
        max_v = float(mx) if mx is not None else 10.0
        try:
            tmpl = _build_float_parm_template(
                _hou, name, label, default, min_v, max_v)
            templates.append(tmpl)
        except Exception:
            # Template construction failed for this one; skip it (the value is
            # still recorded for expression evaluation).
            pass
        result[name] = {
            "value": default,
            "channel_path": f"{root.path()}/{name}",
            "label": label if label != name else None,
            "installed": False,  # set True only if a group install succeeds
        }
    # Derived params — merged into the SAME template batch so a single
    # setParmTemplateGroup call produces one edini_params folder for all.
    for name, dspec in derived_values.items():
        value = float(dspec.get("value", 0.0))
        label = dspec.get("label", name)
        min_v = float(dspec.get("min", -1000.0))
        max_v = float(dspec.get("max", 1000.0))
        try:
            tmpl = _build_float_parm_template(
                _hou, name, label, value, min_v, max_v)
            templates.append(tmpl)
        except Exception:
            pass
        result[name] = {
            "value": value,
            "channel_path": f"{root.path()}/{name}",
            "label": label if label != name else None,
            "installed": False,
        }
    if templates:
        installed = False
        # 1. Preferred: read-merge folder params (H21-compatible on geo).
        try:
            installed = _install_params_via_template_group(
                root, _hou, templates)
        except Exception:
            installed = False
        # 2. Legacy fallback: setSpareParmGroup (older Houdini).
        if not installed:
            try:
                group = _hou.ParmTemplateGroup()
                for t in templates:
                    group.append(t)
                root.setSpareParmGroup(group)
                installed = True
            except Exception:
                # Mock or unsupported build — defaults still usable for expr
                # eval. Caller emits a warning that channel refs may not bind.
                installed = False
        if installed:
            for name in result:
                result[name]["installed"] = True
    return result


def _evaluate_derived_params(
    params_spec: dict[str, dict],
    primary_values: dict[str, float],
) -> dict[str, Any]:
    """Compute derived (kind: "derived") param values (pure — no install).

    Derived params reference primary (or earlier derived) values via a
    "from" expression, e.g.::

        "seat_top_x": {"kind": "derived",
                        "from": "seat_length * cos(radians(st_angle))"}

    Evaluated in dependency order (topological sort via Kahn). The result is
    returned to the caller, which installs ALL params (primary + derived) in
    a single ``_install_spare_params`` call — producing ONE edini_params
    folder rather than one folder per derived param (the previous bug).

    Returns {"derived_values": {name: {value, label, min, max}}, "errors": [...]}.
    """
    from collections import deque

    derived_values: dict[str, dict[str, Any]] = {}
    errors: list[str] = []

    # Separate derived from primary
    derived_specs: dict[str, dict] = {}
    for name, spec in params_spec.items():
        if spec.get("kind", "primary") == "derived":
            derived_specs[name] = spec
    if not derived_specs:
        return {"derived_values": {}, "errors": []}

    # Build dependency graph (only derived->derived edges; primary refs are
    # already in primary_values)
    graph: dict[str, list[str]] = {}
    for name, spec in derived_specs.items():
        from_expr = spec.get("from", "")
        if not from_expr:
            errors.append(f"derived param '{name}' has no 'from' expression")
            continue
        try:
            from edini.exprs import extract_refs
            deps = extract_refs(from_expr)
        except Exception:
            deps = []
        graph[name] = [d for d in deps if d in derived_specs]

    # Topological sort (Kahn)
    in_degree: dict[str, int] = {n: len(d) for n, d in graph.items()}
    queue: deque[str] = deque(n for n, d in in_degree.items() if d == 0)
    order: list[str] = []
    while queue:
        node = queue.popleft()
        order.append(node)
        for other, deps in graph.items():
            if node in deps:
                in_degree[other] -= 1
                if in_degree[other] == 0:
                    queue.append(other)
    if len(order) != len(graph):
        remaining = [n for n in graph if n not in order]
        errors.append(f"derived param cycle detected among: {remaining}")
        return {"derived_values": {}, "errors": errors}

    # Evaluate in topological order — pure computation, no install.
    eval_bindings = dict(primary_values)
    for name in order:
        spec = derived_specs[name]
        from_expr = spec["from"]
        try:
            from edini.exprs import evaluate as eval_expr
            value = eval_expr(from_expr, eval_bindings)
        except Exception as e:
            errors.append(f"derived param '{name}': cannot evaluate '{from_expr}': {e}")
            continue
        eval_bindings[name] = value
        derived_values[name] = {
            "value": value,
            "label": spec.get("label", name),
            "min": spec.get("min", -1000.0),
            "max": spec.get("max", 1000.0),
        }
    return {"derived_values": derived_values, "errors": errors}


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


def _resolve_anchor_exprs(
    anchors: list[dict],
    params: dict[str, float],
    default_cid: str,
) -> tuple[list[dict], list[str]]:
    """Evaluate position_expr/orient_expr/pscale_expr against asset params.

    Returns (resolved_anchors, errors). Each resolved anchor has numeric
    position/orient/pscale/component_id — the shape _anchor_generator_code
    already expects — so expression handling is transparent downstream.

    position_expr is evaluated at BUILD time (deterministic). Static numeric
    position passes through unchanged. orient_expr/pscale_expr default to
    identity / 1.0 when absent (same as the existing static defaults).
    """
    from edini.exprs import ExprError, evaluate_tuple, evaluate

    resolved: list[dict] = []
    errors: list[str] = []
    for i, anc in enumerate(anchors):
        out: dict[str, Any] = {}
        cid = anc.get("component_id", default_cid)
        out["component_id"] = cid

        # position: static or expr
        if "position_expr" in anc:
            try:
                pos = evaluate_tuple(
                    anc["position_expr"], params, length=3, what="position_expr")
            except ExprError as e:
                errors.append(f"anchor[{i}] ({cid}) position_expr: {e}")
                continue
            out["position"] = list(pos)
        else:
            pos = anc.get("position", [0.0, 0.0, 0.0])
            out["position"] = [float(p) for p in pos]

        # orient: static or expr (default identity)
        if "orient_expr" in anc:
            try:
                orient = evaluate_tuple(
                    anc["orient_expr"], params, length=4, what="orient_expr")
            except ExprError as e:
                errors.append(f"anchor[{i}] ({cid}) orient_expr: {e}")
                continue
            out["orient"] = list(orient)
        else:
            orient = anc.get("orient", [0.0, 0.0, 0.0, 1.0])
            out["orient"] = [float(v) for v in orient]

        # pscale: static, expr, or default 1.0
        if "pscale_expr" in anc:
            try:
                out["pscale"] = float(evaluate(anc["pscale_expr"], params))
            except ExprError as e:
                errors.append(f"anchor[{i}] ({cid}) pscale_expr: {e}")
                continue
        else:
            out["pscale"] = float(anc.get("pscale", 1.0))

        resolved.append(out)
    return resolved, errors


def _sanitize_node_name(type_str: str) -> str:
    """Sanitize a node type name into a legal Houdini node name.

    Houdini node names may only contain [A-Za-z0-9_]. Postprocess types often
    carry a version suffix (e.g. ``fuse::2.0``); using the type directly as a
    node name triggers ``InvalidNodeName`` in real Houdini, which silently
    skips the entire postprocess node (observed in a real bicycle build where
    the fuse was skipped, leaving 652 non-manifold edges). This replaces every
    non-word character with an underscore.
    """
    import re
    return re.sub(r"[^A-Za-z0-9_]", "_", type_str)


def _safe_create_node(parent_path: str, node_type: str, name: str) -> Any:
    """Create a node, returning the node object (or raising on failure).

    Uses hou.node(parent).createNode directly (the sandbox already lives under
    /obj/<sandbox>, so we want raw creation, not the /obj-defaulting wrapper).

    After a successful creation the node passes through :func:`_post_create_init`,
    which is the single harness-level chokepoint for post-creation setup. Today
    that initializes Copy-to-Points' attribute transfer (resettargetattribs) so
    per-instance ids/attrs land on every copied prim — without it,
    build_procedural_asset and any hand-written network_mode script silently
    lose per-instance ids. Putting it here means every harness-created copytopoints
    is covered regardless of which build tool created it.
    """
    parent = hou.node(parent_path)
    if parent is None:
        raise RuntimeError(f"Parent node not found: {parent_path}")
    node = None
    # Try bare name first, then namespace variants — mirrors create_node() in
    # node_utils but returns the node object for in-process use.
    try:
        node = parent.createNode(node_type, name)
    except Exception:
        # Walk namespace variants for e.g. "copytopoints" -> "copytopoints::2.0"
        try:
            cats = [
                hou.sopNodeTypeCategory(), hou.objNodeTypeCategory(),
            ]
        except Exception:
            cats = []
        for cat in cats:
            try:
                nt = hou.nodeType(cat, node_type)
            except Exception:
                nt = None
            if nt is None:
                continue
            try:
                for variant in nt.namespaceOrder():
                    try:
                        node = parent.createNode(variant, name)
                        break
                    except Exception:
                        continue
            except Exception:
                continue
            if node is not None:
                break
        if node is None:
            raise
    _post_create_init(node)
    return node


def _post_create_init(node) -> None:
    """Harness-level post-creation initialization hook.

    Centralizes per-node-type setup that must happen on EVERY node the harness
    creates, so individual build tools can't forget it. Best-effort: never raises
    (a failed init is logged but must not break node creation, which would be
    worse than a missing attribute transfer).

    Currently initializes Copy-to-Points 2.0's attribute transfer by pressing
    the ``resettargetattribs`` button — the only sanctioned real-H21 path. See
    ``manual_resettargetattribs_probe.py`` for the captured mechanism. The
    shared implementation lives in ``node_utils._init_copytopoints_attribs`` so
    the harness path and the ``node_utils.create_node`` path (hand-written
    network_mode scripts) behave identically.
    """
    try:
        type_name = node.type().name().split("::")[0].lower()
    except Exception:
        return
    if type_name == "copytopoints":
        from edini.node_utils import _init_copytopoints_attribs
        try:
            _init_copytopoints_attribs(node)
        except Exception:
            # Initialization is best-effort; a failed pressButton must not break
            # the node creation that just succeeded. The caller already has a
            # usable node; attribute transfer can be set up manually if needed.
            pass


def _set_parm_safe(node, parm_name: str, value: Any) -> None:
    """Set a parm, raising a clear error if the parm is missing.

    For multi-component values (list/tuple), uses ``parmTuple`` which
    decomposes to individual sub-parms (e.g. ``size`` → ``sizex/sizey/sizez``
    on box nodes). Single values use ``parm`` directly.
    """
    # Multi-component path (e.g. "size": [2, 0.5, 1] on box)
    if isinstance(value, (list, tuple)) and len(value) > 1:
        ptuple = node.parmTuple(parm_name)
        if ptuple is not None:
            ptuple.set(tuple(float(v) for v in value))
            return
    # Single-value path (also the fallback for single-element lists)
    parm = node.parm(parm_name)
    if parm is None:
        raise RuntimeError(
            f"Parm '{parm_name}' not found on {node.path()} ({node.type().name()})")
    parm.set(value)


# ─────────────────────────────────────────────────────────────────────────────
# Construction-axis derivation (B-station)
#
# Deterministically derives each component's world-space axis from its declared
# local construction_axis + the anchor @orient quaternion. This replaces PCA
# estimation with ground truth, and lets the builder reject self-consistent
# errors (agent declares construction_axis:Y but anchor.orient rotates Y to
# world Z while expected_axis says X) at BUILD time, before any cook.
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_axis_spec(value: Any) -> str | None:
    """Return an upper-cased axis name ('X'/'Y'/'Z'/'-X'/...) or None."""
    if isinstance(value, str):
        v = value.upper()
        if v in ("X", "Y", "Z", "-X", "-Y", "-Z"):
            return v
    return None


def _resolve_construction_world_axis(
    orient_q: list[float],
    construction_axis: str,
) -> tuple[float, float, float]:
    """Rotate a local construction axis into world space by the anchor @orient.

    Pure algebra — no hou, no estimation. Imported lazily from
    orientation_math to keep the top-level import graph stable.
    """
    from edini.orientation_math import LOCAL_AXIS_VECTORS, rotate_vector_by_quaternion

    local_vec = LOCAL_AXIS_VECTORS[construction_axis]
    return rotate_vector_by_quaternion(local_vec, tuple(orient_q))


def _check_construction_axis_consistency(
    components: list[dict],
    orientation_asserts: list[dict],
    tolerance_deg: float = 1.0,
) -> list[str]:
    """Pre-flight consistency check for construction_axis asserts.

    For each assert that declares a construction_axis, resolve the world axis
    from the matching anchor's @orient (or identity for direct-merge
    components with no anchors) and verify it agrees with expected_axis within
    `tolerance_deg`. Returns a list of human-readable error strings (empty =
    all consistent, or no construction_axis asserts present).

    A non-empty list means the recipe is internally contradictory — the agent
    declared a construction axis whose deterministic world projection does NOT
    match the expected_axis it also declared. The builder refuses to build so
    the agent fixes the contradiction at the source instead of producing a
    self-consistent-but-wrong asset that PCA would happily confirm.
    """
    from edini.orientation_math import (
        AXIS_VECTORS, axis_angle_between, dominant_axis_name,
    )

    errors: list[str] = []
    # Index anchors by per-instance component_id for quick lookup.
    # cid_to_orient: maps a per-instance component_id -> its anchor orient
    # (identity for direct-merge components that declare a construction_axis).
    cid_to_orient: dict[str, list[float]] = {}
    direct_components: set[str] = set()
    for comp in components:
        cid = comp.get("id")
        anchors = comp.get("anchors") or []
        if not anchors:
            # Direct-merge component: no anchor, so its world frame is identity.
            direct_components.add(cid)
        else:
            for anc in anchors:
                anc_cid = anc.get("component_id", cid)
                orient = anc.get("orient", [0.0, 0.0, 0.0, 1.0])
                cid_to_orient[anc_cid] = list(orient)

    for a in orientation_asserts:
        caxis = _normalize_axis_spec(a.get("construction_axis"))
        if caxis is None:
            continue  # no construction_axis declared -> PCA path, skip
        cid = a.get("component_id")
        expected = _normalize_axis_spec(a.get("expected_axis"))
        if expected is None:
            continue  # validate_recipe already flagged this

        if cid in cid_to_orient:
            orient_q = cid_to_orient[cid]
        elif cid in direct_components:
            orient_q = [0.0, 0.0, 0.0, 1.0]  # identity for direct-merge
        else:
            # component_id not found among anchors or direct components.
            # This may be a stamped instance id that wasn't declared as an
            # anchor component_id — surface it so the agent fixes the recipe.
            errors.append(
                f"orientation_assert construction_axis references component_id "
                f"{cid!r} but no anchor with that component_id exists (anchors "
                f"use their per-instance component_id field). Either add an "
                f"anchor with component_id={cid!r} or drop construction_axis "
                f"to fall back to PCA for that component."
            )
            continue

        world_vec = _resolve_construction_world_axis(orient_q, caxis)
        expected_vec = AXIS_VECTORS[expected]
        angle_deg, _ = axis_angle_between(world_vec, expected_vec, signed=False)
        if angle_deg > tolerance_deg:
            detected = dominant_axis_name(world_vec)
            errors.append(
                f"orientation_assert for {cid!r}: construction_axis {caxis} "
                f"rotated by anchor @orient {orient_q} projects onto world axis "
                f"{detected} ({[round(c, 3) for c in world_vec]}), which is "
                f"{round(angle_deg, 1)}° from declared expected_axis {expected} "
                f"(tolerance {tolerance_deg}°). This is a contradiction — the "
                f"anchor orient does not place the construction axis where "
                f"expected_axis claims. Fix anchor.orient (or expected_axis / "
                f"construction_axis) so they agree."
            )
    return errors


def _component_id_overwrite_snippet(
    anchor_component_ids: list[str],
    *,
    world_axes: list[tuple[float, float, float]] | None = None,
) -> str:
    """Generate a single-SOP python cook body that overwrites the prim-level
    component_id on stamped instances, so each instance carries its anchor's
    per-instance id (e.g. wheel_fl) instead of the template id (wheel).

    Copy-to-Points produces `n_anchors` consecutive copies of the source
    geometry; the i-th copy's prims get component_id = anchor_component_ids[i].
    We detect copy boundaries by counting prims per copy (source prim count).
    Runs on the copytopoints output.

    B-station: when ``world_axes`` is supplied (one tuple per anchor, parallel
    to anchor_component_ids), the snippet also bakes a prim attribute
    ``edini_world_axis`` (3 floats) carrying the deterministically-derived
    world-space construction axis for that instance. verify_orientation reads
    this to skip PCA entirely for that component.
    """
    # Emit a python list literal of the anchor ids.
    ids_repr = "[" + ", ".join(repr(c) for c in anchor_component_ids) + "]"
    # World axes are optional. Bake them only when every anchor has one and
    # they're non-None; otherwise leave the attribute unset (PCA fallback).
    bake_axes = bool(world_axes) and len(world_axes) == len(anchor_component_ids)
    axes_repr = (
        "[" + ", ".join(
            "(" + ", ".join(repr(float(c)) for c in ax) + ")"
            for ax in (world_axes or [])
        ) + "]"
        if bake_axes else "[]"
    )

    header = (
        "node = hou.pwd()\n"
        "geo = node.geometry()\n"
        "if geo.findPrimAttrib('component_id') is None:\n"
        "    geo.addAttrib(hou.attribType.Prim, 'component_id', '')\n"
        "anchor_ids = " + ids_repr + "\n"
        "world_axes = " + axes_repr + "\n"
        "n_anchors = len(anchor_ids)\n"
        "prims = geo.prims()\n"
        "total = len(prims)\n"
    )
    if not bake_axes:
        return header + (
            "if n_anchors > 0 and total > 0:\n"
            "    per_copy = total // n_anchors\n"
            "    if per_copy > 0:\n"
            "        for i, prim in enumerate(prims):\n"
            "            copy_index = min(i // per_copy, n_anchors - 1)\n"
            "            prim.setAttribValue('component_id', anchor_ids[copy_index])\n"
        )
    # Baking world axes: declare the prim attrib up front, then write both
    # component_id and edini_world_axis per instance.
    return header + (
        "bake_axes = len(world_axes) == n_anchors and n_anchors > 0\n"
        "if bake_axes:\n"
        "    geo.addAttrib(hou.attribType.Prim, 'edini_world_axis', (0.0, 0.0, 0.0))\n"
        "if n_anchors > 0 and total > 0:\n"
        "    per_copy = total // n_anchors\n"
        "    if per_copy > 0:\n"
        "        for i, prim in enumerate(prims):\n"
        "            copy_index = min(i // per_copy, n_anchors - 1)\n"
        "            prim.setAttribValue('component_id', anchor_ids[copy_index])\n"
        "            if bake_axes:\n"
        "                prim.setAttribValue('edini_world_axis', world_axes[copy_index])\n"
    )


def _direct_component_world_axis_snippet(
    world_axis: tuple[float, float, float],
) -> str:
    """Append a prim-level edini_world_axis tag to a direct-merge component.

    For components with no anchors, there's no idfix step — the world axis is
    just the construction_axis itself (identity rotation). We return a small
    cook-body SUFFIX (not a full cook body) to be appended after the
    component's own geometry code, so the attrib lands on every prim that the
    component emitted.
    """
    ax = "(" + ", ".join(repr(float(c)) for c in world_axis) + ")"
    return (
        "\n# edini construction-axis tag (direct-merge, identity world frame)\n"
        "try:\n"
        "    geo.addAttrib(hou.attribType.Prim, 'edini_world_axis', (0.0, 0.0, 0.0))\n"
        "    for _prim in geo.prims():\n"
        f"        _prim.setAttribValue('edini_world_axis', {ax})\n"
        "except Exception:\n"
        "    pass\n"
    )


# ═══════════════════════════════════════════════════════════════
#  Component builders (backend-aware)
# ═══════════════════════════════════════════════════════════════


def _build_python_component(
    root_path: str,
    comp: dict,
    cid: str,
    world_axis_by_cid: dict,
    anchors: list,
) -> Any:
    """Build a Python-backend component. Returns the cooked python SOP."""
    code = comp.get("code", "")
    py_sop = _safe_create_node(root_path, "python", f"{cid}_python")
    effective_code = code
    if not anchors and cid in world_axis_by_cid:
        effective_code = code + _direct_component_world_axis_snippet(
            world_axis_by_cid[cid])
    _set_parm_safe(py_sop, "python", effective_code)
    return py_sop


def _axis_bake_vex_snippet(world_axis: tuple[float, float, float]) -> str:
    """VEX snippet (run over prims) that bakes edini_world_axis onto every
    prim. Used by native_chain / vex_skeleton direct-merge tag nodes so the
    G2 bake check passes without relying on the python direct-merge suffix.

    Uses ``addattrib(0, "prim", name, default)`` where the default IS the axis
    vector — addattrib initializes all existing prims to its default, so no
    separate per-prim write is needed. The naive ``3@name = {...}`` write form
    FAILS to cook in H21 when the attribute doesn't exist yet (it cannot
    auto-create on write in prim run-over context). Caught by hython e2e
    validation (the mock does not compile VEX, so this slipped past mock tests)."""
    ax = ", ".join(repr(float(c)) for c in world_axis)
    return (
        'addattrib(0, "prim", "edini_world_axis", {' + ax + '});\n'
    )


def _build_native_chain_component(
    root_path: str,
    comp: dict,
    cid: str,
    world_axis_by_cid: dict,
    anchors: list,
) -> Any:
    """Build a native_chain component from its node list.

    Creates a chain of native SOPs (box/tube/torus/attribcreate/...)
    wired input-0 to previous. The last node drives the component output.
    Returns the last node in the chain.

    Stage-3: for direct-merge native_chain components (no anchors), appends a
    prim attribwrangle baking edini_world_axis so G2 (bake check) passes.
    Stamped components get their per-instance axis via the idfix SOP instead.
    """
    nodes = comp.get("nodes") or []
    if not nodes:
        raise RuntimeError(f"native_chain component '{cid}' has no nodes")

    prev = None
    last_node = None
    for ni, node_spec in enumerate(nodes):
        ntype = node_spec.get("type", "")
        nname = node_spec.get("name", f"{cid}_n{ni}")
        if not ntype:
            raise RuntimeError(
                f"native_chain component '{cid}' node[{ni}] missing 'type'")
        # Resolve alias: transform→xform, polybevel→polybevel::3.0
        from edini.parm_catalog import ParmCatalog, NODE_ALIASES
        canonical = NODE_ALIASES.get(ntype, ntype)
        try:
            node = _safe_create_node(root_path, canonical, nname)
        except Exception as e:
            raise RuntimeError(
                f"native_chain component '{cid}' node[{ni}] "
                f"'{canonical}' create failed: {e}")
        if prev is not None:
            node.setInput(0, prev)
        # Set parameters
        params = node_spec.get("params") or {}
        # Node-type sensible defaults: procedural workflows ALWAYS want polygon
        # geometry, not Houdini primitives. H21 tube/cylinder default 'type' to
        # 0 (Primitive), which emits a SINGLE primitive instead of a polygon
        # mesh — Copy-to-Points then instances that single primitive as a
        # degenerate point, and the geometry silently "disappears" (caught by
        # real-H21 e2e; the mock does not cook SOPs so it missed this). If the
        # recipe does not explicitly set 'type', default it to 1 (Polygon).
        if canonical in ("tube", "cylinder") and "type" not in params:
            try:
                node.parm("type").set(1)
            except Exception:
                pass  # node may not have 'type' — best-effort
        # attribwrangle special handling: 'class' sets run-over mode,
        # 'snippet' sets the VEX code
        if canonical == "attribwrangle":
            if "class" in params:
                node.parm("class").set(params["class"])
            if "snippet" in params:
                node.parm("snippet").set(params["snippet"])
        else:
            for pname, pvalue in params.items():
                try:
                    _set_parm_safe(node, pname, pvalue)
                except Exception as e:
                    raise RuntimeError(
                        f"native_chain component '{cid}' node[{ni}] "
                        f"parm '{pname}={pvalue}': {e}")
        prev = node
        last_node = node

    # Stage-3: bake edini_world_axis on direct-merge native_chain components.
    # Stamped ones get per-instance axes from the idfix SOP downstream.
    if not anchors and cid in world_axis_by_cid:
        ax_tag = _safe_create_node(root_path, "attribwrangle", f"{cid}_axis")
        ax_tag.setInput(0, last_node)
        ax_tag.parm("class").set("primitive")
        ax_tag.parm("snippet").set(
            _axis_bake_vex_snippet(world_axis_by_cid[cid]))
        last_node = ax_tag

    return last_node


def _build_vex_skeleton_component(
    root_path: str,
    comp: dict,
    cid: str,
    world_axis_by_cid: dict,
    anchors: list,
    param_values: dict[str, float],
) -> Any:
    """Build a vex_skeleton component.

    Single-wrangle mode (no section_code):
      wrangle (profile) → form_node (polyextrude::2.0 by default)

    Dual-wrangle mode (section_code present):
      wrangle_path ──┐
                      ├→ sweep::2.0 (endcaptype=1) → tag
      wrangle_section ┘

    The VEX code emits skeletons (polylines with @pscale).
    The form_node closes the geometry.
    Returns the tag node.
    """
    code = comp.get("code", "")
    section_code = comp.get("section_code", "")
    form = comp.get("form_node")
    if not form:
        raise RuntimeError(
            f"vex_skeleton component '{cid}' requires form_node")
    fn_type = form.get("type", "polyextrude::2.0")
    from edini.parm_catalog import NODE_ALIASES
    canonical_fn = NODE_ALIASES.get(fn_type, fn_type)

    reads = comp.get("reads") or []

    # ── Helper: create a wrangle with spare parms ──
    def _make_wrangle(name, vex_code, extra_reads=None):
        wr = _safe_create_node(root_path, "attribwrangle", name)
        wr.parm("class").set("detail")
        if "#include" not in vex_code and ("make_polyline" in vex_code or "make_circle" in vex_code):
            vex_code = (
                "#include <vexlib/skeleton.vfl>\n"
                "#include <vexlib/sections.vfl>\n" + vex_code
            )
        all_reads = reads + (extra_reads or [])
        for pname in all_reads:
            if pname in param_values:
                try:
                    ptg = wr.parmTemplateGroup()
                    if not ptg.find(pname):
                        t = hou.FloatParmTemplate(pname, pname, 1,
                            (param_values[pname],), 0, 100)
                        ptg.append(t)
                        wr.setParmTemplateGroup(ptg)
                    wr.parm(pname).setExpression(f'ch("../{pname}")')
                except Exception:
                    pass
        _set_parm_safe(wr, "snippet", vex_code)
        return wr

    # ── Dual-wrangle mode: path + section → Sweep ──
    if section_code:
        wr_path = _make_wrangle(f"{cid}_path", code)
        wr_section = _make_wrangle(f"{cid}_section", section_code)

        fn_name = f"{cid}_sweep"
        fn = _safe_create_node(root_path, canonical_fn, fn_name)
        fn.setInput(0, wr_path)
        fn.setInput(1, wr_section)
        fn_params = form.get("params") or {}
        for pname, pvalue in fn_params.items():
            if isinstance(pvalue, str) and ('ch(' in pvalue or 'chf(' in pvalue):
                try:
                    fn.parm(pname).setExpression(pvalue)
                except Exception:
                    _set_parm_safe(fn, pname, pvalue)
            else:
                _set_parm_safe(fn, pname, pvalue)

        # component_id tag + edini_world_axis bake (direct-merge only;
        # stamped components get per-instance axis from the idfix SOP).
        tag_name = f"{cid}_tag"
        tag = _safe_create_node(root_path, "attribwrangle", tag_name)
        tag.setInput(0, fn)
        tag.parm("class").set("primitive")
        tag_snippet = f's@component_id = "{cid}";\n'
        if not anchors and cid in world_axis_by_cid:
            tag_snippet += _axis_bake_vex_snippet(world_axis_by_cid[cid])
        tag.parm("snippet").set(tag_snippet)
        return tag

    # ── Single-wrangle mode: profile → PolyExtrude ──
    wr = _make_wrangle(f"{cid}_wrangle", code)
    fn_params = form.get("params") or {}
    for pname, pvalue in fn_params.items():
        # Support ch() channel expressions for parametric dimensions.
        if isinstance(pvalue, str) and ('ch(' in pvalue or 'chf(' in pvalue):
            try:
                fn.parm(pname).setExpression(pvalue)
            except Exception:
                _set_parm_safe(fn, pname, pvalue)
        else:
            _set_parm_safe(fn, pname, pvalue)

    # ── component_id tag (PolyExtrude/Sweep strip prim attrs from source) ──
    tag_name = f"{cid}_tag"
    tag = _safe_create_node(root_path, "attribwrangle", tag_name)
    tag.setInput(0, fn)
    # Use attribwrangle (prim mode) to re-tag component_id
    tag.parm("class").set("primitive")
    tag_snippet = f's@component_id = "{cid}";\n'
    if not anchors and cid in world_axis_by_cid:
        tag_snippet += _axis_bake_vex_snippet(world_axis_by_cid[cid])
    tag.parm("snippet").set(tag_snippet)

    return tag


# ═══════════════════════════════════════════════════════════════
#  build_procedural_asset (main entry point)
# ═══════════════════════════════════════════════════════════════


def build_procedural_asset(
    recipe: dict,
    *,
    sandbox_name: str | None = None,
    delete_on_failure: bool = False,
) -> dict[str, Any]:
    """Build a modular procedural asset from a declarative recipe.

    The recipe describes components (each with pure-geometry python code),
    per-component anchor points (for Copy-to-Points stamping), optional
    post-processing SOPs, and orientation assertions. The builder deterministically
    assembles a sandbox network (component SOPs → anchor generators →
    Copy-to-Points → merge → postprocess → OUT), cooks it, and returns
    diagnostics + gate previews WITHOUT committing.

    The agent's component code must only emit geometry on its own node
    (``node = hou.pwd(); geo = node.geometry()``) and tag every prim with
    ``component_id``. It must NEVER call createNode.

    Commit is a separate explicit step: ``houdini_commit_sandbox(root_path,
    name, orientation_checks=recipe['orientation_asserts'])`` — the existing
    structure + orientation gates then run on the built OUT automatically.

    Returns a dict shaped like run_python_sandbox plus builder-specific fields
    (components_built, anchors_built, component_id_check).
    """
    # ── Validate recipe ──
    errors = _validate_recipe(recipe)
    if errors:
        return {
            "success": False,
            "execution_mode": EXECUTION_MODE_LIVE,
            "build_mode": "recipe",
            "error": "Invalid recipe: " + "; ".join(errors),
            "validation_errors": errors,
            "preserved": False,
            "deleted": False,
        }

    components = recipe.get("components", [])
    orientation_asserts = recipe.get("orientation_asserts") or []

    # ── Phase A: Enhanced validation (A1-A6, parm catalog cross-check) ──
    # Runs the new pipeline validator if the parm catalog is available.
    # Catches parm-name typos, invalid node types, VEX syntax issues, and
    # dependency graph errors BEFORE any Houdini operations. Missing catalog
    # is not a failure — the existing build logic still runs as fallback.
    phase_a_report = None
    try:
        from edini.recipe_validator import validate_recipe as phase_a_validate
        import os as _os
        catalog_path = _os.path.join(
            os.path.dirname(__file__), "data", "parm-catalog.json")
        # Auto-generate catalog on first use if missing
        if not _os.path.exists(catalog_path):
            try:
                _generate_and_save_catalog(catalog_path)
            except Exception:
                pass  # can't generate — skip Phase A gracefully
        if _os.path.exists(catalog_path):
            phase_a_report = phase_a_validate(recipe, catalog_path)
            if not phase_a_report["passed"]:
                return {
                    "success": False,
                    "execution_mode": EXECUTION_MODE_LIVE,
                    "build_mode": "recipe",
                    "error": (
                        "Phase A validation failed — "
                        f"{phase_a_report['error_count']} blocking error(s). "
                        "See phase_a_report.errors for details."
                    ),
                    "phase_a_report": phase_a_report,
                    "preserved": False,
                    "deleted": False,
                }
            # Phase A passed — carry report forward for diagnostics
    except ImportError:
        pass  # recipe_validator not available — skip Phase A, use existing checks
    except Exception as e:
        # Non-fatal: Phase A is an enhancement, not a hard gate unless it
        # explicitly found blocking errors. Unhandled exceptions here degrade
        # gracefully to the existing validation path.
        import traceback as _tb
        phase_a_report = {"exception": str(e), "traceback": _tb.format_exc()}

    # ── Construction-axis consistency pre-check (B-station) ──
    # Deterministically verify that every construction_axis declaration agrees
    # with its anchor @orient + expected_axis BEFORE building anything. A
    # contradiction here means the recipe is internally wrong — refuse rather
    # than produce a self-consistent-but-incorrect asset (which PCA would
    # happily confirm, since the agent generates geometry + writes asserts from
    # the same mental model).
    has_construction_axis = any(
        _normalize_axis_spec(a.get("construction_axis")) is not None
        for a in orientation_asserts
    )
    construction_errors: list[str] = []
    if has_construction_axis:
        construction_errors = _check_construction_axis_consistency(
            components, orientation_asserts)
    if construction_errors:
        return {
            "success": False,
            "execution_mode": EXECUTION_MODE_LIVE,
            "build_mode": "recipe",
            "error": (
                "Construction-axis consistency check failed — the recipe's "
                "declared construction axes contradict its expected_axis / "
                "anchor @orient. Fix the contradictions at the source (these "
                "are deterministic, not estimated): " + " | ".join(construction_errors)
            ),
            "construction_axis_errors": construction_errors,
            "preserved": False,
            "deleted": False,
        }

    asset_name = recipe.get("asset_name") or "asset"
    name = sandbox_name or asset_name
    job_id, root_path = _create_sandbox_root(name)
    postprocess = recipe.get("postprocess") or []
    orientation_asserts = recipe.get("orientation_asserts") or []
    params_spec = recipe.get("params") or {}

    warnings: list[str] = []
    errors_runtime: list[str] = []
    components_built: list[str] = []
    anchors_built: dict[str, int] = {}
    out_path = ""

    try:
        root = hou.node(root_path)
        if root is None:
            raise RuntimeError(f"Sandbox root not found after creation: {root_path}")
        # A2-station: install asset-level shared params on the sandbox root.
        # Components read them via hou.ch("../../<name>") so a change to any
        # one parm re-cooks every dependent component (true linkage). The
        # resolved default values also feed anchor expression evaluation.
        #
        # Flow: compute primary defaults → compute derived values (pure) →
        # install primary + derived in ONE _install_spare_params call so a
        # single edini_params folder holds every parm (previously each derived
        # got its own folder, fragmenting the parameter UI).
        param_install: dict[str, dict[str, Any]] = {}
        param_values: dict[str, float] = {}
        if params_spec:
            try:
                # 1. Primary defaults (pure computation).
                primary_values: dict[str, float] = {
                    n: float(spec.get("default", 0.0))
                    for n, spec in params_spec.items()
                    if spec.get("kind", "primary") != "derived"
                }
                # 2. Derived values (pure computation, no install).
                derived_report = _evaluate_derived_params(
                    params_spec, primary_values)
                if derived_report.get("errors"):
                    errors_runtime.extend(derived_report["errors"])
                derived_values = derived_report.get("derived_values", {})
                # 3. Install primary + derived together (single folder).
                param_install = _install_spare_params(
                    root, params_spec, derived_values)
                param_values = {n: v["value"] for n, v in param_install.items()}
                # Surface which params failed to install as spare parms:
                # channel refs (hou.ch) in component code will not bind
                # for those, so the agent must add the parms itself or the
                # geometry cook will error. This is the actionable signal.
                not_installed = [n for n, v in param_install.items()
                                 if not v.get("installed")]
                if not_installed:
                    warnings.append(
                        f"spare parms not installed on sandbox root: "
                        f"{not_installed}. Component code using hou.ch('../../<name>') "
                        f"will fail unless these parms exist. Either the Houdini "
                        f"build lacks setSpareParmGroup, or FloatParmTemplate "
                        f"construction failed for them.")
            except Exception as e:
                warnings.append(f"spare-param install failed ({e}); "
                                "component channel refs may not bind")
                param_values = {n: float(spec.get("default", 0.0))
                                for n, spec in params_spec.items()}


        # ── 1. Build one python SOP per component ──
        comp_nodes: list[Any] = []  # nodes whose output goes into the merge
        # Track stamped components: {component_id: (copy_node, anchor_ids)}
        stamped: list[tuple[str, Any, list[str]]] = []

        # B-station: index the recipe's anchor layout so the world-axis
        # resolution below can look up each instance's @orient. This mirrors
        # what _check_construction_axis_consistency already verified, so we
        # can trust every construction_axis assert that reaches here resolves.
        direct_components_set: set[str] = set()
        anchor_cid_orient: dict[str, list[float]] = {}
        # Also index components by id + remember each component's backend + own
        # construction_axis field, for the tiered axis resolution below.
        comp_by_id: dict[str, dict] = {}
        for comp in components:
            cid = comp.get("id")
            comp_by_id[cid] = comp
            anchors = comp.get("anchors") or []
            if not anchors:
                direct_components_set.add(cid)
            else:
                for anc in anchors:
                    anc_cid = anc.get("component_id", cid)
                    anchor_cid_orient[anc_cid] = list(
                        anc.get("orient", [0.0, 0.0, 0.0, 1.0]))

        # ── Stage-3: resolve a world axis for EVERY component (decision 6) ──
        # world_axis_by_cid maps a per-instance component_id (or a direct-merge
        # component id) -> its deterministically-derived world construction
        # axis. Axis source priority (decision 9):
        #   1. the component's construction_axis as declared in an assert
        #   2. the component's own top-level `construction_axis` field
        #   3. backend inference (native_chain tube/torus/cylinder -> length axis)
        #   4. fallback Y
        # Tiers 3/4 are recorded in `defaulted_axes` so the receipt can flag
        # them for agent review. Every component gets an axis here — G2 (bake
        # check) then confirms the axis actually landed on geometry.
        world_axis_by_cid: dict[str, tuple[float, float, float]] = {}
        # defaulted_axes: {cid: "Y(fallback)"/"tube:Y(inferred)"...} — only
        # components that did NOT explicitly declare an axis go here.
        defaulted_axes: dict[str, str] = {}

        def _infer_native_chain_axis(comp: dict) -> str | None:
            """Decision 9 tier 3: infer the length axis from the first
            tube/torus/cylinder primitive node in a native_chain. Returns
            a local axis name (X/Y/Z) or None if no inference possible."""
            for node_spec in (comp.get("nodes") or []):
                tname = (node_spec.get("type") or "").lower()
                # Strip namespace: 'tube::2.0' -> 'tube'
                bare = tname.split("::")[0]
                if bare in ("tube", "cylinder"):
                    return "Y"  # tube SOP default length axis is Y
                if bare == "torus":
                    return "Y"  # torus lies in XZ plane -> normal is Y
            return None

        # Build a quick lookup: assert construction_axis by the component_id
        # the assert references (per-instance id for stamped, comp id for direct).
        assert_caxis_by_cid: dict[str, str] = {}
        for a in orientation_asserts:
            caxis = _normalize_axis_spec(a.get("construction_axis"))
            if caxis is not None:
                assert_caxis_by_cid[a.get("component_id", "")] = caxis

        for comp in components:
            cid = comp.get("id")
            backend = comp.get("backend", "python")
            anchors = comp.get("anchors") or []
            comp_caxis_field = _normalize_axis_spec(comp.get("construction_axis"))

            if anchors:
                # Stamped component: resolve a world axis PER anchor instance.
                for anc in anchors:
                    anc_cid = anc.get("component_id", cid)
                    orient = anchor_cid_orient.get(
                        anc_cid, [0.0, 0.0, 0.0, 1.0])
                    # Tier 1: assert for this instance
                    caxis = assert_caxis_by_cid.get(anc_cid)
                    source_tag = None
                    if caxis is None and comp_caxis_field is not None:
                        # Tier 2: component-level field applies to all instances
                        caxis = comp_caxis_field
                    if caxis is None:
                        # Tier 3: backend inference
                        if backend == "native_chain":
                            inferred = _infer_native_chain_axis(comp)
                            if inferred is not None:
                                caxis = inferred
                                source_tag = f"{backend}:{inferred}(inferred)"
                    if caxis is None:
                        # Tier 4: fallback Y
                        caxis = "Y"
                        source_tag = "Y(fallback)"
                    if source_tag is not None:
                        defaulted_axes[anc_cid] = source_tag
                    world_axis_by_cid[anc_cid] = _resolve_construction_world_axis(
                        orient, caxis)
            else:
                # Direct-merge component: world frame is identity.
                caxis = assert_caxis_by_cid.get(cid)
                source_tag = None
                if caxis is None and comp_caxis_field is not None:
                    caxis = comp_caxis_field
                if caxis is None:
                    if backend == "native_chain":
                        inferred = _infer_native_chain_axis(comp)
                        if inferred is not None:
                            caxis = inferred
                            source_tag = f"{backend}:{inferred}(inferred)"
                if caxis is None:
                    caxis = "Y"
                    source_tag = "Y(fallback)"
                if source_tag is not None:
                    defaulted_axes[cid] = source_tag
                world_axis_by_cid[cid] = _resolve_construction_world_axis(
                    [0.0, 0.0, 0.0, 1.0], caxis)

        for comp in components:
            cid = comp["id"]
            backend = comp.get("backend", "python")
            anchors = comp.get("anchors") or []

            # ── Build component geometry (backend-dependent) ──
            out_sop = None  # the node whose geometry enters CTP or merge
            try:
                if backend == "native_chain":
                    out_sop = _build_native_chain_component(
                        root_path, comp, cid, world_axis_by_cid, anchors)
                elif backend == "vex_skeleton":
                    out_sop = _build_vex_skeleton_component(
                        root_path, comp, cid, world_axis_by_cid, anchors,
                        param_values)
                else:  # python (default)
                    out_sop = _build_python_component(
                        root_path, comp, cid, world_axis_by_cid, anchors)
            except Exception as e:
                errors_runtime.append(
                    f"component '{cid}' ({backend}): {e}")
                import traceback as _tb
                errors_runtime.append(_tb.format_exc())
                continue

            if out_sop is None:
                errors_runtime.append(
                    f"component '{cid}': no output node produced")
                continue

            # Cook the component immediately so a per-component error surfaces
            # with a clear attribution.
            try:
                out_sop.cook(force=True)
                cook_errs = list(out_sop.errors() or [])
                if cook_errs:
                    raise RuntimeError("; ".join(cook_errs))
            except Exception as e:
                errors_runtime.append(f"component '{cid}' cook failed: {e}")
                continue
            components_built.append(cid)

            if anchors:
                # ── stamp pattern: anchor generator + copytopoints + id-overwrite ──
                # A2-station: resolve position_expr/orient_expr/pscale_expr
                # against the asset params at BUILD time (deterministic).
                resolved_anchors, anc_expr_errors = _resolve_anchor_exprs(
                    anchors, param_values, cid)
                for ae in anc_expr_errors:
                    errors_runtime.append(ae)
                if anc_expr_errors:
                    continue  # anchors broken; skip stamping
                anchor_ids = [a["component_id"] for a in resolved_anchors]
                anchors_built[cid] = len(resolved_anchors)

                # anchor generator python SOP (fed numeric, resolved anchors)
                anc_name = f"{cid}_anchors"
                anc_sop = _safe_create_node(root_path, "python", anc_name)
                _set_parm_safe(anc_sop, "python", _anchor_generator_code(resolved_anchors, cid))
                anc_sop.cook(force=True)
                anc_errs = list(anc_sop.errors() or [])
                if anc_errs:
                    warnings.append(f"component '{cid}' anchors: {anc_errs}")

                # copytopoints: in0 = component geometry, in1 = anchor points
                copy_name = f"copy_{cid}"
                copy_node = _safe_create_node(root_path, "copytopoints", copy_name)
                copy_node.setInput(0, out_sop)
                copy_node.setInput(1, anc_sop)

                # id-overwrite python SOP: gives each instance its anchor
                # component_id, AND bakes edini_world_axis per instance when
                # the recipe declared construction axes (B-station).
                ow_name = f"{cid}_idfix"
                ow_sop = _safe_create_node(root_path, "python", ow_name)
                stamp_world_axes = [
                    world_axis_by_cid.get(aid)
                    for aid in anchor_ids
                ]
                # Only bake if ALL anchors of this component resolved a world
                # axis (partial baking would leave some instances tag-less and
                # silently fall back to PCA for them — confusing). If any is
                # missing, pass None to keep the idfix on the PCA fallback.
                if any(wa is None for wa in stamp_world_axes):
                    stamp_world_axes_param: list[tuple[float, float, float]] | None = None
                else:
                    stamp_world_axes_param = stamp_world_axes  # type: ignore[assignment]
                _set_parm_safe(
                    ow_sop, "python",
                    _component_id_overwrite_snippet(
                        anchor_ids, world_axes=stamp_world_axes_param))
                ow_sop.setInput(0, copy_node)
                # Cook the idfix so the per-instance component_id lands on geometry.
                # (Real Houdini lazy-cooks on OUT; explicit is safer and works in tests.)
                ow_sop.cook(force=True)
                ow_errs = list(ow_sop.errors() or [])
                if ow_errs:
                    warnings.append(f"component '{cid}' idfix: {ow_errs}")

                comp_nodes.append(ow_sop)
                stamped.append((cid, ow_sop, anchor_ids))
            else:
                # ── direct: component geometry straight into merge ──
                comp_nodes.append(out_sop)

        if not comp_nodes:
            errors_runtime.append("no component output nodes were built")

        # ── 2. Merge all component streams ──
        merge_node = None
        last_node = None
        if comp_nodes and not errors_runtime:
            merge_node = _safe_create_node(root_path, "merge", "merge_all")
            for idx, node in enumerate(comp_nodes):
                merge_node.setInput(idx, node)
            last_node = merge_node

        # ── 3. Post-processing chain ──
        if last_node is not None:
            from edini.parm_catalog import NODE_ALIASES
            for i, pp in enumerate(postprocess):
                pp_type = pp["type"]
                pp_type = NODE_ALIASES.get(pp_type, pp_type)  # resolve alias
                pp_params = pp.get("params") or {}
                pp_name = f"post_{i}_{_sanitize_node_name(pp_type)}"
                try:
                    pp_node = _safe_create_node(root_path, pp_type, pp_name)
                except Exception as e:
                    warnings.append(
                        f"postprocess[{i}] '{pp_type}' could not be created: {e}; skipped")
                    continue
                pp_node.setInput(0, last_node)
                for pname, pval in pp_params.items():
                    try:
                        _set_parm_safe(pp_node, pname, pval)
                    except Exception as e:
                        warnings.append(
                            f"postprocess[{i}] '{pp_type}' parm '{pname}': {e}")
                last_node = pp_node

        # ── 4. OUT null ──
        if last_node is not None:
            out_node = _safe_create_node(root_path, "null", "OUT")
            out_node.setInput(0, last_node)
            out_node.setDisplayFlag(True)
            out_path = out_node.path()
            try:
                root.layoutChildren()
            except Exception:
                pass

        if errors_runtime:
            raise RuntimeError("; ".join(errors_runtime))

        if not out_path:
            raise RuntimeError("builder produced no OUT node")

        # ── 5. Cook OUT + collect errors ──
        out_node = hou.node(out_path)
        cook_errors: list[str] = []
        try:
            out_node.cook(force=True)
            cook_errors = list(out_node.errors() or [])
            # Also surface errors from component SOPs (a component can fail
            # without OUT reporting it on the display node).
            for sub in root.allSubChildren():
                try:
                    sub_errs = list(sub.errors() or [])
                except Exception:
                    sub_errs = []
                for e in sub_errs:
                    tag = f"[{sub.name()}] {e}"
                    if tag not in cook_errors:
                        cook_errors.append(tag)
        except Exception as e:
            cook_errors.append(f"OUT cook raised: {e}")

        if cook_errors:
            raise RuntimeError("; ".join(cook_errors))

        # ── 6. component_id presence check ──
        # Read from the gate target (largest component_id-bearing node), which
        # is the merge/OUT in real Houdini. This is more robust than relying on
        # OUT.geometry() (which stays empty for a null until cooked downstream).
        component_id_check = {"missing": [], "ok": []}
        try:
            gate_target = _select_gate_target(root)
            gate_geo = gate_target.geometry() if gate_target is not None else None
            declared_cids = {c["id"] for c in components}
            # For stamped components, the per-instance ids replace the template id
            for cid, _ow, anchor_ids in stamped:
                declared_cids.discard(cid)
                declared_cids.update(anchor_ids)
            found_cids = _geometry_component_ids(gate_geo) if gate_geo else set()
            for cid in sorted(declared_cids):
                (component_id_check["ok"] if cid in found_cids
                 else component_id_check["missing"]).append(cid)
        except Exception as e:
            warnings.append(f"component_id check failed: {e}")

        # ── 6b. G2 bake gate: every prim must carry a non-zero edini_world_axis ──
        # Decision 6/11 + spec §4 G2. The builder bakes edini_world_axis on
        # every component (direct-merge via tag/suffix, stamped via idfix).
        # A missing or zero axis means a backend forgot to wire the bake — a
        # build bug, surfaced now rather than at commit (G3 repeats the check
        # as the final defense-in-depth layer against raw-sandbox bypass).
        g2_baked = True
        g2_missing: list[str] = []
        g2_detail: list[str] = []
        try:
            gate_target = _select_gate_target(root)
            if gate_target is not None:
                g2_baked, g2_missing, g2_detail = _verify_world_axes_baked(gate_target)
        except Exception as e:
            warnings.append(f"G2 bake check failed: {e}")
        if not g2_baked:
            raise RuntimeError(
                "G2_NOT_BAKED: build did not bake edini_world_axis on every "
                "prim. This means a backend skipped the axis bake (a build "
                f"bug) or the asset was not built via build_procedural_asset. "
                f"Missing on: {g2_missing}. Detail: {g2_detail[:10]}")

        # ── 7. Diagnostics + structural checks + gate previews ──
        diag = _safe_collect_diagnostics(out_path, include_geometry=True)
        geo_stats = diag.get("geometry") or {}
        structural_checks = {
            "has_geometry": geo_stats.get("point_count", 0) > 0,
            "point_count": geo_stats.get("point_count", 0),
            "prim_count": geo_stats.get("prim_count", 0),
            "bounds_nonzero": _bounds_nonzero(geo_stats),
        }

        response: dict[str, Any] = {
            "success": True,
            "execution_mode": EXECUTION_MODE_LIVE,
            "build_mode": "recipe",
            "job_id": job_id,
            "root_path": root_path,
            "output_node": out_path,
            "components_built": components_built,
            "anchors_built": anchors_built,
            "component_id_check": component_id_check,
            "params_summary": param_install if param_install else {},
            "diagnostics": diag,
            "structural_checks": structural_checks,
            "warnings": warnings,
            "preserved": True,
            "deleted": False,
        }

        # Stage-3: surface the deterministic construction axes baked on every
        # component (decision 6 — ALL components get an axis, not just those
        # with asserts). `defaulted_axes` flags components whose axis came from
        # tier 3 (backend inference) or tier 4 (Y fallback) rather than an
        # explicit declaration — the agent should review those.
        if world_axis_by_cid:
            response["construction_axis_summary"] = {
                cid: {
                    "world_axis": [round(c, 6) for c in ax],
                    "method": "construction",
                }
                for cid, ax in sorted(world_axis_by_cid.items())
            }
        if defaulted_axes:
            response["defaulted_axes"] = defaulted_axes
            response["warnings"].append(
                "Some components had no explicit construction_axis and were "
                "assigned an inferred/fallback axis: "
                + ", ".join(f"{c}={a}" for c, a in sorted(defaulted_axes.items()))
                + ". Review these in the receipt — if the inferred axis is "
                "wrong, declare construction_axis explicitly on the component "
                "or its orientation_assert.")

        # structure advisory (reuses the same gate commit_sandbox enforces)
        try:
            struct_check = _run_structure_gate(root_path)
            if struct_check is not None:
                response["structure_advisory"] = struct_check
        except Exception as e:
            response["structure_advisory_error"] = str(e)

        # Phase A validation report (if available — informational, already passed)
        if phase_a_report is not None:
            response["phase_a_validation"] = {
                "passed": True,
                "stages": phase_a_report.get("stages", {}),
                "warning_count": phase_a_report.get("warning_count", 0),
            }

        # orientation preview (advisory only — commit enforces it as a hard gate).
        # Run against the gate target (the component_id-bearing node), not the
        # bare OUT null, so verify_orientation actually finds the component_id
        # prim attribute. In real Houdini OUT carries the merged geo; the gate
        # target selection matches what commit_sandbox's gate will inspect.
        if orientation_asserts:
            try:
                from edini.node_utils import verify_orientation
                gate_target = _select_gate_target(root)
                ori = verify_orientation(gate_target.path(), orientation_asserts)
                response["orientation_check"] = {
                    "passed": ori.get("passed", 0),
                    "failed": ori.get("failed", 0),
                    "total": ori.get("total", 0),
                    "checks": ori.get("checks", []),
                }
                if not ori.get("success"):
                    response["orientation_check_error"] = ori.get("error", "")
            except Exception as e:
                response["orientation_check_error"] = str(e)

        if component_id_check["missing"]:
            response["warnings"].append(
                "component_id missing on OUT for: "
                + ", ".join(component_id_check["missing"])
                + " — these components' orientation checks will fail at commit.")

        return response

    except Exception as e:
        execution_traceback = traceback.format_exc()
        diag = _safe_collect_diagnostics(
            out_path or root_path, include_geometry=True)

        deleted = False
        if delete_on_failure:
            try:
                _destroy_node(root_path)
                deleted = True
            except Exception:
                pass

        return {
            "success": False,
            "execution_mode": EXECUTION_MODE_LIVE,
            "build_mode": "recipe",
            "job_id": job_id,
            "root_path": root_path,
            "output_node": out_path,
            "components_built": components_built,
            "anchors_built": anchors_built,
            "error": str(e),
            "traceback": execution_traceback,
            "diagnostics": diag,
            "warnings": warnings,
            "preserved": not deleted,
            "deleted": deleted,
        }


# ===========================================================================
# Variant Scatter (V-station) — multi-source Copy-to-Points via piece attr
# ===========================================================================
# build_variant_scatter builds a network where DIFFERENT variant geometries are
# scattered onto points according to a weighted, seeded distribution. This is
# the modern (H19.5+) workflow: pack each variant, tag with an integer `variant`
# attribute, let Attribute from Pieces + Copy to Points (piece attribute) pick
# the right variant per point.
#
# Why a separate tool (not a recipe extension): build_procedural_asset's idfix
# (_component_id_overwrite_snippet) detects copy boundaries via
# `per_copy = total // n_anchors`, which assumes ONE uniform source geometry.
# A variant library has different prim counts per variant, so that boundary
# detection breaks. This tool owns a piece-attribute-based id strategy instead.

# Name of the integer piece attribute Copy to Points 2.0 reads by default to
# dispatch variants (Houdini 21). Must be int or string — never float.
_VARIANT_PIECE_ATTR = "variant"

def _setup_copy_apply_attributes(copy_node, attribs: str = "id") -> bool:
    """Initialize Copy to Points 2.0's attribute transfer so the target
    point's attributes (notably ``id``) are stamped onto every instance.

    Why this exists: the per-instance ``id`` must be identical for ALL prims of
    one copied instance — even when the variant is a disconnected mesh (e.g. a
    window = frame + glass + mullions). Connectivity can't give that (it would
    assign different piece values to the disconnected parts). Copy to Points'
    "Attributes from Target" stamps the target point's attribute onto the whole
    copied piece in one shot, so we use it to carry ``id``.

    Real-H21 mechanism (verified on 21.0.440): the ``targetattribs`` parm is a
    multiparm Folder whose instance count starts at 0 (no transfer). The
    ``resettargetattribs`` BUTTON, when pressed, auto-populates the folder with
    sensible default entries — entry #1 is ``applymethod=0`` (copy) with
    ``applyattribs='*,^v,^Alpha,^N,^up,^pscale,^scale,^orient,^rot,^pivot,
    ^trans,^transform'``, which copies every target-point attribute EXCEPT the
    transform family. That default already includes ``id`` (and ``variant``),
    so simply pressing the button is sufficient — no per-instance parm
    manipulation needed.

    The previous implementation tried to grow the multiparm manually via
    setMultiparmInstanceCount / count-parm probes / PTG folder growth; all
    three failed on real H21 because the count-parm name is ``targetattribs``
    (not numapplyattrs) and H21 lacks setMultiparmInstanceCount. The button is
    Houdini's own sanctioned initialization path. See
    manual_resettargetattribs_probe.py for the captured structure.

    Args:
        copy_node: the copytopoints::2.0 node.
        attribs: unused after the button-press simplification (kept for API
            compatibility with older callers). The default entry transfers all
            non-transform attributes, which already covers ``id``.

    Returns:
        True if the button was found and pressed; False otherwise (caller
        emits a warning so the user can transfer attributes manually).
    """
    # Delegate to the single shared implementation in node_utils, so the
    # variant-scatter path, _post_create_init, and node_utils.create_node all
    # press the same button via one code path.
    from edini.node_utils import _init_copytopoints_attribs
    return _init_copytopoints_attribs(copy_node)


def _validate_variant_recipe(recipe: Any) -> list[str]:
    """Validate a variant-scatter recipe. Returns a list of error strings
    (empty = valid). Mirrors the shape of _validate_recipe."""
    errors: list[str] = []

    if not isinstance(recipe, dict):
        return ["recipe must be a JSON object"]

    variants = recipe.get("variants")
    if not isinstance(variants, list) or not variants:
        errors.append("recipe.variants must be a non-empty list")
        return errors  # nothing else to check meaningfully

    seen_ids: set[str] = set()
    for i, v in enumerate(variants):
        if not isinstance(v, dict):
            errors.append(f"variants[{i}] must be an object")
            continue
        vid = v.get("id")
        if not isinstance(vid, str) or not vid:
            errors.append(f"variants[{i}].id must be a non-empty string")
        elif vid in seen_ids:
            errors.append(f"variants[{i}].id duplicates an earlier variant id")
        else:
            seen_ids.add(vid)
        code = v.get("code")
        if not isinstance(code, str) or not code:
            errors.append(f"variants[{i}].code must be a non-empty string")

    scatter = recipe.get("scatter")
    if not isinstance(scatter, dict):
        errors.append("recipe.scatter must be an object")
    else:
        src = scatter.get("source")
        if not isinstance(src, str) or not src:
            errors.append("scatter.source must be a non-empty string "
                          "(python code emitting scatter points)")
        seed = scatter.get("seed", 0)
        if not isinstance(seed, int) or isinstance(seed, bool):
            errors.append("scatter.seed must be an integer (for reproducibility)")
        weights = scatter.get("weights")
        if weights is not None:
            if not isinstance(weights, dict):
                errors.append("scatter.weights must be an object {variant_id: weight}")
            else:
                for wid, w in weights.items():
                    if wid not in seen_ids:
                        errors.append(
                            f"scatter.weights references unknown variant '{wid}'")
                    if not isinstance(w, (int, float)) or isinstance(w, bool):
                        errors.append(
                            f"scatter.weights['{wid}'] must be a number")
                # Weights are auto-normalized at build time; only flag the
                # pathological all-zero case (can't normalize).
                if weights and isinstance(weights, dict) and all(
                        isinstance(w, (int, float)) and w == 0
                        for w in weights.values()):
                    errors.append("scatter.weights are all zero — cannot normalize")

    return errors


def _variant_idfix_snippet(variant_ids: list[str]) -> str:
    """Generate a single-SOP python cook body that runs AFTER unpacking, and
    overwrites prim component_id per instance.

    The prim-level integer `variant` attribute (tagged on the source variant
    geometry) survives unpack — it identifies WHICH variant each prim belongs
    to. The integer `id` attribute (set on the scatter points and transferred
    onto instance points via Copy to Points "Apply Attributes") identifies
    WHICH instance (copy) the prim belongs to. Combined these yield a
    globally-unique component_id `{variant_id}_{id}`.

    This is more robust than Connectivity because `id` is identical for all
    prims of an instance even when the variant is a disconnected mesh
    (e.g. a window = frame + glass + mullions as separate pieces).
    Connectivity would assign DIFFERENT piece values to parts of one such
    instance, corrupting the component_id.

    This intentionally does NOT use the `per_copy = total // n_anchors`
    boundary detection of _component_id_overwrite_snippet, because variant
    sources have differing prim counts.
    """
    ids_repr = "[" + ", ".join(repr(c) for c in variant_ids) + "]"
    return (
        "node = hou.pwd()\n"
        "geo = node.geometry()\n"
        "variant_ids = " + ids_repr + "\n"
        "# `variant` is a PRIM attrib (survives unpack from source tagging).\n"
        "# `id` is a POINT attrib transferred from the target scatter point\n"
        "# via Copy to Points Apply Attributes — identical for all prims of\n"
        "# one instance, regardless of variant connectivity.\n"
        "if geo.findPrimAttrib('component_id') is None:\n"
        "    geo.addAttrib(hou.attribType.Prim, 'component_id', '')\n"
        "# Stage-4: bake edini_world_axis so variant-scatter assets pass the\n"
        "# G2/G3 bake gates (decision 1 — variant scatter is a build path).\n"
        "# Variants are detail scatter (windows, rocks, props) without a\n"
        "# meaningful construction-axis declaration, so we use the Y fallback\n"
        "# (upright). Recipe authors who care about per-variant orientation\n"
        "# should use build_procedural_asset with explicit construction_axis.\n"
        "if geo.findPrimAttrib('edini_world_axis') is None:\n"
        "    geo.addAttrib(hou.attribType.Prim, 'edini_world_axis', (0.0, 0.0, 0.0))\n"
        "for prim in geo.prims():\n"
        "    vidx = 0\n"
        "    try: vidx = int(prim.attribValue('" + _VARIANT_PIECE_ATTR + "'))\n"
        "    except Exception: vidx = 0\n"
        "    if vidx < 0 or vidx >= len(variant_ids):\n"
        "        vidx = 0\n"
        "    inst_id = 0\n"
        "    verts = prim.vertices()\n"
        "    if verts:\n"
        "        pt = verts[0].point()\n"
        "        try: inst_id = int(pt.attribValue('id'))\n"
        "        except Exception: inst_id = 0\n"
        "    cid = variant_ids[vidx] + '_' + str(inst_id)\n"
        "    prim.setAttribValue('component_id', cid)\n"
        "    prim.setAttribValue('edini_world_axis', (0.0, 1.0, 0.0))\n"
    )


def _variant_scatter_points_code(source_code: str) -> str:
    """Wrap the user's scatter `source` code with a per-point `id` attribute.

    The user's code emits points (with @P, optionally @orient/@pscale/@N).
    This wrapper numbers them with an integer point-level `id` attribute so
    each scatter point has a stable, globally-unique identity that survives
    the downstream Copy to Points (transferred onto instances via
    ``resettargetattribs``) and lets idfix build per-instance component_ids.

    NOTE: this wrapper NO LONGER assigns the ``variant`` attribute. Variant
    assignment is now done by the downstream ``attribfrompieces`` SOP, which
    draws a `variant` value onto each scatter point from the source piece
    library (pieceattrib=variant). AFP covers all variants reliably even at
    low point counts — the old hand-rolled weighted-random assignment could
    starve low-weight variants (e.g. seed=42 over 8 pts assigned zero points
    to variant 2). See manual_variant_dispatch_diagnose.py / progress doc.

    The user's code is executed verbatim first (it does its own geo.clear()
    and point emission); then this wrapper annotates the resulting points.
    """
    return (
        "# ── User scatter code (emits points) ──\n"
        + source_code
        + "\n"
        "# ── Per-point id (generated wrapper) ──\n"
        "# `variant` is assigned downstream by attribfrompieces, NOT here.\n"
        "geo.addAttrib(hou.attribType.Point, 'id', 0)\n"
        "for idx, pt in enumerate(geo.points()):\n"
        "    pt.setAttribValue('id', idx)\n"
    )


def _variant_tag_code(variant_index: int, user_code: str) -> str:
    """Wrap a variant's user code so that, after it emits its geometry, every
    prim is tagged with an integer `variant` attribute = variant_index (in
    addition to whatever component_id the user set). This attribute survives
    packing and is what Attribute from Pieces / Copy to Points reads."""
    return (
        "# ── Variant geometry code ──\n"
        + user_code
        + "\n"
        "# ── Tag every prim with the variant piece index ──\n"
        "geo.addAttrib(hou.attribType.Prim, '" + _VARIANT_PIECE_ATTR + "', 0)\n"
        "for prim in geo.prims():\n"
        "    prim.setAttribValue('" + _VARIANT_PIECE_ATTR + "', "
        + repr(int(variant_index)) + ")\n"
    )


def build_variant_scatter(
    recipe: dict,
    *,
    sandbox_name: str | None = None,
    delete_on_failure: bool = False,
) -> dict[str, Any]:
    """Build a variant-scatter asset: multiple variant geometries distributed
    onto scatter points via a weighted, seeded distribution, using the modern
    packed-primitive + piece-attribute workflow (Attribute from Pieces +
    Copy to Points 2.0).

    The recipe describes variant source geometries (each pure-geometry python
    code), a scatter source (python code emitting points), an optional weighted
    distribution + seed, and the usual postprocess / orientation asserts.

    Commit is a separate explicit step: ``houdini_commit_sandbox(root_path,
    name, orientation_checks=recipe['orientation_asserts'])``.

    Per-instance ``component_id`` is assigned as ``{variant_id}_{ptnum}`` so
    orientation verification can PCA each instance independently.
    """
    errors = _validate_variant_recipe(recipe)
    if errors:
        return {
            "success": False,
            "execution_mode": EXECUTION_MODE_LIVE,
            "build_mode": "variant_scatter",
            "error": "Invalid recipe: " + "; ".join(errors),
            "validation_errors": errors,
            "preserved": False,
            "deleted": False,
        }

    variants = recipe.get("variants", [])
    variant_ids = [v["id"] for v in variants]
    scatter_spec = recipe.get("scatter", {})
    weights = scatter_spec.get("weights") or {}
    seed = scatter_spec.get("seed", 0)
    source_code = scatter_spec["source"]
    postprocess = recipe.get("postprocess") or []

    asset_name = recipe.get("asset_name") or "variant_asset"
    name = sandbox_name or asset_name
    job_id, root_path = _create_sandbox_root(name)

    warnings: list[str] = []
    variants_built: list[str] = []
    out_path = ""

    try:
        root = hou.node(root_path)
        if root is None:
            raise RuntimeError(f"Sandbox root not found after creation: {root_path}")

        # ── 1. One python SOP per variant (tagged with `variant` index) ──
        variant_nodes: list[Any] = []
        for i, v in enumerate(variants):
            py_name = f"{v['id']}_python"
            tagged = _variant_tag_code(i, v["code"])
            py_sop = _safe_create_node(root_path, "python", py_name)
            _set_parm_safe(py_sop, "python", tagged)
            try:
                py_sop.cook(force=True)
                cook_errs = list(py_sop.errors() or [])
            except Exception as e:
                cook_errs = [str(e)]
            if cook_errs:
                raise RuntimeError(
                    f"variant '{v['id']}' cook failed: " + "; ".join(cook_errs))
            variant_nodes.append(py_sop)
            variants_built.append(v["id"])

        if not variant_nodes:
            raise RuntimeError("no variant source nodes were built")

        # ── 2. Merge variants → pack each into its OWN packed prim ──
        # Each variant is tagged with an integer `variant` piece attribute by
        # _variant_tag_code. Pack By Name (on that integer attribute) produces
        # exactly one packed primitive per variant index.
        variants_merge = _safe_create_node(root_path, "merge", "variants_merge")
        for idx, node in enumerate(variant_nodes):
            variants_merge.setInput(idx, node)

        # variants_merge is used UNPACKED — H21 Copy to Points dispatches on
        # plain source geometry by matching source prim `variant` against target
        # point `variant`. (Packing via Pack By Name HIDES the prim `variant`
        # inside the PackedFragment, making it unreadable to Copy's piece
        # dispatch — verified broken on 21.0.440. See
        # manual_variant_dispatch_diagnose.py / manual_attribfrompieces_probe.py.)

        # ── 3. Scatter source — emit target points + per-point id ───────────
        # The wrapper NO LONGER assigns `variant` here. Variant assignment is
        # delegated to the downstream attribfrompieces SOP (step 4), which
        # draws a `variant` value onto each point from the source piece library
        # and reliably covers ALL variants even at low point counts. The old
        # hand-rolled weighted-random assignment could starve low-weight
        # variants (seed=42 over 8 pts → zero points for variant 2 → win_c
        # never instanced).
        scatter_code = _variant_scatter_points_code(source_code)
        scatter_sop = _safe_create_node(root_path, "python", "scatter_points")
        _set_parm_safe(scatter_sop, "python", scatter_code)
        try:
            scatter_sop.cook(force=True)
            cook_errs = list(scatter_sop.errors() or [])
        except Exception as e:
            cook_errs = [str(e)]
        if cook_errs:
            raise RuntimeError(
                "scatter source cook failed: " + "; ".join(cook_errs))

        # ── 4. attribfrompieces — give each scatter point a `variant` ───────
        #    input 0 = target points (scatter), input 1 = source piece library
        #    (the variant merge). pieceattrib=variant reads the source's per-prim
        #    `variant` to define the pieces, then assigns each target point a
        #    `variant` value drawn from that piece set (seed controls the draw).
        #    This is the H21-sanctioned way to scatter variants by attribute and
        #    guarantees every variant index present in the source gets instanced.
        afp_node = _safe_create_node(root_path, "attribfrompieces", "scatter_afp")
        afp_node.setInput(0, scatter_sop)      # target points
        afp_node.setInput(1, variants_merge)   # source piece library
        _set_parm_safe(afp_node, "pieceattrib", _VARIANT_PIECE_ATTR)
        _set_parm_safe(afp_node, "seed", int(seed))

        # ── 5. Copy to Points (piece attribute dispatches variants) ─────────
        #    H21 Copy to Points 2.0 uses `useidattrib` (the "Piece Attribute"
        #    toggle) + `idattrib` (the attribute NAME) to dispatch. The UNPACKED
        #    source prim `variant` matches the AFP-assigned target point
        #    `variant` 1:1 — no packing needed.
        copy_node = _safe_create_node(root_path, "copytopoints", "copy_scatter")
        copy_node.setInput(0, variants_merge)  # UNPACKED variant library (source)
        copy_node.setInput(1, afp_node)        # scatter points (with i@variant + i@id)
        try:
            copy_node.parm("useidattrib").set(1)   # enable Piece Attribute dispatch
            copy_node.parm("idattrib").set(_VARIANT_PIECE_ATTR)  # match by `variant`
        except Exception as e:
            warnings.append(
                f"Copy to Points piece-attribute setup failed ({e}); variants "
                f"may not dispatch correctly. Check copytopoints::2.0 parms.")

        # Transfer the target-point `id` (and other non-transform attributes)
        # onto each instance. Real-H21 path: press the `resettargetattribs`
        # BUTTON, which auto-populates the `targetattribs` multiparm with a
        # default entry that copies all attributes except the transform family
        # — already covering `id`. See manual_resettargetattribs_probe.py.
        if not _setup_copy_apply_attributes(copy_node, attribs="id"):
            warnings.append(
                "Copy to Points attribute transfer could not be initialized "
                "(resettargetattribs button missing); per-instance id may not "
                "transfer. idfix falls back to id=0.")

        # NO Unpack node: Copy on UNPACKED source already yields expanded
        # geometry, so per-prim component_id overwrite is possible directly.

        # ── 6. idfix — assign per-instance component_id {variant_id}_{id} ───
        # Reads the prim `variant` (which variant, tagged on the source prim and
        # carried through Copy) + the point `id` (which instance, transferred
        # from the target scatter point via resettargetattribs) to build a
        # globally-unique id per instance.
        idfix_code = _variant_idfix_snippet(variant_ids)
        idfix = _safe_create_node(root_path, "python", "scatter_idfix")
        _set_parm_safe(idfix, "python", idfix_code)
        idfix.setInput(0, copy_node)
        # Force-cook the idfix so per-instance component_id + edini_world_axis
        # (Stage-4 bake) actually land on geometry in both the mock and real
        # Houdini. Without this the OUT/gate-target reads the upstream copy
        # geometry which has template-level component_id but no axis.
        try:
            idfix.cook(force=True)
        except Exception:
            pass

        last_node = idfix

        # ── 7. Post-processing chain (fuse/clean/normal ...) ──
        for i, pp in enumerate(postprocess):
            pp_type = pp.get("type")
            pp_params = pp.get("params") or {}
            if not isinstance(pp_type, str) or not pp_type:
                warnings.append(f"postprocess[{i}] has no type; skipped")
                continue
            pp_name = f"post_{i}_{_sanitize_node_name(pp_type)}"
            try:
                pp_node = _safe_create_node(root_path, pp_type, pp_name)
            except Exception as e:
                warnings.append(
                    f"postprocess[{i}] '{pp_type}' could not be created: {e}; skipped")
                continue
            pp_node.setInput(0, last_node)
            for pname, pval in pp_params.items():
                try:
                    _set_parm_safe(pp_node, pname, pval)
                except Exception as e:
                    warnings.append(
                        f"postprocess[{i}] '{pp_type}' parm '{pname}': {e}")
            last_node = pp_node

        # ── 9. OUT ──
        out_node = _safe_create_node(root_path, "null", "OUT")
        out_node.setInput(0, last_node)
        out_node.setDisplayFlag(True)
        out_path = out_node.path()
        try:
            root.layoutChildren()
        except Exception:
            pass

        # ── 10. Cook OUT + collect errors ──
        cook_errors: list[str] = []
        cook_exc: Exception | None = None
        try:
            out_node.cook(force=True)
        except Exception as e:
            cook_exc = e
        # Whether or not cook raised, scan every node for its own error/warning
        # messages — Houdini stores per-node cook diagnostics that survive the
        # raised exception and pinpoint WHICH node failed.
        for sub in root.allSubChildren():
            try:
                sub_errs = list(sub.errors() or [])
            except Exception:
                sub_errs = []
            try:
                sub_warns = list(sub.warnings() or [])
            except Exception:
                sub_warns = []
            for e in sub_errs:
                tag = f"[{sub.name()} ERROR] {e}"
                if tag not in cook_errors:
                    cook_errors.append(tag)
            for w in sub_warns:
                tag = f"[{sub.name()} warn] {w}"
                if tag not in cook_errors:
                    cook_errors.append(tag)
        if cook_exc is not None:
            cook_errors.insert(0, f"OUT cook raised: {cook_exc}")

        if cook_errors:
            raise RuntimeError("; ".join(cook_errors))

        # ── 11. component_id presence check ──
        component_id_check = {"missing": [], "ok": []}
        try:
            gate_target = _select_gate_target(root)
            gate_geo = gate_target.geometry() if gate_target is not None else None
            found_cids = _geometry_component_ids(gate_geo) if gate_geo else set()
            # We can't predict exact per-instance ids ({variant}_{ptnum}) without
            # cooking the scatter, so just confirm at least one cid per variant
            # prefix is present, and report what we found.
            for vid in variant_ids:
                if any(cid.startswith(vid + "_") or cid == vid
                       for cid in found_cids):
                    component_id_check["ok"].append(vid)
                else:
                    component_id_check["missing"].append(vid)
        except Exception as e:
            warnings.append(f"component_id check failed: {e}")

        # ── 12. Diagnostics + structure gate + orientation preview ──
        diag = _safe_collect_diagnostics(out_path, include_geometry=True)
        geo_stats = diag.get("geometry") or {}
        structural_checks = {
            "has_geometry": geo_stats.get("point_count", 0) > 0,
            "point_count": geo_stats.get("point_count", 0),
            "prim_count": geo_stats.get("prim_count", 0),
            "bounds_nonzero": _bounds_nonzero(geo_stats),
        }
        structure_advisory = _run_structure_gate(root_path) or {
            "passed": True, "is_monolithic": False,
            "reason": "structure gate unavailable", "suggestion": "",
            "details": {},
        }

        response: dict[str, Any] = {
            "success": True,
            "execution_mode": EXECUTION_MODE_LIVE,
            "build_mode": "variant_scatter",
            "job_id": job_id,
            "root_path": root_path,
            "output_node": out_path,
            "variants_built": variants_built,
            "n_variants": len(variants_built),
            "weights": {vid: weights.get(vid, 1.0) for vid in variant_ids},
            "seed": seed,
            "piece_attribute": _VARIANT_PIECE_ATTR,
            "component_id_check": component_id_check,
            "diagnostics": diag,
            "structural_checks": structural_checks,
            "structure_advisory": structure_advisory,
            "warnings": warnings,
            "preserved": True,
            "deleted": False,
        }

        # Orientation preview (same shape as build_procedural_asset).
        orientation_asserts = recipe.get("orientation_asserts") or []
        if orientation_asserts:
            try:
                from edini.node_utils import verify_orientation
                ori = verify_orientation(out_path, orientation_asserts)
                response["orientation_check"] = {
                    "passed": ori.get("passed", 0),
                    "failed": ori.get("failed", 0),
                    "total": ori.get("total", 0),
                    "checks": ori.get("checks", []),
                }
                if not ori.get("success"):
                    response["orientation_check_error"] = ori.get("error", "")
            except Exception as e:
                response["orientation_check_error"] = str(e)

        return response

    except Exception as e:
        execution_traceback = traceback.format_exc()
        diag = _safe_collect_diagnostics(
            out_path or root_path, include_geometry=True)
        deleted = False
        if delete_on_failure:
            try:
                _destroy_node(root_path)
                deleted = True
            except Exception:
                pass
        return {
            "success": False,
            "execution_mode": EXECUTION_MODE_LIVE,
            "build_mode": "variant_scatter",
            "job_id": job_id,
            "root_path": root_path,
            "output_node": out_path,
            "variants_built": variants_built,
            "error": str(e),
            "traceback": execution_traceback,
            "diagnostics": diag,
            "warnings": warnings,
            "preserved": not deleted,
            "deleted": deleted,
        }


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


def validate_recipe_tool(
    recipe: dict,
    catalog_path: str | None = None,
) -> dict[str, Any]:
    """Tool wrapper for Phase A validation.

    Args:
        recipe: The recipe dict to validate.
        catalog_path: Path to parm-catalog.json. Defaults to
                      <edini>/python3.11libs/edini/data/parm-catalog.json
    Returns:
        ValidationReport dict with success, passed, errors, etc.
    """
    import os

    if catalog_path is None:
        catalog_path = os.path.join(
            os.path.dirname(__file__), "data", "parm-catalog.json"
        )
    if not os.path.exists(catalog_path):
        return {
            "success": False,
            "error": (
                "Parm catalog not found. Run dump_parm_catalog() first, "
                "or pass catalog_path to an existing catalog."
            ),
        }
    from edini.recipe_validator import validate_recipe as _validate
    result = _validate(recipe, catalog_path)
    result["success"] = True
    return result

