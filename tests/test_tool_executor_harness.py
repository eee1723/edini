"""Dispatcher tests for procedural harness tool handlers."""
import importlib
import os
import sys
import unittest

from tests.mock_hou import MockNode, create_mock_hou


# Add python3.11libs to path so "edini.tool_executor" resolves to the runtime copy.
_RUNTIME_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "python3.11libs")
)
if _RUNTIME_PATH not in sys.path:
    sys.path.insert(0, _RUNTIME_PATH)


class TestHarnessToolHandlers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._previous_hou = sys.modules.get("hou")
        cls._previous_hou_ref = MockNode._hou_ref
        cls._previous_edini_modules = {
            name: module
            for name, module in sys.modules.items()
            if name.startswith("edini")
        }

        cls._mock_hou = create_mock_hou()
        sys.modules["hou"] = cls._mock_hou

        # Force reimport so tool_executor and harness pick up the mock hou module.
        for _mod in list(sys.modules):
            if _mod.startswith("edini"):
                del sys.modules[_mod]

        cls.tool_handlers = importlib.import_module("edini.tool_executor").TOOL_HANDLERS

    @classmethod
    def tearDownClass(cls):
        for _mod in list(sys.modules):
            if _mod.startswith("edini"):
                del sys.modules[_mod]
        sys.modules.update(cls._previous_edini_modules)

        if cls._previous_hou is None:
            sys.modules.pop("hou", None)
        else:
            sys.modules["hou"] = cls._previous_hou
        MockNode._hou_ref = cls._previous_hou_ref

    def test_harness_handlers_registered(self):
        expected = {
            "houdini_collect_diagnostics",
            "houdini_run_python_sandbox",
            "houdini_verify_asset",
            "houdini_verify_orientation",
            "houdini_commit_sandbox",
            "houdini_discard_sandbox",
            "houdini_capture_review",
            "houdini_build_procedural_asset",
        }

        self.assertTrue(expected.issubset(set(self.tool_handlers)))

    def test_collect_diagnostics_dispatches(self):
        r = self.tool_handlers["houdini_collect_diagnostics"](node_path="/obj")

        self.assertTrue(r["success"])
        self.assertEqual(r["node_path"], "/obj")

    def test_verify_asset_dispatches_expected(self):
        r = self.tool_handlers["houdini_verify_asset"](
            node_path="/obj",
            expected={"min_points": 1},
        )

        self.assertFalse(r["success"])
        self.assertEqual(r["node_path"], "/obj")

    def test_commit_sandbox_forwards_orientation_params(self):
        """Verify orientation_checks and skip_orientation reach commit_sandbox."""
        captured = {}

        import edini.tool_executor as te_mod
        original = te_mod.commit_sandbox

        def spy(
            sandbox_root_path,
            final_name,
            replace_existing=False,
            orientation_checks=None,
            skip_orientation=False,
            skip_structure_check=False,
        ):
            captured.update(
                sandbox_root_path=sandbox_root_path,
                final_name=final_name,
                replace_existing=replace_existing,
                orientation_checks=orientation_checks,
                skip_orientation=skip_orientation,
                skip_structure_check=skip_structure_check,
            )
            return {"success": True, "committed": True}

        te_mod.commit_sandbox = spy
        try:
            checks = [{"component_id": "wheel", "kind": "radial", "expected_axis": "X"}]
            self.tool_handlers["houdini_commit_sandbox"](
                sandbox_root_path="/obj/sandbox",
                final_name="bike",
                replace_existing=True,
                orientation_checks=checks,
                skip_orientation=True,
            )
        finally:
            te_mod.commit_sandbox = original

        self.assertEqual(captured["sandbox_root_path"], "/obj/sandbox")
        self.assertEqual(captured["final_name"], "bike")
        self.assertTrue(captured["replace_existing"])
        self.assertEqual(captured["orientation_checks"], checks)
        self.assertTrue(captured["skip_orientation"])

    def test_run_python_sandbox_forwards_network_mode(self):
        """network_mode + output_node_name must reach run_python_sandbox."""
        captured = {}

        import edini.tool_executor as te_mod
        original = te_mod.run_python_sandbox

        def spy(code, sandbox_name="procedural", commit_on_success=False,
                delete_on_failure=False, network_mode=False,
                output_node_name=None):
            captured.update(
                code=code,
                sandbox_name=sandbox_name,
                commit_on_success=commit_on_success,
                delete_on_failure=delete_on_failure,
                network_mode=network_mode,
                output_node_name=output_node_name,
            )
            return {"success": True, "sandbox_mode": "network"}

        te_mod.run_python_sandbox = spy
        try:
            self.tool_handlers["houdini_run_python_sandbox"](
                code="container = hou.node(sandbox_root_path)",
                sandbox_name="bike",
                network_mode=True,
                output_node_name="OUT",
                commit_on_success=False,
            )
        finally:
            te_mod.run_python_sandbox = original

        self.assertEqual(captured["sandbox_name"], "bike")
        self.assertTrue(captured["network_mode"])
        self.assertEqual(captured["output_node_name"], "OUT")

    def test_run_python_sandbox_defaults_network_mode_false(self):
        """Omitting network_mode must default to False (single-SOP)."""
        captured = {}

        import edini.tool_executor as te_mod
        original = te_mod.run_python_sandbox

        def spy(code, sandbox_name="procedural", commit_on_success=False,
                delete_on_failure=False, network_mode=False,
                output_node_name=None):
            captured["network_mode"] = network_mode
            captured["output_node_name"] = output_node_name
            return {"success": True}

        te_mod.run_python_sandbox = spy
        try:
            self.tool_handlers["houdini_run_python_sandbox"](
                code="node = hou.pwd()",
            )
        finally:
            te_mod.run_python_sandbox = original

        self.assertFalse(captured["network_mode"])
        self.assertIsNone(captured["output_node_name"])

    def test_build_procedural_asset_forwards_params(self):
        """recipe / sandbox_name / delete_on_failure must reach build_procedural_asset."""
        captured = {}

        import edini.tool_executor as te_mod
        original = te_mod.build_procedural_asset

        def spy(recipe, sandbox_name=None, delete_on_failure=False):
            captured.update(
                recipe=recipe,
                sandbox_name=sandbox_name,
                delete_on_failure=delete_on_failure,
            )
            return {"success": True, "build_mode": "recipe"}

        te_mod.build_procedural_asset = spy
        try:
            recipe = {"components": [{"id": "x", "code": "pass"}]}
            self.tool_handlers["houdini_build_procedural_asset"](
                recipe=recipe,
                sandbox_name="bike",
                delete_on_failure=True,
            )
        finally:
            te_mod.build_procedural_asset = original

        self.assertEqual(captured["recipe"], recipe)
        self.assertEqual(captured["sandbox_name"], "bike")
        self.assertTrue(captured["delete_on_failure"])

    def test_build_procedural_asset_defaults(self):
        """Omitting optional params must pass sandbox_name=None, delete_on_failure=False."""
        captured = {}

        import edini.tool_executor as te_mod
        original = te_mod.build_procedural_asset

        def spy(recipe, sandbox_name=None, delete_on_failure=False):
            captured["sandbox_name"] = sandbox_name
            captured["delete_on_failure"] = delete_on_failure
            return {"success": True}

        te_mod.build_procedural_asset = spy
        try:
            self.tool_handlers["houdini_build_procedural_asset"](
                recipe={"components": [{"id": "x", "code": "pass"}]},
            )
        finally:
            te_mod.build_procedural_asset = original

        self.assertIsNone(captured["sandbox_name"])
        self.assertFalse(captured["delete_on_failure"])


class TestNodeParmsHandler(unittest.TestCase):
    """The houdini_node_parms handler (C-station query tool) must forward
    node_type + category to node_parms()."""

    @classmethod
    def setUpClass(cls):
        cls._previous_hou = sys.modules.get("hou")
        cls._previous_edini_modules = {
            name: module
            for name, module in sys.modules.items()
            if name.startswith("edini")
        }
        cls._mock_hou = create_mock_hou()
        sys.modules["hou"] = cls._mock_hou
        for _mod in list(sys.modules):
            if _mod.startswith("edini"):
                del sys.modules[_mod]
        cls.tool_handlers = importlib.import_module(
            "edini.tool_executor").TOOL_HANDLERS

    @classmethod
    def tearDownClass(cls):
        for _mod in list(sys.modules):
            if _mod.startswith("edini"):
                del sys.modules[_mod]
        sys.modules.update(cls._previous_edini_modules)
        if cls._previous_hou is None:
            sys.modules.pop("hou", None)
        else:
            sys.modules["hou"] = cls._previous_hou

    def test_handler_registered(self):
        self.assertIn("houdini_node_parms", self.tool_handlers)

    def test_forwards_node_type_and_explicit_category(self):
        captured = {}
        import edini.tool_executor as te_mod
        original = te_mod.node_parms

        def spy(node_type, category="Sop"):
            captured.update(node_type=node_type, category=category)
            return {"success": True, "node_type": node_type, "parms": []}

        te_mod.node_parms = spy
        try:
            self.tool_handlers["houdini_node_parms"](
                node_type="normal", category="Object")
        finally:
            te_mod.node_parms = original

        self.assertEqual(captured["node_type"], "normal")
        self.assertEqual(captured["category"], "Object")

    def test_defaults_category_to_sop(self):
        captured = {}
        import edini.tool_executor as te_mod
        original = te_mod.node_parms

        def spy(node_type, category="Sop"):
            captured.update(node_type=node_type, category=category)
            return {"success": True, "node_type": node_type, "parms": []}

        te_mod.node_parms = spy
        try:
            # No category passed -> handler's lambda supplies "Sop".
            self.tool_handlers["houdini_node_parms"](node_type="copytopoints")
        finally:
            te_mod.node_parms = original

        self.assertEqual(captured["node_type"], "copytopoints")
        self.assertEqual(captured["category"], "Sop")


if __name__ == "__main__":
    unittest.main()
