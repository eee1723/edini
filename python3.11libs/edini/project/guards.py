"""Pre-execution guards for project-modeling tool calls (Fix 1).

Shifts the "use declarative primitives, not hand-rolled addpoint" rule from
SKILL.md prose into a fail-fast platform gate. The chair-modeling log showed
the agent hand-writing ``addpoint(set(0.225,0,0.225), ...)`` inside a component
subnet instead of calling ``project_add_anchors`` — which then cascaded into
VEX syntax errors, wrong wrangle class, and silent anchor cross-talk that took
5 extra tool rounds to patch.

This module exports ``lint_wrangle_snippet`` — called by the tool_executor
dispatch BEFORE the param is applied. It returns an error dict (refuse) or
None (allow). The guard is narrowly scoped:

  - ONLY fires when the target is an ``attribwrangle`` node
  - whose snippet contains ``addpoint(``
  - AND the wrangle lives inside a component subnet of an ``edini::project``
    core (walked via ``node.parent()``).

So recipe / sandbox / standalone wrangles are never affected — the gate is
gated to the project-modeling context where the declarative primitive exists.

Escape hatch: a snippet containing ``// edini-bypass-anchor-guard`` is allowed
through. (``project_add_anchors`` builds its own wrangles via createNode +
.parm().set() in-process, NOT through this tool path, so it never hits the
guard; the hatch is for rare agent-legitimate cases.)
"""
from __future__ import annotations

from typing import Any

try:
    import hou  # real hou at runtime; None in offline/test envs.
except ImportError:
    hou = None  # type: ignore[assignment]

from edini.project.ports import is_internal_scaffold_node

# Substring that marks the agent explicitly opting out (e.g. a legit one-off).
_BYPASS_MARKER = "edini-bypass-anchor-guard"

# The forbidden primitive: hand-emitting anchor points by coordinate. We match
# on the bare call token to catch both VEX ``addpoint(0, pos)`` and Python-SOP
# ``geo.addPoint(hou.Vector(...))`` (lowercased check covers both).
_FORBIDDEN_TOKEN = "addpoint"

# How far up the parent chain to walk looking for an edini::project core.
# subnet → core is 1 hop; a wrangle directly parented to core is 1 hop. A few
# extra hops covers nested helper subnets without an unbounded loop.
_MAX_PARENT_HOPS = 6

_PROJECT_TYPE_NAME = "edini::project"
_WRANGLE_TYPE_HINT = "wrangle"  # matches attribwrangle / attribvop1's inner


def _node_type_name(node: Any) -> str:
    """Best-effort read of node.type().name(); '' on any failure."""
    try:
        return node.type().name()
    except Exception:
        return ""


def _inside_project_core(node: Any) -> bool:
    """True if `node` lives inside (or is) an edini::project core subnet.

    Walks node.parent() up to _MAX_PARENT_HOPS hops. We check BOTH the node
    itself and each ancestor: a wrangle directly inside the core, or nested
    inside a component subnet of the core, both qualify.
    """
    if node is None:
        return False
    cursor = node
    for _ in range(_MAX_PARENT_HOPS):
        if cursor is None:
            break
        if _node_type_name(cursor) == _PROJECT_TYPE_NAME:
            return True
        try:
            cursor = cursor.parent()
        except Exception:
            break
    return False


def _is_wrangle(node: Any) -> bool:
    """True if node is an attribwrangle (or its inner attribvop)."""
    tname = _node_type_name(node)
    return "wrangle" in tname


def lint_wrangle_snippet(node_path: str, snippet: Any) -> dict[str, Any] | None:
    """Return a refusal dict if `snippet` violates a project contract.

    Called by tool_executor before applying a `snippet` param. Returns:
      - None → snippet is fine, proceed.
      - dict → refuse; the dict is the tool's error result body.

    Two independent refusals (either fires independently):
      A. INTERNAL-NODE guard (Round-2 Fix A): the target node is an internal
         scaffold node (__-prefixed, e.g. __edini_axis_bake). These bake
         platform contracts the scaffold owns and re-forces on rebuild; the
         agent editing them silently corrupts the contract. Refused regardless
         of snippet content.
      B. ADDPOINT guard (Fix 1): the snippet contains addpoint() AND the target
         is a wrangle inside a project core AND no bypass marker present.

    Hou import is lazy + optional: if hou isn't importable (e.g. unit test of
    the pure-logic parts), the context checks degrade to "can't tell" → allow.
    The addpoint-detection itself is pure string logic and unit-testable.
    """
    # ── Guard A: internal-node protection ──
    # Parse the node name from the path (no hou needed for this check). The
    # last path segment is the node name. Refuse ANY snippet edit on internal
    # nodes — they're owned by the scaffold.
    node_name = node_path.rstrip("/").rsplit("/", 1)[-1] if node_path else ""
    if is_internal_scaffold_node(node_name):
        return {
            "success": False,
            "blocked_by": "internal_node_guard",
            "error": (
                f"Refused: '{node_name}' is an internal scaffold node (the '__' "
                f"prefix marks it platform-owned). It bakes a contract the "
                f"scaffold enforces and re-forces on every rebuild — editing it "
                f"would be silently undone and risks corrupting the contract. "
                f"If you meant to set component_id or per-component attribs, "
                f"edit the 'tag_component' node in the same subnet instead."
            ),
            "suggested_node": "tag_component",
        }

    # ── Guard B: addpoint hardcoding ──
    # Pure-logic gate on the snippet content first (cheap, no hou needed).
    if not isinstance(snippet, str):
        return None
    if _BYPASS_MARKER in snippet:
        return None
    if _FORBIDDEN_TOKEN not in snippet.lower():
        return None

    # Context gate: only refuse inside a project core. Requires hou. We use the
    # module-level `hou` (imported at top, None if unavailable) so tests can
    # inject a fake by assigning edini.project.guards.hou — a function-local
    # `import hou` would re-bind to sys.modules and defeat that injection.
    if hou is None:
        return None

    node = hou.node(node_path)
    if node is None:
        return None
    if not _is_wrangle(node):
        return None
    if not _inside_project_core(node):
        return None

    # Refuse. Name the right tool + the rule, so the agent learns in one round.
    # Vocabulary aligned with project-modeling SKILL.md leading words: "measure".
    return {
        "success": False,
        "blocked_by": "project_anchor_guard",
        "error": (
            "Refused: measure violation — hardcoded addpoint() inside a "
            "Project HDA component. ALWAYS measure anchors from geometry via "
            "project_add_anchors so they move when params change; NEVER "
            "hardcode coordinates. project_add_anchors generates a LIVE VEX "
            "wrangle that measures the component's bbox on every cook. "
            "(Guardrail 2: always measure — never hardcode.) If this addpoint "
            "is genuinely not an anchor (rare), add "
            "`// edini-bypass-anchor-guard` to the snippet."
        ),
        "suggested_tool": "project_add_anchors",
        "schema_hint": {
            "core_path": "<the edini::project SOP HDA path>",
            "component_id": "<the component subnet name this wrangle is inside>",
            "anchors": [
                {"measure": "bbox_corner", "axes": "+X-Y+Z", "name": "leg_mount_fr"},
                {"measure": "bbox_face_center", "face": "+Y", "name": "seat_top_center"},
            ],
        },
    }


# ── Test affordance ──────────────────────────────────────────────────────
# Expose the pure-logic predicate so tests can cover the addpoint-detection
# without a live hou. lint_wrangle_snippet itself needs hou for the context
# half; tests inject a fake via monkeypatching `hou` in this module's globals.
def _snippet_violates(snippet: Any) -> bool:
    """Pure-logic: True if the snippet text itself is a violation candidate
    (contains addpoint, no bypass marker). Does NOT check project context."""
    if not isinstance(snippet, str):
        return False
    if _BYPASS_MARKER in snippet:
        return False
    return _FORBIDDEN_TOKEN in snippet.lower()
