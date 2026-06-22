"""Single-path + three-gate design — gate test matrix (spec §5.3).

Each test reproduces a concrete failure mode documented in the road_bike
session log analysis (the castle log that motivated the single-path design).
The gates are layered defense-in-depth:

  G1 (validate_recipe) — A8 mandatory construction_axis, A9 hardcoded-size
  G2 (build_procedural_asset) — bake check on output geometry
  G3 (commit_sandbox) — bake + orientation + health hard gates + receipt

These tests run entirely on the mock hou (no real Houdini). Where the mock's
copytopoints does not propagate geometry, tests build the post-build state
directly (e.g. a hand-rolled sandbox with baked/unbaked axes) to exercise the
commit gate, which is what those tests are about.
"""
import importlib
import sys
import unittest

from tests.test_node_utils import _mock_hou


class TestG1A8MandatoryConstructionAxis(unittest.TestCase):
    """A8: every non-empty orientation_assert must declare construction_axis.

    Reproduces the log failure where an assert reached verify_orientation with
    no axis to verify against, producing a confusing 'edini_world_axis missing'
    error at commit instead of a clear 'declare the axis' error at validation.
    """

    def test_missing_construction_axis_rejected(self):
        from edini.recipe_validator import validate_recipe
        r = validate_recipe({
            "components": [{"id": "frame", "code": "x"}],
            "orientation_asserts": [
                {"component_id": "frame", "kind": "elongated",
                 "expected_axis": "Y"},
            ],
        })
        self.assertFalse(r["passed"])
        stages = [e["stage"] for e in r["errors"]]
        self.assertIn("A8_MISSING_CONSTRUCTION_AXIS", stages)

    def test_bad_construction_axis_value_rejected(self):
        from edini.recipe_validator import validate_recipe
        r = validate_recipe({
            "components": [{"id": "frame", "code": "x"}],
            "orientation_asserts": [
                {"component_id": "frame", "kind": "elongated",
                 "expected_axis": "Y", "construction_axis": "W"},
            ],
        })
        stages = [e["stage"] for e in r["errors"]]
        self.assertIn("A8_BAD_CONSTRUCTION_AXIS", stages)

    def test_empty_asserts_array_is_explicit_opt_out(self):
        from edini.recipe_validator import validate_recipe
        r = validate_recipe({
            "components": [{"id": "frame", "code": "x"}],
            "orientation_asserts": [],
        })
        self.assertNotIn("A8_MISSING_CONSTRUCTION_AXIS",
                         [e["stage"] for e in r["errors"]])


class TestG1A9HardcodedSizeGuard(unittest.TestCase):
    """A9: hardcoded dimension literals in component code are BLOCKING.

    Reproduces the log failure where editing an asset-level parm did nothing
    because the geometry was baked from a literal (wheelbase = 1.0) rather
    than a channel.
    """

    def test_hardcoded_wheelbase_rejected(self):
        from edini.recipe_validator import validate_recipe
        r = validate_recipe({
            "components": [{
                "id": "frame",
                "code": "wheelbase = 1.0\nnode = hou.pwd()",
            }],
        })
        stages = [e["stage"] for e in r["errors"]]
        self.assertIn("A9_HARDCODED_SIZE", stages)
        self.assertFalse(r["passed"])

    def test_param_declared_size_passes(self):
        from edini.recipe_validator import validate_recipe
        r = validate_recipe({
            "components": [{
                "id": "frame",
                "code": "wheelbase = 1.0\nnode = hou.pwd()",
            }],
            "params": {"wheelbase": {"default": 1.0}},
        })
        self.assertNotIn("A9_HARDCODED_SIZE",
                         [e["stage"] for e in r["errors"]])

    def test_read_list_alias_passes(self):
        from edini.recipe_validator import validate_recipe
        r = validate_recipe({
            "components": [{
                "id": "frame",
                "code": "bb_height = 0.3\nnode = hou.pwd()",
                "reads": ["bb_height"],
            }],
        })
        self.assertNotIn("A9_HARDCODED_SIZE",
                         [e["stage"] for e in r["errors"]])

    def test_loop_counter_not_flagged(self):
        from edini.recipe_validator import validate_recipe
        r = validate_recipe({
            "components": [{
                "id": "frame",
                "code": "for i in range(10):\n    pass\nj = 0",
            }],
        })
        self.assertNotIn("A9_HARDCODED_SIZE",
                         [e["stage"] for e in r["errors"]])

    def test_native_chain_skipped(self):
        from edini.recipe_validator import validate_recipe
        r = validate_recipe({
            "components": [{
                "id": "tube",
                "backend": "native_chain",
                "nodes": [{"type": "tube", "params": {"rad": 0.5}}],
            }],
        })
        self.assertNotIn("A9_HARDCODED_SIZE",
                         [e["stage"] for e in r["errors"]])


class TestG2BakeGate(unittest.TestCase):
    """G2: build_procedural_asset bakes edini_world_axis on every component.

    Reproduces the log failure where a backend forgot to wire the bake (or a
    raw network_mode build bypassed it entirely), leaving the asset without a
    deterministic axis for orientation verification.
    """

    def setUp(self):
        self.prev_hou = sys.modules.get("hou")
        sys.modules["hou"] = _mock_hou

    def tearDown(self):
        if self.prev_hou is not None:
            sys.modules["hou"] = self.prev_hou
        else:
            sys.modules.pop("hou", None)

    def test_builder_bakes_axis_on_every_component(self):
        """A direct-merge component with no explicit construction_axis still
        gets a Y fallback axis baked (decision 6 tier 4), recorded in
        defaulted_axes."""
        from edini import harness
        r = harness.build_procedural_asset({
            "asset_name": "g2_bake",
            "components": [{
                "id": "box_a",
                "code": (
                    "node = hou.pwd()\ngeo = node.geometry()\ngeo.clear()\n"
                    'geo.addAttrib(hou.attribType.Prim, "component_id", "")\n'
                    "for p in [(0,0,0),(1,0,0),(1,1,0),(0,1,0)]:\n"
                    "    pt = geo.createPoint(); pt.setPosition(p)\n"
                    "    poly = geo.createPolygon(); poly.addVertex(pt)\n"
                    '    poly.setAttribValue("component_id", "box_a")\n'
                ),
                "anchors": [],
            }],
        })
        self.assertTrue(r["success"], msg=r.get("error"))
        # Y fallback recorded for the agent to review
        self.assertEqual(r.get("defaulted_axes"), {"box_a": "Y(fallback)"})
        # construction_axis_summary present for every component
        summary = r.get("construction_axis_summary", {})
        self.assertIn("box_a", summary)
        self.assertEqual(summary["box_a"]["method"], "construction")

    def test_explicit_construction_axis_not_in_defaulted(self):
        """When a component declares construction_axis (via an assert), it is
        NOT recorded in defaulted_axes."""
        from edini import harness
        r = harness.build_procedural_asset({
            "asset_name": "g2_explicit",
            "components": [{
                "id": "axle",
                "code": (
                    "node = hou.pwd()\ngeo = node.geometry()\ngeo.clear()\n"
                    'geo.addAttrib(hou.attribType.Prim, "component_id", "")\n'
                    "for p in [(0,0,0),(1,0,0),(1,1,0),(0,1,0)]:\n"
                    "    pt = geo.createPoint(); pt.setPosition(p)\n"
                    "    poly = geo.createPolygon(); poly.addVertex(pt)\n"
                    '    poly.setAttribValue("component_id", "axle")\n'
                ),
                "anchors": [],
            }],
            "orientation_asserts": [
                {"component_id": "axle", "kind": "elongated",
                 "expected_axis": "Y", "construction_axis": "Y"},
            ],
        })
        self.assertTrue(r["success"], msg=r.get("error"))
        # axle had an explicit axis → NOT defaulted
        self.assertNotIn("axle", r.get("defaulted_axes", {}))


class TestG3CommitGate(unittest.TestCase):
    """G3: commit_sandbox refuses unbaked / mis-oriented / unhealthy assets.

    Reproduces the log failure where a raw network_mode build (hand-written
    Python SOP emitting component_id geometry without edini_world_axis) was
    committed as if it were a validated procedural asset.
    """

    def setUp(self):
        self.prev_hou = sys.modules.get("hou")
        sys.modules["hou"] = _mock_hou

    def tearDown(self):
        if self.prev_hou is not None:
            sys.modules["hou"] = self.prev_hou
        else:
            sys.modules.pop("hou", None)

    def _build_raw_sandbox(self, bake_axis: bool):
        """Build a sandbox whose OUT has component_id prims but (optionally)
        no edini_world_axis — a hand-written network_mode build."""
        from edini import harness
        code_lines = [
            "node = hou.pwd()",
            "geo = node.geometry()",
            "geo.clear()",
            'geo.addAttrib(hou.attribType.Prim, "component_id", "")',
        ]
        if bake_axis:
            code_lines.append(
                'geo.addAttrib(hou.attribType.Prim, "edini_world_axis", '
                "(0.0, 0.0, 0.0))")
        code_lines += [
            "for p in [(0,0,0),(1,0,0),(1,1,0),(0,1,0)]:",
            "    pt = geo.createPoint(); pt.setPosition(p)",
            "    poly = geo.createPolygon(); poly.addVertex(pt)",
            '    poly.setAttribValue("component_id", "frame")',
        ]
        if bake_axis:
            code_lines.append(
                '    poly.setAttribValue("edini_world_axis", (0.0, 1.0, 0.0))')
        code = "\n".join(code_lines)
        return harness.run_python_sandbox(code, sandbox_name="raw_test")

    def test_g3a_refuses_raw_sandbox_without_axis(self):
        """A raw network_mode build (component_id prims, no edini_world_axis)
        is refused at G3a."""
        from edini import harness
        sb = self._build_raw_sandbox(bake_axis=False)
        self.assertTrue(sb["success"])
        c = harness.commit_sandbox(
            sb["root_path"], "raw_no_axis", replace_existing=False)
        self.assertFalse(c["success"])
        self.assertFalse(c["committed"])
        self.assertTrue(c.get("refused"))
        self.assertIn("G3_NOT_BAKED", c["error"])

    def test_g3a_passes_when_axis_baked(self):
        """The same build WITH edini_world_axis baked passes G3a."""
        from edini import harness
        sb = self._build_raw_sandbox(bake_axis=True)
        self.assertTrue(sb["success"])
        c = harness.commit_sandbox(
            sb["root_path"], "raw_with_axis", replace_existing=False)
        self.assertTrue(c["success"], msg=c.get("error"))
        self.assertTrue(c["committed"])

    def test_g3_preserves_sandbox_on_failure(self):
        """Decision 12: a refused commit keeps the sandbox (no rename, no
        discard) so the agent can fix and re-commit without rebuilding."""
        from edini import harness
        sb = self._build_raw_sandbox(bake_axis=False)
        root_path = sb["root_path"]
        c = harness.commit_sandbox(
            root_path, "preserve_test", replace_existing=False)
        self.assertFalse(c["committed"])
        # The sandbox root must still exist (not renamed away / discarded).
        self.assertIsNotNone(_mock_hou.node(root_path))


class TestVerificationReceipt(unittest.TestCase):
    """The tamper-evident receipt (spec §5.2). The agent's completion report
    must reference these fields rather than re-counting geometry."""

    def setUp(self):
        self.prev_hou = sys.modules.get("hou")
        sys.modules["hou"] = _mock_hou

    def tearDown(self):
        if self.prev_hou is not None:
            sys.modules["hou"] = self.prev_hou
        else:
            sys.modules.pop("hou", None)

    def _build_and_commit_clean(self, final_name="receipt_final"):
        from edini import harness
        r = harness.build_procedural_asset({
            "asset_name": "receipt",
            "components": [{
                "id": "box_a",
                "code": (
                    "node = hou.pwd()\ngeo = node.geometry()\ngeo.clear()\n"
                    'geo.addAttrib(hou.attribType.Prim, "component_id", "")\n'
                    "for p in [(0,0,0),(1,0,0),(1,1,0),(0,1,0)]:\n"
                    "    pt = geo.createPoint(); pt.setPosition(p)\n"
                    "    poly = geo.createPolygon(); poly.addVertex(pt)\n"
                    '    poly.setAttribValue("component_id", "box_a")\n'
                ),
                "anchors": [],
            }],
        })
        self.assertTrue(r["success"], msg=r.get("error"))
        return harness.commit_sandbox(
            r["root_path"], final_name, replace_existing=False)

    def test_receipt_present_on_success(self):
        c = self._build_and_commit_clean(final_name="rcpt_present")
        self.assertTrue(c["success"])
        self.assertIn("verification_receipt", c)

    def test_receipt_required_fields(self):
        import json
        c = self._build_and_commit_clean(final_name="rcpt_fields")
        rcpt = c["verification_receipt"]
        # Must be JSON-serializable (the tool result is JSON).
        json.dumps(rcpt)
        for field in ("passed", "orientation", "health", "components_detected",
                      "construction_axes_baked", "timestamp"):
            self.assertIn(field, rcpt, msg=f"missing receipt field: {field}")
        for sub in ("passed", "failed", "total", "failures"):
            self.assertIn(sub, rcpt["orientation"])
        for sub in ("overall_ok", "hard_errors_count", "soft_warnings"):
            self.assertIn(sub, rcpt["health"])

    def test_receipt_passed_true_when_clean(self):
        c = self._build_and_commit_clean(final_name="rcpt_clean")
        rcpt = c["verification_receipt"]
        self.assertTrue(rcpt["passed"])
        self.assertEqual(rcpt["health"]["hard_errors_count"], 0)

    def test_receipt_reports_components_detected(self):
        c = self._build_and_commit_clean(final_name="rcpt_comps")
        rcpt = c["verification_receipt"]
        self.assertEqual(rcpt["components_detected"], ["box_a"])


if __name__ == "__main__":
    unittest.main()
