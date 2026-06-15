"""Houdini node operation utilities.

Pure houp wrappers. No UI dependencies. All functions return
JSON-serializable dicts with {"success": bool, ...} shape.
"""
from __future__ import annotations

import os
import traceback

import hou
from typing import Any


# ---------------------------------------------------------------------------
# Scene / Node Operations
# ---------------------------------------------------------------------------

def get_scene_info() -> dict[str, Any]:
    """Get an overview of the current Houdini scene."""
    try:
        root = hou.node("/")
        return {
            "success": True,
            "hip_file": hou.hipFile.name() or "(unsaved)",
            "root_children": [n.name() for n in root.children()],
            "total_nodes": len(root.allSubChildren()),
            "current_path": hou.pwd().path() if hou.pwd() else "/",
            "obj_nodes": [n.name() for n in hou.node("/obj").children()] if hou.node("/obj") else [],
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def create_node(
    node_type: str,
    name: str | None = None,
    parent_path: str = "/obj",
) -> dict[str, Any]:
    """Create a new node in the scene.

    Automatically resolves the preferred namespace (e.g. 'copytopoints'
    → 'copytopoints::2.0') to match Tab-menu creation behavior.
    """
    try:
        parent = hou.node(parent_path)
        if parent is None:
            return {"success": False, "error": f"Parent path not found: {parent_path}"}

        node = _create_with_namespace_fallback(parent, node_type, name)
        return {
            "success": True,
            "path": node.path(),
            "name": node.name(),
            "type": node.type().name(),
        }
    except hou.OperationFailed as e:
        return {"success": False, "error": f"Failed to create node '{node_type}': {e}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _create_with_namespace_fallback(parent, node_type: str, name: str | None):
    """Try creating a node with bare type name, falling back to namespace resolution.

    After creation, applies any Tab-menu tool presets by finding matching
    shelf tools and executing their post-creation parameter modifications.
    """
    # Attempt 1: bare name
    node = None
    try:
        node = parent.createNode(node_type, node_name=name if name else None)
    except hou.OperationFailed:
        pass

    # Attempt 2: resolve via namespaceOrder across all categories
    if node is None:
        for cat in [
            hou.sopNodeTypeCategory(),
            hou.objNodeTypeCategory(),
            hou.dopNodeTypeCategory(),
            hou.vopNodeTypeCategory(),
            hou.shopNodeTypeCategory(),
            hou.ropNodeTypeCategory(),
        ]:
            nt = hou.nodeType(cat, node_type)
            if nt is not None:
                namespaces = nt.namespaceOrder()
                for ns in namespaces:
                    try:
                        node = parent.createNode(ns, node_name=name if name else None)
                        break
                    except hou.OperationFailed:
                        continue
            if node is not None:
                break

    # All attempts failed — let original exception propagate
    if node is None:
        return parent.createNode(node_type, node_name=name if name else None)

    # Apply Tab-menu presets from matching shelf tool
    _apply_tool_presets(node)
    return node


def _apply_tool_presets(node) -> None:
    """Apply post-creation parameter presets from shelf tools matching this node type.

    The Tab menu runs shelf tools that often call pressButton() or parm().set()
    after creating the node (e.g. 'resettargetattribs' for copytopoints).
    This function finds matching tools and applies those post-creation actions.
    """
    import re

    try:
        node_type_name = node.type().name()  # e.g. 'copytopoints::2.0'
    except Exception:
        return

    # Build candidate tool name patterns
    # e.g. for 'copytopoints::2.0': 'sop_copytopoints::2.0', 'sop_copytopoints'
    # for 'copytopoints': 'sop_copytopoints'
    base = node_type_name.split('::')[0]
    candidates = []
    for suffix in ['::2.0', '::1.0', '::3.0', '']:
        candidates.append(f'sop_{base}{suffix}')
        candidates.append(f'obj_{base}{suffix}')
        candidates.append(f'dop_{base}{suffix}')

    # Also try the exact node type name
    candidates.insert(0, f'sop_{node_type_name}')

    for tool_name in candidates:
        tool = hou.shelves.tool(tool_name)
        if tool is None:
            continue
        script = tool.script()
        if not script:
            continue

        # Extract post-creation actions: pressButton() and parm().set() calls
        # that appear after node creation (genericTool / createNode)
        lines = script.split('\n')
        in_post_creation = False
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                continue

            # Detect the creation line
            if 'genericTool' in stripped or 'createNode' in stripped:
                in_post_creation = True
                continue

            if not in_post_creation:
                continue

            # pressButton('xxx') or .pressButton()
            pm = re.search(r"\.parm\(['\"]([^'\"]+)['\"]\)\.pressButton\(\)", stripped)
            if pm:
                parm_name = pm.group(1)
                try:
                    p = node.parm(parm_name)
                    if p is not None:
                        p.pressButton()
                except Exception:
                    pass
                continue

            # parm('xxx').set(value)
            sm = re.search(
                r"\.parm\(['\"]([^'\"]+)['\"]\)\.set\((.+?)\)",
                stripped
            )
            if sm:
                parm_name = sm.group(1)
                value_expr = sm.group(2).strip()
                # Try to eval simple literals
                try:
                    import ast
                    value = ast.literal_eval(value_expr)
                except (ValueError, SyntaxError):
                    continue
                try:
                    p = node.parm(parm_name)
                    if p is not None:
                        p.set(value)
                except Exception:
                    pass

        break  # Found and processed first matching tool


def delete_node(node_path: str) -> dict[str, Any]:
    """Delete a node by its full path."""
    try:
        node = hou.node(node_path)
        if node is None:
            return {"success": False, "error": f"Node not found: {node_path}"}
        node.destroy()
        return {"success": True, "path": node_path}
    except Exception as e:
        return {"success": False, "error": str(e)}


def connect_nodes(
    from_path: str,
    to_path: str,
    input_index: int = 0,
) -> dict[str, Any]:
    """Connect the output of one node to the input of another."""
    try:
        from_node = hou.node(from_path)
        to_node = hou.node(to_path)
        if from_node is None:
            return {"success": False, "error": f"Source node not found: {from_path}"}
        if to_node is None:
            return {"success": False, "error": f"Destination node not found: {to_path}"}

        to_node.setInput(input_index, from_node)
        return {
            "success": True,
            "from": from_path,
            "to": to_path,
            "input_index": input_index,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def set_param(node_path: str, param_name: str, value: Any) -> dict[str, Any]:
    """Set a parameter value on a node."""
    try:
        node = hou.node(node_path)
        if node is None:
            return {"success": False, "error": f"Node not found: {node_path}"}

        parm = node.parm(param_name)
        if parm is None:
            return {"success": False, "error": f"Parameter '{param_name}' not found on {node_path}"}

        parm.set(value)
        return {"success": True, "path": node_path, "param": param_name, "value": value}
    except Exception as e:
        return {"success": False, "error": str(e)}


def set_params_batch(node_path: str, params: dict[str, Any]) -> dict[str, Any]:
    """Set multiple parameters on a node in a single call."""
    try:
        node = hou.node(node_path)
        if node is None:
            return {"success": False, "error": f"Node not found: {node_path}"}

        failed: list[str] = []
        for name, value in params.items():
            parm = node.parm(name)
            if parm is None:
                failed.append(name)
                continue
            try:
                parm.set(value)
            except Exception as e:
                failed.append(f"{name}: {e}")

        if failed:
            return {
                "success": True,
                "partial": True,
                "set_count": len(params) - len(failed),
                "total_count": len(params),
                "failed_params": failed,
                "warning": f"{len(failed)} parameter(s) could not be set",
            }
        return {
            "success": True,
            "set_count": len(params),
            "total_count": len(params),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_param(node_path: str, param_name: str) -> dict[str, Any]:
    """Read a parameter value from a node."""
    try:
        node = hou.node(node_path)
        if node is None:
            return {"success": False, "error": f"Node not found: {node_path}"}

        parm = node.parm(param_name)
        if parm is None:
            return {"success": False, "error": f"Parameter '{param_name}' not found on {node_path}"}

        return {"success": True, "path": node_path, "param": param_name, "value": parm.eval()}
    except Exception as e:
        return {"success": False, "error": str(e)}


def list_nodes(parent_path: str = "/", type_filter: str | None = None) -> dict[str, Any]:
    """List nodes under a parent path, optionally filtered by type."""
    try:
        parent = hou.node(parent_path)
        if parent is None:
            return {"success": False, "error": f"Path not found: {parent_path}"}

        nodes = []
        for child in parent.children():
            if type_filter and child.type().name() != type_filter:
                continue
            nodes.append({
                "name": child.name(),
                "path": child.path(),
                "type": child.type().name(),
                "input_count": len(child.inputs()),
                "output_count": len(child.outputs()),
            })

        return {"success": True, "parent": parent_path, "node_count": len(nodes), "nodes": nodes}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_node_info(node_path: str) -> dict[str, Any]:
    """Get detailed info about a specific node."""
    try:
        node = hou.node(node_path)
        if node is None:
            return {"success": False, "error": f"Node not found: {node_path}"}

        parms = []
        for p in node.parms():
            parms.append({"name": p.name(), "label": p.description(), "value": p.eval()})

        return {
            "success": True,
            "name": node.name(),
            "path": node.path(),
            "type": node.type().name(),
            "type_description": node.type().description(),
            "inputs": [inp.path() if inp else None for inp in node.inputs()],
            "outputs": [out.path() for out in node.outputs()],
            "parameters": parms,
            "is_time_dependent": node.isTimeDependent(),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def layout_nodes(parent_path: str = "/obj") -> dict[str, Any]:
    """Auto-layout nodes in a network."""
    try:
        parent = hou.node(parent_path)
        if parent is None:
            return {"success": False, "error": f"Path not found: {parent_path}"}
        parent.layoutChildren()
        return {"success": True, "parent": parent_path}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Query / Search Operations
# ---------------------------------------------------------------------------

def search_nodes(keyword: str) -> dict[str, Any]:
    """Search for available node types by keyword across all categories."""
    try:
        results = []
        keyword_lower = keyword.lower()

        for category_name in hou.nodeTypeCategories().keys():
            category = hou.nodeTypeCategories()[category_name]
            for node_type in category.nodeTypes().values():
                name = node_type.name()
                desc = node_type.description()
                if keyword_lower in name.lower() or keyword_lower in desc.lower():
                    results.append({"name": name, "category": category_name, "description": desc})

        results = results[:20]
        return {"success": True, "keyword": keyword, "match_count": len(results), "results": results}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_help(node_type_name: str) -> dict[str, Any]:
    """Get help documentation for a node type."""
    try:
        found = None
        for category in hou.nodeTypeCategories().values():
            nt = category.nodeType(node_type_name)
            if nt is not None:
                found = nt
                break

        if found is None:
            return {"success": False, "error": f"Node type '{node_type_name}' not found"}

        return {
            "success": True,
            "name": found.name(),
            "category": found.category().name(),
            "description": found.description(),
            "max_inputs": found.maxNumInputs(),
            "min_inputs": found.minNumInputs(),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


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

    Returns {success, node_path, summary, checks: {...}, overall_ok}.
    `overall_ok` is True only if every check passes.
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
    degenerate_prims: list[int] = []
    for prim in prims:
        try:
            type_name = prim.type().name().lower()
            if "poly" not in type_name:
                continue  # only polygonal area is meaningful here
            verts = prim.vertices()
            if len(verts) < 3:
                degenerate_prims.append(prim.number())
                continue
            # Shoelace via the first three vertices' positions in world space —
            # a triangle area proxy. For >3 verts this still flags colinear/
            # zero-area faces reliably.
            p0 = verts[0].point().position()
            p1 = verts[1].point().position()
            p2 = verts[2].point().position()
            e01 = (p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2])
            e02 = (p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2])
            cross = (
                e01[1] * e02[2] - e01[2] * e02[1],
                e01[2] * e02[0] - e01[0] * e02[2],
                e01[0] * e02[1] - e01[1] * e02[0],
            )
            tri_area2 = 0.5 * (
                cross[0] * cross[0] + cross[1] * cross[1] + cross[2] * cross[2]
            )
            if tri_area2 < degenerate_area_eps:
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
    overall_ok = all(c["passed"] for c in checks.values())

    return {
        "success": True,
        "node_path": node_path,
        "point_count": n_points,
        "prim_count": n_prims,
        "overall_ok": overall_ok,
        "summary": {
            name: c["count"] for name, c in checks.items()
        },
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# Script / HDA Operations
# ---------------------------------------------------------------------------

def _safe_getvalue(stream) -> tuple[str, str | None]:
    try:
        return stream.getvalue(), None
    except Exception as e:
        return "", str(e)


def run_python(code: str) -> dict[str, Any]:
    """Execute arbitrary Python code in Houdini context.

    This is intentionally raw execution. Procedural asset generation should
    prefer harness sandbox tools so failed cooks preserve diagnostics.
    """
    import io
    import sys
    import traceback

    namespace = {"hou": hou, "__builtins__": __builtins__}
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    sys.stdout = stdout_capture
    sys.stderr = stderr_capture

    try:
        exec(code, namespace)
        output, output_error = _safe_getvalue(stdout_capture)
        stderr, stderr_error = _safe_getvalue(stderr_capture)
        capture_errors = [err for err in (output_error, stderr_error) if err]
        if capture_errors:
            return {
                "success": False,
                "error": "; ".join(capture_errors),
                "output": output,
                "stderr": stderr,
                "warning": "Raw houdini_run_python is not sandboxed; failed code may have changed the live scene.",
            }
        return {
            "success": True,
            "output": output or "(no output)",
            "stderr": stderr,
            "warning": "Raw houdini_run_python is not sandboxed; use harness tools for procedural assets.",
        }
    except Exception as e:
        output, _ = _safe_getvalue(stdout_capture)
        stderr, _ = _safe_getvalue(stderr_capture)
        return {
            "success": False,
            "error": str(e),
            "output": output,
            "stderr": stderr,
            "traceback": traceback.format_exc(),
            "warning": "Raw houdini_run_python is not sandboxed; failed code may have changed the live scene.",
        }
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr


def run_vex(
    code: str,
    node_path: str | None = None,
    attrib_name: str = "result",
) -> dict[str, Any]:
    """Execute VEX code by creating a temporary Attribute Wrangle node."""
    try:
        parent = hou.node("/obj")
        if parent is None:
            return {"success": False, "error": "No /obj context"}

        if node_path:
            input_node = hou.node(node_path)
            if input_node is None:
                return {"success": False, "error": f"Input node not found: {node_path}"}
        else:
            input_node = None

        wrangle = parent.createNode("attribwrangle", node_name="edini_temp_wrangle")
        if input_node:
            wrangle.setInput(0, input_node)

        wrangle.parm("snippet").set(code)
        if wrangle.parm("snippet_attribname") is not None:
            wrangle.parm("snippet_attribname").set(attrib_name)

        wrangle.cook(force=True)
        return {
            "success": True,
            "wrangle_path": wrangle.path(),
            "note": "Temporary wrangle created. Remove when done or rename to keep.",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def create_hda(node_path: str, hda_name: str, hda_label: str = "") -> dict[str, Any]:
    """Create an HDA (digital asset) from a node."""
    try:
        node = hou.node(node_path)
        if node is None:
            return {"success": False, "error": f"Node not found: {node_path}"}

        hip_dir = hou.hipFile.dirName()
        if not hip_dir:
            hip_dir = hou.homeHoudiniDirectory()
        save_path = f"{hip_dir}/{hda_name}.hda"

        definition = node.type().definition()
        if definition is None:
            node.createDigitalAsset(name=hda_name, hda_file_name=save_path, description=hda_label)
        else:
            return {"success": False, "error": f"Node is already an HDA: {node_path}"}

        return {
            "success": True,
            "name": hda_name,
            "label": hda_label or hda_name,
            "path": save_path,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Capture Operations
#
# Use capture_review() and capture_network() below.
# capture_viewport() and capture_viewport_safe() have been removed;
# single-frame captures are handled by capture_review(views=["perspective"]).
# ---------------------------------------------------------------------------


def capture_network(
    filepath: str,
    parent_path: str = "/obj",
) -> dict[str, Any]:
    """Capture the node network editor as an image.

    Navigates to the requested parent path, then grabs the Network Editor
    pane tab widget. Returns the image dimensions and filesize.
    """
    try:
        from PySide6.QtWidgets import QApplication
        import os

        desktop = hou.ui.curDesktop()
        editor = desktop.paneTabOfType(hou.paneTabType.NetworkEditor)
        if editor is None:
            return {"success": False, "error": "No Network Editor pane found"}

        # Navigate to the requested parent path
        target = hou.node(parent_path)
        if target is not None:
            editor.setPwd(target)

        QApplication.processEvents()

        # Ensure output directory exists
        os.makedirs(os.path.dirname(os.path.abspath(filepath)) or ".", exist_ok=True)

        # Grab the network editor widget. Houdini 21 removed the
        # NetworkEditor.grab() convenience; the underlying Qt widget must
        # be reached via qtWindow()/qtWidget() (hou.qt). Try several paths
        # in order so this works across H19/H20/H21.
        pixmap = None
        tried: list[str] = []
        grab_candidates = []
        # 1. direct editor.grab() (H19/H20)
        if hasattr(editor, "grab"):
            grab_candidates.append(lambda: editor.grab())
            tried.append("editor.grab")
        # 2. Qt widget via hou.qt (H21 path)
        try:
            from hou import qt as _houqt  # type: ignore
            if hasattr(_houqt, "qtWindow"):
                grab_candidates.append(lambda: _houqt.qtWindow(editor).grab())
                tried.append("hou.qt.qtWindow(editor).grab")
            if hasattr(_houqt, "qtWidget"):
                grab_candidates.append(lambda: _houqt.qtWidget(editor).grab())
                tried.append("hou.qt.qtWidget(editor).grab")
        except Exception:
            pass
        last_err = None
        for grab_fn in grab_candidates:
            try:
                pixmap = grab_fn()
                if pixmap is not None:
                    break
            except Exception as ge:
                last_err = ge
                continue
        if pixmap is None:
            return {
                "success": False,
                "error": (f"Network grab failed: no usable Qt grab API. "
                          f"Tried: {tried}. Last error: {last_err}"),
                "guidance": ("NetworkEditor screenshot is unavailable in this "
                             "Houdini build. Use houdini_capture_review for "
                             "viewport screenshots instead. To verify node "
                             "network structure, use houdini_layout_nodes or "
                             "houdini_list_nodes."),
            }
        pixmap.save(filepath, "PNG")

        if os.path.exists(filepath):
            size_kb = round(os.path.getsize(filepath) / 1024, 1)
            return {
                "success": True,
                "path": filepath,
                "size_kb": size_kb,
                "width": pixmap.width(),
                "height": pixmap.height(),
                "parent_path": parent_path,
            }
        return {"success": False, "error": f"File not created: {filepath}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Review Capture — multi-view + frame-range contact sheets
# ---------------------------------------------------------------------------

_VIEW_TYPE_MAP: dict[str, Any] = {}  # populated lazily in Houdini


def _get_view_type(view_name: str) -> Any:
    """Map a view name string to hou.geometryViewportType enum."""
    if not _VIEW_TYPE_MAP:
        try:
            _VIEW_TYPE_MAP.update({
                "perspective": hou.geometryViewportType.Perspective,
                "top": hou.geometryViewportType.Top,
                "bottom": hou.geometryViewportType.Bottom,
                "front": hou.geometryViewportType.Front,
                "back": hou.geometryViewportType.Back,
                "right": hou.geometryViewportType.Right,
                "left": hou.geometryViewportType.Left,
            })
        except Exception:
            pass
    return _VIEW_TYPE_MAP.get(view_name.lower())


def _trim_white_border(img: Any, threshold: int = 240) -> Any:
    """Auto-crop white/light borders from a PIL image."""
    import numpy as np
    try:
        arr = np.array(img.convert("RGB"))
        # Mask: pixels where all channels are below threshold (not white)
        mask = np.any(arr < threshold, axis=2)
        rows = np.any(mask, axis=1)
        cols = np.any(mask, axis=0)
        if not rows.any() or not cols.any():
            return img  # entirely white — skip
        rmin, rmax = np.where(rows)[0][[0, -1]]
        cmin, cmax = np.where(cols)[0][[0, -1]]
        cropped = img.crop((cmin, rmin, cmax + 1, rmax + 1))
        if cropped.width > 0 and cropped.height > 0:
            return cropped
    except ImportError:
        pass
    except Exception:
        pass
    return img


def _concat_images_grid(
    image_paths: list[str],
    output_path: str,
    columns: int,
    cell_size: tuple[int, int] | None = None,
) -> bool:
    """Concatenate multiple images into a grid using Pillow.

    If cell_size is provided, all images are resized to that exact
    size before pasting — prevents cropping and ensures uniform cells.
    Otherwise uses the largest image dimensions as cell size (legacy).

    Returns True on success, False if Pillow not available or any error.
    """
    try:
        from PIL import Image
    except ImportError:
        return False

    try:
        imgs: list[Image.Image] = []
        for p in image_paths:
            if os.path.exists(p):
                raw = Image.open(p)
                imgs.append(_trim_white_border(raw))
        if not imgs:
            return False

        cols = max(1, min(columns, len(imgs)))
        rows = (len(imgs) + cols - 1) // cols

        # Determine cell dimensions
        if cell_size is not None:
            cell_w, cell_h = cell_size
            # Resize all images to cell size
            resized: list[Image.Image] = []
            for img in imgs:
                if img.width != cell_w or img.height != cell_h:
                    resized.append(img.resize((cell_w, cell_h), Image.LANCZOS))
                    img.close()
                else:
                    resized.append(img)
            imgs = resized
        else:
            cell_w = max(img.width for img in imgs)
            cell_h = max(img.height for img in imgs)

        canvas = Image.new("RGB", (cell_w * cols, cell_h * rows), (30, 30, 30))
        for i, img in enumerate(imgs):
            r, c = i // cols, i % cols
            x, y = c * cell_w, r * cell_h
            # Center in cell (no-op if already resized to cell_w × cell_h)
            ox = (cell_w - img.width) // 2
            oy = (cell_h - img.height) // 2
            canvas.paste(img, (x + ox, y + oy))
            img.close()

        canvas.save(output_path, "PNG")
        canvas.close()
        return True
    except Exception:
        return False


def _target_bounds(target_node: Any) -> Any:
    """Compute a hou.BoundingBox around the target node's cooked geometry.

    Returns None if the bounds cannot be determined. The bounds come from the
    node's own cooked geometry (not the whole viewport), which is what we want
    for tight per-asset framing.
    """
    try:
        geo = target_node.geometry()
        if geo is None:
            return None
    except Exception:
        return None
    # Prefer the geometry's bounding box (a hou.BoundingBox object) so we can
    # hand it to viewport.setViewToBoundingBox directly.
    try:
        bbox = geo.boundingBox()
        # A degenerate/empty bbox (min > max) means no real geometry
        if bbox is not None:
            mn = bbox.minvec()
            mx = bbox.maxvec()
            try:
                if (float(mx[0]) < float(mn[0])
                        or float(mx[1]) < float(mn[1])
                        or float(mx[2]) < float(mn[2])):
                    return None
            except Exception:
                return None
            # Expand by a small epsilon so zero-thickness planes still frame
            for axis in range(3):
                if float(mx[axis]) - float(mn[axis]) < 1e-6:
                    mn_list = list(mn)
                    mx_list = list(mx)
                    mn_list[axis] -= 0.05
                    mx_list[axis] += 0.05
                    # hou.Vector3 is read-only; rebuild via hou.BoundingBox
                    try:
                        import hou as _hou
                        return _hou.BoundingBox(
                            tuple(mn_list), tuple(mx_list))
                    except Exception:
                        return bbox
        return bbox
    except Exception:
        return None


def _frame_to_bounds(
    viewport: Any,
    target_node: Any,
    padding: float = 1.15,
) -> bool:
    """Frame the viewport tightly around the target node's geometry.

    This is the correct way to ensure orthographic (top/front/right) views
    show the COMPLETE model. The old code called `viewport.homeAll()`, which
    frames the entire viewport contents and is affected by the persistent
    pan/zoom state of orthographic cameras — so switching to a Top view after
    a zoomed-in Perspective session would often cut off the model.

    `viewport.setViewToBoundingBox(bbox)` resets the view to fit a specific
    bounding box, which is exactly what we need. We expand the box by
    `padding` (default 1.15× — a little breathing room) so edges aren't
    clipped against the frame.

    Returns True if bounding-box framing succeeded, False if it fell back to
    homeAll() (or that also failed).
    """
    bbox = _target_bounds(target_node)
    if bbox is not None:
        try:
            viewport.setViewToBoundingBox(bbox, 0.0, padding)
            viewport.draw(True, True)
            return True
        except Exception:
            pass
    # Fallback: home everything (less precise but always available)
    try:
        viewport.homeAll()
        viewport.draw(True, True)
        return True
    except Exception:
        return False


def _capture_single_view(
    viewer: Any,
    viewport: Any,
    filepath: str,
    frame: int,
    resolution: tuple[int, int] | None = None,
) -> tuple[bool, str]:
    """Capture a single viewport frame via flipbook. Returns (success, error_detail)."""
    try:
        base_settings = viewer.flipbookSettings()
        settings = base_settings.stash() if hasattr(base_settings, "stash") else base_settings
        settings.output(filepath)
        settings.outputToMPlay(False)
        settings.frameRange((frame, frame))
        if resolution is not None:
            try:
                settings.resolution(resolution)
            except Exception:
                pass
        viewer.flipbook(viewport, settings)
        if os.path.exists(filepath):
            return True, ""
        return False, f"flipbook ran but no file at {filepath}"
    except Exception as e:
        import traceback as _tb
        return False, f"{e}\n{_tb.format_exc()}"


def capture_review(
    filepath: str,
    target_path: str | None = None,
    views: list[str] | None = None,
    frames: list[int] | None = None,
    columns: int = 0,
    shading_mode: str = "smooth",
    home_target: bool = True,
    resolution: tuple[int, int] | None = None,
) -> dict[str, Any]:
    """Capture a review contact sheet — multi-view, multi-frame snapshots.

    Captures each (view × frame) combination as a separate flipbook pass,
    then concatenates all captures into a single grid image using Pillow.

    Args:
        filepath: Output image path (PNG).
        target_path: Node to frame and isolate. Required for predictable results.
        views: View types to capture. Default: ["perspective"].
               Supported: "perspective", "top", "front", "right",
               "bottom", "back", "left".
        frames: Frame numbers to capture. Default: [1].
                Use [1, 10, 20, 30] for a 4-frame time contact sheet.
        columns: Grid columns. 0 = auto (√n rounded up). Default: 0.
        shading_mode: "smooth", "wire", "flat", etc. Default: "smooth".
        home_target: Frame the target before each view capture. Default: True.
        resolution: (width, height) for each cell. None = viewport native.
                    Set to e.g. (960, 540) for consistent quad-view cells.

    Returns:
        {success, path, size_kb, grid: {rows, cols, cells},
         captured: [list of individual file paths]}
    """
    import os
    import uuid
    import tempfile

    filepath = os.path.abspath(filepath)  # resolve relative to Houdini process cwd

    method = "review_capture"
    stage = "initialize"

    if views is None:
        views = ["perspective"]
    if frames is None:
        frames = [1]

    # Validate inputs
    valid_views = {"perspective", "top", "front", "right", "bottom", "back", "left"}
    views = [v.lower() for v in views if v.lower() in valid_views]
    if not views:
        views = ["perspective"]
    frames = sorted(set(frames))
    if not frames:
        frames = [1]

    total_cells = len(views) * len(frames)
    if columns <= 0:
        columns = max(1, int(total_cells ** 0.5 + 0.5)) if total_cells > 1 else 1

    # ── State to restore ──
    _restore_hidden: list[str] = []
    _restore_shading: Any = None
    _restore_view_type: Any = None
    _restore_guides: dict[Any, bool] = {}
    _restore_reference_plane: bool | None = None
    _restore_color_scheme: Any = None

    try:
        stage = "get_viewer"
        desktop = hou.ui.curDesktop()
        viewer = desktop.paneTabOfType(hou.paneTabType.SceneViewer)
        if viewer is None:
            return {"success": False, "error": "No Scene Viewer pane found", "method": method}

        viewport = viewer.curViewport()
        _restore_view_type = viewport.type() if hasattr(viewport, "type") else None

        # ── Shading ──
        try:
            shading_map = {
                "smooth": hou.glShadingType.Smooth,
                "smooth_wire": hou.glShadingType.SmoothWire,
                "flat": hou.glShadingType.Flat,
                "wire": hou.glShadingType.Wire,
            }
            if shading_mode in shading_map:
                vp_settings = viewport.settings()
                display_set = vp_settings.displaySet(hou.displaySetType.DisplayModel)
                _restore_shading = display_set.shadedMode()
                display_set.setShadedMode(shading_map[shading_mode])
        except Exception:
            pass

        # ── Color scheme: switch to Dark (black bg) to prevent white alpha fringing ──
        try:
            _restore_color_scheme = vp_settings.colorScheme()
            vp_settings.setColorScheme(hou.viewportColorScheme.Dark)
        except Exception:
            pass

        # ── Guides: hide grid planes, rulers, gnomon for clean capture ──
        VIEWPORT_GUIDES_TO_HIDE = [
            hou.viewportGuide.XYPlane,
            hou.viewportGuide.XZPlane,
            hou.viewportGuide.YZPlane,
            hou.viewportGuide.OriginGnomon,
            hou.viewportGuide.FloatingGnomon,
            hou.viewportGuide.NodeHandles,
            hou.viewportGuide.ObjectNames,
            hou.viewportGuide.ObjectPaths,
            hou.viewportGuide.SafeArea,
            hou.viewportGuide.CameraMask,
        ]
        for guide in VIEWPORT_GUIDES_TO_HIDE:
            try:
                was_enabled = vp_settings.guideEnabled(guide)
                _restore_guides[guide] = was_enabled
                vp_settings.enableGuide(guide, False)
            except Exception:
                pass
        # Hide grid ruler numbers (distance labels along grid axis)
        try:
            _restore_guides["_ortho_ruler"] = vp_settings.orthoRuler()
            vp_settings.setOrthoRuler(hou.viewportGridRuler.Hide)
        except Exception:
            pass

        # ── Reference Plane: hide (keep ConstructionPlane for visual reference) ──
        try:
            rplane = viewer.referencePlane()
            _restore_reference_plane = rplane.isVisible()
            rplane.setIsVisible(False)
        except Exception:
            pass

        # ── Target ──
        target_node = None
        if target_path:
            target_node = hou.node(target_path)
            if target_node is not None:
                try:
                    target_node.setDisplayFlag(True)
                    target_node.setCurrent(True, clear_all_selected=True)
                except Exception:
                    pass
                try:
                    if hasattr(hou, "setFrame"):
                        hou.setFrame(frames[0])
                except Exception:
                    pass

        # ── Isolate ──
        try:
            if target_node is not None:
                obj = hou.node("/obj")
                if obj is not None:
                    target_path_val = target_node.path()
                    for child in obj.children():
                        child_path = child.path()
                        # Skip: exact match, or ancestor of target (e.g. /obj/bicycle
                        # is ancestor of /obj/bicycle/OUT — hiding it would hide the target)
                        if child_path == target_path_val:
                            continue
                        if target_path_val.startswith(child_path + "/"):
                            continue
                        try:
                            if child.isDisplayFlagSet():
                                child.setDisplayFlag(False)
                                _restore_hidden.append(child_path)
                        except Exception:
                            pass
        except Exception:
            pass

        # ── Prepare output ──
        stage = "prepare_output"
        os.makedirs(os.path.dirname(os.path.abspath(filepath)) or ".", exist_ok=True)

        # ── Capture each cell ──
        stage = "capture_cells"
        tmp_dir = os.path.dirname(os.path.abspath(filepath))
        captured: list[str] = []
        cell_errors: list[str] = []

        for fi, frame in enumerate(frames):
            # Set frame
            try:
                if hasattr(hou, "setFrame"):
                    hou.setFrame(frame)
            except Exception:
                pass

            for vi, view_name in enumerate(views):
                cell_index = fi * len(views) + vi
                tmp_path = os.path.join(tmp_dir, f"_edini_review_{uuid.uuid4().hex[:8]}.png")

                # Change view type
                view_type = _get_view_type(view_name)
                if view_type is not None:
                    try:
                        viewport.changeType(view_type)
                        viewport.draw(True, True)
                    except Exception:
                        pass

                # Frame target: use bounding-box framing so each view (esp.
                # orthographic top/front/right) shows the COMPLETE model.
                # homeAll() alone is unreliable for ortho views — it inherits
                # the previous pan/zoom state and frequently clips the model.
                if home_target and target_node is not None:
                    # Orthographic views benefit from slightly more padding so
                    # thin extents (e.g. a bike's X-width) aren't edge-clipped.
                    ortho_padding = 1.3 if view_name != "perspective" else 1.15
                    _frame_to_bounds(viewport, target_node, padding=ortho_padding)

                # Capture
                ok, err_detail = _capture_single_view(viewer, viewport, tmp_path, frame, resolution)
                if ok:
                    captured.append(tmp_path)
                else:
                    cell_errors.append(f"{view_name}@f{frame}: {err_detail[:120]}")

        # ── Concatenate ──
        stage = "concat"
        if not captured:
            return {
                "success": False,
                "error": f"All {total_cells} captures failed: {', '.join(cell_errors)}" if cell_errors else "No captures succeeded",
                "method": method,
                "stage": stage,
            }

        concat_ok = _concat_images_grid(captured, filepath, columns, resolution)

        # Clean up temp files
        for tmp_path in captured:
            try:
                if os.path.exists(tmp_path) and tmp_path != filepath:
                    os.remove(tmp_path)
            except Exception:
                pass

        if not concat_ok:
            # If concatenation failed, keep the first capture as fallback
            if captured and os.path.exists(captured[0]):
                import shutil
                shutil.copy(captured[0], filepath)

        if os.path.exists(filepath):
            size_kb = round(os.path.getsize(filepath) / 1024, 1)
            actual_cols = min(columns, len(captured))
            actual_rows = (len(captured) + actual_cols - 1) // actual_cols
            result = {
                "success": True,
                "path": filepath,
                "size_kb": size_kb,
                "method": method,
                "grid": {"rows": actual_rows, "cols": actual_cols, "cells": len(captured)},
                "captured": captured[:10],  # truncate for tool result size
                "errors": cell_errors[:10] if cell_errors else [],
                "views": views,
                "frames": frames,
            }
            # Attach a per-component geometry inventory so the agent (and the
            # vision model) can cross-check "is this component present but
            # small?" against hard geometry data rather than relying on the
            # screenshot alone. This defeats the recurring failure where vision
            # reports small components (chains, pedals, bolts) as "missing".
            if target_node is not None:
                try:
                    inv = geometry_inventory(target_node.path())
                    if inv.get("success"):
                        result["geometry_inventory"] = inv.get("inventory_text")
                        result["inventory_components"] = inv.get("total_components")
                except Exception:
                    pass
            return result
        return {
            "success": False,
            "error": f"Output file not created: {filepath}",
            "method": method,
            "stage": stage,
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "method": method,
            "stage": stage,
            "traceback": traceback.format_exc(),
        }
    finally:
        # ── Restore state ──
        try:
            if _restore_color_scheme is not None:
                vp_settings.setColorScheme(_restore_color_scheme)
        except Exception:
            pass
        try:
            for guide, was_enabled in _restore_guides.items():
                if isinstance(guide, str):  # _ortho_ruler marker
                    continue
                vp_settings.enableGuide(guide, was_enabled)
        except Exception:
            pass
        try:
            if "_ortho_ruler" in _restore_guides:
                vp_settings.setOrthoRuler(_restore_guides["_ortho_ruler"])
        except Exception:
            pass
        try:
            if _restore_reference_plane is not None:
                viewer.referencePlane().setIsVisible(_restore_reference_plane)
        except Exception:
            pass
        try:
            if _restore_view_type is not None:
                viewport.changeType(_restore_view_type)
        except Exception:
            pass
        try:
            if _restore_hidden:
                for path in _restore_hidden:
                    node = hou.node(path)
                    if node is not None:
                        node.setDisplayFlag(True)
        except Exception:
            pass
        try:
            if _restore_shading is not None:
                vp_settings = viewport.settings()
                display_set = vp_settings.displaySet(hou.displaySetType.DisplayModel)
                display_set.setShadedMode(_restore_shading)
        except Exception:
            pass


def capture_component_detail(
    filepath: str,
    node_path: str,
    component_ids: list[str],
    views: list[str] | None = None,
    shading_mode: str = "smooth",
    resolution: tuple[int, int] | None = None,
) -> dict[str, Any]:
    """Capture close-up screenshots of specific components, one cell per id.

    This solves the recurring "component exists but is too small to see at
    whole-asset viewport resolution" failure (chains, pedals, bolts, small
    trim). For each component_id in `component_ids`, the viewport is framed
    tightly around THAT component's own bounding box and captured, so the
    vision model can actually see it.

    Args:
        filepath: Output grid image path.
        node_path: SOP node carrying the geometry with @component_id.
        component_ids: e.g. ["chain_top", "pedal", "chainring"].
        views: Per-cell view(s). Default ["perspective"]. A single view keeps
            cells large; pass ["perspective","top"] for a 2-view-per-component
            contact sheet.
        shading_mode: Passed through to the viewport display set.
        resolution: Per-cell pixel size.

    Returns: same shape as capture_review (success/path/grid/captured).
    """
    import os as _os
    import uuid as _uuid

    filepath = _os.path.abspath(filepath)
    if views is None:
        views = ["perspective"]
    valid_views = {"perspective", "top", "front", "right", "bottom", "back", "left"}
    views = [v.lower() for v in views if v.lower() in valid_views] or ["perspective"]

    # Resolve per-component bounding boxes from the geometry inventory
    inv = geometry_inventory(node_path)
    if not inv.get("success"):
        return {"success": False, "error": inv.get("error", "inventory failed"),
                "method": "component_detail"}
    if not inv.get("has_component_id"):
        return {"success": False,
                "error": "Geometry has no @component_id attribute — cannot "
                         "isolate components for close-up capture.",
                "method": "component_detail"}

    by_id = {c["component_id"]: c for c in inv["components"]}
    missing = [cid for cid in component_ids if cid not in by_id]
    present = [cid for cid in component_ids if cid in by_id]
    if missing:
        return {
            "success": False,
            "error": (f"component_ids not found in geometry: {missing}. "
                      f"Available: {sorted(by_id)[:20]}"),
            "method": "component_detail",
            "available": sorted(by_id)[:40],
        }
    if not present:
        return {"success": False, "error": "No matching component_ids.",
                "method": "component_detail"}

    _restore_hidden: list[str] = []
    _restore_shading = None
    _restore_view_type = None
    stage = "initialize"

    try:
        stage = "get_viewer"
        desktop = hou.ui.curDesktop()
        viewer = desktop.paneTabOfType(hou.paneTabType.SceneViewer)
        if viewer is None:
            return {"success": False, "error": "No Scene Viewer pane found",
                    "method": "component_detail"}
        viewport = viewer.curViewport()
        _restore_view_type = viewport.type() if hasattr(viewport, "type") else None

        # Shading
        vp_settings = viewport.settings()
        try:
            shading_map = {
                "smooth": hou.glShadingType.Smooth,
                "smooth_wire": hou.glShadingType.SmoothWire,
                "wire": hou.glShadingType.Wire,
                "flat": hou.glShadingType.Flat,
            }
            if shading_mode in shading_map:
                display_set = vp_settings.displaySet(hou.displaySetType.DisplayModel)
                _restore_shading = display_set.shadedMode()
                display_set.setShadedMode(shading_map[shading_mode])
        except Exception:
            pass

        # Make the target visible + current, hide other /obj siblings
        target_node = hou.node(node_path)
        if target_node is None:
            return {"success": False, "error": f"Node not found: {node_path}",
                    "method": "component_detail"}
        try:
            target_node.setDisplayFlag(True)
            target_node.setCurrent(True, clear_all_selected=True)
        except Exception:
            pass
        try:
            obj = hou.node("/obj")
            tp = target_node.path()
            for child in obj.children() if obj else []:
                cp = child.path()
                if cp == tp or tp.startswith(cp + "/"):
                    continue
                try:
                    if child.isDisplayFlagSet():
                        child.setDisplayFlag(False)
                        _restore_hidden.append(cp)
                except Exception:
                    pass
        except Exception:
            pass

        _os.makedirs(_os.path.dirname(filepath) or ".", exist_ok=True)
        tmp_dir = _os.path.dirname(filepath)
        captured: list[str] = []
        cell_errors: list[str] = []

        for cid in present:
            comp = by_id[cid]
            bnds = comp.get("bounds")
            if not bnds:
                cell_errors.append(f"{cid}: no bounds")
                continue

            # Build a hou.BoundingBox for this component and frame to it
            try:
                bbox = hou.BoundingBox(
                    hou.Vector3(bnds["min"]),
                    hou.Vector3(bnds["max"]),
                )
            except Exception:
                cell_errors.append(f"{cid}: bbox build failed")
                continue

            for view_name in views:
                tmp_path = _os.path.join(
                    tmp_dir, f"_edini_detail_{_uuid.uuid4().hex[:8]}.png")
                view_type = _get_view_type(view_name)
                if view_type is not None:
                    try:
                        viewport.changeType(view_type)
                    except Exception:
                        pass
                # Frame tightly around THIS component with extra padding so the
                # whole part is centered and clearly visible.
                try:
                    viewport.setViewToBoundingBox(bbox, 0.0, 1.4)
                    viewport.draw(True, True)
                except Exception:
                    try:
                        viewport.homeAll()
                    except Exception:
                        pass
                ok, err = _capture_single_view(
                    viewer, viewport, tmp_path, 1, resolution)
                if ok:
                    captured.append(tmp_path)
                else:
                    cell_errors.append(f"{cid}@{view_name}: {err[:100]}")

        if not captured:
            return {"success": False,
                    "error": f"All captures failed: {cell_errors[:5]}",
                    "method": "component_detail"}

        columns = len(views)
        concat_ok = _concat_images_grid(captured, filepath, columns, resolution)
        for tmp in captured:
            try:
                if _os.path.exists(tmp) and tmp != filepath:
                    _os.remove(tmp)
            except Exception:
                pass
        if not concat_ok and captured and _os.path.exists(captured[0]):
            import shutil
            shutil.copy(captured[0], filepath)

        if not _os.path.exists(filepath):
            return {"success": False, "error": f"Output not created: {filepath}",
                    "method": "component_detail"}

        size_kb = round(_os.path.getsize(filepath) / 1024, 1)
        actual_cols = min(columns, len(captured))
        actual_rows = (len(captured) + actual_cols - 1) // actual_cols
        return {
            "success": True,
            "path": filepath,
            "size_kb": size_kb,
            "method": "component_detail",
            "grid": {"rows": actual_rows, "cols": actual_cols, "cells": len(captured)},
            "captured": captured[:10],
            "errors": cell_errors[:10] if cell_errors else [],
            "components": present,
            "views": views,
        }
    except Exception as e:
        return {"success": False, "error": str(e), "method": "component_detail",
                "stage": stage, "traceback": traceback.format_exc()}
    finally:
        try:
            if _restore_view_type is not None:
                viewport.changeType(_restore_view_type)
        except Exception:
            pass
        try:
            for p in _restore_hidden:
                n = hou.node(p)
                if n is not None:
                    n.setDisplayFlag(True)
        except Exception:
            pass
        try:
            if _restore_shading is not None:
                ds = viewport.settings().displaySet(hou.displaySetType.DisplayModel)
                ds.setShadedMode(_restore_shading)
        except Exception:
            pass


def get_hda_info(hda_name: str) -> dict[str, Any]:
    """Get information about an HDA definition."""
    try:
        definition = hou.hda.definitions().get(hda_name)
        if definition is None:
            return {"success": False, "error": f"HDA '{hda_name}' not found in loaded definitions"}

        return {
            "success": True,
            "name": definition.nodeTypeName(),
            "description": definition.description(),
            "path": definition.libraryFilePath(),
            "version": definition.version(),
            "is_editable": definition.isEditable(),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Context / Inspection Operations
# ---------------------------------------------------------------------------

def get_selection() -> dict[str, Any]:
    """Get the user's currently selected nodes."""
    try:
        selected = hou.selectedNodes()
        nodes = []
        for n in selected:
            nodes.append({
                "name": n.name(),
                "path": n.path(),
                "type": n.type().name(),
            })
        return {"success": True, "count": len(nodes), "nodes": nodes}
    except Exception as e:
        return {"success": False, "error": str(e)}


def check_errors(node_path: str | None = None) -> dict[str, Any]:
    """Check for Houdini node errors. If node_path given, check that node
    only. Otherwise scan the entire scene."""
    try:
        if node_path:
            node = hou.node(node_path)
            if node is None:
                return {"success": False, "error": f"Node not found: {node_path}"}
            errors = node.errors() or []
            warnings = node.warnings() or []
            return {
                "success": True,
                "path": node_path,
                "error_count": len(errors),
                "warning_count": len(warnings),
                "errors": errors,
                "warnings": warnings,
            }

        # Full scene scan
        error_nodes = []
        warning_nodes = []
        for n in hou.node("/").allSubChildren():
            try:
                errs = n.errors()
                warns = n.warnings()
                if errs:
                    error_nodes.append({"path": n.path(), "errors": errs})
                if warns:
                    warning_nodes.append({"path": n.path(), "warnings": warns})
            except Exception:
                continue

        return {
            "success": True,
            "total_nodes": len(hou.node("/").allSubChildren()),
            "error_nodes": len(error_nodes),
            "warning_nodes": len(warning_nodes),
            "details": error_nodes[:10] + warning_nodes[:10],
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def set_display_flag(node_path: str) -> dict[str, Any]:
    """Set a node as the display/render flag — the node shown in the viewport.

    Tolerates being handed an Object-level node (e.g. a /obj/<geo> container
    from commit_sandbox) which has setDisplayFlag but NO setRenderFlag
    (render flag is a SOP/ROP concept; Object nodes expose it differently).
    Render-flag set is best-effort and never fails the call.
    """
    try:
        node = hou.node(node_path)
        if node is None:
            return {"success": False, "error": f"Node not found: {node_path}"}
        flags_set = {"display": False, "render": False}
        try:
            node.setDisplayFlag(True)
            flags_set["display"] = True
        except Exception:
            pass
        # Render flag is optional — not all node types support it
        # (e.g. ObjNode). Setting it is best-effort.
        try:
            node.setRenderFlag(True)
            flags_set["render"] = True
        except Exception:
            pass
        if not flags_set["display"]:
            return {"success": False, "error":
                    f"Could not set display flag on {node_path} "
                    f"({node.type().name()})"}
        return {"success": True, "path": node_path, "flags": flags_set}
    except Exception as e:
        return {"success": False, "error": str(e)}



# ---------------------------------------------------------------------------
# Orientation Verification (PCA-based) — math lives in edini.orientation_math
# ---------------------------------------------------------------------------

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
            world_axis_attr = geo.findPrimAttrib("edini_world_axis")
            has_world_axis = world_axis_attr is not None
            construction_vec: tuple[float, float, float] | None = None
            if has_world_axis:
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

            # ── PCA fallback path (no edini_world_axis baked) ──
            if len(pts) < 4:
                entry["error"] = (
                    f"Only {len(pts)} unique points - need >= 4 for PCA. "
                    "Subdivide or add more samples."
                )
                results.append(entry); failed += 1; continue

            cov, centroid = _compute_covariance(pts)
            eigs, vecs = _jacobi_eigen_3x3(cov)

            rank = _KIND_EIGEN_RANK[kind]
            detected_vec = vecs[rank]
            expected_vec = _AXIS_VECTORS[expected_axis]
            if not signed_kind:
                detected_vec = _flip_to_hemisphere(detected_vec, expected_vec)
            detected_axis = _dominant_axis_name(detected_vec)

            angle_deg, fix_q = _axis_angle_between(
                detected_vec, expected_vec, signed=signed_kind
            )
            passed_check = angle_deg <= tol_deg

            eig_total = sum(abs(e) for e in eigs) + 1e-12
            ratios = [abs(e) / eig_total for e in eigs]

            entry.update({
                "method": "pca",
                "point_count": len(pts),
                "centroid": [round(c, 4) for c in centroid],
                "eigenvalues": [round(e, 6) for e in eigs],
                "eigenvalue_ratios": [round(r, 4) for r in ratios],
                "eigenvectors": [
                    [round(c, 4) for c in vecs[0]],
                    [round(c, 4) for c in vecs[1]],
                    [round(c, 4) for c in vecs[2]],
                ],
                "detected_axis": detected_axis,
                "detected_vector": [round(c, 4) for c in detected_vec],
                "angle_error_deg": round(angle_deg, 2),
                "passed": passed_check,
            })

            if not passed_check:
                kind_hint = {
                    "radial": "rotational symmetry axis (axle)",
                    "planar": "surface normal",
                    "elongated": "long axis",
                }[kind]
                entry["hint"] = (
                    f"{cid} {kind_hint} currently along {detected_axis} "
                    f"({[round(c,2) for c in detected_vec]}). "
                    f"Expected {expected_axis}. Apply quaternion "
                    f"(x,y,z,w)={[round(c,4) for c in fix_q]} to the component's "
                    f"geometry, or pre-multiply the generating transform: "
                    f"hou.Quaternion({round(fix_q[3],4)}, "
                    f"hou.Vector3({round(fix_q[0],4)}, {round(fix_q[1],4)}, {round(fix_q[2],4)}))."
                )

            results.append(entry)
            if passed_check:
                passed += 1
            else:
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
