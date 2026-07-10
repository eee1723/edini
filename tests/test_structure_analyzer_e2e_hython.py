"""Real-Houdini (hython) tests for edini.structure. Auto-discovers hython
via tests/_hython.py; skips when not found.
Run: py -3 -m pytest tests/test_structure_analyzer_e2e_hython.py -v
"""
import json, os, subprocess, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python3.11libs"))
from _hython import HYTHON  # noqa: E402
_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _run(harness_py: str) -> dict:
    proc = subprocess.run([HYTHON, "-c", harness_py % (_REPO, _REPO)],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise AssertionError(f"hython failed (rc={proc.returncode}):\n{proc.stderr}")
    return json.loads(proc.stdout.strip().splitlines()[-1])


# Build a 1-component project whose wheel is a Python SOP (no CTP) — the
# deepseek-bike failure shape. _extract_component_signals must report
# instancing_nodes empty + python_emit_geometry True + inferred_repeats True.
_EXTRACT_HARNESS = r"""
import json, sys, os
sys.path.insert(0, os.path.join(r"%s", "python3.11libs"))
import hou
_hda = os.path.join(r"%s", "otls", "edini_project.hda")
if os.path.isfile(_hda): hou.hda.installFile(_hda)
from edini.project.node import create_project_hda
from edini.project.builder import build_project_scaffold
from edini.project.state import empty_declaration
from edini.project.ports import OUT_GEOMETRY_NODE
from edini.structure import _extract_component_signals

core = create_project_hda(name="proj_struct_extract")
decl = empty_declaration("proj_struct_extract")
decl["components"] = [{"id": "wheel", "structure": {"kind": "radial", "expected_axis": "Z",
    "repeats": [{"part": "spoke", "count": 28, "method": "copytopoints"}]}}]
build_project_scaffold(core, declaration=decl)
wheel = core.node("wheel")
# A python SOP that emits many prims, wired into out_geometry — no CTP.
py = wheel.createNode("python", "wheel_gen")
py.parm("python").set(
    "geo = hou.pwd().geometry()\n"
    "for i in range(60):\n"
    "    geo.createPolygon()\n")
outg = wheel.node(OUT_GEOMETRY_NODE)
outg.setInput(0, py)
outg.cook(force=True)
sig = _extract_component_signals(wheel, "wheel")
print(json.dumps({"prim_types": sig["prim_types"],
                  "instancing_nodes": sorted(sig["instancing_nodes"]),
                  "python_emit_geometry": sig["python_emit_geometry"],
                  "inferred_repeats": sig["inferred_repeats"]}))
"""


class TestExtractSignals(unittest.TestCase):
    @unittest.skipUnless(HYTHON, "hython not installed — run under real Houdini")
    def test_python_sop_wheel_signals(self):
        r = _run(_EXTRACT_HARNESS)
        self.assertGreater(r["prim_types"].get("Polygon", 0), 0)
        self.assertEqual(r["instancing_nodes"], [])
        self.assertTrue(r["python_emit_geometry"])
        self.assertTrue(r["inferred_repeats"])


# analyze_component_structure on the python-SOP wheel must verdict FATAL with
# F2_repeat_no_instancing (declared copytopoints but no CTP node).
_ANALYZE_HARNESS = r"""
import json, sys, os
sys.path.insert(0, os.path.join(r"%s", "python3.11libs"))
import hou
_hda = os.path.join(r"%s", "otls", "edini_project.hda")
if os.path.isfile(_hda): hou.hda.installFile(_hda)
from edini.project.node import create_project_hda
from edini.project.builder import build_project_scaffold
from edini.project.state import empty_declaration
from edini.project.ports import OUT_GEOMETRY_NODE
from edini.structure import analyze_component_structure

core = create_project_hda(name="proj_struct_analyze")
decl = empty_declaration("proj_struct_analyze")
decl["components"] = [{"id": "wheel", "structure": {"kind": "radial", "expected_axis": "Z",
    "repeats": [{"part": "spoke", "count": 28, "method": "copytopoints"}]}}]
build_project_scaffold(core, declaration=decl)
wheel = core.node("wheel")
py = wheel.createNode("python", "wheel_gen")
py.parm("python").set("geo=hou.pwd().geometry()\n[geo.createPolygon() for _ in range(60)]\n")
wheel.node(OUT_GEOMETRY_NODE).setInput(0, py)
res = analyze_component_structure(core.path(), component_id="wheel")
print(json.dumps({"overall": res["overall"],
                  "rules": [f["rule"] for f in res["fatal"]]}))
"""


class TestAnalyze(unittest.TestCase):
    @unittest.skipUnless(HYTHON, "hython not installed — run under real Houdini")
    def test_python_wheel_is_fatal(self):
        r = _run(_ANALYZE_HARNESS)
        self.assertEqual(r["overall"], "fatal")
        self.assertIn("F2_repeat_no_instancing", r["rules"])


# build_project_scaffold must REFUSE a component whose structure fails lint,
# before creating any nodes.
_LINT_REFUSE_HARNESS = r"""
import json, sys, os
sys.path.insert(0, os.path.join(r"%s", "python3.11libs"))
import hou
_hda = os.path.join(r"%s", "otls", "edini_project.hda")
if os.path.isfile(_hda): hou.hda.installFile(_hda)
from edini.project.node import create_project_hda
from edini.project.builder import build_project_scaffold
from edini.project.state import empty_declaration
core = create_project_hda(name="proj_lint_refuse")
decl = empty_declaration("proj_lint_refuse")
decl["components"] = [{"id": "wheel", "structure": {"kind": "radial"}}]  # no axis
res = build_project_scaffold(core, declaration=decl)
# res may be a dict (refusal) — coerce for JSON. If it's not a dict, the
# scaffold failed to refuse; signal that.
if not isinstance(res, dict):
    print(json.dumps({"refused": False, "code": None,
                      "note": "scaffold did not return a refusal dict"}))
else:
    print(json.dumps({"refused": not res.get("success", False),
                      "code": (res.get("lint_errors") or [{}])[0].get("code")}))
"""


class TestScaffoldLint(unittest.TestCase):
    @unittest.skipUnless(HYTHON, "hython not installed — run under real Houdini")
    def test_scaffold_refuses_bad_structure(self):
        r = _run(_LINT_REFUSE_HARNESS)
        self.assertTrue(r["refused"], f"scaffold should refuse bad structure, got: {r}")
        self.assertEqual(r["code"], "missing_axis")


# A project with a fatal structure verdict must NOT finalize even with
# acknowledge_skip=True (skip does not bypass Gate 4). Only structure_override
# + structure_reason passes.
_FINALIZE_GATE4_HARNESS = r"""
import json, sys, os
sys.path.insert(0, os.path.join(r"%s", "python3.11libs"))
import hou
_hda = os.path.join(r"%s", "otls", "edini_project.hda")
if os.path.isfile(_hda): hou.hda.installFile(_hda)
from edini.project.node import create_project_hda
from edini.project.builder import build_project_scaffold
from edini.project.state import empty_declaration
from edini.project.ports import OUT_GEOMETRY_NODE
from edini.verify import project_finalize

core = create_project_hda(name="proj_gate4")
decl = empty_declaration("proj_gate4")
decl["components"] = [{"id": "wheel", "structure": {"kind": "radial", "expected_axis": "Z",
    "repeats": [{"part": "spoke", "count": 28, "method": "copytopoints"}]}}]
build_project_scaffold(core, declaration=decl)
wheel = core.node("wheel")
py = wheel.createNode("python", "wheel_gen")
py.parm("python").set("geo=hou.pwd().geometry()\n[geo.createPolygon() for _ in range(60)]\n")
wheel.node(OUT_GEOMETRY_NODE).setInput(0, py)
skip = project_finalize(core.path(), acknowledge_skip=True, skip_reason="try to skip")
over = project_finalize(core.path(), structure_override=True, structure_reason="test override")
print(json.dumps({"skip_finalized": skip.get("finalized"),
                  "skip_structure_blocked": skip.get("structure_blocked"),
                  "override_finalized": over.get("finalized")}))
"""


class TestFinalizeGate4(unittest.TestCase):
    @unittest.skipUnless(HYTHON, "hython not installed — run under real Houdini")
    def test_skip_does_not_bypass_gate4(self):
        r = _run(_FINALIZE_GATE4_HARNESS)
        self.assertFalse(r["skip_finalized"], "acknowledge_skip must NOT bypass fatal structure verdicts")
        self.assertTrue(r["skip_structure_blocked"])
        self.assertTrue(r["override_finalized"], "structure_override+reason must pass")


# Replays of the 2026-07-09 logged failures + a clean case.
_ACCEPTANCE_HARNESS = r"""
import json, sys, os
sys.path.insert(0, os.path.join(r"%s", "python3.11libs"))
import hou
_hda = os.path.join(r"%s", "otls", "edini_project.hda")
if os.path.isfile(_hda): hou.hda.installFile(_hda)
from edini.project.node import create_project_hda
from edini.project.builder import build_project_scaffold
from edini.project.state import empty_declaration
from edini.project.ports import OUT_GEOMETRY_NODE
from edini.structure import analyze_component_structure

def fresh(name, comps):
    core = create_project_hda(name=name)
    decl = empty_declaration(name)
    decl["components"] = comps
    build_project_scaffold(core, declaration=decl)
    return core

# 1. deepseek wheel: python SOP, no CTP, declared radial+Z
c = fresh("acc_wheel", [{"id":"wheel","structure":{"kind":"radial","expected_axis":"Z",
    "repeats":[{"part":"spoke","count":28,"method":"copytopoints"}]}}])
w = c.node("wheel"); py = w.createNode("python","wg")
py.parm("python").set("g=hou.pwd().geometry()\n[g.createPolygon() for _ in range(60)]\n")
w.node(OUT_GEOMETRY_NODE).setInput(0, py)

# 2. glm frame: bare NURBS curve wired to out_geometry (no PolyWire/Sweep)
# The modern curve SOP lacks type/coords parms; use a python SOP to emit a
# real NURBSCurve prim so F1's keyword match fires on "nurbs".
c2 = fresh("acc_frame", [{"id":"frame","structure":{"kind":"solid"}}])
f = c2.node("frame"); cv = f.createNode("python","skel")
cv.parm("python").set(
    "g=hou.pwd().geometry()\n"
    "for c in [(0,0,0),(1,1,1),(2,0,0),(3,0,1)]:\n"
    "    p=g.createPoint(); p.setPosition(hou.Vector3(*c))\n"
    "g.createNURBSCurve(4,False,4)\n")
f.node(OUT_GEOMETRY_NODE).setInput(0, cv)

# 3. deepseek candles: CTP present but target has no orient
# scatter requires input geometry to scatter on — use a grid as scatter surface.
c3 = fresh("acc_candle", [{"id":"candles","structure":{"kind":"repeated",
    "repeats":[{"part":"candle","count":6,"method":"copytopoints"}]}}])
cd = c3.node("candles")
surf = cd.createNode("grid","surf"); tmpl = cd.createNode("tube","candle_body")
scatter = cd.createNode("scatter","pts"); scatter.setInput(0, surf)
scatter.parm("npts").set(10)
ctp = cd.createNode("copytopoints::2.0","copy")
ctp.setInput(0, tmpl); ctp.setInput(1, scatter)
cd.node(OUT_GEOMETRY_NODE).setInput(0, ctp)

# 4. clean table legs: CTP + orient on target points
# scatter requires input geometry — grid → scatter → wrangle(orient) → CTP target.
c4 = fresh("acc_legs", [{"id":"legs","structure":{"kind":"repeated",
    "repeats":[{"part":"leg","count":4,"method":"copytopoints"}]}}])
lg = c4.node("legs")
lsurf = lg.createNode("grid","lsurf"); leg = lg.createNode("tube","leg_t")
sc = lg.createNode("scatter","lp"); sc.setInput(0, lsurf); sc.parm("npts").set(4)
wr = lg.createNode("attribwrangle","ori"); wr.parm("snippet").set("p@orient={0,0,0,1};")
wr.setInput(0, sc); cp = lg.createNode("copytopoints::2.0","cp")
cp.setInput(0, leg); cp.setInput(1, wr); lg.node(OUT_GEOMETRY_NODE).setInput(0, cp)

out = {}
for name, core in [("wheel", c), ("frame", c2), ("candle", c3), ("legs", c4)]:
    r = analyze_component_structure(core.path())
    out[name] = {"overall": r["overall"], "rules": [f["rule"] for f in r["fatal"]]}
print(json.dumps(out))
"""


class TestAcceptance(unittest.TestCase):
    @unittest.skipUnless(HYTHON, "hython not installed — run under real Houdini")
    def test_logged_failures_are_fatal_and_clean_is_clean(self):
        r = _run(_ACCEPTANCE_HARNESS)
        self.assertEqual(r["wheel"]["overall"], "fatal")
        self.assertIn("F2_repeat_no_instancing", r["wheel"]["rules"])
        self.assertEqual(r["frame"]["overall"], "fatal")
        self.assertIn("F1_bare_curves_at_out", r["frame"]["rules"])
        self.assertEqual(r["candle"]["overall"], "fatal")
        self.assertIn("F4_ctp_no_orient", r["candle"]["rules"])
        self.assertEqual(r["legs"]["overall"], "clean")
