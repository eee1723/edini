"""
Edini Pipeline Architecture — End-to-End Validation Script
===========================================================
Run in Houdini Python Shell.
"""
import json, os, sys
EDINI_ROOT = r"Z:\EEE_Project\Edini"
sys.path.insert(0, os.path.join(EDINI_ROOT, "python3.11libs"))
for mod in list(sys.modules.keys()):
    if mod.startswith("edini."): del sys.modules[mod]
if "edini" in sys.modules: del sys.modules["edini"]

PASS = FAIL = 0

def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        msg = f"  [FAIL] {name}"
        if detail: msg += f" -- {str(detail)[:200]}"
        print(msg)

def section(title):
    print(f"\n{'='*60}\n  {title}\n{'='*60}")

# ═══ Phase 0: Catalog ═══
section("Phase 0: Parm Catalog")
from edini.parm_catalog import ParmCatalog
catalog_path = os.path.join(EDINI_ROOT, "python3.11libs", "edini", "data", "parm-catalog.json")

try:
    raw = ParmCatalog.generate_catalog()
    os.makedirs(os.path.dirname(catalog_path), exist_ok=True)
    with open(catalog_path, "w", encoding="utf-8") as f:
        json.dump(raw, f, indent=2, ensure_ascii=False)
    check("0.1 Catalog generated", len(raw.get("Sop",{})) > 100, f"{len(raw.get('Sop',{}))} SOP types")
except Exception as e:
    check("0.1 Catalog generated", os.path.exists(catalog_path), str(e)[:100])

try:
    cat = ParmCatalog.load(catalog_path)
    check("0.2 Catalog loaded", cat is not None)
except Exception as e:
    check("0.2 Catalog loaded", False, str(e)[:100])
    cat = None

if cat:
    check("0.3 torus exists", cat.has_node_type("torus"))
    check("0.4 tube exists", cat.has_node_type("tube"))
    check("0.5 xform exists", cat.has_node_type("xform"))
    check("0.6 sweep exists", cat.has_node_type("sweep::2.0"))
    check("0.7 transform->xform", cat.resolve_alias("transform") == "xform")
    check("0.8 fuse alias", cat.resolve_alias("fuse") == "fuse::2.0")

# ═══ Phase A: Validation ═══
section("Phase A: Recipe Validation")
from edini.recipe_validator import validate_recipe as phase_a

r = phase_a({"components": [{"id":"b","backend":"native_chain","nodes":[{"type":"box"}]}]})
check("A1 valid recipe", r["passed"])

r = phase_a({"components": [{"id":"b","backend":"INVALID"}]})
check("A1 invalid backend", not r["passed"])

r = phase_a({"components": [{"id":"f","backend":"vex_skeleton","code":"chf('%r%');","form_node":{"type":"sweep::2.0","input0":"self"}}]})
check("A4 VEX %", not r["passed"])

r = phase_a({"components": [{"id":"f","backend":"vex_skeleton","code":"void foo(){}","form_node":{"type":"sweep::2.0","input0":"self"}}]})
check("A4 VEX function", not r["passed"])

r = phase_a({"components": [{"id":"r","backend":"native_chain","nodes":[{"type":"torus","params":{"radscale":0.1}}]}],
              "orientation_asserts": [{"component_id":"r","kind":"radial","construction_axis":"Y","expected_axis":"X","tolerance_deg":10}]})
check("A5 axis mismatch", not r["passed"])

r = phase_a({"components": [{"id":"b","backend":"native_chain","nodes":[{"type":"box"}]}],
              "params": {"A":{"kind":"derived","from":"B+1","default":1},"B":{"kind":"derived","from":"A+1","default":2}}})
check("A6 cycle", not r["passed"])

if cat:
    r = phase_a({"components": [{"id":"b","backend":"native_chain","nodes":[{"type":"tube","params":{"nonexistent_xyz":999}}]}]}, catalog_path)
    check("A2 bad parm", not r["passed"])
    r = phase_a({"components": [{"id":"b","backend":"vex_skeleton","code":"int a;","form_node":{"type":"nonexistent_xyz","input0":"self"}}]}, catalog_path)
    check("A3 bad type", not r["passed"])

# ═══ Phase B+C: Build ═══
section("Phase B+C: Build & Verify")
import hou
from edini.harness import build_procedural_asset, commit_sandbox
from edini.node_utils import inspect_geometry_health, verify_orientation, geometry_inventory

# Clean previous
existing = hou.node("/obj/validation_test_result")
if existing: existing.destroy()

recipe = {
    "asset_name": "validation_test",
    "components": [
        {"id": "base_box", "backend": "native_chain",
         "nodes": [{"type": "box", "params": {"size": [2, 0.5, 1]}},
                   {"type": "attribwrangle", "params": {"class": "primitive", "snippet": "s@component_id = 'base_box';"}}]},
        {"id": "pillar", "backend": "native_chain",
         "nodes": [{"type": "box", "params": {"size": [0.3, 0.3, 0.3]}},
                   {"type": "attribwrangle", "params": {"class": "primitive", "snippet": "s@component_id = 'pillar';"}}],
         "anchors": [{"position": [2, 0.5, 0], "orient": [0,0,0,1], "pscale": 1.0, "component_id": "pillar_copy"}]}
    ],
    "postprocess": [],
    "orientation_asserts": [
        {"component_id": "base_box", "kind": "planar", "expected_axis": "Y", "signed": True},
        {"component_id": "pillar_copy", "kind": "planar", "expected_axis": "Y", "signed": True}
    ]
}

result = build_procedural_asset(recipe)
check("B1 build success", result.get("success"), str(result.get("error",""))[:200])
out_node = result.get("output_node", "")
check("B2 output_node", bool(out_node))
check("B3 has geometry", result.get("structural_checks",{}).get("has_geometry",False))

if out_node:
    health = inspect_geometry_health(out_node)
    check("C1 inspect_health", health.get("success"))
    check("C2 overall_ok", health.get("overall_ok"))
    
    orient = verify_orientation(out_node, [
        {"component_id": "base_box", "kind": "planar", "expected_axis": "Y", "signed": True},
        {"component_id": "pillar_copy", "kind": "planar", "expected_axis": "Y", "signed": True}
    ])
    check("C3 verify_orientation", orient.get("success"))
    check("C4 all passed", orient.get("passed",0) == orient.get("total",0))
    
    inv = geometry_inventory(out_node)
    check("C5 inventory", inv.get("success"))
    txt = inv.get("inventory_text","")
    check("C6 base_box present", "base_box" in txt)
    check("C7 pillar_copy present", "pillar_copy" in txt)

# ═══ Commit ═══
section("Commit")
if result.get("root_path"):
    cr = commit_sandbox(result["root_path"], "validation_test_result",
        orientation_checks=[
            {"component_id": "base_box", "kind": "planar", "expected_axis": "Y", "signed": True},
            {"component_id": "pillar_copy", "kind": "planar", "expected_axis": "Y", "signed": True}
        ])
    check("D1 commit", cr.get("success"), str(cr.get("error",""))[:200])
    check("D2 committed", bool(cr.get("final_path")))
    check("D3 orientation", cr.get("orientation",{}).get("passed_all",False))

print(f"\n{'='*60}\n  RESULTS: {PASS} passed, {FAIL} failed\n{'='*60}")
