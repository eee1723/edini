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
