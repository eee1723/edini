"""Dispatcher tests for procedural harness tool handlers."""
import os
import sys
import unittest

from tests.mock_hou import create_mock_hou


_mock_hou = create_mock_hou()
sys.modules["hou"] = _mock_hou

# Add python3.11libs to path so "edini.tool_executor" resolves to the runtime copy.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python3.11libs"))

# Force reimport so tool_executor and harness pick up the mock hou module.
for _mod in list(sys.modules):
    if _mod.startswith("edini"):
        del sys.modules[_mod]

from edini.tool_executor import TOOL_HANDLERS


class TestHarnessToolHandlers(unittest.TestCase):
    def test_harness_handlers_registered(self):
        expected = {
            "houdini_collect_diagnostics",
            "houdini_run_python_sandbox",
            "houdini_verify_asset",
            "houdini_commit_sandbox",
            "houdini_discard_sandbox",
        }

        self.assertTrue(expected.issubset(set(TOOL_HANDLERS)))
        self.assertNotIn("houdini_capture_viewport_safe", TOOL_HANDLERS)

    def test_collect_diagnostics_dispatches(self):
        r = TOOL_HANDLERS["houdini_collect_diagnostics"](node_path="/obj")

        self.assertTrue(r["success"])
        self.assertEqual(r["node_path"], "/obj")

    def test_verify_asset_dispatches_expected(self):
        r = TOOL_HANDLERS["houdini_verify_asset"](
            node_path="/obj",
            expected={"min_points": 1},
        )

        self.assertFalse(r["success"])
        self.assertEqual(r["node_path"], "/obj")


if __name__ == "__main__":
    unittest.main()
