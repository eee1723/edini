"""Tests for Edini procedural harness helpers."""
import unittest

from tests.test_node_utils import MockParm, _mock_hou


from edini import harness


class RaisingParm(MockParm):
    def eval(self):
        raise RuntimeError("bad expression")


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

    def test_parameter_eval_error_is_reported(self):
        obj = _mock_hou.node("/obj")
        node = obj.createNode("box", "bad_parm_box")
        _mock_hou.add_node(node)
        node._parms["bad"] = RaisingParm("bad", label="Bad Expression")

        r = harness.collect_diagnostics(node.path(), include_parms=True)

        self.assertTrue(r["success"])
        self.assertEqual(r["parameters"][0]["name"], "bad")
        self.assertEqual(r["parameters"][0]["label"], "Bad Expression")
        self.assertIn("bad expression", r["parameters"][0]["error"])
        self.assertNotIn("value", r["parameters"][0])


if __name__ == "__main__":
    unittest.main()
