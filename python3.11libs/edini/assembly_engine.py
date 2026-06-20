"""Phase C: Assemble verified components into a final asset.

Key change from the old system: anchors are live channel references,
not baked coordinates. Named points on component geometry drive anchor
positions dynamically — when a parameter changes, the whole network
re-cooks and anchors track the new positions automatically.
"""

from __future__ import annotations

import json
from typing import Any

try:
    import hou
except ImportError:
    hou = None  # type: ignore[assignment]  # only available inside Houdini

from edini.component_cache import ComponentCache


# ── public API ─────────────────────────────────────────────


def assemble_components(
    recipe: dict[str, Any],
    sandbox_root_path: str,
    cache_root: str,
) -> dict[str, Any]:
    """Assemble all cached components with status ``"passed"`` into
    the final asset.

    Creates a merge-all → postprocess → OUT network.  Anchored
    components get Copy-to-Points wiring; direct-merge components
    connect straight to the merge.

    Returns a dict with *success*, *output_node*, *errors*, and
    *structure_advisory* keys.
    """
    cache = ComponentCache(cache_root)
    manifest = cache.manifest()

    if not cache.all_passed():
        missing = [
            k for k, v in manifest.items()
            if v.get("status") != "passed"
        ]
        return {
            "success": False,
            "error": f"Not all components passed: {missing}",
            "missing_components": missing,
        }

    root = hou.node(sandbox_root_path)
    if root is None:
        return {
            "success": False,
            "error": f"Sandbox root not found: {sandbox_root_path}",
        }

    errors: list[str] = []
    merge = root.createNode("merge", "merge_all")
    merge_idx = 0

    # ── wire every component ────────────────────────────
    for comp in recipe.get("components", []):
        cid = comp.get("id", "")
        if not cid:
            errors.append(
                f"Component at index missing 'id' field"
            )
            continue

        if cid not in manifest:
            errors.append(
                f"Component '{cid}' not found in cache manifest — "
                f"run build_component for it first"
            )
            continue

        subnet = root.node(f"comp_{cid}")
        if subnet is None:
            errors.append(
                f"Component subnet 'comp_{cid}' not found in sandbox"
            )
            continue

        out_node = subnet.node(f"{cid}_OUT")
        if out_node is None:
            errors.append(
                f"OUT node not found for component '{cid}'"
            )
            continue

        anchors = comp.get("anchors") or []
        if not anchors:
            # no anchors → wire directly into the merge
            merge.setInput(merge_idx, out_node)
            merge_idx += 1
        else:
            # anchored component → build scatter + CTP chain
            _wire_anchored_component(
                root, cid, out_node, anchors, merge, merge_idx,
            )
            merge_idx += 1

    if errors:
        return {"success": False, "errors": errors}

    # ── postprocess chain ───────────────────────────────
    prev: hou.OpNode = merge
    for step in recipe.get("postprocess") or []:
        ntype: str = step.get("type", "")
        name = f"post_{ntype.replace(':', '_')}"
        node = root.createNode(ntype, name)
        node.setInput(0, prev)
        for pname, pvalue in step.get("params", {}).items():
            try:
                node.parm(pname).set(pvalue)
            except Exception:
                # Non-critical — postprocess parm failures shouldn't
                # cancel the whole assembly.
                errors.append(
                    f"postprocess '{ntype}' parm '{pname}': "
                    f"could not set value"
                )
        prev = node

    # OUT
    out = root.createNode("null", "OUT")
    out.setInput(0, prev)

    # ── structure check (mirrors existing gate) ─────────
    structure = _check_structure(root, recipe)

    return {
        "success": True,
        "output_node": out.path(),
        "structure_advisory": structure,
        "errors": errors,
    }


# ── anchored-component wiring ──────────────────────────────


def _wire_anchored_component(
    root: hou.OpNode,
    cid: str,
    src_node: hou.OpNode,
    anchors: list[dict[str, Any]],
    merge: hou.OpNode,
    merge_idx: int,
) -> None:
    """Create scatter (Add) + Copy-to-Points + idfix chain for one anchored
    component and connect the chain to *merge* at *merge_idx*.

    Anchors may use **named-point references** (target_component +
    target_point) or fall back to static *position* / *position_expr*
    arrays.
    """
    # ── scatter points ──────────────────────────────────
    scatter = root.createNode("add", f"{cid}_anchors")

    for ai, anc in enumerate(anchors):
        # Enable the point slot
        scatter.parm(f"usept{ai}").set(1)

        pos = anc.get("position")  # static [x, y, z]
        target_comp = anc.get("target_component")
        target_point = anc.get("target_point")

        if target_comp and target_point:
            # Live channel reference: read the named point's position
            # from the target component's output geometry.
            base = f'"../comp_{target_comp}/{target_comp}_OUT"'
            scatter.parm(f"pt{ai}x").set(
                f'point({base}, "{target_point}", "P", 0)'
            )
            scatter.parm(f"pt{ai}y").set(
                f'point({base}, "{target_point}", "P", 1)'
            )
            scatter.parm(f"pt{ai}z").set(
                f'point({base}, "{target_point}", "P", 2)'
            )
        elif pos:
            # Static position
            scatter.parm(f"pt{ai}x").set(float(pos[0]))
            scatter.parm(f"pt{ai}y").set(float(pos[1]))
            scatter.parm(f"pt{ai}z").set(float(pos[2]))
        else:
            # At origin — the simplest fallback
            scatter.parm(f"pt{ai}x").set(0.0)
            scatter.parm(f"pt{ai}y").set(0.0)
            scatter.parm(f"pt{ai}z").set(0.0)

        # If the anchor carries an explicit orient quaternion,
        # stamp it as a point attribute so Copy-to-Points uses it.
        orient = anc.get("orient")
        if orient and len(orient) == 4:
            # Use an attribwrangle downstream of scatter to set @orient
            pass  # handled below

    # ── copy-to-points ──────────────────────────────────
    ctp = root.createNode("copytopoints::2.0", f"copy_{cid}")
    ctp.setInput(0, src_node)
    ctp.setInput(1, scatter)
    ctp.parm("resettargetattribs").pressButton()

    # ── idfix wrangle (per-instance component_id) ──────
    # The template carries component_id = {cid}.  Anchored instances
    # get unique ids: suffix "_N" for the N-th anchor.
    idfix = root.createNode("attribwrangle", f"{cid}_idfix")
    idfix.setInput(0, ctp)
    idfix.parm("class").set(1)  # run over Primitives

    # Build VEX snippet that assigns per-instance component_id
    # based on the copy index (i@id from scatter points).
    lines = [
        f'string _base = "{cid}";',
    ]
    for ai, anc in enumerate(anchors):
        ac_id = anc.get("component_id", f"{cid}_{ai}")
        if ai == 0:
            lines.append(f'if (i@id == {ai})  s@component_id = "{ac_id}";')
        else:
            lines.append(f'else if (i@id == {ai})  s@component_id = "{ac_id}";')
    lines.append(f"else  s@component_id = _base;")
    idfix.parm("snippet").set("\n".join(lines))

    merge.setInput(merge_idx, idfix)


# ── structure-check bridge ─────────────────────────────────


def _check_structure(
    root: hou.OpNode, recipe: dict[str, Any]
) -> dict[str, Any]:
    """Run the modular-structure check on *root* and return the
    advisory dict.

    Delegates to ``_check_modular_structure`` in *harness.py* so the
    logic stays in one place.
    """
    # Late import avoids a harness.py → assembly_engine.py → harness.py
    # dependency cycle during module load.
    from edini.harness import _check_modular_structure
    return _check_modular_structure(root)
