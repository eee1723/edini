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


if __name__ == "__main__":
    unittest.main()
