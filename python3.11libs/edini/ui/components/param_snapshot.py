"""ParamSnapshotPanel — HDA parameter tree + change diff (HDA-only widget).

Shows current HDA parameter key/values and highlights which changed since the
last set_params call. The orange highlight color matches the HDA accent.
"""
from PySide6 import QtGui, QtWidgets
from edini.ui.theme import fs

ACCENT = "#f59e0b"   # HDA accent (matches scope.accent_override)


class ParamSnapshotPanel(QtWidgets.QFrame):
    """Parameter display with per-call diff tracking."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._params: dict[str, str] = {}
        self._prev: dict[str, str] = {}
        self._changed: set[str] = set()
        self.setStyleSheet(
            "QFrame { background:#0e0e15; border:1px solid #2a2a3c; border-radius:6px; }")
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(4)

        header = QtWidgets.QLabel("🔧 Parameters")
        header.setStyleSheet(f"font-size:{fs(11)};font-weight:600;color:#71717a;border:none;")
        lay.addWidget(header)

        self._tree = QtWidgets.QTreeWidget()
        self._tree.setHeaderLabels(["Param", "Value"])
        self._tree.setColumnWidth(0, 110)
        self._tree.setStyleSheet(
            f"QTreeWidget {{ background:transparent; border:none; "
            f"font-size:{fs(11)}; color:#c8ccd4; }}"
            f"QTreeWidget::item {{ padding:2px 4px; }}")
        lay.addWidget(self._tree)

    def set_params(self, params: dict[str, str]):
        """Update params; tracks diff vs previous call. None/empty clears."""
        self._prev = dict(self._params)
        self._params = dict(params) if params else {}
        self._changed = {k for k in self._params if self._prev.get(k) != self._params[k]}
        self._refresh()

    def _refresh(self):
        self._tree.clear()
        for k, v in sorted(self._params.items()):
            item = QtWidgets.QTreeWidgetItem([k, str(v)])
            if k in self._changed:
                orange = QtGui.QColor(ACCENT)
                for col in range(2):
                    item.setForeground(col, orange)
            self._tree.addTopLevelItem(item)

    def params_text(self) -> str:
        """All params as 'key: value' lines (for debugging/testing)."""
        return "\n".join(f"{k}: {v}" for k, v in sorted(self._params.items()))

    def changed_params(self) -> set[str]:
        """Params that changed in the most recent set_params call."""
        return set(self._changed)
