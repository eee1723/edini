"""AgentPanel — Chat timeline (QScrollArea + widgets) + collapsible panels."""
import html
import re
import base64
from PySide6 import QtCore, QtGui, QtWidgets
from edini.ui.theme import accent_color, fs


# ═══════════════════════════════════════════════════════════════════════
# Style helpers (unchanged)
# ═══════════════════════════════════════════════════════════════════════

def _user_bubble_bg() -> str:
    return '#1a3a5c'

def _ai_bubble_bg() -> str:
    return '#1a1a24'

def _user_bubble_style() -> str:
    return (
        f'color:#e5e5eb;font-size:{fs(12)};line-height:1.55;'
        f'padding:8px 14px;background:{_user_bubble_bg()};border-radius:8px;'
    )

def _ai_bubble_style() -> str:
    return (
        f'color:#e5e5eb;font-size:{fs(12)};line-height:1.55;'
        f'padding:8px 14px;background:{_ai_bubble_bg()};border-radius:8px;'
    )

def _thinking_collapsed_style() -> str:
    a = accent_color()
    return (
        f'color:#a1a1aa;font-size:{fs(11)};cursor:pointer;'
        f'background:rgba(0,188,212,0.06);padding:4px 8px;'
        f'border-radius:4px;margin:4px 32px 4px 0;display:block;'
        f'border-left:2px solid {a};'
    )

def _thinking_expanded_style() -> str:
    a = accent_color()
    return (
        f'color:#71717a;font-size:{fs(11)};display:block;'
        f'background:#0e0e15;padding:4px 8px;'
        f'border-left:2px solid {a};margin:4px 32px 4px 8px;'
    )

def _separator_style() -> str:
    return (
        f'text-align:center;color:#52525b;font-size:{fs(10)};'
        f'margin:10px 0;border-top:1px solid #2a2a3c;padding-top:6px;'
    )


# ═══════════════════════════════════════════════════════════════════════
# Tool Card Widget (unchanged)
# ═══════════════════════════════════════════════════════════════════════

class _ToolCardWidget(QtWidgets.QFrame):
    """A single collapsible tool call card. Added/updated in real-time."""

    def __init__(self, tool_name: str, args: dict, tool_call_id: str, parent=None):
        super().__init__(parent)
        self._tool_call_id = tool_call_id
        self._expanded = False

        self.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.setStyleSheet(f"""
            _ToolCardWidget {{
                background: rgba(0,188,212,0.03);
                border: 1px solid #181830;
                border-radius: 4px;
            }}
            _ToolCardWidget:hover {{
                background: rgba(0,188,212,0.06);
                border-color: #253545;
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

        args_str = _format_args(args)
        self._args_label = QtWidgets.QLabel(args_str)
        self._args_label.setWordWrap(True)
        self._args_label.setStyleSheet(f"color:#78909c;font-size:{fs(10)};font-family:monospace;border:none;")
        detail_layout.addWidget(self._args_label)

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


# ═══════════════════════════════════════════════════════════════════════
# Timeline — QScrollArea + widget-based
# ═══════════════════════════════════════════════════════════════════════

class _UserBubble(QtWidgets.QFrame):
    """Right-aligned user message bubble — fills available width with left margin."""
    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(48, 0, 0, 0)  # 48px left margin (right-aligned look)
        layout.setSpacing(0)

        self._label = QtWidgets.QLabel(html.escape(text))
        self._label.setWordWrap(True)
        self._label.setTextFormat(QtCore.Qt.PlainText)
        self._label.setStyleSheet(
            f"QLabel {{ "
            f"color:#e5e5eb; font-size:{fs(12)}; line-height:1.55; "
            f"padding:10px 16px; background:{_user_bubble_bg()}; "
            f"border-radius:10px; border:none; "
            f"}}"
        )
        self._label.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        layout.addWidget(self._label)

        self.setStyleSheet("QFrame { background: transparent; border: none; }")


class _AiBubble(QtWidgets.QFrame):
    """Left-aligned AI message bubble — fills available width with right margin."""
    def __init__(self, rich_html: str = "", parent=None):
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 48, 0)  # 48px right margin (left-aligned look)
        layout.setSpacing(0)

        self._label = QtWidgets.QLabel()
        self._label.setWordWrap(True)
        self._label.setTextFormat(QtCore.Qt.RichText)
        self._label.setOpenExternalLinks(False)
        self._label.linkActivated.connect(self._on_link)
        self._label.setStyleSheet(
            f"QLabel {{ "
            f"color:#e5e5eb; font-size:{fs(12)}; line-height:1.55; "
            f"padding:10px 16px; background:{_ai_bubble_bg()}; "
            f"border-radius:10px; border:none; "
            f"}}"
        )
        self._label.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        layout.addWidget(self._label)

        self._raw_text = ""
        if rich_html:
            wrapped = f'<div style="{_ai_bubble_style()}">{rich_html}</div>'
            self._label.setText(wrapped)

        self.setStyleSheet("QFrame { background: transparent; border: none; }")

    def update_streaming(self, full_text: str):
        """Update with full accumulated text during streaming. Re-renders markdown."""
        self._raw_text = full_text
        rendered = _format_message(html.escape(full_text))
        wrapped = f'<div style="{_ai_bubble_style()}">{rendered}</div>'
        self._label.setText(wrapped)

    def get_raw_text(self) -> str:
        return self._raw_text

    def finalize(self):
        """Called when streaming is complete."""
        rendered = _format_message(html.escape(self._raw_text))
        wrapped = f'<div style="{_ai_bubble_style()}">{rendered}</div>'
        self._label.setText(wrapped)

    def set_stored_content(self, content: str):
        """Set content from a stored message (already plain text, no streaming)."""
        self._raw_text = content
        rendered = _format_message(html.escape(content))
        wrapped = f'<div style="{_ai_bubble_style()}">{rendered}</div>'
        self._label.setText(wrapped)

    @staticmethod
    def _on_link(url: str):
        if url.startswith('edini:copy:'):
            try:
                encoded = url[len('edini:copy:'):]
                text = base64.b64decode(encoded).decode('utf-8')
                QtWidgets.QApplication.clipboard().setText(text)
            except Exception:
                pass


class _Separator(QtWidgets.QFrame):
    """Centered separator line between message rounds."""
    def __init__(self, text: str = "──", parent=None):
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(0)
        layout.addStretch(1)
        label = QtWidgets.QLabel(text)
        label.setStyleSheet(
            f"QLabel {{ color:#52525b; font-size:{fs(10)}; "
            f"background:transparent; border:none; }}"
        )
        layout.addWidget(label)
        layout.addStretch(1)
        self.setStyleSheet(
            f"QFrame {{ background: transparent; border: none; "
            f"border-top: 1px solid #2a2a3c; }}"
        )


class _ErrorBanner(QtWidgets.QFrame):
    """Error message banner."""
    def __init__(self, message: str, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(0)
        layout.addStretch(1)
        label = QtWidgets.QLabel(f"⚠️ {html.escape(message)}")
        label.setWordWrap(True)
        label.setStyleSheet(
            f"QLabel {{ color:#f87171; font-size:{fs(11)}; "
            f"background:transparent; border:none; }}"
        )
        layout.addWidget(label)
        layout.addStretch(1)
        self.setStyleSheet(
            "QFrame { background: rgba(239,68,68,0.08); "
            "border-left: 3px solid #ef4444; border-radius: 4px; "
            "margin: 4px 16px; }"
        )


class _TimelineView(QtWidgets.QScrollArea):
    """Chat timeline using QScrollArea + widgets for reliable smart scrolling.

    Key behavior:
    - When pinned to bottom, new content auto-scrolls to keep the latest visible.
    - When user scrolls up to read history, auto-scroll pauses.
    - User can re-pin by scrolling all the way to the bottom.
    """

    PIN_THRESHOLD = 12  # px from bottom to consider "at bottom"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setWidgetResizable(True)
        self.setStyleSheet(
            "QScrollArea { background-color: #0e0e18; border: none; }"
        )

        # Container widget holding all message widgets
        self._container = QtWidgets.QWidget()
        self._container.setObjectName("TimelineContainer")
        self._container.setStyleSheet(
            "QWidget#TimelineContainer { background: transparent; }"
        )
        self._layout = QtWidgets.QVBoxLayout(self._container)
        self._layout.setContentsMargins(8, 8, 8, 8)
        self._layout.setSpacing(2)
        self._layout.setAlignment(QtCore.Qt.AlignTop)
        # Bottom spacer keeps content at top when few messages
        self._layout.addStretch(1)
        self.setWidget(self._container)

        # Smart scroll state
        self._pinned_to_bottom = True
        self._programmatic_scroll = False

        # Track scroll changes
        sb = self.verticalScrollBar()
        sb.rangeChanged.connect(self._on_range_changed)
        sb.valueChanged.connect(self._on_value_changed)

    # ── Smart scroll ──

    def _on_range_changed(self, _min: int, max_val: int):
        """Content resized. If pinned, scroll to new bottom."""
        if self._pinned_to_bottom:
            self._programmatic_scroll = True
            sb = self.verticalScrollBar()
            sb.setValue(max_val)
            self._programmatic_scroll = False

    def _on_value_changed(self, value: int):
        """Detect user scroll events to unpin or re-pin."""
        if self._programmatic_scroll:
            return
        sb = self.verticalScrollBar()
        at_bottom = value >= sb.maximum() - self.PIN_THRESHOLD
        self._pinned_to_bottom = at_bottom

    def _scroll_to_bottom(self):
        """Force scroll to bottom and re-pin."""
        sb = self.verticalScrollBar()
        self._programmatic_scroll = True
        sb.setValue(sb.maximum())
        self._programmatic_scroll = False
        self._pinned_to_bottom = True

    # ── Public API ──

    def add_widget(self, widget: QtWidgets.QWidget):
        """Insert a message widget before the bottom spacer."""
        idx = self._layout.count() - 1  # before the stretch
        self._layout.insertWidget(idx, widget)
        if self._pinned_to_bottom:
            QtCore.QTimer.singleShot(0, self._scroll_to_bottom)

    def clear_all(self):
        """Remove all message widgets, keep spacer."""
        while self._layout.count() > 1:
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._pinned_to_bottom = True

    def widget_count(self) -> int:
        """Number of message widgets (excluding spacer)."""
        return self._layout.count() - 1

    def remove_last_widget(self):
        """Remove the last message widget (for cancel_current_stream)."""
        count = self._layout.count()
        if count <= 1:
            return
        idx = count - 2  # last widget before stretch
        item = self._layout.takeAt(idx)
        if item.widget():
            item.widget().deleteLater()

    def ensure_pinned(self):
        """Re-enable auto-scroll and scroll to bottom."""
        self._pinned_to_bottom = True
        self._scroll_to_bottom()

    @property
    def is_pinned(self) -> bool:
        return self._pinned_to_bottom


# ═══════════════════════════════════════════════════════════════════════
# Type Toggle Badge (unchanged)
# ═══════════════════════════════════════════════════════════════════════

class _TypeToggleBadge(QtWidgets.QLabel):
    """Clickable badge showing '铁律' or '知识', toggles on click."""

    def __init__(self, is_rule: bool, index: int, callback, parent=None):
        super().__init__(parent)
        self._is_rule = is_rule
        self._index = index
        self._callback = callback
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setToolTip("点击切换铁律 / 知识")
        self.setFixedWidth(36)
        self.setAlignment(QtCore.Qt.AlignCenter)
        self._update_style()

    def _update_style(self):
        text = "铁律" if self._is_rule else "知识"
        color = "#a78bfa" if self._is_rule else "#80cbc4"
        bg = "rgba(167,139,250,0.15)" if self._is_rule else "rgba(128,203,196,0.12)"
        self.setText(text)
        self.setStyleSheet(
            f"color:{color};font-size:{fs(9)};font-weight:600;"
            f"background:{bg};padding:1px 4px;border-radius:3px;border:1px solid {color}44;"
        )

    def mousePressEvent(self, event):
        self._is_rule = not self._is_rule
        self._update_style()
        self._callback(self._index, self._is_rule)

    @property
    def is_rule(self) -> bool:
        return self._is_rule


# ═══════════════════════════════════════════════════════════════════════
# AgentPanel
# ═══════════════════════════════════════════════════════════════════════

class AgentPanel(QtWidgets.QWidget):
    submit_requested = QtCore.Signal(str, object)   # text, images
    stop_requested = QtCore.Signal()
    abort_requested = QtCore.Signal()
    knowledge_accepted = QtCore.Signal(list)        # list of accepted items
    knowledge_rejected = QtCore.Signal()            # all rejected

    STREAM_FLUSH_CHARS = 80
    STREAM_FLUSH_INTERVAL_MS = 80

    def __init__(self, parent=None):
        super().__init__(parent)
        self._busy = False
        self._stream_segments: list[dict] = []     # [{type: text|thinking, content: str}]
        self._current_text = ""                     # current paragraph (may be cleared by think flush)
        self._streaming_full_text = ""              # NEVER cleared — full accumulated stream text
        self._streaming = False
        self._request_count = 0
        self._session_id = ""

        # Streaming bubble — the AiBubble widget being built live
        self._streaming_bubble: _AiBubble | None = None

        # Thinking
        self._thinking_count = 0
        self._thinking_buf = ""
        self._thinking_full = ""
        self._thinking_buf_timer = QtCore.QTimer(self)
        self._thinking_buf_timer.setSingleShot(True)
        self._thinking_buf_timer.setInterval(600)
        self._thinking_buf_timer.timeout.connect(self._flush_thinking_buf)

        # Tool cards
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

        # ── Timeline (QScrollArea + widgets) ──
        self.timeline_view = _TimelineView()
        root.addWidget(self.timeline_view, 1)

        # ── Thinking Panel (collapsible, below timeline) ──
        self._thinking_panel = QtWidgets.QFrame()
        self._thinking_panel.setStyleSheet(f"""
            QFrame {{
                background: #0a0a12;
                border-top: 1px solid #1c1c2a;
            }}
        """)
        tp_layout = QtWidgets.QVBoxLayout(self._thinking_panel)
        tp_layout.setContentsMargins(10, 3, 10, 4)
        tp_layout.setSpacing(0)

        think_header = QtWidgets.QHBoxLayout()
        think_header.setContentsMargins(0, 0, 0, 0)
        self._thinking_toggle = QtWidgets.QLabel("▸ Thinking (0)")
        self._thinking_toggle.setCursor(QtCore.Qt.PointingHandCursor)
        self._thinking_toggle.setStyleSheet(f"color:#4a4a5a;font-size:{fs(10)};border:none;padding:1px 0;")
        self._thinking_toggle.mousePressEvent = self._toggle_thinking_panel
        think_header.addWidget(self._thinking_toggle)
        think_header.addStretch()
        tp_layout.addLayout(think_header)

        self._thinking_view = QtWidgets.QTextEdit()
        self._thinking_view.setReadOnly(True)
        self._thinking_view.setStyleSheet(
            f"QTextEdit {{ background: transparent; color: #8b8fa8; font-size:{fs(11)}; border: none; }}"
        )
        self._thinking_view.setVisible(False)
        tp_layout.addWidget(self._thinking_view)

        self._thinking_panel_expanded = False
        self._THINKING_COLLAPSED_H = 20
        self._THINKING_EXPANDED_H = 200
        self._thinking_panel.setFixedHeight(self._THINKING_COLLAPSED_H)
        root.addWidget(self._thinking_panel)

        # ── Tool Call Panel (collapsible, below timeline) ──
        self._tool_panel = QtWidgets.QFrame()
        self._tool_panel.setStyleSheet(f"""
            QFrame {{
                background: #0a0a12;
                border-top: 1px solid #1c1c2a;
                border-bottom: 1px solid #1c1c2a;
            }}
            _ToolCardWidget {{
                background: rgba(0,188,212,0.04);
                border: 1px solid #1a1a2e;
                border-radius: 4px;
                margin: 1px 0;
            }}
            _ToolCardWidget:hover {{
                background: rgba(0,188,212,0.08);
                border-color: #253545;
            }}
        """)
        tool_panel_layout = QtWidgets.QVBoxLayout(self._tool_panel)
        tool_panel_layout.setContentsMargins(10, 3, 10, 4)
        tool_panel_layout.setSpacing(0)

        tool_header = QtWidgets.QHBoxLayout()
        tool_header.setContentsMargins(0, 0, 0, 0)
        self._tool_toggle = QtWidgets.QLabel("▸ Tool Calls (0)")
        self._tool_toggle.setCursor(QtCore.Qt.PointingHandCursor)
        self._tool_toggle.setStyleSheet(f"color:#4a4a5a;font-size:{fs(10)};border:none;padding:1px 0;")
        self._tool_toggle.mousePressEvent = self._toggle_tool_panel
        tool_header.addWidget(self._tool_toggle)
        tool_header.addStretch()
        tool_panel_layout.addLayout(tool_header)

        self._tool_scroll = QtWidgets.QScrollArea()
        self._tool_scroll.setWidgetResizable(True)
        self._tool_scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self._tool_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self._tool_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self._tool_container = QtWidgets.QWidget()
        self._tool_container.setStyleSheet("background: transparent;")
        self._tool_layout = QtWidgets.QVBoxLayout(self._tool_container)
        self._tool_layout.setAlignment(QtCore.Qt.AlignTop)
        self._tool_layout.setSpacing(1)
        self._tool_layout.setContentsMargins(0, 4, 0, 0)
        self._tool_layout.addStretch()
        self._tool_scroll.setWidget(self._tool_container)

        self._tool_scroll.setVisible(False)
        tool_panel_layout.addWidget(self._tool_scroll)

        self._tool_panel_expanded = False
        self._TOOL_PANEL_COLLAPSED_H = 20
        self._TOOL_PANEL_EXPANDED_H = 200
        self._tool_panel.setFixedHeight(self._TOOL_PANEL_COLLAPSED_H)
        root.addWidget(self._tool_panel)

        # ── Knowledge Extraction Area ──
        self._knowledge_area = QtWidgets.QFrame()
        self._knowledge_area.setStyleSheet(f"""
            QFrame {{
                background: #0a0a12;
                border: 1px solid #1e2e2e;
                border-radius: 4px;
            }}
        """)
        ka_layout = QtWidgets.QVBoxLayout(self._knowledge_area)
        ka_layout.setContentsMargins(10, 4, 10, 6)
        ka_layout.setSpacing(4)

        ka_header = QtWidgets.QHBoxLayout()
        ka_header.setContentsMargins(0, 0, 0, 0)
        self._knowledge_title = QtWidgets.QLabel("🧠 知识提取")
        self._knowledge_title.setStyleSheet(f"color:#80cbc4;font-size:{fs(11)};font-weight:600;border:none;")
        ka_header.addWidget(self._knowledge_title)
        ka_header.addStretch()
        self._knowledge_accept_all = QtWidgets.QPushButton("全部接受")
        self._knowledge_accept_all.setStyleSheet(_knowledge_btn_style("#16a34a"))
        ka_header.addWidget(self._knowledge_accept_all)
        self._knowledge_reject_all = QtWidgets.QPushButton("全部放弃")
        self._knowledge_reject_all.setStyleSheet(_knowledge_btn_style("#555"))
        ka_header.addWidget(self._knowledge_reject_all)
        ka_layout.addLayout(ka_header)

        self._knowledge_scroll = QtWidgets.QScrollArea()
        self._knowledge_scroll.setWidgetResizable(True)
        self._knowledge_scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self._knowledge_scroll.setMaximumHeight(240)
        self._knowledge_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self._knowledge_items_widget = QtWidgets.QWidget()
        self._knowledge_items_widget.setStyleSheet("background: transparent;")
        self._knowledge_items_layout = QtWidgets.QVBoxLayout(self._knowledge_items_widget)
        self._knowledge_items_layout.setContentsMargins(0, 0, 0, 0)
        self._knowledge_items_layout.setSpacing(3)
        self._knowledge_items_layout.addStretch()
        self._knowledge_scroll.setWidget(self._knowledge_items_widget)
        ka_layout.addWidget(self._knowledge_scroll)

        self._knowledge_area.setVisible(False)
        root.addWidget(self._knowledge_area)

        # ── Change Tree Panel (collapsible) ──
        from edini.ui.change_tree_widget import ChangeTreeWidget
        self.change_tree_widget = ChangeTreeWidget()
        root.addWidget(self.change_tree_widget)

        # ── Input row ──
        input_row = QtWidgets.QHBoxLayout()
        self.input_edit = QtWidgets.QPlainTextEdit(self)
        self.input_edit.setPlaceholderText("描述你希望 Edini 完成的任务... (Enter 发送)")
        self.input_edit.setFixedHeight(64)
        input_row.addWidget(self.input_edit, 1)

        action_col = QtWidgets.QVBoxLayout()
        action_col.setSpacing(4)

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
        self._knowledge_accept_all.clicked.connect(self._on_knowledge_accept_all)
        self._knowledge_reject_all.clicked.connect(self._on_knowledge_reject_all)

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
        self._streaming_full_text = ""
        self._streaming = True
        self._thinking_count = 0

        # Reset panels to collapsed state
        self._clear_tool_cards()
        self._clear_thinking()
        self._tool_panel_expanded = False
        self._thinking_panel_expanded = False
        self._tool_scroll.setVisible(False)
        self._thinking_view.setVisible(False)
        self._tool_toggle.setText("▸ Tool Calls (0)")
        self._thinking_toggle.setText("▸ Thinking (0)")
        self._tool_panel.setFixedHeight(self._TOOL_PANEL_COLLAPSED_H)
        self._thinking_panel.setFixedHeight(self._THINKING_COLLAPSED_H)

        # Collapse change tree during conversation
        self.change_tree_widget.collapse()

        images = None
        if self._screenshot_data:
            images = [{"type": "image/jpeg", "data": self._screenshot_data}]
            self._on_remove_screenshot()

        self.submit_requested.emit(text, images)

    # ------------------------------------------------------------------
    # Tool Call Panel (unchanged)
    # ------------------------------------------------------------------

    def _toggle_tool_panel(self, event=None):
        self._tool_panel_expanded = not self._tool_panel_expanded
        self._tool_scroll.setVisible(self._tool_panel_expanded)
        arrow = "▾" if self._tool_panel_expanded else "▸"
        count = len(self._tool_cards)
        self._tool_toggle.setText(f"{arrow} Tool Calls ({count})")
        if self._tool_panel_expanded:
            self._tool_panel.setFixedHeight(self._TOOL_PANEL_EXPANDED_H)
        else:
            self._tool_panel.setFixedHeight(self._TOOL_PANEL_COLLAPSED_H)

    def _collapse_tool_panel(self):
        """Collapse tool panel if currently expanded."""
        if self._tool_panel_expanded:
            self._toggle_tool_panel()

    def _add_tool_card_ui(self, tool_name: str, args: dict, tool_call_id: str):
        card = _ToolCardWidget(tool_name, args, tool_call_id)
        self._tool_layout.insertWidget(self._tool_layout.count() - 1, card)
        self._tool_cards[tool_call_id] = card
        self._tool_scroll.verticalScrollBar().setValue(
            self._tool_scroll.verticalScrollBar().maximum())
        count = len(self._tool_cards)
        arrow = "▾" if self._tool_panel_expanded else "▸"
        self._tool_toggle.setText(f"{arrow} Tool Calls ({count})")
        if not self._tool_panel_expanded and count == 1:
            self._toggle_tool_panel()

    def _update_tool_card_result(self, tool_call_id: str, result_text: str, success: bool = True):
        card = self._tool_cards.get(tool_call_id)
        if card:
            card.set_result(result_text, success)

    def _clear_tool_cards(self):
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

    def get_raw_stream_text(self) -> str:
        """Get the raw accumulated text of the current streaming response."""
        if self._streaming_bubble:
            return self._streaming_bubble.get_raw_text()
        parts = []
        for seg in self._stream_segments:
            if seg["type"] == "text":
                parts.append(seg["content"])
        if self._current_text:
            parts.append(self._current_text)
        return "\n".join(parts)

    def cancel_current_stream(self):
        """Cancel the current streaming response without rendering separator."""
        self._streaming = False
        self._stream_flush_timer.stop()
        if self._streaming_bubble:
            self.timeline_view.remove_last_widget()
            self._streaming_bubble = None
        self._stream_segments.clear()
        self._current_text = ""
        self._streaming_full_text = ""
        self._thinking_buf = ""
        self._clear_tool_cards()
        self._clear_thinking()

    # ------------------------------------------------------------------
    # Knowledge Extraction Area (unchanged)
    # ------------------------------------------------------------------

    def show_extraction_results(self, items: list[dict]):
        self._clear_knowledge_items()
        self._pending_knowledge_items = items
        for i, item in enumerate(items):
            card = self._make_knowledge_card(item, i)
            self._knowledge_items_layout.insertWidget(
                self._knowledge_items_layout.count() - 1, card)
        rule_count = sum(1 for it in items if it.get("type") == "rule")
        entry_count = len(items) - rule_count
        parts = []
        if rule_count:
            parts.append(f"{rule_count} 条铁律")
        if entry_count:
            parts.append(f"{entry_count} 条知识")
        self._knowledge_title.setText(f"🧠 知识提取 — {' + '.join(parts)}")
        self._knowledge_area.setVisible(True)

    def _clear_knowledge_items(self):
        for i in reversed(range(self._knowledge_items_layout.count())):
            item = self._knowledge_items_layout.itemAt(i)
            if item and item.widget():
                item.widget().deleteLater()
        self._pending_knowledge_items = []

    def hide_extraction_results(self):
        self._clear_knowledge_items()
        self._knowledge_area.setVisible(False)

    def _make_knowledge_card(self, item: dict, index: int) -> QtWidgets.QWidget:
        card = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(card)
        layout.setContentsMargins(6, 3, 6, 3)
        layout.setSpacing(6)
        is_rule = item.get("type") == "rule"
        badge = _TypeToggleBadge(is_rule, index, self._on_toggle_item_type)
        layout.addWidget(badge)
        cat_label = QtWidgets.QLabel(item.get("category", ""))
        cat_label.setStyleSheet(f"color:#71717a;font-size:{fs(9)};border:none;")
        cat_label.setFixedWidth(32)
        layout.addWidget(cat_label)
        content_text = QtWidgets.QWidget()
        cl = QtWidgets.QVBoxLayout(content_text)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(1)
        title = QtWidgets.QLabel(item.get("title", ""))
        title.setStyleSheet(f"color:#e5e5eb;font-size:{fs(11)};font-weight:600;border:none;")
        title.setWordWrap(True)
        cl.addWidget(title)
        detail = QtWidgets.QLabel(item.get("content", "")[:120])
        detail.setStyleSheet(f"color:#94a3b8;font-size:{fs(10)};border:none;")
        detail.setWordWrap(True)
        cl.addWidget(detail)
        layout.addWidget(content_text, 1)
        accept_btn = QtWidgets.QPushButton("✓")
        accept_btn.setFixedSize(26, 26)
        accept_btn.setStyleSheet(_knowledge_btn_style("#16a34a"))
        accept_btn.clicked.connect(lambda checked=False, idx=index: self._on_knowledge_accept_one(idx))
        layout.addWidget(accept_btn)
        reject_btn = QtWidgets.QPushButton("✕")
        reject_btn.setFixedSize(26, 26)
        reject_btn.setStyleSheet(_knowledge_btn_style("#555"))
        reject_btn.clicked.connect(lambda checked=False, idx=index: self._on_knowledge_reject_one(idx))
        layout.addWidget(reject_btn)
        return card

    def _on_knowledge_accept_one(self, index: int):
        if 0 <= index < len(self._pending_knowledge_items):
            item = self._pending_knowledge_items.pop(index)
            self.knowledge_accepted.emit([item])
            self._refresh_knowledge_cards()

    def _on_knowledge_reject_one(self, index: int):
        if 0 <= index < len(self._pending_knowledge_items):
            self._pending_knowledge_items.pop(index)
            self._refresh_knowledge_cards()

    def _on_toggle_item_type(self, index: int, is_rule: bool):
        if 0 <= index < len(self._pending_knowledge_items):
            self._pending_knowledge_items[index]["type"] = "rule" if is_rule else "entry"

    def _on_knowledge_accept_all(self):
        items = list(self._pending_knowledge_items)
        self.knowledge_accepted.emit(items)
        self.hide_extraction_results()

    def _on_knowledge_reject_all(self):
        self.knowledge_rejected.emit()
        self.hide_extraction_results()

    def _refresh_knowledge_cards(self):
        if not self._pending_knowledge_items:
            self.hide_extraction_results()
            return
        self._clear_knowledge_items()
        for i, item in enumerate(self._pending_knowledge_items):
            card = self._make_knowledge_card(item, i)
            self._knowledge_items_layout.insertWidget(
                self._knowledge_items_layout.count() - 1, card)

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

    # ── Streaming ──

    def begin_assistant_message(self):
        """Prepare for a new assistant response."""
        self._stream_segments.clear()
        self._current_text = ""
        self._streaming_full_text = ""
        self._thinking_buf = ""
        self._streaming = True
        self._thinking_count = 0
        self._streaming_bubble = None  # Will be created on first chunk

    def append_stream_chunk(self, text: str):
        """Stream a chunk of text. Creates or updates the streaming bubble."""
        if self._thinking_buf.strip():
            self._flush_thinking_buf()
        self._current_text += text
        self._streaming_full_text += text

        # Create the streaming bubble on first content
        if self._streaming_bubble is None and self._streaming_full_text.strip():
            self._streaming_bubble = _AiBubble()
            self.timeline_view.add_widget(self._streaming_bubble)

        # Update bubble in-place with FULL accumulated text
        if self._streaming_bubble:
            self._streaming_bubble.update_streaming(self._streaming_full_text)

        # Update live thinking panel
        if self._thinking_buf:
            self._update_live_thinking()
            if not self._thinking_panel_expanded and not self._thinking_full:
                self._auto_expand_thinking()

        if len(self._current_text) >= self.STREAM_FLUSH_CHARS:
            self._flush_stream()
        elif not self._stream_flush_timer.isActive():
            self._stream_flush_timer.start()

    def _flush_stream(self):
        """No-op in widget mode — updates happen in append_stream_chunk."""
        pass

    def finish_streaming(self):
        """Finalize the streaming response."""
        self._streaming = False
        self._stream_flush_timer.stop()
        if self._thinking_buf.strip():
            self._flush_thinking_buf()

        # Finalize the bubble
        if self._streaming_bubble:
            self._streaming_bubble.finalize()
            self._streaming_bubble = None
        # Add round-end separator
        self.timeline_view.add_widget(_Separator("── 本轮结束 ──"))
        # Auto-collapse panels after completion
        self._collapse_tool_panel()
        self._collapse_thinking_panel()

    # ── Tool cards ──

    def add_tool_card(self, tool_name: str, args: dict, tool_call_id: str = ""):
        self._add_tool_card_ui(tool_name, args, tool_call_id)

    def set_tool_result(self, tool_call_id: str, result: str):
        self._update_tool_card_result(tool_call_id, result, True)

    # ── Thinking ──

    def add_thinking_step(self, step_num: int, text: str):
        self._thinking_count += 1
        clean = _clean_thinking(text)
        if self._thinking_buf:
            sep = "" if clean.startswith((" ", "\n", ",", ".", "!", "?", "，", "。", "、")) else " "
            self._thinking_buf += sep + clean
        else:
            self._thinking_buf = clean
        if '\n\n' in self._thinking_buf:
            parts = re.split(r'\n\n+', self._thinking_buf)
            for para in parts[:-1]:
                if para.strip():
                    self._stream_segments.append({"type": "thinking", "content": para.strip()})
            self._thinking_buf = parts[-1]
        # Update thinking panel view in real-time as thinking arrives
        self._update_live_thinking()
        if not self._thinking_panel_expanded and not self._thinking_full:
            self._auto_expand_thinking()

    def _flush_thinking_buf(self):
        if not self._thinking_buf.strip():
            return
        if self._current_text.strip():
            self._stream_segments.append({"type": "text", "content": self._current_text})
            self._current_text = ""
        paragraphs = re.split(r'\n\n+', self._thinking_buf.strip())
        for para in paragraphs:
            if para.strip():
                self._append_thinking_text(para.strip())
        self._thinking_buf = ""
        self._update_live_thinking()

    # ── Messages ──

    def _append_user_message(self, text: str):
        """Append a user message bubble to the timeline."""
        self.timeline_view.add_widget(_UserBubble(text))

    def _append_assistant_message(self, text: str):
        """Append a non-streaming assistant message."""
        bubble = _AiBubble()
        bubble.set_stored_content(text)
        self.timeline_view.add_widget(bubble)
        self.timeline_view.add_widget(_Separator("──"))

    def _render_stored_assistant_message(self, msg: dict):
        """Render a stored assistant message (from loaded history)."""
        content = msg.get("content", "")
        thinking = msg.get("thinking", [])
        for t in thinking:
            if t.strip():
                self._append_thinking_text(t.strip())
        if content:
            bubble = _AiBubble()
            bubble.set_stored_content(content)
            self.timeline_view.add_widget(bubble)
        self.timeline_view.add_widget(_Separator("──"))

    def add_error(self, message: str):
        """Show an error banner."""
        self.timeline_view.add_widget(_ErrorBanner(message))

    def show_aborted(self):
        """Show 'aborted' marker."""
        self._clear_tool_cards()
        self._clear_thinking()
        # Remove streaming bubble if present (remove_last_widget handles deleteLater)
        if self._streaming_bubble:
            self.timeline_view.remove_last_widget()
            self._streaming_bubble = None
        self.timeline_view.add_widget(_Separator("── 已中止 ──"))
        self._collapse_tool_panel()
        self._collapse_thinking_panel()
        self.set_busy(False)

    def clear_timeline(self):
        """Clear all messages from the timeline."""
        self.timeline_view.clear_all()
        self._clear_tool_cards()
        self._clear_thinking()
        self._streaming_bubble = None
        self._stream_segments.clear()
        self._current_text = ""
        self._streaming_full_text = ""

    # ------------------------------------------------------------------
    # Thinking Panel (unchanged)
    # ------------------------------------------------------------------

    def _toggle_thinking_panel(self, event=None):
        self._thinking_panel_expanded = not self._thinking_panel_expanded
        self._thinking_view.setVisible(self._thinking_panel_expanded)
        arrow = "▾" if self._thinking_panel_expanded else "▸"
        paragraphs = self._thinking_full.count('\n\n') + 1 if self._thinking_full else 0
        self._thinking_toggle.setText(f"{arrow} Thinking ({paragraphs} ¶)")
        if self._thinking_panel_expanded:
            self._thinking_panel.setFixedHeight(self._THINKING_EXPANDED_H)
        else:
            self._thinking_panel.setFixedHeight(self._THINKING_COLLAPSED_H)

    def _auto_expand_thinking(self):
        if not self._thinking_panel_expanded:
            self._toggle_thinking_panel()

    def _collapse_thinking_panel(self):
        """Collapse thinking panel if currently expanded."""
        if self._thinking_panel_expanded:
            self._toggle_thinking_panel()

    def _append_thinking_text(self, text: str):
        if not self._thinking_full:
            self._thinking_full = text
        else:
            self._thinking_full += "\n\n" + text
        display = html.escape(self._thinking_full).replace("\n\n", "<br><br>").replace("\n", "<br>")
        self._thinking_view.setHtml(
            f'<div style="color:#8b8fa8;font-size:{fs(11)};line-height:1.5;">{display}</div>'
        )
        self._thinking_view.verticalScrollBar().setValue(
            self._thinking_view.verticalScrollBar().maximum())
        paragraphs = self._thinking_full.count('\n\n') + 1 if self._thinking_full else 0
        arrow = "▾" if self._thinking_panel_expanded else "▸"
        self._thinking_toggle.setText(f"{arrow} Thinking ({paragraphs} ¶)")

    def _update_live_thinking(self):
        if not self._thinking_buf:
            return
        live = html.escape(self._thinking_buf).replace("\n", "<br>")
        if self._thinking_full:
            base = html.escape(self._thinking_full).replace("\n\n", "<br><br>").replace("\n", "<br>")
            display = f'{base}<br><br>{live}'
        else:
            display = live
        self._thinking_view.setHtml(
            f'<div style="color:#8b8fa8;font-size:{fs(11)};line-height:1.5;">{display}'
            f'<span style="color:#a78bfa;">▊</span></div>'
        )
        self._thinking_view.verticalScrollBar().setValue(
            self._thinking_view.verticalScrollBar().maximum())

    def _clear_thinking(self):
        self._thinking_full = ""
        self._thinking_view.clear()
        self._thinking_toggle.setText("▸ Thinking (0)")
        if self._thinking_panel_expanded:
            self._thinking_view.setVisible(True)


# ═══════════════════════════════════════════════════════════════════════
# Formatting helpers (unchanged)
# ═══════════════════════════════════════════════════════════════════════

def _format_message(text: str) -> str:
    """Convert text with markdown-ish syntax to HTML for QLabel rich text."""
    out = text

    def _code_block_replacer(m):
        code_raw = m.group(2)
        code_escaped = html.escape(code_raw)
        encoded = base64.b64encode(code_raw.encode('utf-8')).decode('ascii')
        return (
            '<div style="position:relative;margin:4px 0;">'
            f'<a href="edini:copy:{encoded}" '
            'style="position:absolute;right:4px;top:4px;background:#2a2a3c;'
            'color:#a1a1aa;text-decoration:none;border-radius:3px;padding:2px 8px;'
            'font-size:10pt;">'
            '📋 Copy</a>'
            '<pre style="background:#0e0e15;color:#d4d4d4;padding:8px;'
            'border-radius:4px;font-family:monospace;font-size:11pt;'
            'overflow-x:auto;margin:0;padding-top:24px;"><code>' + code_escaped + '</code></pre>'
            '</div>'
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
    if re.match(r'^(\d+\.\s+\w+\s*)+$', text):
        return re.sub(r'\d+\.\s+', '', text).strip()
    return text


def _format_args(args: dict) -> str:
    if not args:
        return ""
    parts = []
    for k, v in args.items():
        parts.append(f"<b>{html.escape(k)}</b>: {html.escape(str(v))}")
    return "  ·  ".join(parts)


def _format_tool_result_short(result: str, success: bool) -> str:
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


def _expand_hex(h: str) -> str:
    if len(h) == 4:
        return f"#{h[1]}{h[1]}{h[2]}{h[2]}{h[3]}{h[3]}"
    if len(h) == 5:
        return f"#{h[1]}{h[1]}{h[2]}{h[2]}{h[3]}{h[3]}{h[4]}{h[4]}"
    return h


def _lighter(h: str, a: float) -> str:
    h = _expand_hex(h)
    r, g, b = int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)
    return f"#{min(255,int(r+(255-r)*a)):02x}{min(255,int(g+(255-g)*a)):02x}{min(255,int(b+(255-b)*a)):02x}"


def _darker(h: str, a: float) -> str:
    h = _expand_hex(h)
    r, g, b = int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)
    return f"#{max(0,int(r*(1-a))):02x}{max(0,int(g*(1-a))):02x}{max(0,int(b*(1-a))):02x}"


def _knowledge_btn_style(color: str) -> str:
    return f"""
        QPushButton {{
            background: {color};
            color: #e5e5eb;
            border: none;
            border-radius: 3px;
            font-size: {fs(11)};
            font-weight: 600;
        }}
        QPushButton:hover {{ background: {_lighter(color, 0.15)}; }}
        QPushButton:pressed {{ background: {_darker(color, 0.15)}; }}
    """
