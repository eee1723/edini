"""Phase B: Per-component building.

Each component cooks in its own sandbox sub-network, verified immediately
after cook. Three backends: native_chain, vex_skeleton, python.
"""

from __future__ import annotations

import os
import time
from typing import Any

try:
    import hou
except ImportError:
    hou = None  # type: ignore[assignment]  # only available inside Houdini


class ComponentBuildResult:
    """Result of building a single component."""

    __slots__ = (
        "component_id",
        "status",
        "backend",
        "cook_time_ms",
        "geometry",
        "health",
        "component_id_confirmed",
        "cache_path",
        "error",
    )

    def __init__(self, component_id: str, backend: str) -> None:
        self.component_id = component_id
        self.backend = backend
        self.status = "pending"
        self.cook_time_ms = 0
        self.geometry: dict | None = None
        self.health: dict | None = None
        self.component_id_confirmed = False
        self.cache_path: str | None = None
        self.error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "component_id": self.component_id,
            "backend": self.backend,
            "status": self.status,
            "cook_time_ms": self.cook_time_ms,
            "geometry": self.geometry,
            "health": self.health,
            "component_id_confirmed": self.component_id_confirmed,
            "cache_path": self.cache_path,
            "error": self.error,
        }


# ── Backend builders ─────────────────────────────────────────


def _build_native_chain(
    container: Any,  # hou.ObjNode
    comp: dict[str, Any],
    catalog: Any,
) -> Any:  # hou.OpNode
    """Build a native_chain component inside *container*.

    Creates: SOP chain → attribcreate (component_id tag) → Null OUT.
    Returns the OUT null node.
    """
    cid = comp["id"]
    nodes_list: list[dict] = comp.get("nodes", [])
    prev: Any = None  # hou.OpNode | None

    for ni, node_spec in enumerate(nodes_list):
        ntype: str = node_spec["type"]
        # Resolve alias (e.g. "transform" → "xform")
        canonical = catalog.resolve_alias(ntype) if catalog else ntype
        name = f"{cid}_n{ni}"
        try:
            node = container.createNode(canonical, name)
        except hou.OperationFailed as e:
            raise RuntimeError(
                f"component '{cid}' node[{ni}]: failed to create "
                f"'{canonical}': {e}"
            ) from e

        if prev is not None:
            node.setInput(0, prev)
        prev = node

        # Set parameters
        for pname, pvalue in node_spec.get("params", {}).items():
            try:
                parm = node.parm(pname)
                if parm is None:
                    raise RuntimeError(
                        f"parm '{pname}' not found on {canonical}"
                    )
                parm.set(pvalue)
            except Exception as e:
                raise RuntimeError(
                    f"component '{cid}' node[{ni}] parm '{pname}': {e}"
                ) from e

    # attribcreate for component_id tagging (H21 verified menu values)
    tag = container.createNode("attribcreate", f"{cid}_tag")
    if prev is not None:
        tag.setInput(0, prev)
    tag.parm("name1").set("component_id")
    tag.parm("class1").set("primitive")
    tag.parm("type1").set("string")
    tag.parm("string1").set(cid)

    # OUT null
    out = container.createNode("null", f"{cid}_OUT")
    out.setInput(0, tag)
    return out


def _build_vex_skeleton(
    container: Any,  # hou.ObjNode
    comp: dict[str, Any],
    catalog: Any,
) -> Any:  # hou.OpNode
    """Build a vex_skeleton component.

    Creates: attribwrangle (Detail mode, VEX code) → form_node →
    attribcreate → OUT.
    """
    cid = comp["id"]
    code: str = comp.get("code", "")
    form: dict = comp.get("form_node", {})

    # wrangle (Detail mode)
    wr = container.createNode("attribwrangle", f"{cid}_wrangle")
    # Inject vexlib includes before user code
    full_code = (
        "#include <vexlib/skeleton.vfl>\n"
        "#include <vexlib/sections.vfl>\n"
        + code
    )
    wr.parm("snippet").set(full_code)
    wr.parm("class").set(2)  # 2 = Detail mode

    # form_node (Sweep / PolyExtrude)
    fn_type: str = form.get("type", "sweep::2.0")
    canonical = catalog.resolve_alias(fn_type) if catalog else fn_type
    fn = container.createNode(canonical, f"{cid}_form")
    fn.setInput(0, wr)
    for pname, pvalue in form.get("params", {}).items():
        try:
            parm = fn.parm(pname)
            if parm is None:
                raise RuntimeError(
                    f"parm '{pname}' not found on {canonical}"
                )
            parm.set(pvalue)
        except Exception as e:
            raise RuntimeError(
                f"component '{cid}' form_node parm '{pname}': {e}"
            ) from e

    # attribcreate for component_id
    tag = container.createNode("attribcreate", f"{cid}_tag")
    tag.setInput(0, fn)
    tag.parm("name1").set("component_id")
    tag.parm("class1").set("primitive")
    tag.parm("type1").set("string")
    tag.parm("string1").set(cid)

    out = container.createNode("null", f"{cid}_OUT")
    out.setInput(0, tag)
    return out


def _build_python(
    container: Any,  # hou.ObjNode
    comp: dict[str, Any],
) -> Any:  # hou.OpNode
    """Build a python-backend component."""
    cid = comp["id"]
    code: str = comp.get("code", "")

    py = container.createNode("python", f"{cid}_python")
    py.parm("python").set(code)

    out = container.createNode("null", f"{cid}_OUT")
    out.setInput(0, py)
    return out


# ── Main entry point ────────────────────────────────────────


def build_component(
    recipe: dict[str, Any],
    component_id: str,
    sandbox_root_path: str,
    catalog_path: str | None = None,
) -> dict[str, Any]:
    """Build a single component inside the sandbox.

    Args:
        recipe: The full recipe dict (for param definitions).
        component_id: Which component to build.
        sandbox_root_path: e.g. "/obj/edini_sandbox_..."
        catalog_path: Path to parm-catalog.json (optional; enables
            alias resolution).

    Returns:
        ComponentBuildResult as dict.
    """
    # Load catalog (optional — only needed for alias resolution at build time)
    catalog = None
    if catalog_path:
        from edini.parm_catalog import ParmCatalog

        catalog = ParmCatalog.load(catalog_path)

    # Find the component in the recipe
    comp: dict | None = None
    for c in recipe.get("components", []):
        if c.get("id") == component_id:
            comp = c
            break
    if comp is None:
        return {
            "component_id": component_id,
            "status": "failed",
            "error": f"Component '{component_id}' not found in recipe",
        }

    result = ComponentBuildResult(component_id, comp.get("backend", "python"))
    t0 = time.time()

    try:
        if hou is None:
            raise RuntimeError(
                "hou module not available — component_builder "
                "requires the Houdini Python environment"
            )

        root = hou.node(sandbox_root_path)
        if root is None:
            raise RuntimeError(
                f"Sandbox root not found: {sandbox_root_path}"
            )

        # Create (or re-create) the component subnet
        subnet_name = f"comp_{component_id}"
        existing = root.node(subnet_name)
        if existing is not None:
            existing.destroy()
        subnet = root.createNode("subnet", subnet_name)

        # Dispatch to the correct backend builder
        backend = comp.get("backend", "python")
        if backend == "native_chain":
            out_node = _build_native_chain(subnet, comp, catalog)
        elif backend == "vex_skeleton":
            out_node = _build_vex_skeleton(subnet, comp, catalog)
        else:
            out_node = _build_python(subnet, comp)

        # Cook the OUT node
        out_node.cook(force=True)

        # ── Verify geometry ──
        geo = out_node.geometry()
        if geo is None:
            result.status = "failed"
            result.error = "B1_EMPTY_GEO: component cooked but geometry() returned None"
            result.cook_time_ms = int((time.time() - t0) * 1000)
            return result.to_dict()

        # A geometry with zero points is empty
        try:
            pt_count = geo.intrinsicValue("pointcount")
        except Exception:
            pt_count = -1
        if pt_count <= 0:
            result.status = "failed"
            result.error = (
                "B1_EMPTY_GEO: component cooked but produced "
                "no geometry (0 points)"
            )
            result.cook_time_ms = int((time.time() - t0) * 1000)
            return result.to_dict()

        # ── Check component_id ──
        has_cid = False
        for p in geo.iterPrims():
            try:
                if p.stringAttribValue("component_id") == component_id:
                    has_cid = True
                    break
            except hou.OperationFailed:
                # Prim may not have the attribute at all
                pass

        # ── Health check ──
        from edini.node_utils import inspect_geometry_health

        health = inspect_geometry_health(out_node.path())

        result.status = "passed"
        result.geometry = _geo_stats(geo)
        result.health = health
        result.component_id_confirmed = has_cid
        result.cook_time_ms = int((time.time() - t0) * 1000)

        # Cache path (actual caching done by ComponentCache in Task 4)
        cache_dir = os.path.join(
            os.path.dirname(catalog_path or "."),
            "component_cache",
            component_id,
        )
        result.cache_path = cache_dir

        return result.to_dict()

    except Exception as e:
        result.status = "failed"
        result.error = f"B1_COOK_FAILED: {e}"
        result.cook_time_ms = int((time.time() - t0) * 1000)
        return result.to_dict()


# ── Helpers ──────────────────────────────────────────────────


def _geo_stats(geo: Any) -> dict[str, Any]:  # geo: hou.Geometry
    """Extract basic geometry stats from a cooked geometry object."""
    bbox = geo.boundingBox()
    return {
        "point_count": geo.intrinsicValue("pointcount"),
        "prim_count": geo.intrinsicValue("primitivecount"),
        "vertex_count": geo.intrinsicValue("vertexcount"),
        "bounds": {
            "min": list(bbox.minvec()),
            "max": list(bbox.maxvec()),
            "size": list(bbox.sizevec()),
        },
    }
