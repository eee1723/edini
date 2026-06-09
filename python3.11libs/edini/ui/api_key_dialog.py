"""API key input dialog — shown after selecting a provider to login."""
from PySide6 import QtWidgets

from edini.ui.theme import fs


class ApiKeyDialog(QtWidgets.QDialog):
    """Simple dialog for entering an API key for a provider.

    Args:
        parent: Parent widget.
        provider_name: Display name of the provider.
    """

    def __init__(self, parent, provider_name: str):
        super().__init__(parent)
        self.setWindowTitle(f"Login to {provider_name}")
        self.setMinimumWidth(420)

        self.setStyleSheet(f"""
            QDialog {{ background-color: #0c0c14; }}
            QLabel {{ color: #c8ccd4; font-size:{fs(12)}; background:transparent; }}
            QLineEdit {{
                background-color: #10101a;
                color: #c8ccd4;
                border: 1px solid #1e1e2c;
                border-radius: 4px;
                padding: 8px 12px;
                font-size:{fs(12)};
            }}
            QLineEdit:focus {{ border-color: #06b6d4; }}
        """)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # Header
        header = QtWidgets.QLabel(
            f"Enter API key for <b>{provider_name}</b>")
        header.setWordWrap(True)
        layout.addWidget(header)

        # Key input
        self._key_input = QtWidgets.QLineEdit()
        self._key_input.setEchoMode(QtWidgets.QLineEdit.Password)
        self._key_input.setPlaceholderText("API Key...")
        layout.addWidget(self._key_input)

        # Buttons
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch()

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
        btn_row.addWidget(cancel)

        ok = QtWidgets.QPushButton("Login")
        ok.setStyleSheet(f"""
            QPushButton {{
                background: #0E7490; color: #e5e5eb;
                border: none; border-radius: 4px;
                padding: 6px 20px; font-size:{fs(11)};
                font-weight: 600;
            }}
            QPushButton:hover {{ background: #0c8fa8; }}
        """)
        ok.clicked.connect(self._on_ok)
        btn_row.addWidget(ok)
        layout.addLayout(btn_row)

        self._key_input.setFocus()

    def _on_ok(self) -> None:
        if self._key_input.text().strip():
            self.accept()

    @property
    def api_key(self) -> str:
        return self._key_input.text().strip()
