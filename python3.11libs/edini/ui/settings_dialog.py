"""Settings dialog — tabbed: Providers & Models + Appearance + Knowledge.

Provider/model configuration uses pi-ai data bridge for auto-synced
provider lists. Login/logout flow inspired by pi CLI's /login, /logout,
/model commands.

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
    get_pi_ai_providers, get_pi_ai_models, get_pi_ai_vision_models,
    get_provider_auth_status, get_configured_providers,
)
from edini.ui.theme import THEMES, get_theme, set_theme, set_font_scale, fs
from edini.ui.knowledge_store import rules_count, entries_count, load_rules
from edini.ui.provider_list_dialog import ProviderListDialog
from edini.ui.api_key_dialog import ApiKeyDialog


class SettingsDialog(QtWidgets.QDialog):
    """Settings dialog with three tabs: Providers & Models, Appearance, Knowledge."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._needs_restart = False
        self.setWindowTitle("Edini Settings")
        self.setMinimumSize(560, 640)
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
            QComboBox::drop-down {{
                border: none;
                width: 24px;
            }}
            QComboBox::down-arrow {{
                width: 10px;
                height: 10px;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid #52525b;
            }}
            QComboBox:hover::down-arrow {{
                border-top-color: #71717a;
            }}
            QComboBox QAbstractItemView {{
                background-color: #181824;
                border: 1px solid #2a2a3c;
                selection-background-color: rgba(6, 182, 212, 0.2);
                selection-color: #e5e5eb;
                color:#c8ccd4;
                outline: none;
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
            QTableWidget {{
                background-color: #0e0e16;
                color: #c8ccd4;
                border: 1px solid #1e1e2c;
                border-radius: 4px;
                gridline-color: #1a1a2a;
                font-size:{fs(11)};
            }}
            QTableWidget::item {{
                padding: 4px 8px;
                background: transparent;
            }}
            QHeaderView::section {{
                background-color: #0c0c14;
                color: #71717a;
                padding: 4px 8px;
                border: none;
                border-bottom: 1px solid #1e1e2c;
                font-size:{fs(10)};
            }}
            QTabBar::tab:selected {{
                background: #0c0c14;
                color: #e5e5eb;
                font-weight: 600;
            }}
        """)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Tabs
        self._tabs = QtWidgets.QTabWidget()
        self._tabs.addTab(
            self._build_providers_models_tab(), "\U0001f50c Providers & Models")
        self._tabs.addTab(
            self._build_appearance_tab(), "\U0001f3a8 Appearance")
        self._tabs.addTab(
            self._build_knowledge_tab(get_settings()), "\U0001f4da Knowledge")
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
    # Tab 1: Providers & Models
    # ═══════════════════════════════════════════════════════════════════

    def _build_providers_models_tab(self) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(w)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)

        # ── Section 1: Configured Providers ──
        layout.addWidget(_section_label("Configured Providers"))
        self._auth_table = QtWidgets.QTableWidget(0, 3)
        self._auth_table.setHorizontalHeaderLabels(
            ["Provider", "Auth Source", ""])
        self._auth_table.horizontalHeader().setSectionResizeMode(
            0, QtWidgets.QHeaderView.Stretch)
        self._auth_table.horizontalHeader().setSectionResizeMode(
            1, QtWidgets.QHeaderView.Stretch)
        self._auth_table.horizontalHeader().setSectionResizeMode(
            2, QtWidgets.QHeaderView.Fixed)
        self._auth_table.horizontalHeader().resizeSection(2, 80)
        self._auth_table.verticalHeader().setVisible(False)
        self._auth_table.setEditTriggers(
            QtWidgets.QAbstractItemView.NoEditTriggers)
        self._auth_table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectRows)
        self._auth_table.setSelectionMode(
            QtWidgets.QAbstractItemView.NoSelection)
        self._auth_table.setMaximumHeight(180)
        self._populate_configured_providers()
        layout.addWidget(self._auth_table)

        # Login + Custom provider buttons
        btn_row = QtWidgets.QHBoxLayout()
        login_btn = QtWidgets.QPushButton("+ Login Provider")
        login_btn.setStyleSheet(_btn_style("#0E7490"))
        login_btn.clicked.connect(self._on_login_provider)
        btn_row.addWidget(login_btn)

        custom_btn = QtWidgets.QPushButton("+ Custom Provider")
        custom_btn.setStyleSheet(_btn_style("#1e1e2c", "#a1a1aa"))
        custom_btn.clicked.connect(self._on_add_custom_provider)
        btn_row.addWidget(custom_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # ── Separator ──
        sep = QtWidgets.QFrame()
        sep.setFrameShape(QtWidgets.QFrame.HLine)
        sep.setStyleSheet("color:#1e1e2c;")
        layout.addWidget(sep)

        # ── Section 2: Chat Model ──
        layout.addWidget(_section_label("Chat Model"))

        chat_row = QtWidgets.QHBoxLayout()
        chat_row.addWidget(QtWidgets.QLabel("Provider:"))
        self._chat_provider = QtWidgets.QComboBox()
        self._chat_provider.setEditable(False)
        chat_row.addWidget(self._chat_provider, 1)
        chat_row.addWidget(QtWidgets.QLabel("Model:"))
        self._chat_model = QtWidgets.QComboBox()
        self._chat_model.setEditable(True)
        self._chat_model.setInsertPolicy(QtWidgets.QComboBox.NoInsert)
        self._chat_model.lineEdit().setPlaceholderText("model name...")
        chat_row.addWidget(self._chat_model, 1)
        layout.addLayout(chat_row)

        thinking_row = QtWidgets.QHBoxLayout()
        thinking_row.addWidget(QtWidgets.QLabel("Thinking:"))
        self._thinking_combo = QtWidgets.QComboBox()
        self._thinking_combo.addItems(
            ["off", "minimal", "low", "medium", "high", "xhigh"])
        thinking_row.addWidget(self._thinking_combo)
        thinking_row.addStretch()
        layout.addLayout(thinking_row)

        self._chat_provider.currentIndexChanged.connect(
            lambda: self._on_chat_provider_changed(
                self._chat_provider.currentData() or ""))

        # ── Separator ──
        sep2 = QtWidgets.QFrame()
        sep2.setFrameShape(QtWidgets.QFrame.HLine)
        sep2.setStyleSheet("color:#1e1e2c;")
        layout.addWidget(sep2)

        # ── Section 3: Vision Model ──
        layout.addWidget(_section_label("Vision Model"))

        vision_row = QtWidgets.QHBoxLayout()
        vision_row.addWidget(QtWidgets.QLabel("Provider:"))
        self._vision_provider = QtWidgets.QComboBox()
        self._vision_provider.setEditable(False)
        vision_row.addWidget(self._vision_provider, 1)
        vision_row.addWidget(QtWidgets.QLabel("Model:"))
        self._vision_model = QtWidgets.QComboBox()
        self._vision_model.setEditable(True)
        self._vision_model.setInsertPolicy(QtWidgets.QComboBox.NoInsert)
        self._vision_model.lineEdit().setPlaceholderText("vision model id...")
        vision_row.addWidget(self._vision_model, 1)
        layout.addLayout(vision_row)

        self._vision_provider.currentIndexChanged.connect(
            lambda: self._on_vision_provider_changed(
                self._vision_provider.currentData() or ""))

        # ── Initialize values ──
        self._populate_chat_and_vision()

        hint = QtWidgets.QLabel(
            "\U0001f4a1 Provider data auto-synced from installed pi-ai package. "
            "Run <code>pi /login</code> in terminal for OAuth providers "
            "(Claude Pro, ChatGPT Plus, GitHub Copilot).")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color:#52525b;font-size:{fs(9)};padding:4px 0;")
        layout.addWidget(hint)

        layout.addStretch()
        return w

    def _populate_configured_providers(self) -> None:
        """Fill the configured providers table."""
        self._auth_table.setRowCount(0)
        providers = get_configured_providers()
        for p in providers:
            row = self._auth_table.rowCount()
            self._auth_table.insertRow(row)
            self._auth_table.setItem(
                row, 0, QtWidgets.QTableWidgetItem(p["name"]))
            source_text = p.get("source", "")
            hint = p.get("hint", "")
            display = source_text
            if hint and source_text == "auth.json":
                display = f"{source_text}: {hint}"
            elif hint and source_text == "env":
                display = f"env: {hint}"
            self._auth_table.setItem(
                row, 1, QtWidgets.QTableWidgetItem(display))
            btn = QtWidgets.QPushButton("Logout")
            btn.setStyleSheet("color:#ef4444;border:none;font-size:10px;")
            btn.clicked.connect(
                lambda *a, pid=p["id"]: self._on_logout_provider(pid))
            self._auth_table.setCellWidget(row, 2, btn)

    def _populate_chat_and_vision(self) -> None:
        """Initialize chat model and vision model dropdowns."""
        pi_sett = read_pi_settings()
        settings = get_settings()

        # ── Chat model ──
        configured = get_configured_providers()
        self._chat_provider.blockSignals(True)
        self._chat_provider.clear()
        for p in configured:
            self._chat_provider.addItem(p["name"], p["id"])

        current_provider = pi_sett.get("defaultProvider", "")
        idx = self._chat_provider.findData(current_provider)
        if idx >= 0:
            self._chat_provider.setCurrentIndex(idx)

        # Populate models for current provider
        self._chat_model.clear()
        if current_provider:
            self._on_chat_provider_changed(current_provider)
            current_model = pi_sett.get("defaultModel", "")
            midx = self._chat_model.findData(current_model)
            if midx >= 0:
                self._chat_model.setCurrentIndex(midx)
            elif current_model:
                self._chat_model.setCurrentText(current_model)
        self._chat_provider.blockSignals(False)

        current_thinking = pi_sett.get("defaultThinkingLevel", "medium")
        tidx = self._thinking_combo.findText(current_thinking)
        if tidx >= 0:
            self._thinking_combo.setCurrentIndex(tidx)

        # ── Vision model — only show configured providers ──
        self._vision_provider.blockSignals(True)
        self._vision_provider.clear()
        vision_all = get_pi_ai_vision_models()
        vision_by_provider = {}
        for m in vision_all:
            vision_by_provider.setdefault(m["provider"], []).append(m)
        provider_names = {p["id"]: p["name"]
                          for p in get_pi_ai_providers()}

        for p in configured:
            pid = p["id"]
            name = provider_names.get(pid, p["name"])
            self._vision_provider.addItem(name, pid)

        vision_provider = settings.get("vision_provider", "")
        vidx = self._vision_provider.findData(vision_provider)
        if vidx >= 0:
            self._vision_provider.setCurrentIndex(vidx)
            self._on_vision_provider_changed(vision_provider)
            vision_model = settings.get("vision_model_id", "")
            vmidx = self._vision_model.findData(vision_model)
            if vmidx >= 0:
                self._vision_model.setCurrentIndex(vmidx)
        self._vision_provider.blockSignals(False)

    def _on_chat_provider_changed(self, provider_id: str) -> None:
        """Update chat model dropdown when provider changes."""
        current = self._chat_model.currentData()
        self._chat_model.clear()
        if not provider_id:
            return
        models = get_pi_ai_models(provider_id)
        # Also include custom models from models.json
        custom = read_pi_models().get("providers", {}).get(provider_id, {})
        for m in custom.get("models", []):
            mid = m.get("id", "")
            mname = m.get("name", mid)
            # Don't duplicate if already in bridge data
            if not any(bm["id"] == mid for bm in models):
                models.append({"id": mid, "name": mname,
                               "reasoning": False, "input": ["text"]})

        for m in models:
            name = m.get("name", m["id"])
            if m.get("reasoning"):
                name += "  [R]"
            self._chat_model.addItem(name, m["id"])

        if current:
            idx = self._chat_model.findData(current)
            if idx >= 0:
                self._chat_model.setCurrentIndex(idx)

    def _on_vision_provider_changed(self, provider_id: str) -> None:
        """Update vision model dropdown when provider changes."""
        current = self._vision_model.currentData()
        self._vision_model.clear()
        if not provider_id:
            return
        # Get vision models from pi-ai for this provider
        all_vision = get_pi_ai_vision_models()
        provider_models = [m for m in all_vision
                           if m["provider"] == provider_id]
        # Check if this is a custom provider (not in pi-ai)
        pi_ai_ids = {p["id"] for p in get_pi_ai_providers()}
        is_custom = provider_id not in pi_ai_ids
        # Add custom models from models.json
        custom = read_pi_models().get("providers", {}).get(provider_id, {})
        for m in custom.get("models", []):
            mid = m.get("id", "")
            mname = m.get("name", mid)
            inputs = m.get("input", None)
            # Include if: custom provider (show all), or explicitly has image
            if is_custom or (inputs and "image" in inputs):
                if not any(vm["id"] == mid for vm in provider_models):
                    provider_models.append(
                        {"id": mid, "name": mname, "provider": provider_id})

        for m in provider_models:
            name = m.get("name", m["id"])
            self._vision_model.addItem(name, m["id"])

        if current:
            idx = self._vision_model.findData(current)
            if idx >= 0:
                self._vision_model.setCurrentIndex(idx)

    # ── Login / Logout / Custom Provider ──

    def _on_login_provider(self) -> None:
        """Open provider selector for login."""
        # Start with all pi-ai built-in providers
        all_providers = get_pi_ai_providers()
        configured_ids = {p["id"] for p in get_configured_providers()}
        providers = []
        for p in all_providers:
            p_copy = dict(p)
            p_copy["_configured"] = p["id"] in configured_ids
            providers.append(p_copy)

        # Also include custom providers from models.json
        pi_ai_ids = {p["id"] for p in all_providers}
        for pid, pconf in read_pi_models().get("providers", {}).items():
            if pid not in pi_ai_ids:
                providers.append({
                    "id": pid,
                    "name": pconf.get("name", pid),
                    "modelCount": len(pconf.get("models", [])),
                    "imageModelCount": sum(
                        1 for m in pconf.get("models", [])
                        if "image" in m.get("input", ["text"])
                    ),
                    "_configured": pid in configured_ids,
                })

        dlg = ProviderListDialog(
            self, providers,
            "Select Provider to Login", show_badges=True)
        if dlg.exec() == QtWidgets.QDialog.Accepted and dlg.selected:
            provider = dlg.selected
            provider_id = provider["id"]
            provider_name = provider.get("name", provider_id)

            # Check if already configured
            status = get_provider_auth_status(provider_id)
            if status["configured"]:
                QtWidgets.QMessageBox.information(
                    self, "Already Configured",
                    f"{provider_name} is already configured "
                    f"(source: {status['source']}).\n\n"
                    f"Logout first to reconfigure.")
                return

            # Show API key input
            key_dlg = ApiKeyDialog(self, provider_name)
            if key_dlg.exec() == QtWidgets.QDialog.Accepted:
                # If provider has models.json config, write key there
                models = read_pi_models()
                prov_config = models.get("providers", {}).get(provider_id)
                if prov_config is not None:
                    prov_config["apiKey"] = key_dlg.api_key
                    write_pi_models(models)
                else:
                    # Built-in provider: write to auth.json
                    auth = read_pi_auth()
                    auth[provider_id] = {
                        "type": "api_key", "key": key_dlg.api_key}
                    write_pi_auth(auth)
                self._needs_restart = True
                # Refresh UI
                self._populate_configured_providers()
                self._populate_chat_and_vision()

    def _on_logout_provider(self, provider_id: str) -> None:
        """Remove provider credentials from auth.json and/or models.json."""
        changed = False
        # Remove from auth.json
        auth = read_pi_auth()
        if provider_id in auth:
            del auth[provider_id]
            write_pi_auth(auth)
            changed = True
        # Remove apiKey from models.json
        models = read_pi_models()
        prov = models.get("providers", {}).get(provider_id, {})
        if prov.get("apiKey"):
            del prov["apiKey"]
            write_pi_models(models)
            changed = True
        if changed:
            self._needs_restart = True
            self._populate_configured_providers()
            self._populate_chat_and_vision()

    def _on_add_custom_provider(self) -> None:
        """Add a custom provider (Ollama, LM Studio, etc.)."""
        dlg = _AddProviderDialog(self)
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            data = dlg.get_provider_data()
            models = read_pi_models()
            providers = models.setdefault("providers", {})
            providers[data["name"]] = {
                "baseUrl": data["baseUrl"],
                "api": data["api"],
                "models": [
                    {"id": m.strip()}
                    for m in data["models"].split(",") if m.strip()
                ],
            }
            api_key = data.get("apiKey", "")
            if api_key:
                providers[data["name"]]["apiKey"] = api_key
            write_pi_models(models)
            self._needs_restart = True
            self._populate_configured_providers()
            self._populate_chat_and_vision()

    # ═══════════════════════════════════════════════════════════════════
    # Tab 2: Appearance
    # ═══════════════════════════════════════════════════════════════════

    def _build_appearance_tab(self) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(w)
        layout.setSpacing(12)
        layout.setContentsMargins(12, 12, 12, 12)

        settings = get_settings()

        # Theme
        layout.addWidget(_section_label("Theme"))
        theme_row = QtWidgets.QHBoxLayout()
        theme_row.addWidget(QtWidgets.QLabel("Color:"))
        self._theme_combo = QtWidgets.QComboBox()
        current_theme = settings.get("theme_color", "cyan")
        for key, info in THEMES.items():
            self._theme_combo.addItem(info["name"], key)
            if key == current_theme:
                self._theme_combo.setCurrentIndex(
                    self._theme_combo.count() - 1)
        theme_row.addWidget(self._theme_combo)
        theme_row.addStretch()
        layout.addLayout(theme_row)

        # Font
        layout.addWidget(_section_label("Font Size"))
        font_row = QtWidgets.QHBoxLayout()
        font_row.addWidget(QtWidgets.QLabel("Scale:"))
        self._font_scale = QtWidgets.QComboBox()
        current_scale = str(settings.get("font_scale", 1.0))
        for val in ["0.8", "0.9", "1.0", "1.1", "1.2", "1.3", "1.4"]:
            self._font_scale.addItem(val)
        self._font_scale.setCurrentText(current_scale)
        font_row.addWidget(self._font_scale)
        font_row.addStretch()
        layout.addLayout(font_row)

        layout.addStretch()
        return w

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
        self._knowledge_check.setChecked(
            settings.get("knowledge_enabled", True))
        self._knowledge_check.setStyleSheet(
            f"QCheckBox {{ color:#e5e5eb; font-size:{fs(12)}; spacing:8px; }}")
        layout.addWidget(self._knowledge_check)

        # Reflection model
        model_row = QtWidgets.QHBoxLayout()
        model_row.setSpacing(6)
        model_label = QtWidgets.QLabel("反思模型:")
        model_label.setStyleSheet(f"color:#e5e5eb;font-size:{fs(11)};")
        model_label.setFixedWidth(60)
        model_row.addWidget(model_label)

        self._reflect_provider_combo = QtWidgets.QComboBox()
        self._reflect_provider_combo.addItem("默认（对话模型）", "")
        self._reflect_provider_combo.setStyleSheet(f"""
            QComboBox {{
                background: #1a1a24; color: #e5e5eb;
                border: 1px solid #2a2a3c; border-radius: 4px;
                padding: 3px 6px; font-size: {fs(11)};
                min-width: 120px;
            }}
            QComboBox::drop-down {{ border: none; }}
        """)
        # Populate from pi auth
        from edini.config import read_pi_auth
        for pid in read_pi_auth().keys():
            self._reflect_provider_combo.addItem(pid, pid)
        # Restore saved value
        saved_prov = settings.get("reflection_provider", "")
        idx = self._reflect_provider_combo.findData(saved_prov)
        if idx >= 0:
            self._reflect_provider_combo.setCurrentIndex(idx)
        model_row.addWidget(self._reflect_provider_combo, 1)

        self._reflect_model_edit = QtWidgets.QLineEdit()
        self._reflect_model_edit.setPlaceholderText("默认（对话模型）")
        self._reflect_model_edit.setText(settings.get("reflection_model", ""))
        self._reflect_model_edit.setStyleSheet(f"""
            QLineEdit {{
                background: #1a1a24; color: #e5e5eb;
                border: 1px solid #2a2a3c; border-radius: 4px;
                padding: 3px 6px; font-size: {fs(11)};
            }}
        """)
        self._reflect_model_edit.setFixedWidth(140)
        model_row.addWidget(self._reflect_model_edit)

        layout.addLayout(model_row)

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
        # Chat model
        chat_prov_id = self._chat_provider.currentData() or ""
        chat_model_id = (
            self._chat_model.currentData()
            or self._chat_model.currentText().strip())
        thinking = self._thinking_combo.currentText()

        pi_sett = read_pi_settings()
        pi_sett["defaultProvider"] = chat_prov_id
        pi_sett["defaultModel"] = chat_model_id
        pi_sett["defaultThinkingLevel"] = thinking
        write_pi_settings(pi_sett)

        # Vision model
        vision_prov_id = self._vision_provider.currentData() or ""
        vision_model_id = self._vision_model.currentData() or ""

        save_settings({
            "knowledge_enabled": self._knowledge_check.isChecked(),
            "vision_provider": vision_prov_id,
            "vision_model_id": vision_model_id,
            "reflection_provider": self._reflect_provider_combo.currentData(),
            "reflection_model": self._reflect_model_edit.text().strip(),
        })

        # Theme + font
        theme_key = self._theme_combo.currentData()
        if theme_key:
            set_theme(theme_key)

        font_val = float(self._font_scale.currentText())
        set_font_scale(font_val)

        # Apply to running pi
        from edini.ui.windows import _main_window
        if _main_window:
            _main_window.refresh_theme()
            rpc = _main_window._rpc_client
            rpc.send_set_model(chat_prov_id, chat_model_id)

            if self._needs_restart:
                self._needs_restart = False
                try:
                    rpc.status_changed.disconnect(self._on_restart_done)
                except TypeError:
                    pass
                rpc.status_changed.connect(self._on_restart_done)
                rpc.restart()

        self.accept()

    def _on_restart_done(self, status: str):
        """After Pi restarts, re-send the model config."""
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
# Add Provider Dialog (custom providers like Ollama)
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

        self._api_key = QtWidgets.QLineEdit()
        self._api_key.setEchoMode(QtWidgets.QLineEdit.Password)
        self._api_key.setPlaceholderText("Optional — leave empty for local models")
        form.addRow("API Key:", self._api_key)

        layout.addLayout(form)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok
            | QtWidgets.QDialogButtonBox.Cancel)
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
            "apiKey": self._api_key.text().strip(),
        }


# ═══════════════════════════════════════════════════════════════════════
# Helper Functions
# ═══════════════════════════════════════════════════════════════════════

def _section_label(text: str) -> QtWidgets.QLabel:
    lbl = QtWidgets.QLabel(f"<b>{text}</b>")
    lbl.setStyleSheet(f"color:#c8ccd4;font-size:{fs(12)};font-weight:600;")
    return lbl


def _btn_style(bg: str, fg: str = "#e5e5eb") -> str:
    return f"""
        QPushButton {{
            background: {bg};
            color: {fg};
            border: none;
            border-radius: 4px;
            padding: 6px 16px;
            font-size: {fs(11)};
        }}
        QPushButton:hover {{ background: {_lighter(bg, 0.15)}; }}
        QPushButton:pressed {{ background: {_darker(bg, 0.15)}; }}
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
