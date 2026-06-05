"""Houdini node operation utilities.

Pure houp wrappers. No UI dependencies. All functions return
JSON-serializable dicts with {"success": bool, ...} shape.
"""
from __future__ import annotations

import hou
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

    # Attempt 2: resolve via namespaceOrder across all categories
    if node is None:
        for cat in [
            hou.sopNodeTypeCategory(),
            hou.objNodeTypeCategory(),
            hou.dopNodeTypeCategory(),
            hou.vopNodeTypeCategory(),
            hou.shopNodeTypeCategory(),
            hou.ropNodeTypeCategory(),
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

    # All attempts failed — let original exception propagate
    if node is None:
        return parent.createNode(node_type, node_name=name if name else None)

    # Apply Tab-menu presets from matching shelf tool
    _apply_tool_presets(node)
    return node


def _apply_tool_presets(node) -> None:
    """Apply post-creation parameter presets from shelf tools matching this node type.

    The Tab menu runs shelf tools that often call pressButton() or parm().set()
    after creating the node (e.g. 'resettargetattribs' for copytopoints).
    This function finds matching tools and applies those post-creation actions.
    """
    import re

    try:
        node_type_name = node.type().name()  # e.g. 'copytopoints::2.0'
    except Exception:
        return

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
) -> dict[str, Any]:
    """Connect the output of one node to the input of another."""
    try:
        from_node = hou.node(from_path)
        to_node = hou.node(to_path)
        if from_node is None:
            return {"success": False, "error": f"Source node not found: {from_path}"}
        if to_node is None:
            return {"success": False, "error": f"Destination node not found: {to_path}"}

        to_node.setInput(input_index, from_node)
        return {
            "success": True,
            "from": from_path,
            "to": to_path,
            "input_index": input_index,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def set_param(node_path: str, param_name: str, value: Any) -> dict[str, Any]:
    """Set a parameter value on a node."""
    try:
        node = hou.node(node_path)
        if node is None:
            return {"success": False, "error": f"Node not found: {node_path}"}

        parm = node.parm(param_name)
        if parm is None:
            return {"success": False, "error": f"Parameter '{param_name}' not found on {node_path}"}

        parm.set(value)
        return {"success": True, "path": node_path, "param": param_name, "value": value}
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

        return {"success": True, "path": node_path, "param": param_name, "value": parm.eval()}
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


def get_node_info(node_path: str) -> dict[str, Any]:
    """Get detailed info about a specific node."""
    try:
        node = hou.node(node_path)
        if node is None:
            return {"success": False, "error": f"Node not found: {node_path}"}

        parms = []
        for p in node.parms():
            parms.append({"name": p.name(), "label": p.description(), "value": p.eval()})

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
            "bounds": geo.boundingBox().size() if geo.boundingBox() is not None else None,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Script / HDA Operations
# ---------------------------------------------------------------------------

def run_python(code: str) -> dict[str, Any]:
    """Execute arbitrary Python code in Houdini context."""
    try:
        namespace = {"hou": hou, "__builtins__": __builtins__}
        import io
        import sys

        stdout_capture = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = stdout_capture

        try:
            exec(code, namespace)
        finally:
            sys.stdout = old_stdout

        output = stdout_capture.getvalue()
        return {"success": True, "output": output if output else "(no output)"}
    except Exception as e:
        return {"success": False, "error": str(e)}


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
