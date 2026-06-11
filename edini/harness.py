"""Procedural harness helpers for safer Houdini generation."""
from __future__ import annotations

import datetime as _dt
import io
import json
import re
import sys
import traceback
from typing import Any

import hou


EXECUTION_MODE_LIVE = "live_sandbox"


def make_job_id(label: str = "job") -> str:
    safe = re.sub(r"[^A-Za-z0-9_]+", "_", label).strip("_").lower() or "job"
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{stamp}_{safe}"


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
        result["parameters"] = [
            {"name": p.name(), "label": p.description(), "value": p.eval()}
            for p in node.parms()
        ]

    return result
