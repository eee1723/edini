"""Unit tests for edini.project.ports — port protocol constants + validation.

Pure logic (no hou). Run: pytest tests/test_project_ports.py -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python3.11libs"))


class TestPortConstants(unittest.TestCase):
    def test_geometry_port_is_index_0(self):
        from edini.project.ports import GEOMETRY_PORT_INDEX, PORT_KIND_GEOMETRY
        self.assertEqual(GEOMETRY_PORT_INDEX, 0)
        self.assertEqual(PORT_KIND_GEOMETRY, "geometry")

    def test_anchor_port_starts_at_1(self):
        from edini.project.ports import FIRST_ANCHOR_PORT_INDEX, PORT_KIND_ANCHORS
        self.assertEqual(FIRST_ANCHOR_PORT_INDEX, 1)
        self.assertEqual(PORT_KIND_ANCHORS, "anchors")

    def test_scaffold_node_names(self):
        from edini.project.ports import (
            OUT_GEOMETRY_NODE, OUT_ANCHORS_NODE,
            OUTPUT_0_NODE, OUTPUT_1_NODE,
            TAG_COMPONENT_NODE, AXIS_BAKE_NODE, INPUT_FILTER_PREFIX,
            ANCHOR_CLEAN_PREFIX,
        )
        self.assertEqual(OUT_GEOMETRY_NODE, "out_geometry")
        self.assertEqual(OUT_ANCHORS_NODE, "out_anchors")
        self.assertEqual(OUTPUT_0_NODE, "output_0")
        self.assertEqual(OUTPUT_1_NODE, "output_1")
        # Fix 3 / Round-2 Fix A: tag_component is agent-editable (component_id),
        # __edini_axis_bake is internal (orientation axis).
        self.assertEqual(TAG_COMPONENT_NODE, "tag_component")
        self.assertEqual(AXIS_BAKE_NODE, "__edini_axis_bake")
        # Fix 2: scaffold inserts a per-in-port @name Blast filter.
        self.assertEqual(INPUT_FILTER_PREFIX, "filter_")
        # Round-2 Fix B: per-in-port prim-stripping wrangle (internal).
        self.assertEqual(ANCHOR_CLEAN_PREFIX, "__edini_anchor_clean_")


class TestResolveAxisVector(unittest.TestCase):
    """Round-3 Fix D1: resolve_axis_vector maps axis tokens to 3-float vectors.
    Pure logic — the scaffold bakes these into __edini_axis_bake and
    verify_orientation reads them. A wrong mapping = silent wrong orientation."""

    def test_all_six_tokens_resolve(self):
        from edini.project.ports import resolve_axis_vector
        self.assertEqual(resolve_axis_vector("X"), (1.0, 0.0, 0.0))
        self.assertEqual(resolve_axis_vector("Y"), (0.0, 1.0, 0.0))
        self.assertEqual(resolve_axis_vector("Z"), (0.0, 0.0, 1.0))
        self.assertEqual(resolve_axis_vector("-X"), (-1.0, 0.0, 0.0))
        self.assertEqual(resolve_axis_vector("-Y"), (0.0, -1.0, 0.0))
        self.assertEqual(resolve_axis_vector("-Z"), (0.0, 0.0, -1.0))

    def test_bad_token_raises(self):
        """A typo'd axis must raise (not silently bake a wrong vector)."""
        from edini.project.ports import resolve_axis_vector
        for bad in ("y", "Up", "Z+", "", "XY", None):
            with self.assertRaises((ValueError, TypeError),
                                   msg=f"should reject {bad!r}"):
                resolve_axis_vector(bad)  # type: ignore[arg-type]

    def test_default_axis_constant(self):
        from edini.project.ports import DEFAULT_COMPONENT_AXIS, AXIS_VECTORS
        self.assertEqual(DEFAULT_COMPONENT_AXIS, "Y")
        # Default must be a legal token.
        self.assertIn(DEFAULT_COMPONENT_AXIS, AXIS_VECTORS)


class TestInternalNodePredicate(unittest.TestCase):
    """Round-2 Fix A: is_internal_scaffold_node marks __-prefixed nodes as
    platform-owned (the agent must not edit them; the guard refuses snippet
    edits on them). Pure logic — no hou."""

    def test_double_underscore_prefix_is_internal(self):
        from edini.project.ports import is_internal_scaffold_node
        self.assertTrue(is_internal_scaffold_node("__edini_axis_bake"))
        self.assertTrue(is_internal_scaffold_node("__edini_anchor_clean_seat_leg_fr"))
        self.assertTrue(is_internal_scaffold_node("__anything"))

    def test_single_or_no_underscore_is_not_internal(self):
        from edini.project.ports import is_internal_scaffold_node
        self.assertFalse(is_internal_scaffold_node("tag_component"))
        self.assertFalse(is_internal_scaffold_node("out_geometry"))
        self.assertFalse(is_internal_scaffold_node("_partial"))  # single _ not enough
        self.assertFalse(is_internal_scaffold_node("filter_seat_leg_fr"))

    def test_non_string_is_not_internal(self):
        from edini.project.ports import is_internal_scaffold_node
        self.assertFalse(is_internal_scaffold_node(None))
        self.assertFalse(is_internal_scaffold_node(""))
        self.assertFalse(is_internal_scaffold_node(123))


class TestPortValidation(unittest.TestCase):
    def test_validate_ports_ok(self):
        from edini.project.ports import validate_component_ports
        ports = {
            "out": [
                {"index": 0, "kind": "geometry", "description": "main"},
                {"index": 1, "kind": "anchors", "points": [
                    {"name": "a", "role": "mount", "description": ""}],
                 "description": "anchors"},
            ],
            "in": [],
        }
        # 不 raise 即通过
        validate_component_ports(ports)

    def test_validate_ports_geometry_must_be_index_0(self):
        from edini.project.ports import validate_component_ports
        ports = {"out": [{"index": 0, "kind": "anchors", "points": []}], "in": []}
        with self.assertRaises(ValueError):
            validate_component_ports(ports)

    def test_validate_ports_anchor_point_needs_name(self):
        from edini.project.ports import validate_component_ports
        ports = {"out": [
            {"index": 0, "kind": "geometry"},
            {"index": 1, "kind": "anchors", "points": [
                {"role": "mount"}]},  # 缺 name
        ], "in": []}
        with self.assertRaises(ValueError):
            validate_component_ports(ports)

    def test_validate_ports_anchor_name_must_be_legal(self):
        """锚点 @name 必须是合法 group 名（字母数字下划线）。"""
        from edini.project.ports import validate_component_ports
        ports = {"out": [
            {"index": 0, "kind": "geometry"},
            {"index": 1, "kind": "anchors", "points": [
                {"name": "bad name!", "role": "mount"}]},
        ], "in": []}
        with self.assertRaises(ValueError):
            validate_component_ports(ports)


class TestInPortValidation(unittest.TestCase):
    def test_validate_in_port_needs_from(self):
        from edini.project.ports import validate_component_ports
        ports = {"out": [{"index": 0, "kind": "geometry"}],
                 "in": [{"port": 1, "anchor": "x"}]}  # 缺 from
        with self.assertRaises(ValueError):
            validate_component_ports(ports)

    def test_validate_in_port_needs_anchor(self):
        from edini.project.ports import validate_component_ports
        ports = {"out": [{"index": 0, "kind": "geometry"}],
                 "in": [{"from": "chassis", "port": 1}]}  # 缺 anchor
        with self.assertRaises(ValueError):
            validate_component_ports(ports)

    def test_validate_in_port_rejects_duplicate_anchor(self):
        """同组件内 in[].anchor 撞名拒绝（避免节点名冲突）。"""
        from edini.project.ports import validate_component_ports
        ports = {"out": [{"index": 0, "kind": "geometry"}],
                 "in": [
                     {"from": "chassis", "port": 1, "anchor": "wheel_mount"},
                     {"from": "frame", "port": 0, "anchor": "wheel_mount"}]}
        with self.assertRaises(ValueError):
            validate_component_ports(ports)

    def test_validate_in_port_needs_port(self):
        """ports.in[] 的 port 字段必填（修复前完全不验证，builder 里抛裸 KeyError）。"""
        from edini.project.ports import validate_component_ports
        ports = {"out": [{"index": 0, "kind": "geometry"}],
                 "in": [{"from": "chassis", "anchor": "wheel_mount"}]}  # 缺 port
        with self.assertRaises(ValueError):
            validate_component_ports(ports)

    def test_validate_in_port_rejects_non_int_port(self):
        from edini.project.ports import validate_component_ports
        ports = {"out": [{"index": 0, "kind": "geometry"}],
                 "in": [{"from": "chassis", "port": "1", "anchor": "x"}]}
        with self.assertRaises(ValueError):
            validate_component_ports(ports)


class TestPortSchemaContract(unittest.TestCase):
    """Tests for the aggregated-error + expected-schema behaviour (Fix: ports
    schema used to fail one field at a time, forcing 5 trial-and-error rounds)."""

    def test_expected_ports_schema_returns_filled_example(self):
        from edini.project.ports import expected_ports_schema
        schema = expected_ports_schema()
        # Must contain the full contract so it can be shown in one error.
        out0 = schema["out"][0]
        self.assertEqual(out0["index"], 0)
        self.assertEqual(out0["kind"], "geometry")
        self.assertTrue(any(o.get("kind") == "anchors" for o in schema["out"]))
        in0 = schema["in"][0]
        for field in ("from", "port", "anchor"):
            self.assertIn(field, in0)

    def test_aggregated_error_lists_all_violations(self):
        """Multiple violations at once → all listed in one error (not first-wins)."""
        from edini.project.ports import validate_component_ports
        ports = {
            "out": [{"index": 0, "kind": "anchors", "points": []}],  # out[0] wrong kind
            "in": [
                {"port": 1, "anchor": "x"},          # missing from
                {"from": "c", "port": -1, "anchor": "bad name!"},  # bad port + bad anchor
            ],
        }
        try:
            validate_component_ports(ports)
            self.fail("should have raised")
        except ValueError as e:
            msg = str(e)
            # All distinct violations surfaced in the single error.
            self.assertIn("out[0]", msg)
            self.assertIn("'from'", msg)
            self.assertIn("'port'", msg)
            self.assertIn("'anchor'", msg)
            # And the expected schema is appended so the caller learns the
            # whole contract at once.
            self.assertIn("Expected ports shape", msg)

    def test_error_includes_full_expected_shape(self):
        """The error must teach the full contract, not just name the bad field."""
        from edini.project.ports import validate_component_ports
        ports = {"out": [{"index": 1, "kind": "geometry"}], "in": []}
        try:
            validate_component_ports(ports)
            self.fail("should have raised")
        except ValueError as e:
            self.assertIn("Expected ports shape", str(e))


class TestRouteContract(unittest.TestCase):
    """Tests for validate_route_contract (Fix 2): static cross-component
    anchor-routing check. Pure logic — no hou, no cook. Catches typo'd anchor
    names / missing upstreams at declaration time, before any geometry exists."""

    def _decl(self, components):
        return {"components": components}

    def test_clean_declaration_yields_no_warnings(self):
        """A well-routed declaration: every in[].anchor exists upstream."""
        from edini.project.ports import validate_route_contract
        decl = self._decl([
            {"id": "tabletop",
             "ports": {"out": [
                 {"index": 0, "kind": "geometry"},
                 {"index": 1, "kind": "anchors", "points": [
                     {"name": "leg_mount_fr"}, {"name": "leg_mount_fl"}]}]}},
            {"id": "legs",
             "ports": {"out": [{"index": 0, "kind": "geometry"}],
                       "in": [
                           {"from": "tabletop", "port": 1, "anchor": "leg_mount_fr"},
                           {"from": "tabletop", "port": 1, "anchor": "leg_mount_fl"}]}},
        ])
        self.assertEqual(validate_route_contract(decl), [])

    def test_warns_on_anchor_not_emitted_upstream(self):
        """The chair-log bug, made declarative: leg consumes 'leg_mount_fr' but
        upstream only emits differently-named anchors. Static check flags it."""
        from edini.project.ports import validate_route_contract
        decl = self._decl([
            {"id": "seat",
             "ports": {"out": [
                 {"index": 0, "kind": "geometry"},
                 {"index": 1, "kind": "anchors", "points": [
                     {"name": "leg_fr"}, {"name": "backrest_c"}]}]}},
            {"id": "leg",
             "ports": {"out": [{"index": 0, "kind": "geometry"}],
                       "in": [{"from": "seat", "port": 1, "anchor": "leg_mount_fr"}]}},
        ])
        warnings = validate_route_contract(decl)
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0]["component"], "leg")
        self.assertEqual(warnings[0]["anchor"], "leg_mount_fr")
        self.assertIn("leg_mount_fr", warnings[0]["reason"])

    def test_warns_on_missing_upstream_component(self):
        """in[].from names a component that isn't declared (typo / not-yet-built)."""
        from edini.project.ports import validate_route_contract
        decl = self._decl([
            {"id": "leg",
             "ports": {"out": [{"index": 0, "kind": "geometry"}],
                       "in": [{"from": "tabletoop", "port": 1, "anchor": "x"}]}},
        ])
        warnings = validate_route_contract(decl)
        self.assertEqual(len(warnings), 1)
        self.assertIn("tabletoop", warnings[0]["reason"])

    def test_empty_upstream_anchors_does_not_warn(self):
        """If the upstream declares NO anchor names (anchors port with no
        points yet), we can't check — don't false-positive. The runtime Blast
        filter is the enforcement; this static check only flags KNOWN mismatches."""
        from edini.project.ports import validate_route_contract
        decl = self._decl([
            {"id": "seat",
             "ports": {"out": [
                 {"index": 0, "kind": "geometry"},
                 {"index": 1, "kind": "anchors", "points": []}]}},
            {"id": "leg",
             "ports": {"out": [{"index": 0, "kind": "geometry"}],
                       "in": [{"from": "seat", "port": 1, "anchor": "leg_fr"}]}},
        ])
        self.assertEqual(validate_route_contract(decl), [])

    def test_handles_malformed_declaration_gracefully(self):
        """Non-dict components / missing ports must not crash the check."""
        from edini.project.ports import validate_route_contract
        decl = {"components": [None, {"id": "x"}, {"ports": {}}]}
        # No exception, no warnings (nothing to check).
        self.assertEqual(validate_route_contract(decl), [])


if __name__ == "__main__":
    unittest.main()
