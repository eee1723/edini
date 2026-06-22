"""
Multi-component CTP end-to-end test (real Houdini only).

This complements pipeline_e2e_validation.py (which uses a minimal box+pillar)
by exercising the REAL user path: a templated component stamped onto multiple
anchors via Copy-to-Points. It was created after the tube-type bug (type:0
Primitive emitted 1 prim, CTP instances degenerated to points) slipped past
the minimal e2e. Run under hython:

    set EDINI_LIB_PATH=<repo>\python3.11libs
    "D:/houdini/bin/hython.exe" tests/multi_component_e2e.py
"""
import os
import sys

EDINI_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(EDINI_ROOT, "python3.11libs"))
for mod in list(sys.modules.keys()):
    if mod.startswith("edini."):
        del sys.modules[mod]
if "edini" in sys.modules:
    del sys.modules["edini"]

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        msg = f"  [FAIL] {name}"
        if detail:
            msg += f" -- {str(detail)[:200]}"
        print(msg)


def section(t):
    print(f"\n{'=' * 60}\n  {t}\n{'=' * 60}")


section("Multi-component CTP e2e (real Houdini)")

import hou  # noqa: E402
from edini.harness import build_procedural_asset, commit_sandbox  # noqa: E402
from edini.node_utils import (  # noqa: E402
    inspect_geometry_health, verify_orientation, geometry_inventory,
)

# Clean any previous run.
for n in ("table_ctp_e2e_final",):
    ex = hou.node(f"/obj/{n}")
    if ex:
        ex.destroy()

# A real table: desktop (direct-merge box) + 4 legs (templated tube via CTP).
# The tube uses the builder's default type=1 (Polygon); before the fix this
# would have emitted 1 prim and the legs would vanish.
recipe = {
    "asset_name": "table_ctp_e2e",
    "components": [
        {"id": "top", "backend": "native_chain",
         "nodes": [{"type": "box", "params": {"size": [1.2, 0.05, 0.7]}},
                   {"type": "attribwrangle",
                    "params": {"class": "primitive",
                               "snippet": "s@component_id = 'top';"}}]},
        {"id": "leg", "backend": "native_chain",
         "nodes": [{"type": "tube",
                    "params": {"rad": [0.03, 0.03], "height": 0.7,
                               "rows": 2, "cols": 12}},
                   {"type": "attribwrangle",
                    "params": {"class": "primitive",
                               "snippet": "s@component_id = 'leg';"}}],
         "anchors": [
             {"position": [0.55, -0.35, 0.30], "orient": [0, 0, 0, 1],
              "pscale": 1.0, "component_id": "leg_fl"},
             {"position": [-0.55, -0.35, 0.30], "orient": [0, 0, 0, 1],
              "pscale": 1.0, "component_id": "leg_fr"},
             {"position": [0.55, -0.35, -0.30], "orient": [0, 0, 0, 1],
              "pscale": 1.0, "component_id": "leg_bl"},
             {"position": [-0.55, -0.35, -0.30], "orient": [0, 0, 0, 1],
              "pscale": 1.0, "component_id": "leg_br"},
         ]},
    ],
    "postprocess": [{"type": "fuse", "params": {"dist": 0.0001}},
                    {"type": "clean"},
                    {"type": "normal", "params": {"cuspangle": 60}}],
    "orientation_asserts": [
        {"component_id": "leg_fl", "kind": "elongated",
         "expected_axis": "Y", "construction_axis": "Y", "tolerance_deg": 15},
        {"component_id": "top", "kind": "planar", "expected_axis": "Y",
         "signed": True, "construction_axis": "Y", "tolerance_deg": 15},
    ],
}

section("Build")
b = build_procedural_asset(recipe)
check("B1 build success", b.get("success"), b.get("error", ""))
check("B2 output_node", bool(b.get("output_node")))
check("B3 no missing ids",
      not b.get("component_id_check", {}).get("missing"))

if b.get("success"):
    section("Geometry integrity (the tube-type regression check)")
    inv = geometry_inventory(b["output_node"])
    comps = inv.get("components", inv) if isinstance(inv, dict) else inv
    if isinstance(comps, dict):
        comps = list(comps.values())
    by_id = {c["component_id"]: c for c in comps}
    # Each leg must have real polygon geometry (cols=12 → ~24+ prims for
    # rows=2). type:0 would give prim_count=1 — the regression.
    for leg in ("leg_fl", "leg_fr", "leg_bl", "leg_br"):
        c = by_id.get(leg)
        check(f"C1 {leg} has polygon geometry (>1 prim)",
              c is not None and c.get("prim_count", 0) > 1,
              c)
    # No instance should have a zero-size bbox (degenerate point).
    zero_size = [cid for cid, c in by_id.items()
                 if max(c.get("bounds", {}).get("size", [1, 1, 1])) < 1e-6]
    check("C2 no degenerate (zero-size) instances", not zero_size, zero_size)

    section("Verification layers")
    h = inspect_geometry_health(b["output_node"])
    check("D1 health overall_ok", h.get("overall_ok"), h)
    o = verify_orientation(b["output_node"], recipe["orientation_asserts"])
    check("D2 orientation all passed",
          o.get("failed", 1) == 0, o)

    section("G3 commit + receipt")
    c = commit_sandbox(b["root_path"], "table_ctp_e2e_final",
                       replace_existing=False,
                       orientation_checks=recipe["orientation_asserts"])
    check("E1 committed", c.get("committed"), c.get("error", ""))
    rcpt = c.get("verification_receipt", {})
    check("E2 receipt present", bool(rcpt))
    check("E3 receipt.passed", rcpt.get("passed") is True, rcpt.get("passed"))
    check("E4 receipt hard_errors==0",
          rcpt.get("health", {}).get("hard_errors_count") == 0,
          rcpt.get("health", {}).get("hard_errors_count"))
    check("E5 components_detected has all 5",
          set(rcpt.get("components_detected", [])) ==
          {"top", "leg_fl", "leg_fr", "leg_bl", "leg_br"},
          rcpt.get("components_detected"))

# Cleanup the committed asset.
ex = hou.node("/obj/table_ctp_e2e_final")
if ex:
    ex.destroy()

print(f"\n{'=' * 60}\n  RESULTS: {PASS} passed, {FAIL} failed\n{'=' * 60}")
sys.exit(1 if FAIL else 0)
