"""ProjectPanelWidget — the embedded widget for a Project HDA.

Three-column layout (Plan | Chat | State) per spec §6.2. Minimal-loop
version: project selector + placeholder columns. Reuses edini.ui.theme.
"""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets
# NOTE: Houdini 21 ships PySide6 (matches the rest of edini.ui). The Qt API used
# here is identical to PySide2's.

from edini.ui.theme import apply_theme, accent_color, fs


class _StreamBubble(QtWidgets.QFrame):
    """Lightweight AI reply bubble for the Project panel.

    Why this exists instead of reusing edini.ui._AiBubble: _AiBubble.update_streaming
    runs a FULL mistune markdown parse + Qt rich-text word-wrap relayout over the
    ENTIRE accumulated text on every chunk (O(n^2) over the stream), which freezes
    the panel's input box during long replies (Houdini's Python Panel shares one
    main thread with everything).

    This bubble renders stream chunks as PLAIN TEXT (QLabel.setText on plain text
    skips HTML parsing and the expensive word-wrap relayout chain) — microsecond
    cost per chunk. Only on finalize() does it run ONE mistune pass for the final
    markdown rendering. Visual result is identical to _AiBubble after finalize
    (same _ai_bubble_style); during streaming it's plain text in the same frame.

    Spec §6.2 said "reuse mistune rendering" — this defers markdown to finalize,
    final display still uses mistune. Annotated as a performance trade-off.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        # Match _AiBubble's frame look (bg + rounded) via stylesheet, so the
        # bubble is visually distinct even during plain-text streaming.
        from edini.ui.agent_panel import _ai_bubble_bg
        self.setStyleSheet(
            f"background:{_ai_bubble_bg()};border-radius:8px;"
        )
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(14, 8, 14, 8)
        self._label = QtWidgets.QLabel()
        self._label.setWordWrap(True)
        self._label.setTextFormat(QtCore.Qt.PlainText)  # CRITICAL: no HTML parse
        self._label.setStyleSheet(
            f"color:#e5e5eb;font-size:{fs(12)};line-height:1.45;background:transparent;"
        )
        lay.addWidget(self._label)
        self._raw_text = ""

    def append_chunk(self, chunk: str) -> None:
        """Accumulate a stream chunk and show plain text. Cheap (no markdown)."""
        self._raw_text += chunk
        self._label.setText(self._raw_text)

    def get_raw_text(self) -> str:
        return self._raw_text

    def finalize(self) -> None:
        """One-time full markdown render at stream end. Switches to rich text."""
        from edini.ui.agent_panel import _format_full, _ai_bubble_style
        try:
            rendered = _format_full(self._raw_text)
        except Exception:
            # Fallback: show the plain text as-is (escaped) if mistune fails.
            import html
            rendered = html.escape(self._raw_text).replace("\n", "<br>")
        self._label.setTextFormat(QtCore.Qt.RichText)
        self._label.setText(f'<div style="{_ai_bubble_style()}">{rendered}</div>')


class _InputEdit(QtWidgets.QPlainTextEdit):
    """Input box that survives IME (input method) candidate-window focus theft.

    Symptom being fixed: when typing Chinese (or any IME language) inside a
    Houdini Python Panel, the IME candidate window pops up as a separate
    top-level window and STEALS focus from the embedded QPlainTextEdit. The
    Python Panel container doesn't restore focus afterward, so the user can't
    keep typing. This doesn't happen in the standalone EdiniMainWindow (a real
    top-level QMainWindow manages its own focus chain).

    Fix: if focus is lost WHILE the input method is composing (a preedit string
    is active), immediately reclaim focus. This lets the IME candidate window
    do its job without orphaning the input box. We also force StrongFocus +
    WA_InputMethodEnabled so Qt treats this widget as an IME target from the
    start.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.setAttribute(QtCore.Qt.WA_InputMethodEnabled, True)
        # Track whether an IME preedit is in progress so focusOutEvent knows
        # whether the loss is IME-induced.
        self._ime_composing = False

    def inputMethodEvent(self, event):
        # A non-empty preedit string means the IME is mid-composition (candidate
        # window up). Empty preedit + commit string means composition finished.
        if event.preeditString():
            self._ime_composing = True
        else:
            self._ime_composing = False
        super().inputMethodEvent(event)

    def focusOutEvent(self, event):
        # If focus is lost while the IME is composing, the candidate window
        # stole it. Reclaim focus so the user can continue typing. We defer
        # via QTimer.singleShot(0) to avoid fighting Qt's internal focus
        # negotiation during the same event delivery.
        if self._ime_composing:
            QtCore.QTimer.singleShot(0, self.setFocus)
            return
        super().focusOutEvent(event)


class ProjectPanelWidget(QtWidgets.QWidget):
    """The root widget shown inside the Houdini Python Pane tab."""

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self._bound_node_path: str | None = None
        self._stream_wired = False
        self._current_ai = None
        # Per-panel RpcClient (own Pi subprocess), created lazily on first send.
        # See _get_rpc — independent of EdiniMainWindow, per spec decision #11.
        self._rpc = None
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
        self.input_edit = _InputEdit()
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
        from PySide6 import QtCore
        if obj is self.input_edit and event.type() == QtCore.QEvent.KeyPress:
            # Don't intercept Enter while the IME is composing — that Enter
            # confirms a candidate character, it must NOT send the message.
            if getattr(self.input_edit, "_ime_composing", False):
                return super().eventFilter(obj, event)
            if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter) \
               and not (event.modifiers() & (QtCore.Qt.ShiftModifier | QtCore.Qt.ControlModifier)):
                self._send()
                return True  # swallow the key
        return super().eventFilter(obj, event)

    def _get_rpc(self):
        """Return a per-panel RpcClient owning its own Pi subprocess.

        Per spec decision #11 ("each HDA = independent panel + independent Pi
        session"), the Project panel runs its OWN Pi process — it does NOT
        reuse the main window's RpcClient and does NOT open the main window.

        The Pi subprocess finds the Houdini tool executor (HTTP:9876) via the
        EDINI_TOOL_PORT env var (see config.get_pi_env), so it shares the
        global, stateless ToolExecutor singleton (get_tool_executor) without
        conflict. Multiple panels → multiple Pi processes, all POSTing to one
        HTTP server.

        Each project gets its own Pi session: new_session + set_session_name
        (named after the bound node path) so conversation histories are
        isolated per project.
        """
        if self._rpc is not None:
            return self._rpc
        # Ensure the shared tool-executor HTTP server is up (idempotent).
        from edini.tool_executor import get_tool_executor
        get_tool_executor()
        # Own Pi subprocess. RpcClient.start() is self-contained: it spawns pi
        # (stdin/stdout JSON-RPC, no port) and wires the worker signals.
        from edini.rpc_client import RpcClient
        self._rpc = RpcClient(parent=self)
        self._rpc.start()
        # Fresh isolated session for this project, named after the node path.
        self._rpc.send_new_session()
        if self._bound_node_path:
            self._rpc.send_set_session_name(self._bound_node_path)
        # Wire streaming signals once.
        self._rpc.text_delta.connect(self._on_stream_delta)
        self._rpc.agent_finished.connect(self._on_turn_done)
        self._stream_wired = True
        return self._rpc

    def _send(self) -> None:
        text = self.input_edit.toPlainText().strip()
        if not text or self._bound_node_path is None:
            return
        self.input_edit.clear()
        # Show the user's message immediately.
        from edini.ui.agent_panel import _UserBubble
        self.timeline.add_widget(_UserBubble(text))
        # Drive the LLM via this panel's OWN RpcClient (independent Pi session,
        # per spec decision #11). Session setup happens once in _get_rpc.
        rpc = self._get_rpc()
        rpc.send_prompt(text)

    def _on_stream_delta(self, chunk: str) -> None:
        # Append to the lightweight _StreamBubble. append_chunk is plain-text
        # setText (microseconds, no markdown/HTML parse), so it's safe to call
        # per chunk without freezing the input box. The expensive markdown
        # render happens once in finalize() on turn-done.
        if self._current_ai is None and chunk.strip():
            self._current_ai = _StreamBubble()
            self.timeline.add_widget(self._current_ai)
        if self._current_ai is not None:
            self._current_ai.append_chunk(chunk)

    def _on_turn_done(self) -> None:
        # One-shot full markdown render at stream end.
        if self._current_ai is not None:
            self._current_ai.finalize()
            self._current_ai = None
        if self._current_ai is not None:
            self._current_ai.finalize()
            self._current_ai = None

    @property
    def bound_node_path(self) -> str | None:
        return self._bound_node_path
