"""Settings dialog — Provider dropdown, model history, theme live refresh."""
from PySide6 import QtCore, QtWidgets
from edini.config import get_settings, save_settings, add_model_history, get_model_history
from edini.ui.theme import THEMES, get_theme, set_theme, set_font_scale, fs

PROVIDERS = ["deepseek", "anthropic", "openai", "google"]


class SettingsDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edini Settings")
        self.setMinimumWidth(420)
        self.setStyleSheet(f"""
            QDialog {{ background-color: #0c0c14; }}
            QLabel {{ color: #c8ccd4; font-size:{fs(12)}; background:transparent; }}
            QLineEdit {{
                background-color: #10101a;
                color: #c8ccd4;
                border: 1px solid #1e1e2c;
                border-radius: 4px;
                padding: 6px 10px;
                font-size:{fs(12)};
            }}
            QLineEdit:focus {{ border-color: #06b6d4; }}
            QComboBox {{
                background-color: #10101a;
                color: #c8ccd4;
                border: 1px solid #1e1e2c;
                border-radius: 4px;
                padding: 6px 10px;
                font-size:{fs(12)};
            }}
            QComboBox:focus {{ border-color: #06b6d4; }}
            QComboBox::drop-down {{ border:none; width:20px; }}
            QComboBox QAbstractItemView {{
                background-color: #101018;
                border: 1px solid #1e1e2c;
                selection-background-color: #1a1a2a;
                color:#c8ccd4;
            }}
        """)

        settings = get_settings()
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        # ── Provider ──
        layout.addWidget(_section_label("Provider"))

        self._provider = QtWidgets.QComboBox()
        for p in PROVIDERS:
            self._provider.addItem(p)
        current_provider = settings.get("provider", "deepseek")
        idx = self._provider.findText(current_provider)
        if idx >= 0:
            self._provider.setCurrentIndex(idx)
        layout.addWidget(self._provider)

        # ── Model Name ──
        layout.addWidget(_section_label("Model Name"))

        self._model_combo = QtWidgets.QComboBox()
        self._model_combo.setEditable(True)
        self._model_combo.setInsertPolicy(QtWidgets.QComboBox.NoInsert)
        self._model_combo.lineEdit().setPlaceholderText("model name...")
        # Load history
        history = get_model_history()
        for h in history:
            self._model_combo.addItem(h)
        self._model_combo.setCurrentText(settings.get("model_id", "deepseek-chat"))
        layout.addWidget(self._model_combo)

        # Result preview
        self._model_preview = QtWidgets.QLabel(
            f"→ deepseek / {settings.get('model_id', 'deepseek-chat')}"
        )
        self._model_preview.setStyleSheet(f"color:#71717a;font-size:{fs(11)};")
        layout.addWidget(self._model_preview)

        self._provider.currentTextChanged.connect(self._on_provider_changed)
        self._model_combo.currentTextChanged.connect(self._on_model_changed)

        # ── API Key ──
        layout.addWidget(_section_label("API Key"))
        api_key_row = QtWidgets.QHBoxLayout()
        self._api_key = QtWidgets.QLineEdit()
        self._api_key.setEchoMode(QtWidgets.QLineEdit.Password)
        self._api_key.setText(settings.get("api_key", ""))
        api_key_row.addWidget(self._api_key)

        show_btn = QtWidgets.QPushButton("Show")
        show_btn.setFixedWidth(60)
        show_btn.setCheckable(True)
        show_btn.toggled.connect(
            lambda v: self._api_key.setEchoMode(
                QtWidgets.QLineEdit.Normal if v else QtWidgets.QLineEdit.Password
            )
        )
        api_key_row.addWidget(show_btn)
        layout.addLayout(api_key_row)

        # ── Appearance ──
        layout.addWidget(_section_label("Appearance"))
        appear_row = QtWidgets.QHBoxLayout()
        appear_row.addWidget(QtWidgets.QLabel("Theme:"))
        self._theme_combo = QtWidgets.QComboBox()
        current_theme = settings.get("theme_color", "cyan")
        for key, info in THEMES.items():
            self._theme_combo.addItem(info["name"], key)
            if key == current_theme:
                self._theme_combo.setCurrentIndex(self._theme_combo.count() - 1)
        appear_row.addWidget(self._theme_combo)

        appear_row.addWidget(QtWidgets.QLabel("Font:"))
        self._font_scale = QtWidgets.QComboBox()
        current_scale = str(settings.get("font_scale", 1.0))
        for val in ["0.8", "0.9", "1.0", "1.1", "1.2", "1.3", "1.4"]:
            self._font_scale.addItem(val)
        self._font_scale.setCurrentText(current_scale)
        appear_row.addWidget(self._font_scale)
        layout.addLayout(appear_row)

        # Separator
        sep = QtWidgets.QFrame()
        sep.setFrameShape(QtWidgets.QFrame.HLine)
        sep.setStyleSheet("border:none;border-top:1px solid #1e1e2c;margin:4px 0;")
        layout.addWidget(sep)

        # ── Buttons ──
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QtWidgets.QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        ok_btn = QtWidgets.QPushButton("Save")
        ok_btn.setObjectName("PrimaryButton")
        ok_btn.clicked.connect(self._on_save)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(ok_btn)
        layout.addLayout(btn_row)

    def _on_provider_changed(self, text: str):
        self._model_preview.setText(
            f"→ {text} / {self._model_combo.currentText().strip()}"
        )

    def _on_model_changed(self, text: str):
        self._model_preview.setText(
            f"→ {self._provider.currentText()} / {text.strip()}"
        )

    def _on_save(self):
        provider = self._provider.currentText().strip()
        model = self._model_combo.currentText().strip()

        save_settings({
            "api_key": self._api_key.text().strip(),
            "provider": provider,
            "model_id": model,
        })

        # Model history
        if model:
            add_model_history(model)

        # Theme
        theme_key = self._theme_combo.currentData()
        if theme_key:
            set_theme(theme_key)

        # Font scale
        font_val = float(self._font_scale.currentText())
        set_font_scale(font_val)

        # Notify main window
        from edini.ui.windows import _main_window
        if _main_window:
            _main_window.refresh_theme()

        self.accept()


def _section_label(text: str) -> QtWidgets.QLabel:
    lbl = QtWidgets.QLabel(f"<b>{text}</b>")
    lbl.setStyleSheet(f"color:#c8ccd4;font-size:{fs(12)};font-weight:600;")
    return lbl
