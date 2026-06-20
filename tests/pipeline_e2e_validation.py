"""
Edini Pipeline Architecture — End-to-End Validation Script
===========================================================
Run in Houdini Python Shell (Window > Python Shell).
Tests all 4 phases of the pipeline without Agent involvement.
"""

import json, os, sys, traceback

# ── Setup ──────────────────────────────────────────────────
EDINI_ROOT = r"Z:\EEE_Project\Edini"
sys.path.insert(0, os.path.join(EDINI_ROOT, "python3.11libs"))

PASS = 0
FAIL = 0
_results = []

def check(name: str, condition: bool, detail: str = ""):
    global PASS, FAIL
    if condition:
        PASS += 1
        _results.append(f"  [PASS] {name}")
    else:
        FAIL += 1
        _results.append(f"  [FAIL] {name} — {detail}")

def section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

def report():
    print(f"\n{'='*60}")
    print(f"  RESULTS: {PASS} passed, {FAIL} failed")
    print(f"{'='*60}")
    for r in _results:
        print(r)
    print()

# ═══════════════════════════════════════════════════════════
#  PHASE 0: PARM CATALOG
# ═══════════════════════════════════════════════════════════
section("Phase 0: Parm Catalog")

from edini.parm_catalog import ParmCatalog

catalog_path = os.path.join(EDINI_ROOT, "python3.11libs", "edini", "data", "parm-catalog.json")

# 0.1 — Generate catalog
try:
    raw = ParmCatalog.generate_catalog()
    os.makedirs(os.path.dirname(catalog_path), exist_ok=True)
    with open(catalog_path, "w", encoding="utf-8") as f:
        json.dump(raw, f, indent=2, ensure_ascii=False)
    sop_count = len(raw.get("Sop", {}))
    check("0.1 Catalog generated", sop_count > 100, f"{sop_count} SOP types")
except Exception as e:
    check("0.1 Catalog generated", False, str(e))

# 0.2 — Load catalog
try:
    cat = ParmCatalog.load(catalog_path)
    check("0.2 Catalog loaded", cat is not None)
except Exception as e:
    check("0.2 Catalog loaded", False, str(e))
    cat = None

# 0.3 — Key SOP types exist
if cat:
    check("0.3 torus exists", cat.has_node_type("torus"))
    check("0.4 tube exists", cat.has_node_type("tube"))
    check("0.5 xform exists", cat.has_node_type("xform"))
    check("0.6 sweep::2.0 exists", cat.has_node_type("sweep::2.0"))
    check("0.7 attribcreate exists", cat.has_node_type("attribcreate"))

# 0.4 — Parm name validation
if cat:
    check("0.8 torus has radscale (not rad)", "radscale" in cat.parm_names("torus"))
    check("0.9 torus lacks rad", "rad" not in cat.parm_names("torus"))
    check("0.10 tube has rad", "rad" in cat.parm_names("tube"))

# 0.5 — Alias resolution
if cat:
    check("0.11 transform→xform", cat.resolve_alias("transform") == "xform")
    check("0.12 polybevel→polybevel::3.0", cat.resolve_alias("polybevel") == "polybevel::3.0")

# ═══════════════════════════════════════════════════════════
#  PHASE A: RECIPE VALIDATION
# ═══════════════════════════════════════════════════════════
section("Phase A: Recipe Validation")

from edini.recipe_validator import validate_recipe as phase_a_validate

# A1 — Valid minimal recipe
r = phase_a_validate({
    "components": [{"id": "box", "backend": "native_chain",
                    "nodes": [{"type": "box"}]}]
}, catalog_path)
check("A1 valid recipe passes", r["passed"], str(r.get("errors", [])))

# A2 — Bad parm name (must have catalog)
if cat:
    r = phase_a_validate({
        "components": [{"id": "bad", "backend": "native_chain",
                        "nodes": [{"type": "torus", "params": {"rad": [0.08, 0.08]}}]}]
    }, catalog_path)
    check("A2 bad parm 'rad' on torus", not r["passed"], str(r.get("errors", [])))

# A3 — Invalid node type
if cat:
    r = phase_a_validate({
        "components": [{"id": "bad", "backend": "vex_skeleton",
                        "code": "int pts[] = make_polyline(0, array({0,0,0},{1,0,0}));",
                        "form_node": {"type": "transform", "input0": "self"}}]
    }, catalog_path)
    check("A3 invalid node 'transform'", not r["passed"], str(r.get("errors", [])))

# A4 — VEX percent
r = phase_a_validate({
    "components": [{"id": "f", "backend": "vex_skeleton",
                    "code": "float r = chf(\"%radius%\");",
                    "form_node": {"type": "sweep::2.0", "input0": "self"}}]
})
check("A4 VEX %percent%", not r["passed"],
      f"errors: {[e['stage'] for e in r['errors']]}")

# A4 — VEX function definition
r = phase_a_validate({
    "components": [{"id": "f", "backend": "vex_skeleton",
                    "code": "void make_tube(vector pts[]; float r) {\n    int pt = addpoint(0, pts[0]);\n}",
                    "form_node": {"type": "sweep::2.0", "input0": "self"}}]
})
check("A4 VEX function definition", not r["passed"],
      f"errors: {[e['stage'] for e in r['errors']]}")

# A5 — Construction axis mismatch
r = phase_a_validate({
    "components": [{"id": "ring", "backend": "native_chain",
                    "nodes": [{"type": "torus", "params": {"radscale": 0.1}}]}],
    "orientation_asserts": [{"component_id": "ring", "kind": "radial",
                              "construction_axis": "Y", "expected_axis": "X",
                              "tolerance_deg": 10}]
})
check("A5 construction axis mismatch", not r["passed"],
      f"errors: {[e['stage'] for e in r['errors']]}")

# A6 — Dependency cycle
r = phase_a_validate({
    "components": [{"id": "box", "backend": "native_chain",
                    "nodes": [{"type": "box"}]}],
    "params": {"A": {"kind": "derived", "from": "B + 1", "default": 1},
               "B": {"kind": "derived", "from": "A + 1", "default": 2}}
})
check("A6 dependency cycle", not r["passed"],
      f"errors: {[e['stage'] for e in r['errors']]}")

# ═══════════════════════════════════════════════════════════
#  PHASE B+C: BUILD A SIMPLE ASSET
# ═══════════════════════════════════════════════════════════
section("Phase B+C: Build Simple Asset")

from edini.harness import build_procedural_asset, commit_sandbox, discard_sandbox
import hou

# Test recipe: a simple box + anchored sphere
simple_recipe = {
    "asset_name": "validation_test",
    "components": [
        {
            "id": "base_box",
            "backend": "native_chain",
            "nodes": [
                {"type": "box", "params": {"sizex": 2, "sizey": 0.5, "sizez": 1}},
                {"type": "attribcreate", "name": "tag",
                 "params": {"name1": "component_id", "class1": "primitive",
                            "type1": "string", "string1": "base_box"}}
            ]
        },
        {
            "id": "sphere_top",
            "backend": "native_chain",
            "nodes": [
                {"type": "tube", "params": {"rad": [0.15, 0.12], "height": 0.3,
                                             "rows": 3, "cols": 16}},
                {"type": "attribcreate", "name": "tag",
                 "params": {"name1": "component_id", "class1": "primitive",
                            "type1": "string", "string1": "sphere_top"}}
            ],
            "anchors": [
                {"position": [0, 0.5, 0], "orient": [0, 0, 0, 1],
                 "pscale": 1.0, "component_id": "pillar_center"}
            ]
        }
    ],
    "postprocess": [
        {"type": "fuse"},
        {"type": "clean"},
        {"type": "normal", "params": {"cuspangle": 60}}
    ],
    "orientation_asserts": [
        {"component_id": "base_box", "kind": "planar", "expected_axis": "Y",
         "signed": True, "tolerance_deg": 15},
        {"component_id": "pillar_center", "kind": "elongated", "expected_axis": "Y",
         "construction_axis": "Y", "tolerance_deg": 15}
    ]
}

# B1 — Build asset
try:
    result = build_procedural_asset(simple_recipe)
    check("B1 build_procedural_asset success", result.get("success", False),
          result.get("error", ""))
    sandbox_root = result.get("root_path", "")
    out_node = result.get("output_node", "")
    check("B2 output_node exists", bool(out_node), out_node)
    check("B3 has geometry", result.get("structural_checks", {}).get("has_geometry", False))
    print(f"  Point count: {result.get('structural_checks',{}).get('point_count','?')}")
except Exception as e:
    check("B1 build attempt", False, str(e))
    sandbox_root = ""
    out_node = ""

# ═══════════════════════════════════════════════════════════
#  VERIFICATION
# ═══════════════════════════════════════════════════════════
section("Verification Tools")

from edini.node_utils import inspect_geometry_health, verify_orientation, geometry_inventory

if out_node:
    # C1 — Health check
    try:
        health = inspect_geometry_health(out_node)
        check("C1 inspect_health", health.get("success", False))
        check("C2 overall_ok", health.get("overall_ok", False))
        print(f"  Points: {health.get('point_count')}, Prims: {health.get('prim_count')}")
        print(f"  Orphans: {health.get('summary',{}).get('orphan_points')}, "
              f"Non-manifold: {health.get('summary',{}).get('nonmanifold_edges')}")
    except Exception as e:
        check("C1 inspect_health", False, str(e))

    # C3 — Orientation
    try:
        orient = verify_orientation(out_node, [
            {"component_id": "base_box", "kind": "planar", "expected_axis": "Y",
             "signed": True, "tolerance_deg": 15},
            {"component_id": "pillar_center", "kind": "elongated", "expected_axis": "Y",
             "construction_axis": "Y", "tolerance_deg": 15}
        ])
        check("C3 verify_orientation success", orient.get("success", False))
        check("C4 all passed", orient.get("passed", 0) == orient.get("total", 0),
              f"{orient.get('passed')}/{orient.get('total')}")
    except Exception as e:
        check("C3 verify_orientation", False, str(e))

    # C5 — Inventory
    try:
        inv = geometry_inventory(out_node)
        check("C5 geometry_inventory success", inv.get("success", False))
        # Check component_ids exist
        text = inv.get("inventory_text", "")
        has_box = "base_box" in text
        has_pillar = "pillar_center" in text
        check("C6 base_box in inventory", has_box)
        check("C7 pillar_center in inventory", has_pillar)
    except Exception as e:
        check("C5 geometry_inventory", False, str(e))

# ═══════════════════════════════════════════════════════════
#  COMMIT
# ═══════════════════════════════════════════════════════════
section("Commit")

if sandbox_root:
    try:
        commit_result = commit_sandbox(
            sandbox_root_path=sandbox_root,
            final_name="validation_test_result",
            orientation_checks=[
                {"component_id": "base_box", "kind": "planar", "expected_axis": "Y",
                 "signed": True, "tolerance_deg": 15},
                {"component_id": "pillar_center", "kind": "elongated", "expected_axis": "Y",
                 "construction_axis": "Y", "tolerance_deg": 15}
            ]
        )
        check("D1 commit success", commit_result.get("success", False),
              commit_result.get("error", ""))
        check("D2 committed path", bool(commit_result.get("final_path")),
              commit_result.get("final_path", ""))
        check("D3 orientation all passed",
              commit_result.get("orientation", {}).get("passed_all", False))
    except Exception as e:
        check("D1 commit", False, str(e))

# ═══════════════════════════════════════════════════════════
#  REPORT
# ═══════════════════════════════════════════════════════════
report()
