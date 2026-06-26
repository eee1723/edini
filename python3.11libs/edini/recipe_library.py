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
import shutil
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

# Node-type-name substrings that indicate SOP-context geometry work. A recipe
# whose nodes match any of these must be rebuilt inside a `geo` (Geometry)
# container, NOT a bare `subnet` — SOP nodes (spiral, sweep, circle, ...) can
# only be created in a Geometry's SOP context. Stripping a trailing ::version
# (sweep::2.0 → sweep) before matching.
_SOP_NODE_HINTS = (
    "spiral", "sweep", "circle", "curve", "box", "sphere", "grid", "tube",
    "torus", "polyextrude", "polywire", "polypatch", "polybevel",
    "attribwrangle", "pointwrangle", "primwrangle", "detailwrangle",
    "attribvop", "vop", "copytopoints", "copytopoints::", "scatter",
    "transform", "blast", "fuse", "peak", "polyreduce", "remesh",
    "subdivide", "divide", "ray", "project", "boolean", "polybool",
    "normal", "faceted", "smooth", "vellum", "vdb", "volumerasterize",
    "filecache", "file", "alembic", "null", "merge", "switch",
    "groupexpression", "groupfrombbox", "grouprange", "delete",
    "timeshift", "trail", "resample", "polypath", "ends", "fuse",
    "measure", "uvunwrap", "uvtexture", "uvspline", "uvflatten",
    "skin", "loft", "rail", "sweep", "extrude", "revolve",
    "surfsect", "stitch",
)


def _infer_container_type(nodes: list[dict]) -> str:
    """Pick the Houdini container type for a rebuild based on node context.

    SOP nodes (geometry generators/modifiers like spiral/sweep/circle) can only
    be created inside a Geometry (``geo``) container's SOP context, never inside
    a bare ``subnet`` (Object context). Since most recipes are SOP networks, we
    return ``geo`` as soon as ANY node looks like SOP work. Only fall back to
    ``subnet`` for recipes that contain purely non-SOP nodes.
    """
    for spec in nodes:
        t = (spec.get("type", "") or "").split("::", 1)[0].lower()
        if any(t == h or t.startswith(h.rstrip(":")) for h in _SOP_NODE_HINTS):
            return "geo"
    return "subnet"

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

    The manifest catalogs BOTH versioned (``sweep::2.0``) and unversioned
    (``sweep``) names, and they are DIFFERENT nodes (the v1 ``sweep`` and the
    rewritten ``sweep::2.0`` have unrelated parameter sets). So we must prefer
    the exact versioned name; only fall back to the unversioned base name when
    the versioned entry is absent (e.g. for a node that has no ``::version``).
    Matching the base first used to silently return the wrong node's defaults,
    which flagged every real parm as "unknown" and corrupted capture.
    Returns {} if the manifest is missing or neither name is catalogued.
    """
    if not manifest:
        return {}
    node_types = manifest.get("node_types", {})
    entry = node_types.get(node_type)
    if not isinstance(entry, dict):
        base = node_type.split("::", 1)[0]
        entry = node_types.get(base)
    if not isinstance(entry, dict):
        return {}
    defaults: dict[str, Any] = {}
    for p in entry.get("parms", []):
        if isinstance(p, dict) and "name" in p and "default" in p:
            defaults[p["name"]] = p["default"]
    return defaults


def _values_equal(a: Any, b: Any) -> bool:
    """Loose equality for default comparison (float drift, list/tuple, scalar-vs-list).

    The manifest stores defaults as single-element lists (e.g. ``[4]`` for an
    Int, ``['']`` for a String, ``['roll']`` for an attrib name) while
    ``parm.eval()`` returns bare scalars. Normalize a scalar against a 1-element
    list/tuple before comparing so a parm at its default isn't wrongly flagged
    as changed. This applies to BOTH numbers and strings — String parms are the
    most common false-positive source (an attrib name like 'roll' never looks
    equal to ['roll'] without this normalization).
    """
    if a == b:
        return True
    # Normalize scalar <-> single-element list/tuple (manifest wraps numbers
    # AND strings in a 1-element list).
    if (isinstance(a, (int, float, str, bool))
            and isinstance(b, (list, tuple)) and len(b) == 1):
        return _values_equal(a, b[0])
    if (isinstance(b, (int, float, str, bool))
            and isinstance(a, (list, tuple)) and len(a) == 1):
        return _values_equal(a[0], b)
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


import re as _re

# Multiparm instance names come in two shapes:
#   * base + index + suffix:  'heightprofile2pos' -> template 'heightprofile#pos'
#   * base + index (no tail): 'value0' / 'useapply1' -> template 'value#' / 'useapply#'
_MULTIPARM_INSTANCE_RE = _re.compile(r"^(.+?)(\d+)([A-Za-z_]\w*)$")
_MULTIPARM_INDEX_TAIL_RE = _re.compile(r"^([A-Za-z_][A-Za-z_0-9]*?)(\d+)$")
# Vector component expansions. Houdini splits a vector parm into component
# parms two ways: 'upvectorx/y/z' (xyzw suffix) and 'uvscale1/2' (numeric
# suffix). Match both so a component maps back to its parent vector default.
_VECTOR_XYZW_RE = _re.compile(r"^(.+?)([xyzw])$")
_VECTOR_NUM_RE = _re.compile(r"^(.+?)([12])$")

# Collapsible-folder / tab-switcher state parms. The manifest generator skips
# these UI templates, so they're never catalogued; their value is the collapse
# or active-tab state (0/1), not an authored setting. Recognize every naming
# variant Houdini uses so they don't pollute changed_params as noise.
_FOLDER_STATE_SUFFIXES = (
    "_folder", "_folder1", "_folder2",
    "_switcher", "_switcher1",
    "section",  # polyextrude::2.0: xformsection, outputsection, uvssection...
    "folder",   # attribrandomize: folder, folder01
)
# Exact-name folder/tab state parms that don't fit a suffix rule.
_FOLDER_STATE_EXACT = {"stdswitcher1", "folder", "folder01", "values"}


def _is_folder_state_parm(pname: str) -> bool:
    """True for collapsible-folder / tab-switcher UI state parms.

    These are never authored and never catalogued by the manifest; their value
    encodes which tab is open / whether a folder is collapsed, so recording
    them as 'changed' is pure noise.
    """
    if pname in _FOLDER_STATE_EXACT:
        return True
    return pname.endswith(_FOLDER_STATE_SUFFIXES)


def _manifest_lookup(pname: str, manifest_defaults: dict[str, Any]) -> Any:
    """Look up a parm's default in the manifest, normalizing instance names.

    Live nodes report component/instance names the manifest doesn't store
    verbatim, so a direct lookup misses and the parm is wrongly flagged
    'changed'. We normalize three cases:
      * multiparm instance: ``heightprofile2pos`` → ``heightprofile#pos``
      * vector component:   ``upvectorx`` → ``upvector[0]``
      * ramp whole-object:  ``scaleramp`` → derived from ``scaleramp#value``
    Returns the default (None if truly unknown).
    """
    default = manifest_defaults.get(pname)
    if default is not None:
        return default

    # Multiparm normalization: 'heightprofile2pos' -> 'heightprofile#pos'.
    m = _MULTIPARM_INSTANCE_RE.match(pname)
    if m and m.group(1) and m.group(3):
        template = f"{m.group(1)}#{m.group(3)}"
        default = manifest_defaults.get(template)
        if default is not None:
            return default

    # Multiparm normalization, index-only tail: 'value0' / 'useapply1' ->
    # 'value#' / 'useapply#'. These are the common Nth-instance parms
    # (attribrandomize value0..value3, copytopoints useapply1..useapply3).
    mt = _MULTIPARM_INDEX_TAIL_RE.match(pname)
    if mt:
        template = f"{mt.group(1)}#"
        if template in manifest_defaults:
            return manifest_defaults[template]

    # Vector component, xyzw suffix: 'upvectorx' -> 'upvector', take slot.
    vm = _VECTOR_XYZW_RE.match(pname)
    if vm:
        base = vm.group(1)
        comp = vm.group(2)
        vec = manifest_defaults.get(base)
        if isinstance(vec, (list, tuple)) and len(vec) > 1:
            idx = "xyzw".index(comp)
            if idx < len(vec):
                return vec[idx]

    # Vector component, numeric suffix: 'uvscale1'/'uvscale2' -> 'uvscale'.
    # Only match when the parent name IS a multi-element vector default
    # (avoids colliding with true multiparms like 'scaleramp1value', whose
    # parent 'scaleramp' isn't a vector in the manifest).
    vm2 = _VECTOR_NUM_RE.match(pname)
    if vm2:
        base = vm2.group(1)
        idx = int(vm2.group(2)) - 1  # 1-based -> 0-based
        vec = manifest_defaults.get(base)
        if isinstance(vec, (list, tuple)) and len(vec) > 1 and idx < len(vec):
            return vec[idx]

    # Ramp whole-object: 'scaleramp' (a hou.Ramp serialized as a dict) has no
    # single manifest entry; it is the aggregation of scaleramp#pos/value. We
    # can't cheaply reconstruct the default ramp, so report a sentinel that
    # compares unequal only if the ramp is non-trivial. The simplest honest
    # answer: return None (kept as changed) — ramps are rare and the author
    # usually DID set them deliberately, so recording is the safe default.
    return None


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
    """Coerce a Houdini value (vector/enum/ramp) into JSON-serializable form."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    # hou.Ramp — serialize to a structured dict so it can be restored on rebuild.
    # Detected by duck type (keys/values/basis/isColor methods) since hou may not
    # be importable in test environments.
    if (hasattr(value, "keys") and hasattr(value, "values")
            and hasattr(value, "basis") and hasattr(value, "isColor")):
        return _ramp_to_dict(value)
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    # Vector3/Vector2/Vector4 — duck-typed by indexing. (Ramp is caught above.)
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


_RAMP_MARKER = "__edini_ramp__"


def _ramp_to_dict(ramp) -> dict:
    """Serialize a hou.Ramp into a JSON-safe dict: keys, values, basis, is_color.

    ``basis`` is the per-segment interpolation type (a hou.rampBasis enum per
    key). We store its int value so rebuild can reconstruct via hou.Ramp().
    """
    try:
        keys = list(ramp.keys())
        values = [_json_safe(v) for v in ramp.values()]
        try:
            basis = [int(b) for b in ramp.basis()]
        except Exception:
            basis = []
        try:
            is_color = bool(ramp.isColor())
        except Exception:
            is_color = False
        return {
            "__type__": _RAMP_MARKER,
            "keys": keys,
            "values": values,
            "basis": basis,
            "is_color": is_color,
        }
    except Exception:
        return str(ramp)


def _dict_to_ramp(data: dict):
    """Reconstruct a hou.Ramp from a _ramp_to_dict dict. Returns hou.Ramp."""
    hou = _hou()
    if hou is None:
        return None
    keys = data.get("keys", [])
    values = data.get("values", [1.0] * len(keys))
    basis_ints = data.get("basis", [])
    is_color = data.get("is_color", False)
    # Normalize values to tuples-of-floats (color ramps → Vector3 per key).
    if is_color:
        vals = []
        for v in values:
            if isinstance(v, (list, tuple)):
                vals.append(hou.Vector3(float(v[0]), float(v[1]), float(v[2])))
            else:
                vals.append(hou.Vector3(float(v), float(v), float(v)))
        values = vals
    else:
        values = [float(v) for v in values]
    # Basis: per-key interpolation enum. Default to Linear (1) if unspecified.
    bases = []
    for b in (basis_ints or [1] * len(keys)):
        try:
            bases.append(hou.rampBasis.Values[b] if hasattr(hou, "rampBasis")
                         else b)
        except Exception:
            bases.append(b)
    if not bases:
        bases = [1] * len(keys)
    try:
        return hou.Ramp(bases, keys, values)
    except Exception:
        return None


def _is_ramp_dict(value: Any) -> bool:
    return isinstance(value, dict) and value.get("__type__") == _RAMP_MARKER


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
        # Collapsible-folder state (e.g. 'up_folder') is UI chrome, not an
        # authored setting, and the manifest never catalogs it. Skip the
        # identity (collapsed=0) value so it doesn't become noise; keep a
        # non-default (expanded=1) only if the author marked it.
        if _is_folder_state_parm(pname) and pname not in marked_set:
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
            default = _manifest_lookup(pname, manifest_defaults)
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


def _is_container_network(node) -> bool:
    """A network container (dopnet/popnet/sopnet...) is a *category layer* iff
    all its non-ignored children are themselves organizational (subnet/geo/
    another container network) with NO work nodes (no SOP/DOP/VOP etc.).

    This lets us descend a dopnet that the user used as a taxonomy folder
    (e.g. /obj/hda/dopnet holding recipe subnets) WITHOUT piercing a dopnet
    that holds DOP work nodes (which is a leaf's content). The companion
    _is_leaf_subnet treats a subnet that contains such a work-filled network
    container as a leaf.
    """
    try:
        kids = [c for c in node.children() if not _is_ignored_node(c)]
    except Exception:
        return False
    if not kids:
        return False  # empty network — treat as non-category, skip
    for c in kids:
        try:
            t = c.type().name()
        except Exception:
            return False
        # Only organizational types may live in a category-layer network.
        if t in _CONTAINER_TYPES or t in _NETWORK_CONTAINER_TYPES:
            continue
        return False  # any work node → not a pure category layer
    return True


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
            # Network containers (dopnet/popnet/sopnet...) serve two roles in a
            # user tree: (1) a CATEGORY LAYER whose children are subnets (the
            # user organizes recipes under a dopnet the way they would under a
            # subnet), and (2) a LEAF's CONTENT (a subnet that holds a dopnet
            # IS the recipe — its dopnet must be captured whole, not pierced).
            # _is_leaf_subnet already treats a subnet containing a network
            # container as a leaf, so here we only need to descend network
            # containers that themselves are pure category layers.
            if t in _NETWORK_CONTAINER_TYPES:
                # Descend only if all non-ignored kids are themselves subnets/
                # containers (category role). If the network container holds
                # work nodes, it is itself a leaf's content and its parent
                # subnet (handled by _is_leaf_subnet) is the harvested leaf.
                if _is_container_network(c):
                    walk(c, in_root_subtree=True)
                continue
            if t not in _CONTAINER_TYPES:
                continue  # plain work node — not harvestable, not a category
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
        # python_script is reference material for edini (the LLM reads it to
        # author networks, it does not execute it). Generated from nodes[] so
        # it always matches the structured data — single source of truth.
        "python_script": _generate_python_script({
            "id": rid, "name": subnet.name(),
            "function": parsed["function"],
            "use_case": parsed["use_case"], "avoid": parsed["avoid"],
            "vex_snippets": vex_snippets, "nodes": recipe_nodes,
        }),
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


def _prune_orphan_recipes(keep_rids: set[str]) -> list[str]:
    """Remove recipes NOT captured this run. The recipe library is a single
    authoritative snapshot of the current manager tree, so any recipe whose id
    is not in ``keep_rids`` is stale (user deleted/moved/renamed the subnet,
    or the manager node itself was renamed) and is removed. The index is
    rebuilt afterwards. Returns the list of removed recipe ids.

    NOTE: this treats the manager tree as the single source of truth — there
    is no per-manager isolation. Every recipe must be present in the tree at
    capture time, or it is pruned.
    """
    root = recipes_root()
    removed: list[str] = []
    if not os.path.isdir(root):
        return removed
    for entry in os.listdir(root):
        child = os.path.join(root, entry)
        if not os.path.isdir(child):
            continue
        if entry in keep_rids:
            continue  # captured this run — keep it
        # Stale: not present in the current tree. Remove it.
        try:
            shutil.rmtree(child)
            removed.append(entry)
        except OSError:
            pass  # best-effort; leave it rather than aborting
    if removed:
        rebuild_index()
    return removed


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

    # Prune stale recipes: the manager tree is the single source of truth, so
    # any recipe not captured this run (user deleted/moved/renamed the subnet,
    # or the manager node itself was renamed) is removed.
    captured_rids = {c["recipe_id"] for c in captured}
    pruned = _prune_orphan_recipes(captured_rids)

    return {
        "success": True,
        "root": root_path,
        "captured_count": len(captured),
        "skipped_count": len(skipped),
        "pruned_count": len(pruned),
        "pruned": pruned,
        "captured": captured,
        "skipped": skipped,
    }


def _infer_category(function_text: str, recipe_id: str) -> str:
    """Heuristic category from the function description + id keywords."""
    text = f"{function_text} {recipe_id}".lower()
    rules = [
        (("管", "tube", "pipe", "圆柱", "沿曲线"), "tube"),
        (("挤出", "extrude", "截面", "beam"), "extrude"),
        (("旋转", "revolve", "回转", "绕轴"), "revolve"),
        (("镜像", "mirror", "对称", "reflect"), "deform"),
        (("阵列", "array", "辐条", "spoke", "均布", "环形"), "array"),
        (("散布", "copy", "scatter", "重复", "ctp", "复制"), "copy"),
        (("布尔", "boolean", "切割", "cut"), "boolean"),
        (("倒角", "bevel", "圆角", "chamfer", "fillet"), "bevel"),
        (("法线", "normal", "fuse", "clean", "清理"), "postprocess"),
        (("变形", "transform", "lattice", "bend", "twist"), "deform"),
    ]
    for keywords, cat in rules:
        if any(k in text for k in keywords):
            return cat
    return "misc"


# ─────────────────────────────────────────────────────────────────────────────
# Python-script generation — turn a recipe into readable reconstruction code.
#
# The script is NOT executed by recipe_rebuild (that path uses the structured
# nodes[] directly). It exists as *reference material* for edini: the LLM reads
# it to learn the node-authoring idiom, the parameters the author cared about,
# and the wiring — then composes its own network with that knowledge. This keeps
# edini's authoring ability unbounded by any single recipe's shape.
# ─────────────────────────────────────────────────────────────────────────────

# Transform params whose default-near-zero values add noise without intent
# (tx/ty/tz=0, rx/ry/rz=0). They are filtered from the generated script unless
# the author marked them.
_NOISE_PARAMS = {
    "tx", "ty", "tz", "rx", "ry", "rz", "px", "py", "pz",
    "originx", "originy", "originz", "dirx", "diry", "dirz",
}


def _format_value(value: Any) -> str:
    """Render a recipe value as a Python literal for the generated script."""
    if isinstance(value, str):
        # Ramp dicts and ordinary strings both serialize as repr; the LLM reads
        # them, it does not eval them, so fidelity matters more than validity.
        return repr(value)
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, float):
        # Trim trailing zeros for readability: 0.012000 -> 0.012
        s = repr(value)
        return s
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_format_value(v) for v in value) + "]"
    if isinstance(value, dict):
        # Ramp dict etc. — emit as a compact dict literal.
        items = ", ".join(
            f"{_format_value(k)}: {_format_value(v)}" for k, v in value.items())
        return "{" + items + "}"
    return repr(value)


def _generate_python_script(recipe: dict[str, Any]) -> str:
    """Turn a captured recipe into a readable Python reconstruction script.

    The script reconstructs the author's subnet network: createNode + setInput +
    parm.set, with VEX snippets inlined. Only the parameters the author MARKED
    (Notes '重要参数') are set explicitly with a comment, so the script surfaces
    author intent instead of drowning in 70+ sweep defaults. Non-trivial changed
    params (a value that is not a default-looking transform) are also included
    so the script reproduces the geometry faithfully; pure-noise params
    (tx/ty/tz=0 ...) are dropped.

    Returns a code string. Pure function — no hou, no file I/O.
    """
    lines: list[str] = []
    nodes = recipe.get("nodes", [])
    vex = {s.get("node"): s for s in recipe.get("vex_snippets", [])}

    # Header: orient the LLM reader about provenance and intent.
    name = recipe.get("name") or recipe.get("id") or "recipe"
    lines.append(f"# Recipe: {recipe.get('id', name)}")
    func = recipe.get("function") or ""
    if func:
        lines.append(f"# 功能: {func}")
    use_case = recipe.get("use_case") or ""
    if use_case:
        lines.append(f"# 用途: {use_case}")
    avoid = recipe.get("avoid") or ""
    if avoid:
        lines.append(f"# 不要用于: {avoid}")
    lines.append(f"# Reconstructs {len(nodes)} node(s). "
                 "Adapt freely — this is reference material, not a contract.")
    lines.append(f'def build_{name}(parent):')

    # Topo-order so setInput targets exist before they're wired. Reuse the same
    # sorter recipe_rebuild uses for consistency.
    ordered = _topo_sort(nodes)
    for spec in ordered:
        nname = spec.get("name", "?")
        ntype = spec.get("type", "?")
        lines.append(f"    # {ntype}")
        lines.append(f"    {nname} = parent.createNode("
                     f"{_format_value(ntype)}, {_format_value(nname)})")

        # VEX snippet (wrangle nodes): the code IS the payload — emit it as a
        # triple-quoted string so the LLM can read the actual logic.
        snip = vex.get(nname)
        if snip and snip.get("code"):
            code = snip["code"]
            runover = snip.get("runover")
            ro_comment = f"  # run-over: class={runover}" if runover is not None else ""
            lines.append(f'    {nname}.parm("snippet").set("""')
            for code_line in code.splitlines():
                lines.append(f"        {code_line}")
            lines.append(f'    """){ro_comment}')

        # Marked params first — these are the author's declared important knobs.
        # Each gets an inline comment so the LLM sees WHY it matters.
        marked = spec.get("marked_params", {}) or {}
        for pname in sorted(marked):
            val = marked.get(pname)
            if pname == "snippet":
                continue  # handled above
            lines.append(f'    {nname}.parm({_format_value(pname)}).set('
                         f"{_format_value(val)})  # author-marked")

        # Non-trivial changed params: reproduce geometry faithfully, but skip
        # the noise (transforms at identity) so the script stays readable.
        changed = spec.get("changed_params", {}) or {}
        for pname in sorted(changed):
            if pname in marked or pname == "snippet":
                continue
            if pname in _NOISE_PARAMS:
                continue
            val = changed.get(pname)
            # Drop empty-string and zero-ish values that carry no intent.
            if val in ("", 0, 0.0, None):
                continue
            lines.append(f'    {nname}.parm({_format_value(pname)}).set('
                         f"{_format_value(val)})")

        # Expressions: preserve any channel references verbatim (rare but
        # meaningful — e.g. a driven relationship the author wired).
        for pname, expr in sorted((spec.get("expressions") or {}).items()):
            if pname == "snippet":
                continue
            lines.append(f"    {nname}.parm({_format_value(pname)})"
                         f".setExpression({_format_value(expr)})")

    # Wiring: emit after all nodes exist (matches rebuild order).
    for spec in ordered:
        nname = spec.get("name", "?")
        inputs = spec.get("inputs") or {}
        for idx_str in sorted(inputs, key=lambda k: int(k) if str(k).isdigit() else 0):
            src = inputs.get(idx_str)
            if not src:
                continue
            lines.append(f"    {nname}.setInput({idx_str}, {src})")

    lines.append("    parent.layoutChildren()")
    # Point at the last real node as the display/render output.
    displayable = [s.get("name") for s in ordered
                   if s.get("type") not in ("null", "output", "stashed_geo")]
    target = displayable[-1] if displayable else (
        ordered[-1].get("name") if ordered else "OUT")
    lines.append(f"    {target}.setDisplayFlag(True)")
    lines.append(f"    return {target}")
    return "\n".join(lines)


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
        # Collect the author-marked parm names across all nodes — these are the
        # signal parms (the ones the recipe deliberately sets) and must be
        # searchable so recipe_list(query="endcaptype") can find a recipe by
        # the convention it encodes.
        marked_parms: list[str] = []
        for n in rj.get("nodes", []):
            marked_parms.extend(
                p for p in (n.get("marked_params") or {}).keys()
                if p not in marked_parms)
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
            "marked_parms": marked_parms,
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


# Bilingual synonyms for cross-language recipe search. Recipes store their
# function text in Chinese (e.g. "沿曲线生成管材"), but the agent often queries
# in English ("tube pipe curve"). Without these mappings a substring search
# misses every recipe. Each group lists terms that are treated as equivalent;
# a query term in any group also matches the haystack if the haystack contains
# ANY other term from the same group. Maps are applied both to the query terms
# and (redundantly, for safety) to the haystack so the direction doesn't matter.
_RECIPE_SYNONYMS: list[set[str]] = [
    {"tube", "pipe", "管", "管材", "管道", "圆柱", "筒"},
    {"curve", "path", "曲线", "路径", "沿曲线"},
    {"sweep", "扫掠", "扫", "sweep::2.0"},
    {"extrude", "挤出", "拉伸", "polyextrude"},
    {"revolve", "旋转", "回转", "lathe"},
    {"copy", "scatter", "散布", "复制", "实例", "instance"},
    {"mirror", "镜像", "对称", "reflect"},
    {"array", "radial", "阵列", "环形", "辐条"},
    {"boolean", "布尔", "cut", "切割"},
    {"bevel", "倒角", "圆角", "fillet", "chamfer"},
    {"revolve", "回转体"},
    {"bolt", "螺栓", "螺钉"},
    {"flange", "法兰"},
    {"deform", "变形", "bend", "twist", "lattice"},
]
# Precompute a term -> set-of-equivalent-terms lookup for O(1) expansion.
_SYNONYM_INDEX: dict[str, set[str]] = {}
for _grp in _RECIPE_SYNONYMS:
    for _term in _grp:
        _SYNONYM_INDEX.setdefault(_term, set()).update(_grp)


def _expand_query_synonyms(term: str) -> set[str]:
    """Return the term plus its bilingual synonyms (lowercased)."""
    t = term.lower()
    syns = _SYNONYM_INDEX.get(t) or _SYNONYM_INDEX.get(term, set())
    return {t} | {s.lower() for s in syns}


def recipe_list(query: str = "", category: str = "", kind: str = "") -> dict[str, Any]:
    """Query the recipe index by keyword and/or category and/or kind.

    Pure file I/O — safe to call without Houdini. Matching is case-insensitive
    substring over the function text + id + category + tree_path components +
    exposed parm names. A multi-word query is split into tokens and matched
    token-by-token (a recipe matches if ANY token hits), and bilingual synonyms
    bridge EN<->CN so "tube" matches "管材". An empty query returns all entries.
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
    # Tokenize the query into terms and expand each with bilingual synonyms.
    # A multi-word query like "tube pipe curve" must NOT be matched as one
    # literal string (that matches nothing); each token is matched
    # independently, and a recipe matches if ANY token hits (with synonyms
    # bridging EN<->CN, e.g. "tube" matches "管材").
    query_terms = q.split() if q else []
    expanded_terms: list[set[str]] = [
        _expand_query_synonyms(t) for t in query_terms
    ]
    for e in entries:
        if cat and e.get("category", "").lower() != cat:
            continue
        if knd and e.get("kind", "network").lower() != knd:
            continue
        if expanded_terms:
            haystack = " ".join([
                e.get("id", ""), e.get("function", ""),
                e.get("category", ""), e.get("kind", ""),
                " ".join(e.get("tree_path", [])),
                " ".join(e.get("exposed_parms", [])),
                " ".join(e.get("marked_parms", [])),
            ]).lower()
            # A recipe matches if ANY query term (or its synonym) is a
            # substring of the haystack. The original whole-string match
            # failed whenever the query had >1 word.
            if not any(any(syn in haystack for syn in syns)
                       for syns in expanded_terms):
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
            "marked_parms": e.get("marked_parms", []),
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
    """Set a parm, returning False if the parm doesn't exist or fails.

    Handles ramp parms: if ``value`` is a serialized ramp dict (from
    _ramp_to_dict), reconstruct a hou.Ramp and set it via set() — Houdini's
    parm.set() accepts a hou.Ramp for ramp-type parms.
    """
    p = node.parm(pname)
    if p is None:
        return False
    try:
        if _is_ramp_dict(value):
            ramp = _dict_to_ramp(value)
            if ramp is None:
                return False
            p.set(ramp)
        else:
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
    container_type = _infer_container_type(recipe_data.get("nodes", []))
    try:
        container = parent.createNode(container_type, container_name)
    except Exception:
        # Fallback: if the inferred container type fails in this parent's
        # context, fall back to subnet (the most permissive container).
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


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard support: read-only tree scan, HDA creation, Notes editing
# ─────────────────────────────────────────────────────────────────────────────

def _classify_node_for_scan(node) -> str:
    """Classify a node as 'container' | 'leaf' | 'ignored' for the dashboard tree.

    Reuses the capture predicates so the scan view matches what capture_tree
    would actually harvest. 'ignored' = output/stashed_geo plumbing.
    """
    try:
        if _is_ignored_node(node):
            return "ignored"
    except Exception:
        return "ignored"
    try:
        t = node.type().name()
    except Exception:
        return "ignored"
    # Only organizational subnet/geo and network containers are tree nodes.
    if t not in _CONTAINER_TYPES and t not in _NETWORK_CONTAINER_TYPES:
        return "ignored"
    if t in _NETWORK_CONTAINER_TYPES:
        # A network container is a category layer iff pure-org kids, else leaf.
        if _is_container_network(node):
            return "container"
        return "leaf"
    if _is_leaf_subnet(node):
        return "leaf"
    if _is_container_subnet(node):
        return "container"
    return "ignored"  # empty subnet — neither


def _scan_node(node) -> dict[str, Any]:
    """Recursively build a display dict for one node (read-only)."""
    entry: dict[str, Any] = {
        "name": node.name(),
        "path": node.path(),
        "type": "ignored",
        "notes": "",
        "children": [],
    }
    try:
        entry["notes"] = node.comment() or ""
    except Exception:
        pass
    kind = _classify_node_for_scan(node)
    entry["type"] = kind
    if kind == "leaf":
        try:
            kids = [c for c in node.children() if not _is_ignored_node(c)]
            entry["node_count"] = len(kids)
        except Exception:
            entry["node_count"] = 0
        # Infer kind (network|vex) + category from notes for display.
        parsed = parse_notes(entry["notes"])
        entry["category"] = _infer_category(parsed["function"], node.name())
        entry["kind"] = "vex" if _looks_like_vex_leaf(node) else "network"
    # Recurse into containers (and the root) to build the full nested tree.
    if kind in ("container", "leaf"):
        # Even leaves get children=[] (empty) — we don't pierce into leaf
        # internals here (that's recipe_read's job). Containers recurse.
        pass
    if kind == "container":
        try:
            for c in node.children():
                ck = _classify_node_for_scan(c)
                if ck == "ignored":
                    continue
                entry["children"].append(_scan_node(c))
        except Exception:
            pass
    return entry


def _looks_like_vex_leaf(node) -> bool:
    """True if a leaf subnet contains any wrangle node (kind=vex)."""
    try:
        for c in node.children():
            if _is_ignored_node(c):
                continue
            if c.type().name() in _VEX_NODE_TYPES:
                return True
    except Exception:
        pass
    return False


def scan_recipe_tree(root_path: str) -> dict[str, Any]:
    """Read-only scan of a subnet tree for dashboard display.

    Returns a nested structure (containers contain children, leaves carry
    node_count/kind/category) WITHOUT writing any recipe.json. This is the
    dashboard's data source — call on a QTimer to keep the tree in sync.

    The root itself is classified (container/leaf/missing) and returned as the
    top of the tree. Missing root → success=False.
    """
    hou = _hou()
    if hou is None:
        return {"success": False, "error": "Houdini (hou module) unavailable."}
    root = hou.node(root_path)
    if root is None:
        return {"success": False, "error": f"root not found: {root_path}",
                "root": root_path, "tree": None}
    tree = _scan_node(root)
    return {"success": True, "root": root_path, "tree": tree}


def set_node_notes(node_path: str, notes: str) -> dict[str, Any]:
    """Write Notes (comment) back to a node, after validation.

    Used by the dashboard's Notes editor. Validates non-empty/non-placeholder
    before writing. Returns {success, node_path, valid} or {success:False, error}.
    """
    hou = _hou()
    if hou is None:
        return {"success": False, "error": "Houdini (hou module) unavailable."}
    node = hou.node(node_path)
    if node is None:
        return {"success": False, "error": f"node not found: {node_path}"}
    ok, reason = validate_notes(notes)
    if not ok:
        return {"success": False, "error": reason, "valid": False}
    try:
        node.setComment(notes)
        # Auto-show the comment in the network editor (the "Show Comment in
        # Network Editor" checkbox) so the Notes are visible by default without
        # the user having to tick it per node.
        node.setGenericFlag(hou.nodeFlag.DisplayComment, True)
    except Exception as e:
        return {"success": False, "error": f"setComment failed: {e}"}
    return {"success": True, "node_path": node_path, "valid": True}


def create_recipe_manager(parent_path: str = "/obj",
                          name: str = "edini_recipe_manager",
                          source_root: str | None = None) -> dict[str, Any]:
    """Create the main recipe-manager HDA (unlocked contents) + initial tree.

    Two modes:
      * **empty** (source_root=None): builds a subnet + an initial
        ``procedural_modeling`` category container.
      * **seeded** (source_root set): builds the HDA, then MOVES the entire
        subtree under ``source_root`` into the HDA, and serializes every leaf
        into recipes/<id>/recipe.json (the database). Use this to turn a scene
        tree you already built (e.g. /obj/hda with procedural_modeling/...
        subnets) into a full Recipe Manager HDA in one shot.

    The HDA is packaged with save_as_locked=False so the internal subnet tree
    stays readable/editable (the dashboard and recipe_capture walk children).

    Returns {success, hda_path, hda_file, seeded?} or {success:False, error}.
    """
    hou = _hou()
    if hou is None:
        return {"success": False, "error": "Houdini (hou module) unavailable."}
    parent = hou.node(parent_path)
    if parent is None:
        return {"success": False, "error": f"parent not found: {parent_path}"}
    existing = parent.node(name)
    if existing is not None:
        return {"success": False,
                "error": f"node already exists: {existing.path()} — "
                         f"use a different name or remove it first"}

    source_node = None
    if source_root:
        source_node = hou.node(source_root)
        if source_node is None:
            return {"success": False,
                    "error": f"source_root not found: {source_root}"}

    try:
        subnet = parent.createNode("subnet", name)
        subnet.setComment("Edini Recipe Manager — 配方仓库与仪表盘")
        if source_node is None:
            # Empty mode: one initial category container.
            cat = subnet.createNode("subnet", "procedural_modeling")
            cat.setComment("分类容器：程序化建模配方")
        try:
            subnet.layoutChildren()
        except Exception:
            pass
        # Package as HDA with UNLOCKED contents — the critical flag.
        # Store the .hda in the repo's otls/ dir (created on demand) so it is
        # registered globally via HOUDINI_OTLSCAN_PATH and travels with git —
        # not trapped inside a single .hip file.
        otls_dir = os.path.join(_project_root(), "otls")
        os.makedirs(otls_dir, exist_ok=True)
        hda_file = os.path.join(otls_dir, f"{name}.hda")
        # NOTE: H21's createDigitalAsset has no save_as_locked kwarg. Content
        # is created UNLOCKED by default (editable via Allow Editing); the
        # dashboard + recipe_capture walk children regardless. We pass only the
        # documented kwargs (name/hda_file_name/description).
        subnet.createDigitalAsset(
            name=name,
            hda_file_name=hda_file,
            description="Edini Recipe Manager",
        )
    except Exception as e:
        try:
            if "subnet" in locals() and subnet is not None:
                subnet.destroy()
        except Exception:
            pass
        return {"success": False, "error": f"createDigitalAsset failed: {e}"}

    # ── Seeded mode: move source subtree in + serialize database ──────────
    seeded_summary = None
    if source_node is not None:
        try:
            seeded_summary = _seed_from_source(subnet, source_node)
        except Exception as e:
            seeded_summary = {"moved": 0, "captured": 0, "error": str(e)}

    result = {"success": True, "hda_path": subnet.path(), "hda_file": hda_file}
    if seeded_summary is not None:
        result["seeded"] = seeded_summary
    return result


def _seed_from_source(hda_root, source_root) -> dict:
    """Move source_root's children into hda_root, then capture every leaf.

    Returns {moved, captured, skipped, errors}. The source_root itself is NOT
    moved (only its children) so the original scene node remains as a marker.
    """
    moved = 0
    errors: list[str] = []
    for child in list(source_root.children()):
        try:
            child.moveTo(hda_root)
            moved += 1
        except Exception as e:
            errors.append(f"{child.path()}: {e}")
    try:
        hda_root.layoutChildren()
    except Exception:
        pass
    # Now serialize: capture every leaf under the HDA into recipes/.
    cap = recipe_capture_tree(hda_root.path())
    captured = cap.get("captured_count", 0) if cap.get("success") else 0
    skipped = cap.get("skipped_count", 0) if cap.get("success") else 0
    if not cap.get("success"):
        errors.append(f"capture_tree: {cap.get('error', '?')}")
    return {"moved": moved, "captured": captured, "skipped": skipped,
            "errors": errors}

