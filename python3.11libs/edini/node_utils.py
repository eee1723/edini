"""Houdini node operation utilities.

Pure houp wrappers. No UI dependencies. All functions return
JSON-serializable dicts with {"success": bool, ...} shape.
"""
from __future__ import annotations

import os
import json
import re
import traceback

try:
    import hou
except ImportError:
    # Houdini runtime not available (e.g. offline manifest queries / unit
    # tests install a mock into sys.modules before importing this module).
    hou = None  # type: ignore[assignment]
from typing import Any


# ---------------------------------------------------------------------------
# Scene / Node Operations
# ---------------------------------------------------------------------------

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


# ── Lop-only node-type diagnosis (Fix 6) ─────────────────────────────────
# Some node type names exist only in the Lop (Solaris) category while a SOP
# equivalent with a different name does the same job in SOP context. Map the
# common ones so a failed create_node under a SOP parent returns a useful hint
# instead of a bare 'Invalid node type name'.
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
    (mirrors assembly_builder._set_parm + node_utils menu coercion):
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


# ── Parameter-name suggestions (Fix 4) ───────────────────────────────────
# A few node types have a documented common gotcha where the agent's memorized
# name is wrong. Surface those explicitly first (deterministic, high-signal),
# then fall back to manifest + difflib fuzzy match.
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


# ---------------------------------------------------------------------------
# Query / Search Operations
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Node Type Parameter Manifest (C-station)
# ---------------------------------------------------------------------------
# A pre-generated, version-pinned catalogue of every SOP node type's
# parameters (name/type/label/default/menu_items). Generated once against a
# real Houdini install and committed to the repo, so:
#   - `node_parms()` (the houdini_node_parms tool) reads it with zero runtime
#     cost and no Houdini dependency — always accurate for the pinned version.
#   - harness `_validate_recipe` uses it to reject misspelled postprocess parm
#     names at build time (before any node is created).
# See scripts/generate_node_parms_manifest.py for the generator.

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


# Cap on how many parm entries the create_node inventory surfaces. Past this we
# truncate and report the total, so a heavyweight node's full parm sheet can't
# bloat the create response. Most primitive/modifier SOPs the agent creates in a
# modeling loop have well under this many user-facing parms.
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


# Third-party / plugin / asset namespaces excluded from the manifest by default.
# These are large, environment-specific (installed plugins, user HDAs), and
# irrelevant to procedural recipe building. Built-in versioned nodes
# (copytopoints::2.0, polybevel::3.0) are KEPT because their prefix is the
# bare SOP base name, which isn't in this set.
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


# ── Type-specific gotcha hints (Round-3 Fix D3 + general) ────────────────
# Some node types have a documented default that bites agents who don't read
# it. tube defaults to type=prim (a single primitive), so copytopoints copies
# only the anchor points, not the tube — session 3 produced 4-point "legs".
# Map the common offenders so query_parms surfaces the gotcha proactively.
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


def _vector_to_list(value) -> list[float]:
    try:
        return [float(value[0]), float(value[1]), float(value[2])]
    except Exception:
        return [float(value.x()), float(value.y()), float(value.z())]


def _geometry_bounds(geo) -> dict[str, list[float]] | None:
    try:
        raw = geo.intrinsicValue("bounds")
        if raw is not None and len(raw) == 6:
            mn = [float(raw[0]), float(raw[2]), float(raw[4])]
            mx = [float(raw[1]), float(raw[3]), float(raw[5])]
            return {
                "min": mn,
                "max": mx,
                "size": [mx[0] - mn[0], mx[1] - mn[1], mx[2] - mn[2]],
            }
    except Exception:
        pass

    try:
        bbox = geo.boundingBox()
        if bbox is None:
            return None
        mn = _vector_to_list(bbox.minvec())
        mx = _vector_to_list(bbox.maxvec())
        return {
            "min": mn,
            "max": mx,
            "size": [mx[0] - mn[0], mx[1] - mn[1], mx[2] - mn[2]],
        }
    except Exception:
        return None


def inspect_geometry(node_path: str) -> dict[str, Any]:
    """Inspect the geometry output of a SOP node."""
    try:
        node = hou.node(node_path)
        if node is None:
            return {"success": False, "error": f"Node not found: {node_path}"}

        geo = node.geometry()
        if geo is None:
            return {"success": False, "error": f"No geometry on {node_path}"}

        attribs = []
        for attr in geo.pointAttribs():
            attribs.append({"name": attr.name(), "type": str(attr.dataType()), "class": "point"})
        for attr in geo.primAttribs():
            attribs.append({"name": attr.name(), "type": str(attr.dataType()), "class": "prim"})
        for attr in geo.vertexAttribs():
            attribs.append({"name": attr.name(), "type": str(attr.dataType()), "class": "vertex"})
        for attr in geo.globalAttribs():
            attribs.append({"name": attr.name(), "type": str(attr.dataType()), "class": "detail"})

        return {
            "success": True,
            "path": node_path,
            "point_count": geo.intrinsicValue("pointcount"),
            "prim_count": geo.intrinsicValue("primitivecount"),
            "vertex_count": geo.intrinsicValue("vertexcount"),
            "attributes": attribs,
            "bounds": _geometry_bounds(geo),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def _component_bounds(geo, prim_subset) -> dict[str, Any] | None:
    """Compute bounds + centroid for a subset of prims of a geometry."""
    xs: list[float] = []
    ys: list[float] = []
    zs: list[float] = []
    for prim in prim_subset:
        for vtx in prim.vertices():
            p = vtx.point().position()
            xs.append(float(p[0])); ys.append(float(p[1])); zs.append(float(p[2]))
    if not xs:
        return None
    mn = (min(xs), min(ys), min(zs))
    mx = (max(xs), max(ys), max(zs))
    centroid = (sum(xs) / len(xs), sum(ys) / len(ys), sum(zs) / len(zs))
    return {
        "bounds": {"min": list(mn), "max": list(mx),
                   "size": [mx[i] - mn[i] for i in range(3)]},
        "centroid": [round(c, 4) for c in centroid],
    }


def geometry_inventory(node_path: str, max_components: int = 60) -> dict[str, Any]:
    """Build a per-component_id inventory of the geometry on a node.

    For each distinct `component_id` prim-attribute value, report:
      - prim_count, point_count (unique vertices)
      - bounds (min/max/size) and centroid
      - size relative to the whole-asset diagonal (fraction), so the caller can
        spot components that are present but tiny (the recurring "chain/pedals
        exist but vision reports them missing" failure).

    Returns {success, node_path, total_components, components: [...],
             whole_bounds, inventory_text}.
    `inventory_text` is a compact human-readable block meant to be fed to a
    vision model alongside a screenshot for cross-validation.
    """
    try:
        node = hou.node(node_path)
        if node is None:
            return {"success": False, "error": f"Node not found: {node_path}"}
        geo = node.geometry()
        if geo is None:
            return {"success": False, "error": f"No geometry on {node_path}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

    comp_attr = geo.findPrimAttrib("component_id")
    if comp_attr is None:
        # No component_id — fall back to a single whole-geometry entry
        bounds = _geometry_bounds(geo)
        return {
            "success": True,
            "node_path": node_path,
            "total_components": 0,
            "has_component_id": False,
            "whole_bounds": bounds,
            "inventory_text": (
                "(no @component_id attribute on this geometry; cannot break "
                "down per-component. Whole geometry bounds shown above.)"
            ),
        }

    # Bucket prims by component_id value
    buckets: dict[str, list] = {}
    for prim in geo.prims():
        try:
            cid = str(prim.stringAttribValue("component_id"))
        except Exception:
            cid = ""
        if not cid:
            cid = "(unlabeled)"
        buckets.setdefault(cid, []).append(prim)

    # Whole-asset diagonal for relative-size computation
    whole = _geometry_bounds(geo)
    whole_diag = 1.0
    if whole and whole.get("size"):
        s = whole["size"]
        whole_diag = max(1e-6, (s[0] ** 2 + s[1] ** 2 + s[2] ** 2) ** 0.5)

    components: list[dict[str, Any]] = []
    for cid in sorted(buckets.keys()):
        prims = buckets[cid]
        info = _component_bounds(geo, prims) or {
            "bounds": None, "centroid": [0, 0, 0]}
        seen_pts: set[int] = set()
        for prim in prims:
            for vtx in prim.vertices():
                seen_pts.add(vtx.point().number())
        size = info["bounds"]["size"] if info.get("bounds") else [0, 0, 0]
        diag = (size[0] ** 2 + size[1] ** 2 + size[2] ** 2) ** 0.5
        components.append({
            "component_id": cid,
            "prim_count": len(prims),
            "point_count": len(seen_pts),
            "bounds": info["bounds"],
            "centroid": info["centroid"],
            "size_fraction": round(diag / whole_diag, 4),
        })
        if len(components) >= max_components:
            break

    # Compact text for vision cross-validation
    lines = ["GEOMETRY_INVENTORY (component_id -> prim_count, size_fraction of whole):"]
    for c in components:
        flag = "  <-- SMALL" if c["size_fraction"] < 0.08 else ""
        lines.append(
            f"  {c['component_id']}: {c['prim_count']} prims, "
            f"{c['point_count']} pts, size={c['size_fraction']}{flag}"
        )
    inventory_text = "\n".join(lines)

    return {
        "success": True,
        "node_path": node_path,
        "has_component_id": True,
        "total_components": len(buckets),
        "components": components,
        "whole_bounds": whole,
        "inventory_text": inventory_text,
    }


def _edge_key(a: int, b: int) -> tuple[int, int]:
    """Canonical undirected edge key from two point numbers."""
    return (a, b) if a <= b else (b, a)


# Two-tier severity for inspect_geometry_health. BLOCKING checks gate
# overall_ok (and thus commit); ADVISORY checks are reported but never block.
_HEALTH_BLOCKING_CHECKS = ("orphan_points", "open_curves")
_HEALTH_ADVISORY_CHECKS = (
    "degenerate_prims",
    "nonmanifold_edges",
    "open_boundary_edges",
    "coincident_points",
)


def inspect_geometry_health(
    node_path: str,
    degenerate_area_eps: float = 1e-7,
    coincident_eps: float = 1e-6,
    max_coincident_report: int = 20,
) -> dict[str, Any]:
    """Run structural health checks on a node's cooked geometry.

    Detects problems that viewport screenshots CANNOT reveal but that silently
    break procedural assets (and downstream sims/booleans/renders):

      - orphan_points:   points not referenced by any primitive
      - open_curves:     open (non-closed) curve primitives — usually stray
                         construction curves that should have been deleted
      - degenerate_prims: polygons/faces with ~zero area (slivers, colinear)
      - nonmanifold_edges: edges shared by 3+ polygons (bad topology)
      - open_boundary_edges: edges shared by exactly 1 polygon (holes in what
                         should be a closed surface)
      - coincident_points: distinct points within `coincident_eps` of each other
                         (duplicates that Fuse would merge)

    Each finding includes a `fix` recommendation naming the SOP to use.

    **Two-tier severity** (see _HEALTH_BLOCKING_CHECKS / _HEALTH_ADVISORY_CHECKS):
      - BLOCKING (gate overall_ok + commit): orphan_points, open_curves.
        These are unambiguous defects that always warrant a fix.
      - ADVISORY (reported, never block): degenerate_prims, nonmanifold_edges,
        open_boundary_edges, coincident_points. These are routinely tolerated
        or EXPECTED (open_boundary_edges on open surfaces like terrain or an
        intentional gateway opening). Treating them as blocking produced false
        ``overall_ok=False`` on clean geometry and drove rebuild loops.

    Returns {success, node_path, summary, checks: {...}, overall_ok,
    blocking_checks, advisory_checks}. ``overall_ok`` is True only if every
    BLOCKING check passes; ADVISORY findings never affect it. Each check also
    carries a ``severity`` field.
    """
    try:
        node = hou.node(node_path)
        if node is None:
            return {"success": False, "error": f"Node not found: {node_path}"}
        geo = node.geometry()
        if geo is None:
            return {"success": False, "error": f"No geometry on {node_path}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

    points = geo.points()
    prims = geo.prims()
    n_points = len(points)
    n_prims = len(prims)

    # ── Orphan points: points referenced by no prim ──
    referenced_pts: set[int] = set()
    for prim in prims:
        # Use prim.vertices() which works for polygons; curve prims also have
        # vertices. Guard per-prim to avoid one bad prim aborting the scan.
        try:
            for vtx in prim.vertices():
                referenced_pts.add(vtx.point().number())
        except Exception:
            continue
    orphan_pt_nums = [p.number() for p in points if p.number() not in referenced_pts]
    orphan_points = {
        "count": len(orphan_pt_nums),
        "sample": orphan_pt_nums[: max(0, max_coincident_report)],
        "passed": len(orphan_pt_nums) == 0,
        "fix": ("Delete orphans with a Blast/Delete SOP targeting unreferenced "
                "points, or add a Fuse SOP (Consolidate Points) to merge them."),
    }

    # ── Open curves: curve primitives that are not closed ──
    open_curve_prims: list[int] = []
    for prim in prims:
        try:
            # Prim type name: 'Poly', 'PolyLine'/'Mesh', 'NURBSCurve',
            # 'BezierCurve', etc. Anything curve-like that isn't closed is a
            # stray construction curve in a procedural asset.
            type_name = prim.type().name().lower()
            is_curve = ("curve" in type_name) or (type_name == "polyline")
            if is_curve and hasattr(prim, "isClosed") and not prim.isClosed():
                open_curve_prims.append(prim.number())
        except Exception:
            continue
    open_curves = {
        "count": len(open_curve_prims),
        "sample": open_curve_prims[:max_coincident_report],
        "passed": len(open_curve_prims) == 0,
        "fix": ("Open curves are usually leftover construction geometry. "
                "Blast them, or convert to closed polygons. They cause "
                "errors in Boolean/Sweep and pollute renders."),
    }

    # ── Degenerate prims: zero-area polygons ──
    # Area is obtained from the Houdini-native "measuredarea" intrinsic (the
    # true polygon area for polygons AND n-gons), falling back to a corrected
    # shoelace that sums the triangle fan over ALL vertices (not just the
    # first three). This fixes two prior defects that produced false positives
    # on legitimate tube/fan caps: (a) comparing 0.5*|cross|² (== 2·area²,
    # NOT area) against the eps, and (b) sampling only the first three verts.
    degenerate_prims: list[int] = []

    def _shoelace_fan_area(vts) -> float:
        # Sum of |cross(e0i, e0j)| / 2 over consecutive vertex pairs around a
        # reference vertex 0 — the true signed area for planar/convex faces.
        if len(vts) < 3:
            return 0.0
        p0 = vts[0].point().position()
        total = 0.0
        for k in range(1, len(vts) - 1):
            p1 = vts[k].point().position()
            p2 = vts[k + 1].point().position()
            e01 = (p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2])
            e02 = (p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2])
            cross = (
                e01[1] * e02[2] - e01[2] * e02[1],
                e01[2] * e02[0] - e01[0] * e02[2],
                e01[0] * e02[1] - e01[1] * e02[0],
            )
            mag = (cross[0] ** 2 + cross[1] ** 2 + cross[2] ** 2) ** 0.5
            total += 0.5 * mag
        return total

    for prim in prims:
        try:
            type_name = prim.type().name().lower()
            if "poly" not in type_name:
                continue  # only polygonal area is meaningful here
            verts = prim.vertices()
            if len(verts) < 3:
                degenerate_prims.append(prim.number())
                continue
            # Prefer the native measuredarea intrinsic (accurate for n-gons).
            area = None
            try:
                area = float(prim.intrinsicValue("measuredarea"))
            except Exception:
                area = None
            if area is None:
                area = _shoelace_fan_area(verts)
            if area < degenerate_area_eps:
                degenerate_prims.append(prim.number())
        except Exception:
            continue
    degenerate = {
        "count": len(degenerate_prims),
        "sample": degenerate_prims[:max_coincident_report],
        "passed": len(degenerate_prims) == 0,
        "fix": ("Use a Clean SOP (Remove Degenerate Faces) or Delete SOP by "
                "the listed primitive numbers. Degenerate faces break normals "
                "and subdivision."),
    }

    # ── Edge valence: open boundary (1) and non-manifold (3+) edges ──
    edge_counts: dict[tuple[int, int], int] = {}
    for prim in prims:
        try:
            verts = prim.vertices()
            n = len(verts)
            if n < 2:
                continue
            for i in range(n):
                a = verts[i].point().number()
                b = verts[(i + 1) % n].point().number()
                if a == b:
                    continue
                key = _edge_key(a, b)
                edge_counts[key] = edge_counts.get(key, 0) + 1
        except Exception:
            continue
    open_boundary = [list(k) for k, c in edge_counts.items() if c == 1]
    nonmanifold = [list(k) for k, c in edge_counts.items() if c >= 3]
    open_boundary_edges = {
        "count": len(open_boundary),
        "sample": open_boundary[:max_coincident_report],
        "passed": len(open_boundary) == 0,
        "note": ("An open boundary edge belongs to exactly one polygon. This "
                 "is EXPECTED for open surfaces (terrain, cloth, a single "
                 "panel) but flags holes in what should be a closed solid."),
        "fix": ("If the asset should be closed: cap holes with a PolyFill or "
                "Cap SOP. If it's intentionally open, ignore."),
    }
    nonmanifold_edges = {
        "count": len(nonmanifold),
        "sample": nonmanifold[:max_coincident_report],
        "passed": len(nonmanifold) == 0,
        "fix": ("Non-manifold edges (shared by 3+ polygons) are always bad. "
                "Find and remove the extra polygons; a Clean SOP helps. These "
                "break Boolean operations and simulations."),
    }

    # ── Coincident points (O(n^2) — skip for very large point counts) ──
    coincident_pairs: list[list[int]] = []
    if n_points <= 4000:
        positions = [(p.number(), p.position()) for p in points]
        eps2 = coincident_eps * coincident_eps
        for i in range(len(positions)):
            na, pa = positions[i]
            for j in range(i + 1, len(positions)):
                nb, pb = positions[j]
                dx = pa[0] - pb[0]; dy = pa[1] - pb[1]; dz = pa[2] - pb[2]
                if dx * dx + dy * dy + dz * dz < eps2:
                    coincident_pairs.append([na, nb])
                    if len(coincident_pairs) >= max_coincident_report:
                        break
            if len(coincident_pairs) >= max_coincident_report:
                break
    coincident = {
        "count": len(coincident_pairs),
        "sample": coincident_pairs[:max_coincident_report],
        "skipped_large_pointcount": n_points > 4000,
        "passed": len(coincident_pairs) == 0,
        "fix": ("Run a Fuse SOP (Consolidate Points) to merge coincident "
                "points. Unmerged duplicates break Copy-to-Points, shading, "
                "and attribute interpolation."),
    }

    checks = {
        "orphan_points": orphan_points,
        "open_curves": open_curves,
        "degenerate_prims": degenerate,
        "nonmanifold_edges": nonmanifold_edges,
        "open_boundary_edges": open_boundary_edges,
        "coincident_points": coincident,
    }

    # Two-tier severity: BLOCKING checks gate commit; ADVISORY checks are
    # reported but never flip overall_ok. Rationale (from production runs):
    # non-manifold edges and coincident points are routinely tolerated, and
    # open_boundary_edges are EXPECTED on open surfaces (terrain, a single
    # panel, an intentional gateway opening). Treating them as blocking made
    # overall_ok report false on geometry that was already clean, which drove
    # agents into rebuild loops over non-defects. Only orphan points and stray
    # open curves are unambiguous defects that always warrant a fix.
    for cname in _HEALTH_BLOCKING_CHECKS:
        if cname in checks:
            checks[cname]["severity"] = "blocking"
    for cname in _HEALTH_ADVISORY_CHECKS:
        if cname in checks:
            checks[cname]["severity"] = "advisory"

    overall_ok = all(
        checks[c]["passed"] for c in _HEALTH_BLOCKING_CHECKS if c in checks
    )

    return {
        "success": True,
        "node_path": node_path,
        "point_count": n_points,
        "prim_count": n_prims,
        "overall_ok": overall_ok,
        "blocking_checks": [c for c in _HEALTH_BLOCKING_CHECKS if c in checks],
        "advisory_checks": [c for c in _HEALTH_ADVISORY_CHECKS if c in checks],
        "summary": {
            name: c["count"] for name, c in checks.items()
        },
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# Script / HDA Operations
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Capture Operations
#
# Use capture_review() and capture_network() below.
# capture_viewport() and capture_viewport_safe() have been removed;
# single-frame captures are handled by capture_review(views=["perspective"]).
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Review Capture — multi-view + frame-range contact sheets
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Context / Inspection Operations
# ---------------------------------------------------------------------------

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



# ---------------------------------------------------------------------------
# Orientation Verification (PCA-based) — math lives in edini.orientation_math
# ---------------------------------------------------------------------------

from edini.orientation_math import (
    AXIS_VECTORS as _AXIS_VECTORS,
    KIND_EIGEN_RANK as _KIND_EIGEN_RANK,
    compute_covariance as _compute_covariance,
    jacobi_eigen_3x3 as _jacobi_eigen_3x3,
    axis_angle_between as _axis_angle_between,
    dominant_axis_name as _dominant_axis_name,
    flip_to_hemisphere as _flip_to_hemisphere,
    dominant_axis_name as _axis_name_of,  # alias for construction-path reuse
)


def verify_orientation(
    node_path: str,
    checks: list[dict],
) -> dict[str, Any]:
    """Verify component orientations via PCA on point positions.

    Each check dict:
        {
            "component_id": "wheel_front",
            "kind": "radial" | "elongated" | "planar",
            "expected_axis": "X" | "Y" | "Z" | "-X" | "-Y" | "-Z",
            "tolerance_deg": 15,
            "signed": false
        }

    For each component:
      - Gather points where prim attribute `component_id` == check's component_id
      - Compute 3x3 position covariance + centroid
      - Jacobi eigendecomposition -> 3 eigenvectors (ascending eigenvalues)
      - Pick eigenvector by kind:
          radial / planar -> smallest eigenvalue's vector (symmetry axis / normal)
          elongated       -> largest eigenvalue's vector (long axis)
      - Compare to expected axis; emit pass/fail + fix quaternion

    Returns:
        {success, passed, failed, total, checks: [...]}
    """
    try:
        node = hou.node(node_path)
        if node is None:
            return {"success": False, "error": f"Node not found: {node_path}"}
        geo = node.geometry()
        if geo is None:
            return {"success": False, "error": f"No geometry on {node_path}"}

        comp_attr = geo.findPrimAttrib("component_id")
        if comp_attr is None:
            return {
                "success": False,
                "error": (
                    "Primitive attribute `component_id` not found. "
                    "Assign @component_id per component in the generator "
                    "(geo.addAttrib(hou.attribType.Prim, 'component_id', '') "
                    "before creating geometry)."
                ),
            }

        results: list[dict] = []
        passed = failed = 0

        for chk in checks:
            cid = chk.get("component_id")
            kind = chk.get("kind", "radial").lower()
            expected_axis = chk.get("expected_axis", "Y").upper()
            tol_deg = float(chk.get("tolerance_deg", 15.0))
            signed_kind = bool(chk.get("signed", False))

            entry: dict[str, Any] = {
                "component_id": cid,
                "kind": kind,
                "expected_axis": expected_axis,
                "tolerance_deg": tol_deg,
                "signed": signed_kind,
                "passed": False,
            }

            if kind not in _KIND_EIGEN_RANK:
                entry["error"] = f"Unknown kind: {kind}"
                results.append(entry); failed += 1; continue
            if expected_axis not in _AXIS_VECTORS:
                entry["error"] = f"Invalid expected_axis: {expected_axis}"
                results.append(entry); failed += 1; continue

            comp_prims = [
                p for p in geo.prims()
                if str(p.stringAttribValue("component_id")) == cid
            ]
            if not comp_prims:
                entry["error"] = (
                    f"No prims with component_id={cid!r}. "
                    f"Available: {sorted(set(str(p.stringAttribValue('component_id')) for p in geo.prims() if p.stringAttribValue('component_id')))[:10]}"
                )
                results.append(entry); failed += 1; continue

            seen_pts = set()
            pts: list[tuple[float, float, float]] = []
            for prim in comp_prims:
                for vtx in prim.vertices():
                    pt = vtx.point()
                    pid = pt.number()
                    if pid in seen_pts:
                        continue
                    seen_pts.add(pid)
                    pos = pt.position()
                    pts.append((float(pos[0]), float(pos[1]), float(pos[2])))

            # ── B-station: construction-axis fast path ──
            # If the builder baked `edini_world_axis` onto these prims
            # (deterministic derivation from construction_axis + anchor @orient),
            # read it directly and SKIP PCA. This is ground truth, not an
            # estimate, so it supersedes the point-distribution-based path.
            # We still run an OPTIONAL PCA crosscheck when enough points exist:
            # a large divergence means the agent's declared construction axis
            # disagrees with the geometry it actually emitted (caught here as a
            # WARNING, not a failure — PCA is noisy, the construction axis is
            # the authority).
            #
            # Round-3 Fix D2: an explicit per-check `construction_axis` token
            # (X/Y/Z/-X/-Y/-Z) OVERRIDES the baked attr for THIS check. This
            # honors the tool's documented parameter (which the backend
            # previously ignored when a bake existed — the session-3 L87 trap):
            # it lets the agent verify against a hypothetical without rebuilding,
            # and falls back to it when no bake is present either.
            world_axis_attr = geo.findPrimAttrib("edini_world_axis")
            has_world_axis = world_axis_attr is not None
            construction_vec: tuple[float, float, float] | None = None
            construction_source = None  # 'baked' | 'override' — for diagnostics
            # 1) Explicit per-check override takes precedence.
            override_axis = chk.get("construction_axis")
            if override_axis is not None and override_axis in _AXIS_VECTORS:
                construction_vec = _AXIS_VECTORS[override_axis]
                construction_source = "override"
            # 2) Otherwise read the baked prim attr (the scaffold's ground truth).
            if construction_vec is None and has_world_axis:
                try:
                    raw = comp_prims[0].floatListAttribValue("edini_world_axis") \
                        if hasattr(comp_prims[0], "floatListAttribValue") \
                        else None
                except Exception:
                    raw = None
                if raw is None or len(raw) < 3:
                    # Fallback: some mock/attrib backends expose tuple access.
                    try:
                        raw = comp_prims[0].attribValue("edini_world_axis")
                        if not isinstance(raw, (list, tuple)) or len(raw) < 3:
                            raw = None
                    except Exception:
                        raw = None
                if raw is not None:
                    construction_vec = (
                        float(raw[0]), float(raw[1]), float(raw[2]))
                    construction_source = "baked"

            if construction_vec is not None:
                # Deterministic construction path.
                detected_vec = construction_vec
                expected_vec = _AXIS_VECTORS[expected_axis]
                if not signed_kind:
                    detected_vec = _flip_to_hemisphere(detected_vec, expected_vec)
                detected_axis = _dominant_axis_name(detected_vec)
                angle_deg, fix_q = _axis_angle_between(
                    detected_vec, expected_vec, signed=signed_kind)
                passed_check = angle_deg <= tol_deg

                entry.update({
                    "method": "construction",
                    "point_count": len(pts),
                    "detected_axis": detected_axis,
                    "detected_vector": [round(c, 4) for c in detected_vec],
                    "world_axis_baked": [round(c, 4) for c in construction_vec],
                    "axis_source": construction_source,  # 'override' | 'baked'
                    "angle_error_deg": round(angle_deg, 2),
                    "passed": passed_check,
                })

                # Optional PCA crosscheck (warning-only). Catches the case
                # where the declared construction axis disagrees with the
                # actual emitted geometry — e.g. agent said construction_axis:Y
                # but the wheel code generates an X-symmetric ring.
                if len(pts) >= 4:
                    try:
                        cov, _ = _compute_covariance(pts)
                        eigs, vecs = _jacobi_eigen_3x3(cov)
                        pca_vec = vecs[_KIND_EIGEN_RANK[kind]]
                        if not signed_kind:
                            pca_vec = _flip_to_hemisphere(pca_vec, construction_vec)
                        pca_angle, _ = _axis_angle_between(
                            pca_vec, construction_vec, signed=False)
                        entry["pca_crosscheck"] = {
                            "pca_axis": _dominant_axis_name(pca_vec),
                            "divergence_deg": round(pca_angle, 2),
                        }
                        # 2x tolerance = clearly inconsistent, surface as warning.
                        if pca_angle > 2.0 * tol_deg:
                            entry["pca_crosscheck"]["warning"] = (
                                f"Declared construction axis ({detected_axis}) "
                                f"diverges from PCA estimate "
                                f"({_dominant_axis_name(pca_vec)}) by "
                                f"{round(pca_angle, 1)}°. The construction axis "
                                f"is authoritative (passed), but this suggests "
                                f"the component code emits geometry whose "
                                f"distribution disagrees with the declared axis. "
                                f"Verify the construction_axis value matches "
                                f"how the geometry is actually generated."
                            )
                    except Exception:
                        pass

                if not passed_check:
                    kind_hint = {
                        "radial": "rotational symmetry axis (axle)",
                        "planar": "surface normal",
                        "elongated": "long axis",
                    }[kind]
                    entry["hint"] = (
                        f"{cid} {kind_hint} baked as world axis {detected_axis} "
                        f"({[round(c,2) for c in detected_vec]}). "
                        f"Expected {expected_axis}. This is a deterministic "
                        f"construction-axis mismatch — fix the component's "
                        f"construction_axis or the anchor @orient in the recipe "
                        f"(do NOT apply a post-hoc quaternion; the bake is "
                        f"ground truth)."
                    )

                results.append(entry)
                if passed_check:
                    passed += 1
                else:
                    failed += 1
                continue

            # ── No edini_world_axis baked (PCA fallback REMOVED, decision 3) ──
            # The PCA estimation path was removed because it misclassifies
            # elongated cylinders (the hub 90° bug): PCA picks the inertia axis,
            # which for a radially-symmetric tube is the length axis, not the
            # radial axle the assert expects. With the fallback gone there is no
            # estimation path left, so a prim without a baked axis fails
            # outright and points the agent at the fix: the asset must be built
            # by a builder that bakes edini_world_axis from the declared
            # construction_axis, or, if the component genuinely has no
            # construction axis, the orientation_assert should be removed.
            entry.update({
                "method": "no_axis",
                "point_count": len(pts),
                "passed": False,
                "error": (
                    f"{cid} has no valid edini_world_axis prim attribute "
                    f"(a NON-ZERO 3-float unit vector, read as "
                    f"floatListAttribValue — NOT a string like \"y\"). "
                    f"Bake it with an attribwrangle (class=primitive): "
                    f"v@edini_world_axis = {{0,1,0}};  // construction axis. "
                    f"A builder is NOT required — any valid baked axis vector "
                    f"passes. Or remove this orientation_assert if the component "
                    f"has no meaningful construction axis."
                ),
            })
            results.append(entry)
            failed += 1

        return {
            "success": True,
            "node_path": node_path,
            "passed": passed,
            "failed": failed,
            "total": len(checks),
            "checks": results,
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"{e}\n{traceback.format_exc()}",
        }


def verify_parametric(
    node_path: str,
    core_path: str,
    param: str,
    new_value: float,
    expected_axis: str | None = None,
    min_relative_change: float = 0.05,
) -> dict[str, Any]:
    """Prove a design param actually drives the geometry (the LIVE guarantee).

    This is the cure for the "declare done prematurely" failure (session log 2,
    the road bike): the agent declared the model complete after `inspect_health`
    returned `overall_ok`, but never verified that changing a param actually
    moved the geometry. `overall_ok` only proves "not broken right now"; it does
    NOT prove "parametric". This tool proves parametric by PERTURBATION:

      1. Read the target node's current geometry (bbox size + point/prim count).
      2. Set the core's design param to ``new_value``.
      3. Force-recook the target node.
      4. Read the perturbed geometry.
      5. Assert: geometry non-empty, no new cook errors, and at least one bbox
         axis changed by >= ``min_relative_change`` (the param propagated to the
         geometry). If ``expected_axis`` is given (X/Y/Z), THAT axis MUST change.
      6. ALWAYS restore the param to its original value (never mutate the user's
         scene as a side effect of a check).

    Args:
        node_path: the node whose geometry proves parametricity (usually the
            project's OUT node).
        core_path: the edini::project HDA core carrying the design param.
        param: design param name on the core (e.g. "length").
        new_value: the perturbation value (should be meaningfully different from
            the current value; a sanity check rejects no-op perturbations).
        expected_axis: optional "X"/"Y"/"Z" — if given, this axis MUST change.
        min_relative_change: minimum |Δsize|/|size| for an axis to count as
            "changed" (default 5%, guards against float noise).

    Returns:
        {success, passed, param, original_value, new_value, restored,
         before:{sizes,points,prims}, after:{...}, axis_changes:{X,Y,Z},
         reason}
    """
    try:
        node = hou.node(node_path)
        if node is None:
            return {"success": False, "error": f"Node not found: {node_path}"}
        core = hou.node(core_path)
        if core is None:
            return {"success": False, "error": f"Core not found: {core_path}"}
        parm = core.parm(param)
        if parm is None:
            return {"success": False,
                    "error": f"Param {param!r} not found on {core_path}"}

        def _snapshot():
            """Read bbox sizes (X/Y/Z), point count, prim count of `node`."""
            g = node.geometry()
            if g is None:
                return None
            bb = g.boundingBox()
            mn = _vector_to_list(bb.minvec())
            mx = _vector_to_list(bb.maxvec())
            return {
                "sizes": [mx[0] - mn[0], mx[1] - mn[1], mx[2] - mn[2]],
                "points": len(g.points()),
                "prims": len(g.prims()),
            }

        original_value = parm.eval()
        # Reject a no-op perturbation — it would always "pass" vacuously and
        # teach the agent the wrong lesson.
        try:
            if abs(float(new_value) - float(original_value)) < 1e-9:
                return {"success": False,
                        "error": (f"new_value {new_value} equals the current "
                                  f"value {original_value}; pick a perturbation "
                                  f"that actually differs to prove parametricity")}
        except (TypeError, ValueError):
            return {"success": False,
                    "error": f"new_value must be numeric, got {new_value!r}"}

        before = _snapshot()
        if before is None:
            return {"success": False,
                    "error": f"No geometry on {node_path} before perturbation"}

        # ── Perturb + recook ──
        # The restore is GUARANTEED via try/finally: if cook/_snapshot/errors
        # raise, the finally still puts the param back. Without this, a cook
        # error mid-verification (the exact failure this tool exists to detect)
        # would silently mutate the user's scene — violating the docstring's
        # "ALWAYS restore" contract. (session-logs-analysis C2 audit.)
        # `_restored` is set ONLY when the finally has actually run, so the
        # outer except can report the param's true state to the agent.
        after = None
        errors: list[str] = []
        _restored = False
        try:
            parm.set(new_value)
            node.cook(force=True)
            after = _snapshot()
            # Capture errors AFTER the recook (this catches broken ch() chains
            # that silently produce zero geometry — the session-log "promote
            # returns 0 / nothing moves" failure).
            errors = list(node.errors() or [])
        finally:
            parm.set(original_value)
            node.cook(force=True)
            _restored = True

        if after is None:
            return {"success": True, "passed": False,
                    "param": param, "original_value": original_value,
                    "new_value": new_value, "restored": True,
                    "before": before, "after": None,
                    "reason": f"geometry vanished after perturbing {param}"}
        if errors:
            return {"success": True, "passed": False,
                    "param": param, "original_value": original_value,
                    "new_value": new_value, "restored": True,
                    "before": before, "after": after,
                    "errors": errors,
                    "reason": f"cook errors after perturbing {param}: {errors}"}
        if after["points"] == 0:
            return {"success": True, "passed": False,
                    "param": param, "original_value": original_value,
                    "new_value": new_value, "restored": True,
                    "before": before, "after": after,
                    "reason": f"zero points after perturbing {param}"}

        # ── Per-axis relative change ──
        axis_labels = ["X", "Y", "Z"]
        axis_changes: dict[str, float] = {}
        any_changed = False
        for i, lbl in enumerate(axis_labels):
            b = before["sizes"][i] or 1e-9   # guard divide-by-zero
            a = after["sizes"][i]
            rel = abs(a - b) / abs(b)
            axis_changes[lbl] = rel
            if rel >= min_relative_change:
                any_changed = True

        if not any_changed:
            return {"success": True, "passed": False,
                    "param": param, "original_value": original_value,
                    "new_value": new_value, "restored": True,
                    "before": before, "after": after,
                    "axis_changes": axis_changes,
                    "reason": (f"no bbox axis changed by >= {min_relative_change} "
                               f"when {param} {original_value}->{new_value}; "
                               f"the param likely does not reach the geometry "
                               f"(broken ch() chain?)")}

        # If an expected axis was named, it specifically must have changed.
        if expected_axis:
            ea = expected_axis.upper()
            if ea not in axis_labels:
                return {"success": False,
                        "error": f"expected_axis must be X/Y/Z, got {expected_axis!r}"}
            if axis_changes[ea] < min_relative_change:
                return {"success": True, "passed": False,
                        "param": param, "original_value": original_value,
                        "new_value": new_value, "restored": True,
                        "before": before, "after": after,
                        "axis_changes": axis_changes,
                        "reason": (f"expected axis {ea} did NOT change "
                                   f"({axis_changes[ea]:.4f} < {min_relative_change}) "
                                   f"when {param} changed; the param propagated "
                                   f"but not on the expected axis")}

        return {"success": True, "passed": True,
                "param": param, "original_value": original_value,
                "new_value": new_value, "restored": True,
                "before": before, "after": after,
                "axis_changes": axis_changes,
                "reason": (f"PASS: {param} {original_value}->{new_value} moved "
                           f"the geometry"
                           + (f" on axis {expected_axis.upper()}" if expected_axis else "")
                           + f"; axis_changes={axis_changes}")}
    except Exception as e:
        # If the exception happened after perturbation, the inner finally has
        # already restored the param (_restored=True). If it happened before
        # (e.g. parm.eval / node lookup), no perturbation occurred. Either way,
        # report the param's true state so the agent knows the scene is clean.
        restored = locals().get("_restored", False)
        return {"success": False,
                "restored": restored,
                "error": f"{e}\n{traceback.format_exc()}"}


# Regex matching ch('...') / hou.ch('...') calls inside an expression string.
# Captures the function name (group 1) and the quoted path argument (group 2).
# Handles single OR double quotes. Used by repath_to_relative.
_CH_CALL_RE = re.compile(r'(hou\.)?ch\(\s*[\'"]([^\'"]+)[\'"]\s*\)')


def _relative_path_to_core(node_path: str, core_path: str) -> str | None:
    """Compute the relative ch() path from `node_path` up to `core_path`.

    Returns e.g. "../../" such that ch("../../<parm>") on `node_path` resolves
    to `core_path`'s parm. Returns None if `node_path` is not a descendant of
    `core_path` (cannot form a relative reference).

    Pure path-segment arithmetic — no hou needed, fully unit-testable.
    """
    node_parts = node_path.strip("/").split("/")
    core_parts = core_path.strip("/").split("/")
    # node must be strictly deeper than core and share core as a prefix.
    if len(node_parts) <= len(core_parts):
        return None
    if node_parts[:len(core_parts)] != core_parts:
        return None
    depth = len(node_parts) - len(core_parts)
    return "../" * depth


def repath_to_relative(core_path: str, component_id: str) -> dict[str, Any]:
    """Rewrite a component's absolute core ch() references to relative ones.

    This is the cure for the "absolute path → component not migratable" problem
    (Finding 4). Under the design_params path, geometry references core parms via
    absolute ``ch('/obj/.../project_core/<p>')``. That ties the component to its
    current project path — copy the subnet to another project and every ch()
    breaks. This tool rewrites those absolute references to relative ones
    (``ch("../../<p>")``, depth computed per-node), so the component references
    its core by POSITION rather than path. A migrated component then cooks
    anywhere a ``<project_core>`` node sits at the same relative depth (which the
    project HDA structure guarantees).

    Scope: ONE component subnet (on-demand, not whole-project). Rewrites every
    ``ch('.../project_core/<p>')`` and ``hou.ch('.../project_core/<p>')`` inside
    the component's subtree to ``ch('<relative>/<p>')``. Non-ch() expressions
    and references to other nodes are left untouched.

    Args:
        core_path: the edini::project HDA core path.
        component_id: the component subnet name (direct child of core).

    Returns:
        {success, component, rewritten:[{node, parm, before, after}], count,
         skipped, dry_run}
    """
    try:
        core = hou.node(core_path)
        if core is None:
            return {"success": False, "error": f"Core not found: {core_path}"}
        subnet = core.node(component_id)
        if subnet is None:
            return {"success": False,
                    "error": f"Component {component_id!r} not found under {core_path}"}

        core_path_norm = core_path.rstrip("/")
        rewritten: list[dict] = []
        skipped = 0

        # allSubChildren includes the subnet itself; iterate the subtree.
        nodes = list(subnet.allSubChildren()) + [subnet]
        for node in nodes:
            rel = _relative_path_to_core(node.path(), core_path_norm)
            if rel is None:
                continue   # node not a descendant of core (shouldn't happen)
            for parm in node.parms():
                try:
                    expr = parm.expression()
                except Exception:
                    expr = None
                if not expr:
                    continue
                # Does this expression reference the core via an absolute path?
                if core_path_norm not in expr:
                    continue
                new_expr = _CH_CALL_RE.sub(
                    _make_replacer(core_path_norm, rel), expr)
                if new_expr != expr:
                    rewritten.append({
                        "node": node.path(),
                        "parm": parm.name(),
                        "before": expr,
                        "after": new_expr,
                    })
                    try:
                        parm.setExpression(new_expr)
                    except Exception as e:
                        # Don't abort the whole repath on one parm failure —
                        # record and continue (the agent can see partial result).
                        rewritten[-1]["set_error"] = str(e)
                else:
                    skipped += 1

        # `count` counts ONLY successful rewrites. A failed setExpression
        # (recorded with `set_error` on the rewritten entry) does NOT count —
        # previously len(rewritten) over-reported, telling the agent "N refs
        # migrated" when some had silently failed. (session-logs-analysis audit.)
        failed = [r for r in rewritten if "set_error" in r]
        return {"success": True,
                "component": subnet.path(),
                "core": core_path_norm,
                "rewritten": rewritten,
                "count": len(rewritten) - len(failed),
                "failed": [{"node": r["node"], "parm": r["parm"],
                            "error": r["set_error"]} for r in failed],
                "skipped_no_change": skipped}
    except Exception as e:
        return {"success": False,
                "error": f"{e}\n{traceback.format_exc()}"}


def _make_replacer(core_path: str, rel: str):
    """Build a regex sub callback that rewrites ch('/abs/core/path/<p>') and
    hou.ch('/abs/core/path/<p>') to ch('<rel><p>') / hou.ch('<rel><p>').

    Only rewrites references whose path equals core_path or core_path + a parm
    tail (core_path/parm). Leaves other absolute references alone.
    """
    def repl(m: re.Match) -> str:
        fn = m.group(1) or ""    # "hou." or ""
        path = m.group(2)
        # Match exactly core_path or core_path/<parm>.
        if path == core_path:
            return f'{fn}ch("{rel[:-1] if rel != "../" else rel}")'
        if path.startswith(core_path + "/"):
            parm_tail = path[len(core_path) + 1:]
            # guard against deeper paths (core/something/else) — only one level.
            if "/" in parm_tail:
                return m.group(0)
            return f'{fn}ch("{rel}{parm_tail}")'
        return m.group(0)
    return repl


