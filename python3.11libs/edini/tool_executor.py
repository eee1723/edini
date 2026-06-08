"""Tool executor HTTP server.

Runs inside Houdini's Python process. Receives tool execution requests
from Pi extensions via HTTP POST and dispatches to node_utils.
"""
from __future__ import annotations

import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any, Callable

from edini.eval.store import EvalStore
from edini.node_utils import (
    get_scene_info,  create_node, delete_node, connect_nodes,
    set_param, get_param, list_nodes, get_node_info, layout_nodes,
    search_nodes, get_help, inspect_geometry,
    run_python, run_vex, create_hda, get_hda_info,
    get_selection, check_errors, set_display_flag,
)

def get_eval_stats(period: int = 10) -> dict:
    """Read from SQLite and return evaluation stats for agent self-reflection."""
    try:
        store = EvalStore()
        stats = store.get_stats_summary(period=period)
        return {"success": True, **stats}
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

    # Selection / errors / display — missing from initial implementation
    "houdini_get_selection": lambda **kw: get_selection(),
    "houdini_check_errors": lambda **kw: check_errors(
        node_path=kw.get("node_path"),
    ),
    "houdini_set_display_flag": lambda **kw: set_display_flag(
        kw["node_path"],
    ),

    # Evaluation tools
    "edini_get_eval_stats": lambda **kw: get_eval_stats(
        period=kw.get("period", 10),
    ),
}


def test_api_call(provider: str, model: str, api_key: str) -> dict:
    """Test an LLM API connection by sending a minimal prompt."""
    import urllib.request, urllib.error, ssl

    try:
        # Use unverified SSL context for Houdini's embedded Python
        ctx = ssl._create_unverified_context()

        if provider == "deepseek":
            url = "https://api.deepseek.com/chat/completions"
            body = json.dumps({
                "model": model,
                "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
                "temperature": 0.01,
                "max_tokens": 10,
            }).encode("utf-8")
            req = urllib.request.Request(url, data=body, headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            })
        elif provider == "anthropic":
            url = "https://api.anthropic.com/v1/messages"
            body = json.dumps({
                "model": model, "max_tokens": 10,
                "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
            }).encode("utf-8")
            req = urllib.request.Request(url, data=body, headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            })
        elif provider in ("google", "gemini"):
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            body = json.dumps({
                "contents": [{"parts": [{"text": "Reply with exactly: OK"}]}],
                "generationConfig": {"maxOutputTokens": 10, "temperature": 0.01},
            }).encode("utf-8")
            req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        elif provider == "openai":
            base = "https://api.openai.com/v1"
            url = f"{base}/chat/completions"
            body = json.dumps({
                "model": model,
                "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
                "temperature": 0.01, "max_tokens": 10,
            }).encode("utf-8")
            req = urllib.request.Request(url, data=body, headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            })
        elif provider == "aliyun":
            url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
            body = json.dumps({
                "model": model,
                "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
                "temperature": 0.01, "max_tokens": 10,
            }).encode("utf-8")
            req = urllib.request.Request(url, data=body, headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            })
        elif provider == "openrouter":
            url = "https://openrouter.ai/api/v1/chat/completions"
            body = json.dumps({
                "model": model,
                "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
                "temperature": 0.01, "max_tokens": 10,
            }).encode("utf-8")
            req = urllib.request.Request(url, data=body, headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            })
        elif provider == "zhipu":
            url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
            body = json.dumps({
                "model": model,
                "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
                "temperature": 0.01, "max_tokens": 10,
            }).encode("utf-8")
            req = urllib.request.Request(url, data=body, headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            })
        else:
            return {"success": False, "error": f"Unknown provider: {provider}"}

        resp = urllib.request.urlopen(req, timeout=15, context=ctx)
        data = json.loads(resp.read().decode("utf-8"))

        # Extract response text
        if provider == "anthropic":
            reply = data.get("content", [{}])[0].get("text", "")
        elif provider in ("google", "gemini"):
            reply = (data.get("candidates", [{}])[0]
                     .get("content", {})
                     .get("parts", [{}])[0]
                     .get("text", ""))
        else:
            reply = data.get("choices", [{}])[0].get("message", {}).get("content", "")

        return {"success": True, "reply": reply.strip()[:100]}

    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")[:300]
        return {"success": False, "error": f"HTTP {e.code}: {err_body}"}
    except urllib.error.URLError as e:
        return {"success": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        return {"success": False, "error": f"Error: {e}"}


class _ToolHandler(BaseHTTPRequestHandler):
    """HTTP request handler for tool execution."""

    def do_POST(self) -> None:
        if self.path == "/execute":
            self._handle_execute()
        elif self.path == "/test_model":
            self._handle_test_model()
        else:
            self._send_error(404, "Not found")

    def _handle_execute(self):
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

    def _handle_test_model(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            request = json.loads(body)

            provider = request.get("provider", "")
            model = request.get("model", "")
            api_key = request.get("api_key", "")

            if not provider:
                self._send_json({"success": False, "error": "No provider specified"})
                return
            if not model:
                self._send_json({"success": False, "error": "No model specified"})
                return
            if not api_key:
                self._send_json({"success": False, "error": "No API key"})
                return

            result = test_api_call(provider, model, api_key)
            self._send_json(result)

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
