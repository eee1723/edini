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
