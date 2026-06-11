"""Tests for Edini procedural harness helpers."""
import os
import sys
import unittest

from tests.mock_hou import create_mock_hou

_mock_hou = create_mock_hou()
sys.modules["hou"] = _mock_hou
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python3.11libs"))

for _mod in list(sys.modules):
    if _mod.startswith("edini"):
        del sys.modules[_mod]

from edini import harness


class TestHarnessImports(unittest.TestCase):
    def test_harness_module_imports(self):
        self.assertTrue(hasattr(harness, "make_job_id"))


class TestCollectDiagnostics(unittest.TestCase):
    def test_missing_node(self):
        r = harness.collect_diagnostics("/obj/missing")

        self.assertFalse(r["success"])
        self.assertEqual(r["node_path"], "/obj/missing")
        self.assertIn("not found", r["error"].lower())

    def test_node_with_errors_warnings_and_geometry(self):
        obj = _mock_hou.node("/obj")
        node = obj.createNode("box", "diag_box")
        _mock_hou.add_node(node)
        node._errors = ["bad cook"]
        node._warnings = ["low confidence"]
        node._geometry = _mock_hou.MockGeometry(
            point_count=4,
            prim_count=1,
            vertex_count=4,
            bounds=(0.0, 1.0, 0.0, 2.0, 0.0, 3.0),
        )

        r = harness.collect_diagnostics(node.path(), include_geometry=True, include_parms=True)

        self.assertTrue(r["success"])
        self.assertEqual(r["node_path"], node.path())
        self.assertEqual(r["node_errors"], ["bad cook"])
        self.assertEqual(r["node_warnings"], ["low confidence"])
        self.assertEqual(r["geometry"]["point_count"], 4)
        self.assertEqual(r["geometry"]["bounds"]["size"], [1.0, 2.0, 3.0])
        self.assertIn("parameters", r)


if __name__ == "__main__":
    unittest.main()
