"""Persistent cache for built components.

File-based cache that tracks per-component build results with a manifest
for incremental rebuild decisions. Used by Phase B (component builder)
and consumed by Phase C (assembly engine).
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any


class ComponentCache:
    """File-based cache for per-component build results.

    Each component's result is saved as ``result.json`` inside a
    component-specific directory.  A top-level ``.manifest.json`` tracks
    the status and recipe hash of every cached component so the
    assembler can decide which components are ready to use.
    """

    def __init__(self, cache_root: str) -> None:
        self.root = cache_root
        os.makedirs(cache_root, exist_ok=True)
        self._manifest_path = os.path.join(cache_root, ".manifest.json")

    # ── read / write ───────────────────────────────────────

    def save(
        self, component_id: str, result: dict[str, Any], recipe_hash: str
    ) -> str:
        """Save a component build result.  Returns the cache directory path."""
        comp_dir = os.path.join(self.root, component_id)
        os.makedirs(comp_dir, exist_ok=True)
        result_path = os.path.join(comp_dir, "result.json")
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        self._update_manifest(component_id, result["status"], recipe_hash)
        return comp_dir

    def load(self, component_id: str) -> dict[str, Any] | None:
        """Load cached result, or *None* if not cached."""
        result_path = os.path.join(self.root, component_id, "result.json")
        if not os.path.exists(result_path):
            return None
        with open(result_path, "r", encoding="utf-8") as f:
            return json.load(f)

    # ── manifest ────────────────────────────────────────────

    def manifest(self) -> dict[str, dict[str, Any]]:
        """Return ``{component_id: {status, recipe_hash, ...}}``."""
        if not os.path.exists(self._manifest_path):
            return {}
        with open(self._manifest_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def all_passed(self) -> bool:
        """*True* when every cached component has status ``"passed"``."""
        m = self.manifest()
        return all(v.get("status") == "passed" for v in m.values())

    def passed_count(self) -> int:
        """Return how many cached components are ``"passed"``."""
        return sum(
            1 for v in self.manifest().values() if v.get("status") == "passed"
        )

    # ── internal ────────────────────────────────────────────

    def _update_manifest(
        self, cid: str, status: str, recipe_hash: str
    ) -> None:
        m = self.manifest()
        m[cid] = {"status": status, "recipe_hash": recipe_hash}
        with open(self._manifest_path, "w", encoding="utf-8") as f:
            json.dump(m, f, indent=2, ensure_ascii=False)


# ── utility ─────────────────────────────────────────────────


def recipe_hash(recipe: dict[str, Any]) -> str:
    """Return a stable, short hash of *recipe* for cache invalidation.

    Uses a deterministic JSON serialisation before hashing so that
    key-ordering differences do not produce different hashes.
    """
    raw = json.dumps(recipe, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
