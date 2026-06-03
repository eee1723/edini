"""AgentPanel — Chat timeline with streaming text, tool cards, and markdown rendering."""
import html
import re
from PySide6 import QtCore, QtWidgets
from edini.ui.theme import accent_color, fs


class AgentPanel(QtWidgets.QWidget):
    submit_requested = QtCore.Signal(str)
    stop_requested = QtCore.Signal()

    STREAM_FLUSH_CHARS = 80
    STREAM_FLUSH_INTERVAL_MS = 80

    def __init__(self, parent=None):
        super().__init__(parent)
        self._busy = False
        self._raw_stream_text = ""
        self._streaming = False
        self._ai_bubble_base = ""   # HTML before current AI bubble
        self._request_count = 0
        self._session_id = ""

        self._stream_flush_timer = QtCore.QTimer(self)
        self._stream_flush_timer.setSingleShot(True)
        self._stream_flush_timer.setInterval(self.STREAM_FLUSH_INTERVAL_MS)
        self._stream_flush_timer.timeout.connect(self._flush_stream)

        self._build_ui()
        self._bind_events()

    def _build_ui(self):
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # Session label
        self.session_label = QtWidgets.QLabel("会话: -")
        self.session_label.setStyleSheet("color: #71717a; font-size: 10px;")
        self.session_label.setVisible(False)
        root.addWidget(self.session_label)

        # Plan progress widget
        from edini.ui.plan_progress_widget import PlanProgressWidget
        self.plan_progress_widget = PlanProgressWidget(self)
        self.plan_progress_widget.setMaximumHeight(260)
        root.addWidget(self.plan_progress_widget)

        # Change tree
        from edini.ui.change_tree_widget import ChangeTreeWidget
        self.change_tree_widget = ChangeTreeWidget(self)
        self.change_tree_widget.setMaximumHeight(200)
        root.addWidget(self.change_tree_widget)

        # Timeline view
        self.timeline_view = QtWidgets.QTextBrowser(self)
        self.timeline_view.setReadOnly(True)
        self.timeline_view.setOpenLinks(False)
        self.timeline_view.setPlaceholderText("Edini 对话时间线将在此显示...")
        root.addWidget(self.timeline_view, 1)

        # Input row
        input_row = QtWidgets.QHBoxLayout()
        self.input_edit = QtWidgets.QPlainTextEdit(self)
        self.input_edit.setPlaceholderText("描述你希望 Edini 完成的任务...")
        self.input_edit.setFixedHeight(80)
        input_row.addWidget(self.input_edit, 1)

        action_col = QtWidgets.QVBoxLayout()
        from edini.ui.styled_checkbox import StyledCheckBox
        self.chat_only_check = StyledCheckBox("仅对话", self)
        self.send_btn = QtWidgets.QPushButton("执行", self)
        self.send_btn.setObjectName("PrimaryButton")
        self.send_btn.setMinimumWidth(96)
        action_col.addWidget(self.chat_only_check)
        action_col.addWidget(self.send_btn)
        action_col.addStretch(1)
        input_row.addLayout(action_col)
        root.addLayout(input_row)

    def _bind_events(self):
        self.send_btn.clicked.connect(self._on_send)
        self.input_edit.installEventFilter(self)

    def eventFilter(self, watched, event):
        if watched is self.input_edit and event is not None:
            if int(event.type()) == int(QtCore.QEvent.KeyPress):
                key = int(event.key())
                if key in (int(QtCore.Qt.Key_Return), int(QtCore.Qt.Key_Enter)):
                    modifiers = event.modifiers()
                    if modifiers & (QtCore.Qt.ControlModifier | QtCore.Qt.ShiftModifier):
                        cursor = self.input_edit.textCursor()
                        cursor.insertText("\n")
                        self.input_edit.setTextCursor(cursor)
                        return True
                    if modifiers == QtCore.Qt.NoModifier:
                        self._on_send()
                        return True
        return super().eventFilter(watched, event)

    def _on_send(self):
        text = self.input_edit.toPlainText().strip()
        if not text or self._busy:
            return
        self.input_edit.clear()
        self._append_user_message(text)
        self._request_count += 1
        self._raw_stream_text = ""
        self._streaming = True
        self.submit_requested.emit(text)

    # ------------------------------------------------------------------
    # Public API (called by main_window)
    # ------------------------------------------------------------------

    def set_busy(self, busy: bool):
        self._busy = busy
        self.send_btn.setEnabled(not busy)

    def set_session_id(self, sid: str):
        self._session_id = sid

    def set_request_count(self, count: int):
        self._request_count = count

    def begin_assistant_message(self):
        """Start streaming: save base HTML, begin accumulation."""
        self._raw_stream_text = ""
        self._streaming = True
        self._ai_bubble_base = self.timeline_view.toHtml()

    def append_stream_chunk(self, text: str):
        """Append delta, throttle flush."""
        self._raw_stream_text += text
        if len(self._raw_stream_text) >= self.STREAM_FLUSH_CHARS:
            self._flush_stream()
        elif not self._stream_flush_timer.isActive():
            self._stream_flush_timer.start()

    def _flush_stream(self):
        """Rebuild the single AI bubble with accumulated text + cursor."""
        if not self._raw_stream_text:
            return
        a = accent_color()
        escaped = html.escape(self._raw_stream_text)
        rendered = _format_message(escaped)
        bubble = (
            f'<div style="color:#c8ccd4;font-size:{fs(12)};line-height:1.65;'
            f'padding:10px 14px;background:#10101a;border-radius:8px;'
            f'margin:6px 48px 6px 0;">{rendered}'
            f'<span style="color:{a};">▊</span></div>'
        )
        self.timeline_view.setHtml(self._ai_bubble_base + bubble)

    def finish_streaming(self):
        """Final render without cursor."""
        self._streaming = False
        self._stream_flush_timer.stop()
        if self._raw_stream_text:
            escaped = html.escape(self._raw_stream_text)
            rendered = _format_message(escaped)
            bubble = (
                f'<div style="color:#c8ccd4;font-size:{fs(12)};line-height:1.65;'
                f'padding:10px 14px;background:#10101a;border-radius:8px;'
                f'margin:6px 48px 6px 0;">{rendered}</div>'
            )
            self.timeline_view.setHtml(self._ai_bubble_base + bubble)
        self._raw_stream_text = ""

    def add_tool_card(self, tool_name: str, args: dict):
        """Add a tool call card to the timeline."""
        a = accent_color()
        args_str = str(args)[:200]
        card_html = (
            f'<div style="color:#80cbc4;font-size:{fs(11)};background:rgba(0,188,212,0.06);'
            f'border-left:3px solid {a};padding:8px 12px;'
            f'margin:6px 24px 6px 0;border-radius:4px;">'
            f'🔧 <b>{html.escape(tool_name)}</b><br>'
            f'<span style="color:#78909c;">{html.escape(args_str)}</span>'
            f'</div>'
        )
        current = self.timeline_view.toHtml()
        self.timeline_view.setHtml(current + card_html)

    def add_error(self, message: str):
        """Add an error banner."""
        err_html = (
            f'<div style="color:#f87171;font-size:{fs(11)};background:rgba(239,68,68,0.08);'
            f'border-left:3px solid #ef4444;padding:8px 12px;margin:6px 48px;'
            f'border-radius:4px;">'
            f'⚠️ {html.escape(message)}'
            f'</div>'
        )
        current = self.timeline_view.toHtml()
        self.timeline_view.setHtml(current + err_html)

    def add_separator(self, text: str = "── 本轮结束 ──"):
        """Add a separator line."""
        sep_html = (
            f'<div style="text-align:center;color:#6a6e76;font-size:{fs(10)};'
            f'margin:16px 0;border-top:1px solid #1a1a28;padding-top:8px;">'
            f'{html.escape(text)}</div>'
        )
        current = self.timeline_view.toHtml()
        self.timeline_view.setHtml(current + sep_html)

    def clear_timeline(self):
        self.timeline_view.clear()

    def _append_user_message(self, text: str):
        """Add a user message bubble to the timeline."""
        escaped = html.escape(text)
        bubble_html = (
            f'<div style="color:#e5e5eb;font-size:12px;line-height:1.6;'
            f'padding:8px 12px;background:#1a3a5c;border-radius:8px;'
            f'margin:4px 0 4px 40px;text-align:right;">'
            f'{escaped}'
            f'</div>'
        )
        current = self.timeline_view.toHtml()
        self.timeline_view.setHtml(current + bubble_html)

    def _append_assistant_message(self, text: str):
        """Append a pre-rendered assistant message (used for session loading)."""
        escaped = html.escape(text)
        rendered = _format_message(escaped)
        bubble_html = (
            f'<div style="color:#e5e5eb;font-size:12px;line-height:1.6;'
            f'padding:8px 12px;background:#1a1a24;border-radius:8px;'
            f'margin:4px 40px 4px 0;">{rendered}</div>'
        )
        current = self.timeline_view.toHtml()
        self.timeline_view.setHtml(current + bubble_html)


def _format_message(text: str) -> str:
    """Convert plain text with markdown-ish syntax to simple HTML."""
    out = text

    # Code blocks: ``` ... ```
    out = re.sub(
        r'```(\w*)\n(.*?)```',
        r'<pre style="background:#0e0e15;color:#d4d4d4;padding:8px;'
        r'border-radius:4px;font-family:monospace;font-size:11px;'
        r'margin:4px 0;overflow-x:auto;">\2</pre>',
        out, flags=re.DOTALL,
    )

    # Inline code: `...`
    out = re.sub(
        r'`([^`]+)`',
        r'<code style="background:#1a1a24;color:#67e8f9;padding:1px 4px;'
        r'border-radius:3px;font-family:monospace;font-size:11px;">\1</code>',
        out,
    )

    # Bold: **...**
    out = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', out)

    # Newlines
    out = out.replace("\n", "<br>")

    return out
