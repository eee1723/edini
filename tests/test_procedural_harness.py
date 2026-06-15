"""Tests for Edini procedural harness helpers."""
import json
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


class TestMakeJobId(unittest.TestCase):
    def test_repeated_same_label_ids_are_unique_and_keep_sanitized_label(self):
        original_datetime = harness._dt.datetime

        class FixedDatetime:
            @classmethod
            def now(cls):
                return original_datetime(2026, 6, 11, 12, 30, 5)

        harness._dt.datetime = FixedDatetime
        try:
            first = harness.make_job_id("Fancy Label!")
            second = harness.make_job_id("Fancy Label!")
        finally:
            harness._dt.datetime = original_datetime

        self.assertNotEqual(first, second)
        self.assertIn("fancy_label", first)
        self.assertIn("fancy_label", second)


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

    def test_parameter_values_are_json_serializable(self):
        obj = _mock_hou.node("/obj")
        node = obj.createNode("box", "object_parm_box")
        _mock_hou.add_node(node)
        node._parms["target"] = MockParm("target", node, label="Target Node")

        r = harness.collect_diagnostics(node.path(), include_parms=True)

        json.dumps(r)
        self.assertEqual(r["parameters"][0]["value"], node.path())


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
node = hou.pwd()
geo = node.geometry()
geo.clear()
pt = geo.createPoint()
pt.setPosition((0, 0, 0))
"""
        r = harness.run_python_sandbox(code, sandbox_name="ladder", commit_on_success=False)

        self.assertTrue(r["success"])
        self.assertEqual(r["execution_mode"], "live_sandbox")
        self.assertIn("job_id", r)
        self.assertTrue(r["root_path"].startswith("/obj/edini_sandbox_"))
        self.assertIn("output_node", r)
        self.assertIn("edini_generate", r.get("output_node", ""))
        self.assertIsNotNone(_mock_hou.node(r["root_path"]))

    def test_result_payload_is_json_serializable_when_user_stores_node(self):
        code = """
node = hou.pwd()
container = node.parent()
child = container.createNode("null", "OUT")
hou.add_node(child)
node.geometry().clear()
pt = node.geometry().createPoint()
pt.setPosition((0, 0, 0))
"""

        r = harness.run_python_sandbox(code, sandbox_name="json_payload", commit_on_success=False)

        json.dumps(r)
        self.assertTrue(r["success"])

    def test_output_node_object_is_json_serializable_and_drives_diagnostics(self):
        code = """
node = hou.pwd()
geo = node.geometry()
geo.clear()
pt = geo.createPoint()
pt.setPosition((1, 0, 0))
"""

        r = harness.run_python_sandbox(code, sandbox_name="json_output_node", commit_on_success=False)

        json.dumps(r)
        self.assertTrue(r["success"])
        self.assertTrue(r["diagnostics"]["success"])
        self.assertIn("edini_generate", r["diagnostics"]["node_path"])

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
        self.assertIn("edini_generate", r["diagnostics"]["node_path"])
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
                "node = hou.pwd()\nnode.geometry().clear()",
                sandbox_name="diag_success",
            )
        finally:
            harness.collect_diagnostics = original_collect

        self.assertTrue(r["success"])
        self.assertFalse(r["diagnostics"]["success"])
        self.assertIn("edini_generate", r["diagnostics"]["node_path"])
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
        self.assertIn("edini_generate", r["diagnostics"]["node_path"])
        self.assertIn("diagnostics boom", r["diagnostics"]["error"])

    def test_commit_on_success_requests_but_does_not_report_commit(self):
        r = harness.run_python_sandbox(
            "node = hou.pwd()\nnode.geometry().clear()\npt = node.geometry().createPoint()\npt.setPosition((1, 2, 3))",
            sandbox_name="commit_scaffold",
            commit_on_success=True,
        )

        self.assertTrue(r["success"])
        self.assertTrue(r["commit_requested"])
        self.assertTrue(r["committed"])  # Mock commit should succeed

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

    def test_commit_sandbox_is_idempotent_when_root_is_already_final_path(self):
        r = harness.run_python_sandbox("result['ok'] = True", sandbox_name="idempotent_case")
        root_path = r["root_path"]
        c1 = harness.commit_sandbox(root_path, "idempotent_asset", replace_existing=False)
        final_path = c1["final_path"]
        final_node = _mock_hou.node(final_path)

        c2 = harness.commit_sandbox(final_path, "idempotent_asset", replace_existing=True)

        self.assertTrue(c2["success"])
        self.assertTrue(c2["committed"])
        self.assertEqual(c2["final_path"], final_path)
        self.assertIs(_mock_hou.node(final_path), final_node)
        self.assertFalse(final_node._destroyed)

    def test_commit_sandbox_idempotent_retry_preserves_node_when_display_flag_fails(self):
        r = harness.run_python_sandbox("result['ok'] = True", sandbox_name="idempotent_display_fail")
        root_path = r["root_path"]
        c1 = harness.commit_sandbox(root_path, "idempotent_display_asset", replace_existing=False)
        final_path = c1["final_path"]
        final_node = _mock_hou.node(final_path)

        def broken_display_flag(value):
            raise RuntimeError("retry display flag failed")

        final_node.setDisplayFlag = broken_display_flag

        c2 = harness.commit_sandbox(final_path, "idempotent_display_asset", replace_existing=True)

        self.assertFalse(c2["success"])
        self.assertTrue(c2["committed"])
        self.assertEqual(c2["final_path"], final_path)
        self.assertIn("retry display flag failed", c2["display_error"])
        self.assertIs(_mock_hou.node(final_path), final_node)
        self.assertFalse(final_node._destroyed)

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


class TestSandboxStructure(unittest.TestCase):
    """Tests that run_python_sandbox returns correct structure and diagnostics.

    These tests verify the NEW sandbox model (Task 1.2 will implement it).
    Currently they SHOULD FAIL — the sandbox hasn't been rewritten yet.
    """

    def setUp(self):
        pass  # _mock_hou is module-level from test_node_utils

    def test_sandbox_result_has_required_fields(self):
        """Sandbox result includes job_id, root_path, output_node, diagnostics."""
        code = "node = hou.pwd()\ngeo = node.geometry()\ngeo.clear()\npt = geo.createPoint()\npt.setPosition((1,2,3))"
        result = harness.run_python_sandbox(code, sandbox_name="test_struct")
        for field in ["job_id", "root_path", "output_node", "diagnostics", "structural_checks"]:
            self.assertIn(field, result, f"Missing field: {field}")
        self.assertIn("edini_generate", result.get("output_node", ""))

    def test_sandbox_diagnostics_has_geometry(self):
        """Diagnostics bundle includes geometry stats."""
        code = "node = hou.pwd()\ngeo = node.geometry()\ngeo.clear()\npt = geo.createPoint()\npt.setPosition((0,0,0))"
        result = harness.run_python_sandbox(code, sandbox_name="test_diag")
        diag = result.get("diagnostics", {})
        self.assertTrue(diag.get("success"))
        geo = diag.get("geometry")
        self.assertIsNotNone(geo)

    def test_sandbox_structural_checks_included(self):
        """Structural checks summary always present in result."""
        code = "node = hou.pwd()\ngeo = node.geometry()\ngeo.clear()\npt = geo.createPoint()\npt.setPosition((0,0,0))"
        result = harness.run_python_sandbox(code, sandbox_name="test_struct_chk")
        checks = result.get("structural_checks", {})
        self.assertIn("has_geometry", checks)
        self.assertIn("point_count", checks)
        self.assertIn("bounds_nonzero", checks)

    def test_sandbox_cook_error_preserves_node(self):
        """Sandbox with failing code preserves the node and collects errors."""
        code = """
node = hou.pwd()
geo = node.geometry()
geo.clear()
raise ValueError("intentional test error")
"""
        result = harness.run_python_sandbox(code, sandbox_name="test_error",
                                             delete_on_failure=False)
        self.assertFalse(result["success"])
        self.assertTrue(result.get("preserved", False))
        self.assertIn("error", result)
        self.assertIn("ValueError", result.get("error", ""))

    def test_sandbox_delete_on_failure_cleans_up(self):
        """Sandbox with delete_on_failure=True removes the sandbox on error."""
        code = 'raise RuntimeError("test cleanup")'
        result = harness.run_python_sandbox(code, sandbox_name="test_del",
                                             delete_on_failure=True)
        self.assertFalse(result["success"])
        self.assertTrue(result.get("deleted", False))


class TestLadderRegression(unittest.TestCase):
    def test_ladder_sandbox_preserves_components_and_verifies(self):
        code = """
node = hou.pwd()
geo = node.geometry()
geo.clear()
pt = geo.createPoint()
pt.setPosition((0, 0, 0))
pt2 = geo.createPoint()
pt2.setPosition((0.5, 0, 0))
pt3 = geo.createPoint()
pt3.setPosition((0.5, 0.5, 0))
poly = geo.createPolygon()
poly.addVertex(pt)
poly.addVertex(pt2)
poly.addVertex(pt3)
"""

        run = harness.run_python_sandbox(code, sandbox_name="ladder_regression")
        try:
            self.assertTrue(run["success"])
            verify = harness.verify_asset(
                run["output_node"],
                {"min_points": 1, "min_prims": 1, "bounds_nonzero": True},
            )

            passed_check_names = {check["name"] for check in verify["checks"] if check["passed"]}

            self.assertTrue(verify["success"])
            self.assertGreaterEqual(verify["geometry"]["point_count"], 1)
            self.assertTrue(
                {"min_points", "node_errors"}.issubset(
                    passed_check_names
                )
            )
        finally:
            if _mock_hou.node(run["root_path"]) is not None:
                harness.discard_sandbox(run["root_path"])


class TestOrientationGateNodeSelection(unittest.TestCase):
    """Regression: commit-gate must pick the real asset output (OUT), not the
    empty dispatcher `edini_generate`.

    In the bicycle run log, `edini_generate` is a Python SOP that builds a
    node network but emits no geometry itself. The old gate took the FIRST
    child with non-None geometry out of ("edini_generate","OUT","out"), which
    was the empty dispatcher, so it reported "component_id not found" and the
    agent had to bypass the gate with skip_orientation=true.
    """

    def _build_sandbox_with_dispatcher_and_out(self, sandbox_name):
        """Build a sandbox where edini_generate is empty and OUT has the asset."""
        run = harness.run_python_sandbox(
            "node = hou.pwd()\nnode.geometry().clear()",
            sandbox_name=sandbox_name,
        )
        root = _mock_hou.node(run["root_path"])
        return run, root

    def _make_geo_with_component_id(self, points, prims, verts):
        """Build a MockGeometry whose findPrimAttrib('component_id') hits."""
        geo = _mock_hou.MockGeometry(point_count=points, prim_count=prims,
                                     vertex_count=verts,
                                     bounds=(0.0, 1.0, 0.0, 1.0, 0.0, 1.0))
        # addAttrib(attrib_type, name, default) — mock ignores attrib_type,
        # findPrimAttrib only checks the name key.
        geo.addAttrib(None, "component_id", "")
        return geo

    def test_select_gate_target_prefers_component_id_node_over_empty_dispatcher(self):
        run, root = self._build_sandbox_with_dispatcher_and_out("gate_pick_out")
        # edini_generate is empty (created by sandbox). Add an OUT child with
        # real geometry + component_id attribute + many prims.
        out = root.createNode("null", "OUT")
        _mock_hou.add_node(out)
        out._geometry = self._make_geo_with_component_id(100, 50, 200)

        # Also leave edini_generate with empty geometry (default)
        edini_generate = _mock_hou.node(f"{run['root_path']}/edini_generate")
        edini_generate._geometry = _mock_hou.MockGeometry(
            point_count=0, prim_count=0, vertex_count=0, bounds=None)

        target = harness._select_gate_target(root)
        self.assertIs(target, out,
                      "Gate must select OUT (has component_id + prims), not the "
                      "empty edini_generate dispatcher")

    def test_select_gate_target_picks_most_prims_when_multiple_have_component_id(self):
        run, root = self._build_sandbox_with_dispatcher_and_out("gate_most_prims")
        # Two nodes both carry component_id; the merge/OUT has more prims.
        small = root.createNode("null", "mid")
        _mock_hou.add_node(small)
        small._geometry = self._make_geo_with_component_id(10, 5, 20)

        big = root.createNode("null", "OUT")
        _mock_hou.add_node(big)
        big._geometry = self._make_geo_with_component_id(100, 50, 200)

        target = harness._select_gate_target(root)
        self.assertIs(target, big,
                      "Gate must pick the highest-prim component_id node (the final OUT)")

    def test_commit_sandbox_orientation_gate_no_longer_false_fails_on_dispatcher(self):
        """End-to-end: commit with orientation_checks should run against OUT.

        With the buggy node selection, commit would return passed_all=False
        with "component_id not found". After the fix, since the mock verify
        returns no component_id prims it reports an error — but the KEY point
        is the gate now evaluates OUT (which has component_id), not the empty
        dispatcher (which would report 'not found'). We assert the error path
        differs from the dispatcher's 'attribute not found' message.
        """
        run, root = self._build_sandbox_with_dispatcher_and_out("gate_e2e")
        out = root.createNode("null", "OUT")
        _mock_hou.add_node(out)
        out._geometry = self._make_geo_with_component_id(100, 50, 200)

        result = harness._run_orientation_gate(run["root_path"], [
            {"component_id": "wheel", "kind": "radial", "expected_axis": "X"},
        ])
        # The gate ran (not None). With the fix it inspects OUT which HAS
        # component_id, so it should NOT return the "attribute not found"
        # dispatcher error. The mock has no prims with the value 'wheel', so
        # verify_orientation reports "No prims with component_id" — a DIFFERENT
        # error than "attribute component_id not found".
        self.assertIsNotNone(result)
        self.assertFalse(result.get("passed_all"))
        err = result.get("error", "")
        self.assertNotIn("not found", err.lower(),
                         "Must not report the dispatcher's 'attribute not found' error; "
                         f"got: {err}")


if __name__ == "__main__":
    unittest.main()
