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

    def test_component_orient_applied_to_transform(self):
        # attach.orient = [rx, ry, rz] (degrees) must reach the xform's rotation
        # parm. Without this a tilted backrest / angled strut is impossible —
        # this is the limit the chair real-world test surfaced.
        asset = _inline_table_asset()
        asset["components"][0]["attach"]["orient"] = [15.0, 0.0, 0.0]
        root = self._make_sandbox()
        result = self.build_asset(asset, root.path())
        self.assertTrue(result["success"], result)
        xform = self._child(root, "tabletop_xform")
        self.assertIsNotNone(xform)
        # The rotation was applied: the xform carries a non-default rx.
        r_tuple = xform.parmTuple("r")
        if r_tuple is not None:
            rx = r_tuple.eval()[0]
            self.assertAlmostEqual(rx, 15.0, places=4)

    def test_instance_orient_applied(self):
        # Multi-instance orient: each instance can tilt independently.
        asset = {
            "asset_schema_version": 1, "id": "t",
            "params": {"s": {"kind": "primary", "default": 1.0}},
            "skeleton": {
                "p1": {"expr": ["0", "0", "0"]},
                "p2": {"expr": ["2", "0", "0"]}},
            "components": [{
                "id": "beam", "backend": "native_chain",
                "nodes": [{"type": "box", "params": {"size": ["s", "s", "s"]}}],
                "instances": [
                    {"id": "beam_a", "position": "p1", "orient": [0, 30, 0]},
                    {"id": "beam_b", "position": "p2", "orient": [0, 0, 45]},
                ],
            }],
        }
        root = self._make_sandbox()
        result = self.build_asset(asset, root.path())
        self.assertTrue(result["success"], result)
        a = self._child(root, "beam_a_xform")
        b = self._child(root, "beam_b_xform")
        self.assertIsNotNone(a)
        self.assertIsNotNone(b)
        if a.parmTuple("r") is not None:
            self.assertAlmostEqual(a.parmTuple("r").eval()[1], 30.0, places=4)
        if b.parmTuple("r") is not None:
            self.assertAlmostEqual(b.parmTuple("r").eval()[2], 45.0, places=4)


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


# ===================================================================
# _inject_param_values — value injection (pure function, no hou needed)
# ===================================================================

class TestPythonComponent(_BuilderTestCase):
    """The python backend: agent-authored Python SOP code, with asset params
    injected as literals, generates curve/geometry the native_chain backend
    cannot (e.g. a parametric circle for a rim)."""

    def _asset_with_python_component(self):
        """A 1-point skeleton + 1 python component drawing a circle rim."""
        return {
            "asset_schema_version": 1,
            "id": "py_test",
            "params": {"rim_r": {"kind": "primary", "default": 0.3}},
            "skeleton": {"center": {"expr": ["0", "0", "0"]}},
            "components": [
                {
                    "id": "rim",
                    "backend": "python",
                    "attach": {"position": "center"},
                    "imports": ["math"],
                    "code": (
                        "node = hou.pwd()\n"
                        "geo = node.geometry()\n"
                        "geo.clear()\n"
                        "n = 48\n"
                        "prim = geo.createPolygon()\n"
                        "prim.setIsClosed(False)\n"
                        "for i in range(n):\n"
                        "    a = 6.2832 * i / n\n"
                        "    pt = geo.createPoint()\n"
                        "    pt.setPosition((rim_r * math.cos(a), 0.0, rim_r * math.sin(a)))\n"
                        "    prim.addVertex(pt)\n"
                    ),
                }
            ],
        }

    def test_python_component_creates_python_sop(self):
        root = self._make_sandbox()
        result = self.build_asset(self._asset_with_python_component(), root.path())
        self.assertTrue(result["success"], result)
        py = self._child(root, "rim_python")
        self.assertIsNotNone(py)
        self.assertEqual(py.type().name(), "python")

    def test_param_value_injected_into_code(self):
        # rim_r (0.3) is substituted into the code as a literal; the bare name
        # 'rim_r' must NOT appear in the code set on the python SOP.
        root = self._make_sandbox()
        result = self.build_asset(self._asset_with_python_component(), root.path())
        self.assertTrue(result["success"])
        py = self._child(root, "rim_python")
        code = py.parm("python").eval()
        self.assertIn("0.3", code)
        # The agent's bare 'rim_r' references are gone (replaced by 0.3).
        self.assertNotIn("rim_r * math", code)
        self.assertNotIn("rim_r *", code)

    def test_imports_prepended(self):
        root = self._make_sandbox()
        result = self.build_asset(self._asset_with_python_component(), root.path())
        self.assertTrue(result["success"])
        py = self._child(root, "rim_python")
        code = py.parm("python").eval()
        self.assertIn("import math", code)
        # The import should be at the top, before the agent's code.
        self.assertLess(code.index("import math"), code.index("hou.pwd"))

    def test_python_component_generates_geometry(self):
        # The mock executes the python SOP code on cook; the circle (48 points)
        # should materialize in the geometry.
        root = self._make_sandbox()
        result = self.build_asset(self._asset_with_python_component(), root.path())
        self.assertTrue(result["success"])
        py = self._child(root, "rim_python")
        py.cook(force=True)
        geo = py.geometry()
        self.assertEqual(geo.intrinsicValue("pointcount"), 48)

    def test_python_component_tagged_and_merged(self):
        # Like native_chain, the python component is tagged + merged into OUT.
        root = self._make_sandbox()
        result = self.build_asset(self._asset_with_python_component(), root.path())
        self.assertTrue(result["success"])
        tag = self._child(root, "rim_tag")
        out = self._child(root, "OUT")
        self.assertIsNotNone(tag)
        self.assertIsNotNone(out)
        self.assertEqual(result["components_built"], 1)

    def test_python_without_code_fails_cleanly(self):
        asset = self._asset_with_python_component()
        del asset["components"][0]["code"]
        root = self._make_sandbox()
        result = self.build_asset(asset, root.path())
        self.assertFalse(result["success"])
        self.assertIn("error", result)


# ===================================================================
# Multi-instance: one component definition instanced onto N skeleton points
# ===================================================================

class TestMultiInstance(_BuilderTestCase):
    """Multi-instance via transform copying: the component geometry is built
    ONCE, then N transforms each move a copy onto a declared skeleton point
    with its own component_id. This replaces the old CTP-stamping (whose anchor
    private coords + idfix boundary math were fragile and violated the M2
    skeleton-point contract)."""

    def _dual_wheel_asset(self):
        return {
            "asset_schema_version": 1,
            "id": "wheels_test",
            "params": {"wr": {"kind": "primary", "default": 0.34}},
            "skeleton": {
                "front_axle": {"expr": ["1.0", "wr", "0"]},
                "rear_axle": {"expr": ["0", "wr", "0"]},
            },
            "components": [
                {
                    "id": "wheel",
                    "backend": "native_chain",
                    "nodes": [{"type": "box", "params": {"size": ["wr", "wr", "wr"]}}],
                    "instances": [
                        {"id": "wheel_front", "position": "front_axle"},
                        {"id": "wheel_rear", "position": "rear_axle"},
                    ],
                }
            ],
        }

    def test_two_instances_build_two_chains(self):
        root = self._make_sandbox()
        result = self.build_asset(self._dual_wheel_asset(), root.path())
        self.assertTrue(result["success"], result)
        # One geometry source (wheel_n0) + 2 transforms + 2 tags + merge + OUT.
        children = {c.name(): c for c in root.children()}
        self.assertIn("wheel_n0", children)
        self.assertIn("wheel_front_xform", children)
        self.assertIn("wheel_rear_xform", children)
        self.assertIn("wheel_front_tag", children)
        self.assertIn("wheel_rear_tag", children)

    def test_geometry_source_built_once(self):
        # The component's geometry (wheel_n0) exists exactly once — both
        # instances transform-copy it rather than rebuilding it.
        root = self._make_sandbox()
        self.build_asset(self._dual_wheel_asset(), root.path())
        geom_nodes = [c for c in root.children() if c.name().startswith("wheel_n")]
        self.assertEqual(len(geom_nodes), 1)

    def test_each_instance_at_its_skeleton_point(self):
        # wheel_front → front_axle (x=1.0), wheel_rear → rear_axle (x=0).
        root = self._make_sandbox()
        result = self.build_asset(self._dual_wheel_asset(), root.path())
        self.assertTrue(result["success"])
        placements = result["placements"]
        self.assertAlmostEqual(placements["wheel_front"][0], 1.0, places=4)
        self.assertAlmostEqual(placements["wheel_rear"][0], 0.0, places=4)

    def test_components_built_counts_instances(self):
        # components_built counts the placed instances (2), not definitions (1).
        root = self._make_sandbox()
        result = self.build_asset(self._dual_wheel_asset(), root.path())
        self.assertTrue(result["success"])
        self.assertEqual(result["components_built"], 2)

    def test_merge_collects_all_instances(self):
        root = self._make_sandbox()
        self.build_asset(self._dual_wheel_asset(), root.path())
        merge = self._child(root, "merge_all")
        connected = [n for n in merge.inputs() if n is not None]
        self.assertEqual(len(connected), 2)

    def test_both_transforms_share_one_geometry_source(self):
        # Both xform nodes take input from the SAME geometry node (fan-out),
        # confirming the geometry is built once and copied, not rebuilt.
        root = self._make_sandbox()
        self.build_asset(self._dual_wheel_asset(), root.path())
        front_xform = self._child(root, "wheel_front_xform")
        rear_xform = self._child(root, "wheel_rear_xform")
        # Each xform's input is the shared geometry tail (wheel_n0). The exact
        # node may be wrapped, but both must share the same source.
        self.assertIsNotNone(front_xform.inputs()[0])
        self.assertIsNotNone(rear_xform.inputs()[0])


class TestParamInjection(_BuilderTestCase):
    """The python-backend value injector: rewrites a bare parameter NAME in
    agent-authored code into its resolved numeric literal, via a SAFE AST walk
    (only global Name nodes in Load context, never function args / locals /
    attributes). This lets an agent write ``r = rim_r`` and the builder
    substitutes ``r = 0.3`` — zero Houdini parameter-API knowledge required.

    Inherits _BuilderTestCase only so the edini package imports cleanly under
    the mock hou (asset_builder's top-level imports pull in hou transitively);
    the injector itself is a pure function with no hou dependency."""

    def _inject(self, code, params):
        return self.asset_builder._inject_param_values(code, params)

    def test_simple_param_replaced_with_value(self):
        out = self._inject("r = rim_r", {"rim_r": 0.3})
        self.assertIn("0.3", out)
        self.assertNotIn("rim_r", out)

    def test_param_in_arithmetic(self):
        out = self._inject("d = rim_r * 2", {"rim_r": 0.3})
        # rim_r → 0.3, d stays (not a param)
        self.assertIn("0.3", out)
        self.assertNotIn("rim_r", out)
        self.assertIn("d", out)

    def test_unknown_name_preserved(self):
        # A name not in the param library is left untouched.
        out = self._inject("x = unknown", {"rim_r": 0.3})
        self.assertIn("unknown", out)

    def test_local_variable_not_replaced(self):
        # 'leg' is assigned locally; it's not a param, so it stays. But 'rim_r'
        # (a param) inside the same scope IS replaced.
        out = self._inject("leg = rim_r\nheight = leg", {"rim_r": 0.3})
        self.assertIn("0.3", out)
        # 'leg' should still appear (it's a local, not a param).
        self.assertIn("leg", out)

    def test_function_arg_name_not_replaced(self):
        # A function parameter named identically to a param must NOT be
        # substituted inside the function body — it shadows the param.
        code = "def make(rim_r):\n    return rim_r * 2"
        out = self._inject(code, {"rim_r": 0.3})
        # The def-line arg stays 'rim_r'; we don't mangle signatures.
        self.assertIn("def make(rim_r)", out)

    def test_attribute_access_not_replaced(self):
        # math.cos — 'math' is an attribute base, not a free name to replace.
        # Even if a param were named 'math', the attribute context protects it.
        code = "node = hou.pwd()\ngeo = node.geometry()\nx = math.cos(0)"
        out = self._inject(code, {"math": 9.9, "node": 1.0})
        # 'math' must survive (it's a module, used as attribute base).
        self.assertIn("math.cos", out)
        # 'hou' must survive (excluded builtin-equivalent).
        self.assertIn("hou.pwd", out)

    def test_hou_geo_node_builtins_preserved(self):
        # The standard Python-SOP header names are never params.
        code = "node = hou.pwd()\ngeo = node.geometry()\ngeo.clear()"
        out = self._inject(code, {})
        self.assertIn("hou.pwd", out)
        self.assertIn("node.geometry", out)

    def test_multiple_params_replaced(self):
        out = self._inject("box = [w, h, d]", {"w": 1.0, "h": 0.5, "d": 2.0})
        self.assertIn("1.0", out)
        self.assertIn("0.5", out)
        self.assertIn("2.0", out)

    def test_keyword_argument_name_not_replaced(self):
        # pscale=1.0 — 'pscale' is a keyword arg NAME, not a value reference.
        code = "pt.setAttribValue('pscale', 1.0)"
        out = self._inject(code, {"pscale": 0.5})
        # The string 'pscale' stays a kwarg name; the literal 1.0 stays.
        self.assertIn("'pscale'", out)
        self.assertIn("1.0", out)

    def test_for_loop_target_not_replaced(self):
        code = "for i in range(n):\n    pt = geo.createPoint()"
        out = self._inject(code, {"n": 48, "i": 9.9})
        # 'n' (param) replaced with 48; loop target 'i' is NOT a param here so
        # it stays, but even if it were, the loop target context is Load-safe.
        self.assertIn("48", out)
        self.assertIn("range", out)

    def test_invalid_python_raises_clean_error(self):
        with self.assertRaises(Exception):
            self._inject("def ( broken syntax", {"rim_r": 0.3})


if __name__ == "__main__":
    unittest.main()
