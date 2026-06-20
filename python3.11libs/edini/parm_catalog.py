"""Auto-generated parameter catalog from the installed Houdini version.

Scans all SOP types on first run, caches to parm-catalog.json.
Phase A validation uses this catalog as ground truth for parm-name
and node-type checks — no cook required.
"""

import json
import os
import hou
from typing import Any

CATALOG_PATH = os.path.join(
    os.path.dirname(__file__), "data", "parm-catalog.json"
)

# Known aliases for node types that changed names between Houdini versions.
NODE_ALIASES = {
    "transform": "xform",
    "polybevel": "polybevel::3.0",
}


class ParmCatalog:
    """Read-only catalog of Houdini SOP parm definitions."""

    def __init__(self, data: dict[str, Any]):
        self._data = data
        self._sops: dict[str, dict] = data.get("Sop", {})

    # ── lookup ──────────────────────────────────────────────

    def has_node_type(self, node_type: str) -> bool:
        """True if node_type is a known SOP type (canonical name)."""
        return node_type in self._sops

    def resolve_alias(self, node_type: str) -> str:
        """If node_type is a known alias, return the canonical name."""
        return NODE_ALIASES.get(node_type, node_type)

    def get_parms(self, node_type: str) -> dict[str, Any] | None:
        """Return {parm_name: ParmDef} for a SOP type, or None."""
        entry = self._sops.get(node_type)
        return entry.get("parms") if entry else None

    def parm_names(self, node_type: str) -> set[str]:
        """Return the set of valid parm names for a SOP type."""
        parms = self.get_parms(node_type)
        return set(parms.keys()) if parms else set()

    # ── validation ──────────────────────────────────────────

    def validate_parm(self, node_type: str, name: str, value: Any) -> str | None:
        """Return an error string if parm doesn't exist or value is invalid, else None.

        Checks:
        1. Parm exists on this node type.
        2. For menu parms, the value is a valid menu item string.
        """
        parms = self.get_parms(node_type)
        if parms is None:
            return f"node type '{node_type}' not in catalog"
        if name not in parms:
            closest = _closest_match(name, parms.keys())
            hint = f" (did you mean '{closest}'?)" if closest else ""
            return f"parm '{name}' not found on {node_type}{hint}"
        pdef = parms[name]
        if pdef.get("type") == "Menu" and isinstance(value, str):
            items = set(pdef.get("menu_items") or [])
            if value not in items:
                return (
                    f"parm '{name}' on {node_type}: invalid menu item "
                    f"'{value}'. Valid: {sorted(items)}"
                )
        return None

    # ── serialization ───────────────────────────────────────

    @staticmethod
    def load(path: str = CATALOG_PATH) -> "ParmCatalog":
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"Parm catalog not found at {path}. "
                f"Call dump_parm_catalog() first."
            )
        with open(path, "r", encoding="utf-8") as f:
            return ParmCatalog(json.load(f))

    @staticmethod
    def generate_catalog() -> dict[str, Any]:
        """Scan installed Houdini for all SOP types and their parm definitions."""
        sops: dict[str, dict] = {}
        for cat_name, cat in hou.nodeTypeCategories().items():
            if cat_name != "Sop":
                continue
            for nt in cat.nodeTypes().values():
                entry = {"internal_name": nt.name(), "parms": {}}
                # nt.parmTemplates() returns the factory defaults —
                # the same metadata houdini_node_parms returned previously.
                for pt in nt.parmTemplates():
                    # Skip folder/separator/button templates — they have no value
                    ptype = pt.type().name
                    if ptype in ("FolderSet", "Folder", "Separator", "ButtonStrip",
                                 "Label", "Button"):
                        continue
                    try:
                        default_val = pt.defaultValue()
                        # Some parm types return methods or other non-serializable objects
                        if callable(default_val) and not isinstance(default_val, (int, float, str, bool, list, tuple, dict)):
                            default_val = None
                    except (AttributeError, TypeError):
                        default_val = None
                    # Convert to JSON-serializable
                    try:
                        json.dumps(default_val)
                    except (TypeError, ValueError):
                        default_val = repr(default_val) if default_val is not None else None
                    pdef = {
                        "type": ptype,
                        "label": pt.label(),
                        "default": default_val,
                    }
                    if ptype == "Menu":
                        # Collect menu item labels
                        pdef["menu_items"] = [
                            mi.label() for mi in (pt.menuItems() or [])
                        ]
                    entry["parms"][pt.name()] = pdef
                sops[nt.name()] = entry
        return {
            "houdini_version": hou.applicationVersionString(),
            "Sop": sops,
        }


def _closest_match(name: str, candidates: set[str]) -> str | None:
    """Return the candidate with the smallest Levenshtein distance to name."""
    best, best_dist = None, float("inf")
    for c in candidates:
        d = _levenshtein(name, c)
        if d < best_dist:
            best, best_dist = c, d
    return best if best_dist <= 3 else None


def _levenshtein(a: str, b: str) -> int:
    m, n = len(a), len(b)
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev, dp[0] = dp[0], i
        for j in range(1, n + 1):
            prev, dp[j] = dp[j], min(
                dp[j] + 1, dp[j - 1] + 1, prev + (a[i - 1] != b[j - 1])
            )
    return dp[n]
