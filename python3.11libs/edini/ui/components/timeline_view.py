"""TimelineView — scrollable chat bubble container with smart auto-scroll.

Pinned-to-bottom auto-scrolls new content; scrolling up pauses it.
Drag-selecting text inside a bubble auto-scrolls when cursor nears edges.
"""
from PySide6 import QtCore, QtGui, QtWidgets


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
