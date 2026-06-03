"""Edini main window — 3-panel layout with QSplitter."""
import uuid
import importlib
from PySide6 import QtCore, QtWidgets

from edini.rpc_client import RpcClient
from edini.tool_executor import ToolExecutor
from edini.ui.chat_runtime import ChatRuntime
from edini.ui.theme import apply_main_theme
from edini.ui.agent_panel import AgentPanel
from edini.ui.history_panel import HistoryPanel
from edini.ui.context_panel import ContextPanel
from edini.config import get_settings

try:
    hou = importlib.import_module("hou")
except Exception:
    hou = None


class EdiniMainWindow(QtWidgets.QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edini Agent")
        self.resize(1360, 860)

        self._tool_executor = ToolExecutor()
        self._rpc_client = RpcClient()
        self._chat_runtime = ChatRuntime(self._rpc_client, self)
        self._current_session_id = ""

        self._build_ui()
        self._bind_events()
        self._bootstrap()

    def _build_ui(self):
        apply_main_theme(self)

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
        self._chat_runtime.tool_started.connect(self._on_tool_call)
        self._chat_runtime.completed.connect(self._on_agent_done)
        self._chat_runtime.failed.connect(self._on_error)
        self._chat_runtime.busy_changed.connect(self._on_busy_changed)
        self._chat_runtime.stats_updated.connect(self.context_panel.set_usage)

        # Agent panel signals
        self.agent_panel.submit_requested.connect(self._on_agent_submit)

        # History panel signals
        self.history_panel.new_session_requested.connect(self._on_new_session)
        self.history_panel.session_selected.connect(self._on_session_selected)
        self.history_panel.session_deleted.connect(self._on_session_deleted)

        # Pi status
        self._rpc_client.status_changed.connect(self._on_status_changed)

        # Scene refresh timer
        self._scene_timer = QtCore.QTimer(self)
        self._scene_timer.setInterval(3000)
        self._scene_timer.timeout.connect(self.context_panel.refresh_scene_info)
        self._scene_timer.start()

    def _bootstrap(self):
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

    def _on_agent_submit(self, text: str):
        self.agent_panel.begin_assistant_message()
        self._rpc_client.send_prompt(text)

    def _on_agent_started(self, _):
        self.agent_panel.set_busy(True)
        self.status.showMessage("Processing...")

    def _on_agent_done(self, _):
        self.agent_panel.finish_streaming()
        self.agent_panel.set_busy(False)
        self.context_panel.refresh_scene_info()
        self._rpc_client.send_get_stats()
        self.status.showMessage("Ready")

    def _on_tool_call(self, tool_name: str, tool_call_id: str, args: dict):
        self.agent_panel.add_tool_card(tool_name, args)

    def _on_error(self, msg: str):
        self.agent_panel.add_error(msg)
        self.agent_panel.set_busy(False)
        self.status.showMessage(f"Error: {msg}")

    def _on_busy_changed(self, busy: bool):
        pass

    def _on_status_changed(self, status: str):
        self.context_panel.set_pi_status(status)
        self.status.showMessage(f"Pi: {status}")

    def _on_new_session(self):
        from edini.ui.session_store import create_session
        sid = "sess-" + uuid.uuid4().hex[:8]
        create_session(sid, "New Session")
        self._current_session_id = sid
        self.agent_panel.clear_timeline()
        self.history_panel.load_sessions()
        self.agent_panel.set_session_id(sid)

    def _on_session_selected(self, sid: str):
        from edini.ui.session_store import load_messages
        self._current_session_id = sid
        self.agent_panel.clear_timeline()
        msgs = load_messages(sid)
        for m in msgs:
            role = m.get("role", "")
            content = m.get("content", "")
            if role == "user":
                self.agent_panel._append_user_message(content)
            elif role == "assistant":
                self.agent_panel._append_assistant_message(content)
        self.agent_panel.set_session_id(sid)

    def _on_session_deleted(self, sid: str):
        self.history_panel.remove_session(sid)
        if sid == self._current_session_id:
            self._current_session_id = ""
            self.agent_panel.clear_timeline()

    def closeEvent(self, event):
        self._rpc_client.stop()
        self._tool_executor.stop()
        super().closeEvent(event)
