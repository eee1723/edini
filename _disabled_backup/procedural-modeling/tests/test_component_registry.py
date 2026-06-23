"""Tests for edini.component_registry — semantic component references.

Batch 3 (语义组件库) acceptance tests. The core regression being fixed:

  BEFORE: two wheels = two copy-pasted components (rim_front/rim_rear) with
  identical VEX, doubling the recipe and defeating Copy-to-Points.
  AFTER:  one {"component":"wheel","instances":[...]} reference expands to a
  single component carrying N anchors → real CTP stamping.

These are pure-data tests (no `hou`): they verify expansion logic and that
the built-in component JSON files are valid and loadable.
"""
from __future__ import annotations

import json
import os

import pytest

from edini import component_registry as cr


# ── Catalog loading ───────────────────────────────────────────────────────

class TestCatalog:
    def test_components_dir_exists(self):
        assert os.path.isdir(cr.components_dir())

    def test_builtin_components_present(self):
        names = cr.list_components()
        # The seed set for the bicycle validation case
        for expected in ("wheel", "tube", "hub", "spoke", "chain_link", "bolt"):
            assert expected in names, f"missing built-in component: {expected}"

    def test_get_component_returns_deep_copy(self):
        a = cr.get_component("wheel")
        b = cr.get_component("wheel")
        assert a is not b, "get_component must return independent copies"
        a["geometry"]["backend"] = "MUTATED"
        assert cr.get_component("wheel")["geometry"]["backend"] != "MUTATED"

    def test_unknown_component_returns_none(self):
        assert cr.get_component("nonexistent_xyz") is None

    def test_reload_catalog_picks_up_changes(self, tmp_path, monkeypatch):
        # Point the registry at a temp dir, add a file, reload, verify seen.
        monkeypatch.setattr(cr, "_COMPONENTS_DIR", str(tmp_path))
        cr.reload_catalog()
        assert cr.list_components() == []
        (tmp_path / "custom.json").write_text(
            json.dumps({"name": "custom", "geometry": {"backend": "native_chain"}}),
            encoding="utf-8")
        cr.reload_catalog()
        assert "custom" in cr.list_components()
        # restore for other tests
        cr.reload_catalog()


# ── Built-in component validity ───────────────────────────────────────────

class TestBuiltinDefinitions:
    """Every shipped component JSON must be well-formed and self-consistent."""

    @pytest.mark.parametrize("name", [
        "wheel", "tube", "hub", "spoke", "chain_link", "bolt",
    ])
    def test_definition_has_required_fields(self, name):
        spec = cr.get_component(name)
        assert spec is not None, f"{name} not loadable"
        assert "geometry" in spec, f"{name} missing 'geometry'"
        geo = spec["geometry"]
        assert "backend" in geo, f"{name} geometry missing 'backend'"
        # backend-specific geometry fields
        if geo["backend"] == "native_chain":
            assert "nodes" in geo and geo["nodes"], f"{name} native_chain needs nodes"
        elif geo["backend"] == "vex_skeleton":
            assert "code" in geo, f"{name} vex_skeleton needs code"
            assert "form_node" in geo, f"{name} vex_skeleton needs form_node"

    @pytest.mark.parametrize("name", [
        "wheel", "tube", "hub", "spoke", "chain_link", "bolt",
    ])
    def test_component_id_is_parameterised(self, name):
        """native_chain templates must tag via $component_id placeholder so
        each instance gets its own id (not a hardcoded name)."""
        spec = cr.get_component(name)
        if spec["geometry"]["backend"] != "native_chain":
            pytest.skip("only native_chain uses snippet tagging")
        blob = json.dumps(spec)
        assert "$component_id" in blob, (
            f"{name}: snippet must use $component_id placeholder, "
            f"not a hardcoded name")


# ── Expansion: the P3 regression ──────────────────────────────────────────

class TestResolve:
    def test_no_refs_unchanged(self):
        recipe = {"components": [
            {"id": "frame", "backend": "native_chain", "nodes": []}]}
        out = cr.resolve(recipe)
        assert out["components"] == recipe["components"]
        # and it's a copy, not the same object
        assert out is not recipe

    def test_uses_component_refs_detects_refs(self):
        assert cr.uses_component_refs({"components": [
            {"component": "wheel", "instances": []}]}) is True
        assert cr.uses_component_refs({"components": [
            {"id": "frame", "backend": "native_chain"}]}) is False

    def test_single_component_expands_to_inline(self):
        recipe = {"components": [
            {"component": "hub", "id": "my_hub"}]}
        out = cr.resolve(recipe)
        assert len(out["components"]) == 1
        comp = out["components"][0]
        assert comp["id"] == "my_hub"
        assert comp["backend"] == "native_chain"
        assert "nodes" in comp  # geometry inlined
        # No leftover "component" key
        assert "component" not in comp

    def test_two_wheels_become_one_component_with_two_anchors(self):
        """THE regression: front+rear wheel = ONE component, TWO anchors."""
        recipe = {"components": [
            {"component": "wheel", "id": "wheels", "instances": [
                {"position_expr": [0.5, 0.3, 0], "component_id": "wheel_front"},
                {"position_expr": [-0.5, 0.3, 0], "component_id": "wheel_rear"},
            ]}]}
        out = cr.resolve(recipe)
        # ONE component (not two) — the whole point of CTP
        assert len(out["components"]) == 1
        comp = out["components"][0]
        assert comp["id"] == "wheels"
        assert comp["backend"] == "vex_skeleton"
        # TWO anchors → harness stamps twice via Copy-to-Points
        assert len(comp["anchors"]) == 2
        ids = [a["component_id"] for a in comp["anchors"]]
        assert ids == ["wheel_front", "wheel_rear"]
        # The geometry is shared (single code block), not duplicated
        assert "code" in comp and "section_code" in comp

    def test_unknown_component_raises(self):
        recipe = {"components": [
            {"component": "does_not_exist"}]}
        with pytest.raises(KeyError, match="unknown component"):
            cr.resolve(recipe)

    def test_instance_missing_component_id_raises(self):
        recipe = {"components": [
            {"component": "wheel", "id": "wheels", "instances": [
                {"position_expr": [0, 0, 0]}]}]}  # no component_id
        with pytest.raises(ValueError, match="component_id"):
            cr.resolve(recipe)

    def test_mixed_refs_and_inline(self):
        """A recipe can mix component refs and hand-written components."""
        recipe = {"components": [
            {"component": "wheel", "id": "wheels", "instances": [
                {"position_expr": [0.5, 0.3, 0], "component_id": "wf"}]},
            {"id": "frame", "backend": "native_chain", "nodes": []},
        ]}
        out = cr.resolve(recipe)
        assert len(out["components"]) == 2
        assert out["components"][0]["id"] == "wheels"
        assert out["components"][1]["id"] == "frame"

    def test_anchor_optional_fields_passed_through(self):
        recipe = {"components": [
            {"component": "spoke", "id": "spokes", "instances": [
                {"position_expr": [0, 0, 0], "component_id": "s0",
                 "orient_expr": [0, 0, 0, 1], "pscale_expr": 1.0}]}]}
        out = cr.resolve(recipe)
        anc = out["components"][0]["anchors"][0]
        assert anc["orient_expr"] == [0, 0, 0, 1]
        assert anc["pscale_expr"] == 1.0

    def test_component_id_substituted_in_single_use(self):
        """A single (non-instanced) component ref should bake its component_id
        into the snippet."""
        recipe = {"components": [
            {"component": "hub", "id": "front_hub", "component_id": "front_hub"}]}
        out = cr.resolve(recipe)
        blob = json.dumps(out["components"][0])
        assert "$component_id" not in blob, "placeholder not substituted"
        assert "front_hub" in blob

    def test_param_schema_present_on_wheel(self):
        spec = cr.get_component("wheel")
        assert "param_schema" in spec
        assert "rim_r" in spec["param_schema"]
        # defaults and ranges are present
        ps = spec["param_schema"]["rim_r"]
        assert "default" in ps and "min" in ps and "max" in ps
        assert ps["min"] < ps["default"] < ps["max"]
