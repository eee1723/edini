"""ProjectChatDialog — a lightweight chat popup launched from a Project HDA's
parameter button (problem C: the HDA's param panel gets a "💬 Chat" button that
opens this dialog, replacing the standalone Python Pane workflow).

Reuses the existing chat core (RpcClient + _StreamBubble lightweight streaming
+ IME popout input) but is a slim standalone QDialog — no three-column layout,
no knowledge zone, no toolbar. Parented to hou.qt.mainWindow() so it's a real
top-level OS window (IME works).

One dialog instance per HDA core; the dialog knows its core_path (used as the
Pi session name, so each project has isolated conversation history).
"""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from edini.project.panel.project_widget import _StreamBubble, _InputDialog
from edini.ui.theme import apply_theme, fs


class ProjectChatDialog(QtWidgets.QDialog):
    """Slim chat dialog bound to a Project HDA core node.

    Launched from the HDA's "edini_chat" button (PythonModule open_chat).
    Owns its RpcClient (independent Pi subprocess, per spec decision #11) +
    session named after the core node path.
    """

    def __init__(self, core_path: str, parent=None):
        super().__init__(parent)
        self._core_path = core_path
        self._rpc = None
        self._rpc_ready = False
        self._pending_prompt: str | None = None
        self._current_ai = None
        self._input_dialog = None
        self.setWindowTitle(f"Edini — {core_path}")
        self.resize(560, 640)
        self._build_ui()

    def _build_ui(self) -> None:
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        # Header: bound project + status.
        header = QtWidgets.QHBoxLayout()
        lbl = QtWidgets.QLabel(f"💬 {self._core_path}")
        lbl.setStyleSheet(f"color:#e5e5eb;font-size:{fs(12)};")
        header.addWidget(lbl)
        header.addStretch(1)
        self.status_label = QtWidgets.QLabel("disconnected")
        self.status_label.setStyleSheet(f"color:#8b8fa8;font-size:{fs(10)};")
        header.addWidget(self.status_label)
        lay.addLayout(header)

        # Timeline (reuse the lightweight streaming bubble).
        from edini.ui.agent_panel import _TimelineView, _UserBubble
        self._TimelineView = _TimelineView
        self._UserBubble = _UserBubble
        self.timeline = _TimelineView()
        lay.addWidget(self.timeline, 1)

        # Inline input (English/quick) + IME button.
        input_row = QtWidgets.QHBoxLayout()
        self.input_edit = QtWidgets.QPlainTextEdit()
        self.input_edit.setFixedHeight(56)
        self.input_edit.setPlaceholderText("输入消息 (Enter 发送)…")
        self.input_edit.installEventFilter(self)
        input_row.addWidget(self.input_edit, 1)
        self.input_btn = QtWidgets.QPushButton("💬\n输入")
        self.input_btn.setFixedHeight(56)
        self.input_btn.setMaximumWidth(56)
        self.input_btn.setToolTip("打开输入窗口(支持中文输入法)")
        self.input_btn.clicked.connect(self._open_input_dialog)
        input_row.addWidget(self.input_btn)
        lay.addLayout(input_row)

        apply_theme(self)

    # --- Event filter: Enter to send (inline input) -----------------------

    def eventFilter(self, obj, event):
        if obj is self.input_edit and event.type() == QtCore.QEvent.KeyPress:
            if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter) \
               and not (event.modifiers() & (QtCore.Qt.ShiftModifier | QtCore.Qt.ControlModifier)):
                self._send_inline()
                return True
        return super().eventFilter(obj, event)

    def _send_inline(self) -> None:
        text = self.input_edit.toPlainText().strip()
        if not text:
            return
        self.input_edit.clear()
        self._send_text(text)

    def _open_input_dialog(self) -> None:
        if self._input_dialog is None:
            import hou
            self._input_dialog = _InputDialog(hou.qt.mainWindow())
            self._input_dialog.submitted.connect(self._send_text)
        self._input_dialog.open_for_input()

    # --- Send + stream (mirrors ProjectPanelWidget's chat core) -----------

    def _send_text(self, text: str) -> None:
        if not text:
            return
        self.timeline.add_widget(self._UserBubble(text))
        rpc = self._get_rpc()
        if self._rpc_ready:
            rpc.send_prompt(text)
        else:
            self._pending_prompt = text

    def _get_rpc(self):
        if self._rpc is not None:
            return self._rpc
        from edini.tool_executor import get_tool_executor
        get_tool_executor()
        from edini.rpc_client import RpcClient
        self._rpc = RpcClient(parent=self)
        self._rpc.text_delta.connect(self._on_stream_delta)
        self._rpc.agent_finished.connect(self._on_turn_done)
        self._rpc.status_changed.connect(self._on_rpc_status)
        self._rpc.start()
        return self._rpc

    def _on_rpc_status(self, status: str) -> None:
        self.status_label.setText(status)
        if status != "connected" or self._rpc_ready or self._rpc is None:
            return
        self._rpc_ready = True
        if self._core_path:
            self._rpc.send_set_session_name(self._core_path)
        try:
            from edini.config import read_pi_settings
            pi_sett = read_pi_settings()
            provider = pi_sett.get("defaultProvider", "")
            model_id = pi_sett.get("defaultModel", "")
            if provider and model_id:
                self._rpc.send_set_model(provider, model_id)
        except Exception:
            pass
        if self._pending_prompt is not None:
            text, self._pending_prompt = self._pending_prompt, None
            self._rpc.send_prompt(text)

    def _on_stream_delta(self, chunk: str) -> None:
        if self._current_ai is None and chunk.strip():
            self._current_ai = _StreamBubble()
            self.timeline.add_widget(self._current_ai)
        if self._current_ai is not None:
            self._current_ai.append_chunk(chunk)

    def _on_turn_done(self) -> None:
        if self._current_ai is not None:
            self._current_ai.finalize()
            self._current_ai = None

    def closeEvent(self, event):
        if self._rpc is not None:
            try:
                self._rpc.stop()
            except Exception:
                pass
        super().closeEvent(event)


# --- Active-dialog registry (so the PythonModule callback can find/reuse) ---
# Keeps one dialog per core_path; re-opening the button focuses the existing one.
_active_dialogs: dict[str, ProjectChatDialog] = {}


def open_chat_for_core(core_path: str) -> None:
    """Launch (or focus) the chat dialog for a Project HDA core node.

    Called by the HDA's PythonModule open_chat() (button callback). Parented to
    hou.qt.mainWindow() so it's a real top-level window (IME works).
    """
    import hou
    dlg = _active_dialogs.get(core_path)
    if dlg is None:
        dlg = ProjectChatDialog(core_path, parent=hou.qt.mainWindow())
        _active_dialogs[core_path] = dlg
    dlg.show()
    dlg.raise_()
    dlg.activateWindow()
