"""Node CRUD, scene queries, script execution, and capture/screenshot helpers.

Imports ``_json_safe`` / ``manifest_parm_names`` / ``_node_parm_inventory``
from ``.manifest`` and ``geometry_inventory`` from ``.geometry_inspect``.

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

from .manifest import (  # noqa: F401
    _json_safe,
    manifest_parm_names,
    _node_parm_inventory,
)
from .geometry_inspect import geometry_inventory  # noqa: F401



def get_scene_info() -> dict[str, Any]:
    """Get an overview of the current Houdini scene."""
    try:
        root = hou.node("/")
        return {
            "success": True,
            "hip_file": hou.hipFile.name() or "(unsaved)",
            "root_children": [n.name() for n in root.children()],
            "total_nodes": len(root.allSubChildren()),
            "current_path": hou.pwd().path() if hou.pwd() else "/",
            "obj_nodes": [n.name() for n in hou.node("/obj").children()] if hou.node("/obj") else [],
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def create_node(
    node_type: str,
    name: str | None = None,
    parent_path: str = "/obj",
) -> dict[str, Any]:
    """Create a new node in the scene.

    Automatically resolves the preferred namespace (e.g. 'copytopoints'
    → 'copytopoints::2.0') to match Tab-menu creation behavior.

    The return value carries a compact ``parms`` inventory of the freshly
    created node — the agent learns each real parm name (e.g. a line SOP's
    ``dist``, not the guessed ``length``) at creation time, with no extra
    ``query_parms`` round-trip. The inventory is read from the live node's
    own ``parmTemplateGroup()``, so it reflects the actual instantiated
    version (no manifest drift). It is best-effort: any failure to read it
    degrades to an empty list rather than failing the create.
    """
    try:
        parent = hou.node(parent_path)
        if parent is None:
            return {"success": False, "error": f"Parent path not found: {parent_path}"}

        node = _create_with_namespace_fallback(parent, node_type, name)
        return {
            "success": True,
            "path": node.path(),
            "name": node.name(),
            "type": node.type().name(),
            "parms": _node_parm_inventory(node),
        }
    except hou.OperationFailed as e:
        return {"success": False, "error": f"Failed to create node '{node_type}': {e}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _create_with_namespace_fallback(parent, node_type: str, name: str | None):
    """Try creating a node with bare type name, falling back to namespace resolution.

    After creation, applies any Tab-menu tool presets by finding matching
    shelf tools and executing their post-creation parameter modifications.
    """
    # Attempt 1: bare name
    node = None
    try:
        node = parent.createNode(node_type, node_name=name if name else None)
    except hou.OperationFailed:
        pass

    # Attempt 2: resolve via namespaceOrder across all categories.
    # Lop is included (Fix 6): a bare 'cylinder' resolves in Lop, but creating
    # a Lop node under a SOP parent still fails — so the Lop entry is mainly
    # consulted by the _LOP_TO_SOP_HINTS branch below to produce a helpful
    # error rather than a bare 'Invalid node type name'.
    if node is None:
        for cat in [
            hou.sopNodeTypeCategory(),
            hou.objNodeTypeCategory(),
            hou.dopNodeTypeCategory(),
            hou.vopNodeTypeCategory(),
            hou.shopNodeTypeCategory(),
            hou.ropNodeTypeCategory(),
            hou.lopNodeTypeCategory(),
        ]:
            nt = hou.nodeType(cat, node_type)
            if nt is not None:
                namespaces = nt.namespaceOrder()
                for ns in namespaces:
                    try:
                        node = parent.createNode(ns, node_name=name if name else None)
                        break
                    except hou.OperationFailed:
                        continue
            if node is not None:
                break

    # All attempts failed — diagnose a Lop-only-type mistake (Fix 6) before
    # re-raising the bare 'Invalid node type name'. 'cylinder' is a Lop type
    # with a SOP equivalent ('tube'); without this hint the chair-log agent
    # had to search_nodes + query_parms to recover.
    if node is None:
        hint = _lop_only_type_hint(parent, node_type)
        if hint is not None:
            raise hou.OperationFailed(hint)
        return parent.createNode(node_type, node_name=name if name else None)

    # Apply Tab-menu presets from matching shelf tool
    _apply_tool_presets(node)
    return node


_LOP_TO_SOP_HINTS: dict[str, str] = {
    "cylinder": "tube",   # 'cylinder' is Lop-only; 'tube' is the SOP primitive
    "cube": "box",        # 'cube' is Lop-only; 'box' is the SOP primitive
    "sphere": "sphere",   # exists in both, but listed for clarity
    "cone": "tube",       # SOP has no cone primitive — tube with one rad=0
}


def _lop_only_type_hint(parent, node_type: str) -> str | None:
    """If `node_type` resolves ONLY in Lop (not the parent's category), return
    an OperationFailed-style message naming the SOP equivalent. Else None.

    Only triggers when the type genuinely doesn't exist for the parent's
    context — so a real Lop parent creating a Lop 'cylinder' is unaffected.
    """
    try:
        bare = node_type.split("::")[0].lower()
        sop_hint = _LOP_TO_SOP_HINTS.get(bare)
        if sop_hint is None:
            return None
        # Confirm the type is actually absent from SOP (don't mis-hint if a SOP
        # version exists under a namespace we didn't try).
        sop_nt = hou.nodeType(hou.sopNodeTypeCategory(), node_type)
        if sop_nt is not None:
            return None  # a SOP version exists; the failure was something else
        lop_nt = hou.nodeType(hou.lopNodeTypeCategory(), node_type)
        if lop_nt is None:
            return None  # not a Lop type either; no specific hint
        return (
            f"'{node_type}' is a Lop (Solaris) node and cannot be created under "
            f"a SOP parent. In SOP context use '{sop_hint}' instead "
            f"(e.g. houdini_create_node(node_type='{sop_hint}')). "
            f"Use search_nodes('{node_type}') to confirm categories."
        )
    except Exception:
        return None


def _init_copytopoints_attribs(node) -> bool:
    """Press Copy-to-Points' ``resettargetattribs`` button to initialize the
    attribute transfer so the target point's attributes (notably ``id``) are
    stamped onto every copied instance.

    Real-H21 mechanism (verified on 21.0.440): the ``targetattribs`` parm is a
    multiparm folder starting at 0 entries (no transfer). The
    ``resettargetattribs`` BUTTON auto-populates it with a default entry that
    copies every non-transform target-point attribute — which already covers
    ``id`` (and ``variant``). So pressing the button is sufficient.

    Kept in node_utils so all node-creation paths share one implementation
    (``node_utils.create_node`` and the recipe rebuild path).

    Best-effort: returns False (never raises) if the button is missing or the
    press fails — the caller already has a usable node; a missing transfer is
    preferable to a failed node creation.
    """
    try:
        reset = node.parm("resettargetattribs")
        if reset is None:
            return False
        reset.pressButton()
        return True
    except Exception:
        return False


def _apply_tool_presets(node) -> None:
    """Apply post-creation parameter presets from shelf tools matching this node type.

    The Tab menu runs shelf tools that often call pressButton() or parm().set()
    after creating the node (e.g. 'resettargetattribs' for copytopoints).
    This function finds matching tools and applies those post-creation actions.

    For Copy-to-Points the shelf-tool path is unreliable across builds, so a
    hardcoded fallback in :func:`_init_copytopoints_attribs` guarantees the
    attribute transfer is initialized regardless of shelf availability.
    """
    import re

    try:
        node_type_name = node.type().name()  # e.g. 'copytopoints::2.0'
    except Exception:
        return

    # Hardcoded Copy-to-Points init: press resettargetattribs so per-instance
    # ids/attrs transfer onto every copied prim. This is the only sanctioned
    # real-H21 path (see harness._setup_copy_apply_attributes). Done here so
    # node_utils.create_node (used by hand-written network_mode scripts) is
    # covered identically to the harness path.
    if node_type_name.split("::")[0].lower() == "copytopoints":
        _init_copytopoints_attribs(node)

    # Build candidate tool name patterns
    # e.g. for 'copytopoints::2.0': 'sop_copytopoints::2.0', 'sop_copytopoints'
    # for 'copytopoints': 'sop_copytopoints'
    base = node_type_name.split('::')[0]
    candidates = []
    for suffix in ['::2.0', '::1.0', '::3.0', '']:
        candidates.append(f'sop_{base}{suffix}')
        candidates.append(f'obj_{base}{suffix}')
        candidates.append(f'dop_{base}{suffix}')

    # Also try the exact node type name
    candidates.insert(0, f'sop_{node_type_name}')

    for tool_name in candidates:
        tool = hou.shelves.tool(tool_name)
        if tool is None:
            continue
        script = tool.script()
        if not script:
            continue

        # Extract post-creation actions: pressButton() and parm().set() calls
        # that appear after node creation (genericTool / createNode)
        lines = script.split('\n')
        in_post_creation = False
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                continue

            # Detect the creation line
            if 'genericTool' in stripped or 'createNode' in stripped:
                in_post_creation = True
                continue

            if not in_post_creation:
                continue

            # pressButton('xxx') or .pressButton()
            pm = re.search(r"\.parm\(['\"]([^'\"]+)['\"]\)\.pressButton\(\)", stripped)
            if pm:
                parm_name = pm.group(1)
                try:
                    p = node.parm(parm_name)
                    if p is not None:
                        p.pressButton()
                except Exception:
                    pass
                continue

            # parm('xxx').set(value)
            sm = re.search(
                r"\.parm\(['\"]([^'\"]+)['\"]\)\.set\((.+?)\)",
                stripped
            )
            if sm:
                parm_name = sm.group(1)
                value_expr = sm.group(2).strip()
                # Try to eval simple literals
                try:
                    import ast
                    value = ast.literal_eval(value_expr)
                except (ValueError, SyntaxError):
                    continue
                try:
                    p = node.parm(parm_name)
                    if p is not None:
                        p.set(value)
                except Exception:
                    pass

        break  # Found and processed first matching tool


def delete_node(node_path: str) -> dict[str, Any]:
    """Delete a node by its full path."""
    try:
        node = hou.node(node_path)
        if node is None:
            return {"success": False, "error": f"Node not found: {node_path}"}
        node.destroy()
        return {"success": True, "path": node_path}
    except Exception as e:
        return {"success": False, "error": str(e)}


def connect_nodes(
    from_path: str,
    to_path: str,
    input_index: int = 0,
    output_index: int = 0,
) -> dict[str, Any]:
    """Connect an output port of one node to an input of another.

    output_index selects which of the source node's output ports to wire from
    (0 = primary output). This matters for Project HDA component subnets, which
    expose multiple outputs: out[0]=main geometry, out[1..n]=anchor/info point
    clouds. A downstream component consumes an upstream anchor by connecting
    with output_index=1. Default 0 preserves the old 2-arg setInput behavior.
    """
    try:
        from_node = hou.node(from_path)
        to_node = hou.node(to_path)
        if from_node is None:
            return {"success": False, "error": f"Source node not found: {from_path}"}
        if to_node is None:
            return {"success": False, "error": f"Destination node not found: {to_path}"}

        to_node.setInput(input_index, from_node, output_index)
        return {
            "success": True,
            "from": from_path,
            "to": to_path,
            "input_index": input_index,
            "output_index": output_index,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def _parm_menu_items(parm) -> list[str] | None:
    """Return the menu tokens for a menu parm, or None if it isn't a menu.

    Real Houdini exposes them via parm.parmTemplate().menuItems(); some menu
    templates also carry a different type tag. We probe defensively so a
    non-menu parm (Float/Int/String) returns None and the caller skips
    coercion entirely. Mock parms lack parmTemplate(), so this returns None
    there too — and since the mock's .set() never raises, coercion is moot.
    """
    try:
        tmpl = parm.parmTemplate()
    except Exception:
        return None
    if tmpl is None:
        return None
    try:
        # Only Menu / String-menu templates have menuItems().
        items = tmpl.menuItems()
    except Exception:
        return None
    if not items:
        return None
    return [str(i) for i in items]


def _coerce_menu_value(parm, value, menu_items: list[str]):
    """Translate an agent-supplied menu value into something .set() accepts.

    Houdini menu parms accept either a valid menu *token* (str) or a numeric
    *index* (int). But agents pass values straight from JSON, where:
      - the manifest's ``default: 0`` round-trips as the string ``"0"``
      - ``set("0")`` is then treated as a token lookup → "Invalid menu item".

    We resolve the value against the known token list:
      1. exact token match            → use the token string
      2. numeric string in index range → use the integer index
      3. already an int in range       → use it as-is
    Returns the coerced value, or None if no mapping was found (caller then
    surfaces a clear error naming the valid tokens).
    """
    # 1. Exact token match (case-sensitive, the Houdini default).
    token = str(value)
    if token in menu_items:
        return token

    # 2. Numeric string / int → interpret as a menu index.
    try:
        idx = int(value)
    except (TypeError, ValueError):
        return None
    if 0 <= idx < len(menu_items):
        return idx
    return None


def _looks_like_expr(value: Any) -> bool:
    """True if value is an HScript expression string (contains ch()).

    Used to route live channel-reference values (e.g. ch("../length")) to
    setExpression instead of .set() — a numeric parm can't .set() a string.

    IMPORTANT: must NOT match VEX/Python code snippets that happen to contain
    ch() calls (e.g. ``float d = ch("distance");``). We exclude multi-line
    strings (code blocks) and strings containing semicolons (statements), so
    only single-line pure expressions like ``ch("../length")`` are treated as
    expressions.
    """
    if not isinstance(value, str):
        return False
    if "ch(" not in value:
        return False
    # Multi-line strings or strings with semicolons are code, not expressions.
    if "\n" in value or ";" in value:
        return False
    return True


def _set_parm_value(parm, value) -> tuple[bool, Any, str | None]:
    """Set a parm value with menu-token coercion fallback.

    Returns (ok, applied_value, error). On a plain .set() success the applied
    value equals the input. If .set() raises a menu error and the parm is a
    menu, we coerce the value (e.g. "0" → index 0 or the matching token) and
    retry once. This absorbs the common "agent sends default-as-string" trap
    without changing behaviour for non-menu parms.
    """
    try:
        parm.set(value)
        return True, value, None
    except Exception as first_err:
        msg = str(first_err)
        # Only attempt coercion when the failure looks menu-related; avoids
        # masking unrelated errors (e.g. type mismatches on Float parms).
        if "menu" not in msg.lower():
            return False, value, msg

        menu_items = _parm_menu_items(parm)
        if not menu_items:
            return False, value, msg

        coerced = _coerce_menu_value(parm, value, menu_items)
        if coerced is None:
            return (
                False,
                value,
                f"{msg}. Valid menu tokens for this parm: {menu_items}",
            )
        try:
            parm.set(coerced)
            return True, coerced, None
        except Exception as second_err:
            return (
                False,
                coerced,
                f"{second_err}. Valid menu tokens for this parm: {menu_items}",
            )


def _apply_one_param(node, param_name: str, value: Any) -> tuple[bool, Any, str | None]:
    """Apply one parameter value to a node (resolved hou.Node).

    Shared dispatch used by BOTH set_param and set_params_batch, so batch and
    single-set have identical capabilities. Supports three value shapes
    (vector / expression / scalar dispatch + menu-token coercion):
      - vector (list/tuple, len > 1): parmTuple; per-component setExpression if
        any component is an expression (ch("../x")), else tuple .set().
      - scalar expression string (contains "ch("): setExpression (Hscript).
      - plain scalar: .set() with menu-token coercion fallback.

    Returns (ok, applied_value, error). `applied_value` is the value actually
    set (may differ from the input for menu coercion, e.g. "0" → 0), so callers
    can report what landed. On failure, error explains why — and now (Fix 4)
    appends a "Did you mean" suggestion from the parm manifest + difflib.
    """
    # Vector parm (list/tuple, >1 component) → parmTuple (handles group names
    # like box "size"/"t" where node.parm("size") is None but parmTuple works).
    if isinstance(value, (list, tuple)) and len(value) > 1:
        pt = node.parmTuple(param_name)
        if pt is None:
            return False, value, _not_found_msg(node, param_name, tuple=True)
        if any(_looks_like_expr(v) for v in value):
            for sub, v in zip(pt, value):
                if _looks_like_expr(v):
                    try:
                        sub.setExpression(v, language=hou.exprLanguage.Hscript)
                    except (AttributeError, TypeError):
                        sub.setExpression(v)
                else:
                    sub.set(v)
        else:
            pt.set(tuple(value))
        return True, list(value), None

    # Scalar expression string → setExpression (numeric parms can't .set() a str).
    if _looks_like_expr(value):
        parm = node.parm(param_name)
        if parm is None:
            return False, value, _not_found_msg(node, param_name)
        try:
            parm.setExpression(value, language=hou.exprLanguage.Hscript)
        except (AttributeError, TypeError):
            parm.setExpression(value)
        return True, value, None

    # Plain scalar → .set() with menu-token coercion fallback.
    parm = node.parm(param_name)
    if parm is None:
        return False, value, _not_found_msg(node, param_name)
    ok, applied, err = _set_parm_value(parm, value)
    if not ok:
        return False, value, err
    return True, applied, None


_PARM_NAME_GOTCHAS: dict[str, dict[str, str]] = {
    # node_type(lowercased, namespace-stripped) -> {wrong_name -> hint}
    "box": {"center": "box has no 'center' parm — use 't' (translate). "
                       "Set via set_param('t', [x,y,z]) or query_parms('box')."},
}


def _not_found_msg(node, param_name: str, *, tuple: bool = False) -> str:
    """Build a 'parameter not found' error enriched with a suggestion.

    Enrichment layers (each best-effort, degrades gracefully):
      1. A documented gotcha for this node type (e.g. box.center → t).
      2. difflib.get_close_matches against the manifest's valid parm names.
      3. A pointer to the query_parms tool.
    If nothing is available (no manifest), the bare 'not found' string is
    returned — identical to pre-Fix-4 behaviour.
    """
    kind = "parameter tuple" if tuple else "parameter"
    base = f"{kind} '{param_name}' not found"
    node_type = _node_type_for_lookup(node)
    extras: list[str] = []

    # 1. Documented gotcha.
    gotcha = _PARM_NAME_GOTCHAS.get(node_type, {}).get(param_name)
    if gotcha:
        extras.append(gotcha)

    # 2. Manifest + difflib fuzzy suggestions.
    suggestions = _suggest_parm_names(node_type, param_name)
    if suggestions:
        extras.append("Did you mean: " + ", ".join(suggestions) + "?")

    # 3. Discovery pointer (always helpful on a miss).
    extras.append(f"Use query_parms(node_type={node_type!r}) to list all parms.")

    if extras:
        return base + ". " + " ".join(extras)
    return base


def _node_type_for_lookup(node) -> str:
    """Lowercased, namespace-stripped node type name for gotcha/manifest lookup.

    'polybevel::3.0' → 'polybevel'. Robust to None / mock nodes.
    """
    try:
        tname = node.type().name()
    except Exception:
        return ""
    return tname.split("::")[0].lower()


def _suggest_parm_names(node_type: str, wrong_name: str) -> list[str]:
    """difflib.get_close_matches against the manifest's valid parm set.

    Returns up to 3 close matches, or [] if the manifest/type is unavailable.
    Degrades to [] when the manifest isn't loaded (offline/test envs) — callers
    just get the bare not-found message, same as before.
    """
    if not node_type or not wrong_name:
        return []
    import difflib
    try:
        valid = manifest_parm_names(node_type)
    except Exception:
        valid = None
    if not valid:
        return []
    matches = difflib.get_close_matches(wrong_name, sorted(valid), n=3, cutoff=0.5)
    return matches


def set_param(node_path: str, param_name: str, value: Any) -> dict[str, Any]:
    """Set a parameter value on a node.

    Three value shapes are supported:
      - scalar (number/string/bool): set via .set(), with menu-token coercion
        fallback (a stringified menu index like "0" is remapped automatically).
      - vector (list/tuple with len > 1): set via parmTuple — e.g. a box's
        ``size`` as [1,2,3]. Components that are expression strings
        (ch("../x")) are routed to per-component setExpression.
      - expression string (contains "ch("): set via setExpression (Hscript) —
        a numeric parm can't .set() a string, so live channel references must
        go through this path. Enables Project HDA's two-layer ch() live params.
    """
    try:
        node = hou.node(node_path)
        if node is None:
            return {"success": False, "error": f"Node not found: {node_path}"}
        ok, applied, err = _apply_one_param(node, param_name, value)
        if not ok:
            return {"success": False, "error": f"{err} on {node_path}"}
        return {"success": True, "path": node_path, "param": param_name, "value": applied}
    except Exception as e:
        return {"success": False, "error": str(e)}


def set_params_batch(node_path: str, params: dict[str, Any]) -> dict[str, Any]:
    """Set multiple parameters on a node in a single call.

    Each value goes through _apply_one_param — the SAME dispatch as set_param —
    so batch sets support vectors (group names like box "size"/"t") AND
    expression strings (ch("../x")), exactly like the single-call path. Menu
    coercion fallback is also preserved (stringified indices succeed).
    """
    try:
        node = hou.node(node_path)
        if node is None:
            return {"success": False, "error": f"Node not found: {node_path}"}

        failed: list[str] = []
        for name, value in params.items():
            ok, _applied, err = _apply_one_param(node, name, value)
            if not ok:
                failed.append(f"{name}: {err}")

        if failed:
            return {
                "success": True,
                "partial": True,
                "set_count": len(params) - len(failed),
                "total_count": len(params),
                "failed_params": failed,
                "warning": f"{len(failed)} parameter(s) could not be set",
            }
        return {
            "success": True,
            "set_count": len(params),
            "total_count": len(params),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_param(node_path: str, param_name: str) -> dict[str, Any]:
    """Read a parameter value from a node."""
    try:
        node = hou.node(node_path)
        if node is None:
            return {"success": False, "error": f"Node not found: {node_path}"}

        parm = node.parm(param_name)
        if parm is None:
            return {"success": False, "error": f"Parameter '{param_name}' not found on {node_path}"}

        return {"success": True, "path": node_path, "param": param_name, "value": _json_safe(parm.eval())}
    except Exception as e:
        return {"success": False, "error": str(e)}


def list_nodes(parent_path: str = "/", type_filter: str | None = None) -> dict[str, Any]:
    """List nodes under a parent path, optionally filtered by type."""
    try:
        parent = hou.node(parent_path)
        if parent is None:
            return {"success": False, "error": f"Path not found: {parent_path}"}

        nodes = []
        for child in parent.children():
            if type_filter and child.type().name() != type_filter:
                continue
            nodes.append({
                "name": child.name(),
                "path": child.path(),
                "type": child.type().name(),
                "input_count": len(child.inputs()),
                "output_count": len(child.outputs()),
            })

        return {"success": True, "parent": parent_path, "node_count": len(nodes), "nodes": nodes}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _serialize_parm_value(parm, value) -> Any:
    """Serialize a parm's value for JSON, handling hou.Ramp specially.

    `get_node_info` (and any path returning live parm values) must not feed a
    raw hou.Ramp into the result dict — ramp params' .eval() returns a hou.Ramp,
    which json.dumps cannot serialize, crashing the WHOLE node-info response
    (not just the ramp parm). A ramp is serialised as its control points so the
    agent sees something useful instead of an opaque str(). Other value types
    go through _json_safe (handles vectors/enums, falls back to str).
    """
    # Detect a ramp parm via its template type (defensive: some mock/test parms
    # have no parmTemplate()).
    try:
        ptype = parm.parmTemplate().type().name()
    except Exception:
        ptype = ""
    if ptype == "Ramp" and value is not None:
        try:
            keys = list(value.keys())
            vals = [_json_safe(v) for v in value.values()]
            return {"__type__": "ramp", "keys": keys, "values": vals}
        except Exception:
            # Ramp API varies across versions; fall back to a count placeholder
            # rather than crashing — the rest of the node is still readable.
            return {"__type__": "ramp", "note": "ramp (control points unavailable)"}
    return _json_safe(value)


def get_node_info(node_path: str) -> dict[str, Any]:
    """Get detailed info about a specific node."""
    try:
        node = hou.node(node_path)
        if node is None:
            return {"success": False, "error": f"Node not found: {node_path}"}

        parms = []
        for p in node.parms():
            parms.append({"name": p.name(), "label": p.description(),
                          "value": _serialize_parm_value(p, p.eval())})

        return {
            "success": True,
            "name": node.name(),
            "path": node.path(),
            "type": node.type().name(),
            "type_description": node.type().description(),
            "inputs": [inp.path() if inp else None for inp in node.inputs()],
            "outputs": [out.path() for out in node.outputs()],
            "parameters": parms,
            "is_time_dependent": node.isTimeDependent(),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def layout_nodes(parent_path: str = "/obj") -> dict[str, Any]:
    """Auto-layout nodes in a network."""
    try:
        parent = hou.node(parent_path)
        if parent is None:
            return {"success": False, "error": f"Path not found: {parent_path}"}
        parent.layoutChildren()
        return {"success": True, "parent": parent_path}
    except Exception as e:
        return {"success": False, "error": str(e)}


def search_nodes(keyword: str) -> dict[str, Any]:
    """Search for available node types by keyword across all categories."""
    try:
        results = []
        keyword_lower = keyword.lower()

        for category_name in hou.nodeTypeCategories().keys():
            category = hou.nodeTypeCategories()[category_name]
            for node_type in category.nodeTypes().values():
                name = node_type.name()
                desc = node_type.description()
                if keyword_lower in name.lower() or keyword_lower in desc.lower():
                    results.append({"name": name, "category": category_name, "description": desc})

        results = results[:20]
        return {"success": True, "keyword": keyword, "match_count": len(results), "results": results}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_help(node_type_name: str) -> dict[str, Any]:
    """Get help documentation for a node type."""
    try:
        found = None
        for category in hou.nodeTypeCategories().values():
            nt = category.nodeType(node_type_name)
            if nt is not None:
                found = nt
                break

        if found is None:
            return {"success": False, "error": f"Node type '{node_type_name}' not found"}

        return {
            "success": True,
            "name": found.name(),
            "category": found.category().name(),
            "description": found.description(),
            "max_inputs": found.maxNumInputs(),
            "min_inputs": found.minNumInputs(),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def _safe_getvalue(stream) -> tuple[str, str | None]:
    try:
        return stream.getvalue(), None
    except Exception as e:
        return "", str(e)


def run_python(code: str) -> dict[str, Any]:
    """Execute arbitrary Python code in Houdini context.

    This is intentionally raw execution. Procedural asset generation should
    prefer harness sandbox tools so failed cooks preserve diagnostics.
    """
    import io
    import sys
    import traceback

    namespace = {"hou": hou, "__builtins__": __builtins__}
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    sys.stdout = stdout_capture
    sys.stderr = stderr_capture

    try:
        exec(code, namespace)
        output, output_error = _safe_getvalue(stdout_capture)
        stderr, stderr_error = _safe_getvalue(stderr_capture)
        capture_errors = [err for err in (output_error, stderr_error) if err]
        if capture_errors:
            return {
                "success": False,
                "error": "; ".join(capture_errors),
                "output": output,
                "stderr": stderr,
                "warning": "Raw houdini_run_python is not sandboxed; failed code may have changed the live scene.",
            }
        return {
            "success": True,
            "output": output or "(no output)",
            "stderr": stderr,
            "warning": "Raw houdini_run_python is not sandboxed; use harness tools for procedural assets.",
        }
    except Exception as e:
        output, _ = _safe_getvalue(stdout_capture)
        stderr, _ = _safe_getvalue(stderr_capture)
        return {
            "success": False,
            "error": str(e),
            "output": output,
            "stderr": stderr,
            "traceback": traceback.format_exc(),
            "warning": "Raw houdini_run_python is not sandboxed; failed code may have changed the live scene.",
        }
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr


def run_vex(
    code: str,
    node_path: str | None = None,
    attrib_name: str = "result",
) -> dict[str, Any]:
    """Execute VEX code by creating a temporary Attribute Wrangle node."""
    try:
        parent = hou.node("/obj")
        if parent is None:
            return {"success": False, "error": "No /obj context"}

        if node_path:
            input_node = hou.node(node_path)
            if input_node is None:
                return {"success": False, "error": f"Input node not found: {node_path}"}
        else:
            input_node = None

        wrangle = parent.createNode("attribwrangle", node_name="edini_temp_wrangle")
        if input_node:
            wrangle.setInput(0, input_node)

        wrangle.parm("snippet").set(code)
        if wrangle.parm("snippet_attribname") is not None:
            wrangle.parm("snippet_attribname").set(attrib_name)

        wrangle.cook(force=True)
        return {
            "success": True,
            "wrangle_path": wrangle.path(),
            "note": "Temporary wrangle created. Remove when done or rename to keep.",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def create_hda(node_path: str, hda_name: str, hda_label: str = "") -> dict[str, Any]:
    """Create an HDA (digital asset) from a node."""
    try:
        node = hou.node(node_path)
        if node is None:
            return {"success": False, "error": f"Node not found: {node_path}"}

        hip_dir = hou.hipFile.dirName()
        if not hip_dir:
            hip_dir = hou.homeHoudiniDirectory()
        save_path = f"{hip_dir}/{hda_name}.hda"

        definition = node.type().definition()
        if definition is None:
            node.createDigitalAsset(name=hda_name, hda_file_name=save_path, description=hda_label)
        else:
            return {"success": False, "error": f"Node is already an HDA: {node_path}"}

        return {
            "success": True,
            "name": hda_name,
            "label": hda_label or hda_name,
            "path": save_path,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def capture_network(
    filepath: str,
    parent_path: str = "/obj",
) -> dict[str, Any]:
    """Capture the node network editor as an image.

    Navigates to the requested parent path, then grabs the Network Editor
    pane tab widget. Returns the image dimensions and filesize.
    """
    try:
        from PySide6.QtWidgets import QApplication
        import os

        desktop = hou.ui.curDesktop()
        editor = desktop.paneTabOfType(hou.paneTabType.NetworkEditor)
        if editor is None:
            return {"success": False, "error": "No Network Editor pane found"}

        # Navigate to the requested parent path
        target = hou.node(parent_path)
        if target is not None:
            editor.setPwd(target)

        QApplication.processEvents()

        # Ensure output directory exists
        os.makedirs(os.path.dirname(os.path.abspath(filepath)) or ".", exist_ok=True)

        # Grab the network editor widget. Houdini 21 removed the
        # NetworkEditor.grab() convenience; the underlying Qt widget must
        # be reached via qtWindow()/qtWidget() (hou.qt). Try several paths
        # in order so this works across H19/H20/H21.
        pixmap = None
        tried: list[str] = []
        grab_candidates = []
        # 1. direct editor.grab() (H19/H20)
        if hasattr(editor, "grab"):
            grab_candidates.append(lambda: editor.grab())
            tried.append("editor.grab")
        # 2. Qt widget via hou.qt (H21 path)
        try:
            from hou import qt as _houqt  # type: ignore
            if hasattr(_houqt, "qtWindow"):
                grab_candidates.append(lambda: _houqt.qtWindow(editor).grab())
                tried.append("hou.qt.qtWindow(editor).grab")
            if hasattr(_houqt, "qtWidget"):
                grab_candidates.append(lambda: _houqt.qtWidget(editor).grab())
                tried.append("hou.qt.qtWidget(editor).grab")
        except Exception:
            pass
        last_err = None
        for grab_fn in grab_candidates:
            try:
                pixmap = grab_fn()
                if pixmap is not None:
                    break
            except Exception as ge:
                last_err = ge
                continue
        if pixmap is None:
            return {
                "success": False,
                "error": (f"Network grab failed: no usable Qt grab API. "
                          f"Tried: {tried}. Last error: {last_err}"),
                "guidance": ("NetworkEditor screenshot is unavailable in this "
                             "Houdini build. Use houdini_capture_review for "
                             "viewport screenshots instead. To verify node "
                             "network structure, use houdini_layout_nodes or "
                             "houdini_list_nodes."),
            }
        pixmap.save(filepath, "PNG")

        if os.path.exists(filepath):
            size_kb = round(os.path.getsize(filepath) / 1024, 1)
            return {
                "success": True,
                "path": filepath,
                "size_kb": size_kb,
                "width": pixmap.width(),
                "height": pixmap.height(),
                "parent_path": parent_path,
            }
        return {"success": False, "error": f"File not created: {filepath}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


_VIEW_TYPE_MAP: dict[str, Any] = {}  # populated lazily in Houdini


def _get_view_type(view_name: str) -> Any:
    """Map a view name string to hou.geometryViewportType enum."""
    if not _VIEW_TYPE_MAP:
        try:
            _VIEW_TYPE_MAP.update({
                "perspective": hou.geometryViewportType.Perspective,
                "top": hou.geometryViewportType.Top,
                "bottom": hou.geometryViewportType.Bottom,
                "front": hou.geometryViewportType.Front,
                "back": hou.geometryViewportType.Back,
                "right": hou.geometryViewportType.Right,
                "left": hou.geometryViewportType.Left,
            })
        except Exception:
            pass
    return _VIEW_TYPE_MAP.get(view_name.lower())


def _trim_white_border(img: Any, threshold: int = 240) -> Any:
    """Auto-crop white/light borders from a PIL image."""
    import numpy as np
    try:
        arr = np.array(img.convert("RGB"))
        # Mask: pixels where all channels are below threshold (not white)
        mask = np.any(arr < threshold, axis=2)
        rows = np.any(mask, axis=1)
        cols = np.any(mask, axis=0)
        if not rows.any() or not cols.any():
            return img  # entirely white — skip
        rmin, rmax = np.where(rows)[0][[0, -1]]
        cmin, cmax = np.where(cols)[0][[0, -1]]
        cropped = img.crop((cmin, rmin, cmax + 1, rmax + 1))
        if cropped.width > 0 and cropped.height > 0:
            return cropped
    except ImportError:
        pass
    except Exception:
        pass
    return img


def _concat_images_grid(
    image_paths: list[str],
    output_path: str,
    columns: int,
    cell_size: tuple[int, int] | None = None,
) -> bool:
    """Concatenate multiple images into a grid using Pillow.

    If cell_size is provided, all images are resized to that exact
    size before pasting — prevents cropping and ensures uniform cells.
    Otherwise uses the largest image dimensions as cell size (legacy).

    Returns True on success, False if Pillow not available or any error.
    """
    try:
        from PIL import Image
    except ImportError:
        return False

    try:
        imgs: list[Image.Image] = []
        for p in image_paths:
            if os.path.exists(p):
                raw = Image.open(p)
                imgs.append(_trim_white_border(raw))
        if not imgs:
            return False

        cols = max(1, min(columns, len(imgs)))
        rows = (len(imgs) + cols - 1) // cols

        # Determine cell dimensions
        if cell_size is not None:
            cell_w, cell_h = cell_size
            # Resize all images to cell size
            resized: list[Image.Image] = []
            for img in imgs:
                if img.width != cell_w or img.height != cell_h:
                    resized.append(img.resize((cell_w, cell_h), Image.LANCZOS))
                    img.close()
                else:
                    resized.append(img)
            imgs = resized
        else:
            cell_w = max(img.width for img in imgs)
            cell_h = max(img.height for img in imgs)

        canvas = Image.new("RGB", (cell_w * cols, cell_h * rows), (30, 30, 30))
        for i, img in enumerate(imgs):
            r, c = i // cols, i % cols
            x, y = c * cell_w, r * cell_h
            # Center in cell (no-op if already resized to cell_w × cell_h)
            ox = (cell_w - img.width) // 2
            oy = (cell_h - img.height) // 2
            canvas.paste(img, (x + ox, y + oy))
            img.close()

        canvas.save(output_path, "PNG")
        canvas.close()
        return True
    except Exception:
        return False


def _target_bounds(target_node: Any) -> Any:
    """Compute a hou.BoundingBox around the target node's cooked geometry.

    Returns None if the bounds cannot be determined. The bounds come from the
    node's own cooked geometry (not the whole viewport), which is what we want
    for tight per-asset framing.
    """
    try:
        geo = target_node.geometry()
        if geo is None:
            return None
    except Exception:
        return None
    # Prefer the geometry's bounding box (a hou.BoundingBox object) so we can
    # hand it to viewport.setViewToBoundingBox directly.
    try:
        bbox = geo.boundingBox()
        # A degenerate/empty bbox (min > max) means no real geometry
        if bbox is not None:
            mn = bbox.minvec()
            mx = bbox.maxvec()
            try:
                if (float(mx[0]) < float(mn[0])
                        or float(mx[1]) < float(mn[1])
                        or float(mx[2]) < float(mn[2])):
                    return None
            except Exception:
                return None
            # Expand by a small epsilon so zero-thickness planes still frame
            for axis in range(3):
                if float(mx[axis]) - float(mn[axis]) < 1e-6:
                    mn_list = list(mn)
                    mx_list = list(mx)
                    mn_list[axis] -= 0.05
                    mx_list[axis] += 0.05
                    # hou.Vector3 is read-only; rebuild via hou.BoundingBox
                    try:
                        import hou as _hou
                        return _hou.BoundingBox(
                            tuple(mn_list), tuple(mx_list))
                    except Exception:
                        return bbox
        return bbox
    except Exception:
        return None


def _frame_to_bounds(
    viewport: Any,
    target_node: Any,
    padding: float = 1.15,
) -> bool:
    """Frame the viewport tightly around the target node's geometry.

    This is the correct way to ensure orthographic (top/front/right) views
    show the COMPLETE model. The old code called `viewport.homeAll()`, which
    frames the entire viewport contents and is affected by the persistent
    pan/zoom state of orthographic cameras — so switching to a Top view after
    a zoomed-in Perspective session would often cut off the model.

    `viewport.setViewToBoundingBox(bbox)` resets the view to fit a specific
    bounding box, which is exactly what we need. We expand the box by
    `padding` (default 1.15× — a little breathing room) so edges aren't
    clipped against the frame.

    Returns True if bounding-box framing succeeded, False if it fell back to
    homeAll() (or that also failed).
    """
    bbox = _target_bounds(target_node)
    if bbox is not None:
        try:
            viewport.setViewToBoundingBox(bbox, 0.0, padding)
            viewport.draw(True, True)
            return True
        except Exception:
            pass
    # Fallback: home everything (less precise but always available)
    try:
        viewport.homeAll()
        viewport.draw(True, True)
        return True
    except Exception:
        return False


def _capture_single_view(
    viewer: Any,
    viewport: Any,
    filepath: str,
    frame: int,
    resolution: tuple[int, int] | None = None,
) -> tuple[bool, str]:
    """Capture a single viewport frame via flipbook. Returns (success, error_detail)."""
    try:
        base_settings = viewer.flipbookSettings()
        settings = base_settings.stash() if hasattr(base_settings, "stash") else base_settings
        settings.output(filepath)
        settings.outputToMPlay(False)
        settings.frameRange((frame, frame))
        if resolution is not None:
            try:
                settings.resolution(resolution)
            except Exception:
                pass
        viewer.flipbook(viewport, settings)
        if os.path.exists(filepath):
            return True, ""
        return False, f"flipbook ran but no file at {filepath}"
    except Exception as e:
        import traceback as _tb
        return False, f"{e}\n{_tb.format_exc()}"


def capture_review(
    filepath: str,
    target_path: str | None = None,
    views: list[str] | None = None,
    frames: list[int] | None = None,
    columns: int = 0,
    shading_mode: str = "smooth",
    home_target: bool = True,
    resolution: tuple[int, int] | None = None,
) -> dict[str, Any]:
    """Capture a review contact sheet — multi-view, multi-frame snapshots.

    Captures each (view × frame) combination as a separate flipbook pass,
    then concatenates all captures into a single grid image using Pillow.

    Args:
        filepath: Output image path (PNG).
        target_path: Node to frame and isolate. Required for predictable results.
        views: View types to capture. Default: ["perspective"].
               Supported: "perspective", "top", "front", "right",
               "bottom", "back", "left".
        frames: Frame numbers to capture. Default: [1].
                Use [1, 10, 20, 30] for a 4-frame time contact sheet.
        columns: Grid columns. 0 = auto (√n rounded up). Default: 0.
        shading_mode: "smooth", "wire", "flat", etc. Default: "smooth".
        home_target: Frame the target before each view capture. Default: True.
        resolution: (width, height) for each cell. None = viewport native.
                    Set to e.g. (960, 540) for consistent quad-view cells.

    Returns:
        {success, path, size_kb, grid: {rows, cols, cells},
         captured: [list of individual file paths]}
    """
    import os
    import uuid
    import tempfile

    filepath = os.path.abspath(filepath)  # resolve relative to Houdini process cwd

    method = "review_capture"
    stage = "initialize"

    if views is None:
        views = ["perspective"]
    if frames is None:
        frames = [1]

    # Validate inputs
    valid_views = {"perspective", "top", "front", "right", "bottom", "back", "left"}
    views = [v.lower() for v in views if v.lower() in valid_views]
    if not views:
        views = ["perspective"]
    frames = sorted(set(frames))
    if not frames:
        frames = [1]

    total_cells = len(views) * len(frames)
    if columns <= 0:
        columns = max(1, int(total_cells ** 0.5 + 0.5)) if total_cells > 1 else 1

    # ── State to restore ──
    _restore_hidden: list[str] = []
    _restore_shading: Any = None
    _restore_view_type: Any = None
    _restore_guides: dict[Any, bool] = {}
    _restore_reference_plane: bool | None = None
    _restore_color_scheme: Any = None

    try:
        stage = "get_viewer"
        desktop = hou.ui.curDesktop()
        viewer = desktop.paneTabOfType(hou.paneTabType.SceneViewer)
        if viewer is None:
            return {"success": False, "error": "No Scene Viewer pane found", "method": method}

        viewport = viewer.curViewport()
        _restore_view_type = viewport.type() if hasattr(viewport, "type") else None

        # ── Shading ──
        try:
            shading_map = {
                "smooth": hou.glShadingType.Smooth,
                "smooth_wire": hou.glShadingType.SmoothWire,
                "flat": hou.glShadingType.Flat,
                "wire": hou.glShadingType.Wire,
            }
            if shading_mode in shading_map:
                vp_settings = viewport.settings()
                display_set = vp_settings.displaySet(hou.displaySetType.DisplayModel)
                _restore_shading = display_set.shadedMode()
                display_set.setShadedMode(shading_map[shading_mode])
        except Exception:
            pass

        # ── Color scheme: switch to Dark (black bg) to prevent white alpha fringing ──
        try:
            _restore_color_scheme = vp_settings.colorScheme()
            vp_settings.setColorScheme(hou.viewportColorScheme.Dark)
        except Exception:
            pass

        # ── Guides: hide grid planes, rulers, gnomon for clean capture ──
        VIEWPORT_GUIDES_TO_HIDE = [
            hou.viewportGuide.XYPlane,
            hou.viewportGuide.XZPlane,
            hou.viewportGuide.YZPlane,
            hou.viewportGuide.OriginGnomon,
            hou.viewportGuide.FloatingGnomon,
            hou.viewportGuide.NodeHandles,
            hou.viewportGuide.ObjectNames,
            hou.viewportGuide.ObjectPaths,
            hou.viewportGuide.SafeArea,
            hou.viewportGuide.CameraMask,
        ]
        for guide in VIEWPORT_GUIDES_TO_HIDE:
            try:
                was_enabled = vp_settings.guideEnabled(guide)
                _restore_guides[guide] = was_enabled
                vp_settings.enableGuide(guide, False)
            except Exception:
                pass
        # Hide grid ruler numbers (distance labels along grid axis)
        try:
            _restore_guides["_ortho_ruler"] = vp_settings.orthoRuler()
            vp_settings.setOrthoRuler(hou.viewportGridRuler.Hide)
        except Exception:
            pass

        # ── Reference Plane: hide (keep ConstructionPlane for visual reference) ──
        try:
            rplane = viewer.referencePlane()
            _restore_reference_plane = rplane.isVisible()
            rplane.setIsVisible(False)
        except Exception:
            pass

        # ── Target ──
        target_node = None
        if target_path:
            target_node = hou.node(target_path)
            if target_node is not None:
                try:
                    target_node.setDisplayFlag(True)
                    target_node.setCurrent(True, clear_all_selected=True)
                except Exception:
                    pass
                try:
                    if hasattr(hou, "setFrame"):
                        hou.setFrame(frames[0])
                except Exception:
                    pass

        # ── Isolate ──
        try:
            if target_node is not None:
                obj = hou.node("/obj")
                if obj is not None:
                    target_path_val = target_node.path()
                    for child in obj.children():
                        child_path = child.path()
                        # Skip: exact match, or ancestor of target (e.g. /obj/bicycle
                        # is ancestor of /obj/bicycle/OUT — hiding it would hide the target)
                        if child_path == target_path_val:
                            continue
                        if target_path_val.startswith(child_path + "/"):
                            continue
                        try:
                            if child.isDisplayFlagSet():
                                child.setDisplayFlag(False)
                                _restore_hidden.append(child_path)
                        except Exception:
                            pass
        except Exception:
            pass

        # ── Prepare output ──
        stage = "prepare_output"
        os.makedirs(os.path.dirname(os.path.abspath(filepath)) or ".", exist_ok=True)

        # ── Capture each cell ──
        stage = "capture_cells"
        tmp_dir = os.path.dirname(os.path.abspath(filepath))
        captured: list[str] = []
        cell_errors: list[str] = []

        for fi, frame in enumerate(frames):
            # Set frame
            try:
                if hasattr(hou, "setFrame"):
                    hou.setFrame(frame)
            except Exception:
                pass

            for vi, view_name in enumerate(views):
                cell_index = fi * len(views) + vi
                tmp_path = os.path.join(tmp_dir, f"_edini_review_{uuid.uuid4().hex[:8]}.png")

                # Change view type
                view_type = _get_view_type(view_name)
                if view_type is not None:
                    try:
                        viewport.changeType(view_type)
                        viewport.draw(True, True)
                    except Exception:
                        pass

                # Frame target: use bounding-box framing so each view (esp.
                # orthographic top/front/right) shows the COMPLETE model.
                # homeAll() alone is unreliable for ortho views — it inherits
                # the previous pan/zoom state and frequently clips the model.
                if home_target and target_node is not None:
                    # Orthographic views benefit from slightly more padding so
                    # thin extents (e.g. a bike's X-width) aren't edge-clipped.
                    ortho_padding = 1.3 if view_name != "perspective" else 1.15
                    _frame_to_bounds(viewport, target_node, padding=ortho_padding)

                # Capture
                ok, err_detail = _capture_single_view(viewer, viewport, tmp_path, frame, resolution)
                if ok:
                    captured.append(tmp_path)
                else:
                    cell_errors.append(f"{view_name}@f{frame}: {err_detail[:120]}")

        # ── Concatenate ──
        stage = "concat"
        if not captured:
            return {
                "success": False,
                "error": f"All {total_cells} captures failed: {', '.join(cell_errors)}" if cell_errors else "No captures succeeded",
                "method": method,
                "stage": stage,
            }

        concat_ok = _concat_images_grid(captured, filepath, columns, resolution)

        # If concatenation failed, keep the first capture as a fallback.
        # MUST happen before the tmp cleanup below — otherwise the file we
        # want to copy has already been removed and the fallback is a no-op.
        if not concat_ok:
            if captured and os.path.exists(captured[0]):
                import shutil
                try:
                    shutil.copy(captured[0], filepath)
                except Exception:
                    pass

        # Clean up temp files
        for tmp_path in captured:
            try:
                if os.path.exists(tmp_path) and tmp_path != filepath:
                    os.remove(tmp_path)
            except Exception:
                pass

        if os.path.exists(filepath):
            size_kb = round(os.path.getsize(filepath) / 1024, 1)
            actual_cols = min(columns, len(captured))
            actual_rows = (len(captured) + actual_cols - 1) // actual_cols
            result = {
                "success": True,
                "path": filepath,
                "size_kb": size_kb,
                "method": method,
                "grid": {"rows": actual_rows, "cols": actual_cols, "cells": len(captured)},
                "captured": captured[:10],  # truncate for tool result size
                "errors": cell_errors[:10] if cell_errors else [],
                "views": views,
                "frames": frames,
            }
            # Attach a per-component geometry inventory so the agent (and the
            # vision model) can cross-check "is this component present but
            # small?" against hard geometry data rather than relying on the
            # screenshot alone. This defeats the recurring failure where vision
            # reports small components (chains, pedals, bolts) as "missing".
            if target_node is not None:
                try:
                    inv = geometry_inventory(target_node.path())
                    if inv.get("success"):
                        result["geometry_inventory"] = inv.get("inventory_text")
                        result["inventory_components"] = inv.get("total_components")
                except Exception:
                    pass
            return result
        return {
            "success": False,
            "error": f"Output file not created: {filepath}",
            "method": method,
            "stage": stage,
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "method": method,
            "stage": stage,
            "traceback": traceback.format_exc(),
        }
    finally:
        # ── Restore state ──
        try:
            if _restore_color_scheme is not None:
                vp_settings.setColorScheme(_restore_color_scheme)
        except Exception:
            pass
        try:
            for guide, was_enabled in _restore_guides.items():
                if isinstance(guide, str):  # _ortho_ruler marker
                    continue
                vp_settings.enableGuide(guide, was_enabled)
        except Exception:
            pass
        try:
            if "_ortho_ruler" in _restore_guides:
                vp_settings.setOrthoRuler(_restore_guides["_ortho_ruler"])
        except Exception:
            pass
        try:
            if _restore_reference_plane is not None:
                viewer.referencePlane().setIsVisible(_restore_reference_plane)
        except Exception:
            pass
        try:
            if _restore_view_type is not None:
                viewport.changeType(_restore_view_type)
        except Exception:
            pass
        try:
            if _restore_hidden:
                for path in _restore_hidden:
                    node = hou.node(path)
                    if node is not None:
                        node.setDisplayFlag(True)
        except Exception:
            pass
        try:
            if _restore_shading is not None:
                vp_settings = viewport.settings()
                display_set = vp_settings.displaySet(hou.displaySetType.DisplayModel)
                display_set.setShadedMode(_restore_shading)
        except Exception:
            pass


def capture_component_detail(
    filepath: str,
    node_path: str,
    component_ids: list[str],
    views: list[str] | None = None,
    shading_mode: str = "smooth",
    resolution: tuple[int, int] | None = None,
) -> dict[str, Any]:
    """Capture close-up screenshots of specific components, one cell per id.

    This solves the recurring "component exists but is too small to see at
    whole-asset viewport resolution" failure (chains, pedals, bolts, small
    trim). For each component_id in `component_ids`, the viewport is framed
    tightly around THAT component's own bounding box and captured, so the
    vision model can actually see it.

    Args:
        filepath: Output grid image path.
        node_path: SOP node carrying the geometry with @component_id.
        component_ids: e.g. ["chain_top", "pedal", "chainring"].
        views: Per-cell view(s). Default ["perspective"]. A single view keeps
            cells large; pass ["perspective","top"] for a 2-view-per-component
            contact sheet.
        shading_mode: Passed through to the viewport display set.
        resolution: Per-cell pixel size.

    Returns: same shape as capture_review (success/path/grid/captured).
    """
    import os as _os
    import uuid as _uuid

    filepath = _os.path.abspath(filepath)
    if views is None:
        views = ["perspective"]
    valid_views = {"perspective", "top", "front", "right", "bottom", "back", "left"}
    views = [v.lower() for v in views if v.lower() in valid_views] or ["perspective"]

    # Resolve per-component bounding boxes from the geometry inventory
    inv = geometry_inventory(node_path)
    if not inv.get("success"):
        return {"success": False, "error": inv.get("error", "inventory failed"),
                "method": "component_detail"}
    if not inv.get("has_component_id"):
        return {"success": False,
                "error": "Geometry has no @component_id attribute — cannot "
                         "isolate components for close-up capture.",
                "method": "component_detail"}

    by_id = {c["component_id"]: c for c in inv["components"]}
    missing = [cid for cid in component_ids if cid not in by_id]
    present = [cid for cid in component_ids if cid in by_id]
    if missing:
        return {
            "success": False,
            "error": (f"component_ids not found in geometry: {missing}. "
                      f"Available: {sorted(by_id)[:20]}"),
            "method": "component_detail",
            "available": sorted(by_id)[:40],
        }
    if not present:
        return {"success": False, "error": "No matching component_ids.",
                "method": "component_detail"}

    _restore_hidden: list[str] = []
    _restore_shading = None
    _restore_view_type = None
    stage = "initialize"

    try:
        stage = "get_viewer"
        desktop = hou.ui.curDesktop()
        viewer = desktop.paneTabOfType(hou.paneTabType.SceneViewer)
        if viewer is None:
            return {"success": False, "error": "No Scene Viewer pane found",
                    "method": "component_detail"}
        viewport = viewer.curViewport()
        _restore_view_type = viewport.type() if hasattr(viewport, "type") else None

        # Shading. The whole block is best-effort: viewport.settings() and
        # the display-set API are H21 UI plumbing that must never abort a
        # capture. (An unguarded viewport.settings() call here previously
        # turned a shading-setup hiccup into a full capture failure at the
        # "get_viewer" stage.)
        try:
            vp_settings = viewport.settings()
            shading_map = {
                "smooth": hou.glShadingType.Smooth,
                "smooth_wire": hou.glShadingType.SmoothWire,
                "wire": hou.glShadingType.Wire,
                "flat": hou.glShadingType.Flat,
            }
            if shading_mode in shading_map:
                display_set = vp_settings.displaySet(hou.displaySetType.DisplayModel)
                _restore_shading = display_set.shadedMode()
                display_set.setShadedMode(shading_map[shading_mode])
        except Exception:
            pass

        # Make the target visible + current, hide other /obj siblings
        target_node = hou.node(node_path)
        if target_node is None:
            return {"success": False, "error": f"Node not found: {node_path}",
                    "method": "component_detail"}
        try:
            target_node.setDisplayFlag(True)
            target_node.setCurrent(True, clear_all_selected=True)
        except Exception:
            pass
        try:
            obj = hou.node("/obj")
            tp = target_node.path()
            for child in obj.children() if obj else []:
                cp = child.path()
                if cp == tp or tp.startswith(cp + "/"):
                    continue
                try:
                    if child.isDisplayFlagSet():
                        child.setDisplayFlag(False)
                        _restore_hidden.append(cp)
                except Exception:
                    pass
        except Exception:
            pass

        _os.makedirs(_os.path.dirname(filepath) or ".", exist_ok=True)
        tmp_dir = _os.path.dirname(filepath)
        captured: list[str] = []
        cell_errors: list[str] = []

        for cid in present:
            comp = by_id[cid]
            bnds = comp.get("bounds")
            if not bnds:
                cell_errors.append(f"{cid}: no bounds")
                continue

            # Build a hou.BoundingBox for this component and frame to it.
            # Use the 6-scalar overload — `hou.BoundingBox(min, max)` with
            # `hou.Vector3(list)` is finicky on H21 about the sequence type it
            # unpacks (historically raised on a plain list, swallowed by the
            # old bare `except` as the opaque "bbox build failed"). Passing
            # explicit floats sidesteps Vector3 entirely and is the documented
            # constructor signature.
            try:
                mn = bnds["min"]
                mx = bnds["max"]
                bbox = hou.BoundingBox(
                    float(mn[0]), float(mn[1]), float(mn[2]),
                    float(mx[0]), float(mx[1]), float(mx[2]),
                )
            except Exception as _bex:
                cell_errors.append(
                    f"{cid}: bbox build failed ({type(_bex).__name__}: {_bex})")
                continue

            for view_name in views:
                tmp_path = _os.path.join(
                    tmp_dir, f"_edini_detail_{_uuid.uuid4().hex[:8]}.png")
                view_type = _get_view_type(view_name)
                if view_type is not None:
                    try:
                        viewport.changeType(view_type)
                    except Exception:
                        pass
                # Frame tightly around THIS component with extra padding so the
                # whole part is centered and clearly visible.
                try:
                    viewport.setViewToBoundingBox(bbox, 0.0, 1.4)
                    viewport.draw(True, True)
                except Exception:
                    try:
                        viewport.homeAll()
                    except Exception:
                        pass
                ok, err = _capture_single_view(
                    viewer, viewport, tmp_path, 1, resolution)
                if ok:
                    captured.append(tmp_path)
                else:
                    cell_errors.append(f"{cid}@{view_name}: {err[:100]}")

        if not captured:
            return {"success": False,
                    "error": f"All captures failed: {cell_errors[:5]}",
                    "method": "component_detail"}

        columns = len(views)
        concat_ok = _concat_images_grid(captured, filepath, columns, resolution)
        # If concatenation failed, keep the first capture as a fallback.
        # MUST happen before the tmp cleanup below — otherwise the file we
        # want to copy has already been removed and the fallback is a no-op.
        if not concat_ok and captured and _os.path.exists(captured[0]):
            import shutil
            try:
                shutil.copy(captured[0], filepath)
            except Exception:
                pass
        for tmp in captured:
            try:
                if _os.path.exists(tmp) and tmp != filepath:
                    _os.remove(tmp)
            except Exception:
                pass

        if not _os.path.exists(filepath):
            return {"success": False, "error": f"Output not created: {filepath}",
                    "method": "component_detail"}

        size_kb = round(_os.path.getsize(filepath) / 1024, 1)
        actual_cols = min(columns, len(captured))
        actual_rows = (len(captured) + actual_cols - 1) // actual_cols
        return {
            "success": True,
            "path": filepath,
            "size_kb": size_kb,
            "method": "component_detail",
            "grid": {"rows": actual_rows, "cols": actual_cols, "cells": len(captured)},
            "captured": captured[:10],
            "errors": cell_errors[:10] if cell_errors else [],
            "components": present,
            "views": views,
        }
    except Exception as e:
        return {"success": False, "error": str(e), "method": "component_detail",
                "stage": stage, "traceback": traceback.format_exc()}
    finally:
        try:
            if _restore_view_type is not None:
                viewport.changeType(_restore_view_type)
        except Exception:
            pass
        try:
            for p in _restore_hidden:
                n = hou.node(p)
                if n is not None:
                    n.setDisplayFlag(True)
        except Exception:
            pass
        try:
            if _restore_shading is not None:
                ds = viewport.settings().displaySet(hou.displaySetType.DisplayModel)
                ds.setShadedMode(_restore_shading)
        except Exception:
            pass


def get_hda_info(hda_name: str) -> dict[str, Any]:
    """Get information about an HDA definition."""
    try:
        definition = hou.hda.definitions().get(hda_name)
        if definition is None:
            return {"success": False, "error": f"HDA '{hda_name}' not found in loaded definitions"}

        return {
            "success": True,
            "name": definition.nodeTypeName(),
            "description": definition.description(),
            "path": definition.libraryFilePath(),
            "version": definition.version(),
            "is_editable": definition.isEditable(),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_selection() -> dict[str, Any]:
    """Get the user's currently selected nodes."""
    try:
        selected = hou.selectedNodes()
        nodes = []
        for n in selected:
            nodes.append({
                "name": n.name(),
                "path": n.path(),
                "type": n.type().name(),
            })
        return {"success": True, "count": len(nodes), "nodes": nodes}
    except Exception as e:
        return {"success": False, "error": str(e)}


def check_errors(node_path: str | None = None) -> dict[str, Any]:
    """Check for Houdini node errors. If node_path given, check that node
    only. Otherwise scan the entire scene."""
    try:
        if node_path:
            node = hou.node(node_path)
            if node is None:
                return {"success": False, "error": f"Node not found: {node_path}"}
            errors = node.errors() or []
            warnings = node.warnings() or []
            return {
                "success": True,
                "path": node_path,
                "error_count": len(errors),
                "warning_count": len(warnings),
                "errors": errors,
                "warnings": warnings,
            }

        # Full scene scan
        error_nodes = []
        warning_nodes = []
        for n in hou.node("/").allSubChildren():
            try:
                errs = n.errors()
                warns = n.warnings()
                if errs:
                    error_nodes.append({"path": n.path(), "errors": errs})
                if warns:
                    warning_nodes.append({"path": n.path(), "warnings": warns})
            except Exception:
                continue

        return {
            "success": True,
            "total_nodes": len(hou.node("/").allSubChildren()),
            "error_nodes": len(error_nodes),
            "warning_nodes": len(warning_nodes),
            "details": error_nodes[:10] + warning_nodes[:10],
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def set_display_flag(node_path: str) -> dict[str, Any]:
    """Set a node as the display/render flag — the node shown in the viewport.

    Tolerates being handed an Object-level node (e.g. a /obj/<geo> container
    from commit_sandbox) which has setDisplayFlag but NO setRenderFlag
    (render flag is a SOP/ROP concept; Object nodes expose it differently).
    Render-flag set is best-effort and never fails the call.
    """
    try:
        node = hou.node(node_path)
        if node is None:
            return {"success": False, "error": f"Node not found: {node_path}"}
        flags_set = {"display": False, "render": False}
        try:
            node.setDisplayFlag(True)
            flags_set["display"] = True
        except Exception:
            pass
        # Render flag is optional — not all node types support it
        # (e.g. ObjNode). Setting it is best-effort.
        try:
            node.setRenderFlag(True)
            flags_set["render"] = True
        except Exception:
            pass
        if not flags_set["display"]:
            return {"success": False, "error":
                    f"Could not set display flag on {node_path} "
                    f"({node.type().name()})"}
        return {"success": True, "path": node_path, "flags": flags_set}
    except Exception as e:
        return {"success": False, "error": str(e)}
