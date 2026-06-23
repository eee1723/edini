"""Recipe library — capture subnet recipes and rebuild them.

A *recipe* is a JSON serialization of a Houdini subnet's internal node network:
which nodes it contains, how they connect, which parameters were changed from
their type defaults (and which the author marked as important), and which
parameters are promoted to the subnet's top level for an LLM to tweak.

The library lives under ``recipes/`` at the project root. Each recipe is a
directory ``recipes/<id>/`` containing a generated ``recipe.json`` (plus the
author-maintained ``.hda`` source). An ``index.json`` summarizes all recipes
for fast ``recipe_list`` queries without touching Houdini.

Design principles (see docs/edini/specs/recipe-library-design.md):
  - The subnet's node Notes (``comment()``) is the ONLY metadata source and is
    mandatory — capture refuses empty/placeholder notes.
  - ``inputs`` reference upstream nodes by *relative name* (not absolute path)
    so a recipe rebuilds identically in any scene.
  - ``changed_params`` are captured by comparing live values against the bundled
    node-parms manifest; ``marked_params`` are declared in Notes ("重要参数").
  - Rebuild topologically orders nodes (dependees first) and runs a built-in
    geometry diff so a broken recipe fails loudly instead of silently.

hou is imported lazily inside the functions that need it; the index/read path
is pure file I/O and works without Houdini.
"""
from __future__ import annotations

import datetime as _dt
import fnmatch
import json
import os
import re
from typing import Any


SCHEMA_VERSION = 1
GENERATOR_VERSION = "0.1.0"

# Node types that are NOT user-authored recipe nodes — they are Houdini's
# internal plumbing or cooked geometry stashes. Capture skips them entirely.
_IGNORED_NODE_TYPES = {"output", "stashed_geo", "subnetconnector"}

# VEX-wrangling node types whose `snippet` is the real payload, not just a param.
_VEX_NODE_TYPES = {"attribwrangle", "pointwrangle", "primwrangle",
                   "vertexwrangle", "detailwrangle"}

# Attrib Wrangle run-over parm name (H21).
_WRANGLE_RUNOVER_PARM = "class"

# Node types that are pure organizational containers — a tree category layer.
# ONLY plain subnets (and the obj-level geo) count as descent targets. Network
# containers (popnet/dopnet/sopnet/ropnet) are NOT here: they are part of a
# recipe's content (a popnet IS the recipe, the same way a sweep node is), so
# capturing a leaf that contains one must grab the whole leaf, not pierce into
# the network container's internals.
_CONTAINER_TYPES = {"subnet", "geo"}

# Network container node types (popnet/dopnet/sopnet/ropnet). These ARE
# descendable in the sense that they hold child networks, but they must NEVER
# be treated as a category layer — they're leaf content. Listed separately so
# the tree walker can short-circuit: a subnet containing one of these is a
# leaf, full stop.
_NETWORK_CONTAINER_TYPES = {"popnet", "dopnet", "sopnet", "ropnet", "copnet",
                            "chopnet", "driver", "shop"}

# Substrings that, if they're the entire (stripped) Notes content, mark it as a
# placeholder rather than real documentation. Capture refuses these.
_PLACEHOLDER_NOTES = {
    "", "notes", "note", "todo", "tbd", "placeholder", "comment",
    "在这里写说明", "待补充", "注释",
}

# Notes field prefixes the parser recognizes (Chinese + English fallback).
# Each maps to a slot in the parsed-notes dict.
_NOTES_PREFIXES = {
    "功能": "function",      "function": "function", "purpose": "function",
    "用途": "use_case",      "use": "use_case",      "usage": "use_case",
    "输入": "inputs_desc",   "input": "inputs_desc",
    "输出": "outputs_desc",  "output": "outputs_desc",
    "重要参数": "marked",    "important": "marked",  "key params": "marked",
    "不要用于": "avoid",     "avoid": "avoid",       "not for": "avoid",
}


# ─────────────────────────────────────────────────────────────────────────────
# Path resolution
# ─────────────────────────────────────────────────────────────────────────────

def _project_root() -> str:
    """Project root: two levels up from this file (edini/ → python3.11libs/ → root)."""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def recipes_root() -> str:
    """Absolute path to the recipes/ directory (created on demand)."""
    root = os.path.join(_project_root(), "recipes")
    os.makedirs(root, exist_ok=True)
    return root


def index_path() -> str:
    return os.path.join(recipes_root(), "index.json")


def recipe_dir(recipe_id: str) -> str:
    return os.path.join(recipes_root(), recipe_id)


def recipe_json_path(recipe_id: str) -> str:
    return os.path.join(recipe_dir(recipe_id), "recipe.json")


def _atomic_write_json(path: str, data: Any) -> None:
    """Write JSON atomically (write temp then rename)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    os.replace(tmp, path)


def _safe_read_json(path: str) -> Any | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Notes parsing & validation
# ─────────────────────────────────────────────────────────────────────────────

def parse_notes(notes: str) -> dict[str, Any]:
    """Parse a subnet's Notes text into structured fields.

    Recognizes line-initial prefixes (功能/用途/输入/输出/重要参数/不要用于, plus
    English fallbacks). Lines without a prefix accumulate into ``function`` (the
    free-text description). Returns a dict with keys:
    ``function, use_case, inputs_desc, outputs_desc, marked (list), avoid``.

    Example Notes::

        功能：沿曲线生成封闭圆柱管材
        用途：车架管、栏杆
        重要参数：radius, segments
        不要用于：变径管
    """
    result: dict[str, Any] = {
        "function": [], "use_case": [], "inputs_desc": [], "outputs_desc": [],
        "marked": [], "avoid": [],
    }
    if not notes:
        return result

    for raw_line in notes.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        matched = False
        # Longest-prefix-first so "重要参数" wins over "输入" etc.
        for prefix in sorted(_NOTES_PREFIXES, key=len, reverse=True):
            if line.startswith(prefix):
                sep = len(prefix)
                # allow ：(fullwidth) or : (ascii) separator
                rest = line[sep:].lstrip(":： ").strip()
                slot = _NOTES_PREFIXES[prefix]
                if slot == "marked":
                    # comma/space separated param names
                    names = [n.strip() for n in re.split(r"[,\s]+", rest) if n.strip()]
                    result["marked"].extend(names)
                else:
                    if rest:
                        result[slot].append(rest)
                matched = True
                break
        if not matched:
            result["function"].append(line)

    # Collapse single-element text lists to ""-joined strings for readability.
    for k in ("function", "use_case", "inputs_desc", "outputs_desc", "avoid"):
        result[k] = "\n".join(result[k]).strip()
    return result


def validate_notes(notes: str) -> tuple[bool, str]:
    """Enforce the mandatory-Notes rules. Returns (ok, reason).

    The hard rules (user requirement: "notes 不可为空且不可删除"):
      1. non-empty
      2. not a known placeholder ("todo"/"notes"/"placeholder"/...)
    A ``功能：`` prefix is recommended and parsed out for the index, but free
    descriptive text (English or otherwise) is also accepted as the function
    description — we don't force a specific format, only that something
    meaningful is written.
    """
    stripped = (notes or "").strip()
    if not stripped:
        return False, "subnet Notes 为空——配方必须有说明。请在节点 Notes 面板填写。"
    if stripped.lower() in _PLACEHOLDER_NOTES:
        return False, (f"subnet Notes 是占位文本（{stripped!r}）——请填写真实功能说明。")
    # Too-short generic notes are likely not real documentation.
    if len(stripped) < 4:
        return False, ("subnet Notes 太短——请填写有意义的功能说明（至少几个字）。")
    return True, ""


# ─────────────────────────────────────────────────────────────────────────────
# Manifest-backed default comparison
# ─────────────────────────────────────────────────────────────────────────────

def _load_manifest() -> dict | None:
    """Load the bundled node-parms manifest (no hou dependency)."""
    try:
        from edini.node_utils import load_node_parms_manifest
        return load_node_parms_manifest()
    except Exception:
        return None


def _manifest_defaults(node_type: str, manifest: dict | None) -> dict[str, Any]:
    """Return {parm_name: default_value} for a node type from the manifest.

    Strips a trailing ``::version`` from the type (e.g. ``sweep::2.0`` →
    ``sweep``) since the manifest keys are unversioned. Returns {} if the
    manifest is missing or the type isn't catalogued.
    """
    if not manifest:
        return {}
    node_types = manifest.get("node_types", {})
    base = node_type.split("::", 1)[0]
    entry = node_types.get(base) or node_types.get(node_type)
    if not isinstance(entry, dict):
        return {}
    defaults: dict[str, Any] = {}
    for p in entry.get("parms", []):
        if isinstance(p, dict) and "name" in p and "default" in p:
            defaults[p["name"]] = p["default"]
    return defaults


def _values_equal(a: Any, b: Any) -> bool:
    """Loose equality for default comparison (float drift, list/tuple)."""
    if a == b:
        return True
    # numeric drift
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        try:
            return abs(float(a) - float(b)) < 1e-9
        except (TypeError, ValueError):
            return False
    # list vs tuple
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        if len(a) != len(b):
            return False
        return all(_values_equal(x, y) for x, y in zip(a, b))
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Subnet capture
# ─────────────────────────────────────────────────────────────────────────────

def _hou():
    """Lazy hou import (only available inside Houdini)."""
    try:
        import hou  # type: ignore
        return hou
    except ImportError:
        return None


def _json_safe(value: Any) -> Any:
    """Coerce a Houdini value (vector/enum) into JSON-serializable form."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    # Vector3/Vector2/Vector4 — duck-typed by indexing.
    if hasattr(value, "__getitem__"):
        try:
            return [_json_safe(value[i]) for i in range(len(value))]
        except Exception:
            pass
    # enum-like objects expose .name()
    name = getattr(value, "name", None)
    if callable(name):
        try:
            return name()
        except Exception:
            pass
    return str(value)


def _collect_subnet_nodes(subnet) -> list[dict[str, Any]]:
    """Walk a subnet's direct children and return per-node capture dicts.

    Only the immediate children are captured as recipe nodes (a recipe is one
    flat layer). Nodes whose type is in ``_IGNORED_NODE_TYPES`` (output,
    stashed_geo, ...) are skipped — they are Houdini plumbing, not user content.
    Each node records its type, relative-name input wiring, and the
    changed/marked/expression param buckets.
    """
    nodes: list[dict[str, Any]] = []
    for child in subnet.children():
        if _is_ignored_node(child):
            continue
        nodes.append({
            "_node": child,
            "name": child.name(),
            "type": child.type().name(),
        })
    # Index by name for relative input resolution (use ALL children, including
    # ignored ones, so a wire FROM an ignored node still resolves — but in
    # practice ignored nodes are sinks so this is defensive).
    by_name = {n["name"]: n["_node"] for n in nodes}

    for n in nodes:
        child = n["_node"]
        # Inputs: index → upstream node NAME (relative), or None. Use
        # inputs() (returns a positional list) for cross-runtime compat —
        # real Houdini also exposes input(i), but the list form is universal.
        # Skip inputs whose source is an ignored node (e.g. an `output` node
        # wired upstream of a real node — rare, but be defensive).
        in_list = child.inputs()
        inputs: dict[str, str | None] = {}
        for i, src in enumerate(in_list):
            if src is not None and src.name() in by_name:
                inputs[str(i)] = src.name()
            else:
                inputs[str(i)] = None
        n["inputs"] = inputs
        del n["_node"]
    return nodes


def _is_ignored_node(node) -> bool:
    """True if the node is Houdini plumbing, not a user-authored recipe node."""
    try:
        t = node.type().name()
    except Exception:
        return False
    return t in _IGNORED_NODE_TYPES


def _classify_parms(node, node_type: str, manifest_defaults: dict[str, Any],
                    marked_set: set[str], manifest_available: bool
                    ) -> tuple[dict, dict, dict, list[str]]:
    """Bucket a node's parms into (changed, marked, expressions, warnings).

    - changed: live value differs from manifest default (skipped if manifest
      is unavailable — then ALL non-default-named parms go in changed, with a
      warning, so capture stays lossless).
    - marked: parm name appears in the Notes "重要参数" list (recorded even if
      equal to default).
    - expressions: parms carrying an expression (hasExpression()).

    For VEX wrangle nodes, the ``snippet`` and ``class`` (run-over) parms are
    deliberately EXCLUDED from changed/marked — they are captured separately
    into ``vex_snippets`` by the caller so the code is searchable and so it is
    not treated as an ordinary value on rebuild.
    """
    changed: dict[str, Any] = {}
    marked: dict[str, Any] = {}
    expressions: dict[str, Any] = {}
    warnings: list[str] = []

    is_vex = node_type in _VEX_NODE_TYPES
    # On wrangle nodes, snippet+class are extracted elsewhere; skip them here.
    vex_skip = _WRANGLE_RUNOVER_PARM if is_vex else None

    for p in node.parms():
        pname = p.name()
        if _is_auto_param(pname):
            continue
        if pname == "snippet":
            # snippet is always special-cased on wrangles; even on non-wrangle
            # nodes it's a code blob, keep it out of the generic param stream.
            continue
        if vex_skip and pname == vex_skip:
            continue
        try:
            live = p.eval()
        except Exception:
            continue
        live_safe = _json_safe(live)

        # Expression capture.
        try:
            if hasattr(p, "hasExpression") and p.hasExpression():
                expressions[pname] = p.expression()
        except Exception:
            pass

        is_marked = pname in marked_set
        if is_marked:
            marked[pname] = live_safe

        if manifest_available:
            default = manifest_defaults.get(pname)
            if default is not None and not _values_equal(live_safe, default):
                changed[pname] = live_safe
            elif default is None:
                # parm not in manifest — treat as changed if non-trivial
                # (record so capture is lossless; LLM can still see it).
                changed[pname] = live_safe
        else:
            # No manifest: record everything except marked (already recorded).
            changed[pname] = live_safe

    if not manifest_available:
        warnings.append(f"manifest unavailable — all parms recorded for '{node.name()}'")
    return changed, marked, expressions, warnings


def _extract_vex_snippets(subnet_or_nodes, hou_nodes: dict[str, Any]) -> list[dict]:
    """Pull VEX snippets from wrangle nodes inside a captured recipe.

    Returns a list of ``{node, code, runover}`` dicts, one per wrangle node
    that has a non-empty snippet. ``runover`` is the integer class index
    (0=detail,1=point,2=prim,3=vertex) or None if unreadable. The snippet text
    is searchable via recipe_list since it's folded into the recipe function.
    """
    snippets: list[dict] = []
    if isinstance(subnet_or_nodes, list):
        # We were passed the recipe-node specs (already captured dicts).
        items = subnet_or_nodes
    else:
        items = None
    if items is not None:
        for spec in items:
            if spec.get("type") not in _VEX_NODE_TYPES:
                continue
            node = hou_nodes.get(spec["name"])
            if node is None:
                continue
            code, runover = _read_wrangle(node)
            if code:
                snippets.append({"node": spec["name"], "code": code,
                                 "runover": runover})
    return snippets


def _read_wrangle(node) -> tuple[str, Any]:
    """Read a wrangle node's snippet + run-over class. Returns (code, runover)."""
    code, runover = "", None
    try:
        p = node.parm("snippet")
        if p is not None:
            code = p.eval() or ""
    except Exception:
        pass
    try:
        cp = node.parm(_WRANGLE_RUNOVER_PARM)
        if cp is not None:
            runover = cp.eval()
    except Exception:
        pass
    return code, runover


def _is_auto_param(name: str) -> bool:
    """True for Houdini auto-managed params (time/frame/seed/cache/display)."""
    for pat in ("time", "frame", "*frame*", "*seed*", "*cache*", "display*"):
        if fnmatch.fnmatch(name, pat):
            return True
    return False


def _capture_exposed_parms(subnet, marked_set: set[str]) -> tuple[list[dict], list[str]]:
    """Find subnet-top-level parms that are channel-referenced to inner nodes.

    A promoted parm on a subnet typically references an inner node's parm via a
    ``ch("../inner/parm")`` expression. We detect promotion by checking each
    subnet parm: if it has an expression referencing a child node, record it.
    Returns (exposed_parms, warnings).
    """
    exposed: list[dict] = []
    warnings: list[str] = []
    child_names = {c.name() for c in subnet.children()}

    for p in subnet.parms():
        if _is_auto_param(p.name()):
            continue
        try:
            has_expr = hasattr(p, "hasExpression") and p.hasExpression()
        except Exception:
            has_expr = False
        if not has_expr:
            continue
        try:
            expr = p.expression() or ""
        except Exception:
            expr = ""
        # Look for ch("../childname/parm") or ch("childname/parm") references.
        m = re.search(r'ch\s*\(\s*["\'](?:\.\./)*([^/\s"\']+)/([^/\s"\']+)["\']', expr)
        if not m:
            continue
        inner_name, inner_parm = m.group(1), m.group(2)
        if inner_name not in child_names:
            continue
        entry = {
            "subnet_parm": p.name(),
            "target": f"{inner_name}.{inner_parm}",
            "default": _json_safe(_eval_or_none(p)),
        }
        # Range from the parm template if available.
        try:
            tmpl = p.parmTemplate()
            mn = getattr(tmpl, "minValue", None)
            mx = getattr(tmpl, "maxValue", None)
            if callable(mn):
                mn = mn()
            if callable(mx):
                mx = mx()
            if mn is not None:
                entry["min"] = _json_safe(mn)
            if mx is not None:
                entry["max"] = _json_safe(mx)
        except Exception:
            pass
        exposed.append(entry)
    return exposed, warnings


def _eval_or_none(p) -> Any:
    try:
        return p.eval()
    except Exception:
        return None


def _capture_io_ports(subnet) -> tuple[list[dict], list[dict]]:
    """Read subnet input/output connector descriptions."""
    inputs: list[dict] = []
    outputs: list[dict] = []
    connectors = getattr(subnet, "inputConnectors", None)
    input_count = len(connectors()) if callable(connectors) else len(subnet.inputs())
    for i in range(input_count):
        inputs.append({"index": i, "desc": ""})
    out_connectors = getattr(subnet, "outputConnectors", None)
    output_count = len(out_connectors()) if callable(out_connectors) and out_connectors else 1
    for i in range(output_count):
        outputs.append({"index": i, "desc": ""})
    return inputs, outputs


# ─────────────────────────────────────────────────────────────────────────────
# Tree navigation (for recipe_capture_tree)
# ─────────────────────────────────────────────────────────────────────────────

def _is_container_subnet(node) -> bool:
    """A subnet is a *container* (pure organization) iff all its non-ignored
    children are themselves pure organizational subnets (subnet/geo), with no
    work nodes AND no network containers (popnet/dopnet/...).

    The user-built tree uses nested subnets as a category taxonomy:
    sopnet1/Procedural_Modeling/Base_Sweep — the first two are containers,
    Base_Sweep (whose children include curve/sweep SOPs) is a leaf. A subnet
    that holds a popnet is ALSO a leaf: the popnet IS the recipe's content.
    """
    try:
        kids = [c for c in node.children() if not _is_ignored_node(c)]
    except Exception:
        return False
    if not kids:
        return False  # empty subnet — neither container nor leaf
    for c in kids:
        try:
            t = c.type().name()
        except Exception:
            return False
        if t in _NETWORK_CONTAINER_TYPES:
            return False  # network container = leaf content, not a category
        if t not in _CONTAINER_TYPES:
            return False
    return True


def _is_leaf_subnet(node) -> bool:
    """A subnet is a *leaf* (a real recipe) iff it has at least one non-ignored
    child that is a work node OR a network container (popnet/dopnet/...).

    A network container counts as "work" because it IS the recipe — capturing
    the subnet must grab it as one node, not pierce into its internals.
    """
    try:
        kids = [c for c in node.children() if not _is_ignored_node(c)]
    except Exception:
        return False
    if not kids:
        return False
    for c in kids:
        try:
            t = c.type().name()
        except Exception:
            continue
        if t in _NETWORK_CONTAINER_TYPES:
            return True  # popnet/dopnet present → this subnet is a leaf
        if t not in _CONTAINER_TYPES:
            return True  # SOP/work node present → leaf
    return False


def _tree_path_from(root_name: str, leaf_node) -> list[str]:
    """Walk up from a leaf subnet's PARENT to ``root_name`` (inclusive),
    collecting ancestor names = the category path. The leaf itself is excluded.

    e.g. for leaf Base_Sweep under /obj/sopnet1/Procedural_Modeling/Base_Sweep
    with root_name='sopnet1', returns ['sopnet1', 'Procedural_Modeling'].
    """
    names: list[str] = []
    # Start at the leaf's parent — the leaf name is NOT part of tree_path.
    try:
        cur = leaf_node.parent()
    except Exception:
        cur = None
    while cur is not None:
        try:
            nm = cur.name()
        except Exception:
            break
        names.append(nm)
        if nm == root_name:
            break
        try:
            cur = cur.parent()
        except Exception:
            break
    names.reverse()
    return names


def _find_leaf_subnets(root, root_name: str) -> list[tuple[Any, list[str]]]:
    """Recursively collect (leaf_node, tree_path) pairs under ``root``.

    Walks the tree: container subnets are descended into; leaf subnets are
    harvested; empty subnets are skipped. The root itself is never harvested
    (it's the entry point).
    """
    leaves: list[tuple[Any, list[str]]] = []

    def walk(node, in_root_subtree: bool):
        try:
            kids = [c for c in node.children() if not _is_ignored_node(c)]
        except Exception:
            return
        for c in kids:
            try:
                t = c.type().name()
            except Exception:
                continue
            if t not in _CONTAINER_TYPES:
                continue  # not a subnet at all — skip
            if _is_leaf_subnet(c):
                path = _tree_path_from(root_name, c)
                leaves.append((c, path))
            elif _is_container_subnet(c):
                walk(c, in_root_subtree=True)
            # else: empty subnet — skip silently

    walk(root, in_root_subtree=False)
    return leaves


def _make_recipe_id(tree_path: list[str]) -> str:
    """Build a non-colliding recipe_id from the category path + leaf name.

    ['sopnet1', 'Procedural_Modeling'] → 'Procedural_Modeling.Base_Sweep' would
    be wrong (leaf name is in tree_path). Actually tree_path EXCLUDES the leaf,
    so id = '.'.join(tree_path[1:]) + '.' + leaf_name. But tree_path INCLUDES
    the root (sopnet1) which we drop for readability.
    """
    # tree_path = [root_name, cat1, cat2, ...] (leaf excluded, root included)
    # id = cat1.cat2.<leaf>
    if not tree_path:
        return "unnamed"
    # Drop the root (first element = the entry node like 'sopnet1').
    parts = tree_path[1:]
    if not parts:
        # tree_path had only the root → leaf IS the root child path; use last
        return tree_path[-1]
    return ".".join(parts)


def _auto_notes(leaf_node, tree_path: list[str], recipe_id: str) -> str:
    """Generate default Notes for a leaf with no user-written Notes.

    Keeps capture_tree unblocked while still producing searchable metadata.
    Format: tree path + leaf name + the inner node types, so recipe_list can
    match on both category and node vocabulary.
    """
    leaf_name = leaf_node.name()
    try:
        kids = [c for c in leaf_node.children() if not _is_ignored_node(c)]
        types = []
        for c in kids:
            try:
                types.append(c.type().name())
            except Exception:
                pass
    except Exception:
        types = []
    type_str = ", ".join(types) if types else "(no nodes)"
    cat_str = " / ".join(tree_path[1:]) if len(tree_path) > 1 else leaf_name
    return (f"功能：{cat_str} / {leaf_name}（节点: {type_str}）\n"
            f"（auto-generated notes — 请手动补充用途/重要参数）")


# ─────────────────────────────────────────────────────────────────────────────
# Capture
# ─────────────────────────────────────────────────────────────────────────────

def recipe_capture(subnet_path: str, recipe_id: str | None = None,
                   tree_path: list[str] | None = None,
                   allow_auto_notes: bool = False) -> dict[str, Any]:
    """Capture a subnet's internal network into a recipe JSON.

    Reads the subnet at ``subnet_path``, walks children, classifies params,
    extracts VEX snippets (if any wrangle nodes), and writes
    ``recipes/<id>/recipe.json`` + rebuilds the index.

    ``recipe_id`` overrides the id (defaults to the subnet's name). Used by
    recipe_capture_tree to give each leaf a tree-path-based unique id.
    ``tree_path`` is stored verbatim as the category breadcrumb.
    ``allow_auto_notes``: when True, an empty/placeholder Notes is replaced
    with auto-generated metadata instead of failing capture (used by
    capture_tree so a fresh tree can be ingested wholesale).

    Returns ``{success, recipe_id, warnings}`` on success or
    ``{success: False, error}`` on failure.
    """
    hou = _hou()
    if hou is None:
        return {"success": False, "error": "Houdini (hou module) unavailable."}

    subnet = hou.node(subnet_path)
    if subnet is None:
        return {"success": False, "error": f"subnet not found: {subnet_path}"}

    notes = subnet.comment() or ""
    auto_notes_used = False
    ok, reason = validate_notes(notes)
    if not ok:
        if not allow_auto_notes:
            return {"success": False, "error": reason}
        # Auto-generate so capture_tree isn't blocked by empty Notes.
        notes = _auto_notes(subnet, tree_path or [], recipe_id or subnet.name())
        auto_notes_used = True

    parsed = parse_notes(notes)
    marked_set = set(parsed["marked"])
    rid = recipe_id or subnet.name()
    all_warnings: list[str] = []
    if auto_notes_used:
        all_warnings.append("auto-generated notes (subnet Notes was empty/placeholder)")

    manifest = _load_manifest()
    manifest_available = manifest is not None

    raw_nodes = _collect_subnet_nodes(subnet)
    recipe_nodes: list[dict[str, Any]] = []
    # Map node-name → live hou node, for VEX snippet extraction after the loop.
    hou_nodes: dict[str, Any] = {}
    for rn in raw_nodes:
        child = hou.node(f"{subnet_path}/{rn['name']}")
        hou_nodes[rn["name"]] = child
        defaults = _manifest_defaults(rn["type"], manifest)
        changed, marked, expressions, warns = _classify_parms(
            child, rn["type"], defaults, marked_set, manifest_available)
        all_warnings.extend(warns)
        recipe_nodes.append({
            "name": rn["name"],
            "type": rn["type"],
            "inputs": rn["inputs"],
            "changed_params": changed,
            "marked_params": marked,
            "expressions": expressions,
        })

    # VEX snippets: pull from every wrangle node with a non-empty snippet.
    vex_snippets = _extract_vex_snippets(recipe_nodes, hou_nodes)
    kind = "vex" if vex_snippets else "network"

    exposed, exp_warns = _capture_exposed_parms(subnet, marked_set)
    all_warnings.extend(exp_warns)
    inputs, outputs = _capture_io_ports(subnet)

    category = _infer_category(parsed["function"], rid)

    recipe = {
        "schema_version": SCHEMA_VERSION,
        "id": rid,
        "name": subnet.name(),
        "notes": notes,
        "function": parsed["function"],
        "use_case": parsed["use_case"],
        "avoid": parsed["avoid"],
        "category": category,
        "kind": kind,
        "tree_path": tree_path or [],
        "vex_snippets": vex_snippets,
        "nodes": recipe_nodes,
        "exposed_parms": exposed,
        "inputs": inputs,
        "outputs": outputs,
        "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "generator_version": GENERATOR_VERSION,
    }

    d = recipe_dir(rid)
    os.makedirs(d, exist_ok=True)
    _atomic_write_json(recipe_json_path(rid), recipe)
    rebuild_index()

    return {
        "success": True,
        "recipe_id": rid,
        "node_count": len(recipe_nodes),
        "exposed_parm_count": len(exposed),
        "kind": kind,
        "warnings": all_warnings,
    }


def recipe_capture_tree(root_path: str) -> dict[str, Any]:
    """Recursively capture every leaf subnet under ``root_path``.

    Walks the tree: container subnets are descended into; leaf subnets (those
    whose non-ignored children include real SOP nodes) are captured. Each leaf
    gets a tree-path-based recipe_id (e.g. 'Procedural_Modeling.Base_Sweep') so
    same-named leaves in different branches never collide. Empty Notes are
    auto-filled rather than blocking capture.

    Returns ``{success, captured_count, skipped_count, captured[], skipped[]}``.
    """
    hou = _hou()
    if hou is None:
        return {"success": False, "error": "Houdini (hou module) unavailable."}

    root = hou.node(root_path)
    if root is None:
        return {"success": False, "error": f"root not found: {root_path}"}

    root_name = root.name()
    leaves = _find_leaf_subnets(root, root_name)

    captured: list[dict] = []
    skipped: list[dict] = []
    for leaf_node, leaf_path in leaves:
        # leaf_path includes the root name as first element; leaf name is the
        # last segment of the leaf's own path. Build recipe_id from the
        # category portion (root dropped) + leaf name.
        leaf_name = leaf_node.name()
        rid = _make_recipe_id(leaf_path) + "." + leaf_name if leaf_path[1:] else leaf_name
        result = recipe_capture(
            leaf_node.path(), recipe_id=rid, tree_path=leaf_path,
            allow_auto_notes=True)
        if result.get("success"):
            captured.append(result)
        else:
            skipped.append({"recipe_id": rid, "path": leaf_node.path(),
                            "error": result.get("error", "unknown")})

    return {
        "success": True,
        "root": root_path,
        "captured_count": len(captured),
        "skipped_count": len(skipped),
        "captured": captured,
        "skipped": skipped,
    }


def _infer_category(function_text: str, recipe_id: str) -> str:
    """Heuristic category from the function description + id keywords."""
    text = f"{function_text} {recipe_id}".lower()
    rules = [
        (("管", "tube", "pipe", "圆柱", "沿曲线"), "tube"),
        (("挤出", "extrude", "截面", "beam"), "extrude"),
        (("散布", "copy", "scatter", "重复", "ctp", "复制"), "copy"),
        (("布尔", "boolean", "切割", "cut"), "boolean"),
        (("法线", "normal", "fuse", "clean", "清理"), "postprocess"),
        (("变形", "transform", "lattice", "bend", "twist"), "deform"),
    ]
    for keywords, cat in rules:
        if any(k in text for k in keywords):
            return cat
    return "misc"


# ─────────────────────────────────────────────────────────────────────────────
# Index
# ─────────────────────────────────────────────────────────────────────────────

def rebuild_index() -> dict[str, Any]:
    """Scan all recipes/*/recipe.json and (re)write index.json.

    Pure file I/O (no hou). Returns the index dict.
    """
    root = recipes_root()
    entries: list[dict[str, Any]] = []
    for entry in sorted(os.listdir(root)):
        child = os.path.join(root, entry)
        if not os.path.isdir(child):
            continue
        rj = _safe_read_json(os.path.join(child, "recipe.json"))
        if not isinstance(rj, dict) or rj.get("id") != entry:
            continue
        entries.append({
            "id": rj["id"],
            "category": rj.get("category", "misc"),
            "kind": rj.get("kind", "network"),
            "function": rj.get("function", ""),
            "avoid": rj.get("avoid", ""),
            "tree_path": rj.get("tree_path", []),
            "vex_snippet_count": len(rj.get("vex_snippets", [])),
            "node_count": len(rj.get("nodes", [])),
            "inputs": len(rj.get("inputs", [])),
            "outputs": len(rj.get("outputs", [])),
            "exposed_parms": [e.get("subnet_parm", "") for e in rj.get("exposed_parms", [])],
            "generated_at": rj.get("generated_at", ""),
        })
    index = {
        "schema_version": SCHEMA_VERSION,
        "rebuilt_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "entry_count": len(entries),
        "entries": entries,
    }
    _atomic_write_json(index_path(), index)
    return index


def recipe_list(query: str = "", category: str = "", kind: str = "") -> dict[str, Any]:
    """Query the recipe index by keyword and/or category and/or kind.

    Pure file I/O — safe to call without Houdini. Matching is case-insensitive
    substring over the function text + id + category + tree_path components +
    exposed parm names. An empty query returns all entries.
    ``kind`` filters to 'network' or 'vex'.
    """
    index = _safe_read_json(index_path())
    if not isinstance(index, dict):
        # No index yet — rebuild and retry once.
        index = rebuild_index()
    entries = index.get("entries", []) if isinstance(index, dict) else []

    q = (query or "").strip().lower()
    cat = (category or "").strip().lower()
    knd = (kind or "").strip().lower()
    matches = []
    for e in entries:
        if cat and e.get("category", "").lower() != cat:
            continue
        if knd and e.get("kind", "network").lower() != knd:
            continue
        if q:
            haystack = " ".join([
                e.get("id", ""), e.get("function", ""),
                e.get("category", ""), e.get("kind", ""),
                " ".join(e.get("tree_path", [])),
                " ".join(e.get("exposed_parms", [])),
            ]).lower()
            if q not in haystack:
                continue
        matches.append({
            "id": e["id"],
            "category": e.get("category", "misc"),
            "kind": e.get("kind", "network"),
            "summary": e.get("function", "").splitlines()[0]
                       if e.get("function") else "",
            "tree_path": e.get("tree_path", []),
            "inputs": e.get("inputs", 0),
            "outputs": e.get("outputs", 0),
            "exposed_parms": e.get("exposed_parms", []),
            "vex_snippet_count": e.get("vex_snippet_count", 0),
            "node_count": e.get("node_count", 0),
        })
    return {
        "success": True,
        "total": len(entries),
        "matched": len(matches),
        "matches": matches,
    }


def recipe_read(recipe_id: str) -> dict[str, Any]:
    """Read a full recipe JSON by id. Pure file I/O."""
    path = recipe_json_path(recipe_id)
    data = _safe_read_json(path)
    if data is None:
        return {"success": False, "error": f"recipe not found: {recipe_id}"}
    return {"success": True, "recipe": data}


# ─────────────────────────────────────────────────────────────────────────────
# Rebuild
# ─────────────────────────────────────────────────────────────────────────────

def _topo_sort(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Topologically sort recipe nodes so dependees are created first.

    A node depends on another if its ``inputs`` reference that node's name.
    Uses Kahn's algorithm; cycles fall back to original order with a warning.
    """
    by_name = {n["name"]: n for n in nodes}
    # Build dependency edges: for each node, the set of upstream names it needs.
    deps: dict[str, set[str]] = {}
    for n in nodes:
        needed = set()
        for src in n.get("inputs", {}).values():
            if src and src in by_name:
                needed.add(src)
        deps[n["name"]] = needed

    ordered: list[str] = []
    remaining = set(by_name)
    while remaining:
        # Nodes whose deps are all already ordered.
        ready = [name for name in remaining if deps[name] <= set(ordered)]
        if not ready:
            # cycle — emit remaining in original order
            ready = sorted(remaining, key=lambda nm: nodes.index(by_name[nm]))
        for name in ready:
            ordered.append(name)
            remaining.discard(name)
    return [by_name[name] for name in ordered]


def _set_parm_safe(node, pname: str, value: Any) -> bool:
    """Set a parm, returning False if the parm doesn't exist."""
    p = node.parm(pname)
    if p is None:
        return False
    try:
        p.set(value)
        return True
    except Exception:
        return False


def _set_expression_safe(node, pname: str, expr: str) -> bool:
    p = node.parm(pname)
    if p is None:
        return False
    try:
        p.setExpression(expr)
        return True
    except Exception:
        return False


def recipe_rebuild(recipe_id: str, parent_path: str,
                   name: str | None = None, overrides: dict | None = None
                   ) -> dict[str, Any]:
    """Rebuild a subnet's node network at ``parent_path`` from its recipe.

    Creates a subnet container, topologically creates inner nodes, sets their
    changed/marked params, wires inputs, applies exposed-parm overrides, then
    runs a built-in verification (node/param/input count vs recipe).
    Returns ``{success, rebuilt_path, node_count, verify}`` or
    ``{success: False, error}``.
    """
    hou = _hou()
    if hou is None:
        return {"success": False, "error": "Houdini (hou module) unavailable."}

    recipe_data = _safe_read_json(recipe_json_path(recipe_id))
    if not isinstance(recipe_data, dict):
        return {"success": False, "error": f"recipe not found: {recipe_id}"}

    parent = hou.node(parent_path)
    if parent is None:
        return {"success": False, "error": f"parent not found: {parent_path}"}

    container_name = name or f"{recipe_id}_1"
    container = parent.createNode("subnet", container_name)
    container.setComment(recipe_data.get("notes", ""))
    warnings: list[str] = []

    # Create inner nodes in topological order.
    ordered = _topo_sort(recipe_data.get("nodes", []))
    created: dict[str, Any] = {}
    for spec in ordered:
        try:
            inner = container.createNode(spec["type"], spec["name"])
        except Exception as e:
            return {"success": False,
                    "error": f"failed to create node '{spec['name']}' ({spec['type']}): {e}",
                    "rebuilt_path": container.path()}
        created[spec["name"]] = inner
        # Apply params: changed first, then marked (marked may restate a changed
        # value — fine, idempotent).
        missing: list[str] = []
        for pname, val in spec.get("changed_params", {}).items():
            if not _set_parm_safe(inner, pname, val):
                missing.append(pname)
        for pname, val in spec.get("marked_params", {}).items():
            _set_parm_safe(inner, pname, val)
        for pname, expr in spec.get("expressions", {}).items():
            if not _set_expression_safe(inner, pname, expr):
                missing.append(f"{pname}(expr)")
        if missing:
            warnings.append(f"{spec['name']}: parm not found: {missing}")

    # Restore VEX snippets (snippet + run-over class) on wrangle nodes. These
    # were deliberately excluded from changed_params during capture so the code
    # stays searchable; here we write them back to the rebuilt nodes.
    for snip in recipe_data.get("vex_snippets", []):
        node_name = snip.get("node")
        code = snip.get("code", "")
        runover = snip.get("runover")
        target = created.get(node_name)
        if target is None:
            warnings.append(f"vex snippet: node '{node_name}' missing")
            continue
        if not _set_parm_safe(target, "snippet", code):
            warnings.append(f"{node_name}.snippet: parm missing")
        if runover is not None:
            _set_parm_safe(target, _WRANGLE_RUNOVER_PARM, runover)

    # Wire inputs (now that all inner nodes exist).
    for spec in ordered:
        inner = created[spec["name"]]
        for idx_str, src_name in spec.get("inputs", {}).items():
            if src_name is None:
                continue
            upstream = created.get(src_name)
            if upstream is None:
                warnings.append(f"{spec['name']}: missing upstream '{src_name}'")
                continue
            try:
                inner.setInput(int(idx_str), upstream)
            except Exception as e:
                warnings.append(f"{spec['name']}.input[{idx_str}]: {e}")

    # Exposed-parm overrides: re-create the channel reference then set.
    if overrides:
        for exp in recipe_data.get("exposed_parms", []):
            sp = exp.get("subnet_parm")
            if sp and sp in overrides:
                target = exp.get("target", "")
                if "." in target:
                    inner_name, inner_parm = target.split(".", 1)
                    inner_node = created.get(inner_name)
                    if inner_node is not None:
                        _set_parm_safe(inner_node, inner_parm, overrides[sp])

    # Layout so the new network isn't a pile-up.
    try:
        container.layoutChildren()
    except Exception:
        pass

    # ── Built-in verification ──
    verify = _verify_rebuild(container, recipe_data, created)

    return {
        "success": verify["ok"],
        "rebuilt_path": container.path(),
        "node_count": len(created),
        "verify": verify,
        "warnings": warnings,
    }


def _verify_rebuild(container, recipe: dict, created: dict) -> dict[str, Any]:
    """Compare rebuilt container against the recipe: node count, param presence.

    A structural check (does each recipe node exist, are its changed params set
    to the recorded values). Geometry-level diff is intentionally omitted here
    — that belongs to the post-build inspect_health/verify_asset shared tools.
    Returns {ok, checked_nodes, param_checks, mismatches}.
    """
    mismatches: list[str] = []
    checked_nodes = 0
    param_checks = 0
    for spec in recipe.get("nodes", []):
        node = created.get(spec["name"])
        if node is None:
            mismatches.append(f"node missing: {spec['name']}")
            continue
        checked_nodes += 1
        for pname, expected in spec.get("changed_params", {}).items():
            p = node.parm(pname)
            if p is None:
                mismatches.append(f"{spec['name']}.{pname}: parm missing")
                continue
            param_checks += 1
            actual = _json_safe(_eval_or_none(p))
            if not _values_equal(actual, expected):
                mismatches.append(
                    f"{spec['name']}.{pname}: expected {expected!r}, got {actual!r}")
    return {
        "ok": len(mismatches) == 0,
        "checked_nodes": checked_nodes,
        "param_checks": param_checks,
        "mismatches": mismatches,
    }
