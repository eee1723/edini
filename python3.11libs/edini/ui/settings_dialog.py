"""Settings dialog — tabbed: API Keys + Models + Knowledge.

Stores configuration in pi's native config files:
  ~/.pi/agent/auth.json    — API keys
  ~/.pi/agent/models.json  — custom provider/model definitions
  ~/.pi/agent/settings.json — default provider/model/thinking
"""
from PySide6 import QtCore, QtWidgets
from edini.config import (
    get_settings, save_settings,
    read_pi_auth, write_pi_auth,
    read_pi_models, write_pi_models,
    read_pi_settings, write_pi_settings,
    PI_MODELS_FILE,
)
from edini.ui.theme import THEMES, get_theme, set_theme, set_font_scale, fs
from edini.ui.knowledge_store import rules_count, entries_count, load_rules

KNOWN_PROVIDERS = [
    "anthropic", "openai", "deepseek", "google", "mistral", "groq",
    "cerebras", "xai", "openrouter", "nvidia", "fireworks", "together",
    "huggingface", "kimi-coding", "minimax", "minimax-cn", "zai",
    "zai-coding-cn", "xiaomi", "opencode", "aliyun", "zhipu",
]


class SettingsDialog(QtWidgets.QDialog):
    """Settings dialog with three tabs: API Keys, Models, Knowledge."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._needs_restart = False
        self.setWindowTitle("Edini Settings")
        self.setMinimumSize(560, 600)
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
            QTableWidget {{
                background-color: #10101a;
                color: #c8ccd4;
                border: 1px solid #1e1e2c;
                border-radius: 4px;
                gridline-color: #1e1e2c;
                font-size:{fs(11)};
            }}
            QTableWidget::item {{
                padding: 4px 8px;
            }}
            QHeaderView::section {{
                background-color: #0c0c14;
                color: #a1a1aa;
                padding: 4px 8px;
                border: none;
                border-bottom: 1px solid #1e1e2c;
                font-size:{fs(10)};
            }}
        """)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Tabs
        self._tabs = QtWidgets.QTabWidget()
        self._tabs.addTab(self._build_api_keys_tab(), "\U0001f511 API Keys")
        self._tabs.addTab(self._build_models_tab(), "\U0001f916 Models")
        self._tabs.addTab(self._build_knowledge_tab(get_settings()), "\U0001f4da Knowledge")
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

    # ═══════════════════════════════════════════════════════════════════
    # Tab 1: API Keys
    # ═══════════════════════════════════════════════════════════════════

    def _build_api_keys_tab(self) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(w)
        layout.setSpacing(10)
        layout.setContentsMargins(12, 12, 12, 12)

        # Header
        header = QtWidgets.QLabel(
            "API keys are stored in <code>~/.pi/agent/auth.json</code><br>"
            "Shared with <b>pi</b> CLI \u2014 configure once, use everywhere."
        )
        header.setWordWrap(True)
        header.setStyleSheet(f"color:#71717a;font-size:{fs(10)};padding:4px 0;")
        layout.addWidget(header)

        # Configured providers list
        layout.addWidget(_section_label("Configured Providers"))
        self._auth_table = QtWidgets.QTableWidget(0, 3)
        self._auth_table.setHorizontalHeaderLabels(["Provider", "API Key", ""])
        self._auth_table.horizontalHeader().setSectionResizeMode(
            0, QtWidgets.QHeaderView.Stretch)
        self._auth_table.horizontalHeader().setSectionResizeMode(
            1, QtWidgets.QHeaderView.Stretch)
        self._auth_table.horizontalHeader().setSectionResizeMode(
            2, QtWidgets.QHeaderView.Fixed)
        self._auth_table.horizontalHeader().resizeSection(2, 80)
        self._auth_table.verticalHeader().setVisible(False)
        self._auth_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self._auth_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self._auth_table.setMaximumHeight(200)
        self._populate_auth_table(read_pi_auth())
        layout.addWidget(self._auth_table)

        # Add new provider row
        layout.addWidget(_section_label("Add Provider"))
        add_row = QtWidgets.QHBoxLayout()
        self._new_provider_combo = QtWidgets.QComboBox()
        self._new_provider_combo.setEditable(True)
        self._new_provider_combo.addItems(KNOWN_PROVIDERS)
        self._new_provider_combo.setCurrentText("")
        add_row.addWidget(self._new_provider_combo, 1)

        self._new_key_input = QtWidgets.QLineEdit()
        self._new_key_input.setEchoMode(QtWidgets.QLineEdit.Password)
        self._new_key_input.setPlaceholderText("API Key...")
        add_row.addWidget(self._new_key_input, 2)

        add_btn = QtWidgets.QPushButton("Add")
        add_btn.setFixedWidth(60)
        add_btn.clicked.connect(self._on_add_provider_key)
        add_row.addWidget(add_btn)
        layout.addLayout(add_row)

        # Terminal hint
        hint = QtWidgets.QLabel(
            "\U0001f4a1 Advanced: run <code>pi /login</code> in terminal "
            "for OAuth providers (Claude Pro, ChatGPT Plus, GitHub Copilot)")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color:#52525b;font-size:{fs(9)};padding:4px 0;")
        layout.addWidget(hint)

        layout.addStretch()
        return w

    def _populate_auth_table(self, auth: dict) -> None:
        self._auth_table.setRowCount(0)
        for provider, entry in auth.items():
            if not isinstance(entry, dict) or entry.get("type") != "api_key":
                continue
            row = self._auth_table.rowCount()
            self._auth_table.insertRow(row)
            self._auth_table.setItem(row, 0, QtWidgets.QTableWidgetItem(provider))
            key = entry.get("key", "")
            masked = key[:8] + "..." + key[-4:] if len(key) > 12 else key
            self._auth_table.setItem(row, 1, QtWidgets.QTableWidgetItem(masked))
            btn = QtWidgets.QPushButton("Remove")
            btn.setStyleSheet("color:#ef4444;border:none;font-size:10px;")
            btn.clicked.connect(
                lambda checked, p=provider: self._on_remove_provider(p))
            self._auth_table.setCellWidget(row, 2, btn)

    def _on_add_provider_key(self) -> None:
        provider = self._new_provider_combo.currentText().strip()
        key = self._new_key_input.text().strip()
        if not provider or not key:
            return
        auth = read_pi_auth()
        auth[provider] = {"type": "api_key", "key": key}
        write_pi_auth(auth)
        self._populate_auth_table(auth)
        self._new_key_input.clear()
        self._new_provider_combo.setCurrentText("")
        self._needs_restart = True

    def _on_remove_provider(self, provider: str) -> None:
        auth = read_pi_auth()
        auth.pop(provider, None)
        write_pi_auth(auth)
        self._populate_auth_table(auth)
        self._needs_restart = True

    # ═══════════════════════════════════════════════════════════════════
    # Tab 2: Models
    # ═══════════════════════════════════════════════════════════════════

    def _build_models_tab(self) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(w)
        layout.setSpacing(10)
        layout.setContentsMargins(12, 12, 12, 12)

        pi_sett = read_pi_settings()

        # ── Default Model ──
        layout.addWidget(_section_label("Default Model"))
        model_row = QtWidgets.QHBoxLayout()
        model_row.addWidget(QtWidgets.QLabel("Provider:"))
        self._default_provider = QtWidgets.QComboBox()
        self._default_provider.setEditable(False)
        providers = self._get_all_provider_names()
        self._default_provider.addItems(providers)
        current_provider = pi_sett.get("defaultProvider", "")
        if current_provider:
            idx = self._default_provider.findText(current_provider)
            if idx >= 0:
                self._default_provider.setCurrentIndex(idx)
        model_row.addWidget(self._default_provider, 1)

        model_row.addWidget(QtWidgets.QLabel("Model:"))
        self._default_model = QtWidgets.QComboBox()
        self._default_model.setEditable(True)
        self._default_model.setInsertPolicy(QtWidgets.QComboBox.NoInsert)
        self._default_model.lineEdit().setPlaceholderText("model name...")
        self._populate_models_for_provider(
            self._default_provider.currentText(), self._default_model)
        current_model = pi_sett.get("defaultModel", "")
        if current_model:
            idx = self._default_model.findText(current_model)
            if idx >= 0:
                self._default_model.setCurrentIndex(idx)
            else:
                self._default_model.setCurrentText(current_model)
        model_row.addWidget(self._default_model, 1)
        layout.addLayout(model_row)

        # ── Thinking Level ──
        thinking_row = QtWidgets.QHBoxLayout()
        thinking_row.addWidget(QtWidgets.QLabel("Thinking:"))
        self._thinking_combo = QtWidgets.QComboBox()
        self._thinking_combo.addItems(
            ["off", "minimal", "low", "medium", "high", "xhigh"])
        current_thinking = pi_sett.get("defaultThinkingLevel", "medium")
        idx = self._thinking_combo.findText(current_thinking)
        if idx >= 0:
            self._thinking_combo.setCurrentIndex(idx)
        thinking_row.addWidget(self._thinking_combo)
        thinking_row.addStretch()
        layout.addLayout(thinking_row)

        self._default_provider.currentTextChanged.connect(
            lambda p: self._populate_models_for_provider(p, self._default_model))

        # ── Appearance ──
        layout.addWidget(_section_label("Appearance"))
        appear_row = QtWidgets.QHBoxLayout()
        appear_row.addWidget(QtWidgets.QLabel("Theme:"))
        self._theme_combo = QtWidgets.QComboBox()
        settings = get_settings()
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

        # ── Separator ──
        sep = QtWidgets.QFrame()
        sep.setFrameShape(QtWidgets.QFrame.HLine)
        sep.setStyleSheet("color:#1e1e2c;")
        layout.addWidget(sep)

        # ── Custom Providers ──
        layout.addWidget(_section_label("Custom Providers"))
        layout.addWidget(QtWidgets.QLabel(
            f"From <code>{PI_MODELS_FILE}</code>"))
        self._providers_table = QtWidgets.QTableWidget(0, 3)
        self._providers_table.setHorizontalHeaderLabels(
            ["Provider", "API Type", "Models"])
        self._providers_table.horizontalHeader().setSectionResizeMode(
            0, QtWidgets.QHeaderView.ResizeToContents)
        self._providers_table.horizontalHeader().setSectionResizeMode(
            1, QtWidgets.QHeaderView.ResizeToContents)
        self._providers_table.horizontalHeader().setStretchLastSection(True)
        self._providers_table.verticalHeader().setVisible(False)
        self._providers_table.setEditTriggers(
            QtWidgets.QAbstractItemView.NoEditTriggers)
        self._providers_table.setMaximumHeight(200)
        self._populate_providers_table()
        layout.addWidget(self._providers_table)

        add_cp_btn = QtWidgets.QPushButton("+ Add Custom Provider")
        add_cp_btn.setStyleSheet(_btn_style("#0E7490"))
        add_cp_btn.clicked.connect(self._on_add_custom_provider)
        layout.addWidget(add_cp_btn)

        hint = QtWidgets.QLabel(
            "\U0001f4a1 Advanced: edit "
            "<code>~/.pi/agent/models.json</code> directly for full control")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color:#52525b;font-size:{fs(9)};padding:4px 0;")
        layout.addWidget(hint)

        layout.addStretch()
        return w

    def _get_all_provider_names(self) -> list[str]:
        names = set()
        names.update(read_pi_auth().keys())
        models = read_pi_models()
        names.update(models.get("providers", {}).keys())
        for p in KNOWN_PROVIDERS:
            names.add(p)
        return sorted(names)

    def _populate_models_for_provider(
            self, provider: str, combo: QtWidgets.QComboBox) -> None:
        current = combo.currentText()
        combo.clear()
        models_config = read_pi_models()
        provider_config = models_config.get("providers", {}).get(provider, {})
        for m in provider_config.get("models", []):
            name = m.get("name", m.get("id", ""))
            combo.addItem(name, m.get("id", ""))
        if current:
            idx = combo.findText(current)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            elif combo.count() > 0:
                # Keep current text if editable
                combo.setCurrentText(current)

    def _populate_providers_table(self) -> None:
        self._providers_table.setRowCount(0)
        models = read_pi_models()
        for name, config in models.get("providers", {}).items():
            row = self._providers_table.rowCount()
            self._providers_table.insertRow(row)
            self._providers_table.setItem(
                row, 0, QtWidgets.QTableWidgetItem(name))
            self._providers_table.setItem(
                row, 1, QtWidgets.QTableWidgetItem(
                    config.get("api", "")))
            model_names = ", ".join(
                m.get("id", "") for m in config.get("models", []))
            self._providers_table.setItem(
                row, 2, QtWidgets.QTableWidgetItem(model_names))

    def _on_add_custom_provider(self) -> None:
        dlg = _AddProviderDialog(self)
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            data = dlg.get_provider_data()
            models = read_pi_models()
            providers = models.setdefault("providers", {})
            providers[data["name"]] = {
                "baseUrl": data["baseUrl"],
                "api": data["api"],
                "apiKey": (
                    "$" + data["name"].upper().replace("-", "_") + "_API_KEY"
                ),
                "models": [
                    {"id": m.strip()}
                    for m in data["models"].split(",") if m.strip()
                ],
            }
            write_pi_models(models)
            self._populate_providers_table()
            self._default_provider.clear()
            self._default_provider.addItems(self._get_all_provider_names())
            self._needs_restart = True

    # ═══════════════════════════════════════════════════════════════════
    # Tab 3: Knowledge (preserved unchanged)
    # ═══════════════════════════════════════════════════════════════════

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
        self._max_rules_label = QtWidgets.QLabel(
            "铁律上限: 20 条（超过自动淘汰最旧的）")
        self._max_rules_label.setStyleSheet(
            f"color:#71717a;font-size:{fs(10)};")
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
        manage_rules_btn.clicked.connect(
            lambda: self._open_knowledge_manager("rules"))
        btn_row.addWidget(manage_rules_btn)

        manage_entries_btn = QtWidgets.QPushButton("管理知识库")
        manage_entries_btn.setStyleSheet(_btn_style("#0E7490"))
        manage_entries_btn.clicked.connect(
            lambda: self._open_knowledge_manager("entries"))
        btn_row.addWidget(manage_entries_btn)
        layout.addLayout(btn_row)

        layout.addStretch()
        return w

    # ═══════════════════════════════════════════════════════════════════
    # Shared helpers
    # ═══════════════════════════════════════════════════════════════════

    def _refresh_knowledge_stats(self):
        r = rules_count()
        e = entries_count()
        defaults_count = sum(
            1 for r2 in load_rules()
            if r2.get("id", "").startswith("rule00"))
        self._rules_stats.setText(
            f"铁律: {r} 条"
            + (f"（含 {defaults_count} 条默认）" if defaults_count else ""))
        self._entries_stats.setText(f"知识库: {e} 条")

    def _open_knowledge_manager(self, tab: str = "rules"):
        from edini.ui.knowledge_dialog import KnowledgeDialog
        dlg = KnowledgeDialog(self)
        if tab == "entries":
            dlg._tabs.setCurrentIndex(1)
        dlg.exec()
        self._refresh_knowledge_stats()

    # ═══════════════════════════════════════════════════════════════════
    # Save
    # ═══════════════════════════════════════════════════════════════════

    def _on_save(self):
        provider = self._default_provider.currentText()
        model_text = self._default_model.currentText().strip()
        model_id = self._default_model.currentData() or model_text
        thinking = self._thinking_combo.currentText()

        # Write default model to pi settings.json
        pi_sett = read_pi_settings()
        pi_sett["defaultProvider"] = provider
        pi_sett["defaultModel"] = model_id
        pi_sett["defaultThinkingLevel"] = thinking
        write_pi_settings(pi_sett)

        # Write Edini UI settings (theme, font, knowledge)
        save_settings({
            "knowledge_enabled": self._knowledge_check.isChecked(),
        })

        theme_key = self._theme_combo.currentData()
        if theme_key:
            set_theme(theme_key)

        font_val = float(self._font_scale.currentText())
        set_font_scale(font_val)

        from edini.ui.windows import _main_window
        if _main_window:
            _main_window.refresh_theme()
            rpc = _main_window._rpc_client

            # Try to set model without restart
            rpc.send_set_model(provider, model_id)

            if self._needs_restart:
                self._needs_restart = False
                # Connect a one-shot handler for post-restart model re-set
                try:
                    rpc.status_changed.disconnect(self._on_restart_done)
                except TypeError:
                    pass
                rpc.status_changed.connect(self._on_restart_done)
                rpc.restart()

        self.accept()

    def _on_restart_done(self, status: str):
        """After Pi restarts, re-send the model config from pi settings."""
        if status == "connected":
            from edini.ui.windows import _main_window
            if _main_window:
                pi_sett = read_pi_settings()
                rpc = _main_window._rpc_client
                rpc.send_set_model(
                    pi_sett.get("defaultProvider", ""),
                    pi_sett.get("defaultModel", ""),
                )
            try:
                from edini.ui.windows import _main_window
                if _main_window:
                    _main_window._rpc_client.status_changed.disconnect(
                        self._on_restart_done)
            except TypeError:
                pass


# ═══════════════════════════════════════════════════════════════════════
# Add Provider Dialog
# ═══════════════════════════════════════════════════════════════════════

class _AddProviderDialog(QtWidgets.QDialog):
    """Simple dialog for adding a custom provider to models.json."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Custom Provider")
        self.setMinimumWidth(400)
        self.setStyleSheet("""
            QDialog { background-color: #0c0c14; }
            QLabel { color: #c8ccd4; font-size:12px; background:transparent; }
            QLineEdit {
                background-color: #10101a;
                color: #c8ccd4;
                border: 1px solid #1e1e2c;
                border-radius: 4px;
                padding: 6px 10px;
                font-size:12px;
            }
            QLineEdit:focus { border-color: #06b6d4; }
            QComboBox {
                background-color: #10101a;
                color: #c8ccd4;
                border: 1px solid #1e1e2c;
                border-radius: 4px;
                padding: 6px 10px;
                font-size:12px;
            }
            QComboBox::drop-down { border:none; width:20px; }
            QComboBox QAbstractItemView {
                background-color: #101018;
                border: 1px solid #1e1e2c;
                color: #c8ccd4;
                selection-background-color: #1a1a2a;
            }
        """)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(8)
        form = QtWidgets.QFormLayout()

        self._name = QtWidgets.QLineEdit()
        self._name.setPlaceholderText("e.g. ollama")
        form.addRow("Name:", self._name)

        self._base_url = QtWidgets.QLineEdit()
        self._base_url.setPlaceholderText(
            "e.g. http://localhost:11434/v1")
        form.addRow("Base URL:", self._base_url)

        self._api_type = QtWidgets.QComboBox()
        self._api_type.addItems([
            "openai-completions",
            "anthropic-messages",
            "google-generative-ai",
            "openai-responses",
        ])
        form.addRow("API Type:", self._api_type)

        self._models = QtWidgets.QLineEdit()
        self._models.setPlaceholderText(
            "e.g. llama3.1:8b, qwen2.5-coder:7b")
        form.addRow("Models (comma-separated):", self._models)

        layout.addLayout(form)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _validate_and_accept(self):
        if not self._name.text().strip() or not self._base_url.text().strip():
            return
        self.accept()

    def get_provider_data(self) -> dict:
        return {
            "name": self._name.text().strip(),
            "baseUrl": self._base_url.text().strip(),
            "api": self._api_type.currentText(),
            "models": self._models.text().strip(),
        }


# ═══════════════════════════════════════════════════════════════════════
# Helper Functions
# ═══════════════════════════════════════════════════════════════════════

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
    return (
        f"#{min(255, int(r + (255 - r) * a)):02x}"
        f"{min(255, int(g + (255 - g) * a)):02x}"
        f"{min(255, int(b + (255 - b) * a)):02x}"
    )


def _darker(h: str, a: float) -> str:
    h = _expand_hex(h)
    r, g, b = int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)
    return (
        f"#{max(0, int(r * (1 - a))):02x}"
        f"{max(0, int(g * (1 - a))):02x}"
        f"{max(0, int(b * (1 - a))):02x}"
    )


def _expand_hex(h: str) -> str:
    if len(h) == 4:
        return f"#{h[1]}{h[1]}{h[2]}{h[2]}{h[3]}{h[3]}"
    if len(h) == 5:
        return (
            f"#{h[1]}{h[1]}{h[2]}{h[2]}"
            f"{h[3]}{h[3]}{h[4]}{h[4]}"
        )
    return h
