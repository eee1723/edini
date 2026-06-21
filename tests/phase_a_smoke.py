"""Phase A Smoke Test — runs without Houdini."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python3.11libs"))
from edini.recipe_validator import validate_recipe

PASS = FAIL = 0

def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} -- {detail}")

print("=== Phase A Validation (pure Python, no catalog) ===")

# A1 — Schema
r = validate_recipe({"components": [{"id": "b", "backend": "native_chain", "nodes": [{"type": "box"}]}]})
check("A1: valid recipe", r["passed"])
r = validate_recipe({"components": [{"id": "b", "backend": "INVALID"}]})
check("A1: invalid backend caught", not r["passed"])

# A4 — VEX lint
r = validate_recipe({"components": [{"id": "f", "backend": "vex_skeleton", "code": 'float r = chf("%radius%");', "form_node": {"type": "sweep::2.0", "input0": "self"}}]})
check("A4: VEX %% caught", not r["passed"])
r = validate_recipe({"components": [{"id": "f", "backend": "vex_skeleton", "code": 'addprim(0, "poly");', "form_node": {"type": "sweep::2.0", "input0": "self"}}]})
check("A4: addprim poly caught", not r["passed"])
r = validate_recipe({"components": [{"id": "f", "backend": "vex_skeleton", "code": "void make_tube(vector pts[]; float r) { int pt = addpoint(0, pts[0]); }", "form_node": {"type": "sweep::2.0", "input0": "self"}}]})
check("A4: VEX function caught", not r["passed"])

# A5 — Construction axis
r = validate_recipe({"components": [{"id": "ring", "backend": "native_chain", "nodes": [{"type": "torus", "params": {"radscale": 0.1}}]}], "orientation_asserts": [{"component_id": "ring", "kind": "radial", "construction_axis": "Y", "expected_axis": "X", "tolerance_deg": 10}]})
check("A5: axis mismatch caught", not r["passed"])

# A6 — Dependency graph
r = validate_recipe({"components": [{"id": "b", "backend": "native_chain", "nodes": [{"type": "box"}]}], "params": {"A": {"kind": "derived", "from": "B+1", "default": 1}, "B": {"kind": "derived", "from": "A+1", "default": 2}}})
check("A6: cycle caught", not r["passed"])
r = validate_recipe({"components": [{"id": "b", "backend": "native_chain", "nodes": [{"type": "box"}]}], "params": {"A": {"kind": "derived", "from": "UNDECLARED+1", "default": 1}}})
check("A6: dangling ref caught", not r["passed"])
r = validate_recipe({"components": [{"id": "b", "backend": "native_chain", "nodes": [{"type": "box"}]}], "params": {"unused": {"kind": "primary", "default": 1}}})
check("A6: orphan warning", any("ORPHAN" in w["stage"] for w in r["warnings"]))

# Try with catalog if available
catalog_path = os.path.join(os.path.dirname(__file__), "..", "python3.11libs", "edini", "data", "parm-catalog.json")
if os.path.exists(catalog_path):
    print("\n=== With catalog ===")
    # Catalog-dependent checks (A2/A3) require `import hou` which is only
    # available inside Houdini runtime. Skip gracefully when running standalone.
    try:
        import hou
        _has_hou = True
    except ImportError:
        _has_hou = False
    if _has_hou:
        r = validate_recipe({"components": [{"id": "b", "backend": "native_chain", "nodes": [{"type": "torus", "params": {"nonexistent_xyz": 999}}]}]}, catalog_path)
        check("A2: bad parm on torus", not r["passed"])
        r = validate_recipe({"components": [{"id": "b", "backend": "vex_skeleton", "code": "int pts[] = make_polyline(0, array({0,0,0},{1,0,0}));", "form_node": {"type": "nonexistent_xyz", "input0": "self"}}]}, catalog_path)
        check("A3: invalid node nonexistent_xyz", not r["passed"])
    else:
        print("  [SKIP] A2/A3 require Houdini runtime (hou module not available)")
else:
    print("\n[SKIP] Catalog not found — A2/A3 tests require Houdini")
    print("  Run pipeline_e2e_validation.py in Houdini to generate catalog + full test.")

print(f"\n{'='*40}")
print(f"  {PASS} passed, {FAIL} failed")
print(f"{'='*40}")
sys.exit(0 if FAIL == 0 else 1)
