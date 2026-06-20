"""Tool executor HTTP server.

Runs inside Houdini's Python process. Receives tool execution requests
from Pi extensions via HTTP POST and dispatches to node_utils.
"""
from __future__ import annotations

import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any, Callable

from edini.node_utils import (
    get_scene_info,  create_node, delete_node, connect_nodes,
    set_param, set_params_batch, get_param, list_nodes, get_node_info, layout_nodes,
    search_nodes, get_help, inspect_geometry,
    run_python, run_vex, create_hda, get_hda_info,
    capture_review, capture_network, capture_component_detail,
    get_selection, check_errors, set_display_flag,
    verify_orientation, inspect_geometry_health, geometry_inventory,
    node_parms,
)
from edini import screenshots
from edini.harness import (
    collect_diagnostics,
    run_python_sandbox,
    verify_asset,
    commit_sandbox,
    discard_sandbox,
    build_procedural_asset,
    build_variant_scatter,
    dump_parm_catalog,
    validate_recipe_tool,
    build_component_tool,
    assemble_components_tool,
)

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
    ),
    "houdini_set_param": lambda **kw: set_param(
        kw["node_path"], kw["param_name"], kw["value"],
    ),
    "houdini_set_params_batch": lambda **kw: set_params_batch(
        kw["node_path"], kw["params"],
    ),
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
    "houdini_node_parms": lambda **kw: node_parms(
        kw["node_type"], category=kw.get("category", "Sop")),
    "houdini_inspect_geo": lambda **kw: inspect_geometry(kw["node_path"]),
    "houdini_run_python": lambda **kw: run_python(kw["code"]),
    "houdini_run_vex": lambda **kw: run_vex(
        code=kw["code"], node_path=kw.get("node_path"),
        attrib_name=kw.get("attrib_name", "result"),
    ),
    "houdini_create_hda": lambda **kw: create_hda(
        kw["node_path"], kw["hda_name"], kw.get("hda_label", ""),
    ),
    "houdini_get_hda_info": lambda **kw: get_hda_info(kw["hda_name"]),
    "houdini_capture_review": lambda **kw: capture_review(
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
    "houdini_verify_orientation": lambda **kw: verify_orientation(
        kw["node_path"],
        kw.get("checks", []),
    ),
    "houdini_inspect_geometry_health": lambda **kw: inspect_geometry_health(
        kw["node_path"],
        degenerate_area_eps=kw.get("degenerate_area_eps", 1e-7),
        coincident_eps=kw.get("coincident_eps", 1e-6),
    ),
    "houdini_geometry_inventory": lambda **kw: geometry_inventory(
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
    "houdini_commit_sandbox": lambda **kw: commit_sandbox(
        kw["sandbox_root_path"],
        kw["final_name"],
        replace_existing=kw.get("replace_existing", False),
        orientation_checks=kw.get("orientation_checks"),
        skip_orientation=kw.get("skip_orientation", False),
        skip_structure_check=kw.get("skip_structure_check", False),
    ),
    "houdini_discard_sandbox": lambda **kw: discard_sandbox(
        kw["sandbox_root_path"],
    ),
    "houdini_build_procedural_asset": lambda **kw: build_procedural_asset(
        kw["recipe"],
        sandbox_name=kw.get("sandbox_name"),
        delete_on_failure=kw.get("delete_on_failure", False),
    ),
    "houdini_variant_scatter": lambda **kw: build_variant_scatter(
        kw["recipe"],
        sandbox_name=kw.get("sandbox_name"),
        delete_on_failure=kw.get("delete_on_failure", False),
    ),
    "edini_search_knowledge": lambda **kw: search_entries(
        query=kw.get("query", ""),
        category=kw.get("category", ""),
        limit=kw.get("limit", 10),
    ),
    "validate_recipe": lambda **kw: validate_recipe_tool(
        kw["recipe"],
        catalog_path=kw.get("catalog_path"),
    ),
    "build_component": lambda **kw: build_component_tool(
        kw["recipe"],
        kw["component_id"],
        kw["sandbox_root_path"],
        catalog_path=kw.get("catalog_path"),
    ),
    "assemble_components": lambda **kw: assemble_components_tool(
        kw["recipe"],
        kw["sandbox_root_path"],
        kw["cache_root"],
    ),
    "dump_parm_catalog": lambda **kw: dump_parm_catalog(
        output_path=kw.get("output_path"),
        force=kw.get("force", False),
    ),
    "edini_get_eval_stats": lambda **kw: _edini_get_eval_stats(
        period=kw.get("period", 10),
    ),
}


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
            self._send_json({"status": "ok"})
        else:
            self._send_error(404, "Not found")

    def log_message(self, format, *args) -> None:
        pass  # Suppress default logging

    def _send_json(self, data: dict[str, Any]) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, code: int, message: str) -> None:
        body = json.dumps({"success": False, "error": message}).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class ToolExecutor:
    """Manages the tool executor HTTP server lifecycle."""

    def __init__(self, host: str = "127.0.0.1", port: int = 9876):
        self._host = host
        self._port = port
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        return self._port

    def start(self) -> None:
        """Start the HTTP server on a background daemon thread."""
        if self._server is not None:
            return
        self._server = HTTPServer((self._host, self._port), _ToolHandler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Shut down the HTTP server."""
        if self._server is not None:
            self._server.shutdown()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None
