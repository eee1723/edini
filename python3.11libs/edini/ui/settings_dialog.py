"""Settings dialog — tabbed: General + Knowledge."""
from PySide6 import QtCore, QtWidgets
from edini.config import get_settings, save_settings, add_model_history, get_model_history
from edini.ui.theme import THEMES, get_theme, set_theme, set_font_scale, fs

PROVIDERS = ["deepseek", "anthropic", "openai", "google"]


class SettingsDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edini Settings")
        self.setMinimumSize(480, 520)
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
            QTabWidget::pane {{
                background: #0c0c14;
                border: 1px solid #1e1e2c;
                border-top: none;
            }}
            QTabBar::tab {{
                background: #10101a;
                color: #a1a1aa;
                padding: 8px 20px;
                font-size: {fs(12)};
                border: 1px solid #1e1e2c;
                border-bottom: none;
            }}
            QTabBar::tab:selected {{
                background: #0c0c14;
                color: #e5e5eb;
                font-weight: 600;
            }}
        """)

        settings = get_settings()
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Tabs
        self._tabs = QtWidgets.QTabWidget()
        self._tabs.addTab(self._build_general_tab(settings), "General")
        self._tabs.addTab(self._build_knowledge_tab(settings), "Knowledge")
        layout.addWidget(self._tabs, 1)

        # Buttons
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

    # ── General Tab ──

    def _build_general_tab(self, settings: dict) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(w)
        layout.setSpacing(10)
        layout.setContentsMargins(12, 12, 12, 12)

        # Provider
        layout.addWidget(_section_label("Provider"))
        self._provider = QtWidgets.QComboBox()
        for p in PROVIDERS:
            self._provider.addItem(p)
        idx = self._provider.findText(settings.get("provider", "deepseek"))
        if idx >= 0:
            self._provider.setCurrentIndex(idx)
        layout.addWidget(self._provider)

        # Model
        layout.addWidget(_section_label("Model Name"))
        self._model_combo = QtWidgets.QComboBox()
        self._model_combo.setEditable(True)
        self._model_combo.setInsertPolicy(QtWidgets.QComboBox.NoInsert)
        self._model_combo.lineEdit().setPlaceholderText("model name...")
        for h in get_model_history():
            self._model_combo.addItem(h)
        self._model_combo.setCurrentText(settings.get("model_id", "deepseek-chat"))
        layout.addWidget(self._model_combo)

        self._model_preview = QtWidgets.QLabel(
            f"→ deepseek / {settings.get('model_id', 'deepseek-chat')}"
        )
        self._model_preview.setStyleSheet(f"color:#71717a;font-size:{fs(11)};")
        layout.addWidget(self._model_preview)

        self._provider.currentTextChanged.connect(self._on_provider_changed)
        self._model_combo.currentTextChanged.connect(self._on_model_changed)

        # API Key
        layout.addWidget(_section_label("API Key"))
        api_row = QtWidgets.QHBoxLayout()
        self._api_key = QtWidgets.QLineEdit()
        self._api_key.setEchoMode(QtWidgets.QLineEdit.Password)
        self._api_key.setText(settings.get("api_key", ""))
        api_row.addWidget(self._api_key)
        show_btn = QtWidgets.QPushButton("Show")
        show_btn.setFixedWidth(60)
        show_btn.setCheckable(True)
        show_btn.toggled.connect(
            lambda v: self._api_key.setEchoMode(
                QtWidgets.QLineEdit.Normal if v else QtWidgets.QLineEdit.Password))
        api_row.addWidget(show_btn)
        layout.addLayout(api_row)

        # Appearance
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
        layout.addStretch()
        return w

    # ── Knowledge Tab ──

    def _build_knowledge_tab(self, settings: dict) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(w)
        layout.setSpacing(12)
        layout.setContentsMargins(12, 12, 12, 12)

        # Enable
        self._knowledge_check = QtWidgets.QCheckBox(
            "对话结束后自动提取知识（AI 反思 → 用户确认 → 存入铁律/知识库）")
        self._knowledge_check.setChecked(settings.get("knowledge_enabled", True))
        self._knowledge_check.setStyleSheet(
            f"QCheckBox {{ color:#e5e5eb; font-size:{fs(12)}; spacing:8px; }}")
        layout.addWidget(self._knowledge_check)

        # Stats
        stats_card = QtWidgets.QFrame()
        stats_card.setStyleSheet("""
            QFrame {
                background: #10101a;
                border: 1px solid #1e1e2c;
                border-radius: 6px;
            }
        """)
        stats_layout = QtWidgets.QVBoxLayout(stats_card)
        stats_layout.setContentsMargins(12, 10, 12, 10)
        stats_layout.setSpacing(6)

        self._rules_stats = QtWidgets.QLabel()
        self._entries_stats = QtWidgets.QLabel()
        self._max_rules_label = QtWidgets.QLabel("铁律上限: 20 条（超过自动淘汰最旧的）")
        self._max_rules_label.setStyleSheet(f"color:#71717a;font-size:{fs(10)};")
        self._refresh_knowledge_stats()
        stats_layout.addWidget(self._rules_stats)
        stats_layout.addWidget(self._entries_stats)
        stats_layout.addWidget(self._max_rules_label)
        layout.addWidget(stats_card)

        # Hint
        hint = QtWidgets.QLabel(
            "铁律 (Rules)：通用原则，每次对话自动注入 system prompt\n"
            "知识库 (Entries)：细节知识，可通过 search_knowledge 工具检索")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color:#71717a;font-size:{fs(10)};padding:4px 0;")
        layout.addWidget(hint)

        # Manage buttons
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.setSpacing(8)

        manage_rules_btn = QtWidgets.QPushButton("管理铁律")
        manage_rules_btn.setStyleSheet(_btn_style("#1E40AF"))
        manage_rules_btn.clicked.connect(lambda: self._open_knowledge_manager("rules"))
        btn_row.addWidget(manage_rules_btn)

        manage_entries_btn = QtWidgets.QPushButton("管理知识库")
        manage_entries_btn.setStyleSheet(_btn_style("#0E7490"))
        manage_entries_btn.clicked.connect(lambda: self._open_knowledge_manager("entries"))
        btn_row.addWidget(manage_entries_btn)
        layout.addLayout(btn_row)

        layout.addStretch()
        return w

    def _refresh_knowledge_stats(self):
        """Update knowledge stats in the Knowledge tab."""
        from edini.ui.knowledge_store import rules_count, entries_count
        r = rules_count()
        e = entries_count()
        self._rules_stats.setText(f"铁律: {r} 条" + (f" (含 {r - sum(1 for x in _load_non_default_rules())} 条默认)" if r > 0 else ""))
        self._entries_stats.setText(f"知识库: {e} 条")

    # ── Handlers ──

    def _on_provider_changed(self, text: str):
        self._model_preview.setText(
            f"→ {text} / {self._model_combo.currentText().strip()}")

    def _on_model_changed(self, text: str):
        self._model_preview.setText(
            f"→ {self._provider.currentText()} / {text.strip()}")

    def _open_knowledge_manager(self, tab: str = "rules"):
        """Open the knowledge management dialog."""
        from edini.ui.knowledge_dialog import KnowledgeDialog
        dlg = KnowledgeDialog(self)
        if tab == "entries":
            dlg._tabs.setCurrentIndex(1)
        dlg.exec()
        self._refresh_knowledge_stats()

    def _on_save(self):
        provider = self._provider.currentText().strip()
        model = self._model_combo.currentText().strip()

        save_settings({
            "api_key": self._api_key.text().strip(),
            "provider": provider,
            "model_id": model,
            "knowledge_enabled": self._knowledge_check.isChecked(),
        })

        if model:
            add_model_history(model)

        theme_key = self._theme_combo.currentData()
        if theme_key:
            set_theme(theme_key)

        font_val = float(self._font_scale.currentText())
        set_font_scale(font_val)

        from edini.ui.windows import _main_window
        if _main_window:
            _main_window.refresh_theme()

        self.accept()


# ── Helpers ──

def _section_label(text: str) -> QtWidgets.QLabel:
    lbl = QtWidgets.QLabel(f"<b>{text}</b>")
    lbl.setStyleSheet(f"color:#c8ccd4;font-size:{fs(12)};font-weight:600;")
    return lbl


def _btn_style(color: str) -> str:
    return f"""
        QPushButton {{
            background: {color};
            color: #e5e5eb;
            border: none;
            border-radius: 4px;
            padding: 6px 16px;
            font-size: {fs(11)};
        }}
        QPushButton:hover {{ background: {_lighter(color, 0.15)}; }}
        QPushButton:pressed {{ background: {_darker(color, 0.15)}; }}
    """


def _lighter(h: str, a: float) -> str:
    h = _expand_hex(h)
    r, g, b = int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)
    return f"#{min(255, int(r + (255 - r) * a)):02x}{min(255, int(g + (255 - g) * a)):02x}{min(255, int(b + (255 - b) * a)):02x}"


def _darker(h: str, a: float) -> str:
    h = _expand_hex(h)
    r, g, b = int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)
    return f"#{max(0, int(r * (1 - a))):02x}{max(0, int(g * (1 - a))):02x}{max(0, int(b * (1 - a))):02x}"


def _expand_hex(h: str) -> str:
    if len(h) == 4:
        return f"#{h[1]}{h[1]}{h[2]}{h[2]}{h[3]}{h[3]}"
    if len(h) == 5:
        return f"#{h[1]}{h[1]}{h[2]}{h[2]}{h[3]}{h[3]}{h[4]}{h[4]}"
    return h


def _load_non_default_rules() -> list:
    """Helper to count non-default (user-added) rules."""
    from edini.ui.knowledge_store import load_rules
    return [r for r in load_rules() if not r.get("id", "").startswith("rule00")]
