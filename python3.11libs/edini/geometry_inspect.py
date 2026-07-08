"""Geometry read + health inspection (hou wrappers).

Split out of node_utils.py in the Phase 4 refactor. Re-exported from
``edini.node_utils`` for backwards compatibility.
"""
from __future__ import annotations

import os
import json
import re
import traceback

try:
    import hou
except ImportError:  # offline / unit tests install a mock into sys.modules
    hou = None  # type: ignore[assignment]
from typing import Any





def _vector_to_list(value) -> list[float]:
    try:
        return [float(value[0]), float(value[1]), float(value[2])]
    except Exception:
        return [float(value.x()), float(value.y()), float(value.z())]


def _geometry_bounds(geo) -> dict[str, list[float]] | None:
    try:
        raw = geo.intrinsicValue("bounds")
        if raw is not None and len(raw) == 6:
            mn = [float(raw[0]), float(raw[2]), float(raw[4])]
            mx = [float(raw[1]), float(raw[3]), float(raw[5])]
            return {
                "min": mn,
                "max": mx,
                "size": [mx[0] - mn[0], mx[1] - mn[1], mx[2] - mn[2]],
            }
    except Exception:
        pass

    try:
        bbox = geo.boundingBox()
        if bbox is None:
            return None
        mn = _vector_to_list(bbox.minvec())
        mx = _vector_to_list(bbox.maxvec())
        return {
            "min": mn,
            "max": mx,
            "size": [mx[0] - mn[0], mx[1] - mn[1], mx[2] - mn[2]],
        }
    except Exception:
        return None


def inspect_geometry(node_path: str) -> dict[str, Any]:
    """Inspect the geometry output of a SOP node."""
    try:
        node = hou.node(node_path)
        if node is None:
            return {"success": False, "error": f"Node not found: {node_path}"}

        geo = node.geometry()
        if geo is None:
            return {"success": False, "error": f"No geometry on {node_path}"}

        attribs = []
        for attr in geo.pointAttribs():
            attribs.append({"name": attr.name(), "type": str(attr.dataType()), "class": "point"})
        for attr in geo.primAttribs():
            attribs.append({"name": attr.name(), "type": str(attr.dataType()), "class": "prim"})
        for attr in geo.vertexAttribs():
            attribs.append({"name": attr.name(), "type": str(attr.dataType()), "class": "vertex"})
        for attr in geo.globalAttribs():
            attribs.append({"name": attr.name(), "type": str(attr.dataType()), "class": "detail"})

        return {
            "success": True,
            "path": node_path,
            "point_count": geo.intrinsicValue("pointcount"),
            "prim_count": geo.intrinsicValue("primitivecount"),
            "vertex_count": geo.intrinsicValue("vertexcount"),
            "attributes": attribs,
            "bounds": _geometry_bounds(geo),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def _component_bounds(geo, prim_subset) -> dict[str, Any] | None:
    """Compute bounds + centroid for a subset of prims of a geometry."""
    xs: list[float] = []
    ys: list[float] = []
    zs: list[float] = []
    for prim in prim_subset:
        for vtx in prim.vertices():
            p = vtx.point().position()
            xs.append(float(p[0])); ys.append(float(p[1])); zs.append(float(p[2]))
    if not xs:
        return None
    mn = (min(xs), min(ys), min(zs))
    mx = (max(xs), max(ys), max(zs))
    centroid = (sum(xs) / len(xs), sum(ys) / len(ys), sum(zs) / len(zs))
    return {
        "bounds": {"min": list(mn), "max": list(mx),
                   "size": [mx[i] - mn[i] for i in range(3)]},
        "centroid": [round(c, 4) for c in centroid],
    }


def geometry_inventory(node_path: str, max_components: int = 60) -> dict[str, Any]:
    """Build a per-component_id inventory of the geometry on a node.

    For each distinct `component_id` prim-attribute value, report:
      - prim_count, point_count (unique vertices)
      - bounds (min/max/size) and centroid
      - size relative to the whole-asset diagonal (fraction), so the caller can
        spot components that are present but tiny (the recurring "chain/pedals
        exist but vision reports them missing" failure).

    Returns {success, node_path, total_components, components: [...],
             whole_bounds, inventory_text}.
    `inventory_text` is a compact human-readable block meant to be fed to a
    vision model alongside a screenshot for cross-validation.
    """
    try:
        node = hou.node(node_path)
        if node is None:
            return {"success": False, "error": f"Node not found: {node_path}"}
        geo = node.geometry()
        if geo is None:
            return {"success": False, "error": f"No geometry on {node_path}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

    comp_attr = geo.findPrimAttrib("component_id")
    if comp_attr is None:
        # No component_id — fall back to a single whole-geometry entry
        bounds = _geometry_bounds(geo)
        return {
            "success": True,
            "node_path": node_path,
            "total_components": 0,
            "has_component_id": False,
            "whole_bounds": bounds,
            "inventory_text": (
                "(no @component_id attribute on this geometry; cannot break "
                "down per-component. Whole geometry bounds shown above.)"
            ),
        }

    # Bucket prims by component_id value
    buckets: dict[str, list] = {}
    for prim in geo.prims():
        try:
            cid = str(prim.stringAttribValue("component_id"))
        except Exception:
            cid = ""
        if not cid:
            cid = "(unlabeled)"
        buckets.setdefault(cid, []).append(prim)

    # Whole-asset diagonal for relative-size computation
    whole = _geometry_bounds(geo)
    whole_diag = 1.0
    if whole and whole.get("size"):
        s = whole["size"]
        whole_diag = max(1e-6, (s[0] ** 2 + s[1] ** 2 + s[2] ** 2) ** 0.5)

    components: list[dict[str, Any]] = []
    for cid in sorted(buckets.keys()):
        prims = buckets[cid]
        info = _component_bounds(geo, prims) or {
            "bounds": None, "centroid": [0, 0, 0]}
        seen_pts: set[int] = set()
        for prim in prims:
            for vtx in prim.vertices():
                seen_pts.add(vtx.point().number())
        size = info["bounds"]["size"] if info.get("bounds") else [0, 0, 0]
        diag = (size[0] ** 2 + size[1] ** 2 + size[2] ** 2) ** 0.5
        components.append({
            "component_id": cid,
            "prim_count": len(prims),
            "point_count": len(seen_pts),
            "bounds": info["bounds"],
            "centroid": info["centroid"],
            "size_fraction": round(diag / whole_diag, 4),
        })
        if len(components) >= max_components:
            break

    # Compact text for vision cross-validation
    lines = ["GEOMETRY_INVENTORY (component_id -> prim_count, size_fraction of whole):"]
    for c in components:
        flag = "  <-- SMALL" if c["size_fraction"] < 0.08 else ""
        lines.append(
            f"  {c['component_id']}: {c['prim_count']} prims, "
            f"{c['point_count']} pts, size={c['size_fraction']}{flag}"
        )
    inventory_text = "\n".join(lines)

    return {
        "success": True,
        "node_path": node_path,
        "has_component_id": True,
        "total_components": len(buckets),
        "components": components,
        "whole_bounds": whole,
        "inventory_text": inventory_text,
    }


def _edge_key(a: int, b: int) -> tuple[int, int]:
    """Canonical undirected edge key from two point numbers."""
    return (a, b) if a <= b else (b, a)


_HEALTH_BLOCKING_CHECKS = ("orphan_points", "open_curves")


_HEALTH_ADVISORY_CHECKS = (
    "degenerate_prims",
    "nonmanifold_edges",
    "open_boundary_edges",
    "coincident_points",
)


def inspect_geometry_health(
    node_path: str,
    degenerate_area_eps: float = 1e-7,
    coincident_eps: float = 1e-6,
    max_coincident_report: int = 20,
) -> dict[str, Any]:
    """Run structural health checks on a node's cooked geometry.

    Detects problems that viewport screenshots CANNOT reveal but that silently
    break procedural assets (and downstream sims/booleans/renders):

      - orphan_points:   points not referenced by any primitive
      - open_curves:     open (non-closed) curve primitives — usually stray
                         construction curves that should have been deleted
      - degenerate_prims: polygons/faces with ~zero area (slivers, colinear)
      - nonmanifold_edges: edges shared by 3+ polygons (bad topology)
      - open_boundary_edges: edges shared by exactly 1 polygon (holes in what
                         should be a closed surface)
      - coincident_points: distinct points within `coincident_eps` of each other
                         (duplicates that Fuse would merge)

    Each finding includes a `fix` recommendation naming the SOP to use.

    **Two-tier severity** (see _HEALTH_BLOCKING_CHECKS / _HEALTH_ADVISORY_CHECKS):
      - BLOCKING (gate overall_ok + commit): orphan_points, open_curves.
        These are unambiguous defects that always warrant a fix.
      - ADVISORY (reported, never block): degenerate_prims, nonmanifold_edges,
        open_boundary_edges, coincident_points. These are routinely tolerated
        or EXPECTED (open_boundary_edges on open surfaces like terrain or an
        intentional gateway opening). Treating them as blocking produced false
        ``overall_ok=False`` on clean geometry and drove rebuild loops.

    Returns {success, node_path, summary, checks: {...}, overall_ok,
    blocking_checks, advisory_checks}. ``overall_ok`` is True only if every
    BLOCKING check passes; ADVISORY findings never affect it. Each check also
    carries a ``severity`` field.
    """
    try:
        node = hou.node(node_path)
        if node is None:
            return {"success": False, "error": f"Node not found: {node_path}"}
        geo = node.geometry()
        if geo is None:
            return {"success": False, "error": f"No geometry on {node_path}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

    points = geo.points()
    prims = geo.prims()
    n_points = len(points)
    n_prims = len(prims)

    # ── Orphan points: points referenced by no prim ──
    referenced_pts: set[int] = set()
    for prim in prims:
        # Use prim.vertices() which works for polygons; curve prims also have
        # vertices. Guard per-prim to avoid one bad prim aborting the scan.
        try:
            for vtx in prim.vertices():
                referenced_pts.add(vtx.point().number())
        except Exception:
            continue
    orphan_pt_nums = [p.number() for p in points if p.number() not in referenced_pts]
    orphan_points = {
        "count": len(orphan_pt_nums),
        "sample": orphan_pt_nums[: max(0, max_coincident_report)],
        "passed": len(orphan_pt_nums) == 0,
        "fix": ("Delete orphans with a Blast/Delete SOP targeting unreferenced "
                "points, or add a Fuse SOP (Consolidate Points) to merge them."),
    }

    # ── Open curves: curve primitives that are not closed ──
    open_curve_prims: list[int] = []
    for prim in prims:
        try:
            # Prim type name: 'Poly', 'PolyLine'/'Mesh', 'NURBSCurve',
            # 'BezierCurve', etc. Anything curve-like that isn't closed is a
            # stray construction curve in a procedural asset.
            type_name = prim.type().name().lower()
            is_curve = ("curve" in type_name) or (type_name == "polyline")
            if is_curve and hasattr(prim, "isClosed") and not prim.isClosed():
                open_curve_prims.append(prim.number())
        except Exception:
            continue
    open_curves = {
        "count": len(open_curve_prims),
        "sample": open_curve_prims[:max_coincident_report],
        "passed": len(open_curve_prims) == 0,
        "fix": ("Open curves are usually leftover construction geometry. "
                "Blast them, or convert to closed polygons. They cause "
                "errors in Boolean/Sweep and pollute renders."),
    }

    # ── Degenerate prims: zero-area polygons ──
    # Area is obtained from the Houdini-native "measuredarea" intrinsic (the
    # true polygon area for polygons AND n-gons), falling back to a corrected
    # shoelace that sums the triangle fan over ALL vertices (not just the
    # first three). This fixes two prior defects that produced false positives
    # on legitimate tube/fan caps: (a) comparing 0.5*|cross|² (== 2·area²,
    # NOT area) against the eps, and (b) sampling only the first three verts.
    degenerate_prims: list[int] = []

    def _shoelace_fan_area(vts) -> float:
        # Sum of |cross(e0i, e0j)| / 2 over consecutive vertex pairs around a
        # reference vertex 0 — the true signed area for planar/convex faces.
        if len(vts) < 3:
            return 0.0
        p0 = vts[0].point().position()
        total = 0.0
        for k in range(1, len(vts) - 1):
            p1 = vts[k].point().position()
            p2 = vts[k + 1].point().position()
            e01 = (p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2])
            e02 = (p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2])
            cross = (
                e01[1] * e02[2] - e01[2] * e02[1],
                e01[2] * e02[0] - e01[0] * e02[2],
                e01[0] * e02[1] - e01[1] * e02[0],
            )
            mag = (cross[0] ** 2 + cross[1] ** 2 + cross[2] ** 2) ** 0.5
            total += 0.5 * mag
        return total

    for prim in prims:
        try:
            type_name = prim.type().name().lower()
            if "poly" not in type_name:
                continue  # only polygonal area is meaningful here
            verts = prim.vertices()
            if len(verts) < 3:
                degenerate_prims.append(prim.number())
                continue
            # Prefer the native measuredarea intrinsic (accurate for n-gons).
            area = None
            try:
                area = float(prim.intrinsicValue("measuredarea"))
            except Exception:
                area = None
            if area is None:
                area = _shoelace_fan_area(verts)
            if area < degenerate_area_eps:
                degenerate_prims.append(prim.number())
        except Exception:
            continue
    degenerate = {
        "count": len(degenerate_prims),
        "sample": degenerate_prims[:max_coincident_report],
        "passed": len(degenerate_prims) == 0,
        "fix": ("Use a Clean SOP (Remove Degenerate Faces) or Delete SOP by "
                "the listed primitive numbers. Degenerate faces break normals "
                "and subdivision."),
    }

    # ── Edge valence: open boundary (1) and non-manifold (3+) edges ──
    edge_counts: dict[tuple[int, int], int] = {}
    for prim in prims:
        try:
            verts = prim.vertices()
            n = len(verts)
            if n < 2:
                continue
            for i in range(n):
                a = verts[i].point().number()
                b = verts[(i + 1) % n].point().number()
                if a == b:
                    continue
                key = _edge_key(a, b)
                edge_counts[key] = edge_counts.get(key, 0) + 1
        except Exception:
            continue
    open_boundary = [list(k) for k, c in edge_counts.items() if c == 1]
    nonmanifold = [list(k) for k, c in edge_counts.items() if c >= 3]
    open_boundary_edges = {
        "count": len(open_boundary),
        "sample": open_boundary[:max_coincident_report],
        "passed": len(open_boundary) == 0,
        "note": ("An open boundary edge belongs to exactly one polygon. This "
                 "is EXPECTED for open surfaces (terrain, cloth, a single "
                 "panel) but flags holes in what should be a closed solid."),
        "fix": ("If the asset should be closed: cap holes with a PolyFill or "
                "Cap SOP. If it's intentionally open, ignore."),
    }
    nonmanifold_edges = {
        "count": len(nonmanifold),
        "sample": nonmanifold[:max_coincident_report],
        "passed": len(nonmanifold) == 0,
        "fix": ("Non-manifold edges (shared by 3+ polygons) are always bad. "
                "Find and remove the extra polygons; a Clean SOP helps. These "
                "break Boolean operations and simulations."),
    }

    # ── Coincident points (O(n^2) — skip for very large point counts) ──
    coincident_pairs: list[list[int]] = []
    if n_points <= 4000:
        positions = [(p.number(), p.position()) for p in points]
        eps2 = coincident_eps * coincident_eps
        for i in range(len(positions)):
            na, pa = positions[i]
            for j in range(i + 1, len(positions)):
                nb, pb = positions[j]
                dx = pa[0] - pb[0]; dy = pa[1] - pb[1]; dz = pa[2] - pb[2]
                if dx * dx + dy * dy + dz * dz < eps2:
                    coincident_pairs.append([na, nb])
                    if len(coincident_pairs) >= max_coincident_report:
                        break
            if len(coincident_pairs) >= max_coincident_report:
                break
    coincident = {
        "count": len(coincident_pairs),
        "sample": coincident_pairs[:max_coincident_report],
        "skipped_large_pointcount": n_points > 4000,
        "passed": len(coincident_pairs) == 0,
        "fix": ("Run a Fuse SOP (Consolidate Points) to merge coincident "
                "points. Unmerged duplicates break Copy-to-Points, shading, "
                "and attribute interpolation."),
    }

    checks = {
        "orphan_points": orphan_points,
        "open_curves": open_curves,
        "degenerate_prims": degenerate,
        "nonmanifold_edges": nonmanifold_edges,
        "open_boundary_edges": open_boundary_edges,
        "coincident_points": coincident,
    }

    # Two-tier severity: BLOCKING checks gate commit; ADVISORY checks are
    # reported but never flip overall_ok. Rationale (from production runs):
    # non-manifold edges and coincident points are routinely tolerated, and
    # open_boundary_edges are EXPECTED on open surfaces (terrain, a single
    # panel, an intentional gateway opening). Treating them as blocking made
    # overall_ok report false on geometry that was already clean, which drove
    # agents into rebuild loops over non-defects. Only orphan points and stray
    # open curves are unambiguous defects that always warrant a fix.
    for cname in _HEALTH_BLOCKING_CHECKS:
        if cname in checks:
            checks[cname]["severity"] = "blocking"
    for cname in _HEALTH_ADVISORY_CHECKS:
        if cname in checks:
            checks[cname]["severity"] = "advisory"

    overall_ok = all(
        checks[c]["passed"] for c in _HEALTH_BLOCKING_CHECKS if c in checks
    )

    return {
        "success": True,
        "node_path": node_path,
        "point_count": n_points,
        "prim_count": n_prims,
        "overall_ok": overall_ok,
        "blocking_checks": [c for c in _HEALTH_BLOCKING_CHECKS if c in checks],
        "advisory_checks": [c for c in _HEALTH_ADVISORY_CHECKS if c in checks],
        "summary": {
            name: c["count"] for name, c in checks.items()
        },
        "checks": checks,
    }
