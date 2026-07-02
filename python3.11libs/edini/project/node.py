"""Project HDA node helpers — the ONLY module here that imports `hou`.

Creation, hidden-parm install, and node lookup. Real hou at runtime;
tested via tests/mock_hou.py for template construction.

**SOP-context HDA.** `edini::project` registers in the Sop node-type category
(see scripts/make_project_hda.py). Instances therefore live INSIDE a geo and
host a SOP network directly — exactly what rooted build_assembly needs. A
Project is structured as a geo "shell" at /obj (the displayable object) with a
single `edini::project` SOP HDA instance inside it (the modeling core that
carries the declaration + geometry).
"""
from __future__ import annotations

import hou  # noqa: E402  (real hou at runtime)

from .state import STATE_PARM, empty_declaration, save_declaration

# Name of the SOP HDA instance inside the geo shell.
CORE_NODE_NAME = "project_core"


def build_state_parm_template() -> hou.StringParmTemplate:
    """Build the hidden string parm template that holds the declaration JSON.

    Hidden via ``hide(True)`` (the real hou API) — hidden parms still eval and
    can be channel-referenced, they just don't show in the parameter pane.
    """
    tmpl = hou.StringParmTemplate(STATE_PARM, "Edini State", 1)
    tmpl.hide(True)
    tmpl.setTags({"editor": "1"})  # multi-line string editor
    return tmpl


def create_project_hda(name: str = "project", parent_path: str = "/obj",
                       goal: str | None = None) -> "hou.Node":
    """Create a Project HDA and seed it with an empty declaration.

    Creates a geo "shell" at ``<parent>/<name>`` (the displayable object) and a
    ``edini::project`` SOP HDA instance inside it at
    ``<parent>/<name>/project_core`` — the modeling core. The declaration JSON
    and (later) rooted geometry live on/in the core node. Returns the **core**
    node (it carries the state + is build_assembly's root_path).

    The node type `edini::project` must already be registered (via
    HOUDINI_OTLSCAN_PATH pointing at otls/edini_project.hda) in the Sop
    category.
    """
    parent = hou.node(parent_path)
    if parent is None:
        raise ValueError(f"parent not found: {parent_path}")
    # Geo shell — the /obj-level displayable object wrapping the project.
    shell = parent.createNode("geo", node_name=name)
    # SOP HDA instance inside the shell — the modeling core.
    core = shell.createNode("edini::project", node_name=CORE_NODE_NAME)

    # Install the hidden state parm on the CORE (it holds the declaration +
    # is build_assembly's root_path), then seed the empty declaration.
    core.addSpareParmTuple(build_state_parm_template())
    declaration = empty_declaration(project_name=name, goal=goal)
    save_declaration(core, declaration)
    return core


def find_project_cores() -> "list[hou.Node]":
    """Return all edini::project SOP HDA instances in the scene.

    Scans the Sop category (the type is SOP-context). Each returned node is a
    modeling core living inside a geo shell (see create_project_hda).
    """
    t = hou.nodeType(hou.sopNodeTypeCategory(), "edini::project")
    if t is None:
        return []
    return list(t.instances())
