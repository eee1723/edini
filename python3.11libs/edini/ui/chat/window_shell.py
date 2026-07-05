"""ChatWindowShell — three-panel chat skeleton (composer, not base class).

3-panel: left (scope-defined) | center (chat components) | right (ContextPanel).
Accent override applied via objectName-scoped stylesheet for visual diff.
"""
from PySide6 import QtCore, QtWidgets
from edini.ui.theme import fs
from edini.ui.components.timeline_view import _TimelineView as TimelineView
from edini.ui.components.thinking_panel import ThinkingPanel
from edini.ui.components.tool_panel import ToolPanel
from edini.ui.components.input_bar import InputBar
from edini.ui.components.change_tree import ChangeTreeWidget
from edini.ui.components.param_snapshot import ParamSnapshotPanel
from edini.ui.status.context_panel import ContextPanel


def _accent_scope_stylesheet(accent: str, oid: str) -> str:
    """Local-only accent override, scoped by objectName. Doesn't leak to other windows."""
    return f"""
    #{oid} QSplitter::handle:hover {{ background-color:{accent}; }}
    #{oid} QListWidget::item:selected {{ border-left:2px solid {accent}; color:{accent}; }}
    #{oid} QTreeWidget::item:selected {{ border-left:2px solid {accent}; color:{accent}; }}
    #{oid} QProgressBar::chunk {{ background-color:{accent}; }}
    #{oid} QPushButton#PrimaryButton {{ background-color:{accent}; color:#0a0a10; }}
    #{oid} QSlider::handle:horizontal {{ background:{accent}; }}
    """


class ChatWindowShell(QtWidgets.QWidget):
    """3-panel chat window skeleton. Composes components; driven by ScopeConfig."""

    def __init__(self, scope, left_panel=None, parent=None):
        super().__init__(parent)
        self._scope = scope
        if scope.accent_override:
            self.setObjectName(f"ChatShell_{scope.scope_id}")
        self._build(left_panel)

    def _build(self, left_panel):
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ──
        self._header_label = QtWidgets.QLabel(self._build_header_html())
        self._header_label.setStyleSheet(
            f"QLabel {{ color:#e5e5eb; font-size:{fs(13)}; padding:8px 12px; "
            f"background:#0a0a10; border-bottom:1px solid #1e1e2c; }}"
        )
        self._header_label.setTextFormat(QtCore.Qt.RichText)
        root.addWidget(self._header_label)

        # ── 3-panel splitter ──
        self._splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)

        # Left
        self._left_panel = left_panel if left_panel is not None else QtWidgets.QWidget()
        self._splitter.addWidget(self._left_panel)

        # Center
        self._center = self._build_center()
        self._splitter.addWidget(self._center)

        # Right
        self._context_panel = ContextPanel()
        self._splitter.addWidget(self._context_panel)

        for i in range(3):
            self._splitter.setCollapsible(i, False)
        self._splitter.setSizes([240, 720, 400])
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setStretchFactor(2, 0)
        root.addWidget(self._splitter, 1)

        # Accent override
        if self._scope.accent_override:
            self.setStyleSheet(_accent_scope_stylesheet(
                self._scope.accent_override, self.objectName()))

    def _build_header_html(self) -> str:
        title = self._scope.window_title
        if self._scope.header_badge:
            return (f"<b>{title}</b>"
                    f" <span style='color:#a1a1aa;font-size:{fs(10)};'>"
                    f"{self._scope.header_badge}</span>")
        return f"<b>{title}</b>"

    def _build_center(self) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)

        self._timeline = TimelineView()
        lay.addWidget(self._timeline, 1)

        self._thinking_panel = ThinkingPanel()
        lay.addWidget(self._thinking_panel)

        self._tool_panel = ToolPanel()
        lay.addWidget(self._tool_panel)

        if self._scope.show_change_tree:
            self._change_tree = ChangeTreeWidget()
            lay.addWidget(self._change_tree)
        else:
            self._change_tree = None

        if self._scope.show_param_snapshot:
            self._param_snapshot = ParamSnapshotPanel()
            lay.addWidget(self._param_snapshot)
        else:
            self._param_snapshot = None

        self._input_bar = InputBar(show_attachment_bar=self._scope.show_attachment_bar)
        lay.addWidget(self._input_bar)
        return w

    def header_text(self) -> str:
        return self._header_label.text()

    # ── Component accessors (for driver signal binding) ──
    @property
    def timeline(self): return self._timeline
    @property
    def thinking_panel(self): return self._thinking_panel
    @property
    def tool_panel(self): return self._tool_panel
    @property
    def input_bar(self): return self._input_bar
    @property
    def change_tree(self): return self._change_tree
    @property
    def context_panel(self): return self._context_panel
    @property
    def center_widget(self): return self._center
    @property
    def left_panel(self): return self._left_panel
    @property
    def param_snapshot(self): return self._param_snapshot

    def replace_left(self, new_widget):
        """Swap the left panel widget at runtime (e.g., placeholder → version list)."""
        idx = self._splitter.indexOf(self._left_panel)
        self._splitter.replaceWidget(idx, new_widget)
        self._left_panel.setParent(None)
        self._left_panel.deleteLater()
        self._left_panel = new_widget
        self._left_panel.setObjectName("LeftPanel")
