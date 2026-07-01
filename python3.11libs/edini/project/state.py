"""Project declaration state: schema + JSON <-> hidden-parm bridge.

Pure Python (no `hou` import) so it is unit-testable with a fake node.
The declaration JSON is the knowledge graph (see spec §5). It is persisted
in a hidden string parm `STATE_PARM` on the Project HDA node.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

# Name of the hidden string parm on the Project HDA that holds the JSON.
STATE_PARM = "__edini_state"
SCHEMA_VERSION = 1


def empty_declaration(project_name: str, goal: str | None = None) -> dict:
    """Return a fresh empty declaration (the "empty project" state)."""
    return {
        "version": SCHEMA_VERSION,
        "project": {
            "name": project_name,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "goal": goal,
        },
        "plan": [],
        "design_params": [],
        "components": [],
        "log": [],
        "drift": [],
    }


def load_declaration(node) -> dict:
    """Read the declaration JSON from the node's hidden parm.

    Returns a safe empty skeleton if the parm is absent, empty, or corrupt.
    Never raises.
    """
    parm = node.parm(STATE_PARM)
    raw = parm.eval() if parm is not None else ""
    if not raw:
        return empty_declaration(None)
    try:
        data = json.loads(raw)
        if not isinstance(data, dict) or "version" not in data:
            return empty_declaration(None)
        return data
    except (json.JSONDecodeError, TypeError):
        return empty_declaration(None)


def save_declaration(node, declaration: dict) -> None:
    """Write the declaration JSON to the node's hidden parm."""
    node.parm(STATE_PARM).set(json.dumps(declaration))


_STEP_STATUSES = ("pending", "in_progress", "done", "skipped")


def add_plan_step(declaration: dict, step_id: str, title: str,
                  parent: str | None = None, detail: str = "",
                  status: str = "pending") -> dict:
    """Append a plan step to the declaration. Returns the new step.

    Raises ValueError if step_id already exists.
    """
    if any(s["id"] == step_id for s in declaration["plan"]):
        raise ValueError(f"plan step id already exists: {step_id}")
    step = {"id": step_id, "title": title, "parent": parent,
            "status": status, "detail": detail}
    declaration["plan"].append(step)
    return step


def set_step_status(declaration: dict, step_id: str, status: str) -> None:
    """Set a plan step's status. Raises KeyError if step_id unknown,
    ValueError if status not in _STEP_STATUSES."""
    if status not in _STEP_STATUSES:
        raise ValueError(f"bad status: {status}")
    for step in declaration["plan"]:
        if step["id"] == step_id:
            step["status"] = status
            return
    raise KeyError(f"unknown plan step id: {step_id}")
