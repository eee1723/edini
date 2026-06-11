"""Tests for Edini procedural harness helpers."""
import unittest

from tests.test_node_utils import MockParm, _mock_hou


from edini import harness


class RaisingParm(MockParm):
    def eval(self):
        raise RuntimeError("bad expression")


class RaisingGeometry:
    def intrinsicValue(self, name):
        raise RuntimeError(f"geometry intrinsic failed: {name}")


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


class TestVerifyAsset(unittest.TestCase):
    def _make_geo_node(self, name="verify_geo", points=12, prims=6):
        obj = _mock_hou.node("/obj")
        node = obj.createNode("null", name)
        _mock_hou.add_node(node)
        node._geometry = _mock_hou.MockGeometry(
            point_count=points,
            prim_count=prims,
            vertex_count=24,
            bounds=(0.0, 1.0, 0.0, 2.0, 0.0, 0.5),
        )
        return node

    def test_verify_passes_non_empty_geometry(self):
        node = self._make_geo_node()

        r = harness.verify_asset(
            node.path(),
            {"min_points": 1, "min_prims": 1, "bounds_nonzero": True},
        )

        self.assertTrue(r["success"])
        self.assertTrue(all(check["passed"] for check in r["checks"]))

    def test_verify_fails_min_points(self):
        node = self._make_geo_node(name="verify_empty_geo", points=0, prims=0)

        r = harness.verify_asset(node.path(), {"min_points": 1, "min_prims": 1})

        self.assertFalse(r["success"])
        failed_names = [check["name"] for check in r["checks"] if not check["passed"]]
        self.assertIn("min_points", failed_names)
        self.assertIn("min_prims", failed_names)

    def test_verify_returns_failure_when_geometry_stats_raise(self):
        node = self._make_geo_node(name="verify_raising_geo")
        node._geometry = RaisingGeometry()

        r = harness.verify_asset(node.path(), {"min_points": 1})

        self.assertFalse(r["success"])
        self.assertIn("geometry intrinsic failed", r["error"])
        self.assertIn("RuntimeError", r["traceback"])
        failed_names = [check["name"] for check in r["checks"] if not check["passed"]]
        self.assertIn("geometry_stats", failed_names)


class TestRunPythonSandbox(unittest.TestCase):
    def test_success_creates_sandbox_and_returns_job_shape(self):
        code = """
root = hou.node(sandbox_root_path)
child = root.createNode("null", "OUT")
hou.add_node(child)
result["output_node"] = child.path()
result["components"] = {"rungs": 8}
"""
        r = harness.run_python_sandbox(code, sandbox_name="ladder", commit_on_success=False)

        self.assertTrue(r["success"])
        self.assertEqual(r["execution_mode"], "live_sandbox")
        self.assertIn("job_id", r)
        self.assertTrue(r["root_path"].startswith("/obj/edini_sandbox_"))
        self.assertEqual(r["result"]["components"]["rungs"], 8)
        self.assertIsNotNone(_mock_hou.node(r["root_path"]))

    def test_failure_preserves_sandbox_and_returns_traceback(self):
        r = harness.run_python_sandbox(
            "print('before failure')\nraise RuntimeError('sandbox boom')",
            sandbox_name="fail_case",
            delete_on_failure=False,
        )

        self.assertFalse(r["success"])
        self.assertEqual(r["execution_mode"], "live_sandbox")
        self.assertIn("sandbox boom", r["error"])
        self.assertIn("before failure", r["output"])
        self.assertIn("RuntimeError", r["traceback"])
        self.assertIsNotNone(_mock_hou.node(r["root_path"]))

    def test_delete_on_failure_collects_diagnostics_before_deletion(self):
        r = harness.run_python_sandbox(
            "raise RuntimeError('delete me')",
            sandbox_name="delete_case",
            delete_on_failure=True,
        )

        self.assertFalse(r["success"])
        self.assertIn("delete me", r["error"])
        self.assertTrue(r["diagnostics"]["success"])
        self.assertEqual(r["diagnostics"]["node_path"], r["root_path"])
        self.assertFalse(r["preserved"])
        self.assertTrue(r["deleted"])
        self.assertIsNone(_mock_hou.node(r["root_path"]))

    def test_deleting_sandbox_root_removes_child_paths_from_mock_registry(self):
        code = """
root = hou.node(sandbox_root_path)
child = root.createNode("null", "LEFT_BEHIND")
result["child_path"] = child.path()
raise RuntimeError("cleanup")
"""
        r = harness.run_python_sandbox(code, sandbox_name="child_cleanup", delete_on_failure=True)

        self.assertFalse(r["success"])
        self.assertTrue(r["deleted"])
        self.assertIsNone(_mock_hou.node(r["root_path"]))
        self.assertIsNone(_mock_hou.node(f"{r['root_path']}/LEFT_BEHIND"))

    def test_success_survives_diagnostics_failure(self):
        original_collect = harness.collect_diagnostics

        def broken_collect(*args, **kwargs):
            raise RuntimeError("diagnostics boom")

        harness.collect_diagnostics = broken_collect
        try:
            r = harness.run_python_sandbox(
                "result['ok'] = True",
                sandbox_name="diag_success",
            )
        finally:
            harness.collect_diagnostics = original_collect

        self.assertTrue(r["success"])
        self.assertTrue(r["result"]["ok"])
        self.assertFalse(r["diagnostics"]["success"])
        self.assertEqual(r["diagnostics"]["node_path"], r["root_path"])
        self.assertIn("diagnostics boom", r["diagnostics"]["error"])

    def test_failure_preserves_original_error_when_diagnostics_fail(self):
        original_collect = harness.collect_diagnostics

        def broken_collect(*args, **kwargs):
            raise RuntimeError("diagnostics boom")

        harness.collect_diagnostics = broken_collect
        try:
            r = harness.run_python_sandbox(
                "raise RuntimeError('original sandbox error')",
                sandbox_name="diag_failure",
            )
        finally:
            harness.collect_diagnostics = original_collect

        self.assertFalse(r["success"])
        self.assertIn("original sandbox error", r["error"])
        self.assertIn("original sandbox error", r["traceback"])
        self.assertFalse(r["diagnostics"]["success"])
        self.assertEqual(r["diagnostics"]["node_path"], r["root_path"])
        self.assertIn("diagnostics boom", r["diagnostics"]["error"])

    def test_commit_on_success_requests_but_does_not_report_commit(self):
        r = harness.run_python_sandbox(
            "result['ok'] = True",
            sandbox_name="commit_scaffold",
            commit_on_success=True,
        )

        self.assertTrue(r["success"])
        self.assertTrue(r["commit_requested"])
        self.assertFalse(r["committed"])

    def test_cleanup_failure_does_not_mask_original_sandbox_error(self):
        original_destroy = harness._destroy_node

        def broken_destroy(path):
            raise RuntimeError("cleanup failure")

        harness._destroy_node = broken_destroy
        try:
            r = harness.run_python_sandbox(
                "print('before cleanup')\nraise RuntimeError('original user failure')",
                sandbox_name="cleanup_failure",
                delete_on_failure=True,
            )
        finally:
            harness._destroy_node = original_destroy

        self.assertFalse(r["success"])
        self.assertIn("original user failure", r["error"])
        self.assertIn("RuntimeError", r["traceback"])
        self.assertIn("before cleanup", r["output"])
        self.assertFalse(r["deleted"])
        self.assertTrue(r["preserved"])
        self.assertIn("cleanup failure", r["delete_error"])


class TestSandboxLifecycle(unittest.TestCase):
    def test_discard_sandbox_deletes_root(self):
        r = harness.run_python_sandbox("result['ok'] = True", sandbox_name="discard_case")
        root_path = r["root_path"]

        d = harness.discard_sandbox(root_path)

        self.assertTrue(d["success"])
        self.assertIsNone(_mock_hou.node(root_path))

    def test_commit_sandbox_renames_root(self):
        r = harness.run_python_sandbox("result['ok'] = True", sandbox_name="commit_case")
        root_path = r["root_path"]

        c = harness.commit_sandbox(root_path, "committed_asset", replace_existing=False)

        self.assertTrue(c["success"])
        self.assertEqual(c["final_path"], "/obj/committed_asset")
        self.assertIsNotNone(_mock_hou.node("/obj/committed_asset"))

    def test_commit_sandbox_reports_committed_when_display_flag_fails_after_rename(self):
        r = harness.run_python_sandbox("result['ok'] = True", sandbox_name="display_fail_case")
        root_path = r["root_path"]
        node = _mock_hou.node(root_path)

        def broken_display_flag(value):
            raise RuntimeError("display flag failed")

        node.setDisplayFlag = broken_display_flag

        c = harness.commit_sandbox(root_path, "display_failed_asset", replace_existing=False)

        self.assertFalse(c["success"])
        self.assertTrue(c["committed"])
        self.assertEqual(c["final_path"], "/obj/display_failed_asset")
        self.assertIn("display flag failed", c["display_error"])
        self.assertIsNone(_mock_hou.node(root_path))
        self.assertIsNotNone(_mock_hou.node("/obj/display_failed_asset"))

    def test_commit_sandbox_rejects_name_with_separator_without_mutating_sandbox(self):
        r = harness.run_python_sandbox("result['ok'] = True", sandbox_name="bad_name_case")
        root_path = r["root_path"]

        c = harness.commit_sandbox(root_path, "foo/bar", replace_existing=False)

        self.assertFalse(c["success"])
        self.assertFalse(c["committed"])
        self.assertIn("invalid", c["error"].lower())
        self.assertIsNotNone(_mock_hou.node(root_path))
        self.assertIsNone(_mock_hou.node("/obj/foo/bar"))

    def test_commit_sandbox_rejects_whitespace_name_without_mutating_sandbox(self):
        r = harness.run_python_sandbox("result['ok'] = True", sandbox_name="blank_name_case")
        root_path = r["root_path"]

        c = harness.commit_sandbox(root_path, "   ", replace_existing=False)

        self.assertFalse(c["success"])
        self.assertFalse(c["committed"])
        self.assertIn("invalid", c["error"].lower())
        self.assertIsNotNone(_mock_hou.node(root_path))
        self.assertIsNone(_mock_hou.node("/obj/   "))


if __name__ == "__main__":
    unittest.main()
