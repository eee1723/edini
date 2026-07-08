"""End-to-end validation that the rewritten project-modeling SKILL.md workflow
is executable under real hython, AND that each completion criterion stated in
the skill is machine-checkable (not aspirational prose).

This is the "does the skill's contract hold?" test. It does NOT test agent
behavior (that needs a live Pi session). It tests that the DETERMINISTIC path
the skill prescribes actually works end-to-end, including design_params +
project_add_anchors (the additions the rewrite emphasizes), and that every
"Done when" criterion is checkable.

Run: py -3 -m pytest tests/test_skill_workflow_hython.py -v -s
"""
import json
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python3.11libs"))

from _hython import HYTHON  # noqa: E402  (shared discovery; conftest reports availability)

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# The harness mirrors the SKILL.md 4-step workflow exactly. __REPO__ is the
# single injection point (avoids %-format and {} collisions with VEX/Python).
_HARNESS = r'''
import json, sys, os, traceback
sys.path.insert(0, os.path.join(r"__REPO__", "python3.11libs"))
import hou

_hda = os.path.join(r"__REPO__", "otls", "edini_project.hda")
if os.path.isfile(_hda):
    hou.hda.installFile(_hda)

from edini.project.state import empty_declaration, add_component, save_declaration
from edini.project.node import create_project_hda
from edini.project.builder import build_project_scaffold, promote_params
from edini.project.ports import (OUT_GEOMETRY_NODE, OUT_ANCHORS_NODE,
                                 OUTPUT_0_NODE, OUTPUT_1_NODE)
from edini.tool_executor import _project_add_anchors, _project_build_scaffold

result = {"steps": {}, "criteria": {}}

# ============================================================
# STEP 1: project_create  ->  core_path returned
# ============================================================
core = create_project_hda(name="skill_test")
core_path = core.path()
result["steps"]["s1_core_path"] = core_path
result["criteria"]["c1_core_path_valid"] = hou.node(core_path) is not None

# ============================================================
# STEP 2: project_build_scaffold with components + design_params
#         (the tool-handler layer handles design_params -> declaration)
# ============================================================
res = _project_build_scaffold(
    core_path=core_path,
    components=[
        {"id": "tabletop", "purpose": "desktop, emits leg anchors",
         "ports": {"out": [
             {"index": 0, "kind": "geometry", "description": "desktop"},
             {"index": 1, "kind": "anchors", "points": [
                 {"name": "leg_fr", "role": "mount"},
                 {"name": "leg_fl", "role": "mount"},
                 {"name": "leg_br", "role": "mount"},
                 {"name": "leg_bl", "role": "mount"}]}]}},
        {"id": "legs", "purpose": "4 legs consuming tabletop anchors",
         "ports": {"out": [{"index": 0, "kind": "geometry"}],
                   "in": [
                       {"from": "tabletop", "port": 1, "anchor": "leg_fr"},
                       {"from": "tabletop", "port": 1, "anchor": "leg_fl"},
                       {"from": "tabletop", "port": 1, "anchor": "leg_br"},
                       {"from": "tabletop", "port": 1, "anchor": "leg_bl"}]}},
    ],
    design_params=[
        {"name": "length", "label": "len", "default": 1.2, "min": 0.4, "max": 3.0},
        {"name": "width", "label": "wid", "default": 0.6, "min": 0.3, "max": 1.5},
    ])
result["steps"]["s2_scaffold"] = str(res)

tabletop = core.node("tabletop")
legs = core.node("legs")
result["criteria"]["c2_tabletop_subnet"] = tabletop is not None
result["criteria"]["c2_legs_subnet"] = legs is not None
in_nodes = [n.name() for n in legs.children() if n.name().startswith("in_tabletop_")]
result["criteria"]["c2_in_ports_wired"] = sorted(in_nodes) == sorted(
    ["in_tabletop_leg_fr", "in_tabletop_leg_fl", "in_tabletop_leg_br", "in_tabletop_leg_bl"])
length_parm = core.parm("length")
width_parm = core.parm("width")
result["criteria"]["c2_design_param_length"] = length_parm is not None
result["criteria"]["c2_design_param_width"] = width_parm is not None

# ============================================================
# STEP 3: model inside tabletop + project_add_anchors (measure!)
# ============================================================
box = tabletop.createNode("box", "desktop_box")
box.parm("sizex").setExpression('ch("' + core_path + '/length")')
box.parm("sizez").setExpression('ch("' + core_path + '/width")')
box.parm("sizey").set(0.05)
tabletop.node(OUT_GEOMETRY_NODE).setInput(0, box)

anchor_res = _project_add_anchors(
    core_path=core_path,
    component_id="tabletop",
    anchors=[
        {"measure": "bbox_corner", "axes": "+X-Y+Z", "name": "leg_fr"},
        {"measure": "bbox_corner", "axes": "-X-Y+Z", "name": "leg_fl"},
        {"measure": "bbox_corner", "axes": "+X-Y-Z", "name": "leg_br"},
        {"measure": "bbox_corner", "axes": "-X-Y-Z", "name": "leg_bl"},
    ])
result["steps"]["s3_anchors"] = str(anchor_res)

tabletop_out_geo = tabletop.node(OUTPUT_0_NODE).geometry()
result["criteria"]["c3_tabletop_has_geometry"] = tabletop_out_geo is not None

anchor_out_geo = tabletop.node(OUTPUT_1_NODE).geometry()
anchor_points = anchor_out_geo.points() if anchor_out_geo else []
emitted_names = set()
for p in anchor_points:
    try:
        emitted_names.add(p.stringAttribValue("name"))
    except Exception:
        pass
declared_names = {"leg_fr", "leg_fl", "leg_br", "leg_bl"}
result["criteria"]["c3_all_anchors_emitted"] = declared_names.issubset(emitted_names)
result["steps"]["s3_emitted_anchor_names"] = sorted(emitted_names)

# CRITERION 3c: anchors are LIVE (measured, not hardcoded)
# Change length -> bbox changes -> anchor X should move.
try:
    fr_before = None
    for p in anchor_points:
        try:
            if p.stringAttribValue("name") == "leg_fr":
                fr_before = p.position().x()
        except Exception:
            pass
    core.parm("length").set(2.4)
    core.cook(force=True)
    anchor_out_geo2 = tabletop.node(OUTPUT_1_NODE).geometry()
    fr_after = None
    for p in anchor_out_geo2.points():
        try:
            if p.stringAttribValue("name") == "leg_fr":
                fr_after = p.position().x()
        except Exception:
            pass
    result["criteria"]["c3_anchors_are_live"] = (
        fr_before is not None and fr_after is not None and abs(fr_after - fr_before) > 0.01)
    result["steps"]["s3_fr_before"] = fr_before
    result["steps"]["s3_fr_after"] = fr_after
except Exception:
    result["criteria"]["c3_anchors_are_live"] = False
    result["steps"]["s3_live_error"] = traceback.format_exc().splitlines()[-1]

core.parm("length").set(1.2)

# ============================================================
# STEP 4: project_promote_params  ->  LIVE guarantee
# ============================================================
try:
    tmpl = hou.FloatParmTemplate("thick", "Thick", 1, (0.04,))
    tabletop.addSpareParmTuple(tmpl, in_folder=("Design",), create_missing_folders=True)
except Exception:
    pass
promote_res = promote_params(core)
result["steps"]["s4_promote"] = str(promote_res)

try:
    promoted = core.parm("tabletop_thick")
    if promoted is not None:
        subnet_parm = tabletop.parm("thick")
        expr = subnet_parm.expression() if subnet_parm else None
        result["criteria"]["c4_promoted_parm_exists"] = True
        result["criteria"]["c4_subnet_follows_core"] = expr is not None and "tabletop_thick" in str(expr)
        result["steps"]["s4_subnet_expr"] = str(expr)
        promoted.set(0.08)
        result["criteria"]["c4_live_change_propagates"] = abs(subnet_parm.eval() - 0.08) < 0.001
        result["steps"]["s4_subnet_eval_after"] = subnet_parm.eval()
    else:
        result["criteria"]["c4_promoted_parm_exists"] = False
        result["criteria"]["c4_subnet_follows_core"] = False
        result["criteria"]["c4_live_change_propagates"] = False
except Exception:
    result["criteria"]["c4_live_change_propagates"] = False
    result["steps"]["s4_error"] = traceback.format_exc().splitlines()[-1]

print("RESULT_JSON:" + json.dumps(result))
'''.replace("__REPO__", _REPO)


@unittest.skipUnless(HYTHON, "hython not installed")
class TestSkillWorkflowHython(unittest.TestCase):
    """Validates that the SKILL.md 4-step workflow + 5 completion criteria
    are all executable and machine-checkable under real Houdini."""

    def _run_harness(self):
        proc = subprocess.run(
            [HYTHON, "-c", _HARNESS],
            capture_output=True, text=True, timeout=300,
            cwd=_REPO,
            stdin=subprocess.DEVNULL)
        combined = proc.stdout + proc.stderr
        for line in combined.splitlines():
            if line.startswith("RESULT_JSON:"):
                return json.loads(line[len("RESULT_JSON:"):]), combined
        self.fail(f"no RESULT_JSON in output.\n--- stdout ---\n{proc.stdout}\n"
                  f"--- stderr ---\n{proc.stderr}")

    def test_step1_core_path_returned(self):
        """Step 1 criterion: project_create returns a valid core_path."""
        res, _ = self._run_harness()
        self.assertTrue(res["criteria"]["c1_core_path_valid"],
                        f"core_path invalid: {res['steps'].get('s1_core_path')}")

    def test_step2_scaffold_and_design_params(self):
        """Step 2 criterion: subnets built, in-ports wired, design_params created."""
        res, _ = self._run_harness()
        c = res["criteria"]
        self.assertTrue(c["c2_tabletop_subnet"], "tabletop subnet missing")
        self.assertTrue(c["c2_legs_subnet"], "legs subnet missing")
        self.assertTrue(c["c2_in_ports_wired"],
                        f"in-ports not wired: {res['steps'].get('s2_scaffold')}")
        self.assertTrue(c["c2_design_param_length"], "design param 'length' missing")
        self.assertTrue(c["c2_design_param_width"], "design param 'width' missing")

    def test_step3_geometry_and_measured_anchors(self):
        """Step 3 criterion: geometry built, all anchors measured + emitted."""
        res, _ = self._run_harness()
        self.assertTrue(res["criteria"]["c3_tabletop_has_geometry"], "no geometry at out")
        self.assertTrue(res["criteria"]["c3_all_anchors_emitted"],
                        f"anchors missing: {res['steps'].get('s3_emitted_anchor_names')}")

    def test_step3_anchors_are_live(self):
        """Step 3 deep criterion: anchors are MEASURED (live) — they follow geometry.
        This is the core 'measure, don't hardcode' contract made testable."""
        res, _ = self._run_harness()
        self.assertTrue(res["criteria"]["c3_anchors_are_live"],
                        f"anchors NOT live: before={res['steps'].get('s3_fr_before')} "
                        f"after={res['steps'].get('s3_fr_after')} err={res['steps'].get('s3_live_error')}")

    def test_step4_promote_live_guarantee(self):
        """Step 4 criterion: promote creates core parm, subnet follows via ch(),
        and a core value change propagates to the subnet (LIVE)."""
        res, _ = self._run_harness()
        c = res["criteria"]
        self.assertTrue(c["c4_promoted_parm_exists"], "promoted parm missing")
        self.assertTrue(c["c4_subnet_follows_core"],
                        f"subnet not following: {res['steps'].get('s4_subnet_expr')}")
        self.assertTrue(c["c4_live_change_propagates"],
                        f"LIVE failed: {res['steps'].get('s4_subnet_eval_after')}")


if __name__ == "__main__":
    unittest.main()
