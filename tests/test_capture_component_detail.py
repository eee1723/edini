"""Regression tests for houdini_capture_component_detail.

Primary purpose: lock in the Bug 1 fix (procedural-modeling-bugs.md).

Bug 1 — capture_component_detail failed with "bbox build failed" on every
component in a real Houdini 21 session (7/7 captures failed). Root cause:
`hou.BoundingBox(hou.Vector3(list), hou.Vector3(list))` is finicky on H21
about the sequence type Vector3 unpacks, and the bare `except Exception`
swallowed the real error as the opaque "bbox build failed".

Fix: use the 6-scalar overload `hou.BoundingBox(x0,y0,z0, x1,y1,z1)` and
surface the real exception type/message in the error string.

These tests:
  1. Reproduce the bug at the unit level (bbox construction path) under the
     mock — the old code path raised because the mock had no hou.Vector3.
  2. Verify the new 6-float path builds a bbox that minvec()/maxvec() can
     read back (the contract setViewToBoundingBox needs).
  3. End-to-end: capture_component_detail on a 2-component mock asset
     returns success=True with no "bbox build failed" errors.

To run:  python tests/test_capture_component_detail.py
         python -m unittest tests.test_capture_component_detail
"""

import importlib
import os
import sys
import tempfile
import unittest

from tests.mock_hou import (
    MockNode,
    MockSceneViewer,
    MockVector3,
    MockBoundingBox,
    create_mock_hou,
)


class _PngSceneViewer(MockSceneViewer):
    """MockSceneViewer variant whose flipbook() writes a valid image file.

    The base mock writes `b"mock flipbook"` (invalid image bytes), which is
    fine for tests that only check method/stage fields. capture_component_detail's
    concat-grid step (`_concat_images_grid`) can only produce a real output PNG
    from Pillow-openable captures; when it can't, the code falls back to
    copying the first raw capture. We therefore emit a 4x4 PNG so BOTH the
    concat path AND the file-copy fallback have a usable file to work with,
    exercising the full capture -> output chain.

    Note: the repo bundles a Pillow build under python3.11libs/PIL that may be
    compiled for a different CPython ABI than the test interpreter, so
    `_concat_images_grid` can legitimately fail with an ImportError here. The
    fallback (`shutil.copy(captured[0], filepath)`) handles that, which is
    itself behaviour worth covering.
    """

    def flipbook(self, viewport, settings):
        self.flipbook_calls.append((viewport, settings))
        out = settings.output_path
        if out:
            try:
                from PIL import Image
                Image.new("RGB", (4, 4), (40, 40, 40)).save(out, "PNG")
            except Exception:
                # Bundled Pillow may be ABI-incompatible; write raw bytes so
                # the file-copy fallback still has something to copy.
                with open(out, "wb") as f:
                    f.write(b"mock flipbook")


class _CaptureComponentDetailFixture(unittest.TestCase):
    """Shared setUp/tearDown: install mock hou, reload edini.node_utils."""

    def setUp(self):
        self.previous_hou = sys.modules.get("hou")
        self.previous_hou_ref = MockNode._hou_ref
        self._reloaded = "edini.node_utils"

        runtime_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "python3.11libs")
        )
        if runtime_path not in sys.path:
            sys.path.insert(0, runtime_path)

        self.mock_hou = create_mock_hou()
        self.viewer = _PngSceneViewer()
        self.mock_hou.ui.set_scene_viewer(self.viewer)
        sys.modules["hou"] = self.mock_hou

        from tests.conftest import reload_edini_modules
        reload_edini_modules(self._reloaded)
        self.node_utils = importlib.import_module("edini.node_utils")

    def tearDown(self):
        from tests.conftest import reload_edini_modules
        reload_edini_modules(self._reloaded)

        if self.previous_hou is None:
            sys.modules.pop("hou", None)
        else:
            sys.modules["hou"] = self.previous_hou
        MockNode._hou_ref = self.previous_hou_ref

    # -- mock geometry builders --------------------------------------------

    def _make_component_asset(self):
        """Build a 2-component mock asset on /obj/detail_asset/OUT.

        Two clearly separated boxes tagged with @component_id prim attr:
          - body   centered near origin
          - knob   offset to the side (so each has distinct bounds)
        """
        obj = self.mock_hou.node("/obj")
        asset = obj.createNode("geo", "detail_asset")
        out = asset.createNode("null", "OUT")

        geo = self.mock_hou.MockGeometry()
        geo.clear()

        def add_box(cid, cx, cy, cz, sx, sy, sz):
            half = (sx / 2.0, sy / 2.0, sz / 2.0)
            corners = [
                (cx - half[0], cy - half[1], cz - half[2]),
                (cx + half[0], cy - half[1], cz - half[2]),
                (cx + half[0], cy + half[1], cz - half[2]),
                (cx - half[0], cy + half[1], cz - half[2]),
                (cx - half[0], cy - half[1], cz + half[2]),
                (cx + half[0], cy - half[1], cz + half[2]),
                (cx + half[0], cy + half[1], cz + half[2]),
                (cx - half[0], cy + half[1], cz + half[2]),
            ]
            pts = []
            for c in corners:
                p = geo.createPoint()
                p.setPosition(c)
                pts.append(p)
            # 6 quads (simplified box faces)
            faces = [
                (0, 1, 2, 3), (4, 5, 6, 7),
                (0, 1, 5, 4), (2, 3, 7, 6),
                (1, 2, 6, 5), (0, 3, 7, 4),
            ]
            for idx in faces:
                prim = geo.createPolygon()
                for i in idx:
                    prim.addVertex(pts[i])
                prim.setAttribValue("component_id", cid)

        add_box("body", 0.0, 0.0, 0.0, 2.0, 2.0, 2.0)
        add_box("knob", 3.0, 0.0, 0.0, 0.4, 0.4, 0.4)

        # geometry_inventory needs findPrimAttrib("component_id") to hit.
        # MockGeometry.findPrimAttrib checks _builder_attribs; addAttrib
        # registers it. setAttribValue on prims alone is not enough.
        geo.addAttrib(self.mock_hou.attribType.Prim, "component_id", "")

        out._geometry = geo
        return out


class TestBoundingBoxOverloads(unittest.TestCase):
    """Unit-level: the bbox construction used by capture_component_detail.

    These do NOT depend on the edini module reload — they validate the mock
    + the 6-float construction contract directly, which is the literal fix.
    """

    def setUp(self):
        # create_mock_hou() mutates the CLASS-level MockNode._hou_ref; save it
        # so we don't leak a throwaway instance into later test modules
        # (test_procedural_harness et al. rely on _hou_ref pointing at the
        # node-tree their own setup built).
        self._prev_hou_ref = MockNode._hou_ref

    def tearDown(self):
        MockNode._hou_ref = self._prev_hou_ref

    def test_six_scalar_overload_roundtrips(self):
        """The fix's overload: BoundingBox(x0,y0,z0, x1,y1,z1)."""
        bbox = MockBoundingBox(-1.0, -2.0, -3.0, 1.0, 2.0, 3.0)
        self.assertEqual(bbox.minvec(), (-1.0, -2.0, -3.0))
        self.assertEqual(bbox.maxvec(), (1.0, 2.0, 3.0))

    def test_two_vector_overload_still_works(self):
        """The legacy overload (kept for compatibility / _target_bounds)."""
        mn = MockVector3(-1.0, -2.0, -3.0)
        mx = MockVector3(1.0, 2.0, 3.0)
        bbox = MockBoundingBox(mn, mx)
        self.assertEqual(bbox.minvec(), (-1.0, -2.0, -3.0))
        self.assertEqual(bbox.maxvec(), (1.0, 2.0, 3.0))

    def test_two_list_overload_accepts_plain_list(self):
        """The failing path: Vector3(list) / BoundingBox(list, list).

        Before the fix this raised (no hou.Vector3 on the mock). The fix
        passes explicit floats so the list never reaches Vector3. Here we
        confirm the mock now accepts a plain list directly too, so the
        contract is robust regardless of construction form.
        """
        bbox = MockBoundingBox([-1.0, -2.0, -3.0], [1.0, 2.0, 3.0])
        self.assertEqual(bbox.minvec(), (-1.0, -2.0, -3.0))
        self.assertEqual(bbox.maxvec(), (1.0, 2.0, 3.0))

    def test_hou_exposes_vector3_and_boundingbox(self):
        """hou.Vector3 / hou.BoundingBox must exist on the mock."""
        hou = create_mock_hou()
        self.assertTrue(hasattr(hou, "Vector3"))
        self.assertTrue(hasattr(hou, "BoundingBox"))
        v = hou.Vector3(1.0, 2.0, 3.0)
        self.assertEqual((v[0], v[1], v[2]), (1.0, 2.0, 3.0))
        b = hou.BoundingBox(0.0, 0.0, 0.0, 1.0, 1.0, 1.0)
        self.assertEqual(b.minvec(), (0.0, 0.0, 0.0))


class TestCaptureComponentDetailRegression(_CaptureComponentDetailFixture):
    """End-to-end: capture_component_detail on a known-good 2-component asset.

    This is the regression test called for in procedural-modeling-bugs.md
    Bug 1 ("Add a regression test: capture detail on a known-good
    2-component asset").
    """

    def test_two_component_capture_succeeds(self):
        """Body + knob both capture with no 'bbox build failed' error."""
        out = self._make_component_asset()
        with tempfile.TemporaryDirectory() as tmp:
            filepath = os.path.join(tmp, "detail.png")
            result = self.node_utils.capture_component_detail(
                filepath,
                node_path=out.path(),
                component_ids=["body", "knob"],
                views=["perspective"],
            )

        self.assertTrue(
            result.get("success"),
            f"capture_component_detail failed: {result}",
        )
        self.assertEqual(result.get("method"), "component_detail")
        # No bbox construction errors — the Bug 1 symptom.
        errors = result.get("errors") or []
        bbox_failures = [e for e in errors if "bbox build failed" in e]
        self.assertEqual(
            bbox_failures, [],
            f"Bug 1 regression: bbox build failed errors present: {bbox_failures}",
        )

    def test_capture_frames_each_component_bbox(self):
        """The viewport must be repositioned to each component's own bbox.

        Bug 1's real-world effect was that capture failed before ever
        framing, so the viewport never moved to the small knob. After the
        fix, setViewToBoundingBox is called with a bbox whose extents match
        the component (here the knob, which is tiny and offset).
        """
        out = self._make_component_asset()
        vp = self.viewer.viewport
        vp.set_view_to_bbox_called = False

        with tempfile.TemporaryDirectory() as tmp:
            filepath = os.path.join(tmp, "detail.png")
            self.node_utils.capture_component_detail(
                filepath,
                node_path=out.path(),
                component_ids=["knob"],
                views=["perspective"],
            )

        self.assertTrue(
            vp.set_view_to_bbox_called,
            "viewport must be framed via setViewToBoundingBox per component",
        )
        # The last bbox framed should be the knob's: x around 3.0, small size.
        last = vp.last_bbox
        self.assertIsNotNone(last, "a bbox must have been passed to the viewport")
        mn = last.minvec()
        mx = last.maxvec()
        self.assertAlmostEqual(mn[0], 2.8, places=3)  # 3.0 - 0.2
        self.assertAlmostEqual(mx[0], 3.2, places=3)  # 3.0 + 0.2

    def test_missing_component_id_returns_clear_error(self):
        """No @component_id on geometry -> clear error, not a crash."""
        obj = self.mock_hou.node("/obj")
        node = obj.createNode("geo", "no_comp")
        out = node.createNode("null", "OUT")
        out._geometry = self.mock_hou.MockGeometry(
            point_count=4, prim_count=1, vertex_count=4,
            bounds=(0.0, 1.0, 0.0, 1.0, 0.0, 1.0),
        )

        with tempfile.TemporaryDirectory() as tmp:
            filepath = os.path.join(tmp, "detail.png")
            result = self.node_utils.capture_component_detail(
                filepath,
                node_path=out.path(),
                component_ids=["anything"],
            )

        self.assertFalse(result.get("success"))
        self.assertIn("component_id", result.get("error", ""))

    def test_unknown_component_id_lists_available(self):
        """Asking for a non-existent id returns the available ids."""
        out = self._make_component_asset()
        with tempfile.TemporaryDirectory() as tmp:
            filepath = os.path.join(tmp, "detail.png")
            result = self.node_utils.capture_component_detail(
                filepath,
                node_path=out.path(),
                component_ids=["nonexistent"],
            )

        self.assertFalse(result.get("success"))
        # Available ids should include the two we built.
        available = result.get("available") or []
        avail_str = " ".join(available)
        self.assertIn("body", avail_str)
        self.assertIn("knob", avail_str)


if __name__ == "__main__":
    unittest.main()
