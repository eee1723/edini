"""Real-Houdini (hython) end-to-end replay of the 2026-07-09 Rubik's-cube
session, proving the THREE check-layer fixes work together on a live scene.

The cube session exposed three coupled gaps in the project-modeling CHECK
layer; each is unit-tested elsewhere, but this test confirms they hold on a
REAL edini::project HDA (real parent-walk, real geometry, real recook):

  FIX 1 (guard, P1a): an ``attribwrangle`` inside a project core with a
      COMPUTED-position addpoint (the cube grid_pts pattern
      ``set(i-base,j-base,k-base)*step``) is ALLOWED — no bypass marker
      needed — while a LITERAL-coordinate addpoint is still refused.

  FIX 2 (multi-probe, P2): a "shape" design param that moves points WITHOUT
      moving the bbox now PASSES ``verify_parametric`` via the point-position
      hash (the bbox-only proxy false-negatived it). A truly dead param still
      FAILS (regression guard for the new probe).

  FIX 3 (coupling advisory, P1b): a 2-component project with no ``ports.in``
      surfaces the ``independent_components`` advisory from ``project_status``.

Auto-discovers hython via tests/_hython.py; skips when not found.
Run: py -3 -m pytest tests/test_checklayer_e2e_hython.py -v
"""
import json
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python3.11libs"))
from _hython import HYTHON  # noqa: E402

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


# hython subprocess: build a real 2-component project, exercise all three fixes.
_HARNESS = r"""
import json, sys, os
sys.path.insert(0, os.path.join(r"%s", "python3.11libs"))
import hou

_hda = os.path.join(r"%s", "otls", "edini_project.hda")
if os.path.isfile(_hda):
    hou.hda.installFile(_hda)

from edini.project.state import (empty_declaration, add_component,
                                 add_design_param)
from edini.project.node import create_project_hda
from edini.project.builder import build_project_scaffold
from edini.project.ports import OUT_GEOMETRY_NODE
from edini.project.guards import lint_wrangle_snippet
from edini.node_utils import verify_parametric, project_status

result = {"steps": {}}

core = create_project_hda(name="proj_cube_replay")
core_path = core.path()
decl = empty_declaration("proj_cube_replay")
add_design_param(decl, "unit", default=1.0, min=0.3, max=3.0, label="尺寸")
add_design_param(decl, "wave", default=0.5, min=0.0, max=1.0, label="形变")
add_component(decl, "cubies", purpose="方块本体")
add_component(decl, "stickers", purpose="贴纸")
build_project_scaffold(core, declaration=decl)
cubies = core.node("cubies")
out_node = core.node("OUT")

# ─────────────────────────── FIX 1: guard ───────────────────────────
# The cube grid_pts pattern: a computed-position addpoint inside a real
# project-core wrangle. MUST be allowed (no bypass marker).
grid_pts = cubies.createNode("attribwrangle", "grid_pts")
computed = (
    'int n = 3;\n'
    'float u = chf("' + core_path + '/unit");\n'
    'float step = u * 1.06;\n'
    'float base = (n - 1) * 0.5;\n'
    'for (int i=0;i<n;i++) for (int j=0;j<n;j++) for (int k=0;k<n;k++) {\n'
    '    vector p = set(i - base, j - base, k - base) * step;\n'
    '    addpoint(0, p);\n'
    '}')
g_computed = lint_wrangle_snippet(grid_pts.path(), computed)
result["steps"]["fix1_computed_allowed"] = (g_computed is None)

# The chair-incident anti-pattern: a literal coordinate. MUST be refused.
bad = cubies.createNode("attribwrangle", "bad_anchor")
literal = "int p = addpoint(0, set(0.225, 0, 0.225));"
g_literal = lint_wrangle_snippet(bad.path(), literal)
result["steps"]["fix1_literal_refused"] = (
    g_literal is not None
    and g_literal.get("success") is False
    and g_literal.get("blocked_by") == "project_anchor_guard")

# ─────────────────────── FIX 2: multi-probe ────────────────────────
# A box sets the bbox (±0.5); a detail wrangle adds interior points whose Y
# follows 'wave' (computed addpoint — guard-allowed). Perturbing 'wave'
# moves the interior points but leaves the bbox byte-identical → only the
# point-position hash detects it. The old bbox-only proxy false-negatived.
box = cubies.createNode("box", "bbox_box")
mover = cubies.createNode("attribwrangle", "mover")
mover.parm("class").set(0)  # detail (runs once, owns a geometry to add to)
mover.parm("snippet").set(
    'float t = chf("' + core_path + '/wave");\n'
    'addpoint(0, set(0.0, t*0.3, 0.0));\n'
    'addpoint(0, set(0.2, t*0.3, 0.0));\n'
    'addpoint(0, set(-0.2, t*0.3, 0.0));\n')
merge = cubies.createNode("merge", "m")
merge.setInput(0, box)
merge.setInput(1, mover)
cubies.node(OUT_GEOMETRY_NODE).setInput(0, merge)

vp_wave = verify_parametric(
    node_path=out_node.path(), core_path=core_path,
    param="wave", new_value=0.9)
result["steps"]["fix2_wave_passed"] = vp_wave.get("passed")
result["steps"]["fix2_wave_hash_changed"] = vp_wave.get("point_hash_changed")
result["steps"]["fix2_wave_reason"] = vp_wave.get("reason")

# Regression guard: a TRULY dead param (geometry unrelated to 'wave') must
# still FAIL — the new probe must not create false positives.
dead = cubies.createNode("box", "dead_box")
dead.parm("sizex").set(1.0)  # literal, 'wave' never reaches it
cubies.node(OUT_GEOMETRY_NODE).setInput(0, dead)
vp_dead = verify_parametric(
    node_path=out_node.path(), core_path=core_path,
    param="wave", new_value=0.9)
result["steps"]["fix2_dead_failed"] = (vp_dead.get("passed") is False)

# ─────────────────────── FIX 3: coupling advisory ───────────────────
# 2 components, neither declares ports.in → independent islands. The cube
# pattern. project_status must surface the advisory (non-blocking).
status = project_status(core_path)
advs = status.get("coupling_advisories", []) or []
result["steps"]["fix3_has_advisory"] = any(
    a.get("kind") == "independent_components" for a in advs)
result["steps"]["fix3_advisory_components"] = (
    advs[0].get("component_count") if advs else None)
# Advisory must be NON-blocking: status success regardless.
result["steps"]["fix3_status_success"] = status.get("success")

print("RESULT_JSON:" + json.dumps(result))
""" % (_REPO, _REPO)


@unittest.skipUnless(HYTHON, "hython not installed — run under real Houdini")
class TestCheckLayerE2EHython(unittest.TestCase):
    """Decisive real-Houdini replay of the cube session's three check-layer
    fixes (guard rescoping + verify_parametric multi-probe + coupling
    advisory)."""

    def _run(self):
        proc = subprocess.run(
            [HYTHON, "-c", _HARNESS],
            capture_output=True, text=True, timeout=240, cwd=_REPO,
            stdin=subprocess.DEVNULL)
        combined = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, 0,
                         f"hython failed (rc={proc.returncode}):\n"
                         f"{combined[-3000:]}")
        idx = combined.rfind("RESULT_JSON:")
        self.assertGreater(idx, -1, f"no RESULT_JSON:\n{combined[-3000:]}")
        return json.loads(combined[idx + len("RESULT_JSON:"):]), combined

    def test_fix1_computed_addpoint_allowed(self):
        """The cube grid_pts pattern (computed position) needs no bypass."""
        res, _ = self._run()
        self.assertTrue(res["steps"]["fix1_computed_allowed"],
                        "computed-position addpoint must be allowed in a "
                        f"project core: {res}")

    def test_fix1_literal_addpoint_refused(self):
        """The chair-incident literal coordinate is still refused."""
        res, _ = self._run()
        self.assertTrue(res["steps"]["fix1_literal_refused"],
                        "literal-coordinate addpoint must be refused: "
                        f"{res}")

    def test_fix2_shape_param_passes_via_hash(self):
        """A bbox-preserving shape param PASSES via the point-position hash."""
        res, _ = self._run()
        s = res["steps"]
        self.assertTrue(s["fix2_wave_passed"],
                        f"'wave' (moves points, not bbox) should PASS: {res}")
        self.assertTrue(s["fix2_wave_hash_changed"],
                        "the pass must be driven by the point-position hash: "
                        f"{res}")

    def test_fix2_dead_param_still_fails(self):
        """The multi-probe must not make a truly dead param pass."""
        res, _ = self._run()
        self.assertTrue(res["steps"]["fix2_dead_failed"],
                        f"a dead param must still FAIL: {res}")

    def test_fix3_coupling_advisory_fires(self):
        """2 independent components surface the advisory (non-blocking)."""
        res, _ = self._run()
        s = res["steps"]
        self.assertTrue(s["fix3_has_advisory"],
                        f"independent components must surface an advisory: {res}")
        self.assertEqual(s["fix3_advisory_components"], 2)
        self.assertTrue(s["fix3_status_success"],
                        "the advisory is non-blocking — status still succeeds")


if __name__ == "__main__":
    unittest.main()
