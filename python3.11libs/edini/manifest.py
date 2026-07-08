"""Parm-template manifest: generation, load, query, H21 version parsing.

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





_NODE_PARMS_MANIFEST_REL = os.path.join("edini", "data", "node_parms_manifest.json")


def _node_parms_manifest_path() -> str:
    """Absolute path to the bundled manifest (next to the edini package)."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "data", "node_parms_manifest.json")


def load_node_parms_manifest() -> dict | None:
    """Load the bundled node-params manifest. Returns None if missing or
    corrupt (callers degrade gracefully — the tool reports 'manifest not
    available', the validator skips parm-name checks). Pure file I/O, no hou."""
    path = _node_parms_manifest_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict) or "node_types" not in data:
        return None
    return data


def _attr_or_call(obj, attr: str, default=None):
    """Read `obj.<attr>` whether it is a method (real Houdini) or a plain
    attribute (mock). Returns default on any failure. Houdini ParmTemplates
    expose name/label/defaultValue/menuItems as methods; our mock stores some
    as attributes, so this normalizes both."""
    val = getattr(obj, attr, None)
    if val is None:
        return default
    try:
        return val() if callable(val) else val
    except Exception:
        return default


def _vector_component_names(root: str, ncomp: int) -> list[str]:
    """Return the per-component channel names for a vector parm.

    Houdini's rule is uniform: a vector parm named ``dir`` exposes channels
    ``dirx``/``diry``/``dirz`` (and ``dirw`` for 4-component). This holds for
    every SOP built-in (``t``, ``r``, ``s``, ``p``, ``dir``, ``origin``,
    ``size``, ``rad``, ...). We synthesise the names rather than querying the
    node because the manifest is generated once and consumed offline.

    For ncomp outside 2..4 (rare — e.g. a 9- or 16-element matrix default),
    the default may just be a multi-element scalar array, not a true vector;
    we return [] so no misleading ``components`` are recorded.
    """
    if not root or ncomp not in (2, 3, 4):
        return []
    suffixes = ("x", "y", "z", "w")[:ncomp]
    return [f"{root}{s}" for s in suffixes]


def _extract_parm_spec(tmpl, multiparm_block: str | None = None) -> dict[str, Any] | None:
    """Extract a JSON-serializable spec from one ParmTemplate.
    Returns None for folders/separators/labels (non-parm entries). The spec
    captures what an agent needs to write a recipe: name, type, label, default,
    menu tokens, and numeric range.

    ``multiparm_block`` — when the template is an instance inside a multiparm
    block (its name carries a ``#`` placeholder), this is the block's count
    channel name. We record it so a consumer knows which multiparm this
    instance belongs to and how many instances exist."""
    # Skip non-parm template kinds (folders, separators, labels).
    name = _attr_or_call(tmpl, "name")
    if not name or not isinstance(name, str):
        return None

    # Determine the template's type. hou.parmTemplateType is an enum whose
    # member's .name() yields "Float"/"Int"/"Menu"/"Toggle"/"String"/...;
    # the mock carries a plain _type_name string as a fallback.
    type_name = "unknown"
    t = _attr_or_call(tmpl, "type")
    if t is not None:
        type_name = _attr_or_call(t, "name") or "unknown"
    if type_name in (None, "unknown"):
        type_name = getattr(tmpl, "_type_name", "unknown")

    spec: dict[str, Any] = {"name": name, "type": type_name}

    # Multi-component parms (Float/Int vectors) are addressable on a node by
    # their per-component names — e.g. the circle SOP's radius template is
    # named "rad" but only "radx"/"rady" exist on the live node. Recording the
    # group name alone misleads agents: node.parm("rad") returns None and
    # raises AttributeError. Capture numComponents + the real component names
    # so the manifest reflects what is actually addressable.
    ncomp = _attr_or_call(tmpl, "numComponents") or 1
    try:
        ncomp = int(ncomp)
    except Exception:
        ncomp = 1
    if ncomp > 1:
        suffixes = ("x", "y", "z", "w")[:ncomp]
        comp_names = [name + s for s in suffixes]
        spec["num_components"] = ncomp
        spec["component_names"] = comp_names
        spec["note"] = (
            f"multi-component: use {', '.join(comp_names)} on the node "
            f"(not the group name {name!r})"
        )

    lbl = _attr_or_call(tmpl, "label")
    if lbl and lbl != name:
        spec["label"] = lbl

    # Default value: most templates expose defaultValue().
    dv = _attr_or_call(tmpl, "defaultValue")
    if dv is not None:
        spec["default"] = _json_safe(dv)

    # Menu items: only Menu/String-menu templates have menuItems().
    if type_name in ("Menu", "String"):
        items = _attr_or_call(tmpl, "menuItems")
        if items:
            spec["menu_items"] = [str(i) for i in items]

    # Numeric range (min/max) for Float/Int.
    if type_name in ("Float", "Int"):
        mn = _attr_or_call(tmpl, "minValue")
        if mn is not None:
            spec["min"] = _json_safe(mn)
        mx = _attr_or_call(tmpl, "maxValue")
        if mx is not None:
            spec["max"] = _json_safe(mx)

    # Vector / multi-component detection (CRITICAL fix).
    #
    # In Houdini, a vector parm like ``line.dir`` is a SINGLE ParmTemplate whose
    # ``numComponents()`` > 1 and whose name is the bare vector root (``dir``).
    # But the Python runtime API does NOT let you do ``node.parm('dir')`` — that
    # returns None. You must use ``node.parmTuple('dir')`` or the per-component
    # channels ``dirx`` / ``diry`` / ``dirz``. The old manifest only recorded the
    # root name with type "Float", so agents called ``parm('dir').set(...)`` and
    # hit ``'NoneType' object has no attribute 'set'`` every time.
    #
    # We now record ``vector_size`` + ``components`` so the consumer can tell a
    # true vector from a scalar, and knows the exact component channel names.
    ncomp = _attr_or_call(tmpl, "numComponents")
    try:
        ncomp = int(ncomp) if ncomp is not None else 0
    except (TypeError, ValueError):
        ncomp = 0
    # Fallback: infer size from the default value when numComponents() didn't
    # report a vector (returns 0/1/None, or the API is absent). A multi-element
    # default on a Float/Int template is overwhelmingly a vector
    # (t/dir/origin/size/r/s). NOTE: this fallback must trigger when numComponents
    # reports <=1 too — on some Houdini 21 builds numComponents() under-reports
    # for Float templates, so the default-length signal is the reliable one.
    if ncomp <= 1 and isinstance(spec.get("default"), list):
        ncomp = len(spec["default"])
    if ncomp and ncomp > 1 and type_name in ("Float", "Int"):
        spec["vector_size"] = ncomp
        # Only synthesise component names for PLAIN vectors (no ``#``). A plain
        # vector ``dir`` always exposes ``dirx``/``diry``/``dirz``. But a
        # multiparm-instance vector like ``value#v#`` or ``stroke#_color`` has
        # a totally different channel scheme — the ``#`` is replaced by a
        # 1-based index and the component suffix is numeric (``value1v1``), NOT
        # ``xyz``. Guessing ``stroke#_colorx`` here would be actively wrong, so
        # we record ``vector_size`` only and let the consumer ask a live node
        # for the exact channels.
        if "#" not in name:
            comp = _vector_component_names(name, ncomp)
            if comp:
                spec["components"] = comp

    # Multiparm-instance tagging. A ``#`` in the name marks a per-row template
    # (e.g. ``useapply#`` inside the ``numapply`` block). When we detected the
    # owning block via folderType(), we record it so consumers can reconstruct
    # the multiparm and resolve ``#`` to 1-based indices (e.g. ``useapply1``).
    # Some instance templates sit inside a plain (non-MultiparmBlock) folder —
    # the block detection misses those, but the ``#`` is itself a reliable
    # instance signal, so we tag those too with an unknown block.
    if "#" in name:
        spec["multiparm"] = "instance"
        if multiparm_block:
            spec["multiparm_block"] = multiparm_block

    return spec


def _json_safe(value) -> Any:
    """Coerce a Houdini value (vector/tuple/ramp/enum) into JSON-serializable form.

    Handles hou.Ramp (detected by duck type: keys/values/basis/isColor) which
    otherwise crashes json.dumps with 'Object of type Ramp is not JSON
    serializable'. Mirrors recipe_library._json_safe's Ramp handling.
    """
    if isinstance(value, (int, float, str, bool)) or value is None:
        return value
    # hou.Ramp — serialize to a structured dict (duck-typed, no hou import needed).
    if (hasattr(value, "keys") and hasattr(value, "values")
            and hasattr(value, "basis") and hasattr(value, "isColor")):
        return _ramp_to_safe_dict(value)
    if isinstance(value, (list, tuple)):
        try:
            return [_json_safe(v) for v in value]
        except Exception:
            return str(value)
    # Single-element numeric (hou layer may return a 1-tuple for scalar defaults).
    try:
        for attr in ("x", "y", "z", "w"):
            if hasattr(value, attr):
                return [_json_safe(getattr(value, a)())
                        for a in ("x", "y", "z", "w") if hasattr(value, a)]
    except Exception:
        pass
    try:
        return float(value)
    except Exception:
        pass
    return str(value)


def _ramp_to_safe_dict(ramp) -> dict:
    """Serialize a hou.Ramp into a JSON-safe dict (keys, values, basis, is_color)."""
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
        return {"__type__": "ramp", "keys": keys, "values": values,
                "basis": basis, "is_color": is_color}
    except Exception:
        return str(ramp)


def _correct_vector_components(parms: list[dict[str, Any]], category, type_name: str) -> None:
    """Overwrite each vector parm's ``components`` with the REAL runtime channel
    names read from a live node instance.

    Why: the walker synthesises component names by the ``name+xyz`` rule, but
    Houdini violates it for several SOPs — ``tube.rad`` exposes ``rad1``/``rad2``
    (numeric), ``xform.shear`` exposes ``shear1/2/3``. A guessed ``radx`` makes
    an agent call ``parm('radx')`` which returns None and crashes the build
    (a real, repeated failure in session logs). Reading from an instance is the
    only source of truth.

    Mutates ``parms`` in place. Best-effort: if a temp node can't be created
    (abstract types, mock hou), the existing synthetic names are left as-is.
    """
    vecs = [p for p in parms if p.get("vector_size", 1) > 1 and "#" not in p.get("name", "")]
    if not vecs:
        return
    # Create a temporary node to query real channels. Failures here are
    # non-fatal — we keep the synthetic names and move on.
    try:
        nt = category.nodeType(type_name)
        if nt is None:
            return
        # Build under a throwaway geo so we never pollute the scene. Use the
        # /obj category's default container if Sop, else the type's own table.
        try:
            obj = hou.node("/obj")
        except Exception:
            return
        if obj is None:
            return
        try:
            tmp_geo = obj.createNode("geo", "_manifest_probe")
        except Exception:
            tmp_geo = obj
        try:
            inst = tmp_geo.createNode(type_name, "_p")
        except Exception:
            # Some types can't be created under geo; try directly under /obj.
            try:
                inst = obj.createNode(type_name, "_p")
                tmp_geo = obj  # so cleanup targets /obj... skip, handled below
            except Exception:
                if tmp_geo is not obj:
                    try: tmp_geo.destroy()
                    except Exception: pass
                return
        try:
            for p in vecs:
                nm = p["name"]
                try:
                    pt = inst.parmTuple(nm)
                    if pt and len(pt) > 1:
                        chans = [x.name() for x in pt]
                        if chans:
                            p["components"] = chans
                except Exception:
                    pass
        finally:
            try: inst.destroy()
            except Exception: pass
            try:
                if tmp_geo is not obj:
                    tmp_geo.destroy()
            except Exception: pass
    except Exception:
        return


def _is_multiparm_block(tmpl) -> bool:
    """True if ``tmpl`` is a multiparm (collapsible) folder.

    On real Houdini, a multiparm container is a ``FolderParmTemplate`` whose
    ``folderType() == hou.folderType.MultiparmBlock``. The plain ``type().name()``
    returns "Folder" for BOTH multiparm and simple folders, so it cannot tell
    them apart — only ``folderType()`` can. This helper is defensive: it
    returns False when the API is unavailable (mocks, oddball templates) rather
    than raising, so the walker degrades to the old (folder-recursion) path.
    """
    try:
        ft = tmpl.folderType()
    except Exception:
        return False
    try:
        target = hou.folderType.MultiparmBlock
    except Exception:
        return False
    try:
        return ft == target
    except Exception:
        return False


def _flatten_parm_templates(group) -> list[dict[str, Any]]:
    """Walk a ParmTemplateGroup, recursing into folders, returning a flat list
    of parm specs (folders/separators skipped)."""
    specs: list[dict[str, Any]] = []
    seen_names: set[str] = set()

    def walk(templates, multiparm_block: str | None = None):
        for tmpl in templates:
            # A MultiparmBlock is a Folder whose folderType() is
            # hou.folderType.MultiparmBlock. It is BOTH the count channel (named
            # after the folder, e.g. ``targetattribs``) AND a container whose
            # parmTemplates() are the per-instance templates (named with a ``#``
            # placeholder). IMPORTANT: type().name() returns "Folder" for these,
            # NOT "Multiparm" — only folderType() distinguishes a multiparm
            # folder from a plain (Simple) one. The old walker recursed into the
            # children but skipped the block, so the count channel vanished and
            # the ``#`` params had no grouping context. We now record the block
            # as an Int count parm and tag its instances.
            if _is_multiparm_block(tmpl):
                blk_name = _attr_or_call(tmpl, "name")
                # Record the multiparm's count channel (Int). The folder name IS
                # the count channel (verified on real Houdini 21 nodes).
                if blk_name and blk_name not in seen_names:
                    seen_names.add(blk_name)
                    specs.append({
                        "name": blk_name,
                        "type": "Int",
                        "label": _attr_or_call(tmpl, "label") or blk_name,
                        "multiparm": "counter",
                    })
                try:
                    block_children = tmpl.parmTemplates()
                except Exception:
                    block_children = None
                if block_children:
                    walk(block_children, multiparm_block=blk_name)
                continue

            # Detect folder templates: they expose parmTemplates() returning a
            # non-empty list. Real parm templates either lack the method or it
            # raises, so the try/except below falls through to _extract_parm_spec.
            try:
                children = tmpl.parmTemplates()
            except Exception:
                children = None
            if children:
                walk(children, multiparm_block=multiparm_block)
                continue
            spec = _extract_parm_spec(tmpl, multiparm_block=multiparm_block)
            if spec and spec["name"] not in seen_names:
                seen_names.add(spec["name"])
                specs.append(spec)

    try:
        entries = group.entries()
    except Exception:
        entries = []
    walk(entries)
    return specs


_CREATE_NODE_PARM_CAP = 60


def _node_parm_inventory(node) -> dict[str, Any]:
    """Build a compact, agent-facing inventory of a freshly created node's
    parameters.

    Reads the node's own ``parmTemplateGroup()`` (the actual instantiated
    version — no manifest drift) and flattens it into a small list. Each entry
    keeps only what the agent needs to address the parm next: its name, type,
    and — for multi-component vectors — the real per-component channel names
    (``rad`` → ``radx``/``rady``), which is exactly the gap that caused the
    chair-log agent to guess ``length`` instead of ``dist``.

    This is strictly best-effort: any failure reading templates degrades to an
    empty ``parms`` list with a ``note`` rather than failing ``create_node``.
    A create call must never be blocked by the inventory step.

    Two resolution paths, tried in order:
      1. The node TYPE's ``parmTemplateGroup()`` — canonical, complete, carries
         type + menu + component names. Works in real Houdini.
      2. The node instance's already-materialized ``parms()`` — each parm knows
         at least its own name (and, in real Houdini, its template). This is
         the fallback for environments where the type-level group isn't exposed
         (e.g. the unit-test mock, which populates node._parms at create time
         but leaves the type's group empty).
    The fallback yields name-only entries when a parm's template isn't
    available — still enough to stop the agent guessing parm names.
    """
    # Path 1: type-level parm template group (richest).
    full: list[dict[str, Any]] = []
    group = None
    try:
        ntype = node.type()
        if ntype is not None:
            group = ntype.parmTemplateGroup()
    except Exception:
        group = None
    if group is not None:
        try:
            full = _flatten_parm_templates(group)
        except Exception:  # noqa: BLE001 — inventory must never break create
            full = []

    # Path 2: instance parms (fallback). Used when the type group is empty or
    # wasn't readable. Each parm contributes its name; its template (if
    # available) adds type + menu + component info. We build raw specs in the
    # SAME shape path 1 produces (component_names / menu_items), so the shared
    # compact loop below handles both paths uniformly.
    if not full:
        try:
            live_parms = node.parms()
        except Exception:  # noqa: BLE001
            live_parms = []
        for p in live_parms:
            try:
                nm = p.name()
            except Exception:
                continue
            if not nm:
                continue
            spec: dict[str, Any] = {"name": nm, "type": "unknown"}
            # Real hou.Parm exposes .template(); the mock's MockParm does not —
            # degrade to name-only there (still prevents name-guessing).
            try:
                tmpl = p.template()
                if tmpl is not None:
                    ttype = _attr_or_call(tmpl, "type")
                    tname = _attr_or_call(ttype, "name") if ttype is not None else None
                    if tname:
                        spec["type"] = tname
                    ncomp = _attr_or_call(tmpl, "numComponents") or 1
                    try:
                        ncomp = int(ncomp)
                    except Exception:
                        ncomp = 1
                    if ncomp > 1:
                        spec["component_names"] = [nm + s for s in ("x", "y", "z", "w")[:ncomp]]
                    items = _attr_or_call(tmpl, "menuItems")
                    if items:
                        spec["menu_items"] = [str(i) for i in items]
            except Exception:
                pass
            full.append(spec)

    if not full:
        return {"list": [], "truncated": False, "note": "no readable parms"}

    compact: list[dict[str, Any]] = []
    for spec in full:
        name = spec.get("name")
        if not name:
            continue
        # Always include the primary name + type. Type guides how to set the
        # parm (e.g. Menu needs a token, Float takes a number or expression).
        entry: dict[str, Any] = {"name": name, "type": spec.get("type", "unknown")}
        # Multi-component parms: surface the addressable channel names. This is
        # the single most valuable field — without it, agents address the group
        # name ('rad') which returns None and cascades into wasted rounds.
        comps = spec.get("component_names")
        if comps:
            entry["components"] = comps
        # Menu tokens: a Menu parm's value must be one of these, and guessing a
        # token (e.g. 'x' vs 'X') is a common failure — include them when few.
        menu = spec.get("menu_items")
        if menu and len(menu) <= 12:
            entry["menu"] = menu
        compact.append(entry)

    total = len(compact)
    if total > _CREATE_NODE_PARM_CAP:
        truncated = compact[:_CREATE_NODE_PARM_CAP]
        return {
            "list": truncated,
            "truncated": True,
            "total": total,
            "note": f"showing first {_CREATE_NODE_PARM_CAP} of {total}; "
                    f"use query_parms(node_type=...) for the full list",
        }
    return {"list": compact, "truncated": False, "total": total}


def _node_type_namespace(type_name: str) -> str | None:
    """Return the namespace prefix of a node type name, or None for built-ins.

    Houdini namespaces node types as '<ns>::<base>::<ver>' (e.g.
    'labs::tree_branch_generator::1.1', 'copytopoints::2.0'). A bare version
    suffix like 'copytopoints::2.0' is NOT a namespace — it's a built-in with
    a major version. We treat the prefix as a namespace only when the base
    name (after the prefix) is itself a recognizable SOP base, which we
    approximate by: the prefix is alphabetic AND the full type isn't a known
    built-in pattern. In practice we just return the first '::'-segment and
    let exclude_namespaces match against the well-known third-party set."""
    if "::" not in type_name:
        return None
    return type_name.split("::")[0]


_DEFAULT_EXCLUDE_NAMESPACES = frozenset({
    "labs",        # SideFX Labs (380+ nodes, art-focused)
    "kinefx",      # character rigging (133 nodes)
    "apex",        # APEX graph framework
    "DJA",         # third-party materialx shaders
    "quadspinner", # third-party terrain
    # User HDA namespaces are environment-specific; add yours here if needed.
})


def generate_node_parms_manifest(
    category: str = "Sop",
    exclude_namespaces: frozenset[str] | None = None,
) -> dict[str, Any]:
    """Build the node-params manifest by walking hou.nodeTypeCategories().
    Requires a live Houdini (real hou module). Returns the manifest dict;
    the caller (script/tool) is responsible for writing it to disk.

    By default excludes third-party/plugin/asset namespaces (labs, kinefx,
    apex, ...) which are large, environment-specific, and irrelevant to
    procedural recipe building. Built-in versioned nodes like
    'copytopoints::2.0' are kept. Pass exclude_namespaces=set() to keep
    everything, or a custom set to filter differently.

    The manifest shape:
      {"houdini_version": "...", "generated_at": "...", "category": "Sop",
       "excluded_namespaces": [...],
       "node_types": {"<type_name>": {"parms": [{name,type,...}, ...]}, ...}}
    """
    if exclude_namespaces is None:
        exclude_namespaces = _DEFAULT_EXCLUDE_NAMESPACES

    try:
        version = hou.applicationVersionString()
    except Exception:
        version = "unknown"

    node_types: dict[str, Any] = {}
    categories = hou.nodeTypeCategories()
    cat = categories.get(category) if hasattr(categories, "get") else None
    if cat is None:
        # nodeTypeCategories() on real hou returns a dict; on mock it may be a
        # custom mapping. Fall back to bracket access.
        try:
            cat = categories[category]
        except Exception:
            return {
                "houdini_version": version,
                "generated_at": _now_iso(),
                "category": category,
                "excluded_namespaces": sorted(exclude_namespaces),
                "node_types": {},
                "error": f"category {category!r} not found",
            }

    for nt in cat.nodeTypes().values():
        type_name = nt.name()
        ns = _node_type_namespace(type_name)
        if ns is not None and ns in exclude_namespaces:
            continue
        try:
            group = nt.parmTemplateGroup()
        except Exception:
            # Some node types (e.g. heavily customized HDAs) may not expose a
            # template group — skip them rather than aborting the whole dump.
            continue
        parms = _flatten_parm_templates(group)
        # Fix vector component names against the REAL runtime channels. The
        # walker synthesises component names by rule (name+xyz), but Houdini
        # is inconsistent: tube.rad -> rad1/rad2 (numeric), shear -> shear1/2/3.
        # Guessing radx/rady here would send an agent to a non-existent parm.
        # We instantiate the node once and read each vector's actual channels.
        _correct_vector_components(parms, cat, type_name)
        node_types[type_name] = {"parms": parms}

    return {
        "houdini_version": version,
        "generated_at": _now_iso(),
        "category": category,
        "excluded_namespaces": sorted(exclude_namespaces),
        "node_types": node_types,
    }


def _enrich_manifest_parms(parms: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Backfill component_names/num_components for multi-component parms.

    The manifest was generated before _extract_parm_spec recorded
    numComponents, so legacy entries store only the ParmTemplate *group* name
    (e.g. circle's "rad") — but on the live node only the suffixed per-component
    parms exist ("radx", "rady"). node.parm("rad") returns None and the agent's
    code crashes with AttributeError. Regenerating the manifest requires a live
    Houdini, so we heal the data at serve time instead.

    Two cases:
      1. The entry already carries authoritative component info (a `components`
         list, e.g. tube.rad -> ["rad1","rad2"], box.size -> ["sizex",...]).
         Trust it — derive component_names from it and do NOT synthesise via the
         x/y/z suffix heuristic (that heuristic is wrong for tube, which uses
         numeric suffixes rad1/rad2, not radx/rady).
      2. A legacy entry with no `components` but a list `default` of length 2/3/4:
         synthesise <name>+x/y/z[/w]. This matches how _json_safe serialises
         defaultValue() for FloatParmTemplate with numComponents 2/3/4 (the
         common Radius/Center/Rotate cases). Only used when components is absent.
    """
    suffixes_by_len = {2: ("x", "y"), 3: ("x", "y", "z"), 4: ("x", "y", "z", "w")}
    enriched: list[dict[str, Any]] = []
    for p in parms:
        if not isinstance(p, dict) or p.get("num_components"):
            enriched.append(p)
            continue

        # Case 1: authoritative `components` already present — trust it verbatim.
        existing_components = p.get("components")
        if isinstance(existing_components, list) and existing_components:
            p = dict(p)  # copy so we don't mutate the manifest dict in memory
            p["num_components"] = len(existing_components)
            p["component_names"] = list(existing_components)
            enriched.append(p)
            continue

        # Case 2: legacy entry — synthesise from the default-list length.
        default = p.get("default")
        ptype = p.get("type")
        if (
            ptype in ("Float", "Int")
            and isinstance(default, list)
            and len(default) in suffixes_by_len
        ):
            name = p.get("name", "")
            comps = [name + s for s in suffixes_by_len[len(default)]]
            p = dict(p)  # copy so we don't mutate the manifest dict in memory
            p["num_components"] = len(default)
            p["component_names"] = comps
            p["note"] = (
                f"multi-component: use {', '.join(comps)} on the node "
                f"(not the group name {name!r})"
            )

        # Menu params: append a human-readable index→token mapping so the agent
        # doesn't have to guess what numeric codes mean (e.g. attribwrangle
        # class: 0=detail,1=primitive,2=point,3=vertex,4=number). The manifest
        # stores menu_items as the ordered token list; the index is positional.
        if p.get("type") == "Menu":
            items = p.get("menu_items")
            if isinstance(items, list) and items:
                p = _annotate_menu_options(p, items)
        enriched.append(p)
    return enriched


def _annotate_menu_options(p: dict, items: list) -> dict:
    """Return a copy of menu parm `p` with a `menu_options` index→token map
    and a `note` summarising it, so the agent can set the right numeric value
    without trial-and-error (copies first; never mutates the manifest dict)."""
    p = dict(p)
    opts = [{"index": i, "token": str(tok)} for i, tok in enumerate(items)]
    p["menu_options"] = opts
    summary = ", ".join(f"{i}={tok}" for i, tok in enumerate(items))
    p["note"] = f"menu: {summary} (set the numeric index OR the token string)"
    return p


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


_NODE_TYPE_GOTCHA_HINTS: dict[str, str] = {
    "tube": ("tube defaults to type=prim (a single primitive). For copytopoints "
             "instancing or any polygon workflow, set type=poly or type=mesh."),
}


def _type_specific_hints(node_type: str) -> list[str]:
    """Per-node-type gotcha hints (default-value traps agents hit). Returns
    hints whose key matches the bare (namespace-stripped, lowercased) type."""
    bare = node_type.split("::")[0].lower()
    hint = _NODE_TYPE_GOTCHA_HINTS.get(bare)
    return [hint] if hint else []


def _access_hints(parms: list[dict[str, Any]]) -> list[str]:
    """Build actionable access hints for a parm list, targeted at the exact
    mistakes agents repeatedly make (each hint below maps to a real failure
    seen in session logs).

    The manifest records a vector root name (e.g. ``dir``) and its component
    channels (``dirx``/``diry``/``dirz``), plus multiparm blocks. Without these
    hints, an agent writes ``node.parm('dir').set((1,0,0))`` and crashes with
    ``'NoneType' object has no attribute 'set'`` because ``parm('dir')`` is
    None — you must use ``parmTuple('dir')`` or ``parm('dirx')``.
    """
    hints: list[str] = []
    has_vector = any(p.get("vector_size", 1) and p.get("vector_size", 1) > 1
                     or p.get("components") for p in parms)
    has_multiparm = any(p.get("multiparm") for p in parms)
    if has_vector:
        # Pick one concrete example so the hint is copy-pasteable.
        example = next((p for p in parms if p.get("components")), None)
        if example:
            comps = example["components"]
            hints.append(
                f"VECTOR params: do NOT use node.parm('{example['name']}') — it "
                f"returns None. Use node.parmTuple('{example['name']}').set((..)) "
                f"or the component channels {comps} "
                f"(e.g. node.parm('{comps[0]}').set(val))."
            )
    if has_multiparm:
        # Find a multiparm counter + one of its instances as an example.
        counter = next((p for p in parms if p.get("multiparm") == "counter"), None)
        inst = next((p for p in parms if p.get("multiparm") == "instance"), None)
        detail = ""
        if counter and inst:
            detail = (f" e.g. set {counter['name']} = N to add N instances, "
                      f"then read/write {inst['name']} with '#' -> the 1-based "
                      f"index (first instance = "
                      f"{inst['name'].replace('#','1')}).")
        hints.append(
            "MULTIPARM params (names containing '#') are per-instance channels. "
            "Replace '#' with the instance index (1-based)." + detail
        )
    return hints


def node_parms(node_type: str, category: str = "Sop") -> dict[str, Any]:
    """Query a node TYPE's parameter list (C-station).

    Reads the bundled, version-pinned manifest first (zero hou dependency,
    always accurate for the pinned Houdini version). If the type is absent
    from the manifest AND a live Houdini is available, falls back to a live
    query so the tool stays useful on versions the manifest predates.

    Returns:
      {"success": True, "node_type": ..., "category": ..., "parms": [...],
       "access_hints": [...], "source": "manifest"|"live", "houdini_version"?}
      on hit; {"success": False, "error": "..."}  on miss (or "not found").
    """
    node_type = (node_type or "").strip()
    if not node_type:
        return {"success": False, "error": "node_type is required"}

    # 1. Bundled manifest (preferred — pinned, offline, fast).
    manifest = load_node_parms_manifest()
    if manifest is not None:
        node_types = manifest.get("node_types", {})
        resolved, nt_entry = _resolve_node_type_in_manifest(node_type, node_types)
        if nt_entry is not None:
            # Version-sync: when we resolved a name, confirm it matches the
            # version Houdini's createNode would ACTUALLY instantiate. If the
            # caller asked for a bare name, create_node creates Houdini's default
            # version (e.g. "polybevel::3.0") — so we must return that version's
            # params, not whatever the manifest resolved to. Otherwise the agent
            # gets params (beveltype/relinset) that don't exist on the created
            # node (offset/filletshape on ::3.0). Only corrects when a manifest
            # entry for the live default version exists.
            if not getattr(hou, "_MOCK", False) and "::" not in resolved:
                live_default = _hou_default_version(resolved, category)
                if live_default and live_default in node_types:
                    resolved = live_default
                    nt_entry = node_types[live_default]
            parms = _enrich_manifest_parms(nt_entry.get("parms", []))
            result = {
                "success": True,
                "node_type": resolved,
                "category": manifest.get("category", category),
                "parms": parms,
                "access_hints": _access_hints(parms) + _type_specific_hints(resolved),
                "source": "manifest",
                "houdini_version": manifest.get("houdini_version"),
            }
            if resolved != node_type:
                # The agent asked for a bare name (e.g. 'boolean') but we
                # resolved it to a versioned form ('boolean::2.0',
                # 'polybevel::3.0'). Surface the resolved name so the agent uses
                # it for create_node too.
                result["resolved_from"] = node_type
            return result

    # 2. Live fallback (only if hou is a real Houdini, not a mock).
    try:
        live = _node_parms_live(node_type, category)
        if live is not None:
            live["access_hints"] = (_access_hints(live.get("parms", []))
                                    + _type_specific_hints(live.get("node_type", node_type)))
            return live
    except Exception:
        pass

    # 3. Missed everywhere.
    hint = ""
    if manifest is None:
        hint = " (manifest not bundled; run generate_node_parms_manifest)"
    return {"success": False, "error": f"node type {node_type!r} not found"
            + hint}


def _resolve_node_type_in_manifest(
    node_type: str, node_types: dict[str, Any]
) -> tuple[str, dict | None]:
    """Look up a node type in the manifest, transparently resolving a bare
    name to its versioned form.

    Houdini commits only the current major version of some nodes to the
    manifest: 'boolean' is stored as 'boolean::2.0', 'sweep' optionally as
    'sweep::2.0', etc. An agent that asks for the bare name should still get a
    hit, matching how ``create_node`` resolves namespaces. Returns
    ``(resolved_name, entry)`` or ``(node_type, None)`` on miss.

    IMPORTANT (version-sync): when a bare name (e.g. "polybevel") has BOTH a
    legacy bare manifest entry AND versioned entries ("polybevel::2.0",
    "polybevel::3.0"), we prefer the HIGHEST versioned entry. Reason: Houdini's
    createNode("polybevel") creates the latest version (::3.0), and query_parms
    must return params for the SAME version the agent will actually create — a
    bare legacy entry (with old param names like beveltype/relinset) gives the
    agent params that don't exist on the created node. node_parms() additionally
    corrects this against the LIVE Houdini default via namespaceOrder().
    """
    # Versioned siblings of this name (highest-version-first).
    if "::" not in node_type:
        candidates = [
            k for k in node_types
            if k.split("::")[0] == node_type and k.count("::") == 1
        ]
        if candidates:
            candidates.sort(key=_manifest_version_key, reverse=True)
            best = candidates[0]
            # Prefer the highest versioned entry over a stale bare entry (if any).
            return best, node_types[best]

    entry = node_types.get(node_type)
    if entry is not None:
        return node_type, entry
    return node_type, None


def _manifest_version_key(k: str) -> tuple:
    """Numeric sort key for a versioned manifest key's '::' suffix.

    'polybevel::3.0' -> (3, 0); a bare/unparseable key -> (0,) so it sorts last.
    """
    try:
        return tuple(int(p) for p in k.split("::")[1].split("."))
    except (ValueError, IndexError):
        return (0,)


def _hou_default_version(base: str, category: str) -> str | None:
    """Ask the LIVE Houdini which version a bare createNode(base) resolves to.

    This mirrors exactly what `create_node` does (Houdini's createNode picks the
    first entry of the type's namespaceOrder()). Returns the versioned name
    (e.g. "polybevel::3.0") or None if Houdini isn't real / the type is unknown.

    Used by node_parms() to ensure query_parms returns params for the SAME
    version create_node will instantiate — closing the polybevel beveltype vs
    offset mismatch.
    """
    if getattr(hou, "_MOCK", False):
        return None
    try:
        categories = hou.nodeTypeCategories()
        cat = categories.get(category) if hasattr(categories, "get") else None
        if cat is None or not hasattr(cat, "nodeType"):
            return None
        nt = cat.nodeType(base)
        if nt is None:
            return None
        order = nt.namespaceOrder()  # ["polybevel::3.0", "polybevel::2.0", ...]
        if order:
            # namespaceOrder()[0] is what createNode uses; it's a qualified name
            # like "polybevel::3.0" (or "::ns::polybevel" for namespaced).
            first = order[0]
            # Strip a leading "::" namespace separator if present.
            return first.lstrip(":") if "::" in first else first
    except Exception:
        return None
    return None


def _node_parms_live(node_type: str, category: str) -> dict[str, Any] | None:
    """Live query against a real Houdini install. Returns None if the type
    isn't found or hou is a mock. Used only as a fallback when the bundled
    manifest doesn't cover the requested type."""
    # Detect mock: MockHou exposes a sentinel attribute.
    if getattr(hou, "_MOCK", False):
        return None
    categories = hou.nodeTypeCategories()
    cat = categories.get(category) if hasattr(categories, "get") else None
    if cat is None:
        return None
    nt = cat.nodeType(node_type) if hasattr(cat, "nodeType") else None
    if nt is None:
        return None
    try:
        group = nt.parmTemplateGroup()
    except Exception:
        return None
    # Resolve to the actual versioned name (e.g. "polybevel::3.0") rather than
    # echoing the bare input — so the agent knows which version it got and can
    # pass it to create_node for consistency.
    try:
        resolved_name = nt.name()
    except Exception:
        resolved_name = node_type
    result = {
        "success": True,
        "node_type": resolved_name,
        "category": category,
        "parms": _flatten_parm_templates(group),
        "source": "live",
        "houdini_version": getattr(hou, "applicationVersionString", lambda: "?")(),
    }
    if resolved_name != node_type:
        result["resolved_from"] = node_type
    return result


def manifest_parm_names(node_type: str) -> set[str] | None:
    """Return the set of valid parm names for a node type per the manifest,
    or None if the manifest/type is unavailable. Used by harness validation to
    decide whether to enforce parm-name checks (None = skip, soft degrade).

    Includes vector component channels (``dirx``/``diry``/...) alongside the
    vector roots (``dir``), so an agent using the per-component API is not
    falsely flagged as a misspelled parm.

    For multiparm-instance templates (name with ``#``) we add the pattern with
    ``#`` replaced by ``1`` (``useapply#`` -> ``useapply1``), the first real
    channel. Note this CANNOT enumerate every valid index; a validator should
    treat a name matching ``<root><digits>`` for a ``<root>#`` template as
    valid (see ``manifest_has_parm`` for index-aware lookup)."""
    manifest = load_node_parms_manifest()
    if manifest is None:
        return None
    node_types = manifest.get("node_types", {})
    _resolved, nt_entry = _resolve_node_type_in_manifest(node_type, node_types)
    if nt_entry is None:
        return None
    names: set[str] = set()
    for p in nt_entry.get("parms", []):
        n = p.get("name")
        if not n:
            continue
        names.add(n)
        # Multiparm-instance template: also admit the first-index channel.
        if "#" in n:
            names.add(n.replace("#", "1"))
        # Expand vector roots to their component channels so both
        # ``parm('dir')`` (tuple) and ``parm('dirx')`` (scalar) are accepted.
        comps = p.get("components")
        if comps:
            names.update(comps)
    return names


def manifest_has_parm(node_type: str, param_name: str) -> bool | None:
    """Index-aware membership test against the parm manifest.

    Returns True/False if the manifest knows the type, or None to soft-degrade
    when the manifest/type is unavailable (so callers can skip enforcement
    rather than false-positive). Handles multiparm-instance channels: a name
    matching ``<root><digits>`` for a ``<root>#`` template is accepted (covers
    ``useapply1`` against the ``useapply#`` template, which the bare set from
    ``manifest_parm_names`` only partially enumerates).

    This is the helper the ``manifest_parm_names`` docstring referenced but
    that was never defined — define it now (Fix 4 wires suggestion logic that
    benefits from the index-aware path, and it closes a dangling reference).
    """
    names = manifest_parm_names(node_type)
    if names is None:
        return None
    if param_name in names:
        return True
    # Multiparm-instance channel: <root># template + digits. Walk the templates
    # and accept any name that is <root> + a non-negative int.
    for tmpl in list(names):
        if "#" in tmpl:
            root = tmpl.replace("#", "")
            if root and param_name.startswith(root):
                tail = param_name[len(root):]
                if tail.isdigit():
                    return True
    return False
