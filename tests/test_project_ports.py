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
        )
        self.assertEqual(OUT_GEOMETRY_NODE, "out_geometry")
        self.assertEqual(OUT_ANCHORS_NODE, "out_anchors")
        self.assertEqual(OUTPUT_0_NODE, "output_0")
        self.assertEqual(OUTPUT_1_NODE, "output_1")


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


if __name__ == "__main__":
    unittest.main()
