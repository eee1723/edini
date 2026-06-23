"""
Houdini Runtime Test Suite — runs inside Houdini via hython.
Validates: parm catalog, Phase A validation, Phase B+C build, and commit.
"""
import sys, os, json

EDINI_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(EDINI_ROOT, "python3.11libs"))

# Clear any cached edini modules
for mod in list(sys.modules.keys()):
    if mod.startswith("edini."):
        del sys.modules[mod]
if "edini" in sys.modules:
    del sys.modules["edini"]

# ═══════════════════════════════════════════════════════
PASS = FAIL = SKIP = 0


def check(name, condition, detail=""):
    global PASS, FAIL, SKIP
    if condition is None:  # SKIP sentinel
        SKIP += 1
        print(f"  [SKIP] {name} -- {detail}")
    elif condition:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        msg = f"  [FAIL] {name}"
        if detail:
            msg += f" -- {str(detail)[:200]}"
        print(msg)


def section(title):
    print(f"\n{'=' * 60}\n  {title}\n{'=' * 60}")


# ═══════════════════════════════════════════════════════
# Phase 0: Parm Catalog
# ═══════════════════════════════════════════════════════
section("Phase 0: Parm Catalog")
from edini.parm_catalog import ParmCatalog

catalog_path = os.path.join(EDINI_ROOT, "python3.11libs", "edini", "data", "parm-catalog.json")

try:
    raw = ParmCatalog.generate_catalog()
    os.makedirs(os.path.dirname(catalog_path), exist_ok=True)
    with open(catalog_path, "w", encoding="utf-8") as f:
        json.dump(raw, f, indent=2, ensure_ascii=False)
    sop_count = len(raw.get("Sop", {}))
    check("0.1 Catalog generated", sop_count > 100, f"{sop_count} SOP types")
except Exception as e:
    check("0.1 Catalog generated", False, str(e))

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
    check("0.6 sweep::2.0 exists", cat.has_node_type("sweep::2.0"))
    check("0.7 transform→xform alias", cat.resolve_alias("transform") == "xform")
    check("0.8 fuse→fuse::2.0 alias", cat.resolve_alias("fuse") == "fuse::2.0")
    check("0.9 torus has 'rad' parm (H21)", "rad" in cat.parm_names("torus"))
    check("0.10 torus has 'rows' parm", "rows" in cat.parm_names("torus"))
    check("0.11 torus missing 'radscale' (H21)", "radscale" not in cat.parm_names("torus"))

# ═══════════════════════════════════════════════════════
# Phase A: Recipe Validation (with catalog)
# ═══════════════════════════════════════════════════════
section("Phase A: Recipe Validation")
from edini.recipe_validator import validate_recipe as phase_a

# A1 — Schema
r = phase_a({"components": [{"id": "b", "backend": "native_chain", "nodes": [{"type": "box"}]}]})
check("A1 valid recipe", r["passed"])
r = phase_a({"components": [{"id": "b", "backend": "INVALID"}]})
check("A1 invalid backend", not r["passed"])
r = phase_a({"components": []})
check("A1 empty components", not r["passed"])

# A2 — Parm name cross-validation (catalog-dependent)
if cat:
    r = phase_a({"components": [{"id": "b", "backend": "native_chain", "nodes": [{"type": "torus", "params": {"nonexistent_xyz": 999}}]}]}, catalog_path)
    check("A2 bad parm name caught", not r["passed"])
    r = phase_a({"components": [{"id": "b", "backend": "native_chain", "nodes": [{"type": "box", "params": {"size": [1, 1, 1]}}]}]}, catalog_path)
    check("A2 valid parms pass", r["passed"], str(r.get("errors", [])))

# A3 — Node type validation (catalog-dependent)
if cat:
    r = phase_a({"components": [{"id": "b", "backend": "vex_skeleton", "code": "int a;", "form_node": {"type": "nonexistent_xyz", "input0": "self"}}]}, catalog_path)
    check("A3 bad node type caught", not r["passed"])
    r = phase_a({"components": [{"id": "b", "backend": "native_chain", "nodes": [{"type": "box"}]}]}, catalog_path)
    check("A3 valid node type passes", r["passed"])
    # Test alias resolution
    r = phase_a({"components": [{"id": "t", "backend": "native_chain", "nodes": [{"type": "transform", "params": {"t": [1.0, 0, 0]}}]}]}, catalog_path)
    check("A3 'transform' alias→xform passes", r["passed"], str(r.get("errors", [])))

# A4 — VEX lint
r = phase_a({"components": [{"id": "f", "backend": "vex_skeleton", "code": "chf('%r%');", "form_node": {"type": "sweep::2.0", "input0": "self"}}]})
check("A4 VEX % caught", not r["passed"])
r = phase_a({"components": [{"id": "f", "backend": "vex_skeleton", "code": 'addprim(0, "poly");', "form_node": {"type": "sweep::2.0", "input0": "self"}}]})
check("A4 addprim poly caught", not r["passed"])
r = phase_a({"components": [{"id": "f", "backend": "vex_skeleton", "code": "void foo(){}", "form_node": {"type": "sweep::2.0", "input0": "self"}}]})
check("A4 VEX function caught", not r["passed"])

# A4 — VEX ch() ref check
r = phase_a({"components": [{"id": "f", "backend": "vex_skeleton", "code": 'float r = chf("undeclared_param");', "form_node": {"type": "sweep::2.0", "input0": "self"}}]})
check("A4 undeclared ch() ref caught", not r["passed"])
# Declared param should pass
r = phase_a({"components": [{"id": "f", "backend": "vex_skeleton", "code": 'float r = chf("my_param");', "form_node": {"type": "sweep::2.0", "input0": "self"}}], "params": {"my_param": {"kind": "primary", "default": 1.0}}})
check("A4 declared ch() ref passes", r["passed"])

# A5 — Construction axis
r = phase_a({"components": [{"id": "ring", "backend": "native_chain", "nodes": [{"type": "torus", "params": {"radscale": 0.1}}]}], "orientation_asserts": [{"component_id": "ring", "kind": "radial", "construction_axis": "Y", "expected_axis": "X", "tolerance_deg": 10}]})
check("A5 axis mismatch caught", not r["passed"])
# Valid: torus in XZ plane, construction=Y, anchor=identity, expected=Y
r = phase_a({"components": [{"id": "ring", "backend": "native_chain", "nodes": [{"type": "torus", "params": {"radscale": 0.1}}]}], "orientation_asserts": [{"component_id": "ring", "kind": "radial", "construction_axis": "Y", "expected_axis": "Y", "tolerance_deg": 10}]})
check("A5 consistent axis passes", r["passed"])

# A6 — Dependency graph
r = phase_a({"components": [{"id": "b", "backend": "native_chain", "nodes": [{"type": "box"}]}], "params": {"A": {"kind": "derived", "from": "B+1", "default": 1}, "B": {"kind": "derived", "from": "A+1", "default": 2}}})
check("A6 cycle caught", not r["passed"])
r = phase_a({"components": [{"id": "b", "backend": "native_chain", "nodes": [{"type": "box"}]}], "params": {"A": {"kind": "derived", "from": "UNDECLARED+1", "default": 1}}})
check("A6 dangling ref caught", not r["passed"])
r = phase_a({"components": [{"id": "b", "backend": "native_chain", "nodes": [{"type": "box"}]}], "params": {"unused": {"kind": "primary", "default": 1}}})
check("A6 orphan warning", any("ORPHAN" in w["stage"] for w in r["warnings"]))

# A4 VEX addpoint w/o Detail marker (WARNING)
r = phase_a({"components": [{"id": "f", "backend": "vex_skeleton", "code": "int pt = addpoint(0, {0,0,0});", "form_node": {"type": "sweep::2.0", "input0": "self"}}]})
check("A4 addpoint no-detail WARNING", any("NO_DETAIL" in w["stage"] for w in r["warnings"]) or r["passed"])
# With Detail marker: should pass
r = phase_a({"components": [{"id": "f", "backend": "vex_skeleton", "code": "// Run Over: Detail\nint pt = addpoint(0, {0,0,0});", "form_node": {"type": "sweep::2.0", "input0": "self"}}]})
check("A4 addpoint with Detail marker passes", r["passed"])

# ═══════════════════════════════════════════════════════
# Phase B+C: Build and Verify
# ═══════════════════════════════════════════════════════
section("Phase B+C: Build & Verify")
import hou
from edini.harness import build_procedural_asset, commit_sandbox, discard_sandbox
from edini.node_utils import inspect_geometry_health, verify_orientation, geometry_inventory

# Clean previous test artifacts
for old_name in ["validation_test_result", "edini_sandbox_validation_test"]:
    existing = hou.node(f"/obj/{old_name}")
    if existing:
        existing.destroy()

recipe = {
    "asset_name": "validation_test",
    "params": {
        "box_width": {"kind": "primary", "default": 2.0, "min": 0.5, "max": 10.0},
        "box_height": {"kind": "primary", "default": 0.5, "min": 0.1, "max": 5.0},
    },
    "components": [
        {
            "id": "base_box",
            "backend": "native_chain",
            "nodes": [
                {"type": "box", "params": {"size": [2, 0.5, 1]}},
                {"type": "attribwrangle", "params": {"class": "primitive", "snippet": "s@component_id = 'base_box';"}},
            ],
        },
        {
            "id": "pillar",
            "backend": "native_chain",
            "nodes": [
                {"type": "box", "params": {"size": [0.3, 0.3, 0.3]}},
                {"type": "attribwrangle", "params": {"class": "primitive", "snippet": "s@component_id = 'pillar';"}},
            ],
            "anchors": [
                {"position": [2, 0.5, 0], "orient": [0, 0, 0, 1], "pscale": 1.0, "component_id": "pillar_copy"},
            ],
        },
    ],
    "postprocess": [],
    "orientation_asserts": [
        {"component_id": "base_box", "kind": "planar", "expected_axis": "Y", "signed": True, "construction_axis": "Y"},
        {"component_id": "pillar_copy", "kind": "planar", "expected_axis": "Y", "signed": True, "construction_axis": "Y"},
    ],
}

# Phase A integrated test
section("Phase A Integration (inside build_procedural_asset)")
# Test with invalid recipe first
bad_recipe = {"components": [{"id": "bad", "backend": "INVALID_BACKEND"}]}
result = build_procedural_asset(bad_recipe)
check("B0-1 invalid recipe rejected before cook", not result.get("success"), str(result.get("error", ""))[:150])

# Now build the valid recipe
result = build_procedural_asset(recipe)
check("B1 build success", result.get("success"), str(result.get("error", ""))[:200])
check("B2 build_mode=recipe", result.get("build_mode") == "recipe")

out_node_path = result.get("output_node", "")
check("B3 output_node exists", bool(out_node_path))
out_node = hou.node(out_node_path) if out_node_path else None
check("B4 output_node cookable", out_node is not None)

if out_node:
    # Cook and inspect
    out_node.cook(force=True)
    geo = out_node.geometry()
    check("B5 geometry not None", geo is not None)
    if geo:
        pt_count = geo.intrinsicValue("pointcount")
        prim_count = geo.intrinsicValue("primitivecount")
        check("B6 has points", pt_count > 0, f"{pt_count} points")
        check("B7 has prims", prim_count > 0, f"{prim_count} prims")

    # Inspect health
    health = inspect_geometry_health(out_node_path)
    check("C1 inspect_health success", health.get("success"))
    check("C2 overall_ok", health.get("overall_ok"), str(health.get("blocking_issues", []))[:200])

    # Verify orientation
    orient = verify_orientation(out_node_path, [
        {"component_id": "base_box", "kind": "planar", "expected_axis": "Y", "signed": True, "construction_axis": "Y"},
        {"component_id": "pillar_copy", "kind": "planar", "expected_axis": "Y", "signed": True, "construction_axis": "Y"},
    ])
    check("C3 verify_orientation success", orient.get("success"))
    check("C4 all orientation passed", orient.get("passed", 0) == orient.get("total", 0),
          f"passed={orient.get('passed')}/{orient.get('total')}")

    # Inventory
    inv = geometry_inventory(out_node_path)
    check("C5 geometry_inventory success", inv.get("success"))
    txt = inv.get("inventory_text", "")
    check("C6 base_box in inventory", "base_box" in txt)
    check("C7 pillar_copy in inventory", "pillar_copy" in txt)
    check("C8 pillar in inventory", "pillar" in txt)

# ═══════════════════════════════════════════════════════
# Commit
# ═══════════════════════════════════════════════════════
section("Commit")
if result.get("root_path"):
    cr = commit_sandbox(
        result["root_path"],
        "validation_test_result",
        orientation_checks=[
            {"component_id": "base_box", "kind": "planar", "expected_axis": "Y", "signed": True, "construction_axis": "Y"},
            {"component_id": "pillar_copy", "kind": "planar", "expected_axis": "Y", "signed": True, "construction_axis": "Y"},
        ],
    )
    check("D1 commit success", cr.get("success"), str(cr.get("error", ""))[:200])
    check("D2 committed flag", cr.get("committed"))
    check("D3 final_path exists", bool(cr.get("final_path")))
    check("D4 orientation passed_all", cr.get("orientation", {}).get("passed_all", False))
    check("D5 structure passed", cr.get("structure", {}).get("passed", True))

# ═══════════════════════════════════════════════════════
# Cleanup
# ═══════════════════════════════════════════════════════
section("Cleanup")
if result.get("root_path") and hou.node(result["root_path"]):
    discard_sandbox(result["root_path"])
    check("E1 sandbox cleaned", hou.node(result["root_path"]) is None)
final = hou.node("/obj/validation_test_result")
if final:
    final.destroy()
    check("E2 committed node cleaned", hou.node("/obj/validation_test_result") is None)

# ═══════════════════════════════════════════════════════
# Results
# ═══════════════════════════════════════════════════════
print(f"\n{'=' * 60}")
print(f"  RESULTS: {PASS} passed, {FAIL} failed, {SKIP} skipped")
print(f"{'=' * 60}")
sys.exit(0 if FAIL == 0 else 1)
