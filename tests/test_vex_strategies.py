"""Pure-logic tests for vex_strategies.build_mount_vex dispatch.

These tests verify the (snippet, parms) resolution for each measure kind
WITHOUT needing real hou — the VEX text and the spare-parm dict are the
contract, and both are pure data. The snippet's actual cook behaviour is
verified separately under real hython (test_project_hython.py) where a real
wrangle can run.

The by_name strategy (Layer C1) is the focus here: it is the cure for the
"bbox_face_center on a merged mesh ≠ real dropout" failure (session log 2,
road bike frame). It picks a SEMANTIC marker point the root generator emitted
at a real geometric location, instead of deriving a point from the bbox hull.
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python3.11libs"))
# vex_strategies is pure-data (no hou import at module load) — safe to import.
from edini.vex_strategies import (  # noqa: E402
    build_mount_vex,
    VexStrategyError,
)


class TestByNameStrategy(unittest.TestCase):
    """Layer C1: the by_name measure picks a named marker point."""

    def test_by_name_resolves_snippet_and_marker_parm(self):
        """by_name produces a VEX snippet + a string 'marker' spare parm."""
        snippet, parms = build_mount_vex(
            {"measure": "by_name", "marker": "head_tube_top"})
        # The snippet must reference the marker via chs("marker").
        self.assertIn('chs("marker")', snippet)
        # The marker value is carried as a string parm (leading _ stripped by
        # the builder when installing; here we see the raw strategy output).
        self.assertIn("_marker", parms)
        self.assertEqual(parms["_marker"], "head_tube_top")

    def test_by_name_does_not_use_vex_clear(self):
        """by_name must NOT begin with the _VEX_CLEAR header — it PRESERVES the
        matched input point's real position rather than re-deriving it from the
        bbox. (The bbox strategies all begin with _VEX_CLEAR.)"""
        snippet, _ = build_mount_vex(
            {"measure": "by_name", "marker": "dropout"})
        # _VEX_CLEAR's signature line is the removepoint-from-high-end loop
        # BEFORE the __newpts declaration. by_name declares __newpts LATER
        # (after scanning), so its FIRST non-comment executable is the
        # npoints() scan, not a blind clear.
        first_exec = next(
            (ln.strip() for ln in snippet.splitlines()
             if ln.strip() and not ln.strip().startswith("//")),
            "")
        self.assertIn("npoints(geoself())", first_exec,
                      f"by_name should scan points first, not clear them: "
                      f"{first_exec!r}")

    def test_by_name_requires_marker(self):
        """A by_name spec without a marker raises VexStrategyError."""
        with self.assertRaises(VexStrategyError):
            build_mount_vex({"measure": "by_name"})

    def test_by_name_rejects_non_string_marker(self):
        """A numeric marker is rejected (must be a legal @name token)."""
        with self.assertRaises(VexStrategyError):
            build_mount_vex({"measure": "by_name", "marker": 42})

    def test_by_name_rejects_illegal_marker_chars(self):
        """A marker with spaces/punctuation is rejected (@name must be a
        legal token: letters/digits/underscores)."""
        with self.assertRaises(VexStrategyError):
            build_mount_vex({"measure": "by_name", "marker": "head tube top"})

    def test_by_name_preserves_orient_in_snippet(self):
        """The by_name VEX preserves a generator-supplied orient onto the
        re-emitted marker point (the bike frame may orient its dropouts)."""
        snippet, _ = build_mount_vex(
            {"measure": "by_name", "marker": "dropout"})
        self.assertIn("orient", snippet,
                      "by_name should carry a generator orient if present")


class TestExistingStrategiesUnchanged(unittest.TestCase):
    """Regression guard: the by_name addition must not perturb the existing
    static strategies' resolution."""

    def test_bbox_corner_still_works(self):
        snippet, parms = build_mount_vex(
            {"measure": "bbox_corner", "axes": "+X-Y+Z"})
        self.assertEqual(parms, {"cx": 1, "cy": 0, "cz": 1})
        self.assertIn("getbbox_min", snippet)

    def test_bbox_face_center_still_works(self):
        snippet, parms = build_mount_vex(
            {"measure": "bbox_face_center", "face": "-Y"})
        self.assertEqual(parms["face_axis"], 1)
        self.assertEqual(parms["face_sign"], -1)

    def test_unknown_measure_still_raises(self):
        with self.assertRaises(VexStrategyError):
            build_mount_vex({"measure": "nonexistent"})


if __name__ == "__main__":
    unittest.main()


# ── Finding 4: _relative_path_to_core (pure-logic, no hou) ──
# repath_to_relative's depth computation is pure path arithmetic, testable
# without hython. Imported from node_utils — re-imported here to keep the
# vex test file self-contained for the path-helper sub-test.

class TestRelativePathToCore(unittest.TestCase):
    """The depth computation behind repath_to_relative (Finding 4)."""

    def test_two_levels_deep(self):
        # box at core/box_comp/b1 — core is 2 levels up.
        from edini.node_utils import _relative_path_to_core
        self.assertEqual(
            _relative_path_to_core("/obj/p/project_core/box_comp/b1",
                                   "/obj/p/project_core"),
            "../../")

    def test_one_level_deep(self):
        from edini.node_utils import _relative_path_to_core
        self.assertEqual(
            _relative_path_to_core("/obj/p/project_core/box_comp",
                                   "/obj/p/project_core"),
            "../")

    def test_not_descendant_returns_none(self):
        from edini.node_utils import _relative_path_to_core
        self.assertIsNone(
            _relative_path_to_core("/obj/other/thing", "/obj/p/project_core"))

    def test_equal_paths_returns_none(self):
        # core itself is not a descendant of core — no relative ref meaningful.
        from edini.node_utils import _relative_path_to_core
        self.assertIsNone(
            _relative_path_to_core("/obj/p/project_core", "/obj/p/project_core"))
