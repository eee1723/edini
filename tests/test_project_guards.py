"""Tests for edini.project.guards — the addpoint() anchor guard (Fix 1).

Two layers:
  1. Pure-logic: _snippet_violates (no hou needed).
  2. Context-aware: lint_wrangle_snippet with a fake hou module injected into
     edini.project.guards' globals, simulating an attribwrangle inside vs
     outside an edini::project core subnet.

The chair-modeling log showed the agent hand-writing
``addpoint(set(0.225,0,0.225), ...)`` inside a component subnet. This guard
refuses that and points at project_add_anchors. These tests lock the contract.

Run: pytest tests/test_project_guards.py -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python3.11libs"))


class _FakeType:
    def __init__(self, name):
        self._name = name

    def name(self):
        return self._name


class _FakeNode:
    """Minimal fake hou.Node: type().name() + parent() chain."""

    def __init__(self, type_name, parent=None):
        self._type = _FakeType(type_name)
        self._parent = parent

    def type(self):
        return self._type

    def parent(self):
        return self._parent


def _install_fake_hou(guards_module, target_node):
    """Inject a fake `hou` into guards' globals so lint_wrangle_snippet's
    `import hou` picks it up. Returns the fake module."""

    class _FakeHou:
        def node(self, path):
            # The guard calls hou.node(node_path) once; return the target.
            return target_node

    fake = _FakeHou()
    guards_module.hou = fake  # type: ignore[attr-defined]
    return fake


class TestSnippetViolates(unittest.TestCase):
    """Pure-logic predicate — no hou."""

    def test_detects_vex_addpoint(self):
        from edini.project.guards import _snippet_violates
        self.assertTrue(_snippet_violates("int p = addpoint(0, {0,0,0});"))

    def test_detects_python_addpoint(self):
        from edini.project.guards import _snippet_violates
        self.assertTrue(_snippet_violates("geo.addPoint(hou.Vector3(0,0,0))"))

    def test_detects_addpoint_with_whitespace(self):
        from edini.project.guards import _snippet_violates
        self.assertTrue(_snippet_violates("addpoint (0, pos)"))

    def test_allows_benign_snippet(self):
        from edini.project.guards import _snippet_violates
        self.assertFalse(_snippet_violates('s@component_id = "seat";'))
        self.assertFalse(_snippet_violates("v@P += {0,1,0};"))
        self.assertFalse(_snippet_violates(""))

    def test_allows_non_string(self):
        from edini.project.guards import _snippet_violates
        self.assertFalse(_snippet_violates(None))
        self.assertFalse(_snippet_violates(123))

    def test_bypass_marker_disables_guard(self):
        """The escape hatch: a comment opting out for legit one-off cases."""
        from edini.project.guards import _snippet_violates
        snip = "// edini-bypass-anchor-guard\nint p = addpoint(0, {0,0,0});"
        self.assertFalse(_snippet_violates(snip))


class TestLintWrangleSnippet(unittest.TestCase):
    """Context-aware refusal. The addpoint token alone is NOT enough — it must
    ALSO be a wrangle inside a project core. Recipe/sandbox wrangles pass."""

    def setUp(self):
        import edini.project.guards as g
        self.guards = g
        # Save any prior hou so tests don't bleed into each other.
        self._prev_hou = getattr(g, "hou", None)

    def tearDown(self):
        # Restore — guards' real `import hou` is lazy; tests inject a fake.
        import edini.project.guards as g
        if self._prev_hou is not None:
            g.hou = self._prev_hou  # type: ignore[attr-defined]
        else:
            g.hou = None  # type: ignore[attr-defined]

    def test_refuses_addpoint_in_project_core_wrangle(self):
        """The chair-log scenario: a wrangle inside a component subnet of an
        edini::project core, with addpoint(). MUST refuse + name the fix."""
        # core (edini::project) → component subnet → wrangle
        core = _FakeNode("edini::project")
        subnet = _FakeNode("subnet", parent=core)
        wrangle = _FakeNode("attribwrangle", parent=subnet)
        _install_fake_hou(self.guards, wrangle)

        result = self.guards.lint_wrangle_snippet(
            "/obj/geo1/project1/seat/build_anchors",
            "int p = addpoint(0, set(0.225, 0, 0.225));",
        )
        self.assertIsNotNone(result, "guard must refuse addpoint in project core")
        self.assertFalse(result["success"])
        self.assertEqual(result["suggested_tool"], "project_add_anchors")
        self.assertIn("addpoint", result["error"])
        self.assertIn("project_add_anchors", result["error"])
        # Schema hint tells the agent how to call the right tool.
        self.assertIn("anchors", result["schema_hint"])

    def test_allows_addpoint_outside_project_core(self):
        """A wrangle in a sandbox / standalone geo (NOT under edini::project)
        must NOT be refused — the declarative primitive doesn't apply there."""
        sandbox_geo = _FakeNode("geo")  # /obj/edini_sandbox_...
        wrangle = _FakeNode("attribwrangle", parent=sandbox_geo)
        _install_fake_hou(self.guards, wrangle)

        result = self.guards.lint_wrangle_snippet(
            "/obj/edini_sandbox_xyz/wrangle1",
            "int p = addpoint(0, {0,0,0});",
        )
        self.assertIsNone(result, "guard must NOT fire outside project cores")

    def test_allows_non_wrangle_node(self):
        """addpoint in a Python SOP body (not an attribwrangle) — not the
        guard's target. Don't refuse."""
        core = _FakeNode("edini::project")
        subnet = _FakeNode("subnet", parent=core)
        python_sop = _FakeNode("python", parent=subnet)  # type name has no 'wrangle'
        _install_fake_hou(self.guards, python_sop)

        result = self.guards.lint_wrangle_snippet(
            "/obj/geo1/project1/seat/gen",
            "geo.addPoint(hou.Vector3(0,0,0))",
        )
        self.assertIsNone(result)

    def test_allows_benign_snippet_in_project_core(self):
        """A normal tag wrangle (component_id, no addpoint) inside a project
        core must pass through."""
        core = _FakeNode("edini::project")
        subnet = _FakeNode("subnet", parent=core)
        wrangle = _FakeNode("attribwrangle", parent=subnet)
        _install_fake_hou(self.guards, wrangle)

        result = self.guards.lint_wrangle_snippet(
            "/obj/geo1/project1/seat/tag_seat",
            's@component_id = "seat";\nv@edini_world_axis = {0,1,0};\n',
        )
        self.assertIsNone(result)

    def test_bypass_marker_allows_addpoint_in_project_core(self):
        """The escape hatch works even inside a project core."""
        core = _FakeNode("edini::project")
        subnet = _FakeNode("subnet", parent=core)
        wrangle = _FakeNode("attribwrangle", parent=subnet)
        _install_fake_hou(self.guards, wrangle)

        snip = ("// edini-bypass-anchor-guard: legit one-off scatter seed\n"
                "int p = addpoint(0, {0,0,0});")
        result = self.guards.lint_wrangle_snippet("/x/y", snip)
        self.assertIsNone(result)

    def test_no_hou_allows(self):
        """If hou is unavailable (offline/test env), the context check
        degrades to allow — never block when we can't confirm context."""
        import edini.project.guards as g
        g.hou = None  # type: ignore[attr-defined]
        result = g.lint_wrangle_snippet("/x/y", "addpoint(0, {0,0,0});")
        self.assertIsNone(result)


class TestInternalNodeGuard(unittest.TestCase):
    """Round-2 Fix A: the guard refuses ANY snippet edit on __-prefixed
    internal scaffold nodes (__edini_axis_bake, __edini_anchor_clean_*).
    These bake platform contracts the scaffold owns and re-forces; agent
    edits would be silently undone and risk corrupting the contract. This
    fires regardless of snippet content (doesn't need addpoint) and doesn't
    need hou (parses the node name from the path)."""

    def test_refuses_edit_to_axis_bake_node(self):
        """The exact hole from session 2: agent must not be able to edit
        __edini_axis_bake even with a benign snippet."""
        import edini.project.guards as g
        result = g.lint_wrangle_snippet(
            "/obj/geo1/project1/seat/__edini_axis_bake",
            'v@edini_world_axis = {0, 0, 1};',  # benign, no addpoint
        )
        self.assertIsNotNone(result)
        self.assertFalse(result["success"])
        self.assertEqual(result["blocked_by"], "internal_node_guard")
        self.assertEqual(result["suggested_node"], "tag_component")

    def test_refuses_edit_to_anchor_clean_node(self):
        """The prim-stripping wrangle is also internal."""
        import edini.project.guards as g
        result = g.lint_wrangle_snippet(
            "/obj/geo1/project1/leg/__edini_anchor_clean_seat_leg_fr",
            "removeprim(0, @primnum, 1);",
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["blocked_by"], "internal_node_guard")

    def test_allows_edit_to_tag_component(self):
        """tag_component is AGENT-EDITABLE (no __ prefix) — must pass the
        internal-node guard. (It may still hit the addpoint guard separately,
        but a benign component_id-only snippet passes both.)"""
        import edini.project.guards as g
        # Benign snippet, no addpoint → internal guard doesn't fire, addpoint
        # guard doesn't fire → None (allowed).
        result = g.lint_wrangle_snippet(
            "/obj/geo1/project1/seat/tag_component",
            's@component_id = "seat";',
        )
        self.assertIsNone(result)

    def test_internal_guard_needs_no_hou(self):
        """The internal-node check parses the name from the path, so it works
        even without hou (offline). This is intentional — it's a cheap,
        deterministic structural protection."""
        import edini.project.guards as g
        g.hou = None  # type: ignore[attr-defined]
        result = g.lint_wrangle_snippet(
            "/x/y/__edini_axis_bake", "anything();")
        self.assertIsNotNone(result)
        self.assertEqual(result["blocked_by"], "internal_node_guard")


if __name__ == "__main__":
    unittest.main()
