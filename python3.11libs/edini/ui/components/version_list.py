"""NodeVersionList — left panel showing a node's session versions.

Each version = one Pi session (core_path::vN). Lists version number, first
user message summary, and metadata (time · tokens). Emits version_created /
version_selected signals for the driver to wire.

Layering rule: pure UI component. No `hou`, no RpcClient — emits signals only.
"""
from PySide6 import QtCore, QtWidgets
from edini.ui.theme import fs
from edini.ui.components.version_naming import next_version


class _VersionItem(QtWidgets.QFrame):
    """A single version row in the list."""
    clicked = QtCore.Signal(int)   # version number

    def __init__(self, version: int, summary: str, meta: str, current: bool = False):
        super().__init__()
        self._version = version
        self._current = current
        self.setFixedHeight(56)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self._update_style()

        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(2)

        top = QtWidgets.QHBoxLayout()
        top.setSpacing(6)
        ver_lbl = QtWidgets.QLabel(f"<b>v{version}</b>")
        ver_lbl.setStyleSheet(f"color:{'#f59e0b' if current else '#e5e5eb'};"
                              f"font-size:{fs(12)};border:none;")
        top.addWidget(ver_lbl)
        if current:
            cur = QtWidgets.QLabel("◀ current")
            cur.setStyleSheet(f"color:#f59e0b;font-size:{fs(9)};border:none;")
            top.addWidget(cur)
        top.addStretch()
        lay.addLayout(top)

        sum_lbl = QtWidgets.QLabel(summary[:50] if summary else "(empty)")
        sum_lbl.setStyleSheet(f"color:#a1a1aa;font-size:{fs(10)};border:none;")
        sum_lbl.setWordWrap(False)
        lay.addWidget(sum_lbl)

        meta_lbl = QtWidgets.QLabel(meta or "")
        meta_lbl.setStyleSheet(f"color:#52525b;font-size:{fs(9)};border:none;")
        lay.addWidget(meta_lbl)

    def _update_style(self):
        if self._current:
            self.setStyleSheet(
                "QFrame { background: rgba(245,158,11,0.08); "
                "border-left: 2px solid #f59e0b; border-radius: 3px; }")
        else:
            self.setStyleSheet(
                "QFrame { background: transparent; border: none; }"
                "QFrame:hover { background: #141420; }")

    def set_current(self, current: bool):
        self._current = current
        self._update_style()

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.clicked.emit(self._version)
        super().mousePressEvent(event)


class NodeVersionList(QtWidgets.QWidget):
    """Version list panel for the HDA window's left side.

    Emits:
      version_created(int)  — user clicked "+ New Version" (driver creates new session)
      version_selected(int) — user clicked a version (driver switches session)
    """
    version_created = QtCore.Signal(int)
    version_selected = QtCore.Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: dict[int, _VersionItem] = {}
        self._current_version: int | None = None

        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(4, 6, 4, 6)
        lay.setSpacing(4)

        # Header
        header = QtWidgets.QLabel("Versions")
        header.setStyleSheet(
            f"color:#71717a;font-size:{fs(11)};font-weight:600;"
            f"padding:4px 8px;border:none;")
        lay.addWidget(header)

        # New Version button
        self._new_btn = QtWidgets.QPushButton("+ New Version")
        self._new_btn.setStyleSheet(
            f"QPushButton {{ background:#1a1a24; color:#f59e0b; "
            f"border:1px solid #2a2a3c; border-radius:4px; "
            f"padding:6px; font-size:{fs(11)}; }}"
            f"QPushButton:hover {{ background:#252535; border-color:#f59e0b; }}")
        self._new_btn.clicked.connect(self._on_new_clicked)
        lay.addWidget(self._new_btn)

        # Scrollable list container
        self._scroll = QtWidgets.QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self._scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self._container = QtWidgets.QWidget()
        self._container.setStyleSheet("background: transparent;")
        self._list_layout = QtWidgets.QVBoxLayout(self._container)
        self._list_layout.setContentsMargins(0, 4, 0, 0)
        self._list_layout.setSpacing(2)
        self._list_layout.addStretch()
        self._scroll.setWidget(self._container)
        lay.addWidget(self._scroll, 1)

    def _on_new_clicked(self):
        nxt = next_version(list(self._items.keys()))
        self.version_created.emit(nxt)

    def version_count(self) -> int:
        return len(self._items)

    def current_version(self) -> int | None:
        return self._current_version

    def set_versions(self, versions: list[dict]):
        """Populate the list. Each dict: {version, summary, meta, current?}.

        REPLACES the full list (not append). Call with the complete version list.
        """
        # Clear existing
        for item in self._items.values():
            self._list_layout.removeWidget(item)
            item.deleteLater()
        self._items.clear()
        self._current_version = None

        for v in versions:
            self._add_item(v.get("version", 0), v.get("summary", ""),
                           v.get("meta", ""), v.get("current", False))
        # Sort by version descending (newest first) — rebuild order
        self._reorder()

    def _add_item(self, version: int, summary: str, meta: str, current: bool):
        item = _VersionItem(version, summary, meta, current)
        item.clicked.connect(self.select_version)
        self._items[version] = item
        if current:
            self._current_version = version

    def _reorder(self):
        # Remove all then re-add in descending version order (above stretch)
        for item in self._items.values():
            self._list_layout.removeWidget(item)
        for version in sorted(self._items.keys(), reverse=True):
            self._list_layout.insertWidget(self._list_layout.count() - 1, self._items[version])

    def select_version(self, version: int):
        """Emit selection signal. Driver switches session."""
        self.version_selected.emit(version)

    def mark_current(self, version: int):
        """Update which version shows the 'current' marker."""
        self._current_version = version
        for v, item in self._items.items():
            item.set_current(v == version)
