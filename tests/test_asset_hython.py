"""Real-Houdini (hython) end-to-end test for the validate_asset tool.

This is the milestone-1 "实测" gate required by the roadmap before milestone 2
(capability-before-rules discipline). It launches Houdini's bundled Python
(hython) as a subprocess and exercises the validate_asset tool handler against
the real hou module — proving the asset pipeline works in a genuine Houdini
process, not just under the mock.

The test process itself runs under whatever Python pytest uses; the assertions
are made on JSON that the hython subprocess prints to stdout. This keeps the
two interpreters isolated (hython is Houdini's Python 3.11; pytest may be a
different CPython) while still asserting end-to-end behaviour.

Skipped automatically when hython is not installed (CI without Houdini). Run
manually on a Houdini box:

    python -m pytest tests/test_asset_hython.py -v
"""
import json
import os
import shutil
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
PYTHONLIBS = os.path.join(REPO, "python3.11libs")
BICYCLE = os.path.join(PYTHONLIBS, "edini", "data", "bicycle.asset.json")

# Standard Houdini install locations. The first that exists wins.
_HOUDINI_CANDIDATES = [
    r"C:\Program Files\Side Effects Software",
    "/opt/hfs",  # Linux
    "/Applications/Houdini",  # macOS
]


def _find_hython():
    """Locate hython across platforms. Returns an absolute path or None."""
    # 1. Explicit override.
    env_path = os.environ.get("EDINI_HYTHON") or os.environ.get("HYTHON")
    if env_path and os.path.isfile(env_path):
        return env_path
    # 2. PATH lookup.
    found = shutil.which("hython") or shutil.which("hython.exe")
    if found:
        return found
    # 3. Standard install dirs: find the newest version subdir.
    for base in _HOUDINI_CANDIDATES:
        if not os.path.isdir(base):
            continue
        # base may be the version parent (Windows) or the version dir itself.
        candidates = []
        if os.name == "nt":
            for name in os.listdir(base):
                ver_dir = os.path.join(base, name, "bin")
                exe = os.path.join(ver_dir, "hython.exe")
                if os.path.isfile(exe):
                    candidates.append((name, exe))
        else:
            for name in os.listdir(base):
                ver_dir = os.path.join(base, name, "bin")
                exe = os.path.join(ver_dir, "hython")
                if os.path.isfile(exe):
                    candidates.append((name, exe))
        if candidates:
            # Pick the highest version (sort by name desc).
            candidates.sort(reverse=True)
            return candidates[0][1]
    return None


HYTHON = _find_hython()

# Sentinel markers wrapping the JSON payload so we can robustly extract it
# from mixed stdout (hython may print Houdini banners/warnings).
_START = "___EDINI_RESULT_START___"
_END = "___EDINI_RESULT_END___"

# The script run inside hython. It is kept as a string (not imported) so the
# subprocess is a clean interpreter with no pytest contamination. It loads the
# real edini package, calls the validate_asset handler directly (bypassing the
# HTTP server), and prints a JSON result wrapped in sentinels.
_HYTHON_SCRIPT = r"""
import sys, os, json, traceback

# Make the repo's python3.11libs importable inside hython.
sys.path.insert(0, {pythonlibs!r})

result = {{}}
try:
    import hou  # the REAL hou — proves we are in Houdini, not the mock
    result['houdini_version'] = hou.applicationVersionString()

    from edini import tool_executor

    bicycle = {bicycle!r}
    res = tool_executor.validate_asset(asset_path=bicycle, resolve={resolve!r})
    result['success'] = res.get('success')
    result['errors'] = res.get('errors', [])
    result['point_count'] = len(res.get('resolved_skeleton', {{}}))
    points = res.get('resolved_skeleton', {{}})
    result['points'] = {{k: list(v) if isinstance(v, tuple) else v
                         for k, v in points.items()}}
    # Verify a few physical facts about the resolved skeleton.
    bb = points.get('bb_center')
    if bb is not None:
        # bb_center.x must be negative (BB sits ahead of the rear axle at x=0
        # toward the front, i.e. forward/negative-x in this frame) — the
        # corrected horizontal-projection expression guarantees this.
        result['bb_center_x'] = float(bb[0])
except Exception:
    result['error'] = traceback.format_exc()

print({start!r})
print(json.dumps(result, default=str))
print({end!r})
"""


def _run_hython(resolve):
    """Run the validation script in hython and return the parsed result dict."""
    script = _HYTHON_SCRIPT.format(
        pythonlibs=PYTHONLIBS,
        bicycle=BICYCLE,
        resolve=resolve,
        start=_START,
        end=_END,
    )
    proc = subprocess.run(
        [HYTHON, "-c", script],
        capture_output=True,
        text=True,
        timeout=120,
    )
    output = proc.stdout + proc.stderr
    # Extract the sentinel-wrapped JSON block.
    if _START not in output or _END not in output:
        return {
            "error": "hython produced no result sentinel",
            "stdout": proc.stdout[-2000:],
            "stderr": proc.stderr[-2000:],
        }
    block = output.split(_START, 1)[1].split(_END, 1)[0].strip()
    return json.loads(block)


@unittest.skipUnless(HYTHON, "hython not found — skip real-Houdini test")
class TestValidateAssetHython(unittest.TestCase):
    """End-to-end: validate_asset runs inside a genuine Houdini process."""

    def test_hython_is_real_houdini(self):
        """The subprocess is a real Houdini interpreter (hou importable, has a
        version), not a mock. This is the whole point of '实测'."""
        result = _run_hython(resolve=True)
        self.assertNotIn("error", result, result.get("error", ""))
        self.assertTrue(result.get("houdini_version", "").startswith("21"))

    def test_bicycle_validates_in_houdini(self):
        result = _run_hython(resolve=True)
        self.assertNotIn("error", result, result.get("error", ""))
        self.assertTrue(result["success"], result.get("errors"))
        self.assertEqual(result["errors"], [])

    def test_resolves_five_skeleton_points(self):
        result = _run_hython(resolve=True)
        self.assertNotIn("error", result, result.get("error", ""))
        self.assertEqual(result["point_count"], 5)

    def test_bb_center_physically_correct(self):
        """The corrected bb_center expression resolves to a forward (negative-x)
        position in the real Houdini expression engine — confirming the math
        fix survives real evaluation, not just the unit-tested Python path."""
        result = _run_hython(resolve=True)
        self.assertNotIn("error", result, result.get("error", ""))
        self.assertIn("bb_center_x", result)
        self.assertLess(result["bb_center_x"], 0.0)

    def test_validate_without_resolve(self):
        """resolve=False still validates but omits the skeleton."""
        result = _run_hython(resolve=False)
        self.assertNotIn("error", result, result.get("error", ""))
        self.assertTrue(result["success"])
        self.assertEqual(result["point_count"], 0)


# ── Milestone 2: build_asset (geometry generation) ──────────────────
#
# A second hython script that builds the bundled table.asset.json into a real
# Houdini network and inspects the cooked OUT geometry. This is the milestone-2
# "实测" gate: the declarative asset produces a genuine multi-component object
# (tabletop + 4 legs) with correct component_id tagging.

TABLE = os.path.join(PYTHONLIBS, "edini", "data", "table.asset.json")

_BUILD_SCRIPT = r"""
import sys, os, json, traceback

sys.path.insert(0, {pythonlibs!r})

result = {{}}
try:
    import hou
    result['houdini_version'] = hou.applicationVersionString()

    from edini import asset_builder, asset_model

    table = {table!r}
    asset = asset_model.load_asset(table)

    # Build into a throwaway geo sandbox.
    obj = hou.node('/obj')
    root = obj.createNode('geo', 'edini_m2_test')
    build = asset_builder.build_asset(asset, root.path())
    result['build_success'] = build.get('success')
    result['components_built'] = build.get('components_built')
    if not build.get('success'):
        result['error'] = build.get('error', 'build failed')
    else:
        out = hou.node(build['out_path'])
        out.cook(force=True)
        geo = out.geometry()
        result['out_path'] = build['out_path']
        result['point_count'] = geo.intrinsicValue('pointcount')
        result['prim_count'] = geo.intrinsicValue('primitivecount')
        result['cook_errors'] = list(out.errors() or [])
        cid = geo.findPrimAttrib('component_id')
        if cid is not None:
            result['component_ids'] = sorted(set(
                str(p.stringAttribValue('component_id')) for p in geo.prims()))
        else:
            result['component_ids'] = []
        # Bounding box — a table should span a non-zero volume.
        b = geo.intrinsicValue('bounds')
        if b and len(b) == 6:
            result['bounds_size'] = [b[1]-b[0], b[3]-b[2], b[5]-b[4]]
        # Clean up the sandbox so repeated runs don't accumulate nodes.
        try:
            root.destroy()
        except Exception:
            pass
except Exception:
    result['error'] = traceback.format_exc()

print({start!r})
print(json.dumps(result, default=str))
print({end!r})
"""


def _run_build():
    """Build the table in hython and return the parsed result dict."""
    script = _BUILD_SCRIPT.format(
        pythonlibs=PYTHONLIBS, table=TABLE, start=_START, end=_END,
    )
    proc = subprocess.run(
        [HYTHON, "-c", script],
        capture_output=True, text=True, timeout=180,
    )
    output = proc.stdout + proc.stderr
    if _START not in output or _END not in output:
        return {
            "error": "hython produced no result sentinel",
            "stdout": proc.stdout[-2000:], "stderr": proc.stderr[-2000:],
        }
    block = output.split(_START, 1)[1].split(_END, 1)[0].strip()
    return json.loads(block)


@unittest.skipUnless(HYTHON, "hython not found — skip real-Houdini test")
class TestBuildAssetHython(unittest.TestCase):
    """End-to-end milestone-2: build_asset generates a real table in Houdini."""

    def test_build_succeeds(self):
        result = _run_build()
        self.assertNotIn("error", result, result.get("error", ""))
        self.assertTrue(result["build_success"])

    def test_builds_all_five_components(self):
        result = _run_build()
        self.assertNotIn("error", result, result.get("error", ""))
        self.assertEqual(result["components_built"], 5)

    def test_out_has_geometry(self):
        """The OUT node produces non-trivial geometry (not an empty network)."""
        result = _run_build()
        self.assertNotIn("error", result, result.get("error", ""))
        self.assertGreater(result["point_count"], 0)
        self.assertGreater(result["prim_count"], 0)

    def test_all_components_tagged_with_id(self):
        """Every component's geometry carries its component_id: the tabletop +
        4 legs. This is what the orientation/inventory gates key on."""
        result = _run_build()
        self.assertNotIn("error", result, result.get("error", ""))
        self.assertEqual(
            set(result["component_ids"]),
            {"tabletop", "leg_fl", "leg_fr", "leg_bl", "leg_br"})

    def test_no_cook_errors(self):
        """The built network cooks cleanly — no Houdini errors on OUT."""
        result = _run_build()
        self.assertNotIn("error", result, result.get("error", ""))
        self.assertEqual(result["cook_errors"], [])

    def test_table_has_nonzero_volume(self):
        """A table spans 3D space in all axes (not a degenerate flat shape)."""
        result = _run_build()
        self.assertNotIn("error", result, result.get("error", ""))
        size = result.get("bounds_size", [0, 0, 0])
        for axis_name, extent in zip("xyz", size):
            self.assertGreater(extent, 0.01,
                               f"table is degenerate on {axis_name}: {extent}")


if __name__ == "__main__":
    unittest.main()
