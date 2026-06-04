"""AgentPanel — Chat timeline with double-layer collapse, Copy buttons, smart scroll."""
import html
import re
import base64
from PySide6 import QtCore, QtGui, QtWidgets
from edini.ui.theme import accent_color, fs


# ── Bubble / UI style fragments ──
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

def _tool_collapsed_style() -> str:
    return (
        f'color:#a1a1aa;font-size:{fs(11)};cursor:pointer;'
        f'background:rgba(0,188,212,0.06);padding:4px 8px;'
        f'border-radius:4px;margin:4px 32px 4px 0;display:inline-block;'
        f'border-left:2px solid #80cbc4;'
    )

def _tool_expanded_style() -> str:
    return (
        f'color:#94a3b8;font-size:{fs(11)};'
        f'background:#0e0e15;padding:4px 8px;'
        f'border-left:2px solid #06b6d4;margin:4px 32px 4px 8px;'
    )

def _separator_style() -> str:
    return (
        f'text-align:center;color:#52525b;font-size:{fs(10)};'
        f'margin:10px 0;border-top:1px solid #2a2a3c;padding-top:6px;'
    )


class AgentPanel(QtWidgets.QWidget):
    submit_requested = QtCore.Signal(str, object)   # text, images
    stop_requested = QtCore.Signal()
    abort_requested = QtCore.Signal()

    STREAM_FLUSH_CHARS = 80
    STREAM_FLUSH_INTERVAL_MS = 80

    def __init__(self, parent=None):
        super().__init__(parent)
        self._busy = False
        self._raw_stream_text = ""
        self._streaming = False
        self._ai_bubble_base = ""
        self._request_count = 0
        self._session_id = ""
        self._user_scrolled_up = False

        # Pending block data for AI response unit
        self._pending_thinkings: list[str] = []
        self._pending_tools: list[dict] = []
        self._thinking_count = 0

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
        root.setSpacing(6)

        # Plan progress widget (placeholder)
        from edini.ui.plan_progress_widget import PlanProgressWidget
        self.plan_progress_widget = PlanProgressWidget(self)
        self.plan_progress_widget.setMaximumHeight(260)
        root.addWidget(self.plan_progress_widget)

        # Change tree (placeholder)
        from edini.ui.change_tree_widget import ChangeTreeWidget
        self.change_tree_widget = ChangeTreeWidget(self)
        self.change_tree_widget.setMaximumHeight(200)
        root.addWidget(self.change_tree_widget)

        # Timeline view
        self.timeline_view = QtWidgets.QTextBrowser(self)
        self.timeline_view.setReadOnly(True)
        self.timeline_view.setOpenLinks(False)
        self.timeline_view.setPlaceholderText("Edini 对话时间线将在此显示...")
        self.timeline_view.verticalScrollBar().valueChanged.connect(self._on_user_scroll)
        root.addWidget(self.timeline_view, 1)

        # Input row
        input_row = QtWidgets.QHBoxLayout()
        self.input_edit = QtWidgets.QPlainTextEdit(self)
        self.input_edit.setPlaceholderText("描述你希望 Edini 完成的任务...")
        self.input_edit.setFixedHeight(72)
        input_row.addWidget(self.input_edit, 1)

        # Action column
        action_col = QtWidgets.QVBoxLayout()
        action_col.setSpacing(4)

        # Screenshot button + remove
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
        self.send_btn = QtWidgets.QPushButton("执行", self)
        self.send_btn.setObjectName("PrimaryButton")
        self.send_btn.setMinimumWidth(80)
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
                if key == int(QtCore.Qt.Key_Escape):
                    if self._busy:
                        self.abort_requested.emit()
                    return True
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
        self._raw_stream_text = ""
        self._streaming = True

        images = None
        if self._screenshot_data:
            images = [{"type": "image/jpeg", "data": self._screenshot_data}]
            self._on_remove_screenshot()

        self.submit_requested.emit(text, images)

    # ------------------------------------------------------------------
    # Viewport screenshot
    # ------------------------------------------------------------------

    def _on_capture_viewport(self):
        from edini.ui.viewport import capture_viewport
        b64 = capture_viewport()
        if b64 is None:
            return
        self._screenshot_data = b64
        pixmap = QtGui.QPixmap()
        pixmap.loadFromData(base64.b64decode(b64), "JPEG")
        # Show small preview (shown as a label in action_col area is awkward,
        # we'll just toggle the remove button to indicate presence)
        self._screenshot_remove_btn.setVisible(True)
        self._screenshot_btn.setText("📸")

    def _on_remove_screenshot(self):
        self._screenshot_data = None
        self._screenshot_btn.setText("📷")
        self._screenshot_remove_btn.setVisible(False)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_busy(self, busy: bool):
        self._busy = busy
        self.send_btn.setEnabled(not busy)

    def set_session_id(self, sid: str):
        self._session_id = sid

    def set_request_count(self, count: int):
        self._request_count = count

    def begin_assistant_message(self):
        self._raw_stream_text = ""
        self._streaming = True
        self._pending_thinkings.clear()
        self._pending_tools.clear()
        self._thinking_count = 0
        self._ai_bubble_base = self.timeline_view.toHtml()

    def append_stream_chunk(self, text: str):
        self._raw_stream_text += text
        if len(self._raw_stream_text) >= self.STREAM_FLUSH_CHARS:
            self._flush_stream()
        elif not self._stream_flush_timer.isActive():
            self._stream_flush_timer.start()

    def _flush_stream(self):
        if not self._raw_stream_text:
            return
        a = accent_color()
        escaped = html.escape(self._raw_stream_text)
        rendered = _format_message(escaped)
        bubble = (
            f'<div style="{_bubble_ai_style()}">{rendered}'
            f'<span style="color:{a};">▊</span></div>'
        )
        self.timeline_view.setHtml(self._ai_bubble_base + bubble)
        self._scroll_to_bottom()

    def finish_streaming(self):
        self._streaming = False
        self._stream_flush_timer.stop()
        self.finalize_ai_message()
        self._raw_stream_text = ""

    def add_thinking_step(self, step_num: int, text: str):
        self._thinking_count += 1
        self._pending_thinkings.append(f"{step_num}. {text}")

    def add_tool_card(self, tool_name: str, args: dict, tool_call_id: str = ""):
        self._pending_tools.append({
            "name": tool_name,
            "call_id": tool_call_id,
            "args": args,
            "result": "",
        })

    def set_tool_result(self, tool_call_id: str, result: str):
        for tool in self._pending_tools:
            if tool["call_id"] == tool_call_id:
                tool["result"] = result
                break

    def finalize_ai_message(self):
        """Build complete AI response unit with thinking/tool fold blocks + final reply."""
        parts = []

        # Thinking block (collapsed by default)
        if self._pending_thinkings:
            thinking_text = "\n".join(self._pending_thinkings)
            collapsed = (
                f'<div style="{_thinking_collapsed_style()}" '
                f'onclick="var e=document.getElementById(\'t{self._request_count}\');'
                f'e.style.display=e.style.display==\'none\'?\'block\':\'none\';'
                f'this.innerHTML=this.innerHTML.replace(\'▸\',e.style.display==\'none\'?\'▸\':\'▾\');">'
                f'▸ Thinking ({self._thinking_count} steps)</div>'
            )
            expanded = (
                f'<div id="t{self._request_count}" style="display:none;{_thinking_expanded_style()}">'
                f'<pre style="margin:0;color:#71717a;font-size:{fs(11)};white-space:pre-wrap;'
                f'background:transparent;font-family:inherit;">'
                f'{html.escape(thinking_text)}</pre>'
                f'</div>'
            )
            parts.append(collapsed + expanded)

        # Tool blocks (collapsed by default)
        for i, tool in enumerate(self._pending_tools):
            tid = f"c{self._request_count}_{i}"
            tool_name = html.escape(tool["name"])
            args_str = html.escape(str(tool.get("args", {})))
            result = tool.get("result", "")
            result_str = _format_tool_result(result) if result else "⏳ executing..."

            collapsed = (
                f'<div style="{_tool_collapsed_style()}" '
                f'onclick="var e=document.getElementById(\'{tid}\');'
                f'e.style.display=e.style.display==\'none\'?\'block\':\'none\';'
                f'this.innerHTML=this.innerHTML.replace(\'▸\',e.style.display==\'none\'?\'▸\':\'▾\');">'
                f'▸ 🔧 {tool_name}</div>'
            )
            expanded = (
                f'<div id="{tid}" style="display:none;{_tool_expanded_style()}">'
                f'🔧 <b>{tool_name}</b><br>'
                f'<pre style="margin:2px 0;color:#94a3b8;font-size:{fs(11)};white-space:pre-wrap;'
                f'background:transparent;font-family:inherit;">{args_str}</pre>'
                f'Result: {result_str}'
                f'</div>'
            )
            parts.append(collapsed + expanded)

        # Final reply text
        if self._raw_stream_text:
            escaped = html.escape(self._raw_stream_text)
            rendered = _format_message(escaped)
            parts.append(f'<div style="{_bubble_ai_style()}">{rendered}</div>')

        # Separator
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
        abort_html = (
            f'<div style="text-align:center;color:#f87171;font-size:{fs(11)};'
            f'margin:8px 0;">── Aborted ──</div>'
        )
        self.timeline_view.setHtml(self.timeline_view.toHtml() + abort_html)
        self.set_busy(False)

    def clear_timeline(self):
        self.timeline_view.clear()

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
        """Render a stored assistant message from session history."""
        content = msg.get("content", "")
        thinking = msg.get("thinking", [])
        tools = msg.get("tools", [])

        parts = []

        if thinking:
            thinking_text = "\n".join(thinking)
            parts.append(
                f'<div style="{_thinking_expanded_style()}">'
                f'<pre style="margin:0;color:#71717a;font-size:{fs(11)};'
                f'white-space:pre-wrap;background:transparent;font-family:inherit;">'
                f'{html.escape(thinking_text)}</pre></div>'
            )

        if tools:
            for tool in tools:
                tool_name = html.escape(tool.get("name", ""))
                args_str = html.escape(str(tool.get("args", {})))
                result = tool.get("result", "")
                result_str = _format_tool_result(result) if result else "—"
                parts.append(
                    f'<div style="{_tool_expanded_style()}">'
                    f'🔧 <b>{tool_name}</b><br>'
                    f'<pre style="margin:2px 0;color:#94a3b8;font-size:{fs(11)};'
                    f'white-space:pre-wrap;background:transparent;font-family:inherit;">{args_str}</pre>'
                    f'Result: {result_str}</div>'
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

    # Code blocks with Copy button
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

    # Inline code
    out = re.sub(
        r'`([^`]+)`',
        r'<code style="background:#1a1a24;color:#67e8f9;padding:1px 4px;'
        r'border-radius:3px;font-family:monospace;font-size:11pt;">\1</code>',
        out,
    )

    # Bold
    out = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', out)

    # Newlines
    out = out.replace("\n", "<br>")

    return out


def _format_tool_result(result) -> str:
    """Format a tool execution result for display."""
    if isinstance(result, dict):
        if result.get("success"):
            return "✅ " + html.escape(str(result.get("path", result.get("output", ""))))
        else:
            return "❌ " + html.escape(result.get("error", "Unknown error"))
    if isinstance(result, str):
        return html.escape(result)
    return html.escape(str(result))
