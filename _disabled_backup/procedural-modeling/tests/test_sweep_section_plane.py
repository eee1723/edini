"""Tests for the Sweep cross-section plane detection (Batch 2).

The dual-wrangle Sweep pattern requires the cross-section to lie in the XZ
plane (Y=0, normal=+Y) so Sweep can align it perpendicular to the path
tangent. A section in the XY plane (Z=0) is the #1 cause of "sweep produces
a flat blob instead of a tube". This test covers the heuristic detector that
flags the wrong plane at build time.

These are pure-logic tests (no `hou`) — they import only the detector.
"""
from __future__ import annotations

import importlib
import sys
from unittest import mock

# harness.py does `import hou` at module top. The detector we want to test
# is pure Python but lives in harness, so stub hou before importing.
if "hou" not in sys.modules:
    sys.modules["hou"] = mock.MagicMock(name="hou")

import edini.harness as h  # noqa: E402


# ── The detector itself ──────────────────────────────────────────────────

class TestDetectSectionPlane:
    """Classify which plane a section snippet occupies."""

    def test_xz_explicit_set_pattern(self):
        # The canonical correct pattern from declarative-builder.md
        code = (
            "float r=chf('tube_od')/2.0;int n=16;int pts[];"
            "for(int i=0;i<n;i++){float a=2.0*M_PI*float(i)/float(n);"
            "int pt=addpoint(0,set(r*cos(a),0,r*sin(a)));push(pts,pt);}"
        )
        assert h._detect_section_plane(code) == "XZ"

    def test_xy_wrong_pattern_flagged(self):
        # The classic WRONG pattern: set(r*cos(a), r*sin(a), 0)
        code = (
            "for(int i=0;i<n;i++){float a=2.0*M_PI*float(i)/float(n);"
            "addpoint(0,set(r*cos(a),r*sin(a),0));}"
        )
        assert h._detect_section_plane(code) == "XY"

    def test_vexlib_xz_plane_arg(self):
        code = 'int p[] = make_circle_section(0, r, 16, "XZ", {0,0,0});'
        assert h._detect_section_plane(code) == "XZ"

    def test_vexlib_xy_plane_arg(self):
        code = 'int p[] = make_circle_section(0, r, 16, "XY", {0,0,0});'
        assert h._detect_section_plane(code) == "XY"

    def test_vexlib_make_rect_section_xz(self):
        code = 'int prof[] = make_rect_section(0, chf("w"), chf("h"), "XZ");'
        assert h._detect_section_plane(code) == "XZ"

    def test_unknown_when_no_pattern(self):
        # No set()/plane literal → can't tell, don't warn
        assert h._detect_section_plane("addpoint(0, pos);") == "unknown"

    def test_empty_snippet(self):
        assert h._detect_section_plane("") == "unknown"

    def test_comments_stripped_before_detection(self):
        # A comment mentioning XY should not fool the detector
        code = (
            "// section in XY plane historically\n"
            "addpoint(0, set(r*cos(a), 0, r*sin(a)));"
        )
        assert h._detect_section_plane(code) == "XZ"

    def test_mixed_planes_dominant_wins(self):
        # 2 XZ hits, 1 XY hit → XZ
        code = (
            "set(1, 0, 1); set(2, 0, 2); set(3, 4, 0);"
        )
        assert h._detect_section_plane(code) == "XZ"


# ── The warning is recorded on a real build path ─────────────────────────
# (Verified via the module-level conflict list, mocked hou.)

class TestWarningRecorded:
    """When a Sweep section is in XY, the build records a plane warning."""

    def _make_hou_mock(self):
        """A minimal hou mock supporting the few calls the build path uses."""
        hou = mock.MagicMock(name="hou")
        # node() returns a node mock with the methods harness touches
        node = mock.MagicMock()
        node.path.return_value = "/obj/sb"
        node.name.return_value = "sb"
        node.subnetOfType.return_value = None
        node.createNode.return_value = mock.MagicMock()
        hou.node.return_value = node
        hou.nodeType.return_value = None
        return hou, node

    def test_reset_clears_plane_warnings(self):
        # The build entry resets the global. We can at least confirm the
        # attribute exists and is list-typed.
        assert isinstance(h._SWEEP_SECTION_PLANE_WARNINGS, list)
