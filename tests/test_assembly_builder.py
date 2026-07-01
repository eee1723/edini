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
        wrangle per scaled leaf-mount + one copytopoints per leaf GROUP + OUT.
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
        # Grouped CTP: 4 identical wheels share ONE wheel_fr_ctp (the group's
        # representative leaf id) stamping the merged cloud of their mounts
        # (wheel_fr_cloud). The mounts themselves are NOT merged; only their
        # CLOUD is.
        self.assertIn("wheel_fr_cloud", names)
        self.assertIn("wheel_fr_ctp", names)
        self.assertNotIn("wheel_fl_ctp", names)
        # With all 4 wheels collapsed into ONE group, there is only a single
        # CTP output — so no final merge_all is needed (CTP → OUT directly).
        self.assertNotIn("merge_all", names)
        self.assertIn("OUT", names)

    def test_build_returns_commit_and_live_param_contract(self):
        """The build result must carry everything an agent needs to go end-to-end
        without scanning the container: ``sandbox_root_path`` (commit_sandbox's
        exact key — no rename needed), ``sandbox_root`` (same path, legacy key),
        ``out_path`` (feed to inspect_health/inventory/capture), and
        ``live_params`` (the editable spare parm names — so the agent knows what
        to tweak to re-verify the live guarantee). This is the contract the
        end-to-end Pi-agent path depends on; see the rooted-modeling skill."""
        root_path, res = self._build(_car_assembly())
        self.assertTrue(res["success"], res.get("error"))
        # commit_sandbox reads kw["sandbox_root_path"] — it must be present.
        self.assertEqual(res["sandbox_root_path"], root_path)
        # Legacy key kept for back-compat; same path.
        self.assertEqual(res["sandbox_root"], root_path)
        # out_path for the verify step.
        self.assertTrue(res["out_path"].endswith("/OUT"))
        # live_params = the assembly's params (length/width/...), exposed so the
        # agent can tweak one and re-verify the model moves live.
        self.assertEqual(set(res["live_params"]),
                         {"length", "width", "thickness",
                          "wheel_radius", "wheel_tube_r"})

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


def _cells_keyboard_assembly():
    """A REAL keyboard layout via the `cells` strategy: keys of DIFFERENT sizes
    (a 6.25u spacebar + 1u keys) on a 1u-unit grid, with a QWERTY-style stagger.
    The physical unit is DERIVED from the root's span so the layout FILLS the
    root and rescales when the root resizes. The leaf is a 1u BASIS shape
    (size [1, height, 1]); each cell's per-point v@scale (physical w*unit_x,
    d*unit_z) grows it to the cell's footprint. One leaf → one CTP → many sizes.
    This is what the uniform grid_on_face strategy CANNOT express."""
    return {
        "id": "cells_keyboard",
        "params": {
            "tray_w": 16.0, "tray_d": 6.0, "tray_h": 0.4,
            "key_height": 0.4,
        },
        "root": {"shape": {"type": "box", "params": {
            "size": ["tray_w", "tray_h", "tray_d"]}}},
        "mounts": [
            {"id": "keys", "position": {
                "measure": "cells", "from": "root", "face": "+Y",
                "margin": 0.5,
                "cells": [
                    # row 0 (back row): a few 1u keys
                    {"gx": 0, "gz": 0, "w": 1, "d": 1},
                    {"gx": 1, "gz": 0, "w": 1, "d": 1},
                    {"gx": 2, "gz": 0, "w": 1, "d": 1},
                    # row 1: staggered by 0.5u (QWERTY offset)
                    {"gx": 0.5, "gz": 1, "w": 1, "d": 1},
                    {"gx": 1.5, "gz": 1, "w": 1, "d": 1},
                    # bottom row: a 6.25u spacebar
                    {"gx": 0, "gz": 4, "w": 6.25, "d": 1},
                ]}},
        ],
        # The leaf is a 1u BASIS box. Its X/Z footprint is 1 unit; the per-cell
        # v@scale (w*unit_x, d*unit_z) grows it to the cell's physical footprint.
        # Height (key_height) is the leaf's own property, untouched by scale.
        "leaves": [
            {"id": "key", "mount": "keys",
             "shape": {"type": "box", "params": {
                 "size": [1, "key_height", 1]}}},   # 1u basis; v@scale grows it
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


class TestOriginNormalization(unittest.TestCase):
    """A leaf with an `origin` spec gets a normalize wrangle between its shape
    and CTP that moves the chosen anchor point to the origin (+ optional
    offset), so the leaf lands clear of the root."""

    # NOTE on isolation: assembly_builder binds its module-level `hou` global at
    # import time. The top-of-file import (line 28) pulled it in with hou=None,
    # so we must flush the edini modules and re-import AFTER installing the
    # mock — the same flush-and-reimport contract TestBuildAssemblyStructure /
    # TestM1Builds use. The mock install happens once per class.
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
        root = hou.node("/obj").createNode("geo", "test_origin")
        res = self.build_assembly(assembly, root.path(),
                                  root_geometry_provider=_box_provider)
        return root.path(), res

    def test_leaf_without_origin_has_no_normalize_node(self):
        """Backward compat: a leaf without `origin` builds exactly as before —
        no extra normalize wrangle in the network."""
        asm = _car_assembly()  # car leaves have no `origin`
        root_path, res = self._build(asm)
        self.assertTrue(res["success"], res.get("error"))
        hou = sys.modules["hou"]
        names = {c.name() for c in hou.node(root_path).children()}
        self.assertFalse(any(n.endswith("_normalize") for n in names),
                         f"unexpected normalize node(s): {[n for n in names if n.endswith('_normalize')]}")

    def test_leaf_with_origin_inserts_normalize_wrangle(self):
        """A leaf declaring origin=bbox_center gets a <leaf>_normalize wrangle
        between its shape and its CTP, whose snippet subtracts the bbox center
        and adds the offset. The offset is inlined as a literal (numbers) or
        ch() refs (param names) — M2.6: no longer uses a chv("offset") spare,
        so the offset tracks the container's params live."""
        asm = _car_assembly()
        # Annotate the first wheel with an origin spec.
        asm["leaves"][0]["origin"] = {"anchor": "bbox_center", "offset": [0, 0, 0.2]}
        root_path, res = self._build(asm)
        self.assertTrue(res["success"], res.get("error"))
        hou = sys.modules["hou"]
        names = {c.name() for c in hou.node(root_path).children()}
        self.assertIn("wheel_fr_normalize", names)
        snip = hou.node(f"{root_path}/wheel_fr_normalize").parm("snippet").eval()
        self.assertIn("getbbox_center", snip)
        self.assertIn("@P -=", snip)
        # offset inlined as set(x, y, z) — the literal 0.2 appears.
        self.assertIn("@P += set(0, 0, 0.2)", snip)

    def test_leaf_origin_offset_param_expr_becomes_ch_ref(self):
        """M2.6: an offset component that is a param-name/expression becomes a
        ch("../<name>") reference in the VEX, so the offset tracks the param
        live (not a baked number)."""
        asm = _car_assembly()
        asm["leaves"][0]["origin"] = {
            "anchor": "bbox_center", "offset": [0, 0, "wheel_radius*0.5"]}
        root_path, res = self._build(asm)
        self.assertTrue(res["success"], res.get("error"))
        hou = sys.modules["hou"]
        snip = hou.node(f"{root_path}/wheel_fr_normalize").parm("snippet").eval()
        # wheel_radius*0.5 → ch("../wheel_radius")*0.5
        self.assertIn('ch("../wheel_radius")', snip)
        self.assertNotIn("0.2", snip)  # not the baked default

    def test_leaf_origin_face_anchor_uses_face_center(self):
        """anchor='bbox_face:-Y' subtracts the -Y face center so the leaf's
        base sits on the mount and the body hangs in +Y."""
        asm = _car_assembly()
        asm["leaves"][0]["origin"] = {"anchor": "bbox_face:-Y"}
        root_path, res = self._build(asm)
        self.assertTrue(res["success"], res.get("error"))
        hou = sys.modules["hou"]
        snip = hou.node(f"{root_path}/wheel_fr_normalize").parm("snippet").eval()
        # Face center is computed from bbox min on the chosen axis.
        self.assertIn("getbbox_min", snip)
        self.assertIn("getbbox_max", snip)


class TestGroupedCTP(unittest.TestCase):
    """N structurally-identical leaves (same shape+scale+origin) must share
    ONE shape node + ONE CTP, stamping onto the merged cloud of their mounts —
    not N independent shape+CTP chains."""

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
        import sys
        hou = sys.modules["hou"]
        root = hou.node("/obj").createNode("geo", "test_group")
        from edini.assembly_builder import build_assembly
        res = build_assembly(assembly, root.path())
        return root.path(), res

    def test_four_identical_wheels_produce_one_ctp(self):
        """The car's 4 torus wheels are structurally identical → 1 CTP node
        (not 4). The single CTP stamps onto the merged cloud of all 4 mounts."""
        root_path, res = self._build(_car_assembly())
        self.assertTrue(res["success"], res.get("error"))
        hou = sys.modules["hou"]
        names = {c.name() for c in hou.node(root_path).children()}
        ctp_nodes = [n for n in names if n.endswith("_ctp")]
        self.assertEqual(len(ctp_nodes), 1,
                         f"expected 1 grouped CTP, got {ctp_nodes}")
        # The 4 mounts still exist (grouping merges their CLOUD, not the mounts).
        for c in ("fr", "fl", "br", "bl"):
            self.assertIn(f"mount_wheel_{c}", names)

    def test_different_shapes_stay_separate(self):
        """Two leaves with different shape params do NOT group — each keeps its
        own CTP (grouping must be exact)."""
        asm = _car_assembly()
        asm["leaves"][0]["shape"]["params"]["radx"] = 2.0  # different radius
        root_path, res = self._build(asm)
        self.assertTrue(res["success"], res.get("error"))
        hou = sys.modules["hou"]
        names = {c.name() for c in hou.node(root_path).children()}
        ctp_nodes = [n for n in names if n.endswith("_ctp")]
        self.assertGreaterEqual(len(ctp_nodes), 2,
                                f"different shapes must not group: {ctp_nodes}")


class TestLeafParamsLive(unittest.TestCase):
    """M2.6 leaf-live fix: leaf shape params, leaf scale, and origin offset are
    now wired as ch("../<name>") references (not baked numbers), so EVERY param
    in live_params actually moves when changed. This regression class pins the
    contract the Pi-agent end-to-end test surfaced (a car where wheel_radius /
    cabin_length did nothing when tweaked)."""

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
        root = hou.node("/obj").createNode("geo", "test_leaflive")
        res = self.build_assembly(assembly, root.path(),
                                  root_geometry_provider=_provider_for(assembly))
        return root.path(), res

    def _car_with_leaf_params(self):
        """A car whose leaf shape CARRIES param expressions (the real-agent
        fixture has rady='wheel_tube_r'; the default _car_assembly leaves leaf
        params empty for the mock). This is the case that broke live."""
        asm = _car_assembly()
        for lf in asm["leaves"]:
            lf["shape"]["params"] = {
                "radx": 1.0, "rady": "wheel_tube_r", "rows": 24, "cols": 12}
        return asm

    def test_leaf_shape_param_becomes_ch_ref(self):
        """A leaf shape param that is a param-name string (e.g. wheel_tube_r)
        becomes a ch("../wheel_tube_r") expression on the shape node, NOT a
        baked number."""
        asm = self._car_with_leaf_params()
        root_path, res = self._build(asm)
        self.assertTrue(res["success"], res.get("error"))
        hou = sys.modules["hou"]
        # The grouped wheel shape node (wheel_fr is the representative id).
        shape = hou.node(f"{root_path}/wheel_fr_geoshape")
        rady_parm = shape.parm("rady")
        # setExpression was called with ch("../wheel_tube_r") (mock records it).
        self.assertTrue(rady_parm.hasExpression(),
                        "leaf shape rady should carry a ch() expression")
        self.assertIn('ch("../wheel_tube_r")', rady_parm.expression())
        # And NOT the baked default value (0.08).
        self.assertNotIn("0.08", rady_parm.expression())

    def test_leaf_scale_becomes_ch_ref(self):
        """A leaf scale that is a param-name string becomes a ch("../<name>")
        reference in the pscale wrangle's VEX, not a baked float."""
        asm = _car_assembly()  # scale: "wheel_radius"
        root_path, res = self._build(asm)
        self.assertTrue(res["success"], res.get("error"))
        hou = sys.modules["hou"]
        names = {c.name() for c in hou.node(root_path).children()}
        pscale_nodes = [n for n in names if n.endswith("_pscale")]
        self.assertTrue(pscale_nodes, "expected a pscale wrangle for scaled leaf")
        snip = hou.node(f"{root_path}/{pscale_nodes[0]}").parm("snippet").eval()
        self.assertIn('ch("../wheel_radius")', snip)
        # Not the baked default (0.4).
        self.assertNotIn("f@pscale = 0.4", snip)

    def test_all_params_reported_live_are_actually_wired(self):
        """The contract the Pi-agent test broke: every name in live_params must
        appear as at least one ch("../<name>") reference SOMEWHERE in the built
        network (root shape, a leaf shape, a pscale wrangle, or an offset).
        Build a car with leaf shape + scale params and assert each live_param
        is referenced via ch() in some node's expression/snippet."""
        asm = self._car_with_leaf_params()
        root_path, res = self._build(asm)
        self.assertTrue(res["success"], res.get("error"))
        hou = sys.modules["hou"]
        live_params = res["live_params"]
        # Collect all ch("../<name>") refs across the network.
        refs_found = set()
        for child in hou.node(root_path).allSubChildren():
            for pname_obj in (child.parms() if hasattr(child, "parms") else []):
                expr = getattr(pname_obj, "expression", lambda: "")()
                if expr:
                    import re
                    refs_found.update(re.findall(r'ch\("\.\./([^"]+)"\)', expr))
            # Also scan wrangle snippets for ch() refs.
            snip_parm = child.parm("snippet") if hasattr(child, "parm") else None
            if snip_parm is not None:
                snip = snip_parm.eval()
                if isinstance(snip, str):
                    import re
                    refs_found.update(re.findall(r'ch\("\.\./([^"]+)"\)', snip))
        for p in live_params:
            self.assertIn(p, refs_found,
                          f"live_param {p!r} is reported live but has no "
                          f"ch('../{p}') reference anywhere in the network")


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


class TestCellsLayout(unittest.TestCase):
    """The `cells` strategy — an explicit unit-grid layout where each cell has
    its OWN size (the keyboard-keys strategy done right: a 6.25u spacebar +
    1u keys + staggered rows, all from one 1u leaf via per-point v@scale).
    Geometry correctness (per-key bbox sizes) is the hython test's job; here we
    pin validation + VEX strategy resolution + build structure."""

    def test_cells_assembly_validates(self):
        r = validate_assembly(_cells_keyboard_assembly())
        self.assertTrue(r["success"], r["errors"])

    def test_cells_vex_resolves_face_and_derives_unit_from_bbox(self):
        """The cells VEX must write per-point v@scale via setpointattrib (so CTP
        stamps differently-sized keys from one leaf), resolve the +Y face, AND
        DERIVE the per-axis unit from the bbox (no `unit` spare — it's a live
        function of the root's span, so the layout FILLS the root)."""
        from edini.vex_strategies import build_mount_vex
        a = _cells_keyboard_assembly()
        snippet, parms = build_mount_vex(a["mounts"][0]["position"])
        # Face resolved: +Y → face_axis=1 (Y), face_sign=1 (positive).
        self.assertEqual(parms["face_axis"], 1)
        self.assertEqual(parms["face_sign"], 1)
        # margin + gap are the cells live spares. NO _unit signal — unit is
        # derived in-VEX from the bbox.
        self.assertNotIn("_unit", parms)
        self.assertEqual(parms["_margin"], 0.5)
        self.assertEqual(parms["_gap"], 0.0)   # default gap (keys touch)
        # THE measurement-driven core: unit derived from bbox span / layout span.
        self.assertIn("__u0 = __span0 /", snippet)
        self.assertIn("__u1 = __span1 /", snippet)
        # The per-cell scale write: setpointattrib "scale" on each point.
        self.assertIn('setpointattrib(geoself(), "scale"', snippet)
        # THE COMPACT-LOOP design: the layout table is encoded as VEX array
        # literals (data) + a SINGLE loop processes every cell (code). So there
        # is exactly ONE addpoint call in the VEX regardless of cell count
        # (was N calls with the old loop-unrolling). This decouples data from
        # code — the same loop body handles any tabular (position, size) layout.
        self.assertEqual(snippet.count("addpoint(geoself()"), 1)
        # The spacebar's 6.25 width appears as an array element (in __cw).
        self.assertIn("6.25", snippet)
        # The array literals are present (one per field: cx/cz/cw/cd).
        self.assertIn("__cx[] = {", snippet)
        self.assertIn("__cw[] = {", snippet)

    def test_cells_unit_field_is_optional_now(self):
        """The legacy `unit` field is accepted (backward compat) but no longer
        required — the unit is derived from the bbox. An assembly without it
        still validates."""
        a = _cells_keyboard_assembly()
        self.assertNotIn("unit", a["mounts"][0]["position"])  # fixture has none
        r = validate_assembly(a)
        self.assertTrue(r["success"], r["errors"])

    def test_bad_cells_empty_table_rejected(self):
        a = _cells_keyboard_assembly()
        a["mounts"][0]["position"]["cells"] = []
        r = validate_assembly(a)
        self.assertFalse(r["success"])
        self.assertTrue(any(e["code"] == "MOUNT_BAD_CELLS" for e in r["errors"]))

    def test_bad_cell_zero_width_rejected(self):
        a = _cells_keyboard_assembly()
        a["mounts"][0]["position"]["cells"][0]["w"] = 0
        r = validate_assembly(a)
        self.assertFalse(r["success"])
        self.assertTrue(any(e["code"] == "MOUNT_BAD_CELLS" for e in r["errors"]))

    def test_square_and_fill_validate(self):
        """square (bool) + fill (stretch|pad|repeat) are accepted by validation."""
        a = _cells_keyboard_assembly()
        a["mounts"][0]["position"]["square"] = True
        a["mounts"][0]["position"]["fill"] = "pad"
        r = validate_assembly(a)
        self.assertTrue(r["success"], r["errors"])

    def test_bad_fill_rejected(self):
        a = _cells_keyboard_assembly()
        a["mounts"][0]["position"]["fill"] = "bogus"
        r = validate_assembly(a)
        self.assertFalse(r["success"])
        self.assertTrue(any(e["code"] == "MOUNT_BAD_CELLS" for e in r["errors"]))

    def test_bad_square_type_rejected(self):
        a = _cells_keyboard_assembly()
        a["mounts"][0]["position"]["square"] = "yes"   # not a bool
        r = validate_assembly(a)
        self.assertFalse(r["success"])
        self.assertTrue(any(e["code"] == "MOUNT_BAD_CELLS" for e in r["errors"]))

    def test_square_vex_uses_min_unit(self):
        """square=True → the VEX unifies unit to min(unit0, unit1) so 1u cells
        stay square. stretch (default) → independent per-axis (may deform)."""
        from edini.vex_strategies import build_mount_vex
        spec = {"measure": "cells", "face": "+Y", "margin": 0.0,
                "cells": [{"gx": 0, "gz": 0, "w": 1, "d": 1}]}
        stretch_snip, _ = build_mount_vex(spec)
        square_snip, _ = build_mount_vex({**spec, "square": True})
        # stretch: independent units (no min).
        self.assertIn("__u0 = __span0 /", stretch_snip)
        self.assertNotIn("min(__u0raw", stretch_snip)
        # square: unified to min.
        self.assertIn("min(__u0raw", square_snip)

    def test_repeat_expands_cell_table(self):
        """fill=repeat → the builder pre-expands the cell table with 1u fillers
        so the layout fills the larger axis. A layout spanning 2u×2u but with an
        empty grid slot gets a 1u filler added to fill it."""
        from edini.assembly_builder import _expand_repeat_cells
        # cell A (gx:0,gz:0,w:2,d:1) covers slots (0,0)+(1,0);
        # cell B (gx:0,gz:1,w:1,d:1) covers (0,1). The 2×2 region's empty slot
        # is (1,1) → exactly one 1u filler is added.
        cells = [{"gx": 0, "gz": 0, "w": 2, "d": 1},
                 {"gx": 0, "gz": 1, "w": 1, "d": 1}]
        expanded = _expand_repeat_cells(cells)
        self.assertEqual(len(expanded), 3)   # 2 declared + 1 filler
        # The filler fills the only empty slot (1,1).
        fillers = [c for c in expanded
                   if c not in cells or {"gx": c["gx"], "gz": c["gz"],
                                         "w": c["w"], "d": c["d"]} not in cells]
        filler_slots = sorted((c["gx"], c["gz"]) for c in expanded
                              if (c["gx"], c["gz"]) not in
                              [(cc["gx"], cc["gz"]) for cc in cells])
        self.assertEqual(filler_slots, [(1.0, 1.0)])

    def test_strategy_class_hierarchy_exists(self):
        """The three-layer architecture: VexStrategy → StaticTemplateStrategy /
        TabularFillStrategy → CellsStrategy. All 7 measure kinds dispatch
        through the strategy registry (no raw if/elif chain in build_mount_vex)."""
        from edini.vex_strategies import (VexStrategy, StaticTemplateStrategy,
                                          TabularFillStrategy, CellsStrategy)
        # Static kinds are StaticTemplateStrategy instances.
        from edini.vex_strategies import _STATIC_STRATEGIES
        self.assertTrue(all(isinstance(s, StaticTemplateStrategy)
                            for s in _STATIC_STRATEGIES.values()))
        # CellsStrategy is a TabularFillStrategy (and thus a VexStrategy).
        self.assertTrue(issubclass(CellsStrategy, TabularFillStrategy))
        self.assertTrue(issubclass(TabularFillStrategy, VexStrategy))
        self.assertEqual(len(_STATIC_STRATEGIES), 6)   # the 6 static kinds

    def test_cells_2d_byte_identical_after_axes_refactor(self):
        """After generalizing _build_vex to axes[], the 2D cells path must keep
        producing the SAME VEX variable names + structure (the regression gate
        for the base-class refactor). Existing tests pin __u0/__span0 etc.; this
        test adds a structural snapshot so a careless axes[] generalization that
        renames the 2D variables is caught immediately."""
        from edini.vex_strategies import build_mount_vex
        a = _cells_keyboard_assembly()
        snippet, parms = build_mount_vex(a["mounts"][0]["position"])
        # The measurement-driven core variable names (pinned by other tests too,
        # but asserted here as a block for the refactor's safety net).
        self.assertIn("__u0 = __span0 /", snippet)
        self.assertIn("__u1 = __span1 /", snippet)
        # The compact-loop invariants (data/code decoupling).
        self.assertEqual(snippet.count("addpoint(geoself()"), 1)
        self.assertIn('setpointattrib(geoself(), "scale"', snippet)
        # The layout table arrays (one per field).
        self.assertIn("__cx[] = {", snippet)
        self.assertIn("__cz[] = {", snippet)
        self.assertIn("__cw[] = {", snippet)
        self.assertIn("__cd[] = {", snippet)
        # margin + gap remain live spares (not baked).
        self.assertEqual(parms["_margin"], 0.5)
        self.assertEqual(parms["_gap"], 0.0)


class TestPicketsLayout(unittest.TestCase):
    """The `pickets` strategy — a 1D row of equal-width (or explicit-width)
    pickets along ONE in-plane axis of a face (the fence / baluster strategy).
    Geometry correctness (point-by-point match to measure_pickets) is the
    hython test's job; here we pin validation + the VEX strategy resolution."""

    def test_pickets_count_validates(self):
        a = {"id": "fence",
             "root": {"shape": {"type": "box", "params": {"size": [4, 0.5, 1]}}},
             "mounts": [{"id": "pickets", "position": {
                 "measure": "pickets", "from": "root",
                 "basis": {"face": "+Y"}, "axes": ["X"], "count": 8}}],
             "leaves": [{"id": "post", "mount": "pickets",
                 "shape": {"type": "box", "params": {"size": [0.1, 1.0, 0.1]}}}]}
        r = validate_assembly(a)
        self.assertTrue(r["success"], r["errors"])

    def test_pickets_bad_count_rejected(self):
        a = {"id": "fence",
             "root": {"shape": {"type": "box", "params": {"size": [4, 0.5, 1]}}},
             "mounts": [{"id": "pickets", "position": {
                 "measure": "pickets", "count": 0}}],
             "leaves": []}
        r = validate_assembly(a)
        self.assertFalse(r["success"])
        self.assertTrue(any("count" in str(e.get("message", "")) for e in r["errors"]))

    def test_pickets_vex_one_axis_row(self):
        """PicketStrategy produces a 1D-effective row via the degenerate-2nd-axis
        trick: the inherited _build_vex runs with gz=0/d=1, so all points share
        the same z. The VEX still has ONE addpoint + setpointattrib scale."""
        from edini.vex_strategies import build_mount_vex
        spec = {"measure": "pickets", "face": "+Y", "axes": ["X"],
                "cells": [{"gx": 0, "w": 1}, {"gx": 1, "w": 1}]}
        snippet, parms = build_mount_vex(spec)
        self.assertEqual(snippet.count("addpoint(geoself()"), 1)
        self.assertIn('setpointattrib(geoself(), "scale"', snippet)


class TestTilesLayout(unittest.TestCase):
    """The `tiles` strategy — a 2D tile mosaic. Cells carry {gx,gz,w,d, rot?}.
    rot (degrees) rotates each tile about the face normal → per-cell p@orient
    (CTP reads it). A mount-level `orient` rule (herringbone/checker/running)
    supplies rot for cells without explicit rot."""

    def test_tiles_validates(self):
        a = {"id": "floor",
             "root": {"shape": {"type": "box", "params": {"size": [4, 0.1, 4]}}},
             "mounts": [{"id": "tiles", "position": {
                 "measure": "tiles", "from": "root", "face": "+Y",
                 "cells": [{"gx":0,"gz":0,"w":1,"d":1,"rot":90},
                           {"gx":1,"gz":0,"w":1,"d":1}]}}],
             "leaves": [{"id": "tile", "mount": "tiles",
                 "shape": {"type": "box", "params": {"size": [0.9, 0.05, 0.9]}}}]}
        r = validate_assembly(a)
        self.assertTrue(r["success"], r["errors"])

    def test_tiles_vex_writes_per_cell_orient_when_rot_present(self):
        """When a cell has rot, the VEX emits __rot[] + setpointattrib orient."""
        from edini.vex_strategies import build_mount_vex
        spec = {"measure": "tiles", "face": "+Y",
                "cells": [{"gx":0,"gz":0,"w":1,"d":1,"rot":90}]}
        snippet, parms = build_mount_vex(spec)
        self.assertIn("__rot[]", snippet)
        self.assertIn('setpointattrib(geoself(), "orient"', snippet)

    def test_tiles_vex_no_orient_when_no_rot(self):
        """When NO cell has rot, the VEX does NOT emit orient (mirrors cells)."""
        from edini.vex_strategies import build_mount_vex
        spec = {"measure": "tiles", "face": "+Y",
                "cells": [{"gx":0,"gz":0,"w":1,"d":1}]}  # no rot anywhere
        snippet, parms = build_mount_vex(spec)
        self.assertNotIn('setpointattrib(geoself(), "orient"', snippet)

    def test_cells_still_no_orient(self):
        """REGRESSION: the existing cells strategy must NOT emit orient VEX
        (the per-cell orient addition is gated on _rot_vals)."""
        from edini.vex_strategies import build_mount_vex
        spec = {"measure": "cells", "face": "+Y",
                "cells": [{"gx":0,"gz":0,"w":1,"d":1}]}
        snippet, parms = build_mount_vex(spec)
        self.assertNotIn('setpointattrib(geoself(), "orient"', snippet)


class TestShelfLayout(unittest.TestCase):
    """The `shelf` strategy — a 3D layered layout (bookshelf). Layers stack along
    the face's NORMAL axis; each layer has a height (1u) + within-layer cells.
    ShelfStrategy flattens layers first (via _expand_shelf_layers), then the
    inherited TabularFill loop runs per cell, and _build_vex appends a shelf
    fragment (gated on self._shelf_layers) that overrides each point's face-axis
    position + scale with the layer-derived values. Geometry correctness
    (layer-1 higher than layer-0) is the hython test's job; here we pin
    validation + the VEX strategy resolution + the cells-no-fragment regression."""

    def test_shelf_validates(self):
        a = {"id": "bookcase",
             "root": {"shape": {"type": "box", "params": {"size": [6, 5, 2]}}},
             "mounts": [{"id": "shelves", "position": {
                 "measure": "shelf", "from": "root", "basis": {"face": "+Y"},
                 "axis": "Y",
                 "layers": [
                   {"height": 10, "cells": [{"gx":0,"w":2}, {"gx":2,"w":1}]},
                   {"height": 8,  "cells": [{"gx":0,"w":3}]}]}}],
             "leaves": [{"id": "book", "mount": "shelves",
                 "shape": {"type": "box", "params": {"size": [0.8, 1.0, 0.3]}}}]}
        r = validate_assembly(a)
        self.assertTrue(r["success"], r["errors"])

    def test_shelf_vex_has_layer_arrays(self):
        """ShelfStrategy emits __layer_gy[] + __layer_h[] + a shelf fragment
        that overrides the face-axis position/scale. cells/pickets don't."""
        from edini.vex_strategies import build_mount_vex
        spec = {"measure": "shelf", "face": "+Y", "axis": "Y",
                "layers": [{"height": 10, "cells": [{"gx":0,"w":1}]},
                           {"height": 8,  "cells": [{"gx":0,"w":1}]}]}
        snippet, parms = build_mount_vex(spec)
        self.assertIn("__layer_gy[]", snippet)
        self.assertIn("__layer_h[]", snippet)

    def test_cells_still_no_shelf_fragment(self):
        """REGRESSION: cells VEX must NOT contain the shelf fragment."""
        from edini.vex_strategies import build_mount_vex
        snippet, _ = build_mount_vex({"measure": "cells", "face": "+Y",
            "cells": [{"gx":0,"gz":0,"w":1,"d":1}]})
        self.assertNotIn("__layer_gy[]", snippet)


class TestBlocksLayout(unittest.TestCase):
    """The `blocks` strategy (④ synthesis): 2D footprint + height + optional
    rotation. Composes tiles' rot (→ orient) with a height fragment. Validated
    at the schema level + VEX-structure level here; geometry is hython's job."""

    def test_blocks_validates(self):
        a = {"id": "city",
             "root": {"shape": {"type": "box", "params": {"size": [8, 0.1, 6]}}},
             "mounts": [{"id": "blocks", "position": {
                 "measure": "blocks", "from": "root", "face": "+Y",
                 "cells": [{"gx": 2, "gz": 0, "w": 2, "d": 3, "h": 40},
                           {"gx": 4, "gz": 0, "w": 2, "d": 3, "h": 10, "rot": 0}]}}],
             "leaves": [{"id": "bldg", "mount": "blocks",
                 "shape": {"type": "box", "params": {"size": [1, 1, 1]}}}]}
        r = validate_assembly(a)
        self.assertTrue(r["success"], r["errors"])

    def test_blocks_bad_measure_rejected(self):
        a = {"id": "x",
             "root": {"shape": {"type": "box", "params": {"size": [8, 0.1, 6]}}},
             "mounts": [{"id": "m", "position": {
                 "measure": "blocks", "face": "+Y",
                 "cells": [{"gx": 0, "gz": 0, "w": 0, "d": 1, "h": 10}]}}],  # w<=0
             "leaves": []}
        r = validate_assembly(a)
        self.assertFalse(r["success"])
        self.assertTrue(any(e["code"] == "MOUNT_BAD_BLOCKS" for e in r["errors"]))

    def test_blocks_vex_has_height_and_orient(self):
        """When a cell has both h and rot, the VEX emits BOTH the block-height
        fragment (__block_h/__u_h) AND the orient write. This is the synthesis:
        the two fragments compose independently."""
        from edini.vex_strategies import build_mount_vex
        spec = {"measure": "blocks", "face": "+Y",
                "cells": [{"gx": 0, "gz": 0, "w": 1, "d": 1, "h": 40, "rot": 90}]}
        snippet, parms = build_mount_vex(spec)
        self.assertIn("__block_h[]", snippet)
        self.assertIn("__u_h", snippet)
        self.assertIn('setpointattrib(geoself(), "orient"', snippet)

    def test_blocks_vex_height_only_when_h_present(self):
        """A cell without h does NOT emit the block-height fragment (mirrors how
        tiles-only cells emit no height)."""
        from edini.vex_strategies import build_mount_vex
        spec = {"measure": "blocks", "face": "+Y",
                "cells": [{"gx": 0, "gz": 0, "w": 1, "d": 1, "rot": 90}]}  # no h
        snippet, _ = build_mount_vex(spec)
        self.assertNotIn("__block_h[]", snippet)

    def test_cells_still_no_block_fragment(self):
        """REGRESSION: the existing cells strategy must NOT emit the block
        height fragment (the gate is _block_h_vals, set only by BlockStrategy)."""
        from edini.vex_strategies import build_mount_vex
        snippet, _ = build_mount_vex({"measure": "cells", "face": "+Y",
            "cells": [{"gx": 0, "gz": 0, "w": 1, "d": 1}]})
        self.assertNotIn("__block_h[]", snippet)
        self.assertNotIn("__s3", snippet)


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
        self.assertIn("key_geoshape", names)
        self.assertIn("key_ctp", names)
        self.assertIn("OUT", names)
        # NO per-position xform nodes — the fan-out is via CTP, not N xforms.
        self.assertNotIn("key_0_xform", names)

    def test_cells_keyboard_builds_single_ctp_many_sizes(self):
        """The cells keyboard builds a live network: one cells mount wrangle +
        ONE key shape + ONE CTP (despite 6 differently-sized cells including a
        6.25u spacebar). The per-cell size comes from v@scale on each emitted
        point, which CTP reads per instance — so the size variety does NOT split
        the leaf into multiple groups/CTPs. Geometry-level proof is the hython
        test's job; here we assert the single-CTP structure."""
        hou = sys.modules["hou"]
        a = _cells_keyboard_assembly()
        root = hou.node("/obj").createNode("geo", "ckb")
        res = self.build_assembly(a, root.path())
        self.assertTrue(res["success"], res.get("error"))
        self.assertTrue(res["live"])
        names = {c.name() for c in hou.node(root.path()).children()}
        # One cells mount wrangle + one key shape + one CTP (NOT split by size).
        self.assertIn("mount_keys", names)
        self.assertIn("key_geoshape", names)
        self.assertIn("key_ctp", names)
        self.assertIn("OUT", names)
        # The spacebar (6.25u) does NOT get its own CTP — it shares the one CTP
        # via its per-point v@scale. No second CTP node exists.
        ctp_nodes = [n for n in names if n.endswith("_ctp")]
        self.assertEqual(len(ctp_nodes), 1)
        # The mount wrangle's snippet writes per-point v@scale (the size signal).
        snip = hou.node(f"{root.path()}/mount_keys").parm("snippet").eval()
        self.assertIn('setpointattrib(geoself(), "scale"', snip)


if __name__ == "__main__":
    unittest.main()
