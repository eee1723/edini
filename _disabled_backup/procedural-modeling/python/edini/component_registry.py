"""Semantic component registry — `{"component": "wheel"}` references in recipes.

Why this exists
---------------
Before this module, every component in a recipe had to inline its full
``code``/``nodes``. Two wheels were two copy-pasted components
(``rim_front``/``rim_rear``) with identical VEX — even though the harness
already supported Copy-to-Points stamping via the ``anchors`` field. The
copy-paste happened because there was no *named* component to reference.

This module closes that gap. A recipe may now write::

    {"component": "wheel", "id": "wheels", "instances": [
        {"position_expr": [...], "component_id": "wheel_front"},
        {"position_expr": [...], "component_id": "wheel_rear"},
    ]}

``resolve(recipe)`` expands such references into the standard inline
component shape (``id``/``backend``/``code|nodes``/``anchors``) **before**
A1-A9 validation runs. The expanded form is what the build loop sees, so:

* one wheel definition, N instances → real Copy-to-Points (not N copies)
* the recipe stays small and declarative
* existing inline components are untouched (full backward compatibility)

Component definitions live as JSON in ``python3.11libs/edini/components/``.
Each defines ``backend``, geometry (``code``/``nodes``), a ``param_schema``
(the params it accepts, with defaults/ranges), and a ``reads`` list. The
``component_id`` is parameterised so each instance can be individually tagged.
"""
from __future__ import annotations

import copy
import json
import os
from typing import Any

# ── Location of the built-in component JSON files ─────────────────────────
_COMPONENTS_DIR = os.path.join(os.path.dirname(__file__), "components")


def components_dir() -> str:
    """Directory holding built-in component definitions."""
    return _COMPONENTS_DIR


# lru_cache would persist across tests and hide edits to the JSON files
# during development; a module-level dict with a public invalidator is clearer.
_catalog_cache: dict[str, dict] | None = None


def reload_catalog() -> None:
    """Force the catalog to be re-read from disk on next access."""
    global _catalog_cache
    _catalog_cache = None


def _load_catalog() -> dict[str, dict]:
    """Read every ``*.json`` in the components dir into a name→definition map."""
    global _catalog_cache
    if _catalog_cache is not None:
        return _catalog_cache
    catalog: dict[str, dict] = {}
    if not os.path.isdir(_COMPONENTS_DIR):
        _catalog_cache = catalog
        return catalog
    for fname in sorted(os.listdir(_COMPONENTS_DIR)):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(_COMPONENTS_DIR, fname)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                spec = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
        name = spec.get("name") or os.path.splitext(fname)[0]
        catalog[name] = spec
    _catalog_cache = catalog
    return catalog


def list_components() -> list[str]:
    """Names of all available built-in components."""
    return sorted(_load_catalog().keys())


def get_component(name: str) -> dict | None:
    """Return a deep copy of a component definition, or None if unknown."""
    spec = _load_catalog().get(name)
    return copy.deepcopy(spec) if spec is not None else None


# ── Expansion ─────────────────────────────────────────────────────────────

def _parametrize_component_id(spec: dict, cid: str) -> dict:
    """Replace the placeholder ``$component_id`` / ``__CID__`` in a component
    spec's geometry with a concrete component id.

    Templates use ``s@component_id = "$component_id";`` so each instance can
    carry its own id. We substitute the literal string everywhere it appears
    in code/snippets. For native_chain, the wrangle snippet is rewritten.
    """
    PLACEHOLDER = "$component_id"
    if PLACEHOLDER not in json.dumps(spec):
        return spec

    def _sub(obj: Any) -> Any:
        if isinstance(obj, str):
            return obj.replace(PLACEHOLDER, cid)
        if isinstance(obj, list):
            return [_sub(x) for x in obj]
        if isinstance(obj, dict):
            return {k: _sub(v) for k, v in obj.items()}
        return obj

    return _sub(spec)


def _expand_one(ref: dict) -> list[dict]:
    """Expand a single ``{"component": ...}`` reference into one or more
    inline component specs.

    * With ``instances``: produces ONE component carrying N anchors (so the
      build stamps it N times via Copy-to-Points) — the efficient path.
    * Without ``instances``: produces a single inline component.
    """
    name = ref.get("component")
    spec = get_component(name)
    if spec is None:
        raise KeyError(
            f"unknown component '{name}'. Available: {list_components()}"
        )

    base_id = ref.get("id") or name
    geometry = spec.get("geometry") or {}
    backend = geometry.get("backend", spec.get("backend", "native_chain"))

    # Pull geometry fields verbatim from the template.
    inline: dict[str, Any] = {
        "id": base_id,
        "backend": backend,
    }
    for field in ("code", "section_code", "nodes", "form_node", "reads",
                  "construction_axis"):
        if field in geometry:
            inline[field] = copy.deepcopy(geometry[field])

    instances = ref.get("instances")
    if instances:
        # Multi-instance: emit ONE component with anchors for CTP stamping.
        anchors = []
        for inst in instances:
            if "component_id" not in inst:
                raise ValueError(
                    f"component '{base_id}' instance missing 'component_id'"
                )
            anchor: dict[str, Any] = {"component_id": inst["component_id"]}
            if "position_expr" in inst:
                anchor["position_expr"] = inst["position_expr"]
            if "position" in inst:
                anchor["position"] = inst["position"]
            if "orient_expr" in inst:
                anchor["orient_expr"] = inst["orient_expr"]
            if "pscale_expr" in inst:
                anchor["pscale_expr"] = inst["pscale_expr"]
            anchors.append(anchor)
        inline["anchors"] = anchors
        # The geometry's $component_id placeholder is left as-is for the
        # template stream; the idfix SOP (built by _stamp_component) writes
        # the per-instance component_id onto stamped copies. But the template
        # still needs *a* tag so direct-cook works — use the base id.
        inline = _parametrize_component_id(inline, base_id)
        return [inline]

    # Single instance (no anchors): just parameterise the id.
    inline = _parametrize_component_id(inline, ref.get("component_id", base_id))
    return [inline]


def resolve(recipe: dict) -> dict:
    """Return a copy of ``recipe`` with all ``{"component": ...}`` references
    expanded into inline component specs.

    Pure data transform — no Houdini. Safe to run before validation. Recipes
    with no component references are returned (deep-copied) unchanged.
    """
    if not isinstance(recipe, dict):
        return recipe
    out = copy.deepcopy(recipe)
    components = out.get("components")
    if not isinstance(components, list):
        return out
    expanded: list[dict] = []
    for comp in components:
        if isinstance(comp, dict) and "component" in comp:
            expanded.extend(_expand_one(comp))
        else:
            expanded.append(copy.deepcopy(comp))
    out["components"] = expanded
    return out


def uses_component_refs(recipe: dict) -> bool:
    """True if the recipe contains any ``{"component": ...}`` reference."""
    comps = recipe.get("components") if isinstance(recipe, dict) else None
    if not isinstance(comps, list):
        return False
    return any(
        isinstance(c, dict) and "component" in c for c in comps
    )
