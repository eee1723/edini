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

    # ── Orientation gate ──
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
                    "Orientation verification failed — refusing to commit. "
                    "Fix the defects below (each comes with a fix quaternion), "
                    "or pass skip_orientation=true only if you have a documented "
                    "reason."
                ),
                "orientation": orientation_result,
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

    result = {
        "success": True,
        "sandbox_root_path": sandbox_root_path,
        "final_path": actual_final_path,
        "committed": True,
    }
    if orientation_result is not None:
        result["orientation"] = orientation_result
    return result


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

    target = root
    # Walk down to a displayed SOP if available
    for child_name in ("edini_generate", "OUT", "out"):
        child = root.node(child_name) if hasattr(root, "node") else None
        if child is not None:
            try:
                geo = child.geometry()
                if geo is not None:
                    target = child
                    break
            except Exception:
                continue
    # Fall back to recursing for any displayed child
    if target is root:
        try:
            for sub in [c for c in root.allSubChildren() if hasattr(c, "geometry")]:
                try:
                    if sub.geometry() is not None and sub.isDisplayFlag():
                        target = sub
                        break
                except Exception:
                    continue
        except Exception:
            pass

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


def run_python_sandbox(
    code: str,
    sandbox_name: str = "procedural",
    commit_on_success: bool = False,
    delete_on_failure: bool = False,
) -> dict[str, Any]:
    job_id, root_path = _create_sandbox_root(sandbox_name)

    # Create Python SOP inside sandbox
    sandbox_root = hou.node(root_path)
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
            "bounds_nonzero": (
                isinstance(geo_stats.get("bounds", {}).get("size"), list)
                and any(abs(c) > 1e-6 for c in geo_stats["bounds"]["size"])
                if geo_stats.get("bounds", {}).get("size") else False
            ),
        }

        response = {
            "success": True,
            "job_id": job_id,
            "execution_mode": EXECUTION_MODE_LIVE,
            "root_path": root_path,
            "output_node": output_node_path,
            "output": _safe_getvalue(stdout_capture) or "(no output)",
            "stderr": _safe_getvalue(stderr_capture),
            "diagnostics": diag,
            "structural_checks": structural_checks,
            "commit_requested": bool(commit_on_success),
            "committed": False,
        }

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
