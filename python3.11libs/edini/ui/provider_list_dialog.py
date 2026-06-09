"""Searchable provider list dialog — pi CLI style.

Used for:
  - Login: pick a provider to configure (shows all pi-ai providers)
  - Logout: pick a provider to deconfigure (shows only configured providers)
"""
from PySide6 import QtGui, QtWidgets
from PySide6.QtCore import Qt

from edini.ui.theme import fs, accent_color


class ProviderListDialog(QtWidgets.QDialog):
    """Full-width searchable list for provider selection.

    Args:
        parent: Parent widget.
        providers: List of {id, name, ...} dicts.
        title: Dialog title.
        show_badges: If True, show model/vision count badges.
    """

    def __init__(self, parent, providers: list[dict], title: str,
                 show_badges: bool = True):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(480, 500)
        self.resize(520, 560)
        self._providers = providers
        self._filtered = list(providers)
        self._selected: dict | None = None
        self._show_badges = show_badges

        self.setStyleSheet(f"""
            QDialog {{ background-color: #0c0c14; }}
            QLabel {{ color: #c8ccd4; font-size:{fs(12)}; background:transparent; }}
            QLineEdit {{
                background-color: #10101a;
                color: #c8ccd4;
                border: 1px solid #2a2a3c;
                border-radius: 6px;
                padding: 8px 12px;
                font-size:{fs(13)};
            }}
            QLineEdit:focus {{ border-color: {accent_color()}; }}
            QListWidget {{
                background-color: #0e0e16;
                color: #c8ccd4;
                border: 1px solid #1e1e2c;
                border-radius: 6px;
                font-size:{fs(12)};
                outline: none;
                padding: 6px;
            }}
            QListWidget::item {{
                padding: 10px 14px;
                border-radius: 4px;
                margin: 1px 0;
                background-color: transparent;
            }}
            QListWidget::item:selected {{
                background-color: #1a1a2e;
                color: #e5e5eb;
                border-left: 2px solid {accent_color()};
            }}
            QListWidget::item:hover:!selected {{
                background-color: #141422;
            }}
        """)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)

        # Search hint
        hint = QtWidgets.QLabel(
            "Search · ↑↓ Navigate · Enter Select · Esc Cancel")
        hint.setStyleSheet(f"color:#52525b;font-size:{fs(9)};")
        layout.addWidget(hint)

        # Search input
        self._search = QtWidgets.QLineEdit()
        self._search.setPlaceholderText("Search providers...")
        self._search.textChanged.connect(self._on_filter)
        layout.addWidget(self._search)

        # Provider list
        self._list = QtWidgets.QListWidget()
        self._list.itemDoubleClicked.connect(self._on_select)
        self._list.setVerticalScrollMode(
            QtWidgets.QAbstractItemView.ScrollPerPixel)
        self._populate()
        layout.addWidget(self._list, 1)

        # Cancel button
        cancel = QtWidgets.QPushButton("Cancel")
        cancel.setStyleSheet(f"""
            QPushButton {{
                background: #1a1a2a; color: #a1a1aa;
                border: 1px solid #2a2a3c;
                border-radius: 6px;
                padding: 8px 24px; font-size:{fs(11)};
            }}
            QPushButton:hover {{ background: #22223a; color: #c8ccd4; }}
        """)
        cancel.clicked.connect(self.reject)
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(cancel)
        layout.addLayout(btn_row)

    def _populate(self) -> None:
        self._list.clear()
        for p in self._filtered:
            item = QtWidgets.QListWidgetItem()
            item.setData(Qt.UserRole, p)

            name = p.get("name", p.get("id", ""))
            configured = p.get("_configured", False)

            if self._show_badges:
                mc = p.get("modelCount")
                vc = p.get("imageModelCount")
                parts = [name]
                if mc is not None:
                    parts.append(f"{mc} models")
                    if vc:
                        parts.append(f"{vc} vision")
                info = "  ·  ".join(parts[1:]) if len(parts) > 1 else ""
                if configured:
                    name = f"● {name}"
                elif info:
                    name = f"  {name}    {info}"
            elif p.get("hint"):
                name = f"{name}    {p['hint']}"

            item.setText(name)

            # Dim unconfigured providers slightly
            if not configured:
                item.setForeground(
                    QtGui.QColor("#a1a1aa"))
            else:
                item.setForeground(
                    QtGui.QColor("#c8ccd4"))

            self._list.addItem(item)

        if self._list.count() > 0:
            self._list.setCurrentRow(0)

    def _on_filter(self, text: str) -> None:
        text_lower = text.lower()
        if not text_lower:
            self._filtered = list(self._providers)
        else:
            self._filtered = [
                p for p in self._providers
                if text_lower in p.get("name", "").lower()
                or text_lower in p.get("id", "").lower()
            ]
        self._populate()

    def _on_select(self, item) -> None:
        self._selected = item.data(Qt.UserRole)
        self.accept()

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            row = self._list.currentRow()
            if row >= 0:
                self._selected = self._filtered[row]
                self.accept()
        elif event.key() == Qt.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)

    @property
    def selected(self) -> dict | None:
        return self._selected
