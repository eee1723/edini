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

    # ── C-station postprocess parm-name validation ────────────────────────
    # These exercise the build-time precheck that rejects misspelled parm
    # names (e.g. Normal SOP's 'cangle' in H21) before any node is created.
    # manifest_parm_names is monkeypatched so the tests don't depend on a
    # real Houdini-generated manifest file.

    def _patch_manifest(self, mapping):
        """Patch edini.node_utils.manifest_parm_names to return canned sets.
        `mapping` is {node_type: set(parm_names)}; types not in the mapping
        return None (simulating 'not in manifest' -> soft degrade)."""
        import edini.node_utils as nu_mod

        def fake(node_type):
            return mapping.get(node_type)

        original = nu_mod.manifest_parm_names
        # _validate_recipe imports manifest_parm_names lazily from
        # edini.node_utils at call time, so patching the module attr is enough.
        nu_mod.manifest_parm_names = fake
        return original

    def _restore_manifest(self, original):
        import edini.node_utils as nu_mod
        nu_mod.manifest_parm_names = original

    def test_postprocess_valid_parm_names_accepted(self):
        """When all postprocess parm names are in the manifest, validation
        passes (no parm-name errors)."""
        recipe = {"components": [{"id": "a", "code": "pass"}],
                  "postprocess": [{"type": "normal", "params": {"cuspangle": 60}}]}
        original = self._patch_manifest({"normal": {"cuspangle", "type"}})
        try:
            errors = harness._validate_recipe(recipe)
        finally:
            self._restore_manifest(original)
        self.assertFalse(
            any("unknown parm" in e for e in errors),
            msg=f"unexpected parm error: {errors}")

    def test_postprocess_misspelled_parm_rejected(self):
        """The canonical C-station case: 'cangle' does not exist on Normal SOP
        in H21 (the real name is 'cuspangle'). The validator must reject it at
        build time with the valid names listed, before any node is created."""
        recipe = {"components": [{"id": "a", "code": "pass"}],
                  "postprocess": [{"type": "normal", "params": {"cangle": 30}}]}
        original = self._patch_manifest({"normal": {"cuspangle", "type"}})
        try:
            errors = harness._validate_recipe(recipe)
        finally:
            self._restore_manifest(original)
        joined = " ".join(errors)
        self.assertIn("unknown parm", joined)
        self.assertIn("cangle", joined)
        # The error must list the valid names so the agent can self-correct.
        self.assertIn("cuspangle", joined)

    def test_postprocess_unknown_type_soft_degrades(self):
        """If the node type is NOT in the manifest, parm checks are skipped
        (soft degrade) — never block a build just because the manifest is
        incomplete. Here 'frobnicate' is unknown, so even bogus parms pass."""
        recipe = {"components": [{"id": "a", "code": "pass"}],
                  "postprocess": [
                      {"type": "frobnicate", "params": {"bogus": 1}}]}
        original = self._patch_manifest({"normal": {"cuspangle"}})
        try:
            errors = harness._validate_recipe(recipe)
        finally:
            self._restore_manifest(original)
        self.assertFalse(any("unknown parm" in e for e in errors),
                         msg=f"should soft-degrade, got: {errors}")

    def test_postprocess_manifest_missing_soft_degrades(self):
        """With no manifest at all (manifest_parm_names returns None for
        everything), parm validation is skipped entirely."""
        recipe = {"components": [{"id": "a", "code": "pass"}],
                  "postprocess": [
                      {"type": "normal", "params": {"totally_bogus": 1}}]}
        original = self._patch_manifest({})  # empty -> everything returns None
        try:
            errors = harness._validate_recipe(recipe)
        finally:
            self._restore_manifest(original)
        self.assertFalse(any("unknown parm" in e for e in errors))


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
# Construction-axis (B-station) + asset params (A2-station) tests
# ---------------------------------------------------------------------------

class TestConstructionAxisValidation(unittest.TestCase):
    """recipe validation + build-time consistency pre-check for construction_axis."""

    def test_bad_construction_axis_rejected(self):
        r = harness.build_procedural_asset(
            {"components": [{"id": "a", "code": "x"}],
             "orientation_asserts": [
                 {"component_id": "a", "kind": "radial",
                  "expected_axis": "X", "construction_axis": "W"}]})
        self.assertFalse(r["success"])
        self.assertIn("construction_axis must be one of", r["error"])

    def test_construction_axis_contradiction_rejected_at_build(self):
        """construction_axis=Y, but anchor orient rotates Y to world Z while
        expected_axis says X. This is internally contradictory → build refuses."""
        import math
        # 90° rotation around X maps local Y → world Z. So construction_axis Y
        # projects to world Z, NOT the declared expected_axis X. Reject.
        s = math.sin(math.radians(45))
        c = math.cos(math.radians(45))
        r = harness.build_procedural_asset({
            "asset_name": "contra",
            "components": [
                {"id": "wheel", "code": _geo_code("wheel"), "anchors": [
                    {"position": [0, 0, 0], "orient": [s, 0, 0, c],
                     "pscale": 1.0, "component_id": "wheel_fl"},
                ]},
            ],
            "orientation_asserts": [
                {"component_id": "wheel_fl", "kind": "radial",
                 "expected_axis": "X", "construction_axis": "Y"},
            ],
        })
        self.assertFalse(r["success"])
        self.assertIn("construction_axis", r["error"].lower())
        self.assertIn("contradiction", r["error"].lower())
        # Must NOT leak a sandbox (rejected before _create_sandbox_root)
        self.assertFalse(r["preserved"])
        self.assertIn("construction_axis_errors", r)

    def test_construction_axis_contradiction_does_not_create_sandbox(self):
        """A rejected recipe must not leak a sandbox node (pre-check is pre-build)."""
        before = len(_mock_hou._nodes)
        import math
        s = math.sin(math.radians(45))
        c = math.cos(math.radians(45))
        harness.build_procedural_asset({
            "asset_name": "noleak",
            "components": [
                {"id": "w", "code": _geo_code("w"), "anchors": [
                    {"position": [0, 0, 0], "orient": [s, 0, 0, c],
                     "pscale": 1.0, "component_id": "w1"},
                ]},
            ],
            "orientation_asserts": [
                {"component_id": "w1", "kind": "radial",
                 "expected_axis": "X", "construction_axis": "Y"},
            ],
        })
        self.assertEqual(len(_mock_hou._nodes), before)

    def test_construction_axis_with_unknown_cid_rejected(self):
        """construction_axis references a component_id that has no matching anchor."""
        r = harness.build_procedural_asset({
            "asset_name": "badcid",
            "components": [
                {"id": "frame", "code": _geo_code("frame"), "anchors": []},
            ],
            "orientation_asserts": [
                {"component_id": "ghost", "kind": "radial",
                 "expected_axis": "X", "construction_axis": "Y"},
            ],
        })
        self.assertFalse(r["success"])
        self.assertIn("ghost", r["error"])


class TestConstructionAxisBuildBake(unittest.TestCase):
    """When construction_axis is consistent, the build succeeds and reports the
    deterministic world-axis summary."""

    def test_direct_component_construction_axis_builds(self):
        """Direct-merge component with construction_axis=Y, expected_axis=Y →
        consistent (identity frame), build succeeds with summary."""
        r = harness.build_procedural_asset({
            "asset_name": "direct_axis",
            "components": [
                {"id": "frame", "code": _geo_code("frame"), "anchors": []},
            ],
            "orientation_asserts": [
                {"component_id": "frame", "kind": "elongated",
                 "expected_axis": "Y", "construction_axis": "Y"},
            ],
        })
        self.assertTrue(r["success"], msg=r)
        self.assertIn("construction_axis_summary", r)
        self.assertIn("frame", r["construction_axis_summary"])
        self.assertEqual(
            r["construction_axis_summary"]["frame"]["method"], "construction")
        # identity frame → world axis = local Y = (0,1,0)
        self.assertAlmostEqual(
            r["construction_axis_summary"]["frame"]["world_axis"][1], 1.0, places=5)

    def test_stamped_component_construction_axis_consistent(self):
        """construction_axis=Y with identity orient → world axis Y. expected_axis=Y
        agrees. Build succeeds; the idfix snippet carries the world axis."""
        r = harness.build_procedural_asset({
            "asset_name": "stamp_axis",
            "components": [
                {"id": "frame", "code": _geo_code("frame"), "anchors": []},
                {"id": "wheel", "code": _geo_code("wheel"), "anchors": [
                    {"position": [1, 0, 0], "orient": [0, 0, 0, 1],
                     "pscale": 1.0, "component_id": "wheel_fl"},
                ]},
            ],
            "orientation_asserts": [
                {"component_id": "wheel_fl", "kind": "radial",
                 "expected_axis": "Y", "construction_axis": "Y"},
            ],
        })
        self.assertTrue(r["success"], msg=r)
        self.assertIn("construction_axis_summary", r)
        self.assertIn("wheel_fl", r["construction_axis_summary"])
        # identity orient, local Y → world (0,1,0)
        wa = r["construction_axis_summary"]["wheel_fl"]["world_axis"]
        self.assertAlmostEqual(wa[1], 1.0, places=5)

    def test_idfix_snippet_bakes_world_axis_when_provided(self):
        """The generated idfix cook body writes edini_world_axis when world_axes
        is supplied, and omits it when not (backward compat)."""
        # With world axes
        snippet = harness._component_id_overwrite_snippet(
            ["w1", "w2"],
            world_axes=[(0.0, 1.0, 0.0), (1.0, 0.0, 0.0)])
        self.assertIn("edini_world_axis", snippet)
        self.assertIn("world_axes", snippet)
        # Without world axes (old behavior)
        snippet_old = harness._component_id_overwrite_snippet(["w1", "w2"])
        self.assertNotIn("edini_world_axis", snippet_old)

    def test_construction_axis_omitted_falls_back_to_pca(self):
        """orientation_asserts WITHOUT construction_axis → no summary, PCA path.
        This proves backward compatibility: old recipes are untouched."""
        r = harness.build_procedural_asset({
            "asset_name": "pca_only",
            "components": [
                {"id": "frame", "code": _geo_code("frame"), "anchors": []},
            ],
            "orientation_asserts": [
                {"component_id": "frame", "kind": "elongated",
                 "expected_axis": "Y"},
            ],
        })
        self.assertTrue(r["success"], msg=r)
        self.assertNotIn("construction_axis_summary", r)

    def test_consistency_check_helper_pure(self):
        """The consistency pre-check is deterministic algebra — test it directly."""
        errs = harness._check_construction_axis_consistency(
            components=[
                {"id": "w", "anchors": [
                    {"component_id": "w1", "orient": [0, 0, 0, 1]},
                ]},
            ],
            orientation_asserts=[
                {"component_id": "w1", "expected_axis": "Y",
                 "construction_axis": "Y"},
            ],
        )
        # identity orient, Y→Y, expected Y → consistent, no errors
        self.assertEqual(errs, [])

    def test_consistency_check_detects_rotation_mismatch(self):
        """orient rotates local Y to world Z, but expected_axis=X → error."""
        import math
        s = math.sin(math.radians(45))
        c = math.cos(math.radians(45))
        errs = harness._check_construction_axis_consistency(
            components=[
                {"id": "w", "anchors": [
                    {"component_id": "w1", "orient": [s, 0, 0, c]},
                ]},
            ],
            orientation_asserts=[
                {"component_id": "w1", "expected_axis": "X",
                 "construction_axis": "Y"},
            ],
        )
        self.assertEqual(len(errs), 1)
        self.assertIn("w1", errs[0])


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
        # A2: params_summary is exposed with channel paths + values.
        self.assertIn("params_summary", r)
        self.assertIn("wheelbase", r["params_summary"])
        self.assertAlmostEqual(r["params_summary"]["wheelbase"]["value"], 1.0)
        # The mock now supports ParmTemplateGroup/FolderParmTemplate, so params
        # install successfully via the read-merge setParmTemplateGroup path and
        # are materialized as real parms on the root (installed=True). No
        # "not installed" warning should be emitted.
        self.assertTrue(r["params_summary"]["wheelbase"]["installed"])
        joined = " ".join(r.get("warnings", []))
        self.assertNotIn("not installed", joined)
        # The installed parms are actually present on the root node.
        root_node = _mock_hou.node(r["root_path"])
        self.assertIsNotNone(root_node.parm("wheelbase"))
        self.assertAlmostEqual(root_node.evalParm("wheelbase"), 1.0)
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


class TestInstallSpareParams(unittest.TestCase):
    """_install_spare_params installs asset-level params on the sandbox root.

    With the mock now simulating ParmTemplateGroup/FolderParmTemplate, the
    success path installs the parms (installed=True) and materializes them as
    real parms on the root. A degraded path is also covered: when the
    FloatParmTemplate ctor cannot build any template, the function records
    installed=False and still returns resolved defaults so expression eval can
    proceed."""

    def test_installs_params_and_materializes_on_root(self):
        from tests.test_node_utils import _mock_hou  # shared mock
        # Build a throwaway node on the shared mock.
        root = _mock_hou.node("/obj").createNode("geo", "tmp_root")
        result = harness._install_spare_params(root, {
            "wheelbase": {"default": 1.0, "min": 0.5, "max": 2.0},
            "wheel_r": {"default": 0.35, "label": "Wheel Radius"},
        })
        # Every param recorded with its resolved default.
        self.assertAlmostEqual(result["wheelbase"]["value"], 1.0)
        self.assertAlmostEqual(result["wheel_r"]["value"], 0.35)
        # channel_path points at the sandbox root.
        self.assertTrue(result["wheelbase"]["channel_path"].endswith("/wheelbase"))
        # label surfaces only when it differs from the name.
        self.assertIsNone(result["wheelbase"]["label"])
        self.assertEqual(result["wheel_r"]["label"], "Wheel Radius")
        # Mock supports the template-group path -> installed.
        self.assertTrue(result["wheelbase"]["installed"])
        self.assertTrue(result["wheel_r"]["installed"])
        # The parms are materialized as real parms on the root.
        self.assertIsNotNone(root.parm("wheelbase"))
        self.assertAlmostEqual(root.evalParm("wheelbase"), 1.0)
        self.assertAlmostEqual(root.evalParm("wheel_r"), 0.35)
        root.destroy()

    def test_returns_defaults_when_parm_api_unavailable(self):
        """Degraded path: if FloatParmTemplate construction fails for every
        candidate, params are recorded with installed=False but resolved
        defaults are still returned (so anchor expr eval proceeds)."""
        from tests.test_node_utils import _mock_hou

        class _NoTemplate:
            # Emulates a Houdini build lacking FloatParmTemplate: any ctor
            # invocation raises AttributeError, failing every candidate in the
            # H21-safe ctor chain.
            def __init__(self, *a, **k):
                raise AttributeError("FloatParmTemplate")

        # _install_spare_params reads hou via sys.modules (the shared mock), so
        # patch the shared mock's FloatParmTemplate, then restore it.
        saved = _mock_hou.FloatParmTemplate
        _mock_hou.FloatParmTemplate = _NoTemplate
        try:
            root = _mock_hou.node("/obj").createNode("geo", "tmp_degraded")
            result = harness._install_spare_params(root, {
                "wheelbase": {"default": 1.0, "min": 0.5, "max": 2.0},
            })
            self.assertAlmostEqual(result["wheelbase"]["value"], 1.0)
            # No template could be built -> not installed, but value resolves.
            self.assertFalse(result["wheelbase"]["installed"])
            root.destroy()
        finally:
            _mock_hou.FloatParmTemplate = saved

    def test_empty_spec_returns_empty(self):
        from tests.test_node_utils import _mock_hou
        root = _mock_hou.node("/obj").createNode("geo", "tmp_empty")
        self.assertEqual(harness._install_spare_params(root, {}), {})
        root.destroy()

    def test_build_float_parm_template_candidate_chain_is_safe(self):
        """The ctor candidate chain must not raise unhandled — it raises a
        clear RuntimeError only when ALL candidates fail. Simulate a stripped
        build (no FloatParmTemplate attribute) to force every candidate to
        raise."""
        from tests.mock_hou import MockHou

        class _NoTemplate:
            def __init__(self, *a, **k):
                raise AttributeError("FloatParmTemplate")

        mock = MockHou()
        mock.FloatParmTemplate = _NoTemplate
        with self.assertRaises(RuntimeError) as cm:
            harness._build_float_parm_template(
                mock, "wb", "WB", 1.0, 0.0, 10.0)
        self.assertIn("FloatParmTemplate", str(cm.exception))


# ---------------------------------------------------------------------------
# Variant Scatter (V-station) tests
# ---------------------------------------------------------------------------

def _variant_geo_code(cid):
    """Minimal variant cook body: emits one prim tagged with component_id."""
    return (
        "node = hou.pwd()\n"
        "geo = node.geometry()\n"
        "geo.clear()\n"
        'geo.addAttrib(hou.attribType.Prim, "component_id", "")\n'
        "pt = geo.createPoint(); pt.setPosition((0, 0, 0))\n"
        "poly = geo.createPolygon(); poly.addVertex(pt)\n"
        f'poly.setAttribValue("component_id", "{cid}")\n'
    )


def _scatter_points_code(n=3):
    """Minimal scatter source: emits n points along X."""
    code = (
        "node = hou.pwd()\n"
        "geo = node.geometry()\n"
        "geo.clear()\n"
    )
    for i in range(n):
        code += (
            f"pt{i} = geo.createPoint(); pt{i}.setPosition(({i}, 0, 0))\n")
    return code


class TestVariantRecipeValidation(unittest.TestCase):
    """_validate_variant_recipe mirrors _validate_recipe's shape."""

    def test_non_object_recipe_rejected(self):
        errs = harness._validate_variant_recipe(["not", "a", "dict"])
        self.assertTrue(any("must be a JSON object" in e for e in errs))

    def test_empty_variants_rejected(self):
        errs = harness._validate_variant_recipe({"variants": []})
        self.assertTrue(any("non-empty list" in e for e in errs))

    def test_missing_variant_id_rejected(self):
        errs = harness._validate_variant_recipe(
            {"variants": [{"code": "x"}]})
        self.assertTrue(any("id must be a non-empty string" in e for e in errs))

    def test_missing_variant_code_rejected(self):
        errs = harness._validate_variant_recipe(
            {"variants": [{"id": "a"}], "scatter": {"source": "s"}})
        self.assertTrue(any("code must be a non-empty string" in e for e in errs))

    def test_duplicate_variant_id_rejected(self):
        errs = harness._validate_variant_recipe({
            "variants": [
                {"id": "a", "code": "x"},
                {"id": "a", "code": "y"},
            ],
            "scatter": {"source": "s"}})
        self.assertTrue(any("duplicates" in e for e in errs))

    def test_missing_scatter_rejected(self):
        errs = harness._validate_variant_recipe(
            {"variants": [{"id": "a", "code": "x"}]})
        self.assertTrue(any("scatter must be an object" in e for e in errs))

    def test_missing_scatter_source_rejected(self):
        errs = harness._validate_variant_recipe(
            {"variants": [{"id": "a", "code": "x"}],
             "scatter": {"seed": 1}})
        self.assertTrue(any("source must be a non-empty" in e for e in errs))

    def test_non_int_seed_rejected(self):
        errs = harness._validate_variant_recipe({
            "variants": [{"id": "a", "code": "x"}],
            "scatter": {"source": "s", "seed": 1.5}})
        self.assertTrue(any("seed must be an integer" in e for e in errs))

    def test_weight_for_unknown_variant_rejected(self):
        errs = harness._validate_variant_recipe({
            "variants": [{"id": "a", "code": "x"}],
            "scatter": {"source": "s", "weights": {"ghost": 1.0}}})
        self.assertTrue(any("unknown variant 'ghost'" in e for e in errs))

    def test_all_zero_weights_rejected(self):
        errs = harness._validate_variant_recipe({
            "variants": [{"id": "a", "code": "x"},
                         {"id": "b", "code": "y"}],
            "scatter": {"source": "s", "weights": {"a": 0, "b": 0}}})
        self.assertTrue(any("all zero" in e for e in errs))

    def test_valid_recipe_no_errors(self):
        errs = harness._validate_variant_recipe({
            "variants": [{"id": "a", "code": "x"},
                         {"id": "b", "code": "y"}],
            "scatter": {"source": "s", "seed": 7,
                        "weights": {"a": 0.7, "b": 0.3}}})
        self.assertEqual(errs, [])


class TestBuildVariantScatter(unittest.TestCase):
    """Variant-scatter network structure tests.

    The mock does not simulate real Copy-to-Points piece-attribute dispatch
    or Attribute from Pieces, so we verify the NETWORK STRUCTURE (node names +
    wiring) rather than per-instance geometry — same approach as
    TestBuildStampedComponents for the recipe builder.
    """

    def _minimal_recipe(self):
        return {
            "asset_name": "vscatter",
            "variants": [
                {"id": "win_a", "code": _variant_geo_code("win_a")},
                {"id": "win_b", "code": _variant_geo_code("win_b")},
            ],
            "scatter": {"source": _scatter_points_code(3), "seed": 42},
        }

    def test_build_succeeds_and_reports_mode(self):
        r = harness.build_variant_scatter(self._minimal_recipe())
        self.assertTrue(r["success"], msg=r.get("error"))
        self.assertEqual(r["build_mode"], "variant_scatter")
        self.assertEqual(sorted(r["variants_built"]), ["win_a", "win_b"])
        self.assertEqual(r["n_variants"], 2)
        self.assertEqual(r["seed"], 42)
        self.assertEqual(r["piece_attribute"], "variant")

    def test_expected_node_network_built(self):
        r = harness.build_variant_scatter(self._minimal_recipe())
        self.assertTrue(r["success"], msg=r.get("error"))
        root = _mock_hou.node(r["root_path"])
        names = {c.name() for c in root.children()}
        # One python SOP per variant.
        self.assertIn("win_a_python", names)
        self.assertIn("win_b_python", names)
        # The variant chain: merge → pack(packbyname) → scatter → copytopoints
        # → unpack → idfix. NOTE: no attribfrompieces — the weighted assignment
        # lives in the scatter-points Python wrapper, so Copy to Points
        # dispatches directly by matching the point's `variant` against the
        # packed source's `variant`.
        self.assertIn("variants_merge", names)
        self.assertIn("variants_pack", names)
        self.assertIn("scatter_points", names)
        self.assertIn("copy_scatter", names)
        self.assertIn("scatter_unpack", names)
        self.assertIn("scatter_idfix", names)
        self.assertIn("OUT", names)
        self.assertNotIn("attribfrompieces", names)

    def test_structure_gate_passes_not_monolithic(self):
        """pack/copytopoints are recognized as modular by _MODULAR_NODE_TYPES,
        so the structure gate must NOT flag the result as monolithic."""
        r = harness.build_variant_scatter(self._minimal_recipe())
        self.assertTrue(r["success"], msg=r.get("error"))
        advisory = r["structure_advisory"]
        self.assertTrue(advisory["passed"], msg=advisory)
        self.assertFalse(advisory["is_monolithic"])
        # copy_scatter (copytopoints) must be counted as a modular node.
        self.assertGreaterEqual(advisory["details"]["modular_node_count"], 1)

    def test_weights_normalized_and_reported(self):
        """Weights are auto-normalized; the response echoes the per-variant
        weight regardless of sum."""
        recipe = self._minimal_recipe()
        recipe["scatter"]["weights"] = {"win_a": 14, "win_b": 6}
        r = harness.build_variant_scatter(recipe)
        self.assertTrue(r["success"], msg=r.get("error"))
        # Echoed raw weights (normalization happens in the generated code).
        self.assertEqual(r["weights"], {"win_a": 14, "win_b": 6})

    def test_postprocess_chain_built(self):
        recipe = self._minimal_recipe()
        recipe["postprocess"] = [
            {"type": "fuse"},
            {"type": "clean"},
            {"type": "normal", "params": {"cuspangle": 60}},
        ]
        r = harness.build_variant_scatter(recipe)
        self.assertTrue(r["success"], msg=r.get("error"))
        root = _mock_hou.node(r["root_path"])
        names = {c.name() for c in root.children()}
        self.assertIn("post_0_fuse", names)
        self.assertIn("post_1_clean", names)
        self.assertIn("post_2_normal", names)

    def test_variant_cook_failure_preserves_sandbox(self):
        recipe = {
            "asset_name": "failvs",
            "variants": [
                {"id": "broken", "code": "raise RuntimeError('boom in variant')"},
            ],
            "scatter": {"source": _scatter_points_code(2), "seed": 1},
        }
        r = harness.build_variant_scatter(recipe)
        self.assertFalse(r["success"])
        self.assertIn("broken", r["error"])
        self.assertIn("boom in variant", r["error"])
        self.assertTrue(r["preserved"])
        self.assertIsNotNone(_mock_hou.node(r["root_path"]))

    def test_variant_cook_failure_delete_on_failure(self):
        recipe = {
            "asset_name": "faildelvs",
            "variants": [
                {"id": "broken", "code": "raise RuntimeError('nope')"},
            ],
            "scatter": {"source": _scatter_points_code(2), "seed": 1},
        }
        r = harness.build_variant_scatter(recipe, delete_on_failure=True)
        self.assertFalse(r["success"])
        self.assertTrue(r["deleted"])
        self.assertIsNone(_mock_hou.node(r["root_path"]))

    def test_invalid_recipe_does_not_create_sandbox(self):
        before = len(_mock_hou._nodes)
        harness.build_variant_scatter({"variants": []})
        self.assertEqual(len(_mock_hou._nodes), before)

    def test_result_is_json_serializable(self):
        r = harness.build_variant_scatter(self._minimal_recipe())
        self.assertTrue(r["success"], msg=r.get("error"))
        json.dumps(r)  # must not raise

    def test_built_asset_commits_via_commit_sandbox(self):
        """The variant-scatter OUT must be consumable by the existing commit
        gate (no gate changes needed), same contract as build_procedural_asset."""
        r = harness.build_variant_scatter(self._minimal_recipe())
        self.assertTrue(r["success"], msg=r.get("error"))
        committed = harness.commit_sandbox(
            r["root_path"], "committed_scatter", replace_existing=False)
        self.assertTrue(committed["success"])
        self.assertTrue(committed["committed"])
        self.assertEqual(committed["final_path"], "/obj/committed_scatter")


class TestVariantIdfixSnippet(unittest.TestCase):
    """The idfix code generator is pure string assembly — test it directly."""

    def test_snippet_reads_prim_variant_and_connectivity_piece(self):
        """The variant idfix must NOT use the `per_copy = total // n_anchors`
        boundary detection of _component_id_overwrite_snippet (which assumes a
        single uniform source). Instead it reads the prim-level `variant`
        attribute (which survives unpack) + the `piece` attribute from a
        Connectivity SOP (which gives each connected instance a unique number).
        It must NOT rely on point attributes (edini_scatter_ptnum) because Copy
        to Points does not transfer target-point attributes onto instances."""
        snippet = harness._variant_idfix_snippet(["win_a", "win_b"])
        self.assertIn("variant_ids", snippet)
        self.assertIn("win_a", snippet)
        self.assertIn("win_b", snippet)
        # Reads variant from the PRIM (survives unpack), not from points.
        self.assertIn("prim.attribValue('variant')", snippet)
        # Reads the connectivity `piece` attrib for per-instance uniqueness.
        self.assertIn("'piece'", snippet)
        # Must NOT contain the single-source boundary detection.
        self.assertNotIn("per_copy", snippet)
        # Must NOT rely on the now-gone point-level scatter ptnum.
        self.assertNotIn("edini_scatter_ptnum", snippet)
        # Builds per-instance ids as {variant_id}_{piece}.
        self.assertIn("str(piece)", snippet)


class TestVariantScatterPointsCode(unittest.TestCase):
    """The scatter-points wrapper assigns the `variant` piece attribute per
    point using a weighted, seeded distribution."""

    def test_wrapper_includes_user_code(self):
        wrapper = harness._variant_scatter_points_code(
            ["a", "b"], {"a": 1.0, "b": 1.0}, 42, "# USER CODE HERE")
        self.assertIn("# USER CODE HERE", wrapper)
        self.assertIn("variant", wrapper)
        self.assertIn("edini_scatter_ptnum", wrapper)

    def test_weights_normalized_to_cumulative_thresholds(self):
        """2 variants at 3:1 -> normalized cumulative [0.75, 1.0]."""
        wrapper = harness._variant_scatter_points_code(
            ["a", "b"], {"a": 3.0, "b": 1.0}, 0, "")
        # The first threshold should be ~0.75 (3/4).
        self.assertIn("0.75", wrapper)

    def test_seed_threaded_into_rng(self):
        wrapper = harness._variant_scatter_points_code(
            ["a"], {}, 123, "")
        self.assertIn("123", wrapper)
        self.assertIn("random.Random", wrapper)


if __name__ == "__main__":
    unittest.main()
