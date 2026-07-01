"""ProjectPanelWidget — the embedded widget for a Project HDA.

Three-column layout (Plan | Chat | State) per spec §6.2. Minimal-loop
version: project selector + placeholder columns. Reuses edini.ui.theme.
"""
from __future__ import annotations

from PySide2 import QtCore, QtWidgets
# NOTE: Houdini 21 ships PySide2. If your Houdini uses PySide6, swap the import;
# the Qt API used here is identical between PySide2 and PySide6.

from edini.ui.theme import apply_theme, accent_color, fs


class ProjectPanelWidget(QtWidgets.QWidget):
    """The root widget shown inside the Houdini Python Pane tab."""

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self._bound_node_path: str | None = None
        self._stream_wired = False
        self._current_ai = None
        self._build_ui()

    # --- UI construction -------------------------------------------------

    def _build_ui(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        # Top bar: project selector + status.
        top = QtWidgets.QHBoxLayout()
        top.addWidget(QtWidgets.QLabel("Project:"))
        self.project_combo = QtWidgets.QComboBox()
        self.project_combo.currentIndexChanged.connect(self._on_project_changed)
        top.addWidget(self.project_combo, 1)
        self.status_label = QtWidgets.QLabel("disconnected")
        top.addWidget(self.status_label)
        root.addLayout(top)

        # Three columns.
        cols = QtWidgets.QHBoxLayout()
        self.plan_column = self._placeholder("Plan Tree\n(plan)")
        # Chat column: reuse the existing timeline + bubbles from edini.ui.
        from edini.ui.agent_panel import _TimelineView
        self.chat_column = QtWidgets.QFrame()
        cl = QtWidgets.QVBoxLayout(self.chat_column)
        cl.setContentsMargins(0, 0, 0, 0)
        self.timeline = _TimelineView()
        cl.addWidget(self.timeline, 1)
        self.input_edit = QtWidgets.QPlainTextEdit()
        self.input_edit.setFixedHeight(56)
        self.input_edit.installEventFilter(self)  # Enter to send (handled in eventFilter)
        cl.addWidget(self.input_edit)
        self.state_column = self._placeholder("State + Graph\n(statistics)")
        cols.addWidget(self.plan_column, 1)
        cols.addWidget(self.chat_column, 2)
        cols.addWidget(self.state_column, 1)
        root.addLayout(cols, 1)

        apply_theme(self)

    def _placeholder(self, text: str) -> QtWidgets.QFrame:
        f = QtWidgets.QFrame()
        f.setFrameShape(QtWidgets.QFrame.StyledPanel)
        lay = QtWidgets.QVBoxLayout(f)
        lbl = QtWidgets.QLabel(text)
        lbl.setAlignment(QtCore.Qt.AlignCenter)
        lay.addWidget(lbl)
        return f

    # --- Project binding -------------------------------------------------

    def refresh_project_list(self) -> None:
        """Populate the dropdown with all edini::project nodes in the scene."""
        import hou
        self.project_combo.blockSignals(True)
        self.project_combo.clear()
        nodes = hou.nodeTypeCategories()["Object"].nodeType("edini::project").instances()
        for n in nodes:
            self.project_combo.addItem(n.path(), userData=n.path())
        self.project_combo.blockSignals(False)
        if self.project_combo.count():
            self._bind(self.project_combo.itemData(0))

    def _on_project_changed(self, _idx: int) -> None:
        path = self.project_combo.currentData()
        if path:
            self._bind(path)

    def _bind(self, node_path: str) -> None:
        self._bound_node_path = node_path
        self.status_label.setText(f"bound: {node_path}")

    # --- Chat: send + stream back via shared singleton RpcClient ---------

    def eventFilter(self, obj, event):
        from PySide2 import QtCore
        if obj is self.input_edit and event.type() == QtCore.QEvent.KeyPress:
            if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter) \
               and not (event.modifiers() & (QtCore.Qt.ShiftModifier | QtCore.Qt.ControlModifier)):
                self._send()
                return True  # swallow the key
        return super().eventFilter(obj, event)

    def _get_rpc(self):
        """Return the singleton RpcClient from the main chat window.

        Reuses the already-running Pi subprocess + HTTP server. Never spawns
        a new one (would collide on port 9876). Opens the main window if it
        isn't already (which bootstraps the agent).
        """
        from edini.ui.windows import open_chat_window
        return open_chat_window()._rpc_client

    def _send(self) -> None:
        text = self.input_edit.toPlainText().strip()
        if not text or self._bound_node_path is None:
            return
        self.input_edit.clear()
        # Show the user's message immediately.
        from edini.ui.agent_panel import _UserBubble
        self.timeline.add_widget(_UserBubble(text))
        # Drive the LLM via the shared RpcClient; each project gets its own
        # Pi session, named after the bound node path.
        rpc = self._get_rpc()
        rpc.send_set_session_name(self._bound_node_path)
        # Connect streaming once: route text deltas into a fresh AI bubble.
        if not self._stream_wired:
            rpc.text_delta.connect(self._on_stream_delta)
            rpc.agent_finished.connect(self._on_turn_done)
            self._stream_wired = True
        rpc.send_prompt(text)

    def _on_stream_delta(self, chunk: str) -> None:
        # Mirrors edini.ui.agent_panel.AgentPanel.append_stream_chunk:
        # accumulate full text, call update_streaming(full_text). The AiBubble
        # itself has no .text(); read back via get_raw_text().
        from edini.ui.agent_panel import _AiBubble
        if self._current_ai is None:
            self._current_ai = _AiBubble()
            self.timeline.add_widget(self._current_ai)
        full = self._current_ai.get_raw_text() + chunk
        self._current_ai.update_streaming(full)

    def _on_turn_done(self) -> None:
        if self._current_ai is not None:
            self._current_ai.finalize()
            self._current_ai = None

    @property
    def bound_node_path(self) -> str | None:
        return self._bound_node_path
