"""Snapshot engine for Houdini scene change tracking.

Captures full scene state as dicts, diffs two snapshots to find
created/deleted/modified nodes, and restores from one state to another
via node-level rebuild.
"""
from __future__ import annotations
from typing import Any


# hou is imported lazily — only available inside Houdini
def _hou():
    try:
        import hou  # type: ignore
        return hou
    except ImportError:
        return None


def snapshot(root: str = "/obj") -> dict[str, dict[str, Any]]:
    """Capture full state of all nodes under root as a flat dict.

    Returns {} if hou module is unavailable.

    Each entry:
        path (str): absolute node path (key)
        type (str): node type name
        parent (str): parent node path
        params (dict): param_name → value for all parms
        inputs (dict): input_index → source_path (or None)
        children (list[str]): child node paths
    """
    hou = _hou()
    if hou is None:
        return {}

    root_node = hou.node(root)
    if root_node is None:
        return {}

    state: dict[str, dict[str, Any]] = {}
    _collect_nodes(root_node, state)
    return state


def _collect_nodes(node, state: dict[str, dict[str, Any]]) -> None:
    """Recursively collect all descendant nodes into state dict."""
    path = node.path()
    parms = {}
    for p in node.parms():
        try:
            parms[p.name()] = p.eval()
        except Exception:
            parms[p.name()] = None

    inputs = {}
    for i in range(len(node.inputConnectors())):
        in_node = node.input(i)
        inputs[i] = in_node.path() if in_node else None

    children = [c.path() for c in node.children()]

    state[path] = {
        "type": node.type().name(),
        "parent": node.parent().path() if node.parent() else "",
        "params": parms,
        "inputs": inputs,
        "children": children,
    }

    for child in node.children():
        _collect_nodes(child, state)


def diff(before: dict, after: dict) -> dict:
    """Compare two snapshots and return structured change report.

    Returns:
        {
            "created": [{"path", "type", "parent"}, ...],
            "deleted": [{"path", "type"}, ...],
            "modified": [{"path", "type", "changes": [{"param", "old", "new"}, ...]}, ...],
            "summary": {"created": N, "deleted": N, "modified": N}
        }
        All lists empty if no changes.
    """
    before_paths = set(before.keys())
    after_paths = set(after.keys())

    created_paths = sorted(after_paths - before_paths, key=_path_sort_key)
    deleted_paths = sorted(before_paths - after_paths, key=_path_sort_key)
    common_paths = sorted(before_paths & after_paths, key=_path_sort_key)

    created = []
    for p in created_paths:
        info = after[p]
        created.append({
            "path": p,
            "type": info.get("type", ""),
            "parent": info.get("parent", ""),
        })

    # Filter: remove child nodes when parent was also created
    # (Houdini auto-creates internal children with node types)
    created = _filter_descendants(created)

    deleted = []
    for p in deleted_paths:
        info = before[p]
        deleted.append({
            "path": p,
            "type": info.get("type", ""),
        })

    # Filter: removing a parent deletes all children implicitly
    deleted = _filter_descendants(deleted)

    # Build set of created paths for modified filtering
    created_path_set = {item["path"] for item in created}

    modified = []
    for p in common_paths:
        b = before[p]
        a = after[p]
        changes = []

        # Param changes
        all_params = set(b.get("params", {}).keys()) | set(a.get("params", {}).keys())
        for parm in sorted(all_params):
            old_val = b.get("params", {}).get(parm)
            new_val = a.get("params", {}).get(parm)
            if old_val != new_val:
                changes.append({"param": parm, "old": old_val, "new": new_val})

        # Input changes
        all_inputs = set(b.get("inputs", {}).keys()) | set(a.get("inputs", {}).keys())
        for idx in sorted(all_inputs):
            old_src = b.get("inputs", {}).get(idx)
            new_src = a.get("inputs", {}).get(idx)
            if old_src != new_src:
                changes.append({
                    "param": f"input[{idx}]",
                    "old": old_src or "<none>",
                    "new": new_src or "<none>",
                })

        if changes:
            modified.append({
                "path": p,
                "type": b.get("type", a.get("type", "")),
                "changes": changes,
            })

    # Filter: skip nodes whose parent was created this round
    # (they're children of new nodes, not genuine modifications)
    modified = [
        m for m in modified
        if not any(
            m["path"].startswith(cp + "/")
            for cp in created_path_set
        )
    ]

    return {
        "created": created,
        "deleted": deleted,
        "modified": modified,
        "summary": {
            "created": len(created),
            "deleted": len(deleted),
            "modified": len(modified),
        },
    }


def restore(before: dict, after: dict) -> None:
    """Restore scene from after-state back to before-state.

    Three phases:
    1. Delete nodes in after that don't exist in before
    2. Restore params and inputs for modified nodes
    3. Rebuild nodes in before that don't exist in after

    Logs errors on individual failures; does not abort.
    No-op if hou module unavailable.
    """
    hou = _hou()
    if hou is None:
        return

    # Phase 1: Delete added nodes (bottom-up: deepest children first)
    added = sorted(
        set(after.keys()) - set(before.keys()),
        key=lambda p: -p.count("/"),
    )
    for path in added:
        try:
            node = hou.node(path)
            if node:
                node.destroy()
        except Exception:
            pass

    # Phase 2: Restore modified nodes' params and inputs
    for path in sorted(set(before.keys()) & set(after.keys())):
        b_info = before[path]
        a_info = after[path]
        node = hou.node(path)
        if node is None:
            continue

        # Restore params
        for parm, old_val in b_info.get("params", {}).items():
            new_val = a_info.get("params", {}).get(parm)
            if old_val != new_val:
                try:
                    p = node.parm(parm)
                    if p:
                        p.set(old_val)
                except Exception:
                    pass

        # Restore inputs
        for idx, old_src in b_info.get("inputs", {}).items():
            new_src = a_info.get("inputs", {}).get(idx)
            if old_src != new_src:
                try:
                    src_node = hou.node(old_src) if old_src else None
                    node.setInput(idx, src_node)
                except Exception:
                    pass

    # Phase 3: Rebuild removed nodes (top-down: parent before children)
    removed = sorted(
        set(before.keys()) - set(after.keys()),
        key=lambda p: p.count("/"),
    )
    for path in removed:
        _rebuild_node(path, before)


def _rebuild_node(path: str, state: dict) -> None:
    """Rebuild a single node from state info (parent must already exist)."""
    hou = _hou()
    if hou is None:
        return
    info = state.get(path)
    if not info:
        return

    parent_path = info.get("parent", "")
    parent = hou.node(parent_path) if parent_path else hou.node("/obj")
    if parent is None:
        return

    node_type = info.get("type", "")
    node_name = path.rsplit("/", 1)[-1] if "/" in path else path

    try:
        node = parent.createNode(node_type, node_name)
        if node is None:
            return
    except Exception:
        return

    # Restore params
    for parm, val in info.get("params", {}).items():
        try:
            p = node.parm(parm)
            if p:
                p.set(val)
        except Exception:
            pass

    # Restore inputs
    for idx, src_path in info.get("inputs", {}).items():
        if src_path:
            try:
                src_node = hou.node(src_path)
                if src_node:
                    node.setInput(idx, src_node)
            except Exception:
                pass


def _filter_descendants(items: list[dict]) -> list[dict]:
    """Remove items whose path is a descendant of another item in the list.

    For created/deleted: if parent A was created, its auto-generated children
    should not appear separately. Only the top-most nodes in each branch are kept.
    """
    if len(items) <= 1:
        return items
    # Sort by path depth ascending (parents before children)
    sorted_items = sorted(items, key=lambda x: x["path"].count("/"))
    result = []
    kept_paths: set[str] = set()
    for item in sorted_items:
        path = item["path"]
        # Check if path is a descendant of any already-kept path
        is_descendant = any(
            path.startswith(kp + "/")
            for kp in kept_paths
        )
        if not is_descendant:
            result.append(item)
            kept_paths.add(path)
    return result


def _path_sort_key(path: str) -> tuple[int, str]:
    return (path.count("/"), path)
