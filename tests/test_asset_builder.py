"""Tests for edini.asset_builder — the geometry-construction layer (milestone 2).

asset_builder turns a validated asset JSON into a Houdini node network: it
resolves params + skeleton, then for each component builds the native_chain
geometry and transforms it onto its attach skeleton point, finally merging
everything into an OUT node.

These tests run under the mock hou (like test_node_utils) because asset_builder
imports hou. They verify the NETWORK STRUCTURE the builder produces (which
nodes exist, how they're wired, what params were attempted) rather than cooked
geometry — the real geometry is validated by test_asset_hython.py against a
genuine Houdini process.

Mock isolation: mirrors the test_tool_executor_asset contract (snapshot/restore
_hou_ref + sys.modules['hou'] in setUpClass/tearDownClass) so sibling test
modules see an unchanged MockNode._hou_ref.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python3.11libs"))
sys.path.insert(0, os.path.dirname(__file__))

from mock_hou import create_mock_hou, MockNode  # noqa: E402


def _inline_table_asset():
    """A minimal table for builder tests: 2 skeleton points + tabletop(box) +
    one leg(tube). Small enough to assert node structure clearly."""
    return {
        "asset_schema_version": 1,
        "id": "table_test",
        "params": {
            "top_size": {"kind": "primary", "default": 1.0},
            "top_thickness": {"kind": "primary", "default": 0.04},
            "leg_radius": {"kind": "primary", "default": 0.04},
            "leg_height": {"kind": "primary", "default": 0.75},
        },
        "skeleton": {
            "top_center": {"expr": ["0", "leg_height", "0"]},
            "leg_fl": {"expr": ["-0.45", "leg_height/2", "-0.45"]},
        },
        "components": [
            {
                "id": "tabletop",
                "backend": "native_chain",
                "attach": {"position": "top_center"},
                "nodes": [
                    {"type": "box", "params": {
                        "size": ["top_size", "top_thickness", "top_size"]}},
                ],
            },
            {
                "id": "leg_fl",
                "backend": "native_chain",
                "attach": {"position": "leg_fl"},
                "nodes": [
                    {"type": "tube", "params": {
                        "rad": ["leg_radius", "leg_radius"],
                        "height": "leg_height"}},
                ],
            },
        ],
    }


class _BuilderTestCase(unittest.TestCase):
    """Install a fresh mock hou, import asset_builder against it, restore on
    teardown (same isolation contract as test_tool_executor_asset)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._prev_hou = sys.modules.get("hou")
        cls._prev_hou_ref = MockNode._hou_ref
        cls._hou = create_mock_hou()
        sys.modules["hou"] = cls._hou
        for _mod in list(sys.modules):
            if _mod.startswith("edini"):
                del sys.modules[_mod]
        from edini import asset_builder  # noqa: E402
        cls.build_asset = staticmethod(asset_builder.build_asset)
        cls.asset_builder = asset_builder

    @classmethod
    def tearDownClass(cls):
        MockNode._hou_ref = cls._prev_hou_ref
        sys.modules["hou"] = cls._prev_hou
        for _mod in list(sys.modules):
            if _mod.startswith("edini"):
                del sys.modules[_mod]
        super().tearDownClass()

    def _make_sandbox(self, name="sandbox"):
        """Create a fresh geo container to build into (mirrors harness)."""
        obj = sys.modules["hou"].node("/obj")
        return obj.createNode("geo", name)

    @staticmethod
    def _child(root, name):
        """Look up a built node by name under the sandbox root.

        Uses the global hou.node() (absolute path) rather than root.node() so
        the lookup is robust to the sandbox root's own path."""
        return sys.modules["hou"].node(f"{root.path()}/{name}")


# ===================================================================
# build_asset — happy path
# ===================================================================

class TestBuildAssetHappy(_BuilderTestCase):

    def test_returns_success_and_out_path(self):
        root = self._make_sandbox()
        result = self.build_asset(_inline_table_asset(), root.path())
        self.assertTrue(result["success"], result)
        self.assertTrue(result["out_path"].startswith(root.path()))
        self.assertIn("OUT", result["out_path"])

    def test_creates_one_node_per_component_plus_merge_and_out(self):
        root = self._make_sandbox()
        result = self.build_asset(_inline_table_asset(), root.path())
        self.assertTrue(result["success"])
        children = {c.name(): c for c in root.children()}
        # Each component's first node appears (named {cid}_n0), plus the xform
        # + tag that wrap it, plus merge + OUT.
        self.assertIn("tabletop_n0", children)
        self.assertIn("leg_fl_n0", children)
        self.assertIn("tabletop_xform", children)
        self.assertIn("merge_all", children)
        self.assertIn("OUT", children)
        self.assertEqual(result["components_built"], 2)

    def test_out_is_downstream_of_merge(self):
        root = self._make_sandbox()
        self.build_asset(_inline_table_asset(), root.path())
        out = self._child(root, "OUT")
        merge = self._child(root, "merge_all")
        self.assertIsNotNone(out)
        self.assertIsNotNone(merge)
        # OUT's first input is the merge node.
        self.assertEqual(out.inputs()[0], merge)

    def test_merge_collects_all_components(self):
        root = self._make_sandbox()
        self.build_asset(_inline_table_asset(), root.path())
        merge = self._child(root, "merge_all")
        connected = [n for n in merge.inputs() if n is not None]
        self.assertEqual(len(connected), 2)

    def test_out_has_display_flag(self):
        root = self._make_sandbox()
        self.build_asset(_inline_table_asset(), root.path())
        out = self._child(root, "OUT")
        # The display flag is set so the gate target auto-finds OUT.
        self.assertTrue(out._display_flag)


# ===================================================================
# per-component native_chain construction
# ===================================================================

class TestNativeChainComponent(_BuilderTestCase):

    def test_box_component_creates_box_node(self):
        root = self._make_sandbox()
        self.build_asset(_inline_table_asset(), root.path())
        tabletop = self._child(root, "tabletop_n0")
        self.assertIsNotNone(tabletop)
        self.assertEqual(tabletop.type().name(), "box")

    def test_tube_component_forced_to_polygon_type(self):
        # W2: tube must default to type=1 (Polygon), not H21's primitive default.
        root = self._make_sandbox()
        self.build_asset(_inline_table_asset(), root.path())
        # The leg component's first node is the tube (named {cid}_n0).
        leg = self._child(root, "leg_fl_n0")
        self.assertIsNotNone(leg)
        self.assertEqual(leg.type().name(), "tube")
        type_parm = leg.parm("type")
        if type_parm is not None:
            self.assertEqual(type_parm.eval(), 1)

    def test_component_moved_to_attach_point(self):
        # Each component is wrapped in a transform that moves it to its attach
        # skeleton point. The tabletop attaches to top_center.
        root = self._make_sandbox()
        result = self.build_asset(_inline_table_asset(), root.path())
        self.assertTrue(result["success"])
        # The resolved top_center is (0, 0.75, 0). The builder records where each
        # component landed so we can assert the linkage.
        placements = result.get("placements", {})
        self.assertIn("tabletop", placements)
        self.assertAlmostEqual(placements["tabletop"][1], 0.75, places=4)


# ===================================================================
# param expression resolution (detail-1 = A: string param values are
# evaluated against the param library at build time)
# ===================================================================

class TestParamExprResolution(_BuilderTestCase):

    def test_string_param_value_evaluated(self):
        # box size = ["top_size","top_thickness","top_size"] → resolved against
        # params (top_size=1.0). The build must not crash on string params.
        root = self._make_sandbox()
        result = self.build_asset(_inline_table_asset(), root.path())
        self.assertTrue(result["success"], result)

    def test_numeric_param_value_passed_through(self):
        root = self._make_sandbox()
        asset = _inline_table_asset()
        asset["components"][1]["nodes"][0]["params"]["height"] = 0.75
        result = self.build_asset(asset, root.path())
        self.assertTrue(result["success"])


# ===================================================================
# error surfacing
# ===================================================================

class TestBuildAssetErrors(_BuilderTestCase):

    def test_invalid_asset_returns_error_not_crash(self):
        # An asset that fails validation should be rejected before any node
        # is created (shift-left: validate, then build).
        root = self._make_sandbox()
        asset = _inline_table_asset()
        asset["components"][0]["attach"] = {"position": "nonexistent_point"}
        result = self.build_asset(asset, root.path())
        self.assertFalse(result["success"])
        self.assertIn("error", result)

    def test_unknown_backend_raises_clean_error(self):
        root = self._make_sandbox()
        asset = _inline_table_asset()
        asset["components"][0]["backend"] = "magic"
        result = self.build_asset(asset, root.path())
        self.assertFalse(result["success"])

    def test_result_shape(self):
        root = self._make_sandbox()
        result = self.build_asset(_inline_table_asset(), root.path())
        for key in ("success", "out_path", "components_built"):
            self.assertIn(key, result)


if __name__ == "__main__":
    unittest.main()
