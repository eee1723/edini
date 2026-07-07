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
# _make_replacer and _CH_CALL_RE live in node_utils; that module's top-level
# `import hou` is wrapped in try/except, so the pure-logic helpers import fine
# without a real Houdini.
from edini.node_utils import _make_replacer, _CH_CALL_RE  # noqa: E402


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

    def test_by_name_emits_error_on_zero_match(self):
        """A zero-match (typo'd marker, or generator didn't emit it) MUST NOT
        be silent. The VEX must call error() on the !__found path so the failure
        surfaces via node.errors() and is picked up by inspect_health /
        verify_parametric. The session-logs-analysis audit flagged that the
        original by_name emitted zero points with no diagnostic — the agent
        could not tell "marker not found" from "upstream geometry empty"."""
        marker = "head_tube_top"
        snippet, _ = build_mount_vex({"measure": "by_name", "marker": marker})
        # The error() call must exist and be gated on the NOT-found path.
        # VEX has no real AST here; assert structurally: there is an `else`
        # branch following the `if (__found)` block, and it contains error()
        # referencing the marker name.
        self.assertIn("else", snippet,
                      "by_name must have an else (!__found) branch; a bare "
                      f"if(__found) with no else re-introduces the silent "
                      f"zero-point bug. snippet:\n{snippet}")
        self.assertIn("error(", snippet,
                      "by_name must call VEX error() when the marker is not "
                      f"found. snippet:\n{snippet}")
        # The marker value is read at runtime via chs("marker") into __marker,
        # so the snippet itself only references the VARIABLE — the concrete
        # marker name lives in the 'parms' dict. Assert the error interpolates
        # __marker (so the runtime error names the actual missing marker).
        self.assertIn("__marker", snippet,
                      "the error message must interpolate __marker so the "
                      "runtime error names the actual missing marker.")


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


# ── _make_replacer (pure-logic, no hou): the regex sub behind repath_to_relative ──
# The session-logs-analysis audit found _make_replacer had ZERO unit tests —
# only end-to-end hython coverage of the happy path (bare ch()). These tests
# cover the forms the hython test never exercised: hou.ch(), single/double
# quotes, near-name collisions (project_core_backup), bare-core refs, and the
# multi-level parm_tail guard that is the SOLE protector against rewriting
# foreign parms.

class TestMakeReplacer(unittest.TestCase):
    """The ch()/hou.ch() rewrite callback behind repath_to_relative."""

    def _repl(self, core_path, rel):
        return _make_replacer(core_path, rel)

    def test_bare_ch_single_quotes_rewritten(self):
        repl = self._repl("/obj/p/project_core", "../../")
        result = _CH_CALL_RE.sub(
            repl, "ch('/obj/p/project_core/length')")
        self.assertEqual(result, 'ch("../../length")')

    def test_hou_ch_form_rewritten(self):
        """The regex explicitly supports hou.ch(...) — the hython test only
        ever exercised bare ch(), so this form was unverified."""
        repl = self._repl("/obj/p/project_core", "../../")
        result = _CH_CALL_RE.sub(
            repl, "hou.ch('/obj/p/project_core/length')")
        self.assertEqual(result, 'hou.ch("../../length")')

    def test_double_quoted_path_rewritten(self):
        repl = self._repl("/obj/p/project_core", "../")
        result = _CH_CALL_RE.sub(
            repl, 'ch("/obj/p/project_core/width")')
        self.assertEqual(result, 'ch("../width")')

    def test_preserves_hou_prefix_individually(self):
        """A mixed expression: hou.ch and bare ch in the same string each
        keep their own prefix."""
        repl = self._repl("/obj/p/project_core", "../")
        result = _CH_CALL_RE.sub(
            repl,
            "hou.ch('/obj/p/project_core/a') + ch('/obj/p/project_core/b')")
        self.assertEqual(
            result, 'hou.ch("../a") + ch("../b")')

    def test_near_name_collision_left_untouched(self):
        """A reference to project_core_BACKUP (a sibling whose path merely
        CONTAINS the core path string) must NOT be rewritten. Correctness
        hinges on the `if '/' in parm_tail` guard — without it, the substring
        pre-filter would rewrite foreign parms. This is the audit's #1
        latent-fragility case."""
        repl = self._repl("/obj/p/project_core", "../../")
        result = _CH_CALL_RE.sub(
            repl, "ch('/obj/p/project_core_backup/length')")
        # Must be unchanged — _backup/length is NOT a core parm.
        self.assertEqual(result, "ch('/obj/p/project_core_backup/length')")

    def test_non_core_reference_left_untouched(self):
        """A ch() to a completely unrelated node is never rewritten."""
        repl = self._repl("/obj/p/project_core", "../")
        result = _CH_CALL_RE.sub(
            repl, "ch('/obj/other_subnet/some_parm')")
        self.assertEqual(result, "ch('/obj/other_subnet/some_parm')")

    def test_multi_level_parm_tail_left_untouched(self):
        """A reference deeper than core/parm (e.g. core/sub/parm) is left
        alone — only one level of parm tail is rewritten."""
        repl = self._repl("/obj/p/project_core", "../")
        result = _CH_CALL_RE.sub(
            repl, "ch('/obj/p/project_core/sub/parm')")
        self.assertEqual(result, "ch('/obj/p/project_core/sub/parm')")

    def test_one_level_deep_rewrites_correctly(self):
        """Depth-1 node: ch('/obj/p/project_core/length') -> ch('../length').
        _make_replacer always emits double-quoted ch() regardless of input
        quote style (see test_double_quoted_path_rewritten)."""
        repl = self._repl("/obj/p/project_core", "../")
        result = _CH_CALL_RE.sub(
            repl, "ch('/obj/p/project_core/length')")
        self.assertEqual(result, 'ch("../length")')


if __name__ == "__main__":
    unittest.main()
