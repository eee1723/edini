"""Scope discipline guard.

Components in edini/ui/components/ MUST NOT branch on scope_id string.
They read ScopeConfig fields (show_change_tree, show_attachment_bar, etc.),
never `if scope.scope_id == 'agent'` or `if scope_id == 'project_hda'`.

This keeps the difference between windows expressed in ONE place
(ScopeConfig fields), not scattered as conditionals in components.
"""
import re
from pathlib import Path

COMP_DIR = Path(__file__).parent.parent / "python3.11libs" / "edini" / "ui" / "components"

# Match patterns like:
#   if scope_id == "agent"
#   if scope.scope_id == 'project_hda'
#   if self._scope.scope_id == "agent"
SCOPE_BRANCH_RE = re.compile(
    r'if\s+[\w\.]*scope_?id\s*==',
    re.IGNORECASE,
)


def test_no_scope_id_branches_in_components():
    """No component file may contain an `if ...scope_id ==` branch."""
    assert COMP_DIR.exists(), f"components dir not found: {COMP_DIR}"
    offenders = []
    for py in COMP_DIR.glob("*.py"):
        if py.name == "__init__.py":
            continue
        try:
            text = py.read_text(encoding="utf-8")
        except Exception:
            continue
        if SCOPE_BRANCH_RE.search(text):
            # Find the offending line for a helpful message
            for i, line in enumerate(text.splitlines(), 1):
                if SCOPE_BRANCH_RE.search(line):
                    offenders.append(f"{py.name}:{i}: {line.strip()}")
    assert not offenders, (
        "Components branch on scope_id (violates single-diff-entry-point rule):\n"
        + "\n".join(offenders)
    )
