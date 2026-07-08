"""Tool executor HTTP server.

Runs inside Houdini's Python process. Receives tool execution requests
from Pi extensions via HTTP POST and dispatches to node_utils.
"""
from __future__ import annotations

import atexit
import json
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Any, Callable

from edini.node_utils import (
    get_scene_info,  create_node, delete_node, connect_nodes,
    set_param, set_params_batch, get_param, list_nodes, get_node_info, layout_nodes,
    search_nodes, get_help, inspect_geometry,
    run_vex, create_hda, get_hda_info,
    capture_review, capture_network, capture_component_detail,
    get_selection, check_errors, set_display_flag,
    verify_orientation, inspect_geometry_health, geometry_inventory,
    node_parms,
    verify_parametric,
    verify_robust,
    repath_to_relative,
    project_status,
    project_finalize,
)
from edini import screenshots
from edini.config import _load_edini_settings
from edini.harness import (
    collect_diagnostics,
    run_python_sandbox,
    verify_asset,
    commit_sandbox,
    discard_sandbox,
    dump_parm_catalog,
    _create_sandbox_root,
)
from edini.recipe_library import (
    recipe_list,
    recipe_read,
    recipe_capture,
    recipe_rebuild,
    recipe_capture_tree,
    scan_recipe_tree,
    create_recipe_manager,
    set_node_notes,
)
from edini.project.builder import (
    build_project_scaffold, promote_params, add_anchors, emit_markers,
    emit_component, snapshot_component, restore_component, list_snapshots,
)
from edini.project.guards import lint_wrangle_snippet

# NOTE: Three procedural pipelines are archived under _disabled_backup/:
#   1. procedural-modeling/  — prompt-driven build_procedural_asset + G1-G3 gates.
#   2. asset-pipeline-2026-06/ — declarative asset (params+skeleton DAG,
#      asset_model.py/asset_builder.py/skeleton_resolver.py, validate_asset/
#      build_asset tools). Its positions-come-from-an-expression-DAG premise
#      could not express "measure real root geometry to place leaves".
#   3. rooted-modeling (assembly_builder.py) — Root → Measure → Mount → Shape.
#      Retired 2026-07-08: its flat single-root model was superseded by the
#      Project HDA component pipeline (project_* tools), which expresses
#      multi-component DAGs. Its VEX measurement strategies were internalized
#      into vex_strategies.py (now self-sufficient); the orchestration layer
#      (Root/Measure/Mount/Shape build) is gone. See docs/superpowers/plans/
#      2026-07-08-procedural-agent-refactor.md Phase 0a.
# None is imported here. harness.py (sandbox/commit lifecycle) is kept live for
# the project-modeling skill. exprs.py was retired in Phase 0b (the project
# pipeline uses Houdini's native ch() expressions, not a custom engine); it is
# gone, not retained. add_parm was removed from TOOL_HANDLERS in Phase 1b (no TS
# tool exposed it; the official design_params path forbids subnet spare parms,
# so it was dead agent surface — the function stays in harness.py for internal use).

# Knowledge and eval handlers (available only in Houdini runtime)
try:
    from edini.ui.knowledge_store import search_entries
except ImportError:
    def search_entries(query="", category="", limit=10):
        return {"success": False, "error": "Knowledge store not available in this context"}

try:
    from edini.eval.evaluator import EvalStore
except ImportError:
    EvalStore = None


def _edini_get_eval_stats(period: int = 10) -> dict[str, Any]:
    """Get evaluation statistics for recent sessions."""
    if EvalStore is None:
        return {"success": False, "error": "Eval system not available in this context"}
    try:
        store = EvalStore()
        sessions = store.get_recent_sessions(period)
        if not sessions:
            return {"success": True, "sessions_analyzed": 0, "message": "No evaluation data yet"}

        dims = ["reliability", "efficiency", "cost", "tool_accuracy", "task_completion"]
        scores = {d: [] for d in dims}
        for s in sessions:
            for d in dims:
                score = getattr(s, d, None)
                if score is not None:
                    scores[d].append(score)

        avg = {d: round(sum(v) / len(v), 2) if v else None for d, v in scores.items()}
        weakest = min((d for d in dims if avg[d] is not None), key=lambda d: avg[d], default=None)

        return {
            "success": True,
            "sessions_analyzed": len(sessions),
            "average_scores": avg,
            "weakest_dimension": weakest,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def _project_create(name: str | None = None, goal: str | None = None, **_) -> dict[str, Any]:
    """Create a new Project HDA — the first step of any modeling task.

    Returns the core node path (feed to project_build_scaffold). The Project
    HDA is a SOP-context edini::project instance inside a geo shell.

    Workspace-aware: if the user has an edini::project core selected in the
    network editor, REUSE it (return its path) instead of creating a new one.
    This makes "select a Project HDA → work in it" the natural flow, rather
    than always spawning a new project. Only creates new when nothing relevant
    is selected.
    """
    try:
        from edini.project.node import create_project_hda, build_state_parm_template
        from edini.project.state import STATE_PARM, save_declaration, empty_declaration
        import hou
        # Workspace awareness: reuse a selected Project HDA if present.
        try:
            for node in hou.selectedNodes():
                if node.type().name() == "edini::project":
                    # Guard: a reused node may lack the hidden __edini_state
                    # spare parm (the HDA type def doesn't bake it in; it's only
                    # installed at create time). Without it the next call to
                    # build_scaffold fails with "node has no '__edini_state'
                    # parm". Reinstall it here so the reused node is usable.
                    if node.parm(STATE_PARM) is None:
                        node.addSpareParmTuple(build_state_parm_template())
                        # Seed an empty declaration so save_declaration has a
                        # valid base to merge components into.
                        save_declaration(
                            node,
                            empty_declaration(project_name=node.name(), goal=goal),
                        )
                    return {"success": True, "core_path": node.path(),
                            "shell_path": node.parent().path(),
                            "reused": True}
        except Exception:
            pass
        n = name or "project"
        core = create_project_hda(name=n, goal=goal)
        return {"success": True, "core_path": core.path(),
                "shell_path": hou.node(core.path()).parent().path(),
                "reused": False}
    except Exception as e:
        import traceback
        return {"success": False, "error": str(e),
                "traceback": traceback.format_exc()}


def _project_build_scaffold(core_path: str | None = None,
                            components: list | None = None,
                            design_params: list | None = None, **_) -> dict[str, Any]:
    """Build component scaffolds + design params inside a Project HDA core node.

    `core_path` is the edini::project SOP HDA instance. If `components` is
    given (list of component dicts), it replaces the declaration's components
    before scaffolding; if `design_params` is given (list of {name,default,min,
    max,label,components}), it replaces the design params. Otherwise the existing
    declaration is rebuilt. Wraps builder.build_project_scaffold with error guarding.
    """
    if not core_path:
        return {"success": False, "error": "'core_path' is required (the edini::project SOP HDA instance path)"}
    try:
        import hou
        node = hou.node(core_path)
        if node is None:
            return {"success": False, "error": f"core node not found: {core_path}"}
        declaration = None
        if components is not None or design_params is not None:
            from edini.project.state import load_declaration
            declaration = load_declaration(node)
            if components is not None:
                declaration["components"] = components
            if design_params is not None:
                declaration["design_params"] = design_params
        return build_project_scaffold(node, declaration=declaration)
    except Exception as e:
        import traceback
        return {"success": False, "error": str(e),
                "traceback": traceback.format_exc()}


def _project_promote_params(core_path: str | None = None, **_) -> dict[str, Any]:
    """Promote component subnet spare parms to the Project HDA core interface."""
    if not core_path:
        return {"success": False, "error": "'core_path' is required"}
    try:
        import hou
        node = hou.node(core_path)
        if node is None:
            return {"success": False, "error": f"core node not found: {core_path}"}
        return promote_params(node)
    except Exception as e:
        import traceback
        return {"success": False, "error": str(e),
                "traceback": traceback.format_exc()}


def _project_add_anchors(core_path: str | None = None,
                         component_id: str | None = None,
                         anchors: list | None = None, **_) -> dict[str, Any]:
    """Procedurally generate anchor points from a component's geometry.

    Each anchor is a measurement spec resolved into a LIVE VEX wrangle (reads
    the component geometry's bbox on every cook), so anchors recompute when the
    geometry changes. Replaces hardcoded addpoint coordinates.
    """
    if not core_path:
        return {"success": False, "error": "'core_path' is required"}
    if not component_id:
        return {"success": False, "error": "'component_id' is required"}
    if not anchors:
        return {"success": False, "error": "'anchors' (list of {measure,name,...}) is required"}
    try:
        import hou
        node = hou.node(core_path)
        if node is None:
            return {"success": False, "error": f"core node not found: {core_path}"}
        return add_anchors(node, component_id, anchors)
    except Exception as e:
        import traceback
        return {"success": False, "error": str(e),
                "traceback": traceback.format_exc()}


def _project_emit_markers(core_path: str | None = None,
                          component_id: str | None = None,
                          markers: list | None = None, **_) -> dict[str, Any]:
    """Emit semantic @name marker points into a component's geometry so a
    downstream by_name anchor picks them at REAL geometric locations."""
    if not core_path:
        return {"success": False, "error": "'core_path' is required"}
    if not component_id:
        return {"success": False, "error": "'component_id' is required"}
    if not markers:
        return {"success": False,
                "error": "'markers' (list of {name, measure, ...}) is required"}
    try:
        import hou
        node = hou.node(core_path)
        if node is None:
            return {"success": False, "error": f"core node not found: {core_path}"}
        return emit_markers(node, component_id, markers)
    except Exception as e:
        import traceback
        return {"success": False, "error": str(e),
                "traceback": traceback.format_exc()}


def _project_emit_component(core_path: str | None = None,
                            component_id: str | None = None,
                            archetype: str | None = None,
                            params: dict | None = None, **_) -> dict[str, Any]:
    """Build a component's geometry from an ARCHETYPE (box_panel/...)."""
    if not core_path:
        return {"success": False, "error": "'core_path' is required"}
    if not component_id:
        return {"success": False, "error": "'component_id' is required"}
    if not archetype:
        return {"success": False, "error": "'archetype' is required (e.g. 'box_panel')"}
    try:
        import hou
        node = hou.node(core_path)
        if node is None:
            return {"success": False, "error": f"core node not found: {core_path}"}
        return emit_component(node, component_id, archetype, params or {})
    except Exception as e:
        import traceback
        return {"success": False, "error": str(e),
                "traceback": traceback.format_exc()}


def _project_snapshot_component(core_path: str | None = None,
                                component_id: str | None = None,
                                label: str | None = None, **_) -> dict[str, Any]:
    """Snapshot a component's current state for later restore."""
    if not core_path:
        return {"success": False, "error": "'core_path' is required"}
    if not component_id:
        return {"success": False, "error": "'component_id' is required"}
    try:
        import hou
        node = hou.node(core_path)
        if node is None:
            return {"success": False, "error": f"core node not found: {core_path}"}
        return snapshot_component(node, component_id, label)
    except Exception as e:
        import traceback
        return {"success": False, "error": str(e),
                "traceback": traceback.format_exc()}


def _project_restore_component(core_path: str | None = None,
                               component_id: str | None = None,
                               snapshot_id: str | None = None, **_) -> dict[str, Any]:
    """Restore a component from a snapshot (replaces current state)."""
    if not core_path:
        return {"success": False, "error": "'core_path' is required"}
    if not component_id:
        return {"success": False, "error": "'component_id' is required"}
    if not snapshot_id:
        return {"success": False, "error": "'snapshot_id' is required"}
    try:
        import hou
        node = hou.node(core_path)
        if node is None:
            return {"success": False, "error": f"core node not found: {core_path}"}
        return restore_component(node, component_id, snapshot_id)
    except Exception as e:
        import traceback
        return {"success": False, "error": str(e),
                "traceback": traceback.format_exc()}


def _project_list_snapshots(core_path: str | None = None,
                            component_id: str | None = None, **_) -> dict[str, Any]:
    """List component snapshots in the core's _snapshots store."""
    if not core_path:
        return {"success": False, "error": "'core_path' is required"}
    try:
        import hou
        node = hou.node(core_path)
        if node is None:
            return {"success": False, "error": f"core node not found: {core_path}"}
        return list_snapshots(node, component_id)
    except Exception as e:
        import traceback
        return {"success": False, "error": str(e),
                "traceback": traceback.format_exc()}


# ── Guarded set_param wrappers (Fix 1) ──────────────────────────────────
# Intercept `houdini_set_param` / `houdini_set_params_batch` when they target
# a wrangle `snippet` inside a Project HDA component, and refuse hand-rolled
# addpoint() — pointing the agent at project_add_anchors instead. Shifts the
# "use declaritive anchors" rule from SKILL.md prose to a fail-fast gate.
# See edini.project.guards for scope/escape-hatch details.
def _guarded_set_param(**kw) -> dict[str, Any]:
    node_path = kw.get("node_path")
    param_name = kw.get("param_name")
    value = kw.get("value")
    if node_path and param_name == "snippet":
        blocked = lint_wrangle_snippet(node_path, value)
        if blocked is not None:
            return blocked
    return set_param(node_path, param_name, value)


def _guarded_set_params_batch(**kw) -> dict[str, Any]:
    node_path = kw.get("node_path")
    params = kw.get("params") or {}
    if node_path and isinstance(params.get("snippet"), str):
        blocked = lint_wrangle_snippet(node_path, params["snippet"])
        if blocked is not None:
            # Mirror the batch shape so the agent's partial-result handling
            # still works, but make refusal unambiguous via success:false.
            blocked["set_count"] = 0
            blocked["total_count"] = len(params)
            return blocked
    return set_params_batch(node_path, params)


# Map tool names to handler functions
TOOL_HANDLERS: dict[str, Callable[..., dict[str, Any]]] = {
    "houdini_get_scene_info": lambda **kw: get_scene_info(),
    "houdini_create_node": lambda **kw: create_node(
        node_type=kw["node_type"], name=kw.get("name"),
        parent_path=kw.get("parent_path", "/obj"),
    ),
    "houdini_delete_node": lambda **kw: delete_node(kw["node_path"]),
    "houdini_connect_nodes": lambda **kw: connect_nodes(
        from_path=kw["from_path"], to_path=kw["to_path"],
        input_index=kw.get("input_index", 0),
        output_index=kw.get("output_index", 0),
    ),
    "houdini_set_param": _guarded_set_param,
    "houdini_set_params_batch": _guarded_set_params_batch,
    "houdini_get_param": lambda **kw: get_param(kw["node_path"], kw["param_name"]),
    "houdini_list_nodes": lambda **kw: list_nodes(
        parent_path=kw.get("parent_path", "/"),
        type_filter=kw.get("type_filter"),
    ),
    "houdini_get_node": lambda **kw: get_node_info(kw["node_path"]),
    "houdini_layout_nodes": lambda **kw: layout_nodes(
        parent_path=kw.get("parent_path", "/obj"),
    ),
    "houdini_search_nodes": lambda **kw: search_nodes(kw["keyword"]),
    "houdini_get_help": lambda **kw: get_help(kw["node_type_name"]),
    "query_parms": lambda **kw: node_parms(
        kw["node_type"], category=kw.get("category", "Sop")),
    "houdini_inspect_geo": lambda **kw: inspect_geometry(kw["node_path"]),
    "houdini_run_vex": lambda **kw: run_vex(
        code=kw["code"], node_path=kw.get("node_path"),
        attrib_name=kw.get("attrib_name", "result"),
    ),
    "houdini_create_hda": lambda **kw: create_hda(
        kw["node_path"], kw["hda_name"], kw.get("hda_label", ""),
    ),
    "houdini_get_hda_info": lambda **kw: get_hda_info(kw["hda_name"]),
    # capture_review is gated by visual_verification_enabled in settings.json.
    # Defense-in-depth: even if the agent reaches this handler while VV is off,
    # refuse instead of capturing. [VISUAL-VERIFY-GATE]
    "capture_review": lambda **kw: (
        {"success": False,
         "error": "Visual verification is disabled (settings.json "
                  "visual_verification_enabled=false). Rely on numeric evidence "
                  "(inspect_health, geometry_inventory, inspect_geo)."}
        if not _load_edini_settings().get("visual_verification_enabled")
        else capture_review(
            screenshots.relocate_filepath(
                kw["filepath"], screenshots.current_session(), default_prefix="review"
            ),
            target_path=kw.get("target_path"),
            views=kw.get("views"),
            frames=kw.get("frames"),
            columns=kw.get("columns", 0),
            shading_mode=kw.get("shading_mode", "smooth"),
            home_target=kw.get("home_target", True),
            resolution=kw.get("resolution"),
        )
    ),
    "houdini_capture_network": lambda **kw: capture_network(
        screenshots.relocate_filepath(
            kw["filepath"], screenshots.current_session(), default_prefix="network"
        ),
        parent_path=kw.get("parent_path", "/obj"),
    ),
    "houdini_get_selection": lambda **kw: get_selection(),
    "houdini_check_errors": lambda **kw: check_errors(
        node_path=kw.get("node_path"),
    ),
    "houdini_set_display_flag": lambda **kw: set_display_flag(kw["node_path"]),
    "verify_orientation": lambda **kw: verify_orientation(
        kw["node_path"],
        kw.get("checks", []),
    ),
    "verify_parametric": lambda **kw: verify_parametric(
        kw["node_path"],
        kw["core_path"],
        kw["param"],
        kw["new_value"],
        expected_axis=kw.get("expected_axis"),
        min_relative_change=kw.get("min_relative_change", 0.05),
    ),
    "verify_robust": lambda **kw: verify_robust(
        kw["node_path"],
        kw["core_path"],
        params=kw.get("params"),
        samples=kw.get("samples", "min_default_max"),
    ),
    "project_repath_to_relative": lambda **kw: repath_to_relative(
        kw["core_path"],
        kw["component_id"],
    ),
    "inspect_health": lambda **kw: inspect_geometry_health(
        kw["node_path"],
        degenerate_area_eps=kw.get("degenerate_area_eps", 1e-7),
        coincident_eps=kw.get("coincident_eps", 1e-6),
    ),
    "geometry_inventory": lambda **kw: geometry_inventory(
        kw["node_path"],
        max_components=kw.get("max_components", 60),
    ),
    "houdini_capture_component_detail": lambda **kw: capture_component_detail(
        screenshots.relocate_filepath(
            kw["filepath"], screenshots.current_session(),
            default_prefix="component_detail",
        ),
        node_path=kw["node_path"],
        component_ids=kw["component_ids"],
        views=kw.get("views"),
        shading_mode=kw.get("shading_mode", "smooth"),
        resolution=kw.get("resolution"),
    ),
    "houdini_collect_diagnostics": lambda **kw: collect_diagnostics(
        kw["node_path"],
        include_geometry=kw.get("include_geometry", True),
        include_parms=kw.get("include_parms", False),
    ),
    "houdini_run_python_sandbox": lambda **kw: run_python_sandbox(
        kw["code"],
        sandbox_name=kw.get("sandbox_name", "procedural"),
        commit_on_success=kw.get("commit_on_success", False),
        delete_on_failure=kw.get("delete_on_failure", False),
        network_mode=kw.get("network_mode", False),
        output_node_name=kw.get("output_node_name"),
    ),
    "houdini_verify_asset": lambda **kw: verify_asset(
        kw["node_path"],
        expected=kw.get("expected", {}),
    ),
    "commit_sandbox": lambda **kw: commit_sandbox(
        kw["sandbox_root_path"],
        kw["final_name"],
        replace_existing=kw.get("replace_existing", False),
        orientation_checks=kw.get("orientation_checks"),
        skip_orientation=kw.get("skip_orientation", False),
        skip_structure_check=kw.get("skip_structure_check", False),
    ),
    "discard_sandbox": lambda **kw: discard_sandbox(
        kw["sandbox_root_path"],
    ),
    "edini_search_knowledge": lambda **kw: search_entries(
        query=kw.get("query", ""),
        category=kw.get("category", ""),
        limit=kw.get("limit", 10),
    ),
    "dump_parm_catalog": lambda **kw: dump_parm_catalog(
        output_path=kw.get("output_path"),
        force=kw.get("force", False),
    ),
    "edini_get_eval_stats": lambda **kw: _edini_get_eval_stats(
        period=kw.get("period", 10),
    ),
    "recipe_list": lambda **kw: recipe_list(
        query=kw.get("query", ""),
        category=kw.get("category", ""),
        kind=kw.get("kind", ""),
    ),
    "recipe_read": lambda **kw: recipe_read(kw["recipe_id"]),
    "recipe_capture": lambda **kw: recipe_capture(kw["subnet_path"]),
    "recipe_capture_tree": lambda **kw: recipe_capture_tree(kw["root_path"]),
    "recipe_rebuild": lambda **kw: recipe_rebuild(
        kw["recipe_id"],
        kw["parent_path"],
        name=kw.get("name"),
        overrides=kw.get("overrides"),
    ),
    "recipe_tree_scan": lambda **kw: scan_recipe_tree(kw["root_path"]),
    "recipe_manager_create": lambda **kw: create_recipe_manager(
        kw.get("parent_path", "/obj"),
        kw.get("name", "edini_recipe_manager"),
    ),
    "recipe_set_notes": lambda **kw: set_node_notes(
        kw["node_path"], kw["notes"]),
    # Build component scaffolds INSIDE a Project HDA core node (SOP context).
    # Pass inline `components` (list of component dicts) to set+build in one
    # shot, or omit it to rebuild the existing declaration. `core_path` is the
    # edini::project SOP HDA instance path (e.g. /obj/proj/project_core).
    "project_create": lambda **kw: _project_create(**kw),
    "project_build_scaffold": lambda **kw: _project_build_scaffold(**kw),
    "project_promote_params": lambda **kw: _project_promote_params(**kw),
    "project_add_anchors": lambda **kw: _project_add_anchors(**kw),
    "project_emit_markers": lambda **kw: _project_emit_markers(**kw),
    "project_emit_component": lambda **kw: _project_emit_component(**kw),
    "project_snapshot_component": lambda **kw: _project_snapshot_component(**kw),
    "project_restore_component": lambda **kw: _project_restore_component(**kw),
    "project_list_snapshots": lambda **kw: _project_list_snapshots(**kw),
    # One-shot per-component completion snapshot (geo_flow / anchors emitted /
    # errors). Replaces the N-tool status-gathering loop with a single call.
    "project_status": lambda **kw: project_status(kw["core_path"]),
    # Hard gate: refuse to mark the project complete until it passes
    # verification (status complete + verify_robust + verify_parametric per
    # design param). The structural cure for "declared done prematurely"
    # (bike session log). acknowledge_skip + skip_reason is the audited escape.
    "project_finalize": lambda **kw: project_finalize(
        kw["core_path"],
        acknowledge_skip=kw.get("acknowledge_skip", False),
        skip_reason=kw.get("skip_reason"),
        samples=kw.get("samples", "min_default_max"),
    ),
}

# Backward-compatibility tool aliases (pre-Task-7 rename).
# Old names map to new canonical handlers so existing Pi extension configs
# and scripts don't break after the tool-surface cleanup.
_TOOL_ALIASES: dict[str, str] = {
    "houdini_commit_sandbox": "commit_sandbox",
    "houdini_discard_sandbox": "discard_sandbox",
    "houdini_verify_orientation": "verify_orientation",
    "houdini_capture_review": "capture_review",
    "houdini_node_parms": "query_parms",
    "houdini_inspect_geometry_health": "inspect_health",
    "houdini_geometry_inventory": "geometry_inventory",
}

# Patch aliases into the handler table so dispatch works transparently.
for _alias, _target in _TOOL_ALIASES.items():
    if _target in TOOL_HANDLERS:
        TOOL_HANDLERS[_alias] = TOOL_HANDLERS[_target]





class _ToolHandler(BaseHTTPRequestHandler):
    """HTTP request handler for tool execution."""

    def do_POST(self) -> None:
        if self.path != "/execute":
            self._send_error(404, "Not found")
            return

        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            request = json.loads(body)

            tool_name = request.get("tool")
            params = request.get("params", {})

            if tool_name not in TOOL_HANDLERS:
                self._send_json({"success": False, "error": f"Unknown tool: {tool_name}"})
                return

            result = TOOL_HANDLERS[tool_name](**params)
            self._send_json(result)

        except json.JSONDecodeError as e:
            self._send_error(400, f"Invalid JSON: {e}")
        except Exception as e:
            self._send_json({"success": False, "error": str(e)})

    def do_GET(self) -> None:
        if self.path == "/health":
            # Include PID + port so a client can verify it's talking to the
            # intended Houdini instance (multi-instance diagnostics).
            self._send_json({"status": "ok", "pid": os.getpid()})
        else:
            self._send_error(404, "Not found")

    def log_message(self, format, *args) -> None:
        pass  # Suppress default logging

    def _write_response(self, code: int, body: bytes) -> None:
        """Send a JSON response; swallow client-disconnect.

        The Pi client (forwardTool) has a ~30s timeout. When a tool runs longer
        (e.g. verify_robust sweeping 7×3=21 cooks under main-thread contention),
        the client closes the socket before we finish writing. Writing to that
        closed socket raised ConnectionAbortedError and — because the result-send
        sits inside do_POST's try/except — cascaded into a SECOND failed
        error-response write that propagated uncaught and printed a scary
        traceback to the Houdini console. The client already retried (and usually
        succeeds); this is noise, not a correctness issue, so we drop it quietly.
        """
        try:
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass  # client gone (timed out) — nothing to deliver to

    def _send_json(self, data: dict[str, Any]) -> None:
        self._write_response(
            200, json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def _send_error(self, code: int, message: str) -> None:
        self._write_response(
            code, json.dumps({"success": False, "error": message}).encode("utf-8"))


class ToolExecutor:
    """Manages the tool executor HTTP server lifecycle."""

    def __init__(self, host: str = "127.0.0.1", port: int = 0):
        self._host = host
        self._requested_port = port
        self._port: int = 0
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        return self._port

    def start(self) -> None:
        """Start the HTTP server on a background daemon thread.

        Multi-instance safe: binds port 0 (OS-assigned) if the requested port
        is already taken, so two Houdini processes each get their own unique
        server. The actual bound port is recorded in ``self._port`` and must be
        propagated to Pi subprocesses via the ``EDINI_TOOL_PORT`` env var (see
        ``get_active_tool_port`` / ``get_pi_env``).
        """
        if self._server is not None:
            return
        # Try the requested port first (default 9876 for single-instance
        # backward compat). On Windows SO_REUSEADDR lets a second process
        # "successfully" bind but the first process keeps receiving all
        # connections — silent cross-process routing. So we probe with a
        # throwaway socket instead of relying on HTTPServer bind to fail.
        port = self._probe_free_port(self._requested_port)
        self._server = HTTPServer((self._host, port), _ToolHandler)
        self._port = self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        _write_port_file(self._port)

    @staticmethod
    def _probe_free_port(preferred: int) -> int:
        """Return ``preferred`` if free, else an OS-assigned free port.

        Uses a quick socket bind to test availability. Closing the probe socket
        before HTTPServer binds is safe here because the server thread starts
        immediately after and we are the only caller in this process.
        """
        import socket
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", preferred))
            return preferred
        except OSError:
            # Preferred port taken by another Houdini (or unrelated process).
            # Let the OS pick a free port — HTTPServer with port 0 binds an
            # ephemeral port and records it in server_address.
            return 0

    def stop(self) -> None:
        """Shut down the HTTP server."""
        if self._server is not None:
            self._server.shutdown()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None
        _remove_port_file()


# --- Process-level singleton: decoupled from any UI window -----------------
#
# The ToolExecutor is a global, stateless HTTP server that every Pi subprocess
# calls back into via the EDINI_TOOL_PORT env var (see config.get_pi_env). It
# carries no per-client state, so N Pi processes spawned by one Houdini share
# one server. Previously its lifetime was bound to EdiniMainWindow (constructed
# in __init__, stopped in closeEvent), which forced any other RPC consumer
# (e.g. the Project HDA panel) to go through the main window. This accessor
# makes it a process-level singleton: the first caller creates + starts it, all
# callers share it, and it is never torn down by a single window close (it
# lives until the Houdini process exits; its server thread is a daemon, so it
# is reaped automatically).
#
# MULTI-INSTANCE: when two Houdini processes run, each binds its OWN unique
# port (the preferred 9876 if free, else an OS-assigned ephemeral port — see
# ToolExecutor._probe_free_port). The actual port is exposed via
# ``get_active_tool_port`` and propagated to every Pi subprocess through
# ``EDINI_TOOL_PORT`` (config.get_pi_env reads this accessor). A per-PID
# discovery file under ~/.edini/ports/ aids debugging which Houdini owns
# which port.

_global_executor: ToolExecutor | None = None


def _port_file_path() -> Path:
    """Per-PID discovery file recording the port this Houdini bound.

    Diagnostic only — lets `ls ~/.edini/ports/` show which Houdini (PID) is
    serving which port. Not used for routing (the EDINI_TOOL_PORT env var is
    the routing channel).
    """
    return Path.home() / ".edini" / "ports" / f"{os.getpid()}.json"


def _write_port_file(port: int) -> None:
    """Record the bound port + PID + host for diagnostics. Best-effort."""
    try:
        p = _port_file_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"pid": os.getpid(), "port": port,
                                 "host": "127.0.0.1"}), encoding="utf-8")
        atexit.register(_remove_port_file)
    except OSError:
        pass


def _remove_port_file() -> None:
    """Clean up the per-PID discovery file. Best-effort."""
    try:
        _port_file_path().unlink(missing_ok=True)
    except OSError:
        pass


def get_active_tool_port() -> int:
    """Return the actual port this process's ToolExecutor bound, starting the
    executor if needed. This is the single source of truth for the
    ``EDINI_TOOL_PORT`` env var passed to Pi subprocesses — it MUST reflect the
    real bound port, not the config default, so tool calls route to THIS
    Houdini and not whichever sibling process grabbed port 9876 first.
    """
    exe = get_tool_executor()
    return exe.port


def get_tool_executor() -> ToolExecutor:
    """Return the process-level ToolExecutor singleton (creating + starting it
    on first call). Safe to call from any thread; idempotent.
    """
    global _global_executor
    if _global_executor is None:
        _global_executor = ToolExecutor()
        _global_executor.start()
    return _global_executor

