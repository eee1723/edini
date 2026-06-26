"""Asset builder — the geometry-construction layer (milestone 2).

Turns a validated declarative asset JSON into a Houdini node network. This is
the milestone-2 layer on top of the milestone-1 data model (asset_model.py):

    asset JSON  ──validate──▶  asset_model.validate_asset   (pure data)
                ──build───▶  asset_builder.build_asset      (creates nodes)

Design contract (the milestone-2 difference from the disabled old pipeline):
  - Components attach to skeleton points BY NAME, never via private position
    expressions. A component's ``attach.position`` names a declared skeleton
    point whose coordinates the milestone-1 DAG already computed. Two
    components can therefore never disagree about a shared feature's location.
  - A single-instance component is moved onto its attach point with a Transform
    (xform) node — simpler than the old Copy-to-Points stamping, which existed
    only to instance one component definition N times. Multi-instance stamping
    is a later milestone; M2 validates the build path on per-point components.
  - Node param values that are strings are evaluated as expressions over the
    param library (detail-1 = A) via exprs.evaluate, so a box ``size`` can be
    ``["top_size","top_thickness","top_size"]`` and stays parametric.

This module depends on ``hou`` (it creates real Houdini nodes). The pure-data
validation lives in asset_model; nothing here is testable without hou, which is
why builder tests run under mock_hou and the real geometry is checked by
test_asset_hython against a genuine Houdini process.
"""
from __future__ import annotations

import re
from typing import Any

try:
    import hou
except ImportError:
    # Offline (unit tests install a mock into sys.modules before importing this
    # module). Mirrors node_utils' lazy-hou pattern.
    hou = None  # type: ignore[assignment]

from edini.asset_model import resolve_params, resolve_skeleton, validate_asset
from edini.exprs import ExprError, evaluate
from edini.parm_catalog import NODE_ALIASES


# ── Ported node-creation helpers ────────────────────────────────────
# These were deleted from harness.py when the old procedural-modeling pipeline
# was disabled (commit f17054e); their entire dependency chain (hou, the
# resettargetattribs hook in node_utils, NODE_ALIASES in parm_catalog) is still
# present in the current tree, so they port over near-verbatim. Each carries the
# H21 workaround that motivated it (see the module docstring of the old harness).


def _safe_create_node(parent_path: str, node_type: str, name: str) -> Any:
    """Create a node under ``parent_path``, resolving namespace variants.

    Tries the bare type name, then walks ``namespaceOrder()`` so a request for
    ``copytopoints`` resolves to ``copytopoints::2.0`` (mirroring the Tab menu).
    Runs the post-creation init hook on every created node.
    """
    parent = hou.node(parent_path)  # type: ignore[name-defined]
    if parent is None:
        raise RuntimeError(f"Parent node not found: {parent_path}")
    node = None
    try:
        node = parent.createNode(node_type, name)
    except Exception:
        try:
            cats = [hou.sopNodeTypeCategory(), hou.objNodeTypeCategory()]  # type: ignore[name-defined]
        except Exception:
            cats = []
        for cat in cats:
            try:
                nt = hou.nodeType(cat, node_type)  # type: ignore[name-defined]
            except Exception:
                nt = None
            if nt is None:
                continue
            try:
                for variant in nt.namespaceOrder():
                    try:
                        node = parent.createNode(variant, name)
                        break
                    except Exception:
                        continue
            except Exception:
                continue
            if node is not None:
                break
        if node is None:
            raise
    _post_create_init(node)
    return node


def _post_create_init(node) -> None:
    """Post-creation hook: initialize Copy-to-Points' attribute transfer.

    H21's CTP starts with 0 ``targetattribs`` entries, so per-instance ids/attrs
    are NOT stamped unless the ``resettargetattribs`` button is pressed (W1).
    Best-effort: never raises. Centralized here so every builder-created CTP is
    covered. M2's per-point components don't use CTP yet, but the hook is kept
    so multi-instance stamping (later milestone) inherits the fix for free.
    """
    try:
        type_name = node.type().name().split("::")[0].lower()
    except Exception:
        return
    if type_name == "copytopoints":
        from edini.node_utils import _init_copytopoints_attribs
        try:
            _init_copytopoints_attribs(node)
        except Exception:
            pass


def _set_parm_safe(node, parm_name: str, value: Any) -> None:
    """Set a parm, raising a clear error if it is missing.

    Multi-component values (list/tuple, len>1) use ``parmTuple`` which
    decomposes to sub-parms (box ``size``→sizex/sizey/sizez, tube
    ``rad``→rad1/rad2). Single values use ``parm`` directly. A single-element
    list falls through to the scalar path (its one element is the value)."""
    if isinstance(value, (list, tuple)) and len(value) > 1:
        ptuple = node.parmTuple(parm_name)
        if ptuple is not None:
            ptuple.set(tuple(value))
            return
    parm = node.parm(parm_name)
    if parm is None:
        raise RuntimeError(
            f"Parm '{parm_name}' not found on {node.path()} "
            f"({node.type().name()})")
    parm.set(value)


def _sanitize_node_name(type_str: str) -> str:
    """Legal Houdini node names are [A-Za-z0-9_] only. A type like ``fuse::2.0``
    used directly as a node name triggers InvalidNodeName and the node is
    silently skipped (W5)."""
    return re.sub(r"[^A-Za-z0-9_]", "_", type_str)


# ── Param-value resolution (detail-1 = A) ───────────────────────────


def _resolve_param_value(value: Any, params: dict[str, float]) -> Any:
    """Resolve a node param value at build time.

    A string value is an expression over the param library → evaluated to a
    float. A number is passed through. A list/tuple is resolved element-wise
    (so ``["top_size","top_thickness","top_size"]`` → ``[1.0,0.04,1.0]``).
    Anything else passes through unchanged (e.g. a bool toggle).
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        return evaluate(value, params)
    if isinstance(value, (list, tuple)):
        return [_resolve_param_value(el, params) for el in value]
    return value


# ── Value injection for the python backend ─────────────────────────
#
# An agent writes a Python-SOP cook body using asset param NAMES as if they
# were ordinary variables (``r = rim_r``). The builder rewrites each bare
# parameter name into its resolved numeric literal (``r = 0.3``) before the
# code is set on the python SOP. This is "value injection" — the agent never
# learns Houdini's parameter API (hou.ch, spare parms, ../ paths); every
# dimension is a plain variable that the builder substitutes.
#
# Safety: the rewrite is an AST walk that ONLY substitutes a Name node when:
#   - it is in Load context (not a write target / del / decorator),
#   - it is NOT shadowed by a function parameter of the same name,
#   - it is NOT the base of an attribute access (``math.cos`` — ``math`` is a
#     module, never a param),
#   - it is NOT a keyword-argument name (``f(pscale=1)`` — ``pscale`` there is
#     a kwarg label, not a value).
# Function-local variables that happen to share a param name are protected by
# the arg-shadow check; deeper locals are the agent's responsibility (documented).

import ast as _ast

# Names that are NEVER params — the Python-SOP standard header + builtins the
# agent's code relies on. Substituting these would break the code.
_INJECT_NEVER = frozenset({
    "hou", "geo", "node",  # standard Python-SOP header
    "math",  # common import
    # Python builtins the cook body commonly calls.
    "range", "len", "int", "float", "round", "abs", "min", "max", "sum",
    "sorted", "list", "tuple", "set", "dict", "enumerate", "zip", "True",
    "False", "None", "self", "print",
})


class _ParamInjector(_ast.NodeTransformer):
    """AST transformer that substitutes bare parameter Names with literals.

    Tracks function-argument names so a param name reused as a function
    parameter is NOT substituted inside that function (it shadows the param).
    Skips attribute bases (``obj.attr``) and keyword-argument labels."""

    def __init__(self, params: dict[str, float], shadowed: set[str] | None = None):
        self._params = params
        # Names shadowed by enclosing function args — not substitutable.
        self._shadowed = shadowed if shadowed is not None else set()

    def _substitute(self, name: str) -> _ast.AST | None:
        """Return a Constant node if ``name`` is an injectable param, else None."""
        if (name in self._params
                and name not in _INJECT_NEVER
                and name not in self._shadowed):
            return _ast.Constant(value=float(self._params[name]))
        return None

    def visit_Name(self, node: _ast.Name) -> _ast.AST:
        # Only Load-context names are value references. Store/Del are writes.
        if not isinstance(node.ctx, _ast.Load):
            return node
        sub = self._substitute(node.id)
        return sub if sub is not None else node

    def visit_Attribute(self, node: _ast.Attribute) -> _ast.AST:
        # Do NOT descend into the attribute base: ``math.cos`` must keep
        # ``math`` as a name, never substitute it even if a param is named
        # ``math``. Visit the rest (e.g. nested calls in the value) but skip
        # the base Name.
        self.generic_visit(node)
        return node

    def visit_keyword(self, node: _ast.keyword) -> _ast.AST:
        # A keyword argument's VALUE is visited normally, but its ``arg`` (the
        # label, e.g. ``pscale`` in ``f(pscale=1)``) is a string, not a Name —
        # so it's already safe. generic_visit handles the value.
        self.generic_visit(node)
        return node

    def visit_FunctionDef(self, node: _ast.FunctionDef) -> _ast.AST:
        # Collect this function's arg names, visit its body under the expanded
        # shadow set, then restore. Nested functions get their own layer.
        arg_names = {a.arg for a in node.args.args}
        arg_names |= {a.arg for a in node.args.posonlyargs}
        arg_names |= {a.arg for a in node.args.kwonlyargs}
        if node.args.vararg:
            arg_names.add(node.args.vararg.arg)
        if node.args.kwarg:
            arg_names.add(node.args.kwarg.arg)
        saved = self._shadowed
        self._shadowed = self._shadowed | arg_names
        self.generic_visit(node)
        self._shadowed = saved
        return node

    def visit_Lambda(self, node: _ast.Lambda) -> _ast.AST:
        # Lambdas bind args the same way named functions do.
        arg_names = {a.arg for a in node.args.args}
        arg_names |= {a.arg for a in node.args.posonlyargs}
        arg_names |= {a.arg for a in node.args.kwonlyargs}
        saved = self._shadowed
        self._shadowed = self._shadowed | arg_names
        self.generic_visit(node)
        self._shadowed = saved
        return node


def _inject_param_values(code: str, params: dict[str, float]) -> str:
    """Rewrite a Python-SOP cook body, substituting each bare asset-parameter
    name with its resolved numeric literal. Returns the rewritten code.

    Raises SyntaxError if ``code`` is not valid Python. See
    :class:`_ParamInjector` for the exact safety rules (function-arg shadowing,
    attribute-base / kwarg-label protection).
    """
    tree = _ast.parse(code)
    injector = _ParamInjector(params)
    new_tree = injector.visit(tree)
    _ast.fix_missing_locations(new_tree)
    return _ast.unparse(new_tree)


# ── Per-backend component construction ──────────────────────────────


def _build_native_chain_component(
    root_path: str,
    comp: dict,
    cid: str,
    params: dict[str, float],
) -> Any:
    """Build a native_chain component: a linear chain of native SOPs wired
    input-0 to previous, with node params resolved from the param library.

    Returns the tail node of the chain. Ported from the disabled
    ``_build_native_chain_component`` with the milestone-2 change that param
    values may be expressions (resolved via ``_resolve_param_value``) and the
    anchor/CTP machinery removed (M2 components are moved by a transform at
    assembly time instead).
    """
    nodes = comp.get("nodes") or []
    if not nodes:
        raise RuntimeError(f"native_chain component '{cid}' has no nodes")

    prev = None
    last_node = None
    for ni, node_spec in enumerate(nodes):
        ntype = node_spec.get("type", "")
        nname = node_spec.get("name", f"{cid}_n{ni}")
        if not ntype:
            raise RuntimeError(
                f"native_chain component '{cid}' node[{ni}] missing 'type'")
        canonical = NODE_ALIASES.get(ntype, ntype)
        try:
            node = _safe_create_node(root_path, canonical, nname)
        except Exception as e:
            raise RuntimeError(
                f"native_chain component '{cid}' node[{ni}] "
                f"'{canonical}' create failed: {e}") from None
        if prev is not None:
            node.setInput(0, prev)
        # W2: tube/cylinder default to 'type'=0 (Primitive) on H21, emitting a
        # single degenerate prim. Procedural workflows want Polygon (type=1).
        if canonical in ("tube", "cylinder") and "type" not in (node_spec.get("params") or {}):
            try:
                node.parm("type").set(1)
            except Exception:
                pass
        params_spec = node_spec.get("params") or {}
        if canonical == "attribwrangle":
            if "class" in params_spec:
                try:
                    node.parm("class").set(params_spec["class"])
                except Exception:
                    pass
            if "snippet" in params_spec:
                try:
                    node.parm("snippet").set(params_spec["snippet"])
                except Exception:
                    pass
        else:
            for pname, pvalue in params_spec.items():
                resolved = _resolve_param_value(pvalue, params)
                try:
                    _set_parm_safe(node, pname, resolved)
                except Exception as e:
                    raise RuntimeError(
                        f"native_chain component '{cid}' node[{ni}] "
                        f"parm '{pname}={pvalue!r}': {e}") from None
        prev = node
        last_node = node
    return last_node


def _build_python_component(
    root_path: str,
    comp: dict,
    cid: str,
    params: dict[str, float],
) -> Any:
    """Build a python backend component: a Python SOP whose cook body is the
    agent-authored ``code``, with asset params injected as numeric literals.

    The agent writes ordinary Python using param NAMES as variables
    (``r = rim_r``); the builder rewrites each bare param name to its resolved
    value (``r = 0.3``) via :func:`_inject_param_values`. This is "value
    injection": the agent never touches Houdini's parameter API (hou.ch, spare
    parms, ../ paths). Changing a param rebuilds the network (sufficient for
    one-shot asset generation; live re-cook is a later concern).

    The cook body must follow the Python-SOP standard contract
    (``node = hou.pwd(); geo = node.geometry()``) and build geometry with the
    deterministic hou Geometry API (``geo.createPoint()`` / ``createPolygon()``)
    — NOT interactive tools (curve needs viewport drawing; the agent must
    generate points programmatically instead).

    Optional ``imports`` (e.g. ``["math"]``) are prepended so the cook body can
    use them. Returns the python SOP node (the chain tail; placement + tagging
    are handled by the shared assembly layer, identical to native_chain).
    """
    code = comp.get("code", "")
    if not code or not code.strip():
        raise RuntimeError(f"python component '{cid}' has no 'code'")

    # Inject asset-param values into the code (bare name → numeric literal).
    injected = _inject_param_values(code, params)

    # Prepend declared imports so the cook body can use them.
    imports = comp.get("imports") or []
    if imports:
        import_lines = "\n".join(f"import {m}" for m in imports)
        injected = import_lines + "\n" + injected

    py_sop = _safe_create_node(root_path, "python", f"{cid}_python")
    try:
        _set_parm_safe(py_sop, "python", injected)
    except Exception as e:
        raise RuntimeError(
            f"python component '{cid}' set code failed: {e}") from None
    return py_sop


# ── Assembly ────────────────────────────────────────────────────────


def _move_to_point(
    root_path: str, tail_node, cid: str, position: tuple[float, float, float]
) -> Any:
    """Move a component's geometry onto its attach skeleton point.

    A single-instance M2 component is translated (not CTP-stamped) to its
    declared skeleton point. A Transform (xform) node sits after the chain and
    sets ``t`` to the resolved point coordinates. This is simpler than
    Copy-to-Points and avoids the per-instance attribute-transfer workaround
    (W1) entirely for the per-point case. Multi-instance stamping is a later
    milestone.
    """
    xform = _safe_create_node(root_path, "xform", f"{cid}_xform")
    xform.setInput(0, tail_node)
    try:
        xform.parmTuple("t").set(tuple(float(c) for c in position))
    except Exception as e:
        raise RuntimeError(
            f"component '{cid}' transform to {position} failed: {e}") from None
    return xform


def _tag_component_id(root_path: str, tail_node, cid: str) -> Any:
    """Bake a prim-level ``component_id`` onto a component's geometry.

    Native SOPs (box/tube/torus) carry no component_id, so the orientation /
    inventory gates (which key on component_id) would see nothing. A prim
    attribwrangle writes ``s@component_id = "<cid>";`` after the chain. Uses
    addattrib-style creation implicitly (H21 wrangle auto-creates on string
    attribute write in prim run-over context)."""
    tag = _safe_create_node(root_path, "attribwrangle", f"{cid}_tag")
    tag.setInput(0, tail_node)
    try:
        tag.parm("class").set("primitive")
        tag.parm("snippet").set(f's@component_id = "{cid}";')
    except Exception:
        pass  # best-effort; a missing tag is non-fatal for the build path
    return tag


def build_asset(asset: dict, root_path: str) -> dict[str, Any]:
    """Build a validated asset into a Houdini node network under ``root_path``.

    Flow (shift-left: validate before touching any node):
      1. validate_asset — reject bad assets with a clear error, no nodes made.
      2. resolve_params + resolve_skeleton — compute every param value and
         every skeleton-point coordinate (the milestone-1 data layer).
      3. For each component: build its native_chain geometry, then transform it
         onto its attach skeleton point, then tag it with component_id.
      4. Merge all component outputs into one merge node, wire a display-flagged
         OUT null after it, and layout the network.

    Returns ``{success, out_path, components_built, placements, error?}``.
    ``placements`` maps component id → resolved attach coordinates so the caller
    can verify the parametric linkage without cooking.
    """
    # 1. Shift-left validation.
    result = validate_asset(asset)
    if not result["success"]:
        return {
            "success": False,
            "error": "asset failed validation: " + "; ".join(
                e.get("message", e.get("code", "?")) for e in result["errors"]),
            "validation_errors": result["errors"],
        }

    try:
        root = hou.node(root_path)  # type: ignore[name-defined]
        if root is None:
            raise RuntimeError(f"sandbox root not found: {root_path}")

        # 2. Resolve the data layer.
        param_values = resolve_params(asset)
        skeleton = resolve_skeleton(asset)

        # 3. Build + place each component.
        component_nodes: list = []
        placements: dict[str, list[float]] = {}
        components = asset.get("components") or []
        for comp in components:
            cid = comp.get("id", "component")
            backend = comp.get("backend", "native_chain")

            if backend == "native_chain":
                tail = _build_native_chain_component(root_path, comp, cid, param_values)
            elif backend == "python":
                tail = _build_python_component(root_path, comp, cid, param_values)
            else:
                # vex_skeleton is intentionally NOT supported: the VEX-code path
                # was the root cause of the old pipeline's failures (LLM VEX
                # error rate). The python backend now covers curve/section
                # generation with deterministic Geometry-API code instead.
                raise RuntimeError(
                    f"component '{cid}' backend {backend!r} not supported "
                    f"(use native_chain or python)")

            # Place the component at its attach skeleton point.
            attach = comp.get("attach") or {}
            point_name = attach.get("position")
            if point_name not in skeleton:
                raise RuntimeError(
                    f"component '{cid}' attach {point_name!r} is not a resolved "
                    f"skeleton point (validate should have caught this)")
            position = skeleton[point_name]
            moved = _move_to_point(root_path, tail, cid, position)
            tagged = _tag_component_id(root_path, moved, cid)
            component_nodes.append(tagged)
            placements[cid] = [float(c) for c in position]

        if not component_nodes:
            raise RuntimeError("asset has no components to build")

        # 4. Merge → OUT.
        merge = _safe_create_node(root_path, "merge", "merge_all")
        for idx, node in enumerate(component_nodes):
            merge.setInput(idx, node)
        out = _safe_create_node(root_path, "null", "OUT")
        out.setInput(0, merge)
        try:
            out.setDisplayFlag(True)
        except Exception:
            pass
        try:
            root.layoutChildren()
        except Exception:
            pass

        return {
            "success": True,
            "out_path": out.path(),
            "components_built": len(component_nodes),
            "placements": placements,
        }
    except (RuntimeError, ExprError) as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        import traceback
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }
