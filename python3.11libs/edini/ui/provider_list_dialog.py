"""Searchable provider list dialog — pi CLI style.

Used for:
  - Login: pick a provider to configure (shows all pi-ai providers)
  - Logout: pick a provider to deconfigure (shows only configured providers)
"""
from PySide6 import QtCore, QtWidgets
from PySide6.QtCore import Qt

from edini.ui.theme import fs


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

        self.setStyleSheet(f"""
            QDialog {{ background-color: #0c0c14; }}
            QLabel {{ color: #c8ccd4; font-size:{fs(12)}; background:transparent; }}
            QLineEdit {{
                background-color: #10101a;
                color: #c8ccd4;
                border: 1px solid #1e1e2c;
                border-radius: 4px;
                padding: 8px 12px;
                font-size:{fs(13)};
            }}
            QLineEdit:focus {{ border-color: #06b6d4; }}
            QListWidget {{
                background-color: #10101a;
                color: #c8ccd4;
                border: 1px solid #1e1e2c;
                border-radius: 4px;
                font-size:{fs(12)};
                outline: none;
                padding: 4px;
            }}
            QListWidget::item {{
                padding: 8px 12px;
                border-radius: 3px;
            }}
            QListWidget::item:selected {{
                background-color: rgba(6, 182, 212, 0.15);
                color: #e5e5eb;
            }}
            QListWidget::item:hover {{
                background-color: rgba(255,255,255,0.04);
            }}
        """)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Search hint
        hint = QtWidgets.QLabel("Type to filter, ↑↓ to navigate, Enter to select, Esc to cancel")
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
        self._show_badges = show_badges
        self._populate()
        layout.addWidget(self._list, 1)

        # Cancel button
        cancel = QtWidgets.QPushButton("Cancel")
        cancel.setStyleSheet(f"""
            QPushButton {{
                background: #1e1e2c; color: #a1a1aa;
                border: none; border-radius: 4px;
                padding: 6px 20px; font-size:{fs(11)};
            }}
            QPushButton:hover {{ background: #2a2a3c; }}
        """)
        cancel.clicked.connect(self.reject)
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(cancel)
        layout.addLayout(btn_row)

    def _populate(self) -> None:
        self._list.clear()
        for p in self._filtered:
            text = p.get("name", p.get("id", ""))
            if self._show_badges:
                mc = p.get("modelCount")
                vc = p.get("imageModelCount")
                if mc is not None:
                    badges = f"  {mc} models"
                    if vc:
                        badges += f" · {vc} vision"
                    text += f"  <span style='color:#52525b;font-size:{fs(9)}'>{badges}</span>"
            elif p.get("hint"):
                text += f"  <span style='color:#52525b;font-size:{fs(9)}'>{p['hint']}</span>"

            item = QtWidgets.QListWidgetItem()
            item.setData(Qt.UserRole, p)
            item.setText(p.get("name", p.get("id", "")))
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
