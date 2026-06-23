"""Tests for edini.vexlib_loader — the reliable vexlib injection mechanism.

Batch 1 (vexlib 可加载) acceptance tests. These run fully offline (no `hou`
import) because the loader is pure file/regex logic. They verify the two
failure modes documented in the module docstring are fixed:

  1. ALL library functions trigger injection (not just make_polyline/make_circle)
  2. Injection is by inline source expansion — no HOUDINI_VEX_PATH dependency
"""
from __future__ import annotations

import os

import pytest

from edini import vexlib_loader as vl


# ── Function discovery ────────────────────────────────────────────────────

class TestFunctionIndex:
    """The loader must know all 15 functions actually defined in the .vfl files."""

    EXPECTED_SKELETON = {
        "make_polyline", "make_closed_polyline", "make_helix",
        "make_stair_path", "make_grid",
    }
    EXPECTED_SECTIONS = {
        "make_rect_section", "make_circle_section",
        "make_tapered_section", "make_gear_profile", "make_arc_path",
    }
    EXPECTED_ATTRIBS = {
        "set_orient_from_tangent", "set_component_id_by_range",
        "set_component_id_by_index", "set_scale_along_curve",
        "set_instance_attrs",
    }
    ALL_EXPECTED = EXPECTED_SKELETON | EXPECTED_SECTIONS | EXPECTED_ATTRIBS

    def test_known_functions_matches_vfl_sources(self):
        known = vl.known_functions()
        missing = self.ALL_EXPECTED - known
        assert not missing, f"vexlib_loader failed to discover: {sorted(missing)}"

    def test_function_index_maps_to_correct_file(self):
        idx = vl._function_index()
        for f in self.EXPECTED_SKELETON:
            assert idx[f] == "skeleton.vfl", f"{f} should be in skeleton.vfl"
        for f in self.EXPECTED_SECTIONS:
            assert idx[f] == "sections.vfl", f"{f} should be in sections.vfl"
        for f in self.EXPECTED_ATTRIBS:
            assert idx[f] == "attribs.vfl", f"{f} should be in attribs.vfl"


# ── Call detection ────────────────────────────────────────────────────────

class TestUsedVexlibFunctions:
    """Detect which library functions a snippet *calls* (not just mentions)."""

    def test_make_polyline_detected(self):
        assert "make_polyline" in vl.used_vexlib_functions(
            "int p[] = make_polyline(0, pts);")

    def test_make_circle_section_detected(self):
        # This was the bug: make_circle_section was NOT in the old 2-name guard.
        used = vl.used_vexlib_functions(
            'int p[] = make_circle_section(0, 1.0, 12, "XZ", {0,0,0});')
        assert "make_circle_section" in used

    def test_make_gear_profile_detected(self):
        used = vl.used_vexlib_functions(
            'int g[] = make_gear_profile(0, 42, 0.1, 0.08, "XY", {0,0,0});')
        assert "make_gear_profile" in used

    def test_make_stair_path_detected(self):
        # make_stair_path was never in the old guard either.
        used = vl.used_vexlib_functions(
            "int s[] = make_stair_path(0, 10, 0.3, 0.18, {0,0,0}, {1,0,0});")
        assert "make_stair_path" in used

    def test_attribs_function_detected(self):
        # set_instance_attrs (attribs.vfl) was never auto-included before.
        used = vl.used_vexlib_functions(
            "set_instance_attrs(0, 0, {1,0,0}, {0,1,0}, {0,0,1}, 1.0);")
        assert "set_instance_attrs" in used

    def test_word_boundary_not_substring(self):
        """``my_make_polyline`` must NOT be detected as ``make_polyline``."""
        used = vl.used_vexlib_functions(
            "int p[] = my_make_polyline(0, pts);")
        assert "make_polyline" not in used

    def test_comment_mention_not_treated_as_call(self):
        """A function name in a comment with no following paren is not a call."""
        used = vl.used_vexlib_functions(
            "// TODO: use make_circle_section here\naddpoint(0, {0,0,0});")
        assert "make_circle_section" not in used

    def test_no_vexlib_calls_returns_empty(self):
        assert vl.used_vexlib_functions("addpoint(0, {0,0,0});") == []

    def test_empty_snippet(self):
        assert vl.used_vexlib_functions("") == []


# ── Inline expansion ──────────────────────────────────────────────────────

class TestExpandVexlib:
    """The reliable primary path: inline the .vfl source a snippet needs."""

    def test_expansion_prepends_only_needed_files(self):
        # Calling a sections-only function should NOT inline skeleton if the
        # snippet has no skeleton calls... but sections.vfl CALLS
        # make_closed_polyline from skeleton.vfl, so skeleton is a dependency
        # and MUST be included too. We verify the dependency is pulled in.
        snippet = 'int p[] = make_rect_section(0, 1.0, 2.0, "XZ");'
        out = vl.expand_vexlib(snippet)
        # sections needs make_closed_polyline → skeleton must be present
        assert "make_closed_polyline" in out  # from skeleton.vfl
        assert "make_rect_section" in out     # from sections.vfl
        # The original call is preserved at the end
        assert out.rstrip().endswith(snippet)

    def test_expansion_inlines_full_function_body(self):
        """Expansion must contain real source, not just an #include directive."""
        snippet = 'int p[] = make_helix(0, 100, 1.0, 5.0, 3.0);'
        out = vl.expand_vexlib(snippet)
        # The make_helix body contains this distinctive line
        assert "float angle = t * turns * 2.0 * M_PI;" in out
        # And critically: NO unresolved #include directive emitted
        assert "#include" not in out

    def test_expansion_idempotent_with_handwritten_include(self):
        """If the snippet already has #include, we must NOT double-inject."""
        snippet = (
            "#include <vexlib/skeleton.vfl>\n"
            "int p[] = make_polyline(0, pts);"
        )
        out = vl.expand_vexlib(snippet)
        assert out == snippet, "must leave hand-written include untouched"

    def test_expansion_adds_marker_comment(self):
        snippet = 'int p[] = make_grid(0, 2, 2, 0.5, 0.5, 0, {0,0,0}, "XY");'
        out = vl.expand_vexlib(snippet)
        assert "vexlib inline" in out  # provenance marker

    def test_expansion_no_vexlib_calls_unchanged(self):
        snippet = "addpoint(0, {0,0,0});\naddprim(0, 'polyline', 0, 1);"
        assert vl.expand_vexlib(snippet) == snippet

    def test_expansion_empty_input(self):
        assert vl.expand_vexlib("") == ""

    def test_multiple_calls_pull_union_of_files(self):
        """A snippet using functions from two files gets both."""
        snippet = (
            'int path[] = make_polyline(0, pts);\n'
            'int prof[] = make_circle_section(0, 1.0, 12, "XZ", {0,0,0});'
        )
        out = vl.expand_vexlib(snippet)
        assert "make_polyline" in out           # skeleton
        assert "make_circle_section" in out     # sections

    def test_expansion_is_valid_vex_structure(self):
        """The prepended source + snippet must form contiguous VEX: the
        injected file source must end with a newline so declarations and the
        snippet don't merge into one token."""
        snippet = 'int p[] = make_polyline(0, array({0,0,0},{1,0,0}));'
        out = vl.expand_vexlib(snippet)
        # Find the boundary between injected source and the original snippet.
        # The snippet's first line must start at the beginning of a line.
        marker = "// ── vexlib inline"
        idx = out.find(marker)
        snippet_idx = out.find(snippet)
        assert idx < snippet_idx
        # Char immediately before snippet must be a newline
        assert out[snippet_idx - 1] == "\n"


# ── Path registration ─────────────────────────────────────────────────────

class TestEnsureVexPath:
    """HOUDINI_VEX_PATH registration (for hand-written #include directives)."""

    def test_ensure_vex_path_idempotent(self):
        # Already registered at import; calling again must be safe and True.
        assert vl.ensure_vex_path() is True

    def test_vexlib_dir_exists_and_points_at_real_files(self):
        assert os.path.isdir(vl.VEXLIB_DIR)
        for f in vl._VFL_FILES:
            assert os.path.isfile(os.path.join(vl.VEXLIB_DIR, f)), f"missing {f}"

    def test_registered_path_covers_vexlib_parent(self):
        # ensure_vex_path ran at import; the parent of vexlib/ must be present.
        scripts_dir = os.path.dirname(vl.VEXLIB_DIR)
        paths = os.environ.get("HOUDINI_VEX_PATH", "").split(os.pathsep)
        assert scripts_dir in paths, (
            f"HOUDINI_VEX_PATH missing {scripts_dir}; got: {paths}")


# ── Integration: the regression that batch 1 fixes ────────────────────────

class TestRegressionFullLibraryUsable:
    """End-to-end-ish: every library function, used in a realistic snippet,
    produces expanded VEX that contains its body and no #include directive.

    This is the batch-1 acceptance criterion: the library is TRULY callable,
    for ALL functions, without depending on the environment.
    """

    @pytest.mark.parametrize("call", [
        'make_polyline(0, array({0,0,0},{1,0,0}))',
        'make_closed_polyline(0, array({0,0,0},{1,0,0},{1,1,0}))',
        'make_helix(0, 50, 1.0, 5.0, 3.0)',
        'make_stair_path(0, 5, 0.3, 0.18, {0,0,0}, {1,0,0})',
        'make_grid(0, 4, 4, 0.5, 0.5, 1, {0,0,0}, "XZ")',
        'make_rect_section(0, 1.0, 2.0, "XZ")',
        'make_circle_section(0, 0.5, 16, "XZ", {0,0,0})',
        'make_tapered_section(0, array(1.0,0.8,1.0,0.8), "XZ", {0,0,0})',
        'make_gear_profile(0, 12, 0.1, 0.08, "XY", {0,0,0})',
        'make_arc_path(0, 20, 1.0, 0, 180, "XY", {0,1,0})',
        'set_orient_from_tangent(0, 0, {1,0,0}, {0,1,0})',
        'set_component_id_by_range(0, "x", {0,0,0}, {1,1,1})',
        'set_component_id_by_index(0, "step_", 0, 12)',
        'set_scale_along_curve(0, 0, 0.5, 1.0, 0)',
        'set_instance_attrs(0, 0, {0,0,0}, {0,1,0}, {0,0,1}, 1.0)',
    ])
    def test_every_function_expands_with_body(self, call):
        out = vl.expand_vexlib("int dummy[] = " + call + ";")
        assert "// ── vexlib inline" in out, f"{call}: no inline marker"
        assert "#include" not in out, (
            f"{call}: expansion still emits #include (env dependency)")
        # The function name must appear at least twice now: once in the
        # inlined declaration, once in the original call.
        fname = call.split("(")[0]
        assert out.count(fname) >= 2, (
            f"{call}: function {fname} not fully inlined")
