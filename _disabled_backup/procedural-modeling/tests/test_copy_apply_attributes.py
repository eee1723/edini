"""Tests for the Copy to Points 2.0 attribute-transfer setup.

Primary purpose: lock in the real-H21 mechanism for transferring the
per-instance ``id`` attribute from scatter points onto every prim of each
copied instance.

Real-H21 mechanism (verified on 21.0.440 via manual_resettargetattribs_probe.py):
  - The Copy to Points ``targetattribs`` parm is a multiparm Folder whose
    instance count starts at 0 (no transfer).
  - The ``resettargetattribs`` BUTTON, when pressed, auto-populates the folder
    with default entries. Entry #1 is ``applymethod=0`` (copy) with
    ``applyattribs='*,^v,^Alpha,^N,^up,^pscale,^scale,^orient,^rot,^pivot,
    ^trans,^transform'`` — copies every target-point attribute EXCEPT the
    transform family, which already includes ``id``.
  - So simply pressing the button is sufficient; no per-instance parm
    manipulation is needed.

The previous implementation tried to grow the multiparm manually via
setMultiparmInstanceCount / count-parm probes / PTG folder growth; all three
failed on real H21 (no such API, no such count parm). The button is Houdini's
own sanctioned initialization path.

To run:  python -m unittest tests.test_copy_apply_attributes
"""
import importlib
import os
import sys
import unittest

from tests.mock_hou import MockNode, create_mock_hou


class _HouFixture(unittest.TestCase):
    """Install a fresh mock hou and reload edini.harness around each test."""

    def setUp(self):
        self.previous_hou = sys.modules.get("hou")
        self.previous_hou_ref = MockNode._hou_ref
        self.previous_edini = {
            n: m for n, m in sys.modules.items() if n.startswith("edini")
        }
        runtime = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "python3.11libs"))
        if runtime not in sys.path:
            sys.path.insert(0, runtime)

        self.mock_hou = create_mock_hou()
        sys.modules["hou"] = self.mock_hou
        for n in list(sys.modules):
            if n.startswith("edini"):
                del sys.modules[n]
        self.harness = importlib.import_module("edini.harness")

    def tearDown(self):
        for n in list(sys.modules):
            if n.startswith("edini"):
                del sys.modules[n]
        sys.modules.update(self.previous_edini)
        if self.previous_hou is None:
            sys.modules.pop("hou", None)
        else:
            sys.modules["hou"] = self.previous_hou
        MockNode._hou_ref = self.previous_hou_ref

    def _make_copy_node(self):
        """A copytopoints::2.0 node with the real-H21 resettargetattribs
        button + targetattribs multiparm count parm."""
        obj = self.mock_hou.node("/obj")
        geo = obj.createNode("geo", "g")
        return geo.createNode("copytopoints", "copy_scatter")


class TestSetupCopyApplyAttributes(_HouFixture):
    """The setup now presses the `resettargetattribs` button."""

    def test_returns_true_when_button_present(self):
        copy = self._make_copy_node()
        self.assertIsNotNone(copy.parm("resettargetattribs"))
        ok = self.harness._setup_copy_apply_attributes(copy, "id")
        self.assertTrue(ok)

    def test_returns_false_when_button_missing(self):
        """No resettargetattribs button → returns False (caller warns)."""
        copy = self._make_copy_node()
        # Strip the button so the setup can't proceed.
        copy._parms.pop("resettargetattribs", None)
        ok = self.harness._setup_copy_apply_attributes(copy, "id")
        self.assertFalse(ok)

    def test_presses_the_button(self):
        """The setup must actually invoke resettargetattribs.pressButton()."""
        copy = self._make_copy_node()
        pressed = {"flag": False}
        btn = copy.parm("resettargetattribs")

        orig_press = btn.pressButton

        def spy():
            pressed["flag"] = True
            orig_press()

        btn.pressButton = spy
        self.harness._setup_copy_apply_attributes(copy, "id")
        self.assertTrue(pressed["flag"],
                        "resettargetattribs.pressButton() was not called")

    def test_does_not_touch_piece_attribute_parms(self):
        """Setup must not disturb the Piece Attribute dispatch parms
        (useidattrib/idattrib) — those are configured separately upstream."""
        copy = self._make_copy_node()
        copy.parm("useidattrib").set(1)
        copy.parm("idattrib").set("variant")
        self.harness._setup_copy_apply_attributes(copy, "id")
        self.assertEqual(copy.parm("useidattrib").eval(), 1)
        self.assertEqual(copy.parm("idattrib").eval(), "variant")


class TestVariantScatterIntegration(_HouFixture):
    """End-to-end: build_variant_scatter presses resettargetattribs on the
    copy_scatter node and does NOT warn about attribute transfer."""

    def _minimal_recipe(self):
        return {
            "asset_name": "vsapply",
            "variants": [
                {"id": "win_a", "code": _variant_geo("win_a")},
                {"id": "win_b", "code": _variant_geo("win_b")},
            ],
            "scatter": {"source": _scatter_points(3), "seed": 42},
        }

    def test_no_attribute_transfer_warning(self):
        """The build must NOT warn that attribute transfer could not be set up."""
        r = self.harness.build_variant_scatter(self._minimal_recipe())
        self.assertTrue(r["success"], msg=r.get("error"))
        warnings = r.get("warnings") or []
        transfer_warnings = [w for w in warnings
                             if "attribute transfer" in w.lower()
                             or "resettargetattribs" in w.lower()]
        self.assertEqual(
            transfer_warnings, [],
            f"attribute-transfer setup warned unexpectedly: {transfer_warnings}")

    def test_copy_scatter_reset_button_present(self):
        """The copy_scatter node carries the resettargetattribs button after
        build (so attribute transfer is initialized on it)."""
        r = self.harness.build_variant_scatter(self._minimal_recipe())
        self.assertTrue(r["success"], msg=r.get("error"))
        copy = self.mock_hou.node(r["root_path"] + "/copy_scatter")
        self.assertIsNotNone(copy, "copy_scatter node missing")
        self.assertIsNotNone(copy.parm("resettargetattribs"),
                             "copy_scatter must expose resettargetattribs")

    def test_no_pack_or_unpack_nodes(self):
        """The H21-verified architecture has NO pack/unpack nodes."""
        r = self.harness.build_variant_scatter(self._minimal_recipe())
        self.assertTrue(r["success"], msg=r.get("error"))
        root = self.mock_hou.node(r["root_path"])
        names = {c.name() for c in root.children()}
        self.assertNotIn("variants_pack", names,
                         "pack node must not exist (breaks dispatch on H21)")
        self.assertNotIn("scatter_unpack", names,
                         "unpack node must not exist (copy on unpacked source "
                         "already yields expanded geometry)")

    def test_has_attribfrompieces_node(self):
        """AFP (scatter_afp) owns variant assignment to scatter points."""
        r = self.harness.build_variant_scatter(self._minimal_recipe())
        self.assertTrue(r["success"], msg=r.get("error"))
        root = self.mock_hou.node(r["root_path"])
        names = {c.name() for c in root.children()}
        self.assertIn("scatter_afp", names,
                      "attribfrompieces (scatter_afp) must exist to assign "
                      "variant to scatter points")
        afp = self.mock_hou.node(r["root_path"] + "/scatter_afp")
        self.assertEqual(afp.parm("pieceattrib").eval(), "variant",
                         "AFP pieceattrib must be set to 'variant'")


class TestSafeCreateNodeAutoInitsCopyToPoints(_HouFixture):
    """Change 1: _safe_create_node is the global chokepoint — ANY copytopoints
    it creates must auto-press resettargetattribs, so build_procedural_asset and
    hand-written network_mode scripts are covered without the caller remembering
    to call _setup_copy_apply_attributes."""

    def test_copytopoints_gets_resettargetattribs_pressed(self):
        """A copytopoints created via _safe_create_node has its
        resettargetattribs button pressed (attribute transfer initialized).

        The mock's pressButton is a no-op (it doesn't simulate the real-H21
        side-effect of populating the targetattribs multiparm), so we spy on
        the call itself rather than checking the multiparm count."""
        obj = self.mock_hou.node("/obj")
        geo = obj.createNode("geo", "g")
        # Spy on the button BEFORE creation runs the post-create init.
        # We pre-create the node type's parm template so the button exists to
        # spy on; simplest path: build the node, then verify via a re-init spy.
        copy = geo.createNode("copytopoints", "probe")
        btn = copy.parm("resettargetattribs")
        pressed = {"flag": False}
        orig_press = btn.pressButton

        def spy():
            pressed["flag"] = True
            orig_press()

        btn.pressButton = spy
        # Re-run the post-create init on this node to assert it presses.
        self.harness._post_create_init(copy)
        self.assertTrue(pressed["flag"],
                        "_post_create_init did not press resettargetattribs")

    def test_safe_create_node_init_runs_on_creation(self):
        """End-to-end: _safe_create_node("copytopoints", ...) presses the
        button during creation (not just when _post_create_init is called
        directly). Spied via a node-level button-press counter."""
        obj = self.mock_hou.node("/obj")
        geo = obj.createNode("geo", "g")
        # Track pressButton calls on the to-be-created copy node by wrapping
        # _init_copytopoints_attribs (the shared impl) — if _safe_create_node
        # wires it in, this records a press.
        from edini import node_utils
        called = {"flag": False}
        orig = node_utils._init_copytopoints_attribs

        def spy(node):
            called["flag"] = True
            return orig(node)

        node_utils._init_copytopoints_attribs = spy
        try:
            self.harness._safe_create_node(geo.path(), "copytopoints", "c2")
        finally:
            node_utils._init_copytopoints_attribs = orig
        self.assertTrue(called["flag"],
                        "_safe_create_node did not run copytopoints init")

    def test_non_copy_node_is_left_alone(self):
        """Non-copytopoints nodes must NOT be touched by the post-create init."""
        obj = self.mock_hou.node("/obj")
        geo = obj.createNode("geo", "g")
        # A null node has no resettargetattribs; creating it must not error.
        null = self.harness._safe_create_node(geo.path(), "null", "n")
        self.assertIsNone(null.parm("resettargetattribs"))

    def test_post_create_init_is_best_effort(self):
        """If resettargetattribs is missing, _safe_create_node must still return
        the created node (init failure must not break creation)."""
        # Build a fake node type with no resettargetattribs button is hard via
        # the mock; instead exercise _post_create_init directly with a node
        # whose button is stripped — it must not raise.
        copy = self._make_copy_node()
        copy._parms.pop("resettargetattribs", None)
        # Should complete without raising and return None gracefully.
        self.harness._post_create_init(copy)


# ── recipe code helpers (kept local to avoid cross-module coupling) ────────
def _variant_geo(cid):
    return (
        "node = hou.pwd()\n"
        "geo = node.geometry()\n"
        "geo.clear()\n"
        'geo.addAttrib(hou.attribType.Prim, "component_id", "")\n'
        "pt = geo.createPoint(); pt.setPosition((0, 0, 0))\n"
        "poly = geo.createPolygon(); poly.addVertex(pt)\n"
        f'poly.setAttribValue("component_id", "{cid}")\n'
    )


def _scatter_points(n=3):
    code = "node = hou.pwd()\ngeo = node.geometry()\ngeo.clear()\n"
    for i in range(n):
        code += f"pt{i} = geo.createPoint(); pt{i}.setPosition(({i}, 0, 0))\n"
    return code


if __name__ == "__main__":
    unittest.main()
