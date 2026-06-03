"""Settings dialog — provider config and theme selection."""
from PySide6 import QtCore, QtWidgets
from edini.config import get_settings, save_settings
from edini.ui.theme import THEME_COLORS, get_theme_color, set_theme_color


class SettingsDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edini Settings")
        self.setMinimumWidth(440)
        self.setStyleSheet("""
            QDialog { background-color: #111118; }
            QLabel { color: #e5e5eb; font-size: 12px; }
            QLineEdit {
                background-color: #1a1a24;
                color: #e5e5eb;
                border: 1px solid #2a2a3c;
                border-radius: 4px;
                padding: 6px 8px;
                font-size: 12px;
            }
            QLineEdit:focus { border-color: #06b6d4; }
            QComboBox {
                background-color: #1a1a24;
                color: #e5e5eb;
                border: 1px solid #2a2a3c;
                border-radius: 4px;
                padding: 6px 8px;
                font-size: 12px;
            }
        """)

        settings = get_settings()
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(12)

        # Tabs
        tabs = QtWidgets.QTabWidget(self)
        tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #2a2a3c; background: #0e0e15; }
            QTabBar::tab { background: #1a1a24; color: #71717a; padding: 8px 16px; }
            QTabBar::tab:selected { background: #0e0e15; color: #06b6d4; }
        """)

        # --- Provider Tab ---
        provider_tab = QtWidgets.QWidget()
        provider_form = QtWidgets.QFormLayout(provider_tab)
        provider_form.setSpacing(8)

        self._api_key = QtWidgets.QLineEdit()
        self._api_key.setEchoMode(QtWidgets.QLineEdit.Password)
        self._api_key.setText(settings.get("api_key", ""))
        provider_form.addRow("API Key:", self._api_key)

        self._provider = QtWidgets.QLineEdit()
        self._provider.setText(settings.get("provider", "deepseek"))
        provider_form.addRow("Provider:", self._provider)

        self._model_id = QtWidgets.QLineEdit()
        self._model_id.setText(settings.get("model_id", "deepseek-chat"))
        provider_form.addRow("Model ID:", self._model_id)

        tabs.addTab(provider_tab, "Provider")

        # --- Appearance Tab ---
        app_tab = QtWidgets.QWidget()
        app_form = QtWidgets.QFormLayout(app_tab)
        app_form.setSpacing(8)

        self._theme_combo = QtWidgets.QComboBox()
        current_theme = get_theme_color()
        for key, info in THEME_COLORS.items():
            self._theme_combo.addItem(info["name"], key)
            if key == current_theme:
                self._theme_combo.setCurrentIndex(self._theme_combo.count() - 1)
        app_form.addRow("Theme:", self._theme_combo)

        self._font_scale = QtWidgets.QComboBox()
        for val in ["0.8", "0.9", "1.0", "1.1", "1.2", "1.3", "1.4"]:
            self._font_scale.addItem(val)
        self._font_scale.setCurrentText("1.0")
        app_form.addRow("Font Scale:", self._font_scale)

        tabs.addTab(app_tab, "Appearance")

        layout.addWidget(tabs)

        # Buttons
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch()
        ok_btn = QtWidgets.QPushButton("Save")
        ok_btn.setObjectName("PrimaryButton")
        ok_btn.clicked.connect(self._on_save)
        cancel_btn = QtWidgets.QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(ok_btn)
        layout.addLayout(btn_row)

    def _on_save(self):
        save_settings({
            "api_key": self._api_key.text().strip(),
            "provider": self._provider.text().strip(),
            "model_id": self._model_id.text().strip(),
        })
        key = self._theme_combo.currentData()
        if key:
            set_theme_color(key)
        self.accept()
