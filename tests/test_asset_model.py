"""Tests for edini.asset_model — the declarative asset description layer.

Characterization tests for an already-implemented module (milestone-1
foundation). Covers validate_asset (every error code), resolve_params
(primary + derived DAG), resolve_skeleton, and load/save round-tripping. Also
exercises the bundled bicycle.asset.json end-to-end.

Pure Python — no ``hou`` dependency.
"""
import math
import os
import sys
import tempfile
import unittest

sys.path.insert(0, "python3.11libs")

from edini.exprs import ExprError
from edini.skeleton_resolver import SkeletonCycleError
from edini import asset_model


HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "..", "python3.11libs", "edini", "data")
BICYCLE_PATH = os.path.join(DATA_DIR, "bicycle.asset.json")


def _minimal_asset(**overrides):
    """A minimal but fully-valid asset for happy-path tests."""
    asset = {
        "asset_schema_version": 1,
        "id": "test_asset",
        "params": {
            "a": {"kind": "primary", "default": 1.0},
            "b": {"kind": "primary", "default": 2.0},
        },
        "skeleton": {
            "p1": {"expr": ["a", "b", "0"]},
        },
        "components": [],
    }
    asset.update(overrides)
    return asset


# ===================================================================
# validate_asset — happy path
# ===================================================================

class TestValidateAssetHappy(unittest.TestCase):
    def test_minimal_asset_validates(self):
        result = validate(_minimal_asset())
        self.assertTrue(result["success"], result)
        self.assertEqual(result["errors"], [])

    def test_summary_counts(self):
        result = validate(_minimal_asset())
        self.assertEqual(result["summary"]["param_count"], 2)
        self.assertEqual(result["summary"]["skeleton_point_count"], 1)
        self.assertEqual(result["summary"]["component_count"], 0)

    def test_missing_components_is_warning_not_error(self):
        asset = _minimal_asset()
        del asset["components"]
        result = validate(asset)
        self.assertTrue(result["success"])
        codes = [w["code"] for w in result["warnings"]]
        self.assertIn("NO_COMPONENTS", codes)

    def test_missing_skeleton_is_valid(self):
        asset = _minimal_asset()
        del asset["skeleton"]
        result = validate(asset)
        self.assertTrue(result["success"])
        self.assertEqual(result["summary"]["skeleton_point_count"], 0)


# ===================================================================
# validate_asset — top-level schema errors
# ===================================================================

class TestValidateAssetSchema(unittest.TestCase):
    def test_non_object_asset(self):
        result = validate("not a dict")  # type: ignore[arg-type]
        self.assertFalse(result["success"])
        self.assertTrue(any(e["code"] == "ASSET_NOT_OBJECT" for e in result["errors"]))

    def test_wrong_schema_version(self):
        asset = _minimal_asset(asset_schema_version=2)
        result = validate(asset)
        self.assertFalse(result["success"])
        self.assertTrue(any(e["code"] == "ASSET_SCHEMA_VERSION" for e in result["errors"]))

    def test_missing_id(self):
        asset = _minimal_asset()
        del asset["id"]
        result = validate(asset)
        self.assertFalse(result["success"])
        self.assertTrue(any(e["code"] == "ASSET_NO_ID" for e in result["errors"]))


# ===================================================================
# validate_asset — params library errors
# ===================================================================

class TestValidateParams(unittest.TestCase):
    def test_params_not_object(self):
        asset = _minimal_asset(params="nope")
        result = validate(asset)
        self.assertFalse(result["success"])
        self.assertTrue(any(e["code"] == "PARAMS_NOT_OBJECT" for e in result["errors"]))

    def test_param_spec_not_object(self):
        asset = _minimal_asset()
        asset["params"]["bad"] = "not a dict"
        result = validate(asset)
        self.assertTrue(any(e["code"] == "PARAM_SPEC_NOT_OBJECT" for e in result["errors"]))

    def test_param_bad_kind(self):
        asset = _minimal_asset()
        asset["params"]["a"]["kind"] = "magic"
        result = validate(asset)
        self.assertTrue(any(e["code"] == "PARAM_BAD_KIND" for e in result["errors"]))

    def test_primary_param_needs_default(self):
        asset = _minimal_asset()
        del asset["params"]["a"]["default"]
        result = validate(asset)
        self.assertTrue(any(e["code"] == "PARAM_NO_DEFAULT" for e in result["errors"]))

    def test_param_default_non_numeric(self):
        asset = _minimal_asset()
        asset["params"]["a"]["default"] = "big"
        result = validate(asset)
        self.assertTrue(any(e["code"] == "PARAM_DEFAULT_NON_NUMERIC" for e in result["errors"]))

    def test_derived_param_needs_from(self):
        asset = _minimal_asset()
        asset["params"]["c"] = {"kind": "derived"}  # no 'from'
        result = validate(asset)
        self.assertTrue(any(e["code"] == "PARAM_DERIVED_NO_FROM" for e in result["errors"]))

    def test_derived_param_without_default_is_ok(self):
        # Derived params must NOT have a default — they compute from 'from'.
        asset = _minimal_asset()
        asset["params"]["c"] = {"kind": "derived", "from": "a + b"}
        result = validate(asset)
        self.assertTrue(result["success"], result)


# ===================================================================
# validate_asset — skeleton errors
# ===================================================================

class TestValidateSkeleton(unittest.TestCase):
    def test_skeleton_not_object(self):
        asset = _minimal_asset(skeleton="nope")
        result = validate(asset)
        self.assertFalse(result["success"])
        self.assertTrue(any(e["code"] == "SKELETON_NOT_OBJECT" for e in result["errors"]))

    def test_point_bad_expr_length(self):
        asset = _minimal_asset()
        asset["skeleton"]["p1"] = {"expr": ["a", "b"]}  # only 2 axes
        result = validate(asset)
        self.assertTrue(any(e["code"] == "SKELETON_POINT_BAD_EXPR" for e in result["errors"]))

    def test_cycle_detected(self):
        asset = _minimal_asset()
        asset["skeleton"] = {
            "a": {"expr": ["b[0]", "0", "0"]},
            "b": {"expr": ["a[0]", "0", "0"]},
        }
        result = validate(asset)
        self.assertFalse(result["success"])
        self.assertTrue(any(e["code"] == "SKELETON_CYCLE" for e in result["errors"]))

    def test_dangling_reference(self):
        asset = _minimal_asset()
        # 'ghost' is neither a point nor a declared param.
        asset["skeleton"]["p1"] = {"expr": ["ghost", "0", "0"]}
        result = validate(asset)
        self.assertFalse(result["success"])
        self.assertTrue(any(e["code"] == "SKELETON_DANGLING_REF" for e in result["errors"]))

    def test_expression_syntax_error(self):
        asset = _minimal_asset()
        asset["skeleton"]["p1"] = {"expr": ["a +", "0", "0"]}
        result = validate(asset)
        self.assertTrue(any(e["code"] == "SKELETON_EXPR_SYNTAX" for e in result["errors"]))

    def test_expression_eval_error_on_pure_param_expr(self):
        # A pure-param expression (no point refs) is pre-evaluated. Division by
        # zero surfaces as a SKELETON_EXPR_EVAL error.
        asset = _minimal_asset()
        asset["skeleton"]["p1"] = {"expr": ["1/a - 1/a", "0", "0"]}
        # a defaults to 1.0 so 1/a - 1/a = 0, no error. Force a div-by-zero:
        asset["params"]["zero"] = {"kind": "primary", "default": 0.0}
        asset["skeleton"]["p1"] = {"expr": ["1/zero", "0", "0"]}
        result = validate(asset)
        self.assertTrue(any(e["code"] == "SKELETON_EXPR_EVAL" for e in result["errors"]))

    def test_point_reference_is_not_dangling(self):
        # Referencing another declared point is valid (not a dangling ref).
        asset = _minimal_asset()
        asset["skeleton"] = {
            "base": {"expr": ["0", "0", "0"]},
            "top": {"expr": ["base[0]", "0", "0"]},
        }
        result = validate(asset)
        self.assertTrue(result["success"], result)


# ===================================================================
# validate_asset — components (milestone 2)
# ===================================================================

class TestValidateComponents(unittest.TestCase):
    """Component validation: the milestone-2 layer. Components attach to
    skeleton points BY NAME (not private position expressions) and read their
    dimensions from the param library. These tests lock in the new contract."""

    def _table_asset(self):
        """A minimal but valid table: 1 skeleton point + 1 box tabletop +
        1 tube leg, all attaching to skeleton points by name."""
        return {
            "asset_schema_version": 1,
            "id": "table",
            "params": {
                "top_size": {"kind": "primary", "default": 1.0},
                "top_thickness": {"kind": "primary", "default": 0.04},
                "leg_radius": {"kind": "primary", "default": 0.04},
            },
            "skeleton": {
                "top_center": {"expr": ["0", "0.75", "0"]},
                "leg_fl": {"expr": ["-0.5", "0.375", "-0.5"]},
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
                            "height": "0.75"}},
                    ],
                },
            ],
        }

    def test_valid_table_passes(self):
        result = validate(self._table_asset())
        self.assertTrue(result["success"], result["errors"])

    def test_summary_counts_components(self):
        result = validate(self._table_asset())
        self.assertEqual(result["summary"]["component_count"], 2)

    # ── id checks ──

    def test_component_missing_id(self):
        asset = self._table_asset()
        del asset["components"][0]["id"]
        result = validate(asset)
        self.assertFalse(result["success"])
        self.assertTrue(any(e["code"] == "COMPONENT_NO_ID" for e in result["errors"]))

    def test_component_duplicate_id(self):
        asset = self._table_asset()
        asset["components"][1]["id"] = "tabletop"  # clash
        result = validate(asset)
        self.assertFalse(result["success"])
        self.assertTrue(any(e["code"] == "COMPONENT_DUPLICATE_ID" for e in result["errors"]))

    # ── backend checks ──

    def test_component_bad_backend(self):
        asset = self._table_asset()
        asset["components"][0]["backend"] = "magic"
        result = validate(asset)
        self.assertFalse(result["success"])
        self.assertTrue(any(e["code"] == "COMPONENT_BAD_BACKEND" for e in result["errors"]))

    def test_component_default_backend_is_native_chain(self):
        # Omitting backend defaults to native_chain (the safe/simplest backend).
        asset = self._table_asset()
        del asset["components"][0]["backend"]
        result = validate(asset)
        self.assertTrue(result["success"], result["errors"])

    # ── nodes checks ──

    def test_native_chain_needs_nodes(self):
        asset = self._table_asset()
        del asset["components"][0]["nodes"]
        result = validate(asset)
        self.assertFalse(result["success"])
        self.assertTrue(any(e["code"] == "COMPONENT_NO_NODES" for e in result["errors"]))

    def test_node_entry_needs_type(self):
        asset = self._table_asset()
        asset["components"][0]["nodes"][0] = {"params": {"size": 1}}  # no type
        result = validate(asset)
        self.assertFalse(result["success"])
        self.assertTrue(any(e["code"] == "COMPONENT_NODE_NO_TYPE" for e in result["errors"]))

    # ── python backend code checks ──

    def test_python_backend_needs_code(self):
        asset = self._table_asset()
        asset["components"][0] = {
            "id": "py_comp", "backend": "python",
            "attach": {"position": "top_center"},
            # no code
        }
        result = validate(asset)
        self.assertFalse(result["success"])
        self.assertTrue(any(e["code"] == "COMPONENT_NO_CODE" for e in result["errors"]))

    def test_python_backend_code_syntax_checked(self):
        # A syntax error in the cook body is caught at validate time, not as an
        # opaque cook error later.
        asset = self._table_asset()
        asset["components"][0] = {
            "id": "py_comp", "backend": "python",
            "attach": {"position": "top_center"},
            "code": "def ( broken",
        }
        result = validate(asset)
        self.assertFalse(result["success"])
        self.assertTrue(any(e["code"] == "COMPONENT_CODE_SYNTAX" for e in result["errors"]))

    def test_python_backend_valid_code_passes(self):
        asset = self._table_asset()
        asset["components"][0] = {
            "id": "py_comp", "backend": "python",
            "attach": {"position": "top_center"},
            "code": "node = hou.pwd()\ngeo = node.geometry()",
        }
        result = validate(asset)
        self.assertTrue(result["success"], result["errors"])

    # ── attach checks (the NEW core constraint) ──

    def test_attach_position_must_be_known_point(self):
        # attach.position references a skeleton point that doesn't exist.
        asset = self._table_asset()
        asset["components"][0]["attach"] = {"position": "nonexistent_point"}
        result = validate(asset)
        self.assertFalse(result["success"])
        self.assertTrue(any(e["code"] == "COMPONENT_ATTACH_BAD_POINT" for e in result["errors"]))

    def test_attach_missing(self):
        # A component with no attach at all is flagged (it must hang off a point).
        asset = self._table_asset()
        del asset["components"][0]["attach"]
        result = validate(asset)
        self.assertFalse(result["success"])
        self.assertTrue(any(e["code"] == "COMPONENT_NO_ATTACH" for e in result["errors"]))

    def test_attach_position_valid_point_passes(self):
        result = validate(self._table_asset())
        self.assertTrue(result["success"], result["errors"])

    # ── multi-instance checks ──

    def _dual_wheel_asset(self):
        """A valid asset with ONE wheel component instanced onto 2 skeleton
        points (front + rear axle). Used for multi-instance validation tests."""
        return {
            "asset_schema_version": 1,
            "id": "bike_wheels",
            "params": {"wr": {"kind": "primary", "default": 0.34}},
            "skeleton": {
                "front_axle": {"expr": ["1.0", "wr", "0"]},
                "rear_axle": {"expr": ["0", "wr", "0"]},
            },
            "components": [
                {
                    "id": "wheel",
                    "backend": "native_chain",
                    "nodes": [{"type": "torus", "params": {"r": "wr"}}],
                    "instances": [
                        {"id": "wheel_front", "position": "front_axle"},
                        {"id": "wheel_rear", "position": "rear_axle"},
                    ],
                }
            ],
        }

    def test_valid_multi_instance_passes(self):
        result = validate(self._dual_wheel_asset())
        self.assertTrue(result["success"], result["errors"])

    def test_instances_and_attach_conflict(self):
        # A component with BOTH instances and attach is ambiguous — reject it.
        asset = self._dual_wheel_asset()
        asset["components"][0]["attach"] = {"position": "front_axle"}
        result = validate(asset)
        self.assertFalse(result["success"])
        self.assertTrue(any(
            e["code"] == "COMPONENT_INSTANCES_AND_ATTACH_CONFLICT"
            for e in result["errors"]))

    def test_instance_needs_id(self):
        asset = self._dual_wheel_asset()
        del asset["components"][0]["instances"][0]["id"]
        result = validate(asset)
        self.assertFalse(result["success"])
        self.assertTrue(any(
            e["code"] == "COMPONENT_INSTANCE_NO_ID" for e in result["errors"]))

    def test_instance_duplicate_id(self):
        # Two instances with the same id are ambiguous for the gates.
        asset = self._dual_wheel_asset()
        asset["components"][0]["instances"][1]["id"] = "wheel_front"
        result = validate(asset)
        self.assertFalse(result["success"])
        self.assertTrue(any(
            e["code"] == "COMPONENT_INSTANCE_DUPLICATE_ID"
            for e in result["errors"]))

    def test_instance_bad_point(self):
        # instance.position must reference a declared skeleton point.
        asset = self._dual_wheel_asset()
        asset["components"][0]["instances"][0]["position"] = "no_such_point"
        result = validate(asset)
        self.assertFalse(result["success"])
        self.assertTrue(any(
            e["code"] == "COMPONENT_INSTANCE_BAD_POINT" for e in result["errors"]))

    def test_instance_no_attach_required(self):
        # A component with instances does NOT need a top-level attach (the
        # instances carry their own positions). This must NOT trigger
        # COMPONENT_NO_ATTACH.
        asset = self._dual_wheel_asset()
        result = validate(asset)
        self.assertTrue(result["success"], result["errors"])
        self.assertFalse(any(
            e["code"] == "COMPONENT_NO_ATTACH" for e in result["errors"]))

    def test_single_instance_still_valid(self):
        # Backward compat: a single-instance component (attach, no instances)
        # is unaffected.
        result = validate(self._table_asset())
        self.assertTrue(result["success"], result["errors"])

    # ── orient (rotation) checks — surfaced by the chair real-world test ──

    def test_valid_orient_passes(self):
        asset = self._table_asset()
        asset["components"][0]["attach"]["orient"] = [10, 0, 0]
        result = validate(asset)
        self.assertTrue(result["success"], result["errors"])

    def test_instance_valid_orient_passes(self):
        asset = self._dual_wheel_asset()
        asset["components"][0]["instances"][0]["orient"] = [0, 90, 0]
        result = validate(asset)
        self.assertTrue(result["success"], result["errors"])

    def test_bad_orient_wrong_length(self):
        asset = self._table_asset()
        asset["components"][0]["attach"]["orient"] = [10, 0]  # only 2
        result = validate(asset)
        self.assertFalse(result["success"])
        self.assertTrue(any(
            e["code"] == "COMPONENT_BAD_ORIENT" for e in result["errors"]))

    def test_bad_orient_non_numeric(self):
        asset = self._table_asset()
        asset["components"][0]["attach"]["orient"] = [10, "flat", 0]
        result = validate(asset)
        self.assertFalse(result["success"])
        self.assertTrue(any(
            e["code"] == "COMPONENT_BAD_ORIENT" for e in result["errors"]))

    def test_bad_orient_wrong_type(self):
        asset = self._table_asset()
        asset["components"][0]["attach"]["orient"] = 10  # not a list
        result = validate(asset)
        self.assertFalse(result["success"])
        self.assertTrue(any(
            e["code"] == "COMPONENT_BAD_ORIENT" for e in result["errors"]))

    def test_orient_optional(self):
        # No orient at all is fine (the default, most components don't rotate).
        result = validate(self._table_asset())
        self.assertTrue(result["success"], result["errors"])
        self.assertFalse(any(
            e["code"] == "COMPONENT_BAD_ORIENT" for e in result["errors"]))

    # ── param-ref checks (the hole the old design never closed) ──

    def test_node_param_expr_dangling_ref(self):
        # A string param value references a param that isn't declared.
        asset = self._table_asset()
        asset["components"][0]["nodes"][0]["params"]["size"] = [
            "undeclared_param", "0.04", "1.0"]
        result = validate(asset)
        self.assertFalse(result["success"])
        self.assertTrue(any(
            e["code"] == "COMPONENT_PARAM_REF_DANGLING" for e in result["errors"]))

    def test_node_param_expr_valid_ref_passes(self):
        # String param values that reference declared params are fine.
        result = validate(self._table_asset())
        self.assertTrue(result["success"], result["errors"])

    def test_node_param_numeric_value_passes(self):
        # A plain numeric param value (no expression) is fine.
        asset = self._table_asset()
        asset["components"][1]["nodes"][0]["params"]["height"] = 0.75
        result = validate(asset)
        self.assertTrue(result["success"], result["errors"])

    # ── graph validation still runs with components present ──

    def test_skeleton_cycle_still_caught_with_components(self):
        asset = self._table_asset()
        asset["skeleton"] = {
            "a": {"expr": ["b[0]", "0", "0"]},
            "b": {"expr": ["a[0]", "0", "0"]},
        }
        # components now attach to non-existent points -> also flagged, but the
        # cycle must still appear.
        result = validate(asset)
        self.assertTrue(any(e["code"] == "SKELETON_CYCLE" for e in result["errors"]))


class TestTableAsset(unittest.TestCase):
    """The bundled table.asset.json is the milestone-2 sample. Locks in that it
    validates cleanly and every component attaches to a real skeleton point."""

    @classmethod
    def setUpClass(cls):
        cls.asset = asset_model.load_asset(
            os.path.join(DATA_DIR, "table.asset.json"))
        if cls.asset is None:
            raise AssertionError("table.asset.json failed to load")

    def test_validates_cleanly(self):
        result = validate(self.asset)
        self.assertTrue(result["success"], result["errors"])

    def test_has_seven_params(self):
        # 4 primary + 3 derived (leg_half, leg_inset, rim_radius).
        result = validate(self.asset)
        self.assertEqual(result["summary"]["param_count"], 7)

    def test_has_five_skeleton_points(self):
        result = validate(self.asset)
        self.assertEqual(result["summary"]["skeleton_point_count"], 5)

    def test_has_three_component_definitions(self):
        # 3 component DEFINITIONS: tabletop + table_leg (4 instances) +
        # tabletop_rim. (component_count counts definitions, not instances —
        # instances_built is reported by build_asset, not validate.)
        result = validate(self.asset)
        self.assertEqual(result["summary"]["component_count"], 3)

    def test_param_linkage_top_size_moves_legs(self):
        """Derived param leg_inset = top_size/2 - leg_radius. Increasing
        top_size spreads the legs outward — the skeleton DAG propagates it."""
        import math
        before = asset_model.resolve_skeleton(self.asset)
        self.asset["params"]["top_size"]["default"] = 1.5
        try:
            after = asset_model.resolve_skeleton(self.asset)
        finally:
            self.asset["params"]["top_size"]["default"] = 1.0
        # leg_fl.x = -leg_inset; larger top_size → larger |leg_inset| → more
        # negative leg_fl.x (leg moves outward).
        self.assertLess(after["leg_fl"][0], before["leg_fl"][0])


# ===================================================================
# resolve_params — primary + derived DAG
# ===================================================================

class TestResolveParams(unittest.TestCase):
    def test_primary_uses_default(self):
        asset = _minimal_asset()
        values = asset_model.resolve_params(asset)
        self.assertEqual(values["a"], 1.0)
        self.assertEqual(values["b"], 2.0)

    def test_derived_resolves_from_primary(self):
        asset = _minimal_asset()
        asset["params"]["c"] = {"kind": "derived", "from": "a + b"}
        values = asset_model.resolve_params(asset)
        self.assertAlmostEqual(values["c"], 3.0)

    def test_derived_chain(self):
        asset = _minimal_asset()
        asset["params"]["c"] = {"kind": "derived", "from": "a * 2"}
        asset["params"]["d"] = {"kind": "derived", "from": "c + b"}
        values = asset_model.resolve_params(asset)
        self.assertAlmostEqual(values["c"], 2.0)
        self.assertAlmostEqual(values["d"], 4.0)

    def test_derived_cycle_raises(self):
        asset = _minimal_asset()
        asset["params"]["c"] = {"kind": "derived", "from": "d"}
        asset["params"]["d"] = {"kind": "derived", "from": "c"}
        with self.assertRaises(SkeletonCycleError):
            asset_model.resolve_params(asset)

    def test_derived_dangling_ref_raises(self):
        asset = _minimal_asset()
        asset["params"]["c"] = {"kind": "derived", "from": "nonexistent"}
        with self.assertRaises(ExprError):
            asset_model.resolve_params(asset)


# ===================================================================
# resolve_skeleton — full resolution with param linkage
# ===================================================================

class TestResolveSkeleton(unittest.TestCase):
    def test_resolves_all_points(self):
        asset = _minimal_asset()
        asset["skeleton"] = {
            "base": {"expr": ["0", "0", "0"]},
            "top": {"expr": ["0", "a", "0"]},
        }
        result = asset_model.resolve_skeleton(asset)
        self.assertEqual(result["base"], (0.0, 0.0, 0.0))
        self.assertEqual(result["top"], (0.0, 1.0, 0.0))

    def test_param_linkage_propagates(self):
        # Changing a param value moves dependent points.
        asset = _minimal_asset()
        asset["skeleton"] = {
            "base": {"expr": ["0", "0", "0"]},
            "top": {"expr": ["0", "a", "0"]},
        }
        before = asset_model.resolve_skeleton(asset)
        asset["params"]["a"]["default"] = 5.0
        after = asset_model.resolve_skeleton(asset)
        self.assertEqual(before["top"], (0.0, 1.0, 0.0))
        self.assertEqual(after["top"], (0.0, 5.0, 0.0))


# ===================================================================
# load_asset / save_asset round-trip
# ===================================================================

class TestLoadSaveAsset(unittest.TestCase):
    def test_save_then_load_roundtrip(self):
        asset = _minimal_asset()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "test.asset.json")
            asset_model.save_asset(path, asset)
            loaded = asset_model.load_asset(path)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["id"], "test_asset")

    def test_load_missing_file_returns_none(self):
        self.assertIsNone(asset_model.load_asset("/nonexistent/path/asset.json"))

    def test_load_corrupt_file_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "bad.json")
            with open(path, "w") as f:
                f.write("{ this is not valid json")
            self.assertIsNone(asset_model.load_asset(path))

    def test_load_non_object_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "list.json")
            with open(path, "w") as f:
                f.write("[1, 2, 3]")
            self.assertIsNone(asset_model.load_asset(path))


# ===================================================================
# bicycle.asset.json — bundled sample end-to-end
# ===================================================================

class TestBicycleAsset(unittest.TestCase):
    """The bundled bicycle.asset.json is the canonical milestone-1 sample.
    These tests lock in that it validates, resolves, and produces physically
    plausible coordinates (including the corrected bb_center math)."""

    @classmethod
    def setUpClass(cls):
        cls.asset = asset_model.load_asset(BICYCLE_PATH)
        if cls.asset is None:
            raise AssertionError("bicycle.asset.json failed to load")

    def test_validates_cleanly(self):
        result = validate(self.asset)
        self.assertTrue(result["success"], result["errors"])

    def test_has_expected_param_count(self):
        result = validate(self.asset)
        # 7 primary + 3 derived = 10 params.
        self.assertEqual(result["summary"]["param_count"], 10)

    def test_has_five_skeleton_points(self):
        result = validate(self.asset)
        self.assertEqual(result["summary"]["skeleton_point_count"], 5)

    def test_resolves_five_points(self):
        resolved = asset_model.resolve_skeleton(self.asset)
        self.assertEqual(len(resolved), 5)
        for name in ("base", "rear_axle", "front_axle", "bb_center", "ground"):
            self.assertIn(name, resolved)
            self.assertEqual(len(resolved[name]), 3)

    def test_rear_axle_at_origin_radius_height(self):
        resolved = asset_model.resolve_skeleton(self.asset)
        wr = float(self.asset["params"]["wheel_radius"]["default"])
        self.assertEqual(resolved["rear_axle"], (0.0, wr, 0.0))

    def test_front_axle_is_wheelbase_ahead(self):
        resolved = asset_model.resolve_skeleton(self.asset)
        wb = float(self.asset["params"]["wheelbase"]["default"])
        wr = float(self.asset["params"]["wheel_radius"]["default"])
        self.assertEqual(resolved["front_axle"], (wb, wr, 0.0))

    def test_bb_center_uses_correct_horizontal_projection(self):
        """bb_center.x = rear_x - sqrt(chainstay_len^2 - bb_drop^2).
        This is the physically correct position (the bottom bracket sits ahead
        of the rear axle by the chainstay's horizontal projection). Previously
        the expression was the physically wrong 'rear_x + chainstay_len'."""
        resolved = asset_model.resolve_skeleton(self.asset)
        cl = float(self.asset["params"]["chainstay_len"]["default"])
        bd = float(self.asset["params"]["bb_drop"]["default"])
        expected_x = -math.sqrt(cl ** 2 - bd ** 2)  # rear_x = 0
        self.assertAlmostEqual(resolved["bb_center"][0], expected_x, places=6)
        # Sanity: with defaults (cl=0.405, bd=0.07) the projection ≈ 0.3989.
        self.assertAlmostEqual(resolved["bb_center"][0], -0.3989, delta=0.01)

    def test_bb_center_height_above_ground(self):
        resolved = asset_model.resolve_skeleton(self.asset)
        # bb_height = wheel_radius - bb_drop (derived param).
        wr = float(self.asset["params"]["wheel_radius"]["default"])
        bd = float(self.asset["params"]["bb_drop"]["default"])
        self.assertAlmostEqual(resolved["bb_center"][1], wr - bd, places=6)

    def test_wheel_radius_change_moves_wheels_and_bb(self):
        """Param linkage: increasing wheel_radius lifts both axles AND raises
        the bb (because bb_height is derived from wheel_radius)."""
        before = asset_model.resolve_skeleton(self.asset)
        self.asset["params"]["wheel_radius"]["default"] = 0.40
        try:
            after = asset_model.resolve_skeleton(self.asset)
        finally:
            self.asset["params"]["wheel_radius"]["default"] = 0.34
        self.assertGreater(after["rear_axle"][1], before["rear_axle"][1])
        self.assertGreater(after["bb_center"][1], before["bb_center"][1])


# Helper to keep test bodies concise (module-level reference to validate_asset).
def validate(asset):
    return asset_model.validate_asset(asset)


if __name__ == "__main__":
    unittest.main()
