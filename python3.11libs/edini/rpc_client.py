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
    notification_received = Signal(str, str) # (notify_type, message) for info/warning
    session_switched = Signal(str)          # new session path after switch
    messages_received = Signal(object)      # list of messages from pi session

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._process: subprocess.Popen | None = None
        self._thread: QThread | None = None
        self._worker: _RpcWorker | None = None
        self._is_running = False
        self._cwd: str | None = None

    @property
    def is_running(self) -> bool:
        return self._is_running

    def start(self) -> None:
        """Launch the Pi subprocess and start reading its output."""
        if self._is_running:
            return

        self._thread = QThread()
        self._worker = _RpcWorker(get_pi_command(), TOOL_EXECUTOR_PORT)
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
        self._worker.notification_received.connect(self.notification_received)
        self._worker.session_switched.connect(self.session_switched)
        self._worker.messages_received.connect(self.messages_received)

        if self._cwd:
            self._worker.set_cwd(self._cwd)

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

    def set_cwd(self, cwd: str) -> None:
        """Set the working directory for the Pi subprocess."""
        self._cwd = cwd

    def send_new_session(self) -> None:
        """Tell Pi to start a new session."""
        if self._worker:
            self._worker.send_command({"type": "new_session"})

    def send_switch_session(self, session_path: str) -> None:
        """Tell Pi to switch to an existing session."""
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
    notification_received = Signal(str, str)
    session_switched = Signal(str)
    messages_received = Signal(object)

    def __init__(self, pi_cmd: list[str], tool_port: int):
        super().__init__()
        self._pi_cmd = pi_cmd
        self._tool_port = tool_port
        self._process: subprocess.Popen | None = None
        self._should_stop = False
        self._cwd: str | None = None

    def set_cwd(self, cwd: str) -> None:
        """Set working directory for the subprocess."""
        self._cwd = cwd

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
                # Also hide via startupinfo
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
                popen_kwargs["startupinfo"] = startupinfo

            self._process = subprocess.Popen(self._pi_cmd, **popen_kwargs)
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
                self._process.stdin.write(json.dumps(cmd, ensure_ascii=False) + "\n")
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
                json.dumps(event.get("result", {}), ensure_ascii=False),
            )

        elif event_type == "agent_start":
            self.agent_started.emit()

        elif event_type == "agent_end":
            self.agent_finished.emit()

        elif event_type == "response":
            if not event.get("success", True):
                self.error_occurred.emit(event.get("error", "Unknown error"))
            command = event.get("command", "")
            if command == "get_session_stats":
                self.stats_received.emit(event.get("data", {}))
            elif command in ("new_session", "switch_session"):
                data = event.get("data", {})
                session_path = data.get("sessionPath", "") if isinstance(data, dict) else ""
                self.session_switched.emit(session_path)
            elif command == "get_messages":
                self.messages_received.emit(event.get("data", []))

        elif event_type == "extension_error":
            self.error_occurred.emit(f"Extension: {event.get('error', '')}")

        elif event_type == "extension_ui_request":
            if event.get("method") == "notify":
                notify_type = event.get("notifyType", "info")
                message = event.get("message", "")
                if notify_type == "error":
                    self.error_occurred.emit(f"[{notify_type}] {message}")
                else:
                    self.notification_received.emit(notify_type, message)
