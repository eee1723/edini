"""Project HDA node helpers — the ONLY module here that imports `hou`.

Creation, hidden-parm install, and node lookup. Real hou at runtime;
tested via tests/mock_hou.py for template construction.
"""
from __future__ import annotations

import hou  # noqa: E402  (real hou at runtime)

from .state import STATE_PARM, empty_declaration, save_declaration


def build_state_parm_template() -> hou.StringParmTemplate:
    """Build the hidden string parm template that holds the declaration JSON."""
    tmpl = hou.StringParmTemplate(STATE_PARM, "Edini State", 1)
    tmpl.setHidden(True)
    tmpl.setTags({"editor": "1"})  # multi-line string editor
    return tmpl


def create_project_hda(name: str = "project", parent_path: str = "/obj",
                       goal: str | None = None) -> "hou.Node":
    """Create a Project HDA node and seed it with an empty declaration.

    The node type `edini::project` must already be registered (via
    HOUDINI_OTLSCAN_PATH pointing at otls/edini_project.hda).
    """
    parent = hou.node(parent_path)
    if parent is None:
        raise ValueError(f"parent not found: {parent_path}")
    node = parent.createNode("edini::project", node_name=name)

    # Install the hidden state parm via the node's spare-parm group,
    # then seed the declaration JSON.
    grp = node.spareParmGroup()
    grp.appendToFolder("Spare", build_state_parm_template())
    node.setSpareParmGroup(grp)

    declaration = empty_declaration(project_name=name, goal=goal)
    save_declaration(node, declaration)
    return node
