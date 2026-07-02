"""Project HDA → rooted geometry builder.

Bridges the Project declaration to the existing rooted-modeling
`build_assembly`, building the geometry INSIDE the Project's SOP-context HDA
core node. This is the "can it actually model" leap — the declaration's
`assembly` field (rooted format) becomes live SOP geometry in the HDA.

Pure reuse: `edini.assembly_builder.build_assembly` and `validate_assembly` are
imported unchanged. This module is the Project-HDA-specific entry point that:
  1. loads the declaration from the core node,
  2. validates the assembly (shift-left — fail before touching the scene),
  3. clears the core's existing children (rebuild is idempotent),
  4. calls build_assembly with the core as root_path (geometry lands inside),
  5. logs the result + updates the declaration's components mirror.
"""
from __future__ import annotations

import hou  # real hou at runtime

from edini.assembly_builder import build_assembly, validate_assembly

from .state import (
    get_assembly,
    set_assembly,
    load_declaration,
    save_declaration,
    append_log,
)


def build_project_model(core_node: "hou.Node", *, assembly: dict | None = None) -> dict:
    """Build the rooted geometry inside the Project core node.

    Args:
        core_node: the edini::project SOP HDA instance (build_assembly's
            root_path). Its internal network receives the geometry.
        assembly: optional rooted assembly dict to set BEFORE building
            (convenience — equivalent to set_assembly + save + build). If
            omitted, the declaration's current `assembly` field is used.

    Returns build_assembly's result dict (success/out_path/mount_ids/...),
    enriched with a `project` field carrying the core path. On validation or
    build failure, returns {success: False, error: ...} and the scene is
    untouched (clear-out happens only after validation passes).
    """
    # Load current declaration (or start fresh if the parm is empty).
    declaration = load_declaration(core_node)

    # Optionally update the assembly before building.
    if assembly is not None:
        set_assembly(declaration, assembly)
        save_declaration(core_node, declaration)
        declaration = load_declaration(core_node)  # re-read for consistency

    asm = get_assembly(declaration)
    if asm is None:
        return {"success": False, "error": "no assembly defined in declaration"}

    # Shift-left validation — fail before touching the scene.
    vresult = validate_assembly(asm)
    if not vresult["success"]:
        errs = "; ".join(e.get("message", e.get("code", "?")) for e in vresult["errors"])
        return {"success": False, "error": f"assembly validation failed: {errs}",
                "validation_errors": vresult["errors"]}

    # Clear existing children of the core so rebuild is idempotent. The core is
    # a SOP-context HDA whose internal network holds the rooted geometry.
    # The HDA definition is authored UNLOCKED (lockContents=False +
    # unlockNewInstances=True, see make_project_hda.py) so fresh instances are
    # editable by design. _ensure_editable is kept as a defensive fallback for
    # legacy/locked instances (no-op if already editable).
    _ensure_editable(core_node)
    _clear_children(core_node)

    # Build. root_path = the core node itself; build_assembly creates all SOPs
    # as its children and installs spare parms for the assembly params on it.
    result = build_assembly(asm, core_node.path())

    # Persist outcome + mirror components (lightweight: just ids for now).
    declaration = load_declaration(core_node)
    if result.get("success"):
        _mirror_components(declaration, asm, result)
        append_log(declaration, kind="build", summary=f"built {asm.get('id', '?')}",
                   payload={"out_path": result.get("out_path"),
                            "mount_ids": result.get("mount_ids", []),
                            "leaf_ids": result.get("leaf_ids", [])},
                   result_ok=True)
    else:
        append_log(declaration, kind="build", summary="build failed",
                   payload={"error": result.get("error", "")}, result_ok=False)
    save_declaration(core_node, declaration)

    result["project"] = core_node.path()
    return result


def _clear_children(node: "hou.Node") -> None:
    """Destroy all child nodes of `node` (idempotent rebuild prep)."""
    for child in node.children():
        child.destroy()


def _ensure_editable(node: "hou.Node") -> None:
    """Unlock the node's HDA contents if locked, so we can build inside it.

    HDA instances ship with locked contents (read-only internal network) by
    default. Project HDAs are meant to host dynamically-built + hand-editable
    geometry, so we unlock on first build. allowEditingOfContents is idempotent
    (no-op if already editable). Safe to call on non-HDA nodes too (no-op).
    """
    try:
        node.allowEditingOfContents()
    except Exception:
        # Not an HDA instance, or already editable — either way, proceed.
        pass


def _mirror_components(declaration: dict, assembly: dict, result: dict) -> None:
    """Refresh the components[] mirror from the assembly + build result.

    Minimal v1: one entry per mount + leaf, recording id + type + role. This is
    the seed of the drift-detection inventory (future work); for now it just
    keeps components[] roughly in sync with what was built.
    """
    comps = []
    root_shape = assembly.get("root", {}).get("shape", {})
    comps.append({"id": "root", "role": "root",
                  "type": root_shape.get("type", "?")})
    for mt in assembly.get("mounts") or []:
        comps.append({"id": mt["id"], "role": "mount",
                      "type": mt.get("position", {}).get("measure", "?")})
    for lf in assembly.get("leaves") or []:
        comps.append({"id": lf["id"], "role": "leaf",
                      "type": lf.get("shape", {}).get("type", "?"),
                      "mount": lf.get("mount")})
    declaration["components"] = comps
