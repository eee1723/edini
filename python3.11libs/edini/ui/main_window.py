"""Edini main window — 3-panel layout with QSplitter.

Pi manages all sessions via RPC. Edini is a thin UI wrapper.
"""
import importlib
import os

from PySide6 import QtCore, QtWidgets

from edini.rpc_client import RpcClient
from edini.tool_executor import ToolExecutor
from edini.ui.chat_runtime import ChatRuntime
from edini.ui.theme import apply_theme, accent_color
from edini.ui.agent_panel import AgentPanel
from edini.ui.history_panel import HistoryPanel
from edini.ui.context_panel import ContextPanel
from edini.ui.pi_sessions import load_pi_messages
from edini.config import get_settings

try:
    hou = importlib.import_module("hou")
except Exception:
    hou = None


def _get_working_dir() -> str:
    """Get the working directory for pi: HIP path in Houdini, CWD otherwise."""
    if hou:
        try:
            hip = hou.hipFile.path()
            if hip:
                # Use HIP dir so pi sessions are scoped to the project
                return os.path.dirname(hip) or hip
        except Exception:
            pass
    return os.getcwd()


class EdiniMainWindow(QtWidgets.QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edini Agent")
        self.resize(1520, 1000)

        self._tool_executor = ToolExecutor()
        self._rpc_client = RpcClient()
        self._chat_runtime = ChatRuntime(self._rpc_client, self)
        self._current_session_path = ""
        self._active_session_path = ""
        self._browsing_session_path = ""

        self._build_ui()
        self._bind_events()
        self._bootstrap()

    def _build_ui(self):
        from edini.ui.theme import init_theme_from_config
        init_theme_from_config()
        apply_theme(self)

        central = QtWidgets.QWidget(self)
        root = QtWidgets.QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        self.main_splitter = QtWidgets.QSplitter(central)
        self.main_splitter.setOrientation(QtCore.Qt.Horizontal)

        # Left: History panel
        self.history_panel = HistoryPanel(self.main_splitter)
        self.history_panel.setMinimumWidth(200)
        self.history_panel.setMaximumWidth(260)

        # Center: Agent panel
        self.agent_panel = AgentPanel(self.main_splitter)
        self.agent_panel.setMinimumWidth(500)

        # Right: Context panel
        self.context_panel = ContextPanel(self.main_splitter)
        self.context_panel.setMinimumWidth(340)
        self.context_panel.setMaximumWidth(400)

        self.main_splitter.setCollapsible(0, False)
        self.main_splitter.setCollapsible(1, False)
        self.main_splitter.setCollapsible(2, False)
        self.main_splitter.setSizes([240, 720, 400])
        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setStretchFactor(2, 0)

        root.addWidget(self.main_splitter, 1)

        self.setCentralWidget(central)

        self.status = QtWidgets.QStatusBar(self)
        self.setStatusBar(self.status)
        self.status.showMessage("Ready")

    def _bind_events(self):
        # Chat runtime signals
        self._chat_runtime.started.connect(self._on_agent_started)
        self._chat_runtime.stream_chunk.connect(self.agent_panel.append_stream_chunk)
        self._chat_runtime.thinking_chunk.connect(self._on_thinking)
        self._chat_runtime.tool_started.connect(self._on_tool_call)
        self._chat_runtime.tool_completed.connect(self._on_tool_result)
        self._chat_runtime.completed.connect(self._on_agent_done)
        self._chat_runtime.failed.connect(self._on_error)
        self._chat_runtime.busy_changed.connect(self._on_busy_changed)
        self._chat_runtime.stats_updated.connect(self.context_panel.set_usage)

        # Agent panel signals
        self.agent_panel.submit_requested.connect(self._on_agent_submit)
        self.agent_panel.abort_requested.connect(self._on_abort_request)

        # History panel signals
        self.history_panel.new_session_requested.connect(self._on_new_session)
        self.history_panel.session_selected.connect(self._on_session_selected)
        self.history_panel.session_deleted.connect(self._on_session_deleted)
        self.history_panel.back_to_current_requested.connect(self._on_back_to_current)

        # Pi status
        self._rpc_client.status_changed.connect(self._on_status_changed)

        # Pi session management responses
        self._rpc_client.session_switched.connect(self._on_pi_session_switched)
        self._rpc_client.messages_received.connect(self._on_pi_messages_received)

        # Scene refresh timer
        self._scene_timer = QtCore.QTimer(self)
        self._scene_timer.setInterval(3000)
        self._scene_timer.timeout.connect(self.context_panel.refresh_scene_info)
        self._scene_timer.start()

        # Stats polling timer (during agent execution)
        self._stats_poll_timer = QtCore.QTimer(self)
        self._stats_poll_timer.setInterval(3000)
        self._stats_poll_timer.timeout.connect(self._rpc_client.send_get_stats)

    def _bootstrap(self):
        cwd = _get_working_dir()
        self._rpc_client.set_cwd(cwd)
        self.history_panel.set_cwd(cwd)

        self._tool_executor.start()
        self._rpc_client.start()
        self.history_panel.load_sessions()
        self.context_panel.refresh_scene_info()
        settings = get_settings()
        self.context_panel.set_provider_model(
            settings.get("provider", "deepseek"),
            settings.get("model_id", "deepseek-chat"),
        )
        from edini.ui.hotkey import install_event_filter
        install_event_filter()

    # ── Signal handlers ──

    def _on_agent_submit(self, text: str, images=None):
        self.agent_panel.begin_assistant_message()
        self._rpc_client.send_prompt(text, images=images)

    def _on_agent_started(self, _):
        self.agent_panel.set_busy(True)
        self._stats_poll_timer.start()
        self.status.showMessage("Processing...")

    def _on_agent_done(self, _):
        self.agent_panel.finish_streaming()
        self.agent_panel.set_busy(False)
        self._stats_poll_timer.stop()
        self.context_panel.refresh_scene_info()
        self._rpc_client.send_get_stats()
        self._update_statusbar()
        self.status.showMessage("Ready")
        # Refresh session list (message count updated)
        self.history_panel.load_sessions()

    def _on_tool_call(self, tool_name: str, tool_call_id: str, args: dict):
        self.agent_panel.add_tool_card(tool_name, args, tool_call_id)

    def _on_tool_result(self, tool_name: str, tool_call_id: str, result: str):
        self.agent_panel.set_tool_result(tool_call_id, result)

    def _on_thinking(self, text: str):
        self.agent_panel.add_thinking_step(
            self.agent_panel._thinking_count + 1, text)

    def _on_abort_request(self):
        self._rpc_client.send_abort()
        self.agent_panel.show_aborted()

    def _on_error(self, msg: str):
        self._stats_poll_timer.stop()
        self.agent_panel.add_error(msg)
        self.agent_panel.set_busy(False)
        self.status.showMessage(f"Error: {msg}")

    def _on_busy_changed(self, busy: bool):
        pass

    def _on_status_changed(self, status: str):
        self._last_pi_status = status
        self.context_panel.set_pi_status(status)
        self._update_statusbar()
        # On first connect, set session name and request stats
        if status == "connected":
            if hou:
                try:
                    hip = hou.hipFile.name()
                    if hip:
                        name = os.path.splitext(os.path.basename(hip))[0]
                        self._rpc_client.send_set_session_name(name)
                except Exception:
                    pass
            self._rpc_client.send_get_stats()

    def _on_pi_session_switched(self, session_path: str):
        """Called when pi confirms a session switch (new or resumed)."""
        self._current_session_path = session_path
        self._rpc_client.send_get_stats()
        # Update list highlight to match active session
        highlight = self._browsing_session_path or session_path
        self.history_panel.highlight_session(highlight)

    def _on_pi_messages_received(self, messages: list):
        """Render messages from pi in the agent panel."""
        # This is a fallback; normally we load from local file synchronously
        self.agent_panel.clear_timeline()
        for m in messages:
            role = m.get("role", "")
            content = m.get("content", "")
            if role == "user":
                self.agent_panel._append_user_message(content)
            elif role == "assistant":
                self.agent_panel._render_stored_assistant_message(m)

    def _on_new_session(self):
        # Save current session as active before creating new one (only if not already browsing)
        if not self._browsing_session_path:
            self._active_session_path = self._current_session_path
        self._browsing_session_path = ""
        self.history_panel.set_browsing_mode(False)

        self._current_session_path = ""
        self.agent_panel.clear_timeline()
        self.context_panel.reset_stats()
        self._rpc_client.send_new_session()
        # Schedule a reload after pi creates the session
        QtCore.QTimer.singleShot(500, self.history_panel.load_sessions)

    def _on_session_selected(self, session_path: str):
        if session_path == self._current_session_path and not self._browsing_session_path:
            return  # Already viewing this session in normal mode, no-op

        # Enter browsing mode if not already in it
        if not self._browsing_session_path:
            self._active_session_path = self._current_session_path
        self._browsing_session_path = session_path
        self.history_panel.set_browsing_mode(True)
        self.history_panel.highlight_session(session_path)

        self._current_session_path = session_path
        self.agent_panel.clear_timeline()
        self.context_panel.reset_stats()

        # Load messages directly from local JSONL for instant rendering
        messages = load_pi_messages(session_path)
        for m in messages:
            role = m.get("role", "")
            content = m.get("content", "")
            if role == "user":
                self.agent_panel._append_user_message(content)
            elif role == "assistant":
                self.agent_panel._render_stored_assistant_message(m)

        # Tell pi to switch session (async, updates stats)
        self._rpc_client.send_switch_session(session_path)

    def _on_back_to_current(self):
        """Exit browsing mode and restore the previously active session."""
        target = self._active_session_path
        self._browsing_session_path = ""
        self.history_panel.set_browsing_mode(False)

        if target:
            self._current_session_path = target
            self.agent_panel.clear_timeline()
            self.context_panel.reset_stats()

            messages = load_pi_messages(target)
            for m in messages:
                role = m.get("role", "")
                content = m.get("content", "")
                if role == "user":
                    self.agent_panel._append_user_message(content)
                elif role == "assistant":
                    self.agent_panel._render_stored_assistant_message(m)

            self._rpc_client.send_switch_session(target)
            self.history_panel.highlight_session(target)
        else:
            self._current_session_path = ""
            self.agent_panel.clear_timeline()

    def _on_session_deleted(self, session_path: str):
        self.history_panel.remove_session(session_path)

        # If deleted session was the one being browsed, fall back to active
        if session_path == self._browsing_session_path:
            self._browsing_session_path = ""
            self.history_panel.set_browsing_mode(False)
            if self._active_session_path and self._active_session_path != session_path:
                self._on_session_selected(self._active_session_path)
                self.history_panel.set_browsing_mode(False)
            else:
                self._current_session_path = ""
                self.agent_panel.clear_timeline()
            return

        # If deleted session was the active one, clear it
        if session_path == self._active_session_path:
            self._active_session_path = ""

        if session_path == self._current_session_path:
            self._current_session_path = ""
            self.agent_panel.clear_timeline()

    def refresh_theme(self):
        """Called externally after settings change to reapply theme."""
        from edini.ui.theme import init_theme_from_config, refresh_window_theme
        init_theme_from_config()
        refresh_window_theme(self)

    def _update_statusbar(self):
        parts = []
        status = getattr(self, '_last_pi_status', 'connecting')
        icons = {"connected": "●", "connecting": "◌", "disconnected": "○"}
        parts.append(f"{icons.get(status, '●')} {status}")
        settings = get_settings()
        parts.append(f"{settings.get('provider','?')}/{settings.get('model_id','?')}")
        if hou:
            try:
                root = hou.node("/")
                count = len(root.allSubChildren()) if root else 0
                parts.append(f"Nodes:{count}")
            except Exception:
                pass
        self.status.showMessage("  │  ".join(parts))

    def closeEvent(self, event):
        from edini.ui.windows import _main_window as global_main
        self._rpc_client.stop()
        self._tool_executor.stop()
        super().closeEvent(event)
        # Release the global singleton so reopen creates a fresh window
        if global_main is self:
            import edini.ui.windows as win_mod
            win_mod._main_window = None
