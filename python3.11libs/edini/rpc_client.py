"""Pi RPC client for Houdini.

Manages the Pi subprocess lifecycle and JSON-RPC stdin/stdout protocol.
Runs on a QThread to avoid blocking the Houdini UI.
"""
from __future__ import annotations

import json
import subprocess
from typing import Any

from PySide6.QtCore import QThread, Signal, QObject

from edini.config import get_pi_command, get_pi_env, TOOL_EXECUTOR_PORT


class RpcClient(QObject):
    """Manages the Pi subprocess and JSON-RPC communication.

    Signals are emitted on the main thread (queued connections).
    """

    text_delta = Signal(str)                # Streaming text chunk
    tool_call = Signal(str, str, object)    # tool_name, tool_call_id, args dict
    agent_started = Signal()
    agent_finished = Signal()
    error_occurred = Signal(str)
    status_changed = Signal(str)
    stats_updated = Signal(object)          # dict: tokens, cost, contextUsage

    messages_received = Signal(object)       # list: messages from get_messages
    session_switched = Signal(str)           # session path after switch

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
        self._worker.tool_call.connect(self.tool_call)
        self._worker.agent_started.connect(self.agent_started)
        self._worker.agent_finished.connect(self.agent_finished)
        self._worker.error_occurred.connect(self.error_occurred)
        self._worker.status_changed.connect(self.status_changed)
        self._worker.stats_received.connect(self.stats_updated)
        self._worker.messages_received.connect(self.messages_received)
        self._worker.session_switched.connect(self.session_switched)

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

    def restart(self) -> None:
        """Restart the Pi subprocess (needed after API key change)."""
        was_running = self._is_running
        self.stop()
        if was_running:
            self.start()


class _RpcWorker(QObject):
    """Worker object running on a QThread. Manages subprocess I/O."""

    text_delta = Signal(str)
    tool_call = Signal(str, str, object)
    agent_started = Signal()
    agent_finished = Signal()
    error_occurred = Signal(str)
    status_changed = Signal(str)
    stats_received = Signal(object)
    messages_received = Signal(object)
    session_switched = Signal(str)

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
            self._process = subprocess.Popen(
                self._pi_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                cwd=self._cwd,
                env=get_pi_env(),
            )
            self.status_changed.emit("connected")

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
                self._process.wait(timeout=3)
            except Exception:
                self._process.kill()

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
            if delta.get("type") == "text_delta":
                self.text_delta.emit(delta.get("delta", ""))

        elif event_type == "tool_execution_start":
            self.tool_call.emit(
                event.get("toolName", ""),
                event.get("toolCallId", ""),
                event.get("args", {}),
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
                    # Request state to get the new session path
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

        elif event_type == "extension_error":
            self.error_occurred.emit(f"Extension: {event.get('error', '')}")

        elif event_type == "extension_ui_request":
            if event.get("method") == "notify":
                self.error_occurred.emit(
                    f"[{event.get('notifyType', 'info')}] {event.get('message', '')}"
                )
