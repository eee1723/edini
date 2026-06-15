"""Tests for the declarative recipe builder (build_procedural_asset / A-station).

The builder turns a JSON recipe into a deterministic modular network. These
tests cover: recipe validation, single-component direct-merge, multi-component
Copy-to-Points assembly, component cook failure handling, component_id presence
checking, orientation preview, and JSON serializability.

Mock reuse: this module consumes the shared mock installed by test_node_utils
(same pattern as test_procedural_harness). test_error_surfacing's hou-install
is idempotent so it no longer orphans the shared mock.

Note on mock limitations: the mock's copytopoints does NOT actually stamp
geometry (no real cook cascade), so per-instance component_id overwrite can't
be verified end-to-end here. We verify the *network is built* (copytopoints
node exists → structure gate sees modularity) and direct-merge component_id
flow end-to-end. Real-stamping behavior is validated in Houdini runtime.
"""
import json
import unittest

from tests.test_node_utils import _mock_hou

from edini import harness


def _geo_code(cid):
    """A minimal single-SOP cook body emitting one prim tagged with component_id."""
    return (
        "node = hou.pwd()\n"
        "geo = node.geometry()\n"
        "geo.clear()\n"
        'geo.addAttrib(hou.attribType.Prim, "component_id", "")\n'
        "pt = geo.createPoint(); pt.setPosition((0, 0, 0))\n"
        "poly = geo.createPolygon(); poly.addVertex(pt)\n"
        f'poly.setAttribValue("component_id", "{cid}")\n'
    )


class TestRecipeValidation(unittest.TestCase):
    def test_non_object_recipe_rejected(self):
        r = harness.build_procedural_asset(["not", "a", "dict"])
        self.assertFalse(r["success"])
        self.assertIn("must be a JSON object", r["error"])

    def test_empty_components_rejected(self):
        r = harness.build_procedural_asset({"components": []})
        self.assertFalse(r["success"])
        self.assertIn("non-empty list", r["error"])

    def test_missing_component_id_rejected(self):
        r = harness.build_procedural_asset(
            {"components": [{"code": "x"}]})
        self.assertFalse(r["success"])
        self.assertIn("id must be a non-empty string", r["error"])

    def test_missing_component_code_rejected(self):
        r = harness.build_procedural_asset(
            {"components": [{"id": "a"}]})
        self.assertFalse(r["success"])
        self.assertIn("code must be a non-empty string", r["error"])

    def test_duplicate_component_id_rejected(self):
        r = harness.build_procedural_asset(
            {"components": [
                {"id": "a", "code": "x"},
                {"id": "a", "code": "y"},
            ]})
        self.assertFalse(r["success"])
        self.assertIn("duplicates", r["error"])

    def test_bad_anchor_position_rejected(self):
        r = harness.build_procedural_asset(
            {"components": [
                {"id": "a", "code": "x", "anchors": [
                    {"component_id": "a1", "position": [1, 2]},
                ]},
            ]})
        self.assertFalse(r["success"])
        self.assertIn("position must be", r["error"])

    def test_bad_orientation_kind_rejected(self):
        r = harness.build_procedural_asset(
            {"components": [{"id": "a", "code": "x"}],
             "orientation_asserts": [
                 {"component_id": "a", "kind": "bogus", "expected_axis": "X"}]})
        self.assertFalse(r["success"])
        self.assertIn("kind must be", r["error"])

    def test_validation_does_not_create_sandbox(self):
        """A rejected recipe must not leak a sandbox node."""
        before = len(_mock_hou._nodes)
        harness.build_procedural_asset({"components": []})
        self.assertEqual(len(_mock_hou._nodes), before)


class TestBuildDirectMerge(unittest.TestCase):
    """Single / multi component WITHOUT anchors: each goes straight to merge."""

    def test_single_component_builds_and_finds_component_id(self):
        recipe = {
            "asset_name": "single",
            "components": [{"id": "frame", "code": _geo_code("frame"), "anchors": []}],
        }
        r = harness.build_procedural_asset(recipe)

        self.assertTrue(r["success"])
        self.assertEqual(r["build_mode"], "recipe")
        self.assertEqual(r["components_built"], ["frame"])
        self.assertTrue(r["output_node"].endswith("/OUT"))
        self.assertEqual(r["component_id_check"]["missing"], [])
        self.assertEqual(r["component_id_check"]["ok"], ["frame"])

    def test_two_direct_components_both_build(self):
        """Two direct-merge components each build their own python SOP with
        component_id. (The mock's merge doesn't union geometry onto OUT, so we
        assert each component node carries its own id rather than the merged set.)"""
        recipe = {
            "asset_name": "pair",
            "components": [
                {"id": "frame", "code": _geo_code("frame"), "anchors": []},
                {"id": "saddle", "code": _geo_code("saddle"), "anchors": []},
            ],
        }
        r = harness.build_procedural_asset(recipe)

        self.assertTrue(r["success"])
        self.assertEqual(sorted(r["components_built"]), ["frame", "saddle"])
        frame_node = _mock_hou.node(f"{r['root_path']}/frame_python")
        saddle_node = _mock_hou.node(f"{r['root_path']}/saddle_python")
        self.assertIsNotNone(frame_node)
        self.assertIsNotNone(saddle_node)
        frame_ids = harness._geometry_component_ids(frame_node.geometry())
        saddle_ids = harness._geometry_component_ids(saddle_node.geometry())
        self.assertEqual(frame_ids, {"frame"})
        self.assertEqual(saddle_ids, {"saddle"})

    def test_structure_advisory_runs_on_build(self):
        recipe = {
            "asset_name": "adv",
            "components": [{"id": "x", "code": _geo_code("x"), "anchors": []}],
        }
        r = harness.build_procedural_asset(recipe)
        self.assertTrue(r["success"])
        self.assertIn("structure_advisory", r)
        self.assertTrue(r["structure_advisory"]["passed"])

    def test_postprocess_chain_built(self):
        recipe = {
            "asset_name": "pp",
            "components": [{"id": "x", "code": _geo_code("x"), "anchors": []}],
            "postprocess": [
                {"type": "normal", "params": {}},
            ],
        }
        r = harness.build_procedural_asset(recipe)
        self.assertTrue(r["success"])
        root = _mock_hou.node(r["root_path"])
        names = [c.name() for c in root.children()]
        self.assertIn("post_0_normal", names)
        self.assertIn("OUT", names)

    def test_sandbox_name_defaults_to_asset_name(self):
        recipe = {
            "asset_name": "mybike",
            "components": [{"id": "x", "code": _geo_code("x"), "anchors": []}],
        }
        r = harness.build_procedural_asset(recipe)
        self.assertTrue(r["success"])
        self.assertIn("mybike", r["root_path"])

    def test_explicit_sandbox_name_used(self):
        recipe = {
            "asset_name": "ignored",
            "components": [{"id": "x", "code": _geo_code("x"), "anchors": []}],
        }
        r = harness.build_procedural_asset(recipe, sandbox_name="custom_name")
        self.assertTrue(r["success"])
        self.assertIn("custom_name", r["root_path"])


class TestBuildStampedComponents(unittest.TestCase):
    """Components WITH anchors: builder wires copytopoints + idfix.

    The mock does not simulate real Copy-to-Points stamping, so we verify the
    network structure (copytopoints node present → structure gate sees
    modularity) rather than per-instance geometry.
    """

    def test_stamped_component_creates_copytopoints_network(self):
        recipe = {
            "asset_name": "stamped",
            "components": [
                {"id": "frame", "code": _geo_code("frame"), "anchors": []},
                {"id": "wheel", "code": _geo_code("wheel"), "anchors": [
                    {"position": [0.3, 0.3, -0.5], "orient": [0, 0, 0, 1],
                     "pscale": 1.0, "component_id": "wheel_fl"},
                    {"position": [-0.3, 0.3, 0.5], "orient": [0, 0, 0, 1],
                     "pscale": 1.0, "component_id": "wheel_rr"},
                ]},
            ],
        }
        r = harness.build_procedural_asset(recipe)

        self.assertTrue(r["success"])
        self.assertEqual(r["anchors_built"], {"wheel": 2})
        root = _mock_hou.node(r["root_path"])
        names = {c.name() for c in root.children()}
        self.assertIn("wheel_python", names)
        self.assertIn("wheel_anchors", names)
        self.assertIn("copy_wheel", names)
        self.assertIn("wheel_idfix", names)
        self.assertIn("merge_all", names)
        self.assertIn("OUT", names)

    def test_stamped_network_passes_structure_gate(self):
        """A Copy-to-Points network is NOT monolithic — the gate accepts it."""
        recipe = {
            "asset_name": "modular",
            "components": [
                {"id": "body", "code": _geo_code("body"), "anchors": []},
                {"id": "wheel", "code": _geo_code("wheel"), "anchors": [
                    {"position": [1, 0, 0], "orient": [0, 0, 0, 1],
                     "pscale": 1.0, "component_id": "w1"},
                ]},
            ],
        }
        r = harness.build_procedural_asset(recipe)
        self.assertTrue(r["success"])
        self.assertTrue(r["structure_advisory"]["passed"])
        self.assertFalse(r["structure_advisory"]["is_monolithic"])
        self.assertGreaterEqual(
            r["structure_advisory"]["details"]["modular_node_count"], 1)

    def test_orientation_assert_preview_in_result(self):
        """orientation_asserts produce an orientation_check preview field that
        runs verify_orientation on the built output. (Mock merge doesn't union
        geometry, so the assert's component_id must match the single cooked
        component for verify_orientation to find it.)"""
        recipe = {
            "asset_name": "ori",
            "components": [{"id": "x", "code": _geo_code("x"), "anchors": []}],
            "orientation_asserts": [
                {"component_id": "x", "kind": "elongated", "expected_axis": "Y"},
            ],
        }
        r = harness.build_procedural_asset(recipe)
        self.assertTrue(r["success"])
        self.assertIn("orientation_check", r)
        oc = r["orientation_check"]
        self.assertIn("checks", oc)
        self.assertEqual(oc["total"], 1)


class TestBuildFailures(unittest.TestCase):
    def test_component_cook_failure_preserves_sandbox(self):
        recipe = {
            "asset_name": "fail",
            "components": [
                {"id": "broken", "code": "raise RuntimeError('boom in geo')",
                 "anchors": []},
            ],
        }
        r = harness.build_procedural_asset(recipe)

        self.assertFalse(r["success"])
        self.assertIn("broken", r["error"])
        self.assertIn("boom in geo", r["error"])
        self.assertTrue(r["preserved"])
        self.assertIsNotNone(_mock_hou.node(r["root_path"]))

    def test_component_cook_failure_delete_on_failure(self):
        recipe = {
            "asset_name": "faildel",
            "components": [
                {"id": "broken", "code": "raise RuntimeError('nope')", "anchors": []},
            ],
        }
        r = harness.build_procedural_asset(recipe, delete_on_failure=True)

        self.assertFalse(r["success"])
        self.assertTrue(r["deleted"])
        self.assertIsNone(_mock_hou.node(r["root_path"]))

    def test_missing_component_id_reported_not_silent(self):
        """Component code that forgets to tag component_id is reported in missing."""
        no_tag_code = (
            "node = hou.pwd()\n"
            "geo = node.geometry()\n"
            "geo.clear()\n"
            "pt = geo.createPoint(); pt.setPosition((0, 0, 0))\n"
            "poly = geo.createPolygon(); poly.addVertex(pt)\n"
            # NOTE: deliberately no setAttribValue("component_id", ...)
        )
        recipe = {
            "asset_name": "notag",
            "components": [{"id": "ghost", "code": no_tag_code, "anchors": []}],
        }
        r = harness.build_procedural_asset(recipe)
        self.assertTrue(r["success"])
        self.assertIn("ghost", r["component_id_check"]["missing"])


class TestBuildResultShape(unittest.TestCase):
    def test_result_is_json_serializable(self):
        recipe = {
            "asset_name": "ser",
            "components": [
                {"id": "frame", "code": _geo_code("frame"), "anchors": []},
                {"id": "wheel", "code": _geo_code("wheel"), "anchors": [
                    {"position": [1, 0, 0], "orient": [0, 0, 0, 1],
                     "pscale": 1.0, "component_id": "w1"},
                ]},
            ],
            "orientation_asserts": [
                {"component_id": "frame", "kind": "elongated", "expected_axis": "Z"},
            ],
        }
        r = harness.build_procedural_asset(recipe)
        self.assertTrue(r["success"])
        json.dumps(r)  # must not raise

    def test_built_asset_commits_via_commit_sandbox(self):
        """The builder's OUT must be consumable by the existing commit gate
        (no gate changes needed). End-to-end build → commit on a modular asset."""
        recipe = {
            "asset_name": "commitme",
            "components": [
                {"id": "body", "code": _geo_code("body"), "anchors": []},
                {"id": "wheel", "code": _geo_code("wheel"), "anchors": [
                    {"position": [1, 0, 0], "orient": [0, 0, 0, 1],
                     "pscale": 1.0, "component_id": "w1"},
                ]},
            ],
        }
        built = harness.build_procedural_asset(recipe)
        self.assertTrue(built["success"])

        committed = harness.commit_sandbox(
            built["root_path"], "committed_bike", replace_existing=False)
        self.assertTrue(committed["success"])
        self.assertTrue(committed["committed"])
        self.assertEqual(committed["final_path"], "/obj/committed_bike")


# ---------------------------------------------------------------------------
# A2-station: asset-level shared parameters + expression-driven anchors
# ---------------------------------------------------------------------------

class TestRecipeParamsValidation(unittest.TestCase):
    def test_params_with_non_number_default_rejected(self):
        r = harness.build_procedural_asset({
            "components": [{"id": "a", "code": "x"}],
            "params": {"wheelbase": {"default": "oops"}},
        })
        self.assertFalse(r["success"])
        self.assertIn("default must be a number", r["error"])

    def test_reads_unknown_param_rejected(self):
        r = harness.build_procedural_asset({
            "components": [{"id": "a", "code": "x", "reads": ["bogus"]}],
            "params": {"wheelbase": {"default": 1.0}},
        })
        self.assertFalse(r["success"])
        self.assertIn("unknown param", r["error"])

    def test_position_and_position_expr_both_rejected(self):
        r = harness.build_procedural_asset({
            "components": [{"id": "a", "code": "x", "anchors": [
                {"component_id": "a1", "position": [1, 2, 3],
                 "position_expr": ["1", "2", "3"]},
            ]}],
        })
        self.assertFalse(r["success"])
        self.assertIn("not both", r["error"])

    def test_position_expr_wrong_length_rejected(self):
        r = harness.build_procedural_asset({
            "components": [{"id": "a", "code": "x", "anchors": [
                {"component_id": "a1", "position_expr": ["1", "2"]},
            ]}],
        })
        self.assertFalse(r["success"])
        self.assertIn("position_expr", r["error"])


class TestResolveAnchorExprs(unittest.TestCase):
    """The anchor expression resolver is pure + deterministic — test directly."""

    def test_position_expr_evaluated(self):
        anchors = [{"component_id": "w1",
                    "position_expr": ["wheelbase/2", "wheel_r", "0"]}]
        resolved, errs = harness._resolve_anchor_exprs(
            anchors, {"wheelbase": 1.0, "wheel_r": 0.35}, "wheel")
        self.assertEqual(errs, [])
        self.assertEqual(len(resolved), 1)
        self.assertAlmostEqual(resolved[0]["position"][0], 0.5)
        self.assertAlmostEqual(resolved[0]["position"][1], 0.35)
        self.assertEqual(resolved[0]["component_id"], "w1")
        self.assertEqual(resolved[0]["orient"], [0.0, 0.0, 0.0, 1.0])
        self.assertEqual(resolved[0]["pscale"], 1.0)

    def test_static_position_passes_through(self):
        anchors = [{"component_id": "w1", "position": [1.0, 2.0, 3.0]}]
        resolved, errs = harness._resolve_anchor_exprs(anchors, {}, "wheel")
        self.assertEqual(errs, [])
        self.assertEqual(resolved[0]["position"], [1.0, 2.0, 3.0])

    def test_pscale_expr_evaluated(self):
        anchors = [{"component_id": "w1", "position": [0, 0, 0],
                    "pscale_expr": "wheel_r * 2"}]
        resolved, errs = harness._resolve_anchor_exprs(
            anchors, {"wheel_r": 0.4}, "wheel")
        self.assertEqual(errs, [])
        self.assertAlmostEqual(resolved[0]["pscale"], 0.8)

    def test_orient_expr_evaluated(self):
        anchors = [{"component_id": "w1", "position": [0, 0, 0],
                    "orient_expr": ["0", "0", "0", "1"]}]
        resolved, errs = harness._resolve_anchor_exprs(anchors, {}, "wheel")
        self.assertEqual(errs, [])
        self.assertEqual(resolved[0]["orient"], [0.0, 0.0, 0.0, 1.0])

    def test_bad_expression_reports_error(self):
        anchors = [{"component_id": "w1",
                    "position_expr": ["wheelbase / 0", "0", "0"]}]
        resolved, errs = harness._resolve_anchor_exprs(
            anchors, {"wheelbase": 1.0}, "wheel")
        self.assertEqual(resolved, [])
        self.assertEqual(len(errs), 1)
        self.assertIn("w1", errs[0])

    def test_unknown_param_in_expr_reports_error(self):
        anchors = [{"component_id": "w1",
                    "position_expr": ["bogus + 1", "0", "0"]}]
        resolved, errs = harness._resolve_anchor_exprs(anchors, {}, "wheel")
        self.assertEqual(resolved, [])
        self.assertEqual(len(errs), 1)


class TestBuildWithParams(unittest.TestCase):
    """End-to-end build with params + expression anchors (mock)."""

    def test_build_with_params_succeeds(self):
        recipe = {
            "asset_name": "parametric",
            "params": {
                "wheelbase": {"default": 1.0, "min": 0.5, "max": 2.0},
                "wheel_r": {"default": 0.35},
            },
            "components": [
                {"id": "frame", "code": _geo_code("frame"), "anchors": [],
                 "reads": ["wheelbase", "wheel_r"]},
                {"id": "wheel", "code": _geo_code("wheel"), "anchors": [
                    {"component_id": "wheel_fl",
                     "position_expr": ["wheelbase/2", "wheel_r", "0"],
                     "pscale_expr": "wheel_r * 2"},
                    {"component_id": "wheel_rr",
                     "position_expr": ["-wheelbase/2", "wheel_r", "0"],
                     "pscale_expr": "wheel_r * 2"},
                ]},
            ],
        }
        r = harness.build_procedural_asset(recipe)
        self.assertTrue(r["success"], msg=r.get("error"))
        self.assertEqual(r["anchors_built"], {"wheel": 2})
        anc = _mock_hou.node(f"{r['root_path']}/wheel_anchors")
        self.assertIsNotNone(anc)
        pts = anc.geometry().points()
        self.assertEqual(len(pts), 2)
        self.assertAlmostEqual(pts[0].position()[0], 0.5)
        self.assertAlmostEqual(pts[0].position()[1], 0.35)
        self.assertAlmostEqual(pts[1].position()[0], -0.5)

    def test_build_without_params_backward_compatible(self):
        recipe = {
            "asset_name": "legacy",
            "components": [
                {"id": "frame", "code": _geo_code("frame"), "anchors": []},
                {"id": "wheel", "code": _geo_code("wheel"), "anchors": [
                    {"position": [1, 0, 0], "component_id": "w1"},
                ]},
            ],
        }
        r = harness.build_procedural_asset(recipe)
        self.assertTrue(r["success"], msg=r.get("error"))
        anc = _mock_hou.node(f"{r['root_path']}/wheel_anchors")
        pts = anc.geometry().points()
        self.assertEqual(len(pts), 1)
        self.assertAlmostEqual(pts[0].position()[0], 1.0)

    def test_build_bad_anchor_expr_surfaces_error(self):
        recipe = {
            "asset_name": "badexpr",
            "params": {"wheelbase": {"default": 1.0}},
            "components": [
                {"id": "frame", "code": _geo_code("frame"), "anchors": []},
                {"id": "wheel", "code": _geo_code("wheel"), "anchors": [
                    {"component_id": "w1",
                     "position_expr": ["bogus", "0", "0"]},
                ]},
            ],
        }
        r = harness.build_procedural_asset(recipe)
        self.assertFalse(r["success"])
        self.assertIn("bogus", r["error"])


if __name__ == "__main__":
    unittest.main()
