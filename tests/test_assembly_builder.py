"""Tests for edini.assembly_builder — the Root → Measure → Mount → Shape layer.

Two test layers mirror the archived pipeline's proven approach:

1. **Pure-data validation** (no Houdini): validate_assembly catches schema
   errors, dangling param refs, unknown mounts, bad measurements.
2. **Network structure + measurement** (mock hou): build_assembly creates the
   right nodes (root, leaves, xforms, merge, OUT), and — the core claim —
   the measured mounts track the root's real geometry. We supply a
   ``root_geometry_provider`` test seam that builds a true MockGeometry box
   from the params, so the measure→mount pipeline runs against real box
   geometry (the mock itself cannot synthesize native-SOP geometry).
"""
from __future__ import annotations

import os
import sys
import math
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python3.11libs"))
sys.path.insert(0, os.path.dirname(__file__))

import mock_hou  # noqa: E402
from mock_hou import create_mock_hou, MockNode  # noqa: E402

# validate_assembly is pure-data (no hou) so it imports safely at top level.
from edini.assembly_builder import validate_assembly  # noqa: E402


# ── Shared fixtures ─────────────────────────────────────────────────


def _car_assembly(length=4.0, width=2.0, thickness=0.5, wheel_radius=0.4):
    """A minimal car: a box platform (root) + 4 torus wheels, each mounted at
    a measured bottom corner with its axle oriented along the platform's long
    edge. NOTHING is hardcoded as a coordinate — every wheel position is a
    bbox_corner measurement, every wheel orient is a measured direction."""
    return {
        "id": "car",
        "params": {
            "length": length,
            "width": width,
            "thickness": thickness,
            "wheel_radius": wheel_radius,
            "wheel_tube_r": 0.08,
        },
        "root": {
            "shape": {"type": "box", "params": {
                "size": ["length", "thickness", "width"]}}
        },
        "mounts": [
            # Each wheel sits at one bottom corner of the platform.
            {"id": f"wheel_{c}", "position": {
                "measure": "bbox_corner", "from": "root", "axes": axes},
             "orient": {  # axle runs along the platform's X (long) edge
                "from": "root",
                "from_a": {"measure": "bbox_corner", "axes": "-X-Y+Z"},
                "from_b": {"measure": "bbox_corner", "axes": "+X-Y+Z"}}}
            for c, axes in [
                ("fr", "+X-Y+Z"), ("fl", "+X-Y-Z"),
                ("br", "-X-Y+Z"), ("bl", "-X-Y-Z"),
            ]
        ],
        "leaves": [
            # The leaf shape's own params are validated against real Houdini in
            # the hython test; the mock torus carries no shape params, so here
            # we leave them off. The leaf's SCALE is the parametric bit under
            # test (wheel size = a param expression), and it lands on the xform.
            {"id": f"wheel_{c}", "mount": f"wheel_{c}", "scale": "wheel_radius",
             "shape": {"type": "torus", "params": {}}}
            for c in ("fr", "fl", "br", "bl")
        ],
    }


def _box_provider(root_sop, params, size=("length", "thickness", "width")):
    """Test seam: build a real MockGeometry box from the params so the measure
    layer runs against true box geometry. Mirrors what real Houdini does when
    a box node cooks with these size params.

    ``size`` is the triple of param names the box reads (the car uses the
    default length/thickness/width; the keyboard passes its own tray names).
    The box is centered at origin with corners at (±sx/2, ±sy/2, ±sz/2).
    """
    from edini.exprs import evaluate
    geo = mock_hou.MockGeometry()
    geo.clear()
    sx = evaluate(size[0], params) if isinstance(size[0], str) else float(size[0])
    sy = evaluate(size[1], params) if isinstance(size[1], str) else float(size[1])
    sz = evaluate(size[2], params) if isinstance(size[2], str) else float(size[2])
    for x in (-sx / 2, sx / 2):
        for y in (-sy / 2, sy / 2):
            for z in (-sz / 2, sz / 2):
                p = geo.createPoint()
                p.setPosition((x, y, z))
    return geo


def _provider_for(assembly):
    """Return a root_geometry_provider closure bound to an assembly's root shape
    size, so any box-rooted assembly (car, keyboard, stairs) gets a real box."""
    size = assembly["root"]["shape"]["params"]["size"]
    return lambda root_sop, params: _box_provider(root_sop, params, size=size)


# ── Pure-data validation ────────────────────────────────────────────


class TestValidateAssembly(unittest.TestCase):
    def test_valid_car_passes(self):
        r = validate_assembly(_car_assembly())
        self.assertTrue(r["success"], r["errors"])
        self.assertEqual(r["summary"]["mount_count"], 4)
        self.assertEqual(r["summary"]["leaf_count"], 4)

    def test_missing_id_rejected(self):
        a = _car_assembly()
        del a["id"]
        r = validate_assembly(a)
        self.assertFalse(r["success"])
        self.assertTrue(any(e["code"] == "NO_ID" for e in r["errors"]))

    def test_missing_root_rejected(self):
        a = _car_assembly()
        del a["root"]
        r = validate_assembly(a)
        self.assertFalse(r["success"])
        self.assertTrue(any(e["code"] == "NO_ROOT" for e in r["errors"]))

    def test_bad_shape_type_rejected(self):
        a = _car_assembly()
        a["root"]["shape"]["type"] = "nurbssurface"  # not in M0 set
        r = validate_assembly(a)
        self.assertFalse(r["success"])
        self.assertTrue(any(e["code"] == "ROOT_BAD_SHAPE" for e in r["errors"]))

    def test_dangling_param_ref_rejected(self):
        a = _car_assembly()
        a["root"]["shape"]["params"]["size"] = ["nonexistent", "thickness", "width"]
        r = validate_assembly(a)
        self.assertFalse(r["success"])
        self.assertTrue(any(e["code"] == "PARAM_REF_DANGLING" for e in r["errors"]))

    def test_bad_measure_kind_rejected(self):
        a = _car_assembly()
        a["mounts"][0]["position"]["measure"] = "centroid"  # unsupported in M0
        r = validate_assembly(a)
        self.assertFalse(r["success"])
        self.assertTrue(any(e["code"] == "MOUNT_BAD_MEASURE" for e in r["errors"]))

    def test_bad_axes_rejected(self):
        a = _car_assembly()
        a["mounts"][0]["position"]["axes"] = "+X-Y"  # missing Z
        r = validate_assembly(a)
        self.assertFalse(r["success"])
        self.assertTrue(any(e["code"] == "MOUNT_BAD_AXES" for e in r["errors"]))

    def test_leaf_with_unknown_mount_rejected(self):
        a = _car_assembly()
        a["leaves"][0]["mount"] = "nonexistent_mount"
        r = validate_assembly(a)
        self.assertFalse(r["success"])
        self.assertTrue(any(e["code"] == "LEAF_BAD_MOUNT" for e in r["errors"]))

    def test_bbox_face_center_mount_valid(self):
        a = _car_assembly()
        a["mounts"][0]["position"] = {
            "measure": "bbox_face_center", "from": "root", "face": "+Y"}
        r = validate_assembly(a)
        self.assertTrue(r["success"], r["errors"])


# ── Network structure (mock hou) ────────────────────────────────────


class TestBuildAssemblyStructure(unittest.TestCase):
    """Build-level smoke test under a fresh mock hou. The mock cannot synthesize
    native-SOP geometry OR populate the xform node's t/r/scale parms, so we
    verify what IS mockable here: the build succeeds end-to-end and creates the
    expected NODE COUNT (root + N leaves + N xforms + merge + OUT). The actual
    placement translation / cooked geometry is validated in test_assembly_hython
    against real Houdini.

    The builder's module-level ``hou`` import binds to None at first import (the
    mock isn't installed yet), so we flush edini modules and re-import
    assembly_builder AFTER installing the mock — the archived builder tests'
    isolation contract."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._saved_ref = MockNode._hou_ref
        cls._saved_mod = sys.modules.get("hou")
        cls._hou = create_mock_hou()
        sys.modules["hou"] = cls._hou
        MockNode._hou_ref = cls._hou
        for _m in list(sys.modules):
            if _m.startswith("edini"):
                del sys.modules[_m]
        from edini import assembly_builder  # noqa: E402
        cls.build_assembly = staticmethod(assembly_builder.build_assembly)

    @classmethod
    def tearDownClass(cls):
        MockNode._hou_ref = cls._saved_ref
        sys.modules["hou"] = cls._saved_mod
        for _m in list(sys.modules):
            if _m.startswith("edini"):
                del sys.modules[_m]
        super().tearDownClass()

    def _build(self, assembly):
        hou = sys.modules["hou"]
        root = hou.node("/obj").createNode("geo", "sandbox")
        return root.path(), self.build_assembly(
            assembly, root.path(),
            root_geometry_provider=_box_provider)

    def test_build_creates_live_network_structure(self):
        """M2 live structure: root + one attribwrangle per mount + a pscale
        wrangle per scaled leaf + one copytopoints per leaf + merge + OUT.
        The mock verifies node EXISTENCE + wiring; VEX correctness is hython."""
        root_path, res = self._build(_car_assembly())
        self.assertTrue(res["success"], res.get("error"))
        self.assertTrue(res["out_path"].endswith("/OUT"))
        self.assertTrue(res["live"])  # the live-build signal
        hou = sys.modules["hou"]
        names = {c.name() for c in hou.node(root_path).children()}
        self.assertIn("root_shape", names)
        # 4 mount wrangles (one per wheel corner).
        for c in ("fr", "fl", "br", "bl"):
            self.assertIn(f"mount_wheel_{c}", names)
        # mounts_cloud merge + 4 CTP leaves + the final merge + OUT.
        self.assertIn("mounts_cloud", names)
        for c in ("fr", "fl", "br", "bl"):
            self.assertIn(f"wheel_{c}_ctp", names)
        self.assertIn("merge_all", names)
        self.assertIn("OUT", names)

    def test_mount_wrangle_carries_bbox_corner_vex(self):
        """Each mount wrangle's snippet contains the bbox_corner strategy's
        getbbox_min/max + lerp logic (not a baked coordinate)."""
        root_path, res = self._build(_car_assembly())
        self.assertTrue(res["success"], res.get("error"))
        hou = sys.modules["hou"]
        snip = hou.node(f"{root_path}/mount_wheel_fr").parm("snippet").eval()
        self.assertIn("getbbox_min", snip)
        self.assertIn("getbbox_max", snip)
        self.assertIn("lerp", snip)
        # The VEX must read bbox LIVE — no literal coordinate like "2.0, -0.25".
        self.assertNotIn("addpoint(0, set(2", snip)


# ── VEX strategy selector resolution (mock-testable part of the live path) ──
#
# The live build's geometry correctness is verified by hython (test_assembly_hython)
# against the Python oracle. What the mock CAN verify is the sign-string →
# numeric-selector resolution, which is pure data and determines which corner/
# face the VEX reads. These tests pin that resolution so a typo can't silently
# pick the wrong corner.


class TestVexStrategyResolution(unittest.TestCase):
    def test_corner_selectors_from_sign_string(self):
        from edini.vex_strategies import _corner_selectors
        # "+X-Y+Z" → X=max(1), Y=min(0), Z=max(1)
        self.assertEqual(_corner_selectors("+X-Y+Z"), {"cx": 1, "cy": 0, "cz": 1})
        # "-X+Y-Z" → X=min(0), Y=max(1), Z=min(0)
        self.assertEqual(_corner_selectors("-X+Y-Z"), {"cx": 0, "cy": 1, "cz": 0})

    def test_face_selector_from_sign_string(self):
        from edini.vex_strategies import _face_selector
        # "+Y" → axis 1 (Y), sign +1
        self.assertEqual(_face_selector("+Y"), {"face_axis": 1, "face_sign": 1})
        # "-Z" → axis 2 (Z), sign -1
        self.assertEqual(_face_selector("-Z"), {"face_axis": 2, "face_sign": -1})

    def test_build_mount_vex_bbox_corner(self):
        from edini.vex_strategies import build_mount_vex
        snippet, parms = build_mount_vex({"measure": "bbox_corner", "axes": "+X-Y+Z"})
        self.assertIn("getbbox_min", snippet)
        self.assertIn("getbbox_max", snippet)
        self.assertEqual(parms, {"cx": 1, "cy": 0, "cz": 1})

    def test_build_mount_vex_grid(self):
        from edini.vex_strategies import build_mount_vex
        snippet, parms = build_mount_vex(
            {"measure": "grid_on_face", "face": "+Y", "rows": 3, "cols": 5, "margin": 0.05})
        self.assertIn("addpoint", snippet)  # emits many points
        self.assertEqual(parms["rows"], 3)
        self.assertEqual(parms["cols"], 5)
        self.assertEqual(parms["face_axis"], 1)

    def test_orient_fragment_emitted_for_orient_spec(self):
        from edini.vex_strategies import _orient_fragment
        frag = _orient_fragment({
            "from_a": {"measure": "bbox_corner", "axes": "-X-Y-Z"},
            "from_b": {"measure": "bbox_corner", "axes": "+X-Y-Z"}})
        self.assertIn("dihedral", frag)        # the +Y→dir quaternion
        self.assertIn("{0,1,0}", frag)         # the leaf's built axis

    def test_orient_fragment_writes_point_class_orient(self):
        """The orient must be written as a POINT attribute via setpointattrib,
        NOT a bare p@orient= in the detail wrangle body. copytopoints::2.0
        only reads point-class orient; a detail-class orient (what a bare
        p@orient= in a detail wrangle produces) is silently ignored."""
        from edini.vex_strategies import _orient_fragment
        frag = _orient_fragment({
            "from": "root",
            "from_a": {"measure": "bbox_corner", "axes": "-X-Y+Z"},
            "from_b": {"measure": "bbox_corner", "axes": "+X-Y+Z"}})
        # The point-class contract: orient is written via setpointattrib.
        self.assertIn('setpointattrib(geoself(), "orient"', frag)
        # The bug we're fixing: a bare p@orient = assignment in the body.
        self.assertNotIn("p@orient = ", frag)

    def test_orient_fragment_pscale_like_attrs_use_setpointattrib(self):
        """The same point-class rule applies to any per-instance attribute the
        orient fragment sets. Today only orient, but the contract is: NO bare
        p@/f@ assignments in the detail-wrangle orient fragment."""
        from edini.vex_strategies import _orient_fragment
        frag = _orient_fragment({
            "from": "root",
            "from_a": {"measure": "bbox_corner", "axes": "-X-Y+Z"},
            "from_b": {"measure": "bbox_corner", "axes": "+X-Y+Z"}})
        import re
        bare_exports = re.findall(r'\b[fp]@\w+\s*=', frag)
        self.assertEqual(bare_exports, [],
                         f"orient fragment has bare attribute exports: {bare_exports}")

    def test_orient_fragment_align_axis_z_injects_z_basis(self):
        """align_axis='+Z' must inject {0,0,1} as the dihedral source axis —
        this is the torus-wheel case (torus symmetry axis is +Z)."""
        from edini.vex_strategies import _orient_fragment
        frag = _orient_fragment({
            "from": "root",
            "from_a": {"measure": "bbox_corner", "axes": "-X-Y+Z"},
            "from_b": {"measure": "bbox_corner", "axes": "+X-Y+Z"}},
            align_axis="+Z")
        self.assertIn("dihedral({0,0,1}", frag)

    def test_orient_fragment_default_align_axis_is_y(self):
        """Without align_axis, the source axis stays {0,1,0} (backward compat)."""
        from edini.vex_strategies import _orient_fragment
        frag = _orient_fragment({
            "from": "root",
            "from_a": {"measure": "bbox_corner", "axes": "-X-Y+Z"},
            "from_b": {"measure": "bbox_corner", "axes": "+X-Y+Z"}})
        self.assertIn("dihedral({0,1,0}", frag)

    def test_validation_catches_cyclic_param_via_dangling(self):
        """A leaf scale referencing an undeclared param is rejected."""
        a = _car_assembly()
        a["leaves"][0]["scale"] = "undeclared_param"
        r = validate_assembly(a)
        self.assertFalse(r["success"])
        self.assertTrue(any(e["code"] == "PARAM_REF_DANGLING" for e in r["errors"]))


# ── M1: grid_on_face + array ───────────────────────────────────────


def _keyboard_assembly(tray_width=4.0, tray_depth=1.5, rows=3, cols=5):
    """A keyboard: a box tray (root) + a key grid on its +Y face. One leaf
    definition fans out to rows*cols key instances via grid_on_face. Nothing
    hardcoded — the grid samples the tray's measured top face."""
    return {
        "id": "keyboard",
        "params": {
            "tray_width": tray_width, "tray_depth": tray_depth,
            "tray_thick": 0.1, "key_size": 0.2, "key_height": 0.08,
        },
        "root": {"shape": {"type": "box", "params": {
            "size": ["tray_width", "tray_thick", "tray_depth"]}}},
        "mounts": [
            {"id": "keys", "position": {
                "measure": "grid_on_face", "from": "root", "face": "+Y",
                "rows": rows, "cols": cols, "margin": 0.05}},
        ],
        "leaves": [
            {"id": "key", "mount": "keys",
             "shape": {"type": "box", "params": {
                 "size": ["key_size", "key_height", "key_size"]}}},
        ],
    }


def _staircase_assembly(treads=5):
    """A staircase: treads march up diagonally via an array. The array's origin
    is a measured feature of the root (here a plain box base), and each step
    climbs in Y while advancing in X — a single step vector moving diagonally."""
    return {
        "id": "stairs",
        "params": {"base_w": 3.0, "base_h": 0.2, "base_d": 1.0,
                   "tread_w": 0.6, "tread_h": 0.05, "tread_d": 0.25,
                   "rise": 0.3, "run": 0.5},
        "root": {"shape": {"type": "box", "params": {
            "size": ["base_w", "base_h", "base_d"]}}},
        "mounts": [
            {"id": "treads", "position": {
                "measure": "array", "from": "root",
                "origin": {"measure": "bbox_face_center", "face": "+Y"},
                "count": [treads, 1, 1],
                "step": [["run", "rise", 0], [0, 0, 0], [0, 0, 0]]}},
        ],
        "leaves": [
            {"id": "tread", "mount": "treads",
             "shape": {"type": "box", "params": {
                 "size": ["tread_w", "tread_h", "tread_d"]}}},
        ],
    }


class TestKeyboardGrid(unittest.TestCase):
    """The keyboard's geometry correctness (15 keys on the tray face, rescaling
    with tray width) is verified in hython against the Python oracle. Here we
    pin the validation + the VEX strategy resolution that the mock can reach."""

    def test_keyboard_validates(self):
        r = validate_assembly(_keyboard_assembly())
        self.assertTrue(r["success"], r["errors"])

    def test_grid_mount_vex_resolves_rows_cols(self):
        from edini.vex_strategies import build_mount_vex
        snippet, parms = build_mount_vex(_keyboard_assembly(rows=3, cols=5)["mounts"][0]["position"])
        self.assertEqual(parms["rows"], 3)
        self.assertEqual(parms["cols"], 5)
        self.assertIn("addpoint", snippet)  # emits many points in a double loop

    def test_bad_grid_rejected(self):
        a = _keyboard_assembly()
        a["mounts"][0]["position"]["rows"] = 0  # must be >= 1
        r = validate_assembly(a)
        self.assertFalse(r["success"])
        self.assertTrue(any(e["code"] == "MOUNT_BAD_GRID" for e in r["errors"]))


class TestStaircaseArray(unittest.TestCase):
    """The staircase's diagonal-climb geometry is verified in hython. Here we
    pin validation + array-strategy resolution."""

    def test_staircase_validates(self):
        r = validate_assembly(_staircase_assembly())
        self.assertTrue(r["success"], r["errors"])

    def test_array_vex_resolves_count(self):
        from edini.vex_strategies import build_mount_vex
        a = _staircase_assembly(treads=3)
        snippet, parms = build_mount_vex(a["mounts"][0]["position"])
        self.assertEqual(parms["countx"], 3)
        self.assertIn("addpoint", snippet)

    def test_bad_array_count_rejected(self):
        a = _staircase_assembly()
        a["mounts"][0]["position"]["count"] = [0, 1, 1]  # zero count
        r = validate_assembly(a)
        self.assertFalse(r["success"])
        self.assertTrue(any(e["code"] == "MOUNT_BAD_ARRAY" for e in r["errors"]))

    def test_bad_array_step_shape_rejected(self):
        a = _staircase_assembly()
        a["mounts"][0]["position"]["step"] = [[1, 2], [0, 0, 0], [0, 0, 0]]  # 2-vec
        r = validate_assembly(a)
        self.assertFalse(r["success"])
        self.assertTrue(any(e["code"] == "MOUNT_BAD_ARRAY" for e in r["errors"]))


# setUpClass for the keyboard/stairs BUILD tests (they need the mock hou like
# the structure test does). Re-use the same flush-and-reimport contract.
class TestM1Builds(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._saved_ref = MockNode._hou_ref
        cls._saved_mod = sys.modules.get("hou")
        cls._hou = create_mock_hou()
        sys.modules["hou"] = cls._hou
        MockNode._hou_ref = cls._hou
        for _m in list(sys.modules):
            if _m.startswith("edini"):
                del sys.modules[_m]
        from edini import assembly_builder  # noqa: E402
        cls.build_assembly = staticmethod(assembly_builder.build_assembly)

    @classmethod
    def tearDownClass(cls):
        MockNode._hou_ref = cls._saved_ref
        sys.modules["hou"] = cls._saved_mod
        for _m in list(sys.modules):
            if _m.startswith("edini"):
                del sys.modules[_m]
        super().tearDownClass()

    def test_keyboard_builds_live_structure(self):
        """M2: the keyboard builds a live network — a grid mount wrangle + a
        single key shape + one copytopoints (the fan-out happens at cook time
        via the point count, not via N xform nodes). The grid count is read
        from the wrangle's rows/cols spare parms (no longer a baked count)."""
        hou = sys.modules["hou"]
        a = _keyboard_assembly(rows=2, cols=3)
        root = hou.node("/obj").createNode("geo", "kb2")
        res = self.build_assembly(a, root.path())
        self.assertTrue(res["success"], res.get("error"))
        self.assertTrue(res["live"])
        names = {c.name() for c in hou.node(root.path()).children()}
        # Live structure: root + 1 grid mount wrangle + key shape + key CTP + OUT.
        self.assertIn("mount_keys", names)
        self.assertIn("key_shape", names)
        self.assertIn("key_ctp", names)
        self.assertIn("OUT", names)
        # NO per-position xform nodes — the fan-out is via CTP, not N xforms.
        self.assertNotIn("key_0_xform", names)


if __name__ == "__main__":
    unittest.main()
