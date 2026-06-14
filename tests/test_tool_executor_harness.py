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
        ):
            captured.update(
                sandbox_root_path=sandbox_root_path,
                final_name=final_name,
                replace_existing=replace_existing,
                orientation_checks=orientation_checks,
                skip_orientation=skip_orientation,
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


if __name__ == "__main__":
    unittest.main()
