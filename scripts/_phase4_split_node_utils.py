"""One-shot Phase 4 mechanical split of edini/node_utils.py.

Pure refactor: move top-level functions/constants into node_ops / manifest /
geometry_inspect / verify, and reduce node_utils.py to a re-export shim.

Cross-module import edges (verified acyclic before running):
    verify     -> geometry_inspect._vector_to_list
    node_ops   -> manifest._json_safe, manifest_parm_names, _node_parm_inventory

Run from repo root:  py -3 scripts/_phase4_split_node_utils.py
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NU = ROOT / "python3.11libs" / "edini" / "node_utils.py"
PKG = ROOT / "python3.11libs" / "edini"

# ---- target-module membership -------------------------------------------
GEOMETRY_INSPECT = {
    "_vector_to_list", "_geometry_bounds", "inspect_geometry",
    "_component_bounds", "geometry_inventory", "_edge_key",
    "inspect_geometry_health",
}
MANIFEST = {
    "_node_parms_manifest_path", "load_node_parms_manifest", "_attr_or_call",
    "_vector_component_names", "_extract_parm_spec", "_json_safe",
    "_ramp_to_safe_dict", "_correct_vector_components", "_is_multiparm_block",
    "_flatten_parm_templates", "_node_parm_inventory", "_node_type_namespace",
    "generate_node_parms_manifest", "_enrich_manifest_parms",
    "_annotate_menu_options", "_now_iso", "_type_specific_hints", "_access_hints",
    "node_parms", "_resolve_node_type_in_manifest", "_manifest_version_key",
    "_hou_default_version", "_node_parms_live", "manifest_parm_names",
    "manifest_has_parm",
}
VERIFY = {
    "verify_orientation", "verify_parametric", "verify_robust",
    "_relative_path_to_core", "repath_to_relative", "_make_replacer",
    "_declared_anchor_names", "project_status", "_finalize_perturbation",
    "project_finalize", "project_plan",
}
# module-level Assign targets
ASSIGN_GEOM = {"_HEALTH_BLOCKING_CHECKS", "_HEALTH_ADVISORY_CHECKS"}
ASSIGN_MANIFEST = {
    "_NODE_PARMS_MANIFEST_REL", "_CREATE_NODE_PARM_CAP", "_DEFAULT_EXCLUDE_NAMESPACES",
    "_NODE_TYPE_GOTCHA_HINTS",
}
ASSIGN_VERIFY = {"_CH_CALL_RE"}

HEADER = '''"""{desc}

Split out of node_utils.py in the Phase 4 refactor. Re-exported from
``edini.node_utils`` for backwards compatibility.
"""
from __future__ import annotations

import os
import json
import re
import traceback

try:
    import hou
except ImportError:  # offline / unit tests install a mock into sys.modules
    hou = None  # type: ignore[assignment]
from typing import Any

{extra}

'''

DESC = {
    "geometry_inspect": "Geometry read + health inspection (hou wrappers).",
    "manifest": "Parm-template manifest: generation, load, query, H21 version parsing.",
    "verify": ("Orientation / parametric / robust verification + project status "
               "and finalize/plan gates.\n\n"
               "Imports ``_vector_to_list`` from ``.geometry_inspect``."),
    "node_ops": ("Node CRUD, scene queries, script execution, and capture/"
                 "screenshot helpers.\n\n"
                 "Imports ``_json_safe`` / ``manifest_parm_names`` / "
                 "``_node_parm_inventory`` from ``.manifest``."),
}
EXTRA_IMPORT = {
    "geometry_inspect": "",
    "manifest": "",
    "verify": "from .geometry_inspect import _vector_to_list  # noqa: F401",
    "node_ops": ("from .manifest import (  # noqa: F401\n"
                 "    _json_safe,\n"
                 "    manifest_parm_names,\n"
                 "    _node_parm_inventory,\n"
                 ")\n"
                 "from .geometry_inspect import geometry_inventory  # noqa: F401"),
}


def _assign_target_names(node) -> list[str]:
    """Names bound by an Assign / AnnAssign top-level node."""
    names: list[str] = []
    if isinstance(node, ast.Assign):
        for t in node.targets:
            if isinstance(t, ast.Name):
                names.append(t.id)
    elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        names.append(node.target.id)
    return names


def target_of(node) -> str | None:
    """Map an AST top-level node to its target module, or None to drop."""
    if isinstance(node, ast.FunctionDef):
        n = node.name
        if n in GEOMETRY_INSPECT:
            return "geometry_inspect"
        if n in MANIFEST:
            return "manifest"
        if n in VERIFY:
            return "verify"
        return "node_ops"  # residual
    if isinstance(node, (ast.Assign, ast.AnnAssign)):
        for n in _assign_target_names(node):
            if n in ASSIGN_GEOM:
                return "geometry_inspect"
            if n in ASSIGN_MANIFEST:
                return "manifest"
            if n in ASSIGN_VERIFY:
                return "verify"
            if n.startswith("_"):
                return "node_ops"  # residual private constant
        return "node_ops"
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        # header imports are rewritten per-module; carry only the
        # orientation_math import (lives at ~line 3490) into verify.
        if getattr(node, "module", "") == "edini.orientation_math":
            return "verify"
        return None  # stdlib / header import -> drop (rewritten per module)
    if isinstance(node, ast.Try):
        # the `try: import hou` header block -> dropped (each module has its own)
        return None
    if isinstance(node, ast.Expr) and isinstance(getattr(node, "value", None),
                                                 ast.Constant):
        # bare module docstring -> dropped (each module has its own header)
        return None
    return "node_ops"  # any other top-level statement -> residual, flagged below


def main() -> None:
    src = NU.read_text(encoding="utf-8")
    lines = src.splitlines(keepends=False)
    tree = ast.parse(src)

    buckets: dict[str, list[tuple[int, int, str]]] = {
        m: [] for m in ("geometry_inspect", "manifest", "verify", "node_ops")
    }
    warnings: list[str] = []

    for node in tree.body:
        mod = target_of(node)
        start = node.lineno
        # include decorators if present
        if isinstance(node, ast.FunctionDef) and node.decorator_list:
            start = min(d.lineno for d in node.decorator_list)
        end = node.end_lineno
        if mod is None:
            continue
        if not isinstance(node, (ast.FunctionDef, ast.Assign, ast.AnnAssign,
                                 ast.Import, ast.ImportFrom)):
            warnings.append(f"line {start}: non-def/assign/import top-level "
                            f"node {type(node).__name__} -> node_ops (review)")
        buckets[mod].append((start, end, type(node).__name__))

    # write each module
    counts = {}
    for mod, items in buckets.items():
        items.sort()
        body_chunks = []
        for start, end, kind in items:
            chunk = "\n".join(lines[start - 1:end])
            body_chunks.append(chunk)
        body = "\n\n\n".join(body_chunks).rstrip() + "\n"
        header = HEADER.format(desc=DESC[mod], extra=EXTRA_IMPORT[mod])
        out = (PKG / f"{mod}.py")
        out.write_text(header + "\n\n" + body, encoding="utf-8")
        counts[mod] = len(items)
        print(f"wrote {out.relative_to(ROOT)}: {len(items)} top-level defs "
              f"({sum(e - s + 1 for s, e, _ in items)} lines)")

    # rewrite node_utils.py as shim
    shim = '''"""edini.node_utils - re-export shim (Phase 4 split).

Historically a single ~4600-line module. Split by responsibility into:

    node_ops         - node CRUD, scene queries, script exec, capture/screenshot
    manifest         - parm-template manifest generation / load / query
    geometry_inspect - geometry read + health inspection
    verify           - orientation/parametric/robust verification + project gates

This file re-exports the union of all four so every existing import -
``from edini.node_utils import X`` - including the private (underscore) helpers
that builder.py, archetype_emitter.py, and the test suite import by name -
keeps working unchanged. Behaviour is identical to the pre-split module.
"""
from __future__ import annotations

from .node_ops import *          # noqa: F401,F403
from .manifest import *          # noqa: F401,F403
from .geometry_inspect import *  # noqa: F401,F403
from .verify import *            # noqa: F401,F403

# ``from x import *`` deliberately skips underscore-prefixed names, but the
# codebase imports many private helpers from here (e.g. ``_apply_one_param``,
# ``_relative_path_to_core``, ``_CH_CALL_RE``, ``_frame_to_bounds``,
# ``_HEALTH_BLOCKING_CHECKS``). Mirror the full private surface of the four
# submodules so those imports still resolve.
import sys as _sys
from . import node_ops as _node_ops, manifest as _manifest
from . import geometry_inspect as _geometry_inspect, verify as _verify

_shim = _sys.modules[__name__]
for _sub in (_node_ops, _manifest, _geometry_inspect, _verify):
    for _name in dir(_sub):
        if _name.startswith("_") and not _name.startswith("__") \\
                and not hasattr(_shim, _name):
            setattr(_shim, _name, getattr(_sub, _name))
del _sys, _shim, _sub, _name
del _node_ops, _manifest, _geometry_inspect, _verify
'''
    NU.write_text(shim, encoding="utf-8")
    print(f"\nrewrote {NU.relative_toROOT if False else NU.relative_to(ROOT)} as shim")
    if warnings:
        print("\nWARNINGS (review these landed in node_ops intentionally):")
        for w in warnings:
            print("  " + w)
    total = sum(counts.values())
    print(f"\ntotal top-level nodes distributed: {total}")


if __name__ == "__main__":
    main()
