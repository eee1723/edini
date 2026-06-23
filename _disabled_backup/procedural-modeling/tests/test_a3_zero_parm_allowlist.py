"""Tests for the A3 zero-parm SOP allowlist (Batch 4 / L5 fix).

L5 regression: the road_bike session saw `houdini_search_nodes("clean")`
return the `clean` SOP, but A3 validation rejected `clean` as "not found in
catalog" because the auto-generated catalog (built from parmTemplates()) can
omit zero-parm SOPs. The fix downgrades known zero-parm SOPs (clean/normal/
facet/...) from BLOCKING to WARNING so legitimate postprocess steps aren't
rejected on a catalog gap.
"""
from __future__ import annotations

from unittest import mock

from edini import recipe_validator as rv


def _fake_catalog(known_types: set[str]) -> mock.MagicMock:
    """A catalog mock that knows only the given node types."""
    cat = mock.MagicMock(name="catalog")
    cat.has_node_type.side_effect = lambda t: t in known_types
    cat.resolve_alias.side_effect = lambda t: t
    cat._data = {"houdini_version": "21.0.440"}
    return cat


class TestA3ZeroParmAllowlist:
    def test_unknown_sop_still_blocks(self):
        """A genuinely unknown node type is still a BLOCKING A3 error."""
        cat = _fake_catalog(known_types={"box", "tube"})
        recipe = {"components": [
            {"id": "c", "backend": "native_chain", "nodes": [
                {"type": "totally_made_up_sop"}]}]}
        errors = rv._validate_a3_node_types(recipe, cat)
        blocking = [e for e in errors if e["severity"] == "BLOCKING"]
        assert len(blocking) == 1
        assert "totally_made_up_sop" in blocking[0]["message"]

    def test_clean_postprocess_downgraded_to_warning(self):
        """THE L5 fix: 'clean' missing from catalog → WARNING, not BLOCKING."""
        cat = _fake_catalog(known_types=set())  # catalog knows nothing
        recipe = {"components": [], "postprocess": [{"type": "clean"}]}
        errors = rv._validate_a3_node_types(recipe, cat)
        blocking = [e for e in errors if e["severity"] == "BLOCKING"]
        warnings = [e for e in errors if e["severity"] == "WARNING"]
        assert blocking == [], "clean should not block"
        assert len(warnings) == 1
        assert "clean" in warnings[0]["message"]
        assert "catalog gap" in warnings[0]["message"]

    def test_normal_and_facet_also_allowed(self):
        cat = _fake_catalog(known_types=set())
        recipe = {"postprocess": [
            {"type": "normal"}, {"type": "facet"}]}
        errors = rv._validate_a3_node_types(recipe, cat)
        assert all(e["severity"] == "WARNING" for e in errors)
        assert len(errors) == 2

    def test_known_sop_in_catalog_produces_no_error(self):
        """When the catalog DOES know the SOP, no error or warning."""
        cat = _fake_catalog(known_types={"clean", "box"})
        recipe = {"components": [
            {"id": "c", "backend": "native_chain", "nodes": [
                {"type": "box"}]}],
            "postprocess": [{"type": "clean"}]}
        errors = rv._validate_a3_node_types(recipe, cat)
        assert errors == []

    def test_none_catalog_returns_empty(self):
        recipe = {"components": [], "postprocess": [{"type": "clean"}]}
        assert rv._validate_a3_node_types(recipe, None) == []

    def test_validate_recipe_passes_with_clean_missing(self):
        """End-to-end: a recipe with a clean postprocess that the catalog
        doesn't know still passes validation (warning, not failure)."""
        cat = _fake_catalog(known_types={"box"})
        recipe = {
            "asset_name": "t",
            "components": [
                {"id": "c", "backend": "native_chain", "nodes": [
                    {"type": "box", "params": {"sizex": 1}}]}],
            "postprocess": [{"type": "clean"}],
        }
        # validate_recipe takes a catalog *path*, not a catalog object, so we
        # exercise the A3 function directly (it's the unit under test) plus
        # confirm the severity classification the aggregator relies on.
        errors = rv._validate_a3_node_types(recipe, cat)
        assert not any(e["severity"] == "BLOCKING" for e in errors)
