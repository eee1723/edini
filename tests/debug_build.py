import sys, os
sys.path.insert(0, r"Z:\EEE_Project\Edini\python3.11libs")
for mod in list(sys.modules.keys()):
    if mod.startswith("edini."): del sys.modules[mod]
if "edini" in sys.modules: del sys.modules["edini"]

from edini.harness import build_procedural_asset

base = {
    "components": [
        {"id": "b1", "backend": "native_chain",
         "nodes": [{"type": "box", "params": {"sizex": 2, "sizey": 0.5, "sizez": 1}},
                   {"type": "attribwrangle", "params": {"class": 1, "snippet": "s@component_id = 'b1';"}}]},
        {"id": "b2", "backend": "native_chain",
         "nodes": [{"type": "box", "params": {"sizex": 0.3, "sizey": 0.3, "sizez": 0.3}},
                   {"type": "attribwrangle", "params": {"class": 1, "snippet": "s@component_id = 'b2';"}}],
         "anchors": [{"position": [2,0,0], "orient": [0,0,0,1], "pscale": 1.0, "component_id": "copied"}]}
    ]
}

tests = [
    ("fuse", {"postprocess": [{"type": "fuse"}]}),
    ("fuse+clean", {"postprocess": [{"type": "fuse"}, {"type": "clean"}]}),
    ("fuse+clean+normal", {"postprocess": [{"type": "fuse"}, {"type": "clean"}, {"type": "normal", "params": {"cuspangle": 60}}]}),
    ("caxis_anchored", {"orientation_asserts": [
        {"component_id": "copied", "kind": "planar", "expected_axis": "Y", "signed": True, "construction_axis": "Y"}
    ]}),
    ("caxis_direct", {"orientation_asserts": [
        {"component_id": "b1", "kind": "planar", "expected_axis": "Y", "signed": True, "construction_axis": "Y"}
    ]}),
]

for label, extra in tests:
    recipe = {**base, **extra}
    r = build_procedural_asset(recipe)
    ok = r.get("success")
    err = str(r.get("error",""))[:150] if not ok else ""
    print(f"{label:25s}: {'PASS' if ok else 'FAIL: '+err}")
