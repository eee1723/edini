"""Tests for the validate_asset tool entry point in tool_executor.

tool_executor is the Houdini-side HTTP server that dispatches Pi tool calls.
Its validate_asset handler wraps asset_model.validate_asset + resolve_skeleton
and adds the 'asset_path' file-load and 'resolve' preview behaviour. This test
verifies the handler's contract independently of the HTTP layer (we call the
handler function directly) and without Houdini (a mock hou is installed).

Mock isolation (CRITICAL): MockNode._hou_ref is a CLASS attribute shared across
every mock instance in the process. A module-level mock install would leak our
_hou_ref into sibling modules (notably test_node_utils's geometry-health tests,
which create points via MockPoint and read them back via hou.node() — a stale
_hou_ref makes hou.node() return None and the whole class fails). We therefore
install + restore the mock in setUpClass/tearDownClass, following the same
contract as test_recipe_library: snapshot both _hou_ref and sys.modules['hou'],
restore both on teardown.

The asset_model logic itself is exhaustively covered by test_asset_model.py;
here we test ONLY the tool-handler wrapper: argument handling, file loading,
the resolve flag, and error surfacing.
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python3.11libs"))
sys.path.insert(0, os.path.dirname(__file__))

from mock_hou import create_mock_hou, MockNode  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
BICYCLE_PATH = os.path.join(
    HERE, "..", "python3.11libs", "edini", "data", "bicycle.asset.json"
)


class _HouMockTestCase(unittest.TestCase):
    """Shared base: install a fresh mock hou for the class, import tool_executor
    against it, and restore the prior global mock state on teardown so sibling
    test modules see an unchanged MockNode._hou_ref."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._prev_hou = sys.modules.get("hou")
        cls._prev_hou_ref = MockNode._hou_ref
        sys.modules["hou"] = create_mock_hou()
        # tool_executor/node_utils/harness read sys.modules['hou'] at import
        # time. Drop any cached edini.* so they rebind to our mock.
        for _mod in list(sys.modules):
            if _mod.startswith("edini"):
                del sys.modules[_mod]
        from edini import tool_executor  # noqa: E402
        # staticmethod so `self.validate_asset(...)` doesn't pass `self` as the
        # first positional arg (the handler is a plain function, not a method).
        cls.validate_asset = staticmethod(tool_executor.validate_asset)
        cls.build_asset = staticmethod(tool_executor.build_asset)

    @classmethod
    def tearDownClass(cls):
        MockNode._hou_ref = cls._prev_hou_ref
        sys.modules["hou"] = cls._prev_hou
        # Drop our-mock-bound edini modules so later modules reimport cleanly.
        for _mod in list(sys.modules):
            if _mod.startswith("edini"):
                del sys.modules[_mod]
        super().tearDownClass()


def _valid_inline_asset():
    return {
        "asset_schema_version": 1,
        "id": "unit_test",
        "params": {"w": {"kind": "primary", "default": 1.0}},
        "skeleton": {"p": {"expr": ["0", "w", "0"]}},
        "components": [],
    }


# ===================================================================
# Argument handling
# ===================================================================

class TestValidateAssetArguments(_HouMockTestCase):

    def test_no_asset_no_path_returns_error(self):
        result = self.validate_asset()
        self.assertFalse(result["success"])
        self.assertIn("asset", result["error"].lower())

    def test_inline_asset_succeeds(self):
        result = self.validate_asset(asset=_valid_inline_asset())
        self.assertTrue(result["success"], result)

    def test_asset_path_loads_file(self):
        result = self.validate_asset(asset_path=BICYCLE_PATH)
        self.assertTrue(result["success"], result)

    def test_missing_asset_path_returns_error(self):
        result = self.validate_asset(asset_path="/nonexistent/asset.json")
        self.assertFalse(result["success"])
        self.assertIn("could not read", result["error"])

    def test_inline_takes_precedence_over_path(self):
        # When both given, inline is used (asset_path is only a fallback).
        inline = _valid_inline_asset()
        result = self.validate_asset(asset=inline, asset_path="/nonexistent/asset.json")
        self.assertTrue(result["success"])


# ===================================================================
# The resolve flag — preview coordinates
# ===================================================================

class TestValidateAssetResolve(_HouMockTestCase):

    def test_resolve_false_omits_skeleton(self):
        result = self.validate_asset(asset=_valid_inline_asset(), resolve=False)
        self.assertTrue(result["success"])
        self.assertNotIn("resolved_skeleton", result)

    def test_resolve_true_returns_skeleton(self):
        result = self.validate_asset(asset=_valid_inline_asset(), resolve=True)
        self.assertTrue(result["success"])
        self.assertIn("resolved_skeleton", result)
        # The skeleton points are returned as lists (JSON-serializable).
        self.assertEqual(result["resolved_skeleton"]["p"], [0.0, 1.0, 0.0])

    def test_resolve_on_bicycle_returns_five_points(self):
        result = self.validate_asset(asset_path=BICYCLE_PATH, resolve=True)
        self.assertTrue(result["success"])
        skel = result["resolved_skeleton"]
        self.assertEqual(len(skel), 5)
        for name in ("base", "rear_axle", "front_axle", "bb_center", "ground"):
            self.assertIn(name, skel)
            self.assertEqual(len(skel[name]), 3)

    def test_resolve_skipped_when_validation_fails(self):
        # An invalid asset with resolve=True must NOT attempt resolution.
        bad = _valid_inline_asset()
        del bad["id"]
        result = self.validate_asset(asset=bad, resolve=True)
        self.assertFalse(result["success"])
        self.assertNotIn("resolved_skeleton", result)

    def test_resolve_div_by_zero_surfaced_cleanly(self):
        # A pure-param expression that divides by zero is caught at static
        # validation (pre-eval), so the handler reports it without crashing.
        asset = {
            "asset_schema_version": 1,
            "id": "resolve_fail",
            "params": {"z": {"kind": "primary", "default": 0.0}},
            "skeleton": {"p": {"expr": ["1/z", "0", "0"]}},
            "components": [],
        }
        result = self.validate_asset(asset=asset, resolve=True)
        self.assertFalse(result["success"])


# ===================================================================
# Error surfacing
# ===================================================================

class TestValidateAssetErrors(_HouMockTestCase):

    def test_cycle_error_surfaces(self):
        asset = {
            "asset_schema_version": 1,
            "id": "cyclic",
            "params": {},
            "skeleton": {
                "a": {"expr": ["b[0]", "0", "0"]},
                "b": {"expr": ["a[0]", "0", "0"]},
            },
            "components": [],
        }
        result = self.validate_asset(asset=asset)
        self.assertFalse(result["success"])
        codes = [e["code"] for e in result["errors"]]
        self.assertIn("SKELETON_CYCLE", codes)

    def test_dangling_ref_surfaces(self):
        asset = {
            "asset_schema_version": 1,
            "id": "dangling",
            "params": {},
            "skeleton": {"a": {"expr": ["ghost", "0", "0"]}},
            "components": [],
        }
        result = self.validate_asset(asset=asset)
        self.assertFalse(result["success"])
        codes = [e["code"] for e in result["errors"]]
        self.assertIn("SKELETON_DANGLING_REF", codes)

    def test_result_shape_on_invalid_asset(self):
        # An asset-level validation failure (not a missing-argument error)
        # always carries the standard asset_model keys.
        asset = {
            "asset_schema_version": 1,
            "id": "bad",
            "params": {"a": {"kind": "primary", "default": 1.0}},
            "skeleton": {"a": {"expr": ["ghost", "0", "0"]}},
            "components": [],
        }
        result = self.validate_asset(asset=asset)
        self.assertFalse(result["success"])
        for key in ("success", "errors", "warnings", "summary"):
            self.assertIn(key, result)

    def test_missing_args_returns_short_error(self):
        # A missing-argument early return is a different (handler) layer:
        # it returns {success, error}, NOT the full asset_model shape.
        result = self.validate_asset()
        self.assertFalse(result["success"])
        self.assertIn("error", result)


# ===================================================================
# File-based round trip via the handler
# ===================================================================

class TestValidateAssetFileRoundTrip(_HouMockTestCase):

    def test_temp_file_validates(self):
        asset = _valid_inline_asset()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "tmp.asset.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(asset, f)
            result = self.validate_asset(asset_path=path, resolve=True)
        self.assertTrue(result["success"], result)
        self.assertIn("resolved_skeleton", result)


# ===================================================================
# build_asset handler (milestone 2)
# ===================================================================

class TestBuildAssetHandler(_HouMockTestCase):
    """The build_asset tool handler: validates, creates a sandbox, builds.
    Geometry correctness is covered by test_asset_hython (real Houdini) and
    test_asset_builder (network structure); here we verify the HANDLER wiring
    — argument handling, sandbox creation, and result shape."""

    def _inline_buildable_asset(self):
        return {
            "asset_schema_version": 1,
            "id": "h_test",
            "params": {"s": {"kind": "primary", "default": 1.0}},
            "skeleton": {"p": {"expr": ["0", "s", "0"]}},
            "components": [
                {"id": "c0", "backend": "native_chain",
                 "attach": {"position": "p"},
                 "nodes": [{"type": "box", "params": {"size": ["s", "s", "s"]}}]},
            ],
        }

    def test_no_asset_no_path_returns_error(self):
        result = self.build_asset()
        self.assertFalse(result["success"])
        self.assertIn("asset", result["error"].lower())

    def test_inline_asset_builds_with_sandbox_root(self):
        result = self.build_asset(asset=self._inline_buildable_asset())
        self.assertTrue(result["success"], result)
        self.assertIn("out_path", result)
        self.assertIn("sandbox_root", result)
        self.assertTrue(result["sandbox_root"].startswith("/obj/"))
        self.assertEqual(result["components_built"], 1)

    def test_invalid_asset_returns_validation_error(self):
        asset = self._inline_buildable_asset()
        asset["components"][0]["attach"] = {"position": "no_such_point"}
        result = self.build_asset(asset=asset)
        self.assertFalse(result["success"])
        # Validation failure surfaces before any sandbox is touched.
        self.assertIn("error", result)

    def test_sandbox_root_preserved_on_build_failure(self):
        # On a build error the sandbox is kept so the agent can diagnose it.
        asset = self._inline_buildable_asset()
        asset["components"][0]["backend"] = "magic"  # unknown backend
        result = self.build_asset(asset=asset)
        self.assertFalse(result["success"])
        self.assertIn("sandbox_root", result)


if __name__ == "__main__":
    unittest.main()
