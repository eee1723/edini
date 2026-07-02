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


class _InputDialog(QtWidgets.QDialog):
    """Popout text-input dialog with full IME (Chinese/CJK) support.

    Why this exists: Houdini's Python Panel container intercepts keyboard
    events BEFORE Qt's input-method pipeline (SideFX-acknowledged bug), so IME
    composition (preedit) never reaches an embedded QPlainTextEdit — the
    candidate window doesn't appear and the widget loses focus. This does NOT
    affect Houdini's native parameter pane (different UI toolkit) or a real
    top-level Qt window parented to hou.qt.mainWindow().

    Fix from first principles: since a genuine top-level Qt window is the one
    condition under which IME already works, move text entry into this QDialog
    (parented to hou.qt.mainWindow). It's a real OS window, so the IME attaches
    normally and Chinese input works perfectly.

    Usage: the panel keeps a small inline box for quick English input; a
    "input" button opens this dialog for CJK / longer messages. Enter or the
    Send button returns the text to the panel via the submitted signal.
    """

    # Emitted with the typed text when the user sends (Enter / Send button).
    submitted = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edini Project — Input")
        self.resize(520, 220)
        self._build_ui()

    def _build_ui(self) -> None:
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        hint = QtWidgets.QLabel("在此输入消息(支持中文输入法)。Enter 发送,Shift+Enter 换行。")
        hint.setStyleSheet(f"color:#8b8fa8;font-size:{fs(10)};")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        self.edit = QtWidgets.QPlainTextEdit()
        self.edit.setAttribute(QtCore.Qt.WA_InputMethodEnabled, True)
        self.edit.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.edit.setPlaceholderText("输入消息…")
        self.edit.keyPressEvent = self._on_key  # Enter to send
        lay.addWidget(self.edit, 1)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch(1)
        cancel_btn = QtWidgets.QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        send_btn = QtWidgets.QPushButton("发送")
        send_btn.setDefault(True)
        send_btn.clicked.connect(self._do_send)
        btn_row.addWidget(send_btn)
        lay.addLayout(btn_row)

    def _on_key(self, event):
        from PySide6 import QtCore as _qc
        if event.key() in (_qc.Qt.Key_Return, _qc.Qt.Key_Enter) \
           and not (event.modifiers() & (_qc.Qt.ShiftModifier | _qc.Qt.ControlModifier)):
            self._do_send()
            return
        QtWidgets.QPlainTextEdit.keyPressEvent(self.edit, event)

    def _do_send(self) -> None:
        text = self.edit.toPlainText().strip()
        if not text:
            return
        self.submitted.emit(text)
        self.edit.clear()
        self.accept()

    def open_for_input(self) -> None:
        """Show the dialog modally and clear it for fresh input."""
        self.edit.clear()
        self.show()
        self.raise_()
        self.activateWindow()
        self.edit.setFocus()


class ProjectPanelWidget(QtWidgets.QWidget):
    """The root widget shown inside the Houdini Python Pane tab."""

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self._bound_node_path: str | None = None
        self._current_ai = None
        # Per-panel RpcClient (own Pi subprocess), created lazily on first send.
        # See _get_rpc — independent of EdiniMainWindow, per spec decision #11.
        self._rpc = None
        self._build_ui()
        # Popout input dialog for CJK/IME input (Houdini Python Panel embedded
        # widgets can't receive IME composition — host event interception).
        # Parented to hou.qt.mainWindow() so it's a real top-level OS window
        # where IME works. Created lazily in _open_input_dialog.
        self._input_dialog = None

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
        # Input row: inline box (English / quick input) + a button that opens a
        # popout dialog for CJK/IME input (embedded widgets can't receive IME).
        input_row = QtWidgets.QHBoxLayout()
        input_row.setSpacing(4)
        self.input_edit = QtWidgets.QPlainTextEdit()
        self.input_edit.setFixedHeight(56)
        self.input_edit.setPlaceholderText("输入消息 (Enter 发送)…")
        self.input_edit.installEventFilter(self)  # Enter to send (handled in eventFilter)
        input_row.addWidget(self.input_edit, 1)
        self.input_btn = QtWidgets.QPushButton("💬\n输入")
        self.input_btn.setFixedHeight(56)
        self.input_btn.setMaximumWidth(56)
        self.input_btn.setToolTip("打开输入窗口(支持中文输入法)")
        self.input_btn.clicked.connect(self._open_input_dialog)
        input_row.addWidget(self.input_btn)
        cl.addLayout(input_row)
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
        self._rpc.text_delta.connect(self._on_stream_delta)
        self._rpc.agent_finished.connect(self._on_turn_done)
        # status_changed drives the bootstrap sequence: Pi reports "connecting"
        # then "connected". Session creation + model selection must happen AFTER
        # connected, or the first message is lost (Pi isn't ready). Mirrors
        # EdiniMainWindow._on_status_changed.
        self._rpc.status_changed.connect(self._on_rpc_status)
        self._rpc_ready = False
        self._pending_prompt: str | None = None  # buffered if sent pre-connect
        self._rpc.start()
        return self._rpc

    def _on_rpc_status(self, status: str) -> None:
        """Bootstrap the Pi session once it reports connected.

        On first connect: name the session and select the model (read from pi's
        own settings, same as the main window). Without setting the model, Pi
        has no provider/model and the first message gets no reply.

        NOTE: we do NOT call send_new_session() here. Each panel already runs
        its OWN Pi subprocess (per spec decision #11), which starts with a
        fresh session — so session isolation is already guaranteed. Calling
        new_session on top of that invalidates the ctx that extensions like
        pi-visionizer captured, producing a "stale ctx" error that BLOCKS the
        LLM call (the context hook throws and Pi aborts the turn). The main
        window likewise only set_session_name on connect, never new_session.
        """
        if status != "connected" or self._rpc_ready or self._rpc is None:
            return
        self._rpc_ready = True
        # Name the session after the bound node (display only; the session is
        # already fresh because this is a dedicated Pi subprocess).
        if self._bound_node_path:
            self._rpc.send_set_session_name(self._bound_node_path)
        # Select model from pi's settings (auth.json + models.json). Without
        # this, Pi doesn't know which LLM to call → first message silently
        # dropped (the bug this fixes).
        try:
            from edini.config import read_pi_settings
            pi_sett = read_pi_settings()
            provider = pi_sett.get("defaultProvider", "")
            model_id = pi_sett.get("defaultModel", "")
            if provider and model_id:
                self._rpc.send_set_model(provider, model_id)
        except Exception:
            pass
        # Flush any message that was typed before Pi finished connecting.
        if self._pending_prompt is not None:
            text, self._pending_prompt = self._pending_prompt, None
            self._rpc.send_prompt(text)

    def _send(self) -> None:
        """Send the inline input box's text (English / quick input)."""
        text = self.input_edit.toPlainText().strip()
        if not text:
            return
        self.input_edit.clear()
        self._send_text(text)

    def _send_text(self, text: str) -> None:
        """Core send path shared by inline input and the popout dialog.

        Shows a user bubble immediately, then drives the LLM via this panel's
        OWN RpcClient (independent Pi session, per spec decision #11). If Pi is
        still connecting (cold start), the prompt is buffered and flushed when
        it reports connected — otherwise the first message is lost (Pi isn't
        ready / has no model selected yet).
        """
        if not text or self._bound_node_path is None:
            return
        from edini.ui.agent_panel import _UserBubble
        self.timeline.add_widget(_UserBubble(text))
        rpc = self._get_rpc()
        if getattr(self, "_rpc_ready", False):
            rpc.send_prompt(text)
        else:
            # Pi not connected yet — buffer; _on_rpc_status will flush it.
            self._pending_prompt = text

    def _open_input_dialog(self) -> None:
        """Open the popout input dialog for CJK/IME input.

        Houdini's Python Panel container intercepts keyboard events before Qt's
        input-method pipeline, so IME (Chinese input) doesn't work in the
        embedded inline box. A real top-level QDialog parented to
        hou.qt.mainWindow() is the one condition where IME works, so we route
        CJK text entry through here.
        """
        if self._input_dialog is None:
            import hou
            self._input_dialog = _InputDialog(hou.qt.mainWindow())
            self._input_dialog.submitted.connect(self._send_text)
        self._input_dialog.open_for_input()

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
