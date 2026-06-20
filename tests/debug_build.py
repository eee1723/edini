import sys, os
sys.path.insert(0, r"Z:\EEE_Project\Edini\python3.11libs")
for mod in list(sys.modules.keys()):
    if mod.startswith("edini."): del sys.modules[mod]
if "edini" in sys.modules: del sys.modules["edini"]

import hou
from edini.harness import _safe_create_node, _set_parm_safe, _create_sandbox_root

job_id, root_path = _create_sandbox_root("idfix_debug")
root = hou.node(root_path)

# Create box via safe_create_node (handles namespace resolution)
box = _safe_create_node(root_path, "box", "test_box")
_set_parm_safe(box, "sizex", 1.0)
box.cook(force=True)

# Create Python SOP for idfix
py = _safe_create_node(root_path, "python", "test_idfix")
py.setInput(0, box)

py.parm("python").set("""
node = hou.pwd()
geo = node.geometry()
prims = geo.prims()
for prim in prims:
    prim.setAttribValue('component_id', 'test_id')
""")

try:
    py.cook(force=True)
    print("Cook OK")
    geo = py.geometry()
    print("Prims:", geo.intrinsicValue("primitivecount"))
    for p in geo.prims():
        print("  cid:", p.stringAttribValue("component_id"))
except Exception as e:
    import traceback
    print("FAILED:", e)
    traceback.print_exc()
    print("Node errs:", list(py.errors() or []))
