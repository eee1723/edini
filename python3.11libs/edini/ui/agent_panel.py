"""AgentPanel — Chat timeline + collapsible Tool Call panel + execute/abort toggle."""
import html
import re
import base64
from PySide6 import QtCore, QtGui, QtWidgets
from edini.ui.theme import accent_color, fs


# ── Style fragments ──
def _bubble_user_style() -> str:
    return (
        f'color:#e5e5eb;font-size:{fs(12)};line-height:1.6;'
        f'padding:8px 12px;background:#1a3a5c;border-radius:8px;'
        f'margin:6px 0 6px 48px;'
    )

def _bubble_ai_style() -> str:
    return (
        f'color:#e5e5eb;font-size:{fs(12)};line-height:1.6;'
        f'padding:8px 12px;background:#1a1a24;border-radius:8px;'
        f'margin:6px 48px 6px 0;'
    )

def _thinking_collapsed_style() -> str:
    a = accent_color()
    return (
        f'color:#a1a1aa;font-size:{fs(11)};cursor:pointer;'
        f'background:rgba(0,188,212,0.06);padding:4px 8px;'
        f'border-radius:4px;margin:4px 32px 4px 0;display:inline-block;'
        f'border-left:2px solid {a};'
    )

def _thinking_expanded_style() -> str:
    a = accent_color()
    return (
        f'color:#71717a;font-size:{fs(11)};'
        f'background:#0e0e15;padding:4px 8px;'
        f'border-left:2px solid {a};margin:4px 32px 4px 8px;'
    )

def _separator_style() -> str:
    return (
        f'text-align:center;color:#52525b;font-size:{fs(10)};'
        f'margin:10px 0;border-top:1px solid #2a2a3c;padding-top:6px;'
    )


# ==========================================================================
# Tool Card Widget (real QWidget, not HTML)
# ==========================================================================

class _ToolCardWidget(QtWidgets.QFrame):
    """A single collapsible tool call card. Added/updated in real-time."""

    def __init__(self, tool_name: str, args: dict, tool_call_id: str, parent=None):
        super().__init__(parent)
        self._tool_call_id = tool_call_id
        self._expanded = False

        self.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.setStyleSheet(f"""
            _ToolCardWidget {{
                background: rgba(0,188,212,0.05);
                border: 1px solid #1e2e2e;
                border-radius: 4px;
                margin: 2px 0;
            }}
        """)
        self.setCursor(QtCore.Qt.PointingHandCursor)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(1)

        # Header row: icon + name + status
        header_row = QtWidgets.QHBoxLayout()
        header_row.setSpacing(2)
        self._arrow = QtWidgets.QLabel("▸")
        self._arrow.setStyleSheet(f"color:#80cbc4;font-size:{fs(11)};border:none;")
        self._arrow.setFixedWidth(16)
        header_row.addWidget(self._arrow)

        self._name_label = QtWidgets.QLabel(f"🔧 {html.escape(tool_name)}")
        self._name_label.setStyleSheet(f"color:#80cbc4;font-size:{fs(11)};font-weight:600;border:none;")
        header_row.addWidget(self._name_label, 1)

        self._status_label = QtWidgets.QLabel("⏳")
        self._status_label.setStyleSheet(f"color:#d97706;font-size:{fs(10)};border:none;")
        self._status_label.setFixedWidth(30)
        self._status_label.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        header_row.addWidget(self._status_label)

        layout.addLayout(header_row)

        # Detail area (hidden by default)
        self._detail = QtWidgets.QWidget()
        detail_layout = QtWidgets.QVBoxLayout(self._detail)
        detail_layout.setContentsMargins(20, 2, 0, 2)
        detail_layout.setSpacing(2)

        # Args display
        args_str = _format_args(args)
        self._args_label = QtWidgets.QLabel(args_str)
        self._args_label.setWordWrap(True)
        self._args_label.setStyleSheet(f"color:#78909c;font-size:{fs(10)};font-family:monospace;border:none;")
        detail_layout.addWidget(self._args_label)

        # Result display
        self._result_label = QtWidgets.QLabel("")
        self._result_label.setWordWrap(True)
        self._result_label.setStyleSheet(f"color:#94a3b8;font-size:{fs(10)};border:none;")
        self._result_label.setVisible(False)
        detail_layout.addWidget(self._result_label)

        self._detail.setVisible(False)
        layout.addWidget(self._detail)

    def mousePressEvent(self, event):
        self._expanded = not self._expanded
        self._arrow.setText("▾" if self._expanded else "▸")
        self._detail.setVisible(self._expanded)
        super().mousePressEvent(event)

    def set_result(self, result_text: str, success: bool = True):
        self._status_label.setText("✅" if success else "❌")
        self._status_label.setStyleSheet(
            f"color:{'#16a34a' if success else '#ef4444'};font-size:{fs(10)};border:none;"
        )
        self._result_label.setText(_format_tool_result_short(result_text, success))
        self._result_label.setVisible(True)

    def set_error(self, error_msg: str):
        self._status_label.setText("❌")
        self._status_label.setStyleSheet(f"color:#ef4444;font-size:{fs(10)};border:none;")
        self._result_label.setText(f"Error: {html.escape(error_msg)}")
        self._result_label.setVisible(True)

    @property
    def tool_call_id(self) -> str:
        return self._tool_call_id


# ==========================================================================
# AgentPanel
# ==========================================================================

class AgentPanel(QtWidgets.QWidget):
    submit_requested = QtCore.Signal(str, object)   # text, images
    stop_requested = QtCore.Signal()
    abort_requested = QtCore.Signal()

    STREAM_FLUSH_CHARS = 80
    STREAM_FLUSH_INTERVAL_MS = 80

    def __init__(self, parent=None):
        super().__init__(parent)
        self._busy = False
        self._stream_segments: list[dict] = []  # [{type: text|thinking, content: str}]
        self._current_text = ""
        self._streaming = False
        self._ai_bubble_base = ""
        self._request_count = 0
        self._session_id = ""
        self._user_scrolled_up = False

        # Pending data
        self._thinking_count = 0
        self._thinking_buf = ""  # accumulate R1 word-chunks
        self._thinking_buf_timer = QtCore.QTimer(self)
        self._thinking_buf_timer.setSingleShot(True)
        self._thinking_buf_timer.setInterval(200)
        self._thinking_buf_timer.timeout.connect(self._flush_thinking_buf)
        self._tool_cards: dict[str, _ToolCardWidget] = {}

        # Screenshot
        self._screenshot_data: str | None = None

        self._stream_flush_timer = QtCore.QTimer(self)
        self._stream_flush_timer.setSingleShot(True)
        self._stream_flush_timer.setInterval(self.STREAM_FLUSH_INTERVAL_MS)
        self._stream_flush_timer.timeout.connect(self._flush_stream)

        self._build_ui()
        self._bind_events()

    # ------------------------------------------------------------------
    # UI Build
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(4)

        # Plan progress + Change tree (placeholders, hidden)
        from edini.ui.plan_progress_widget import PlanProgressWidget
        self.plan_progress_widget = PlanProgressWidget(self)
        self.plan_progress_widget.setMaximumHeight(260)
        root.addWidget(self.plan_progress_widget)

        from edini.ui.change_tree_widget import ChangeTreeWidget
        self.change_tree_widget = ChangeTreeWidget(self)
        self.change_tree_widget.setMaximumHeight(200)
        root.addWidget(self.change_tree_widget)

        # ── Timeline + Tool Call Panel (vertical splitter) ──
        self._vsplitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)

        self.timeline_view = QtWidgets.QTextBrowser()
        self.timeline_view.setReadOnly(True)
        self.timeline_view.setOpenLinks(False)
        self.timeline_view.setPlaceholderText("描述你想做的事情，Edini 会帮你操作 Houdini...")
        self.timeline_view.verticalScrollBar().valueChanged.connect(self._on_user_scroll)
        self._vsplitter.addWidget(self.timeline_view)

        # ── Tool Call Panel (collapsible, below timeline) ──
        self._tool_panel = QtWidgets.QFrame()
        self._tool_panel.setStyleSheet("""
            _ToolCardWidget {
                background: #0e0e15;
                border: 1px solid #1c1c28;
                border-radius: 4px;
            }
        """)
        tool_panel_layout = QtWidgets.QVBoxLayout(self._tool_panel)
        tool_panel_layout.setContentsMargins(8, 4, 8, 4)
        tool_panel_layout.setSpacing(2)

        # Header: toggle + counter
        tool_header = QtWidgets.QHBoxLayout()
        self._tool_toggle = QtWidgets.QLabel("▸ Tool Calls (0)")
        self._tool_toggle.setCursor(QtCore.Qt.PointingHandCursor)
        self._tool_toggle.setStyleSheet(f"color:#52525b;font-size:{fs(10)};border:none;")
        self._tool_toggle.mousePressEvent = self._toggle_tool_panel
        tool_header.addWidget(self._tool_toggle)
        tool_header.addStretch()
        tool_panel_layout.addLayout(tool_header)

        # Scroll area for tool cards
        self._tool_scroll = QtWidgets.QScrollArea()
        self._tool_scroll.setWidgetResizable(True)
        self._tool_scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self._tool_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self._tool_scroll.setMaximumHeight(300)
        self._tool_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self._tool_container = QtWidgets.QWidget()
        self._tool_layout = QtWidgets.QVBoxLayout(self._tool_container)
        self._tool_layout.setAlignment(QtCore.Qt.AlignTop)
        self._tool_layout.setSpacing(2)
        self._tool_layout.setContentsMargins(0, 0, 0, 0)
        self._tool_layout.addStretch()
        self._tool_scroll.setWidget(self._tool_container)

        self._tool_scroll.setVisible(False)
        tool_panel_layout.addWidget(self._tool_scroll)

        self._tool_panel_expanded = False
        self._vsplitter.addWidget(self._tool_panel)

        # Set default sizes: timeline gets most space, tool panel minimal
        self._vsplitter.setSizes([-1, 28])
        self._vsplitter.setCollapsible(0, False)
        self._vsplitter.setCollapsible(1, False)
        self._vsplitter.setStretchFactor(0, 3)
        self._vsplitter.setStretchFactor(1, 1)
        root.addWidget(self._vsplitter, 1)

        # ── Input row ──
        input_row = QtWidgets.QHBoxLayout()
        self.input_edit = QtWidgets.QPlainTextEdit(self)
        self.input_edit.setPlaceholderText("描述你希望 Edini 完成的任务... (Enter 发送)")
        self.input_edit.setFixedHeight(64)
        input_row.addWidget(self.input_edit, 1)

        # Action column
        action_col = QtWidgets.QVBoxLayout()
        action_col.setSpacing(4)

        # Screenshot button
        from edini.ui.viewport import is_vision_capable
        from edini.config import get_settings
        settings = get_settings()
        self._screenshot_btn = QtWidgets.QPushButton("📷")
        self._screenshot_btn.setToolTip("Capture viewport screenshot")
        self._screenshot_btn.setFixedSize(32, 32)
        self._screenshot_btn.clicked.connect(self._on_capture_viewport)
        self._screenshot_btn.setVisible(is_vision_capable(
            settings.get("provider", ""), settings.get("model_id", "")))
        action_col.addWidget(self._screenshot_btn)

        self._screenshot_remove_btn = QtWidgets.QPushButton("✕")
        self._screenshot_remove_btn.setObjectName("GhostButton")
        self._screenshot_remove_btn.setToolTip("Remove screenshot")
        self._screenshot_remove_btn.clicked.connect(self._on_remove_screenshot)
        self._screenshot_remove_btn.setVisible(False)
        self._screenshot_remove_btn.setFixedSize(32, 20)
        action_col.addWidget(self._screenshot_remove_btn)

        from edini.ui.styled_checkbox import StyledCheckBox
        self.chat_only_check = StyledCheckBox("仅对话", self)

        # Send / Abort button (toggles)
        self._action_btn = QtWidgets.QPushButton("执行")
        self._action_btn.setObjectName("PrimaryButton")
        self._action_btn.setMinimumWidth(80)
        self._action_btn.clicked.connect(self._on_action_btn)

        action_col.addWidget(self.chat_only_check)
        action_col.addWidget(self._action_btn)
        action_col.addStretch(1)
        input_row.addLayout(action_col)
        root.addLayout(input_row)

    def _bind_events(self):
        self.input_edit.installEventFilter(self)

    def eventFilter(self, watched, event):
        if watched is self.input_edit and event is not None:
            if int(event.type()) == int(QtCore.QEvent.KeyPress):
                key = int(event.key())
                if key == int(QtCore.Qt.Key_Escape):
                    if self._busy:
                        self._on_abort()
                    return True
                if key in (int(QtCore.Qt.Key_Return), int(QtCore.Qt.Key_Enter)):
                    modifiers = event.modifiers()
                    if modifiers & (QtCore.Qt.ControlModifier | QtCore.Qt.ShiftModifier):
                        cursor = self.input_edit.textCursor()
                        cursor.insertText("\n")
                        self.input_edit.setTextCursor(cursor)
                        return True
                    if modifiers == QtCore.Qt.NoModifier:
                        if self._busy:
                            self._on_abort()
                        else:
                            self._on_send()
                        return True
        return super().eventFilter(watched, event)

    # ------------------------------------------------------------------
    # Button toggle
    # ------------------------------------------------------------------

    def _on_action_btn(self):
        if self._busy:
            self._on_abort()
        else:
            self._on_send()

    def _on_abort(self):
        self.abort_requested.emit()

    # ------------------------------------------------------------------
    # Send
    # ------------------------------------------------------------------

    def _on_send(self):
        text = self.input_edit.toPlainText().strip()
        if not text or self._busy:
            return
        self.input_edit.clear()
        self._append_user_message(text)
        self._request_count += 1
        self._stream_segments.clear()
        self._current_text = ""
        self._streaming = True
        self._thinking_count = 0
        self._user_scrolled_up = False

        # Reset tool panel to collapsed state
        self._clear_tool_cards()
        self._tool_panel_expanded = False
        self._tool_scroll.setVisible(False)
        self._tool_toggle.setText("▸ Tool Calls (0)")
        self._vsplitter.setSizes([-1, 28])
        if hasattr(self, '_saved_sizes'):
            del self._saved_sizes

        images = None
        if self._screenshot_data:
            images = [{"type": "image/jpeg", "data": self._screenshot_data}]
            self._on_remove_screenshot()

        self.submit_requested.emit(text, images)

    # ------------------------------------------------------------------
    # Tool Call Panel
    # ------------------------------------------------------------------

    def _toggle_tool_panel(self, event=None):
        self._tool_panel_expanded = not self._tool_panel_expanded
        self._tool_scroll.setVisible(self._tool_panel_expanded)
        arrow = "▾" if self._tool_panel_expanded else "▸"
        count = len(self._tool_cards)
        self._tool_toggle.setText(f"{arrow} Tool Calls ({count})")
        # Resize splitter: collapse tool panel to header-only, or restore
        if self._tool_panel_expanded:
            if hasattr(self, '_saved_sizes'):
                self._vsplitter.setSizes(self._saved_sizes)
        else:
            self._saved_sizes = list(self._vsplitter.sizes())
            self._vsplitter.setSizes([self._vsplitter.height() - 28, 28])

    def _add_tool_card_ui(self, tool_name: str, args: dict, tool_call_id: str):
        """Immediately add a tool card widget to the panel."""
        card = _ToolCardWidget(tool_name, args, tool_call_id)
        self._tool_layout.insertWidget(self._tool_layout.count() - 1, card)
        self._tool_cards[tool_call_id] = card

        # Update counter
        count = len(self._tool_cards)
        arrow = "▾" if self._tool_panel_expanded else "▸"
        self._tool_toggle.setText(f"{arrow} Tool Calls ({count})")

        # Auto-expand panel when first tool arrives
        if not self._tool_panel_expanded and count == 1:
            self._toggle_tool_panel()

    def _update_tool_card_result(self, tool_call_id: str, result_text: str, success: bool = True):
        """Update result on an existing tool card."""
        card = self._tool_cards.get(tool_call_id)
        if card:
            card.set_result(result_text, success)

    def _clear_tool_cards(self):
        """Remove all tool cards from panel."""
        for card in self._tool_cards.values():
            self._tool_layout.removeWidget(card)
            card.deleteLater()
        self._tool_cards.clear()
        self._tool_toggle.setText("▸ Tool Calls (0)")
        if self._tool_panel_expanded:
            self._tool_scroll.setVisible(True)

    # ------------------------------------------------------------------
    # Viewport screenshot
    # ------------------------------------------------------------------

    def _on_capture_viewport(self):
        from edini.ui.viewport import capture_viewport
        b64 = capture_viewport()
        if b64 is None:
            return
        self._screenshot_data = b64
        self._screenshot_btn.setText("📸")
        self._screenshot_remove_btn.setVisible(True)

    def _on_remove_screenshot(self):
        self._screenshot_data = None
        self._screenshot_btn.setText("📷")
        self._screenshot_remove_btn.setVisible(False)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_busy(self, busy: bool):
        self._busy = busy
        if busy:
            self._action_btn.setText("中止")
            self._action_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: #dc2626;
                    color: #f1f1f1;
                    border: none;
                    border-radius: 5px;
                    padding: 6px 14px;
                    font-size: {fs(12)};
                    font-weight: 600;
                    min-height: 24px;
                }}
                QPushButton:hover {{ background-color: #ef4444; }}
                QPushButton:pressed {{ background-color: #b91c1c; }}
            """)
        else:
            self._action_btn.setText("执行")
            self._action_btn.setObjectName("PrimaryButton")
            # Reapply via parent stylesheet refresh or direct
            a = accent_color()
            self._action_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {a};
                    color: #0a0a10;
                    border: none;
                    border-radius: 5px;
                    padding: 6px 20px;
                    font-size: {fs(12)};
                    font-weight: 600;
                }}
                QPushButton:hover {{ background-color: {_lighter(a, 0.3)}; }}
                QPushButton:pressed {{ background-color: {_darker(a, 0.15)}; }}
            """)

    def set_session_id(self, sid: str):
        self._session_id = sid

    def set_request_count(self, count: int):
        self._request_count = count

    def begin_assistant_message(self):
        self._stream_segments.clear()
        self._current_text = ""
        self._thinking_buf = ""
        self._streaming = True
        self._thinking_count = 0
        self._ai_bubble_base = self.timeline_view.toHtml()

    def append_stream_chunk(self, text: str):
        self._current_text += text
        if len(self._current_text) >= self.STREAM_FLUSH_CHARS:
            self._flush_stream()
        elif not self._stream_flush_timer.isActive():
            self._stream_flush_timer.start()

    def _flush_stream(self):
        if not self._stream_segments and not self._current_text:
            return
        self._render_segments()

    def finish_streaming(self):
        self._streaming = False
        self._stream_flush_timer.stop()
        self._thinking_buf_timer.stop()
        self._flush_thinking_buf()
        if self._current_text.strip():
            self._stream_segments.append({"type": "text", "content": self._current_text})
            self._current_text = ""
        self._render_final()

    def add_tool_card(self, tool_name: str, args: dict, tool_call_id: str = ""):
        """Real-time: add tool card widget to panel."""
        self._add_tool_card_ui(tool_name, args, tool_call_id)

    def set_tool_result(self, tool_call_id: str, result: str):
        """Real-time: update tool card result."""
        self._update_tool_card_result(tool_call_id, result, True)

    def add_thinking_step(self, step_num: int, text: str):
        """Accumulate thinking chunks (R1 sends one word per event), flush after 200ms idle."""
        self._thinking_count += 1
        clean = _clean_thinking(text)
        if self._thinking_buf:
            self._thinking_buf += " " + clean
        else:
            self._thinking_buf = clean
        self._thinking_buf_timer.start()  # restart 200ms timer

    def _flush_thinking_buf(self):
        """Flush accumulated thinking buffer as a single segment."""
        if not self._thinking_buf.strip():
            return
        if self._current_text.strip():
            self._stream_segments.append({"type": "text", "content": self._current_text})
            self._current_text = ""
        self._stream_segments.append({"type": "thinking", "content": self._thinking_buf})
        self._thinking_buf = ""
        self._render_segments()

    def _render_segments(self):
        """Render segments with interleaved thinking + live cursor."""
        parts = []
        for i, seg in enumerate(self._stream_segments):
            if seg["type"] == "text":
                escaped = html.escape(seg["content"])
                rendered = _format_message(escaped)
                parts.append(f'<div style="{_bubble_ai_style()}">{rendered}</div>')
            elif seg["type"] == "thinking":
                tid = f"th{self._request_count}_{i}"
                preview = html.escape(seg["content"][:40])
                parts.append(
                    f'<div style="{_thinking_collapsed_style()}" '
                    f'onclick="var e=document.getElementById(\'{tid}\');'
                    f'e.style.display=e.style.display==\'none\'?\'block\':\'none\';'
                    f'this.innerHTML=this.innerHTML.replace(\'▸\',e.style.display==\'none\'?\'▸\':\'▾\');">'
                    f'▸ {preview}</div>'
                )
                parts.append(
                    f'<div id="{tid}" style="display:none;{_thinking_expanded_style()}">'
                    f'<pre style="margin:0;color:#71717a;font-size:{fs(11)};white-space:pre-wrap;'
                    f'background:transparent;font-family:inherit;">'
                    f'{html.escape(seg["content"])}</pre>'
                    f'</div>'
                )
        if self._current_text:
            a = accent_color()
            escaped = html.escape(self._current_text)
            rendered = _format_message(escaped)
            parts.append(
                f'<div style="{_bubble_ai_style()}">{rendered}'
                f'<span style="color:{a};">▊</span></div>'
            )
        if parts:
            self.timeline_view.setHtml(self._ai_bubble_base + "".join(parts))
            self._scroll_to_bottom()

    def _render_final(self):
        """Final render without cursor + separator."""
        parts = []
        for i, seg in enumerate(self._stream_segments):
            if seg["type"] == "text":
                escaped = html.escape(seg["content"])
                rendered = _format_message(escaped)
                parts.append(f'<div style="{_bubble_ai_style()}">{rendered}</div>')
            elif seg["type"] == "thinking":
                tid = f"thf{self._request_count}_{i}"
                preview = html.escape(seg["content"][:40])
                parts.append(
                    f'<div style="{_thinking_collapsed_style()}" '
                    f'onclick="var e=document.getElementById(\'{tid}\');'
                    f'e.style.display=e.style.display==\'none\'?\'block\':\'none\';'
                    f'this.innerHTML=this.innerHTML.replace(\'▸\',e.style.display==\'none\'?\'▸\':\'▾\');">'
                    f'▸ {preview}</div>'
                )
                parts.append(
                    f'<div id="{tid}" style="display:none;{_thinking_expanded_style()}">'
                    f'<pre style="margin:0;color:#71717a;font-size:{fs(11)};white-space:pre-wrap;'
                    f'background:transparent;font-family:inherit;">'
                    f'{html.escape(seg["content"])}</pre>'
                    f'</div>'
                )
        parts.append(f'<div style="{_separator_style()}">── 本轮结束 ──</div>')
        self.timeline_view.setHtml(self._ai_bubble_base + "".join(parts))
        self._scroll_to_bottom()

    def add_error(self, message: str):
        err_html = (
            f'<div style="color:#f87171;font-size:{fs(11)};background:rgba(239,68,68,0.08);'
            f'border-left:3px solid #ef4444;padding:8px 12px;margin:6px 48px;'
            f'border-radius:4px;">'
            f'⚠️ {html.escape(message)}'
            f'</div>'
        )
        self.timeline_view.setHtml(self.timeline_view.toHtml() + err_html)

    def show_aborted(self):
        self._clear_tool_cards()
        abort_html = (
            f'<div style="text-align:center;color:#f87171;font-size:{fs(11)};'
            f'margin:8px 0;">── 已中止 ──</div>'
        )
        self.timeline_view.setHtml(self.timeline_view.toHtml() + abort_html)
        self.set_busy(False)

    def clear_timeline(self):
        self.timeline_view.clear()
        self._clear_tool_cards()

    # ------------------------------------------------------------------
    # Message rendering
    # ------------------------------------------------------------------

    def _append_user_message(self, text: str):
        escaped = html.escape(text)
        bubble_html = f'<div style="{_bubble_user_style()}">{escaped}</div>'
        self.timeline_view.setHtml(self.timeline_view.toHtml() + bubble_html)
        self._scroll_to_bottom()

    def _append_assistant_message(self, text: str):
        escaped = html.escape(text)
        rendered = _format_message(escaped)
        bubble_html = f'<div style="{_bubble_ai_style()}">{rendered}</div>'
        self.timeline_view.setHtml(self.timeline_view.toHtml() + bubble_html)

    def _render_stored_assistant_message(self, msg: dict):
        """Render stored message with interleaved thinking blocks."""
        content = msg.get("content", "")
        thinking = msg.get("thinking", [])
        parts = []
        # Simple: thinking first, then content
        for i, t in enumerate(thinking):
            tid = f"sth_{id(msg)}_{i}"
            preview = html.escape(t[:40])
            parts.append(
                f'<div style="{_thinking_collapsed_style()}" '
                f'onclick="var e=document.getElementById(\'{tid}\');'
                f'e.style.display=e.style.display==\'none\'?\'block\':\'none\';'
                f'this.innerHTML=this.innerHTML.replace(\'▸\',e.style.display==\'none\'?\'▸\':\'▾\');">'
                f'▸ {preview}</div>'
            )
            parts.append(
                f'<div id="{tid}" style="display:none;{_thinking_expanded_style()}">'
                f'<pre style="margin:0;color:#71717a;font-size:{fs(11)};white-space:pre-wrap;'
                f'background:transparent;font-family:inherit;">'
                f'{html.escape(t)}</pre></div>'
            )
        if content:
            escaped = html.escape(content)
            rendered = _format_message(escaped)
            parts.append(f'<div style="{_bubble_ai_style()}">{rendered}</div>')
        parts.append(f'<div style="{_separator_style()}">──</div>')
        self.timeline_view.setHtml(self.timeline_view.toHtml() + "".join(parts))

    # ------------------------------------------------------------------
    # Smart scroll
    # ------------------------------------------------------------------

    def _on_user_scroll(self, value: int):
        sb = self.timeline_view.verticalScrollBar()
        max_val = sb.maximum()
        self._user_scrolled_up = (max_val - value) > 50

    def _scroll_to_bottom(self):
        if not self._user_scrolled_up:
            sb = self.timeline_view.verticalScrollBar()
            sb.setValue(sb.maximum())


# ==========================================================================
# Formatting helpers
# ==========================================================================

def _format_message(text: str) -> str:
    """Convert plain text with markdown-ish syntax to simple HTML with Copy buttons."""
    out = text

    def _code_block_replacer(m):
        code_raw = m.group(2)
        code_escaped = html.escape(code_raw)
        return (
            f'<div style="position:relative;margin:4px 0;">'
            f'<button onclick="'
            f'var ta=document.createElement(\'textarea\');'
            f'ta.value=this.parentElement.querySelector(\'pre code\').innerText;'
            f'document.body.appendChild(ta);ta.select();'
            f'document.execCommand(\'copy\');document.body.removeChild(ta);'
            f'this.innerHTML=\'✓ Copied\';'
            f'setTimeout(function(){{this.innerHTML=\'📋 Copy\';}}.bind(this),2000);'
            f'"'
            f'style="position:absolute;right:4px;top:4px;background:#2a2a3c;'
            f'color:#a1a1aa;border:none;border-radius:3px;padding:2px 8px;'
            f'cursor:pointer;font-size:10pt;z-index:1;">'
            f'📋 Copy</button>'
            f'<pre style="background:#0e0e15;color:#d4d4d4;padding:8px;'
            f'border-radius:4px;font-family:monospace;font-size:11pt;'
            f'overflow-x:auto;margin:0;padding-top:24px;"><code>{code_escaped}</code></pre>'
            f'</div>'
        )

    out = re.sub(r'```(\w*)\n(.*?)```', _code_block_replacer, out, flags=re.DOTALL)

    out = re.sub(
        r'`([^`]+)`',
        r'<code style="background:#1a1a24;color:#67e8f9;padding:1px 4px;'
        r'border-radius:3px;font-family:monospace;font-size:11pt;">\1</code>',
        out,
    )

    out = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', out)
    out = out.replace("\n", "<br>")
    return out


def _clean_thinking(text: str) -> str:
    """Remove DeepSeek R1 word-numbering pattern: '1. word 2. word' → 'word word'."""
    # Pattern: number + dot + space + word, repeated
    if re.match(r'^(\d+\.\s+\w+\s*)+$', text):
        return re.sub(r'\d+\.\s+', '', text).strip()
    return text


def _format_args(args: dict) -> str:
    """Format tool call arguments for compact display."""
    if not args:
        return ""
    parts = []
    for k, v in args.items():
        parts.append(f"<b>{html.escape(k)}</b>: {html.escape(str(v))}")
    return "  ·  ".join(parts)


def _format_tool_result_short(result: str, success: bool) -> str:
    """Format tool result for compact card display."""
    if not result:
        return ""
    try:
        import json
        d = json.loads(result) if isinstance(result, str) else result
        if isinstance(d, dict):
            if d.get("success"):
                out = d.get("path", d.get("output", d.get("name", "")))
                return html.escape(str(out)[:80])
            else:
                return html.escape(d.get("error", "Unknown error")[:80])
    except Exception:
        pass
    return html.escape(str(result)[:80])


def _lighter(h: str, a: float) -> str:
    r, g, b = int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)
    return f"#{min(255,int(r+(255-r)*a)):02x}{min(255,int(g+(255-g)*a)):02x}{min(255,int(b+(255-b)*a)):02x}"


def _darker(h: str, a: float) -> str:
    r, g, b = int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)
    return f"#{max(0,int(r*(1-a))):02x}{max(0,int(g*(1-a))):02x}{max(0,int(b*(1-a))):02x}"
