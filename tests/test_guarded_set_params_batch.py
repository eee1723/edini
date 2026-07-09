"""The snippet-guard batch wrapper (P0 fix, 2026-07-09).

Context: ``_guarded_set_params_batch`` used to refuse the WHOLE batch when its
``snippet`` field tripped the addpoint guard — silently dropping sibling params
set in the same call. In the cube session a batch
``{class:"detail", snippet:<addpoint>}`` was refused wholesale, so ``class``
stayed at its default (point, not detail), the detail wrangle ran 0 times, and
geometry came out empty — a long diagnostic detour.

The fix branches on which sub-guard fired:
  - ``internal_node_guard``  → the whole node is platform-owned; refuse ALL.
  - ``project_anchor_guard`` → only the snippet is suspect; apply siblings,
    refuse only the snippet, tell the agent what to re-send.

These tests pin both branches plus the pass-through. The wrapper logic is
isolated by monkeypatching ``lint_wrangle_snippet`` and ``set_params_batch`` —
no live hou needed.
"""
import sys
import types

import pytest

# Stub hou before importing edini.tool_executor (it imports hou transitively).
if "hou" not in sys.modules:
    sys.modules["hou"] = types.ModuleType("hou")

from edini import tool_executor as te


# ── addpoint guard: siblings MUST survive a snippet refusal ──────────────

def test_addpoint_guard_applies_siblings_and_skips_only_snippet(monkeypatch):
    """The regression: {class, snippet} — class must still be applied."""
    calls = {}

    def fake_lint(node_path, snippet):
        return {
            "success": False,
            "blocked_by": "project_anchor_guard",
            "error": "Refused: measure violation ... addpoint ...",
            "suggested_tool": "project_add_anchors",
        }

    def fake_batch(node_path, params):
        calls["batch"] = (node_path, dict(params))
        return {"success": True, "set_count": len(params),
                "total_count": len(params)}

    monkeypatch.setattr(te, "lint_wrangle_snippet", fake_lint)
    monkeypatch.setattr(te, "set_params_batch", fake_batch)

    result = te._guarded_set_params_batch(
        node_path="/obj/geo1/project1/cubies/grid_pts",
        params={"class": "detail", "snippet": "addpoint(0, {0,0,0});"})

    # Sibling `class` was forwarded to set_params_batch — NOT dropped.
    assert calls["batch"][1] == {"class": "detail"}
    # The refusal is unambiguous (success: False) but partial (1 of 2 applied).
    assert result["success"] is False
    assert result["partial"] is True
    assert result["set_count"] == 1
    assert result["total_count"] == 2
    assert result["skipped_fields"] == ["snippet"]
    assert result["applied_fields"] == ["class"]
    assert result["blocked_by"] == "project_anchor_guard"
    # The agent is told to re-send ONLY the snippet, not the siblings.
    assert "ONLY the snippet" in result["note"]


def test_addpoint_guard_no_siblings_just_refuses(monkeypatch):
    """A snippet-only batch still refuses cleanly, with no sibling claim."""

    def fake_lint(node_path, snippet):
        return {"success": False, "blocked_by": "project_anchor_guard",
                "error": "Refused: addpoint"}

    called = {"batch": False}

    def fake_batch(node_path, params):
        called["batch"] = True
        return {"success": True, "set_count": 0, "total_count": 0}

    monkeypatch.setattr(te, "lint_wrangle_snippet", fake_lint)
    monkeypatch.setattr(te, "set_params_batch", fake_batch)

    result = te._guarded_set_params_batch(
        node_path="/x/y", params={"snippet": "addpoint(0, p);"})

    # No siblings → set_params_batch is not even called.
    assert called["batch"] is False
    assert result["success"] is False
    assert result["set_count"] == 0
    assert result["total_count"] == 1
    assert "applied_fields" not in result


# ── internal-node guard: the whole node is off-limits ────────────────────

def test_internal_node_guard_refuses_wholesale(monkeypatch):
    """An internal (__-prefixed) scaffold node: ALL params refused, siblings
    are NOT applied (the node bakes a platform contract)."""
    called = {"batch": False}

    def fake_lint(node_path, snippet):
        return {"success": False, "blocked_by": "internal_node_guard",
                "error": "Refused: internal scaffold node",
                "suggested_node": "tag_component"}

    def fake_batch(node_path, params):
        called["batch"] = True
        return {"success": True, "set_count": len(params),
                "total_count": len(params)}

    monkeypatch.setattr(te, "lint_wrangle_snippet", fake_lint)
    monkeypatch.setattr(te, "set_params_batch", fake_batch)

    result = te._guarded_set_params_batch(
        node_path="/obj/geo1/project1/cubies/__edini_axis_bake",
        params={"class": "detail", "snippet": "v@P += {0,1,0};"})

    # Wholesale refuse: nothing applied, sibling NOT forwarded.
    assert called["batch"] is False
    assert result["success"] is False
    assert result["set_count"] == 0
    assert result["total_count"] == 2
    assert "partial" not in result
    assert result["blocked_by"] == "internal_node_guard"


# ── pass-through: no refusal → normal batch with all params ──────────────

def test_clean_snippet_passes_through_with_all_params(monkeypatch):
    """A benign snippet (no addpoint) must forward the FULL params dict,
    including the snippet itself."""

    def fake_lint(node_path, snippet):
        return None  # allow

    calls = {}

    def fake_batch(node_path, params):
        calls["batch"] = (node_path, dict(params))
        return {"success": True, "set_count": len(params),
                "total_count": len(params)}

    monkeypatch.setattr(te, "lint_wrangle_snippet", fake_lint)
    monkeypatch.setattr(te, "set_params_batch", fake_batch)

    params = {"class": "detail", "snippet": "v@Cd = {1,1,1};"}
    result = te._guarded_set_params_batch(node_path="/x/y", params=params)

    # ALL params (incl. snippet) forwarded unchanged.
    assert calls["batch"][1] == params
    assert result["success"] is True
    assert result["set_count"] == 2


def test_batch_without_snippet_bypasses_guard(monkeypatch):
    """A batch with no snippet field never calls the guard at all."""

    def fake_lint(node_path, snippet):
        raise AssertionError("guard must not run when there is no snippet")

    def fake_batch(node_path, params):
        return {"success": True, "set_count": len(params),
                "total_count": len(params)}

    monkeypatch.setattr(te, "lint_wrangle_snippet", fake_lint)
    monkeypatch.setattr(te, "set_params_batch", fake_batch)

    result = te._guarded_set_params_batch(
        node_path="/x/y", params={"sizex": 1.0, "sizey": 2.0})
    assert result["success"] is True
    assert result["set_count"] == 2
