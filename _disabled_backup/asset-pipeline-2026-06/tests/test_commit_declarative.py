"""M4 tests: commit_sandbox behavior for declarative assets (milestone 4).

The milestone-4 change lets a declarative-asset sandbox (produced by
build_asset, stamped with an `edini_asset_source` user datum) commit via
commit_sandbox WITHOUT passing the legacy bake (G3a) / PCA-orientation (G3b)
gates — those gates were built for the old prompt-driven pipeline and would
otherwise reject every declarative asset (which never bakes edini_world_axis
and never PCA-estimates orientation; both by design).

These three behaviors are asserted:

  1. Declarative (stamped) sandbox commits successfully; the verification
     receipt is marked method="declarative".
  2. A raw (unstamped) sandbox with component_id geometry is STILL refused by
     the bake gate — the bypass is opt-in via the build_asset stamp only, so
     the old pipeline's defense is not weakened.
  3. (Health-gate preservation is exercised by the hython end-to-end test in
     test_asset_hython.py, where real geometry exists; the mock geometry here
     is empty so the health gate no-ops.)

These run under the mock hou (like test_asset_builder), asserting the COMMIT
DECISION and receipt shape rather than cooked geometry.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python3.11libs"))
sys.path.insert(0, os.path.dirname(__file__))

from mock_hou import create_mock_hou, MockNode  # noqa: E402


def _inline_table_asset():
    """A minimal declarative table (reused from test_asset_builder)."""
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
                "id": "tabletop", "backend": "native_chain",
                "attach": {"position": "top_center"},
                "nodes": [{"type": "box", "params": {
                    "size": ["top_size", "top_thickness", "top_size"]}}],
            },
            {
                "id": "leg_fl", "backend": "native_chain",
                "attach": {"position": "leg_fl"},
                "nodes": [{"type": "tube", "params": {
                    "rad": ["leg_radius", "leg_radius"], "height": "leg_height"}}],
            },
        ],
    }


class _CommitTestCase(unittest.TestCase):
    """Install a fresh mock hou, import asset_builder + harness against it,
    restore on teardown (same isolation contract as test_asset_builder)."""

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
        from edini import harness  # noqa: E402
        cls.build_asset = staticmethod(asset_builder.build_asset)
        cls.commit_sandbox = staticmethod(harness.commit_sandbox)
        cls.harness = harness

    @classmethod
    def tearDownClass(cls):
        MockNode._hou_ref = cls._prev_hou_ref
        sys.modules["hou"] = cls._prev_hou
        for _mod in list(sys.modules):
            if _mod.startswith("edini"):
                del sys.modules[_mod]
        super().tearDownClass()

    def _make_sandbox(self, name="sandbox"):
        obj = sys.modules["hou"].node("/obj")
        return obj.createNode("geo", name)


# ===================================================================
# declarative asset → commit succeeds (G3a/G3b bypassed)
# ===================================================================

class TestDeclarativeCommit(_CommitTestCase):

    def test_declarative_asset_commits_successfully(self):
        """A build_asset sandbox (stamped) commits without needing baked axes
        or orientation_checks — the legacy gates are bypassed."""
        root = self._make_sandbox("dec1")
        result = self.build_asset(_inline_table_asset(), root.path())
        self.assertTrue(result["success"], result)
        # The stamp that authorizes the bypass is present.
        self.assertIsNotNone(root.userData("edini_asset_source"))
        cr = self.commit_sandbox(root.path(), "mytable", replace_existing=True)
        self.assertTrue(cr["success"], cr)
        self.assertTrue(cr["committed"])
        self.assertEqual(cr["final_path"], "/obj/mytable")

    def test_receipt_marked_declarative(self):
        """The verification receipt records method='declarative' so the agent's
        completion report knows orientation was determined by the builder, not
        by the bake/PCA gates."""
        root = self._make_sandbox("dec2")
        self.build_asset(_inline_table_asset(), root.path())
        cr = self.commit_sandbox(root.path(), "mytable2", replace_existing=True)
        receipt = cr["verification_receipt"]
        self.assertEqual(receipt["method"], "declarative")

    def test_declarative_commit_does_not_require_orientation_checks(self):
        """A declarative asset commits even with NO orientation_checks supplied
        — orientation is deterministic from the skeleton DAG, so the agent never
        has to author expected_axis assertions."""
        root = self._make_sandbox("dec3")
        self.build_asset(_inline_table_asset(), root.path())
        cr = self.commit_sandbox(root.path(), "mytable3", replace_existing=True)
        self.assertTrue(cr["success"], cr)

    def test_receipt_carries_health_and_components_fields(self):
        """A declarative commit receipt always carries the health + components
        sections (the receipt is tamper-evident regardless of method).

        Note: the `passed` flag tracks health hard-errors, which on the mock's
        empty geometry are conservatively non-zero (inspect_geometry_health
        returns success=False). The real `passed=True` outcome is asserted by
        the hython end-to-end test where genuine geometry exists."""
        root = self._make_sandbox("dec4")
        self.build_asset(_inline_table_asset(), root.path())
        cr = self.commit_sandbox(root.path(), "mytable4", replace_existing=True)
        receipt = cr["verification_receipt"]
        self.assertIn("health", receipt)
        self.assertIn("components_detected", receipt)
        self.assertEqual(receipt["method"], "declarative")


# ===================================================================
# old-pipeline (unstamped) sandbox → bake gate still blocks (regression)
# ===================================================================

class TestRawSandboxStillGated(_CommitTestCase):

    def test_unstamped_component_id_sandbox_refused_by_bake_gate(self):
        """A raw network_mode sandbox (no edini_asset_source stamp) emitting
        component_id geometry is STILL refused by G3a — the bypass is opt-in
        via the build_asset stamp only. This is the regression guard: the
        declarative bypass must not weaken the old pipeline's defense."""
        root = self._make_sandbox("raw1")
        gen = root.createNode("python", "gen")
        geo = gen.geometry()
        geo.clear()
        geo.addAttrib(None, "component_id", "")
        geo.createPolygon()  # a prim with component_id, but no baked axis
        # Critically: NO edini_asset_source stamp → full gate stack applies.
        self.assertIsNone(root.userData("edini_asset_source"))
        cr = self.commit_sandbox(root.path(), "rawasset", replace_existing=True)
        self.assertFalse(cr["success"])
        self.assertTrue(cr.get("refused"))
        self.assertIn("G3_NOT_BAKED", cr["error"])

    def test_unstamped_sandbox_receipt_method_is_gated(self):
        """Sanity: the method='gated' default is used when the sandbox is NOT a
        declarative asset. (Reached by committing an unstamped, component-id-free
        sandbox, which passes the bake gate trivially.)"""
        root = self._make_sandbox("raw2")
        # Empty geometry, no component_id → bake gate no-ops, structure gate
        # no-ops, orientation gate no-ops → commits with method='gated'.
        cr = self.commit_sandbox(
            root.path(), "emptypass", replace_existing=True,
            skip_structure_check=True)
        self.assertTrue(cr["success"], cr)
        self.assertEqual(cr["verification_receipt"]["method"], "gated")


if __name__ == "__main__":
    unittest.main()
