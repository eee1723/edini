"""Generic archetype emitter — realizes a declarative Archetype Spec as a
component's Houdini node network.

A spec is a dict (DATA, not code) — see ``edini/project/archetypes/box_panel.py``.
It lists ``ops`` from a fixed vocabulary the emitter interprets. The emitter
reuses builder's archetype helpers (``_arch_node``, ``_set_archetype_parm``,
``_resolve_archetype_value``) and ``emit_markers``, so spec-built components
inherit EVERY capability of the old hand-coded archetype functions:

- **idempotent rebuild** — deterministic node names via ``_arch_node`` (replace
  on rebuild, no duplication);
- **relative ch() migratability** (Phase 1a) — ``_set_archetype_parm`` →
  ``_relative_path_to_core``, so a spec-built component copied into another
  project still cooks;
- **loud-fail on a bad parm** (P0-2) — ``_apply_one_param`` raises instead of
  silently dropping;
- **marker forwarding** — via ``emit_markers``.

Adding an archetype = adding a spec module under ``edini/project/archetypes/``,
with ZERO emitter changes (the op vocabulary covers the common SOP patterns; a
genuinely novel dynamic becomes a new op, shared by all archetypes). This
replaces ``builder.py``'s hardcoded ``if archetype == "box_panel"`` dispatch.

Op vocabulary
-------------
Each op is a dict with an ``op`` key. Values in an op may reference the agent's
runtime ``params`` with a ``$`` prefix: ``$size`` → ``params['size']``,
``$size.0`` → ``params['size'][0]``, ``$`` alone → the whole params dict. A
referenced param that is absent resolves to ``None`` (so optional ops skip).
Any other value is passed straight through to ``_set_archetype_parm``: a NUMBER
is a literal, a STRING (no ``ch(``) is a design_param name → relative ch(), a
STRING containing ``ch(`` is an expression.

Implemented (Phase 2a):

- ``node``        — create a SOP node {name, type, params:{parm: value}}.
- ``wire_out``    — out_geometry.setInput(0, <named node>)  ({from: name}).
- ``emit_markers``— forward markers to emit_markers  ({markers: "$markers"}).

Planned (Phase 2b — migrating copy_array + tube_graph):

- ``collect_anchors``   — gather the scaffold's ``in_<from>_<anchor>`` nulls
                          into one cloud (merge if >1); register under {as}.
- ``vex_tube_graph``    — detail wrangle building polyline edges between named
                          anchor points (VEX generated from the ``tubes`` param).
- ``init_ctp_attribs``  — make a Copy-to-Points node read @orient/@scale/@N.
"""
from __future__ import annotations

import importlib
import json
import os
import pkgutil
from pathlib import Path
from typing import Any

from edini.project.builder import _arch_node, _set_archetype_parm, emit_markers
from edini.project.ports import OUT_GEOMETRY_NODE


# ── spec loading ─────────────────────────────────────────────────────────
#
# Two registries (Phase 5b):
#   1. Captured specs — JSON data files in ~/.pi/agent/edini-archetypes/<name>.json
#      (written by builder.project_capture_archetype from a built component).
#   2. Package specs — edini/project/archetypes/<name>.py modules exporting SPEC.
# load_spec checks the captured (data) registry FIRST, then the package. Both are
# immediately usable by emit_component. Adding a captured archetype never touches
# the installed package dir.

def _captured_dir() -> Path:
    """Directory for captured (data) archetype specs."""
    base = os.environ.get("USERPROFILE", os.environ.get("HOME", str(Path.home())))
    return Path(base) / ".pi" / "agent" / "edini-archetypes"


def _captured_path(name: str) -> Path:
    return _captured_dir() / f"{name}.json"


def save_captured_spec(name: str, spec: dict) -> Path:
    """Persist a captured archetype spec as a data file. Returns its path."""
    d = _captured_dir()
    d.mkdir(parents=True, exist_ok=True)
    path = _captured_path(name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(spec, f, ensure_ascii=False, indent=2)
    return path


def delete_captured_spec(name: str) -> bool:
    path = _captured_path(name)
    if path.exists():
        path.unlink()
        return True
    return False


def load_spec(archetype: str) -> dict | None:
    """Load an archetype spec by name, or ``None`` if none exists.

    Checks the captured (data) registry first, then the package modules
    (``edini.project.archetypes.<name>`` exporting ``SPEC``).
    """
    # 1. Captured data spec (sidecar).
    cpath = _captured_path(archetype)
    if cpath.exists():
        try:
            with open(cpath, "r", encoding="utf-8") as f:
                spec = json.load(f)
            if isinstance(spec, dict):
                return spec
        except (json.JSONDecodeError, OSError):
            pass
    # 2. Package spec module.
    try:
        mod = importlib.import_module(f"edini.project.archetypes.{archetype}")
    except ModuleNotFoundError:
        return None
    spec = getattr(mod, "SPEC", None)
    return spec if isinstance(spec, dict) else None


def list_archetypes() -> list[str]:
    """Names of all specs — captured (data) + package — sorted."""
    names: set[str] = set()
    cdir = _captured_dir()
    if cdir.exists():
        for f in cdir.glob("*.json"):
            names.add(f.stem)
    from edini.project import archetypes as _pkg
    for _finder, name, _ispkg in pkgutil.iter_modules(_pkg.__path__):
        names.add(name)
    return sorted(names)


def list_captured_archetypes() -> list[dict]:
    """Captured (data) specs as [{name, description, requires_design_params}]."""
    out = []
    cdir = _captured_dir()
    if not cdir.exists():
        return out
    for f in sorted(cdir.glob("*.json")):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                spec = json.load(fh)
            if isinstance(spec, dict):
                out.append({
                    "name": spec.get("archetype", f.stem),
                    "description": spec.get("description", ""),
                    "requires_design_params": spec.get("requires_design_params", []),
                })
        except (json.JSONDecodeError, OSError):
            continue
    return out


# ── value resolution ─────────────────────────────────────────────────────

def _resolve_value(value, params):
    """Resolve a spec value.

    A STRING starting with ``$`` is a reference into the agent's runtime
    params: ``$size`` → ``params['size']``; ``$size.0`` → ``params['size'][0]``;
    ``$`` alone → the whole params dict. Returns ``None`` if the referenced
    param is absent (so optional ops can skip).

    Anything else is returned as-is — a number literal, a design_param name,
    or a ``ch()`` expression — for ``_set_archetype_parm`` to interpret.
    """
    if isinstance(value, str) and value.startswith("$"):
        cur: Any = params
        for part in value[1:].split("."):
            if part == "":
                continue
            try:
                cur = (cur[int(part)] if part.lstrip("-").isdigit()
                       else cur[part])
            except (KeyError, IndexError, TypeError):
                return None
        return cur
    return value


def _validate_params(params: dict, param_specs: dict | None,
                     archetype: str) -> tuple[bool, str | None]:
    """Validate agent params against the spec's ``param_specs`` (loud-fail).

    Restores the per-archetype param-shape validation the old hardcoded
    functions did (e.g. box_panel ``size`` must be a 3-list of numbers or
    design_param names). A spec declares constraints like::

        "param_specs": {
            "size":    {"type": "list", "len": 3, "item": "number_or_name"},
            "markers": {"type": "list", "required": False},
        }

    ``required`` defaults to True for any declared param. ``type`` is one of
    list / number / string / dict; ``len`` constrains a list; ``item``
    constrains list items (number / number_or_name). Returns (ok, error).
    """
    if not param_specs:
        return True, None
    for name, pspec in param_specs.items():
        required = pspec.get("required", True)
        present = name in params and params[name] is not None
        if not present:
            if required:
                return False, (f"{archetype}: required param {name!r} missing "
                               f"(pass it or add a spec default)")
            continue
        val = params[name]
        t = pspec.get("type")
        if t == "list" and not isinstance(val, (list, tuple)):
            return False, (f"{archetype}: param {name!r} must be a list, "
                           f"got {type(val).__name__}")
        if t == "number" and not isinstance(val, (int, float)):
            return False, (f"{archetype}: param {name!r} must be a number, "
                           f"got {type(val).__name__}")
        if t == "string" and not isinstance(val, str):
            return False, (f"{archetype}: param {name!r} must be a string, "
                           f"got {type(val).__name__}")
        if t == "dict" and not isinstance(val, dict):
            return False, (f"{archetype}: param {name!r} must be a dict, "
                           f"got {type(val).__name__}")
        if t == "list":
            ln = pspec.get("len")
            if ln is not None and len(val) != ln:
                return False, (f"{archetype}: param {name!r} must have {ln} "
                               f"items, got {len(val)}")
            item = pspec.get("item")
            for i, v in enumerate(val):
                if item == "number" and not isinstance(v, (int, float)):
                    return False, (f"{archetype}: param {name}[{i}] must be a "
                                   f"number, got {type(v).__name__}")
                if item == "number_or_name" and not isinstance(v, (int, float, str)):
                    return False, (f"{archetype}: param {name}[{i}] must be a "
                                   f"number or design_param name, got {type(v).__name__}")
    return True, None


# ── the emitter ──────────────────────────────────────────────────────────

def emit_component_from_spec(core_node, component_id: str,
                             archetype: str, params: dict | None = None) -> dict:
    """Build a component's geometry from its Archetype Spec.

    Returns ``{success, archetype, component, nodes, markers_built, project}``,
    mirroring the old per-archetype functions' contract so ``emit_component``'s
    callers (and tests) see no shape change.
    """
    spec = load_spec(archetype)
    if spec is None:
        return {"success": False,
                "error": (f"unknown archetype {archetype!r}; spec-backed: "
                          f"{list_archetypes()}")}
    subnet = core_node.node(component_id)
    if subnet is None:
        return {"success": False,
                "error": f"component subnet not found: {component_id}"}
    out_geo = subnet.node(OUT_GEOMETRY_NODE)
    if out_geo is None:
        return {"success": False,
                "error": f"out_geometry not found in {subnet.name()} (scaffold first)"}

    core_path = core_node.path()
    # Merge the spec's defaults with the agent's params (agent wins).
    merged: dict = dict(spec.get("defaults", {}))
    if params:
        merged.update(params)

    # Validate params against the spec's param_specs (loud-fail on a bad shape
    # — restores per-archetype validation like box_panel 'size' must be 3-list).
    ok, verr = _validate_params(merged, spec.get("param_specs"), archetype)
    if not ok:
        return {"success": False, "error": verr}

    ctx = {
        "core": core_node, "subnet": subnet, "core_path": core_path,
        "params": merged, "out_geo": out_geo,
        "nodes": [], "named": {}, "markers_built": [],
    }
    try:
        for op in spec.get("ops", []):
            _interpret_op(op, ctx)
        subnet.layoutChildren()
    except Exception as e:
        return {"success": False,
                "error": f"{archetype!r} archetype failed: {e}"}

    return {"success": True, "archetype": archetype,
            "component": subnet.name(), "nodes": ctx["nodes"],
            "markers_built": ctx["markers_built"], "project": core_path,
            **({"anchor_inputs": ctx["anchor_inputs"]} if "anchor_inputs" in ctx else {}),
            **({"segments": ctx["segments"]} if "segments" in ctx else {})}


# ── op interpreters ──────────────────────────────────────────────────────

def _interpret_op(op: dict, ctx: dict) -> None:
    kind = op.get("op")
    handler = _OPS.get(kind)
    if handler is None:
        raise ValueError(f"unknown op {kind!r} in archetype spec; "
                         f"known: {sorted(_OPS)}")
    handler(op, ctx)


def _op_node(op: dict, ctx: dict) -> None:
    """Create a SOP node, set params, wire inputs, apply tweaks.

    - ``type``: literal node type OR a ``$`` ref (e.g. ``$leaf.type``).
    - ``params``: a dict ``{parm: value}`` OR a ``$`` ref to a dict. Each value
      is a number / design_param name / ``ch()`` expr / list (vector) — passed
      to ``_set_archetype_parm`` (the SAME dispatch hand-built set_param uses).
      A value resolving to ``None`` is skipped (optional parm).
    - ``inputs``: optional ``{idx: <named node>}`` wiring after creation.
    - ``tweaks``: optional ``[{when_type: "tube", set_if_unset: {parm: val}}]``
      — apply a default ONLY if the agent didn't pass that parm (e.g. tube →
      Polygon on H21). Best-effort (parm may not exist on every type).
    - ``init_ctp_attribs``: optional bool — call ``_init_copytopoints_attribs``
      so a Copy-to-Points node reads @orient/@scale/@N.
    """
    name = op["name"]
    node_type = _resolve_value(op["type"], ctx["params"])
    if not node_type:
        raise ValueError(f"node {name!r}: type resolved to empty "
                         f"(op.type={op.get('type')!r})")
    node = _arch_node(ctx["subnet"], node_type, name)
    ctx["named"][name] = node
    ctx["nodes"].append(name)

    # Resolve params (dict literal OR $ref to a dict), then set each value
    # (which may itself be a $ref). Skip None values (optional parms).
    raw_params = _resolve_value(op.get("params", {}), ctx["params"]) or {}
    if not isinstance(raw_params, dict):
        raise ValueError(f"node {name!r}: params must be a dict, got "
                         f"{type(raw_params).__name__}")
    set_parms: set[str] = set()
    for pname, val in raw_params.items():
        resolved = _resolve_value(val, ctx["params"])
        if resolved is None:
            continue
        _set_archetype_parm(node, pname, resolved, ctx["core_path"])
        set_parms.add(pname)

    # Conditional tweaks: set a default ONLY if the agent didn't pass that parm.
    for tweak in (op.get("tweaks") or []):
        when = tweak.get("when_type")
        if when is not None:
            actual = node.type().name().split("::", 1)[0].lower()
            if actual != when.lower():
                continue
        for pname, val in (tweak.get("set_if_unset") or {}).items():
            if pname in set_parms:
                continue
            try:
                _set_archetype_parm(node, pname, val, ctx["core_path"])
                set_parms.add(pname)
            except Exception:
                pass   # tweak is best-effort (parm may not exist on this type)

    # Wire inputs (named refs from earlier ops).
    for idx_str, src_name in (op.get("inputs") or {}).items():
        src = ctx["named"].get(src_name)
        if src is None:
            raise ValueError(f"node {name!r}: input {idx_str} references "
                             f"unknown node {src_name!r}")
        node.setInput(int(idx_str), src)

    if op.get("init_ctp_attribs"):
        try:
            from edini.node_utils import _init_copytopoints_attribs
            _init_copytopoints_attribs(node)
        except Exception:
            pass


def _op_wire_out(op: dict, ctx: dict) -> None:
    """Wire a named node into the component's out_geometry (→ output_0 / OUT)."""
    src = ctx["named"].get(op["from"])
    if src is None:
        raise ValueError(f"wire_out: node {op['from']!r} not defined by an "
                         f"earlier 'node' op")
    ctx["out_geo"].setInput(0, src)


def _op_emit_markers(op: dict, ctx: dict) -> None:
    """Forward markers to emit_markers (so a downstream by_name anchor picks
    them at real positions). No-op if no markers were passed."""
    markers = _resolve_value(op.get("markers", "$"), ctx["params"])
    if not markers:
        return
    res = emit_markers(ctx["core"], ctx["subnet"].name(), markers)
    if not res.get("success"):
        raise ValueError(f"emit_markers failed: {res.get('error')}")
    ctx["markers_built"] = res.get("markers_built", [])


def _op_collect_anchors(op: dict, ctx: dict) -> None:
    """Gather the scaffold's ``in_<from>_<anchor>`` nulls into one cloud (merge
    if >1); register it under ``op['as']`` for downstream ops. Records the
    consumed anchor-input names in ctx (surfaced in the return)."""
    in_nulls = [n for n in ctx["subnet"].children()
                if n.name().startswith("in_") and n.type().name() == "null"]
    if not in_nulls:
        raise ValueError(f"collect_anchors on {ctx['subnet'].name()!r} found no "
                         f"consumed anchors (declare ports.in + ensure the "
                         f"upstream emitted them).")
    ctx["anchor_inputs"] = [n.name() for n in in_nulls]
    if len(in_nulls) == 1:
        ctx["named"][op["as"]] = in_nulls[0]
    else:
        cloud = _arch_node(ctx["subnet"], "merge", op["as"])
        for i, n in enumerate(in_nulls):
            cloud.setInput(i, n)
        ctx["named"][op["as"]] = cloud
        ctx["nodes"].append(op["as"])


def _build_tube_graph_vex(tubes: list[dict]) -> str:
    """Generate a detail-wrangle body that builds polyline edges between named
    anchor points (a tube graph). Uses VEX (not a Python SOP) so there is ZERO
    Python-SOP error surface — the whole reason tube_graph exists."""
    lines = [
        "// tube_graph: build polyline edges between named anchor points.",
        "int __findpt(string nm) {",
        "    for (int i = 0; i < npoints(geoself()); i++) {",
        '        if (pointattrib(geoself(), "name", i, 0) == nm) return i;',
        "    }",
        "    return -1;",
        "}",
    ]
    for seg in tubes:
        a = seg.get("a")
        b = seg.get("b")
        if not a or not b:
            continue
        lines.append("{")
        lines.append(f'    int ia = __findpt("{a}"); int ib = __findpt("{b}");')
        lines.append("    if (ia >= 0 && ib >= 0) {")
        lines.append('        int pr = addprim(geoself(), "polyline");')
        lines.append("        addvertex(geoself(), pr, ia);")
        lines.append("        addvertex(geoself(), pr, ib);")
        lines.append("    }")
        lines.append("}")
    return "\n".join(lines)


def _op_vex_tube_graph(op: dict, ctx: dict) -> None:
    """Create a detail wrangle that builds polyline edges between named anchor
    points. The VEX is generated from the ``tubes`` param. Wires from a named
    source (usually the collect_anchors cloud). Records segment count in ctx."""
    tubes = _resolve_value(op.get("tubes", "$tubes"), ctx["params"])
    if not isinstance(tubes, list) or not tubes:
        raise ValueError("vex_tube_graph needs 'tubes': [{a, b}, ...]")
    src = ctx["named"].get(op["from"]) if op.get("from") else None
    wr = _arch_node(ctx["subnet"], "attribwrangle", op["name"])
    wr.parm("snippet").set(_build_tube_graph_vex(tubes))
    wr.parm("class").set("detail")
    if src is not None:
        wr.setInput(0, src)
    ctx["named"][op["name"]] = wr
    ctx["nodes"].append(op["name"])
    ctx["segments"] = len(tubes)


# Op registry — the full vocabulary (Phase 2b completes it).
_OPS: dict[str, Any] = {
    "node": _op_node,
    "wire_out": _op_wire_out,
    "emit_markers": _op_emit_markers,
    "collect_anchors": _op_collect_anchors,
    "vex_tube_graph": _op_vex_tube_graph,
}
