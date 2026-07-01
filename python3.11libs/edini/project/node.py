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
