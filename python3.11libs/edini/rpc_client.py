"""Pi RPC client for Houdini.

Manages the Pi subprocess lifecycle and JSON-RPC stdin/stdout protocol.
Runs on a QThread to avoid blocking the Houdini UI.
"""
from __future__ import annotations

import json
import os
import sys
import subprocess
from typing import Any

from PySide6.QtCore import QThread, Signal, QObject

from edini.config import get_pi_command, get_pi_env, TOOL_EXECUTOR_PORT


class RpcClient(QObject):
    """Manages the Pi subprocess and JSON-RPC communication.

    Signals are emitted on the main thread (queued connections).
    """

    text_delta = Signal(str)                # Streaming text chunk
    thinking_delta = Signal(str)            # Thinking/reasoning text chunk
    tool_call = Signal(str, str, object)    # tool_name, tool_call_id, args dict
    tool_result = Signal(str, str, str)     # tool_name, tool_call_id, result
    agent_started = Signal()
    agent_finished = Signal()
    error_occurred = Signal(str)
    status_changed = Signal(str)
    stats_updated = Signal(object)          # dict: tokens, cost, contextUsage
    messages_received = Signal(object)       # list: messages from get_messages
    session_switched = Signal(str)           # session path after switch
    extension_info = Signal(str)            # info/warning from pi extensions (tools loaded, etc.)
    vision_description = Signal(object)     # vision model descriptions from pi-visionizer
    models_received = Signal(object)        # list of model dicts from get_available_models
    model_changed = Signal(object)          # model dict from set_model / cycle_model
    thinking_changed = Signal(str)          # thinking level string

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._process: subprocess.Popen | None = None
        self._thread: QThread | None = None
        self._worker: _RpcWorker | None = None
        self._is_running = False
        self._cwd: str | None = None

    def set_cwd(self, cwd: str) -> None:
        """Set the working directory (must be called before start)."""
        self._cwd = cwd

    @property
    def is_running(self) -> bool:
        return self._is_running

    def start(self) -> None:
        """Launch the Pi subprocess and start reading its output."""
        if self._is_running:
            return

        pi_cmd = get_pi_command()
        self._thread = QThread()
        self._worker = _RpcWorker(pi_cmd, TOOL_EXECUTOR_PORT, self._cwd)
        self._worker.moveToThread(self._thread)

        self._worker.text_delta.connect(self.text_delta)
        self._worker.thinking_delta.connect(self.thinking_delta)
        self._worker.tool_call.connect(self.tool_call)
        self._worker.tool_result.connect(self.tool_result)
        self._worker.agent_started.connect(self.agent_started)
        self._worker.agent_finished.connect(self.agent_finished)
        self._worker.error_occurred.connect(self.error_occurred)
        self._worker.status_changed.connect(self.status_changed)
        self._worker.stats_received.connect(self.stats_updated)
        self._worker.messages_received.connect(self.messages_received)
        self._worker.session_switched.connect(self.session_switched)
        self._worker.extension_info.connect(self.extension_info)
        self._worker.vision_description.connect(self.vision_description)
        self._worker.models_received.connect(self.models_received)
        self._worker.model_changed.connect(self.model_changed)
        self._worker.thinking_changed.connect(self.thinking_changed)

        self._thread.started.connect(self._worker.run)
        self._thread.start()
        self._is_running = True
        self.status_changed.emit("connecting")

    def stop(self) -> None:
        """Terminate the Pi subprocess and cleanup."""
        if not self._is_running:
            return

        if self._worker:
            self._worker.stop()
        if self._thread:
            self._thread.quit()
            self._thread.wait(3000)
        self._is_running = False
        self.status_changed.emit("disconnected")

    def send_prompt(self, text: str, images: list[dict] | None = None) -> None:
        """Send a user prompt to Pi."""
        if self._worker:
            cmd: dict[str, Any] = {"type": "prompt", "message": text}
            if images:
                cmd["images"] = images
                pass  # images attached
            self._worker.send_command(cmd)

    def send_abort(self) -> None:
        """Abort the current agent operation."""
        if self._worker:
            self._worker.send_command({"type": "abort"})

    def send_steer(self, text: str) -> None:
        """Queue a steering message during streaming."""
        if self._worker:
            self._worker.send_command({"type": "steer", "message": text})

    def send_set_model(self, provider: str, model_id: str) -> None:
        """Switch Pi to a different model (no restart needed)."""
        if self._worker:
            self._worker.send_command({
                "type": "set_model",
                "provider": provider,
                "modelId": model_id,
            })

    def send_get_stats(self) -> None:
        """Request session token/cost statistics from Pi."""
        if self._worker:
            self._worker.send_command({"type": "get_session_stats"})

    def send_new_session(self) -> None:
        """Tell Pi to start a new session (equivalent to /new)."""
        if self._worker:
            self._worker.send_command({"type": "new_session"})

    def send_switch_session(self, session_path: str) -> None:
        """Tell Pi to switch to a different session (equivalent to /resume)."""
        if self._worker:
            self._worker.send_command({
                "type": "switch_session",
                "sessionPath": session_path,
            })

    def send_set_session_name(self, name: str) -> None:
        """Set a display name for the current session."""
        if self._worker:
            self._worker.send_command({
                "type": "set_session_name",
                "name": name,
            })

    def send_get_state(self) -> None:
        """Request current session state from Pi."""
        if self._worker:
            self._worker.send_command({"type": "get_state"})

    def send_get_messages(self) -> None:
        """Request all messages from Pi's current session."""
        if self._worker:
            self._worker.send_command({"type": "get_messages"})

    def send_get_available_models(self) -> None:
        """Request list of all configured models from Pi."""
        if self._worker:
            self._worker.send_command({"type": "get_available_models"})

    def send_cycle_model(self) -> None:
        """Cycle to the next available model."""
        if self._worker:
            self._worker.send_command({"type": "cycle_model"})

    def send_set_thinking_level(self, level: str) -> None:
        """Set thinking level: off, minimal, low, medium, high, xhigh."""
        if self._worker:
            self._worker.send_command({"type": "set_thinking_level", "level": level})

    def restart(self) -> None:
        """Restart the Pi subprocess (needed after API key change)."""
        was_running = self._is_running
        self.stop()
        if was_running:
            self.start()


class _RpcWorker(QObject):
    """Worker object running on a QThread. Manages subprocess I/O."""

    text_delta = Signal(str)
    thinking_delta = Signal(str)
    tool_call = Signal(str, str, object)
    tool_result = Signal(str, str, str)
    agent_started = Signal()
    agent_finished = Signal()
    error_occurred = Signal(str)
    status_changed = Signal(str)
    stats_received = Signal(object)
    messages_received = Signal(object)
    session_switched = Signal(str)
    extension_info = Signal(str)            # info/warning from pi extensions (tools loaded, etc.)
    vision_description = Signal(object)      # vision model descriptions from pi-visionizer
    models_received = Signal(object)        # list of model dicts from get_available_models
    model_changed = Signal(object)          # model dict from set_model / cycle_model
    thinking_changed = Signal(str)          # thinking level string

    def __init__(self, pi_cmd: list[str], tool_port: int, cwd: str | None = None):
        super().__init__()
        self._pi_cmd = pi_cmd
        self._tool_port = tool_port
        self._cwd = cwd
        self._process: subprocess.Popen | None = None
        self._should_stop = False

    def run(self) -> None:
        """Start Pi subprocess and read stdout JSONL events."""
        try:
            popen_kwargs: dict[str, Any] = {
                "stdin": subprocess.PIPE,
                "stdout": subprocess.PIPE,
                "stderr": subprocess.PIPE,
                "text": True,
                "bufsize": 1,
                "env": get_pi_env(),
                "cwd": self._cwd,
            }
            # On Windows, suppress console window when spawning pi.cmd
            if sys.platform == "win32":
                popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
                popen_kwargs["startupinfo"] = startupinfo

            self._process = subprocess.Popen(self._pi_cmd, **popen_kwargs)
            self.status_changed.emit("connected")

            # ── Read stderr in a daemon thread for debug logging ──
            import threading
            def _read_stderr():
                try:
                    for line in self._process.stderr:
                        if self._should_stop:
                            break
                        line = line.strip()
                        if line:
                            # Print to Houdini console for debugging
                            print(f"[pi:stderr] {line}", flush=True)
                except Exception:
                    pass
            threading.Thread(target=_read_stderr, daemon=True).start()

            for line in self._process.stdout:
                if self._should_stop:
                    break

                line = line.strip()
                if not line:
                    continue

                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue

                self._dispatch_event(event)

        except FileNotFoundError:
            self.error_occurred.emit(
                "Pi not found. Install: npm install -g @earendil-works/pi-coding-agent"
            )
            self.status_changed.emit("error")
        except Exception as e:
            self.error_occurred.emit(f"Pi process error: {e}")
            self.status_changed.emit("error")

    def stop(self) -> None:
        """Signal the worker to stop and terminate the process."""
        self._should_stop = True
        if self._process:
            try:
                self._process.terminate()
                try:
                    self._process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self._process.kill()
                    self._process.wait(timeout=2)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass

    def send_command(self, cmd: dict[str, Any]) -> None:
        """Send a JSON command to Pi's stdin."""
        if self._process and self._process.stdin:
            try:
                self._process.stdin.write(json.dumps(cmd, ensure_ascii=True) + "\n")
                self._process.stdin.flush()
            except (BrokenPipeError, OSError) as e:
                self.error_occurred.emit(f"Failed to send command: {e}")

    def _dispatch_event(self, event: dict[str, Any]) -> None:
        """Route RPC events to the appropriate signal."""
        event_type = event.get("type", "")

        if event_type == "message_update":
            delta = event.get("assistantMessageEvent", {})
            delta_type = delta.get("type", "")
            if delta_type == "text_delta":
                self.text_delta.emit(delta.get("delta", ""))
            elif delta_type == "thinking_delta":
                self.thinking_delta.emit(delta.get("delta", ""))

        elif event_type == "message_end":
            # Pi emits this when the model turn finishes (or fails). When the
            # model returned an error (400 bad params, insufficient quota, 429,
            # etc.), stopReason is "error" and errorMessage carries the detail.
            # Without this, provider/model errors are silently swallowed — the
            # UI shows nothing and the user has no idea why the turn produced
            # no output.
            msg = event.get("message", {}) or {}
            if isinstance(msg, dict) and msg.get("stopReason") == "error":
                err = msg.get("errorMessage") or "Model call failed (no message)"
                self.error_occurred.emit(err)

        elif event_type == "tool_execution_start":
            self.tool_call.emit(
                event.get("toolName", ""),
                event.get("toolCallId", ""),
                event.get("args", {}),
            )

        elif event_type == "tool_execution_end":
            self.tool_result.emit(
                event.get("toolName", ""),
                event.get("toolCallId", ""),
                json.dumps(event.get("result", {}), ensure_ascii=True),
            )

        elif event_type == "agent_start":
            self.agent_started.emit()

        elif event_type == "agent_end":
            self.agent_finished.emit()

        elif event_type == "response":
            if not event.get("success", True):
                self.error_occurred.emit(event.get("error", "Unknown error"))
            elif event.get("command") == "get_session_stats":
                self.stats_received.emit(event.get("data", {}))
            elif event.get("command") == "get_messages":
                data = event.get("data", {})
                self.messages_received.emit(data.get("messages", []))
            elif event.get("command") == "new_session":
                data = event.get("data", {})
                if not data.get("cancelled", False):
                    self.send_command({"type": "get_state"})
            elif event.get("command") == "switch_session":
                data = event.get("data", {})
                if not data.get("cancelled", False):
                    self.send_command({"type": "get_state"})
            elif event.get("command") == "get_state":
                data = event.get("data", {})
                session_file = data.get("sessionFile", "")
                if session_file:
                    self.session_switched.emit(session_file)
            elif event.get("command") == "get_available_models":
                data = event.get("data", {})
                self.models_received.emit(data.get("models", []))
            elif event.get("command") == "set_model":
                data = event.get("data", {})
                if data:
                    self.model_changed.emit(data)
            elif event.get("command") == "cycle_model":
                data = event.get("data", {})
                if data and data.get("model"):
                    self.model_changed.emit(data.get("model"))
                    self.thinking_changed.emit(data.get("thinkingLevel", ""))

        elif event_type == "extension_error":
            self.error_occurred.emit(f"Extension: {event.get('error', '')}")

        elif event_type == "extension_ui_request":
            if event.get("method") == "notify":
                notify_type = event.get("notifyType", "info")
                message = event.get("message", "")
                # Check for vision_description payload from pi-visionizer
                try:
                    payload = json.loads(message)
                    if isinstance(payload, dict) and payload.get("event") == "vision_description":
                        self.vision_description.emit(payload)  # full payload (includes source, imageData, imagePath)
                        return
                except (json.JSONDecodeError, TypeError):
                    pass
                if notify_type == "error":
                    self.error_occurred.emit(f"[{notify_type}] {message}")
                else:
                    self.extension_info.emit(message)
