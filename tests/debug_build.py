import sys, os, traceback
sys.path.insert(0, r"Z:\EEE_Project\Edini\python3.11libs")
for mod in list(sys.modules.keys()):
    if mod.startswith("edini."): del sys.modules[mod]
if "edini" in sys.modules: del sys.modules["edini"]

import hou
from edini.harness import (
    build_procedural_asset,
    _build_native_chain_component,
    _safe_create_node, _set_parm_safe,
    _anchor_generator_code, _component_id_overwrite_snippet,
    _create_sandbox_root, _resolve_anchor_exprs,
)

# Replicate the full build_procedural_asset flow step by step
recipe = {
    "components": [
        {"id": "b1", "backend": "native_chain",
         "nodes": [{"type": "box", "params": {"sizex": 2, "sizey": 0.5, "sizez": 1}},
                   {"type": "attribwrangle", "params": {"class": 1, "snippet": "s@component_id = 'b1';"}}]},
        {"id": "b2", "backend": "native_chain",
         "nodes": [{"type": "box", "params": {"sizex": 0.3, "sizey": 0.3, "sizez": 0.3}},
                   {"type": "attribwrangle", "params": {"class": 1, "snippet": "s@component_id = 'b2';"}}],
         "anchors": [{"position": [2,0,0], "orient": [0,0,0,1], "pscale": 1.0, "component_id": "copied"}]}
    ],
    "orientation_asserts": [
        {"component_id": "b1", "kind": "planar", "expected_axis": "Y", "signed": True, "construction_axis": "Y"}
    ]
}

job_id, root_path = _create_sandbox_root("step_debug")
root = hou.node(root_path)
print(f"Sandbox: {root_path}")

comp_nodes = []
stamped = []
world_axis_by_cid = {k: (0.0, 0.0, 0.0) for k in ["b1"]}  # mock

try:
    for comp in recipe["components"]:
        cid = comp["id"]
        anchors = comp.get("anchors") or []
        
        out_sop = _build_native_chain_component(root_path, comp, cid, world_axis_by_cid, anchors)
        out_sop.cook(force=True)
        print(f"  {cid}: cooked, pts={out_sop.geometry().intrinsicValue('pointcount')}")
        
        if anchors:
            resolved, _ = _resolve_anchor_exprs(anchors, {}, cid)
            anchor_ids = [a["component_id"] for a in resolved]
            
            anc_sop = _safe_create_node(root_path, "python", f"{cid}_anchors")
            _set_parm_safe(anc_sop, "python", _anchor_generator_code(resolved, cid))
            anc_sop.cook(force=True)
            print(f"    anchors: {anc_sop.geometry().intrinsicValue('pointcount')} pts")
            
            copy_node = _safe_create_node(root_path, "copytopoints", f"copy_{cid}")
            copy_node.setInput(0, out_sop)
            copy_node.setInput(1, anc_sop)
            
            ow_sop = _safe_create_node(root_path, "python", f"{cid}_idfix")
            _set_parm_safe(ow_sop, "python", _component_id_overwrite_snippet(anchor_ids))
            ow_sop.setInput(0, copy_node)
            ow_sop.cook(force=True)
            print(f"    idfix cooked: {ow_sop.geometry().intrinsicValue('pointcount')} pts")
            comp_nodes.append(ow_sop)
        else:
            comp_nodes.append(out_sop)
    
    # Merge
    merge = _safe_create_node(root_path, "merge", "merge_all")
    for idx, node in enumerate(comp_nodes):
        merge.setInput(idx, node)
    print(f"  merge: {merge.path()}")
    
    # Test fuse (just create, don't cook yet)
    fuse = None
    try:
        fuse = _safe_create_node(root_path, "fuse", "post_fuse")
        fuse.setInput(0, merge)
        print(f"  fuse created: {fuse.path()} type={fuse.type().name()}")
        fuse.cook(force=True)
        print(f"  fuse cooked: {fuse.geometry().intrinsicValue('pointcount')} pts")
    except Exception as e:
        print(f"  fuse FAILED: {e}")
