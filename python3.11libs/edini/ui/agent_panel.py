"""AgentPanel — Chat timeline (QScrollArea + widgets) + collapsible panels."""
import html
import os
import re
import subprocess
import sys
from PySide6 import QtCore, QtGui, QtWidgets
from edini.ui.theme import accent_color, fs
from edini.media_manager import (
    MediaItem, MediaSource, capture_viewport,
    from_files, from_clipboard, from_mime_data,
    mime_has_images, MAX_ATTACHMENTS, clipboard_has_image,
)
from edini.ui.image_attachment import ImageAttachmentWidget
from edini.ui.vision_overlay import VisionDescriptionBubble
from edini import screenshots


# ═══════════════════════════════════════════════════════════════════════
# Style helpers (unchanged)
# ═══════════════════════════════════════════════════════════════════════

def _user_bubble_bg() -> str:
    return '#1a3a5c'

def _ai_bubble_bg() -> str:
    return '#1a1a24'

def _user_bubble_style() -> str:
    return (
        f'color:#e5e5eb;font-size:{fs(12)};line-height:1.45;'
        f'padding:8px 14px;background:{_user_bubble_bg()};border-radius:8px;'
    )

def _ai_bubble_style() -> str:
    return (
        f'color:#e5e5eb;font-size:{fs(12)};line-height:1.45;'
        f'padding:8px 14px;background:{_ai_bubble_bg()};border-radius:8px;'
    )

def _thinking_collapsed_style() -> str:
    a = accent_color()
    return (
        f'color:#a1a1aa;font-size:{fs(10)};cursor:pointer;'
        f'background:rgba(0,188,212,0.06);padding:4px 8px;'
        f'border-radius:4px;margin:4px 32px 4px 0;display:block;'
        f'border-left:2px solid {a};'
    )

def _thinking_expanded_style() -> str:
    a = accent_color()
    return (
        f'color:#71717a;font-size:{fs(10)};display:block;'
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

class _ClickableCard(QtWidgets.QFrame):
    """A card that opens a file/image on click. Reliable mouse handling."""

    def __init__(self, open_path: str, tooltip: str = "", parent=None):
        super().__init__(parent)
        self._open_path = open_path
        self.setCursor(QtCore.Qt.PointingHandCursor)
        if tooltip:
            self.setToolTip(tooltip)

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            _open_image_file(self._open_path)
        super().mouseReleaseEvent(event)


class _UserBubble(QtWidgets.QFrame):
    """Right-aligned user message bubble — text + optional image references."""
    def __init__(self, text: str, images: list[dict] | None = None, parent=None):
        super().__init__(parent)
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(2)

        # Text bubble (right-aligned with 48px left margin)
        text_frame = QtWidgets.QFrame()
        text_layout = QtWidgets.QHBoxLayout(text_frame)
        text_layout.setContentsMargins(48, 0, 0, 0)
        text_layout.setSpacing(0)

        self._label = QtWidgets.QLabel(html.escape(text))
        self._label.setWordWrap(True)
        self._label.setTextFormat(QtCore.Qt.RichText)
        self._label.setTextInteractionFlags(
            QtCore.Qt.TextSelectableByMouse
        )
        self._label.setStyleSheet(
            f"QLabel {{ "
            f"color:#e5e5eb; font-size:{fs(12)}; line-height:1.45; "
            f"padding:8px 14px; background:{_user_bubble_bg()}; "
            f"border-radius:10px; border:none; "
            f"}}"
        )
        self._label.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        text_layout.addWidget(self._label)
        outer.addWidget(text_frame)

        # Image references (if any) — clickable chips below text
        if images:
            self._add_image_refs(outer, images)
        else:
            pass

        self.setStyleSheet("QFrame { background: transparent; border: none; }")

    def _add_image_refs(self, outer: QtWidgets.QVBoxLayout, images: list[dict]):
        """Add clickable thumbnail previews below the text bubble."""
        img_frame = QtWidgets.QFrame()
        img_frame.setStyleSheet("QFrame { background: transparent; border: none; }")
        img_layout = QtWidgets.QHBoxLayout(img_frame)
        img_layout.setContentsMargins(54, 2, 8, 2)
        img_layout.setSpacing(6)
        img_layout.addStretch(1)

        for img_meta in images:
            filename = img_meta.get("filename", "image")
            size_kb = img_meta.get("size_bytes", 0) / 1024
            size_str = f"{size_kb:.0f}KB" if size_kb < 1024 else f"{size_kb/1024:.1f}MB"
            cache_path = img_meta.get("cache_path", "")
            b64_fallback = img_meta.get("_b64_pending", "")
            open_path = cache_path if cache_path and os.path.isfile(cache_path) else b64_fallback

            # Card container — QFrame for proper child widget rendering
            card = _ClickableCard(open_path, f"点击查看原图 — {filename} ({size_str})")
            card.setFixedSize(100, 90)
            card.setStyleSheet(f"""
                _ClickableCard {{
                    background: #0e0e15;
                    border: 1px solid #252540;
                    border-radius: 4px;
                }}
                _ClickableCard:hover {{
                    border-color: #4a4a6a;
                    background: #14141e;
                }}
            """)

            card_layout = QtWidgets.QVBoxLayout(card)
            card_layout.setContentsMargins(2, 2, 2, 0)
            card_layout.setSpacing(1)

            # Thumbnail image — use QLabel with pixmap scaled to fill
            thumb = QtWidgets.QLabel()
            thumb.setFixedSize(96, 68)
            thumb.setAlignment(QtCore.Qt.AlignCenter)
            thumb.setScaledContents(False)
            thumb.setStyleSheet(
                "QLabel { background: #06060c; border-radius: 2px; border: none; }"
            )
            pixmap = _load_thumb_pixmap(open_path)
            if pixmap and not pixmap.isNull():
                scaled = pixmap.scaled(
                    96, 68,
                    QtCore.Qt.AspectRatioMode.IgnoreAspectRatio,
                    QtCore.Qt.TransformationMode.SmoothTransformation,
                )
                thumb.setPixmap(scaled)
            else:
                thumb.setText("🖼️")
            card_layout.addWidget(thumb)

            # Filename label
            name_label = QtWidgets.QLabel(_truncate_name(filename, 13))
            name_label.setStyleSheet(
                f"QLabel {{ color:#a1a1aa; font-size:{fs(9)}; border:none; background:transparent; }}"
            )
            name_label.setAlignment(QtCore.Qt.AlignCenter)
            card_layout.addWidget(name_label)

            img_layout.addWidget(card)

        outer.addWidget(img_frame)


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
        self._label.setTextInteractionFlags(
            QtCore.Qt.TextSelectableByMouse
        )
        self._label.setStyleSheet(
            f"QLabel {{ "
            f"color:#e5e5eb; font-size:{fs(12)}; line-height:1.45; "
            f"padding:8px 14px; background:{_ai_bubble_bg()}; "
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
        """Update with full accumulated text during streaming. Uses light formatter."""
        self._raw_text = full_text
        rendered = _format_lite(full_text)
        wrapped = f'<div style="{_ai_bubble_style()}">{rendered}</div>'
        self._label.setText(wrapped)

    def get_raw_text(self) -> str:
        return self._raw_text

    def finalize(self):
        """Called when streaming is complete. Applies full Markdown formatting."""
        rendered = _format_full(self._raw_text)
        wrapped = f'<div style="{_ai_bubble_style()}">{rendered}</div>'
        self._label.setText(wrapped)

    def set_stored_content(self, content: str):
        """Set content from a stored message. Applies full Markdown formatting."""
        self._raw_text = content
        rendered = _format_full(content)
        wrapped = f'<div style="{_ai_bubble_style()}">{rendered}</div>'
        self._label.setText(wrapped)

    @staticmethod
    def _on_link(url: str):
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
    - Drag-selecting text inside a bubble auto-scrolls the viewport when the
      cursor approaches the top/bottom edge, so the selection can extend into
      content that was originally off-screen.
    """

    PIN_THRESHOLD = 12  # px from bottom to consider "at bottom"
    AUTO_SCROLL_MARGIN = 30  # px from viewport edge that triggers auto-scroll
    AUTO_SCROLL_INTERVAL = 30  # ms between auto-scroll ticks
    AUTO_SCROLL_MAX_SPEED = 18  # max px per tick when cursor is far past edge

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

        # Auto-scroll-during-text-selection
        self._auto_scroll_timer = QtCore.QTimer(self)
        self._auto_scroll_timer.setInterval(self.AUTO_SCROLL_INTERVAL)
        self._auto_scroll_timer.timeout.connect(self._auto_scroll_tick)
        self._drag_source_label: QtWidgets.QLabel | None = None
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    # ── Auto-scroll during text drag selection ──

    def eventFilter(self, watched, event):
        """Start the auto-scroll timer when the user mouse-presses on a
        text-selectable label inside this timeline, stop it on release.
        The timer ticks handle the actual scroll.
        """
        if event is not None:
            et = event.type()
            if et == QtCore.QEvent.MouseButtonPress and \
                    event.button() == QtCore.Qt.LeftButton:
                if (isinstance(watched, QtWidgets.QLabel)
                        and self._is_descendant(watched)
                        and self._scroll_range_available()):
                    self._drag_source_label = watched
                    self._auto_scroll_timer.start()
            elif et == QtCore.QEvent.MouseButtonRelease and \
                    event.button() == QtCore.Qt.LeftButton:
                self._drag_source_label = None
                self._auto_scroll_timer.stop()
        return super().eventFilter(watched, event)

    def _scroll_range_available(self) -> bool:
        sb = self.verticalScrollBar()
        return sb.maximum() > sb.minimum()

    def _auto_scroll_tick(self):
        """Scroll toward the cursor when it is in the margin zone; then
        synthesize a MouseMove on the label that received the press so its
        text-selection logic extends into the newly visible content."""
        if not (QtGui.QGuiApplication.mouseButtons()
                & QtCore.Qt.LeftButton):
            self._drag_source_label = None
            self._auto_scroll_timer.stop()
            return
        sb = self.verticalScrollBar()
        if sb.maximum() <= sb.minimum():
            self._auto_scroll_timer.stop()
            return

        cursor_global = QtGui.QCursor.pos()
        tl = self.viewport().mapToGlobal(QtCore.QPoint(0, 0))
        local_y = cursor_global.y() - tl.y()
        viewport_h = self.viewport().height()
        margin = self.AUTO_SCROLL_MARGIN

        old_value = sb.value()
        new_value = old_value

        if local_y < margin:
            distance = margin - max(local_y, 0)
            delta = max(1, min(self.AUTO_SCROLL_MAX_SPEED,
                               int(distance * 0.4) + 1))
            new_value = max(sb.minimum(), old_value - delta)
        elif local_y > viewport_h - margin:
            distance = min(local_y, viewport_h) - (viewport_h - margin)
            delta = max(1, min(self.AUTO_SCROLL_MAX_SPEED,
                               int(distance * 0.4) + 1))
            new_value = min(sb.maximum(), old_value + delta)

        if new_value == old_value:
            return

        self._programmatic_scroll = True
        sb.setValue(new_value)
        self._programmatic_scroll = False

        # Tell the label that received the press that the cursor "moved"
        # relative to its widget coords (which it did, because the widget
        # scrolled under a stationary cursor). This makes the text selection
        # extend into the content that just scrolled into view.
        label = self._drag_source_label
        if label is None:
            return
        try:
            from shiboken6 import isValid
            if not isValid(label):
                self._drag_source_label = None
                return
        except ImportError:
            pass
        if not self._is_descendant(label):
            return
        local = label.mapFromGlobal(cursor_global)
        evt = QtGui.QMouseEvent(
            QtCore.QEvent.MouseMove,
            QtCore.QPointF(local),
            QtCore.QPointF(cursor_global),
            QtCore.Qt.LeftButton,
            QtCore.Qt.LeftButton,
            QtCore.Qt.NoModifier,
        )
        QtWidgets.QApplication.postEvent(label, evt)

    def _is_descendant(self, widget: QtWidgets.QWidget) -> bool:
        p = widget
        while p is not None:
            if p is self:
                return True
            p = p.parentWidget()
        return False

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

# ═══════════════════════════════════════════════════════════════════════
# AgentPanel
# ═══════════════════════════════════════════════════════════════════════

class AgentPanel(QtWidgets.QWidget):
    submit_requested = QtCore.Signal(str, object)   # text, images
    stop_requested = QtCore.Signal()
    abort_requested = QtCore.Signal()
    sig_eval_completed = QtCore.Signal(str, float)  # session_id, total_score

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
        self._THINKING_COLLAPSED_H = 24
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
        self._TOOL_PANEL_COLLAPSED_H = 24
        self._TOOL_PANEL_EXPANDED_H = 200
        self._tool_panel.setFixedHeight(self._TOOL_PANEL_COLLAPSED_H)
        root.addWidget(self._tool_panel)

        # ── Change Tree Panel (collapsible) ──
        from edini.ui.change_tree_widget import ChangeTreeWidget
        self.change_tree_widget = ChangeTreeWidget()
        root.addWidget(self.change_tree_widget)

        # ── Attachment preview bar ──
        self._attachment_bar = ImageAttachmentWidget()
        root.addWidget(self._attachment_bar)

        # ── Input row ──
        input_row = QtWidgets.QHBoxLayout()
        input_row.setSpacing(8)
        self.input_edit = QtWidgets.QPlainTextEdit(self)
        self.input_edit.setPlaceholderText("描述你希望 Edini 完成的任务... (Enter 发送)")
        self.input_edit.setFixedHeight(68)
        input_row.addWidget(self.input_edit, 1)

        # ── Action column (right side) ──
        action_col = QtWidgets.QVBoxLayout()
        action_col.setSpacing(6)

        # ── Multimodal toolbar row ──
        a = accent_color()
        _mm_btn_style = f"""
            QPushButton {{
                background: #1a1a2e;
                color: #c0c0d0;
                border: 1px solid #2a2a40;
                border-radius: 6px;
                padding: 4px 10px;
                font-size: {fs(12)};
                font-weight: 500;
            }}
            QPushButton:hover {{
                background: #252540;
                border-color: {a}66;
                color: #e5e5eb;
            }}
            QPushButton:pressed {{
                background: #2a2a48;
                border-color: {a}99;
            }}
        """

        toolbar_row = QtWidgets.QHBoxLayout()
        toolbar_row.setSpacing(6)

        self._screenshot_btn = QtWidgets.QPushButton("📷 截图")
        self._screenshot_btn.setToolTip("截取 Houdini Scene Viewer 视窗画面")
        self._screenshot_btn.setMinimumHeight(34)
        self._screenshot_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self._screenshot_btn.setStyleSheet(_mm_btn_style)
        self._screenshot_btn.clicked.connect(self._on_capture_viewport)
        toolbar_row.addWidget(self._screenshot_btn)

        self._file_pick_btn = QtWidgets.QPushButton("📁 上传")
        self._file_pick_btn.setToolTip("从磁盘选择图片 (png, jpg, gif, webp, bmp)")
        self._file_pick_btn.setMinimumHeight(34)
        self._file_pick_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self._file_pick_btn.setStyleSheet(_mm_btn_style)
        self._file_pick_btn.clicked.connect(self._on_pick_files)
        toolbar_row.addWidget(self._file_pick_btn)

        action_col.addLayout(toolbar_row)

        # ── Spacer between toolbar and action controls ──
        action_col.addSpacing(4)

        # ── Chat-only checkbox ──
        from edini.ui.styled_checkbox import StyledCheckBox
        self.chat_only_check = StyledCheckBox("仅对话", self)
        action_col.addWidget(self.chat_only_check, alignment=QtCore.Qt.AlignRight)

        # ── Execute / Abort button ──
        self._action_btn = QtWidgets.QPushButton("执行")
        self._action_btn.setObjectName("PrimaryButton")
        self._action_btn.setMinimumWidth(90)
        self._action_btn.setMinimumHeight(34)
        self._action_btn.clicked.connect(self._on_action_btn)
        action_col.addWidget(self._action_btn)
        action_col.addStretch(1)

        input_row.addLayout(action_col)
        root.addLayout(input_row)

    def _bind_events(self):
        self.input_edit.installEventFilter(self)
        # Confirm setup

        # Drag-drop on input_edit
        self.input_edit.setAcceptDrops(True)
        self.input_edit.dragEnterEvent = self._on_drag_enter
        self.input_edit.dragMoveEvent = self._on_drag_move
        self.input_edit.dropEvent = self._on_drop

        # Right-click context menu — must monkey-patch because
        # Houdini's Qt may block ContextMenu events from the event filter.
        self.input_edit.setContextMenuPolicy(QtCore.Qt.DefaultContextMenu)
        self.input_edit.contextMenuEvent = self._on_context_menu

    def eventFilter(self, watched, event):
        if watched is self.input_edit and event is not None:
            ev_type = int(event.type())

            # ── Right-click context menu: intercept paste when image on clipboard ──
            if ev_type == int(QtCore.QEvent.ContextMenu):
                has_img = clipboard_has_image()
                if has_img:
                    menu = QtWidgets.QMenu(self.input_edit)
                    paste_img = menu.addAction("📋 粘贴图片到附件栏")
                    paste_img.triggered.connect(self._paste_image_from_clipboard)
                    menu.addSeparator()
                    paste_text = menu.addAction("粘贴文本")
                    paste_text.triggered.connect(self._context_paste_text)
                    menu.addSeparator()
                    select_all = menu.addAction("全选")
                    select_all.triggered.connect(self.input_edit.selectAll)
                    self._context_menu = menu
                    result = menu.exec(event.globalPos())
                    self._context_menu = None
                    return True
                # No image on clipboard — let default context menu handle text paste
                return False

            if ev_type == int(QtCore.QEvent.KeyPress):
                key = int(event.key())
                modifiers = event.modifiers()
                if key == int(QtCore.Qt.Key_Escape):
                    if self._busy:
                        self._on_abort()
                    return True
                if key in (int(QtCore.Qt.Key_Return), int(QtCore.Qt.Key_Enter)):
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
                if key == int(QtCore.Qt.Key_V):
                    if modifiers & QtCore.Qt.ControlModifier:
                        has_img = clipboard_has_image()
                        if has_img:
                            if self._attachment_bar.is_full():
                                self.add_error(f"最多 {MAX_ATTACHMENTS} 张图片")
                            else:
                                item = from_clipboard()
                                if item is not None:
                                    ok = self._attachment_bar.add(item)
                                else:
                                    pass
                            return True
                        else:
                            pass
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

        # Collect all images from attachment bar
        images: list[dict] = []
        attachment_items = self._attachment_bar.items()
        for item in attachment_items:
            img_info = {
                "type": "image",
                "data": item.base64,
                "mimeType": item.mime_type,
                "filename": item.filename,
                "source": item.source.value,
            }
            images.append(img_info)

        self._attachment_bar.clear()

        self.submit_requested.emit(text, images if images else None)

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
        item = capture_viewport()
        if item is None:
            self._screenshot_btn.setText("❌ 失败")
            QtCore.QTimer.singleShot(2500, lambda: self._screenshot_btn.setText("📷 截图"))
            self.add_error("截图失败 — 请查看 Houdini Console 获取详情")
            return
        if self._attachment_bar.is_full():
            self.add_error(f"最多 {MAX_ATTACHMENTS} 张图片，请先移除一些")
            return
        self._save_viewshot_to_disk(item)
        ok = self._attachment_bar.add(item)
        if ok:
            self._screenshot_btn.setText("📸 ✓")
            QtCore.QTimer.singleShot(1500, lambda: self._screenshot_btn.setText("📷 截图"))

    def _save_viewshot_to_disk(self, item: MediaItem):
        """Also persist viewport screenshots under $HIP/Edini_screenshots/<task>/."""
        import base64 as _b64
        session_path = getattr(self, "_current_session_path", "") or screenshots.current_session()
        if not session_path or not item.base64:
            return
        ext = ".jpg" if "jpeg" in item.mime_type or "jpg" in item.mime_type else ".png"
        try:
            target = screenshots.next_filename(session_path, "viewport", ext)
            raw = _b64.b64decode(item.base64)
            target.write_bytes(raw)
        except Exception:
            pass

    def _on_pick_files(self):
        """Open file dialog to select image files."""
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self,
            "Select Images",
            "",
            "Images (*.png *.jpg *.jpeg *.gif *.webp *.bmp);;All Files (*)",
        )
        if not paths:
            return
        items = from_files(paths)
        added = 0
        for item in items:
            if self._attachment_bar.is_full():
                break
            if self._attachment_bar.add(item):
                added += 1
        if added == 0 and self._attachment_bar.is_full():
            self.add_error(f"最多 {MAX_ATTACHMENTS} 张图片")

    def _paste_image_from_clipboard(self):
        """Paste image from clipboard (called from right-click context menu)."""
        if self._attachment_bar.is_full():
            self.add_error(f"最多 {MAX_ATTACHMENTS} 张图片")
            return
        item = from_clipboard()
        if item is not None:
            ok = self._attachment_bar.add(item)
        else:

            pass
    def _context_paste_text(self):
        """Paste text into input_edit (called from right-click context menu).

        Uses QTimer.singleShot to defer the paste until the context menu
        is fully dismissed and focus is restored to the input_edit.
        """
        QtCore.QTimer.singleShot(0, self._do_context_paste_text)

    def _do_context_paste_text(self):
        self.input_edit.setFocus(QtCore.Qt.OtherFocusReason)
        self.input_edit.paste()

    def _on_drag_enter(self, event):
        if mime_has_images(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def _on_drag_move(self, event):
        if mime_has_images(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def _on_drop(self, event):
        items = from_mime_data(event.mimeData())
        for item in items:
            if self._attachment_bar.is_full():
                break
            self._attachment_bar.add(item)
        if items:
            event.acceptProposedAction()
        else:
            event.ignore()

    def _on_context_menu(self, event):
        """Right-click context menu handler — monkey-patched onto input_edit."""
        has_img = clipboard_has_image()
        if has_img:
            menu = QtWidgets.QMenu(self.input_edit)
            paste_img = menu.addAction("📋 粘贴图片到附件栏")
            paste_img.triggered.connect(self._paste_image_from_clipboard)
            menu.addSeparator()
            paste_text = menu.addAction("粘贴文本")
            paste_text.triggered.connect(self._context_paste_text)
            menu.addSeparator()
            select_all = menu.addAction("全选")
            select_all.triggered.connect(self.input_edit.selectAll)
            self._context_menu = menu
            result = menu.exec(event.globalPos())
            self._context_menu = None
        else:
            # Let QPlainTextEdit show its default context menu
            QtWidgets.QPlainTextEdit.contextMenuEvent(self.input_edit, event)

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
        # Trigger background evaluation
        self._trigger_background_eval()

    # ── Tool cards ──

    def add_tool_card(self, tool_name: str, args: dict, tool_call_id: str = ""):
        self._add_tool_card_ui(tool_name, args, tool_call_id)

    def set_tool_result(self, tool_call_id: str, result: str):
        self._update_tool_card_result(tool_call_id, result, True)

    # ── Inline capture images and descriptions ──

    def add_inline_capture_image(self, filepath: str, width: int = 0, height: int = 0):
        """Show a captured viewport/network screenshot inline in the timeline."""
        resolved = os.path.abspath(filepath) if not os.path.isabs(filepath) else filepath
        if not os.path.exists(resolved):
            return
        widget = _CaptureImageWidget(resolved, width, height)
        self.timeline_view.add_widget(widget)

    def add_inline_description(self, text: str):
        """Show a vision model description bubble inline in the timeline."""
        if not text.strip():
            return
        bubble = _DescriptionBubble(text)
        self.timeline_view.add_widget(bubble)

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

    def _append_user_message(self, text: str, images: list[dict] | None = None):
        """Append a user message bubble to the timeline."""
        self.timeline_view.add_widget(_UserBubble(text, images))

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
        # A failed model turn is persisted with stopReason="error" and an
        # empty content array. Surface the errorMessage so the user can see
        # why a turn produced no output (e.g. insufficient quota, bad params)
        # instead of an empty timeline.
        if msg.get("stopReason") == "error" and msg.get("errorMessage"):
            self.add_error(msg["errorMessage"])
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
        self._trigger_background_eval()
        self.set_busy(False)

    def _trigger_background_eval(self):
        """Run evaluator in background thread after session ends."""
        session_path = getattr(self, '_current_session_path', None)
        _debug_log(str(session_path or ""), "trigger_eval", f"session_path={session_path!r}")
        if not session_path:
            _debug_log("", "trigger_eval", "no session path, returning")
            return
        import threading
        t = threading.Thread(
            target=self._run_evaluation,
            args=(session_path,),
            daemon=True,
        )
        t.start()

    def _run_evaluation(self, session_path: str):
        """Evaluate a single session in background thread."""
        import os
        _debug_log(session_path, "eval_start", f"path={session_path}")
        try:
            from edini.eval.log_parser import LogParser
            from edini.eval.evaluator import EvaluatorPipeline
            from edini.eval.store import EvalStore

            if not os.path.exists(session_path):
                _debug_log(session_path, "eval_fail", "session file not found")
                return

            session = LogParser.parse(session_path)
            if not session:
                _debug_log(session_path, "eval_fail", "LogParser returned None")
                return
            store = EvalStore()
            if store.has_evaluated(session.session_id):
                _debug_log(session_path, "eval_skip", f"already evaluated: {session.session_id[:20]}")
                return
            try:
                result = EvaluatorPipeline().evaluate(session)
            except Exception as inner_e:
                _debug_log(session_path, "eval_exception_detail",
                           f"EvaluatorPipeline.evaluate() failed: {inner_e}")
                import traceback
                _debug_log(session_path, "eval_traceback", traceback.format_exc())
                # Fallback: deterministic-only evaluation (skip LLM judge)
                _debug_log(session_path, "eval_retry", "retrying with force_no_judge=True")
                result = EvaluatorPipeline(force_judge=False).evaluate(session)
                # Patch the judge-based scores to None if they failed
                if result.tool_accuracy is None:
                    result.tool_accuracy = 0.5
                if result.task_completion is None:
                    result.task_completion = 0.5
            store.save_result(session.session_id, result)
            _debug_log(session_path, "eval_done",
                       f"saved {session.session_id[:20]} score={result.total_score:.3f}")
            self.sig_eval_completed.emit(session.session_id, result.total_score)
        except Exception as e:
            import traceback
            _debug_log(session_path, "eval_exception", str(e))
            _debug_log(session_path, "eval_traceback", traceback.format_exc())



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

# ═══════════════════════════════════════════════════════════════════════
# Image helpers
# ═══════════════════════════════════════════════════════════════════════

_SOURCE_ICON_MAP = {
    "viewport": "📸",
    "pick": "📁",
    "drag": "📁",
    "paste": "📋",
    "tool": "🔧",
}


def _source_icon(source: str) -> str:
    return _SOURCE_ICON_MAP.get(source, "🖼️")


def _truncate_name(name: str, max_len: int) -> str:
    if len(name) <= max_len:
        return name
    return name[:max_len - 1] + "…"


def _load_thumb_pixmap(path_or_b64: str) -> QtGui.QPixmap | None:
    """Load a QPixmap from a file path or base64 string.

    Returns None on any failure (safe to call in Houdini's PySide6).
    """
    if not path_or_b64:
        return None
    try:
        pixmap = QtGui.QPixmap()
        if os.path.isfile(path_or_b64):
            pixmap.load(path_or_b64)
        else:
            import base64 as _b64
            data = _b64.b64decode(path_or_b64)
            pixmap.loadFromData(data)
        if pixmap.isNull():
            return None
        return pixmap
    except Exception:
        return None


def _open_image_file(path: str):
    """Open an image file in the OS default viewer.

    If path is not a valid file path, treats it as base64 data and
    writes to a temp file first.
    """
    if not path:
        return

    actual_path = path
    if not os.path.isfile(path):
        # Try to decode as base64 (fallback before cache is written)
        try:
            import base64 as _b64
            import tempfile
            data = _b64.b64decode(path)
            fd, tmp = tempfile.mkstemp(suffix=".jpg", prefix="edini_view_")
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            actual_path = tmp
        except Exception:
            return

    try:
        if sys.platform == "win32":
            os.startfile(actual_path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", actual_path])
        else:
            subprocess.Popen(["xdg-open", actual_path])
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════
# Markdown rendering now lives in edini.ui.components.markdown.
# Re-exported here for backward compatibility during staged migration.
# ═══════════════════════════════════════════════════════════════════════

from edini.ui.components.markdown import (
    _format_lite, _format_full, _DarkRenderer,
)


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


# ==========================================================================
# Inline Capture Image Widget
# ==========================================================================

def _debug_log(session_path: str, tag: str, msg: str):
    """Write debug log to temp file for diagnostics."""
    import os, datetime
    log_file = os.path.join(
        os.environ.get("TEMP", "/tmp"), "edini_eval_debug.log"
    )
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.datetime.now().isoformat()}] [{tag}] {msg}\n")
    except Exception:
        pass

class _CaptureImageWidget(QtWidgets.QFrame):
    """Shows a captured viewport/network screenshot inline in the timeline."""

    def __init__(self, filepath: str, width: int = 0, height: int = 0, parent=None):
        super().__init__(parent)
        self._filepath = filepath

        self.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.setMaximumWidth(500)
        self.setStyleSheet("""
            _CaptureImageWidget {
                background-color: #1a1a24;
                border-radius: 8px;
                border: 1px solid #2a2a3c;
                margin: 4px 0;
            }
        """)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        # Label
        filename = os.path.basename(filepath)
        label = QtWidgets.QLabel(f"📷 <b>Viewport Capture</b> <span style='color:#71717a;'>{filename}</span>")
        label.setStyleSheet("color: #a1a1aa; font-size: 11px; border: none; background: transparent;")
        layout.addWidget(label)

        # Image
        pixmap = QtGui.QPixmap(filepath)
        if pixmap.isNull():
            err_label = QtWidgets.QLabel("⚠️ Image not found")
            err_label.setStyleSheet("color: #ef4444; font-size: 11px; border: none;")
            layout.addWidget(err_label)
            return

        max_w = 480
        if pixmap.width() > max_w:
            pixmap = pixmap.scaledToWidth(max_w, QtCore.Qt.SmoothTransformation)

        img_label = QtWidgets.QLabel()
        img_label.setPixmap(pixmap)
        img_label.setAlignment(QtCore.Qt.AlignCenter)
        img_label.setStyleSheet("border: none; background: transparent;")
        img_label.setCursor(QtCore.Qt.PointingHandCursor)
        img_label.setToolTip("Click to open full-size image")
        img_label.mousePressEvent = lambda e: self._open_full()
        layout.addWidget(img_label)

        if width and height:
            info = QtWidgets.QLabel(f"<span style='color:#52525b;'>{width}×{height}</span>")
            info.setStyleSheet("color: #52525b; font-size: 10px; border: none;")
            layout.addWidget(info)

    def _open_full(self):
        """Open the image with the system default viewer."""
        import os as _os
        _os.startfile(self._filepath)


# ==========================================================================
# Description Bubble (for vision model responses)
# ==========================================================================

class _DescriptionBubble(QtWidgets.QFrame):
    """Shows a vision model description inline in the timeline."""

    def __init__(self, text: str, parent=None):
        super().__init__(parent)

        self.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.setMaximumWidth(500)
        self.setStyleSheet("""
            _DescriptionBubble {
                background-color: #1a2420;
                border-radius: 8px;
                border: 1px solid #2a3c30;
                margin: 4px 0;
            }
        """)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(4)

        header = QtWidgets.QLabel("🔍 <b>Image Description</b>")
        header.setStyleSheet("color: #80c080; font-size: 11px; border: none; background: transparent;")
        layout.addWidget(header)

        # Clean up the description text
        description = text.strip()
        # Remove common prefixes like "The image shows" redundancy
        escaped = html.escape(description)
        body = QtWidgets.QLabel(escaped)
        body.setWordWrap(True)
        body.setStyleSheet("color: #a0c0a0; font-size: 12px; border: none; background: transparent;")
        layout.addWidget(body)

