"""Settings dialog — tabbed: General + Vision + Knowledge."""
from PySide6 import QtCore, QtWidgets
from edini.config import get_settings, save_settings, add_model_history, get_model_history
from edini.ui.theme import THEMES, get_theme, set_theme, set_font_scale, fs
from edini.ui.knowledge_store import rules_count, entries_count, load_rules
import json
import threading
import urllib.request
import urllib.error
import os

PROVIDERS = ["deepseek", "anthropic", "openai", "google", "zhipu"]
VISION_PROVIDERS = [
    "deepseek", "anthropic", "openai", "google", "aliyun", "openrouter", "zhipu",
]


class SettingsDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edini Settings")
        self.setMinimumSize(520, 580)
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
        self._tabs.addTab(self._build_vision_tab(settings), "Vision")
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
            f"→ {settings.get('provider', 'deepseek')} / {settings.get('model_id', 'deepseek-chat')}"
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

        # Test button
        self._test_model_btn = QtWidgets.QPushButton("🧪 Test Model Connection")
        self._test_model_btn.setStyleSheet(_test_btn_style())
        self._test_model_btn.clicked.connect(self._on_test_main_model)
        layout.addWidget(self._test_model_btn)

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

    # ── Vision Tab ──

    def _build_vision_tab(self, settings: dict) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(w)
        layout.setSpacing(10)
        layout.setContentsMargins(12, 12, 12, 12)

        # Description
        desc = QtWidgets.QLabel(
            "配置一个视觉模型用于描述图片。\n"
            "当使用 text-only 模型（如 DeepSeek）时，pi-visionizer 会自动将图片通过视觉模型转为文本描述。"
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color:#71717a;font-size:{fs(10)};padding:4px 0;")
        layout.addWidget(desc)

        # Vision Provider
        layout.addWidget(_section_label("Vision Provider"))
        self._vision_provider = QtWidgets.QComboBox()
        for p in VISION_PROVIDERS:
            self._vision_provider.addItem(p)
        vp = settings.get("vision_provider", "")
        if vp:
            idx = self._vision_provider.findText(vp)
            if idx >= 0:
                self._vision_provider.setCurrentIndex(idx)
        else:
            # Default to google (free tier available)
            idx = self._vision_provider.findText("google")
            if idx >= 0:
                self._vision_provider.setCurrentIndex(idx)
        layout.addWidget(self._vision_provider)

        # Vision Model
        layout.addWidget(_section_label("Vision Model"))
        self._vision_model = QtWidgets.QComboBox()
        self._vision_model.setEditable(True)
        self._vision_model.setInsertPolicy(QtWidgets.QComboBox.NoInsert)
        self._vision_model.lineEdit().setPlaceholderText("e.g. gemini-2.5-flash")
        # Populate common vision models
        _populate_vision_models(self._vision_provider.currentText(), self._vision_model)
        vm = settings.get("vision_model_id", "")
        if vm:
            self._vision_model.setCurrentText(vm)
        layout.addWidget(self._vision_model)

        self._vision_provider.currentTextChanged.connect(
            lambda p: _populate_vision_models(p, self._vision_model)
        )

        # Vision API Key
        layout.addWidget(_section_label("Vision API Key"))
        vapi_row = QtWidgets.QHBoxLayout()
        self._vision_api_key = QtWidgets.QLineEdit()
        self._vision_api_key.setEchoMode(QtWidgets.QLineEdit.Password)
        self._vision_api_key.setPlaceholderText("Leave empty to use same key as General tab")
        self._vision_api_key.setText(settings.get("vision_api_key", ""))
        vapi_row.addWidget(self._vision_api_key)
        vshow_btn = QtWidgets.QPushButton("Show")
        vshow_btn.setFixedWidth(60)
        vshow_btn.setCheckable(True)
        vshow_btn.toggled.connect(
            lambda v: self._vision_api_key.setEchoMode(
                QtWidgets.QLineEdit.Normal if v else QtWidgets.QLineEdit.Password))
        vapi_row.addWidget(vshow_btn)
        layout.addLayout(vapi_row)

        # Hint about API key
        key_hint = QtWidgets.QLabel(
            "💡 如果视觉模型使用与主模型相同的 provider，可留空此字段（自动使用 General 页的 API Key）"
        )
        key_hint.setWordWrap(True)
        key_hint.setStyleSheet(f"color:#52525b;font-size:{fs(9)};padding:2px 0;")
        layout.addWidget(key_hint)

        # Test Vision button
        self._test_vision_btn = QtWidgets.QPushButton("🧪 Test Vision Model Connection")
        self._test_vision_btn.setStyleSheet(_test_btn_style())
        self._test_vision_btn.clicked.connect(self._on_test_vision)
        layout.addWidget(self._test_vision_btn)

        # Status display
        self._vision_status = QtWidgets.QLabel("")
        self._vision_status.setWordWrap(True)
        self._vision_status.setStyleSheet(f"font-size:{fs(10)};padding:4px;")
        layout.addWidget(self._vision_status)

        # Recommended models card
        card = QtWidgets.QFrame()
        card.setStyleSheet("""
            QFrame {
                background: #10101a;
                border: 1px solid #1e1e2c;
                border-radius: 6px;
            }
        """)
        card_layout = QtWidgets.QVBoxLayout(card)
        card_layout.setContentsMargins(12, 10, 12, 10)
        card_layout.setSpacing(4)
        card_title = QtWidgets.QLabel("<b>推荐视觉模型</b>")
        card_title.setStyleSheet(f"color:#c8ccd4;font-size:{fs(11)};")
        card_layout.addWidget(card_title)
        for line in [
            "🟢 Google Gemini 2.5 Flash — 免费层，速度快，视觉强",
            "🔵 Anthropic Claude Sonnet 4 — 最佳视觉理解，适合复杂 UI",
            "🟡 OpenAI GPT-4.1 Mini — 性价比高，普适性强",
            "🔴 Aliyun Qwen-VL-Max — 国内速度快，中文支持好",
        ]:
            lbl = QtWidgets.QLabel(line)
            lbl.setStyleSheet(f"color:#71717a;font-size:{fs(9)};")
            card_layout.addWidget(lbl)
        layout.addWidget(card)

        layout.addStretch()
        return w

    # ── Knowledge Tab ──

    def _build_knowledge_tab(self, settings: dict) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(w)
        layout.setSpacing(12)
        layout.setContentsMargins(12, 12, 12, 12)

        # Enable
        self._knowledge_check = QtWidgets.QCheckBox("对话结束后自动提取知识（AI 反思 → 用户确认 → 存入铁律/知识库）")
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
        r = rules_count()
        e = entries_count()
        defaults_count = sum(1 for r2 in load_rules() if r2.get("id", "").startswith("rule00"))
        self._rules_stats.setText(f"铁律: {r} 条" + (f"（含 {defaults_count} 条默认）" if defaults_count else ""))
        self._entries_stats.setText(f"知识库: {e} 条")

    # ── Model Test ──

    def _on_test_main_model(self):
        """Test the main LLM API connection."""
        provider = self._provider.currentText()
        model = self._model_combo.currentText().strip()
        api_key = self._api_key.text().strip()
        btn = self._test_model_btn

        # Immediate visual feedback (on main thread)
        btn.setEnabled(False)
        btn.setText("⏳ Testing...")
        btn.setStyleSheet(_test_btn_style())

        if not api_key:
            self._show_test_result(btn, "❌ No API key", True)
            return
        if not model:
            self._show_test_result(btn, "❌ No model specified", True)
            return

        def _run():
            try:
                result_text, is_err = _call_test_api_via_tool_executor(provider, model, api_key)
            except Exception as exc:
                result_text = f"❌ Exception: {exc}"
                is_err = True
            QtCore.QTimer.singleShot(0, lambda: self._show_test_result(btn, result_text, is_err))

        t = threading.Thread(target=_run, daemon=True)
        t.start()

    def _show_test_result(self, btn: QtWidgets.QPushButton, text: str, is_error: bool = False):
        """Update button to show test result, then restore after 3s."""
        btn.setEnabled(True)
        if is_error:
            btn.setStyleSheet(_test_result_style(False))
            btn.setText(f"❌ {text[:50]}")
        else:
            btn.setStyleSheet(_test_result_style(True))
            btn.setText(f"✅ OK")
        QtCore.QTimer.singleShot(3000, lambda: (
            btn.setStyleSheet(_test_btn_style()),
            btn.setText("🧪 Test Model Connection" if btn is self._test_model_btn else "🧪 Test Vision Model Connection"),
        ))

    def _on_test_vision(self):
        """Test vision model connection."""
        provider = self._vision_provider.currentText()
        model = self._vision_model.currentText().strip()
        api_key = self._vision_api_key.text().strip()
        # Fallback to main API key
        if not api_key:
            api_key = self._api_key.text().strip()

        # Immediate visual feedback
        btn = self._test_vision_btn
        btn.setEnabled(False)
        btn.setText("⏳ Testing...")
        btn.setStyleSheet(_test_btn_style())
        self._vision_status.setStyleSheet(f"color:#eab308;font-size:{fs(10)};padding:4px;")
        self._vision_status.setText("⏳ Testing vision model...")

        if not api_key:
            self._vision_status.setText("❌ No API key available")
            self._show_test_result(btn, "❌ No API key", True)
            return
        if not model:
            self._vision_status.setText("❌ No model specified")
            self._show_test_result(btn, "❌ No model", True)
            return

        def _run():
            try:
                result_text, is_err = _call_test_api_via_tool_executor(provider, model, api_key)
            except Exception as exc:
                result_text = f"❌ Exception: {exc}"
                is_err = True
            color = "#ef4444" if is_err else "#22c55e"
            QtCore.QTimer.singleShot(0, lambda: (
                self._vision_status.setStyleSheet(
                    f"color:{color};font-size:{fs(10)};padding:4px;"),
                self._vision_status.setText(result_text),
                self._show_test_result(btn, result_text, is_err),
            ))

        t = threading.Thread(target=_run, daemon=True)
        t.start()

    # ── Handlers ──

    def _on_provider_changed(self, text: str):
        self._model_preview.setText(
            f"→ {text} / {self._model_combo.currentText().strip()}")

    def _on_model_changed(self, text: str):
        self._model_preview.setText(
            f"→ {self._provider.currentText()} / {text.strip()}")

    def _open_knowledge_manager(self, tab: str = "rules"):
        from edini.ui.knowledge_dialog import KnowledgeDialog
        dlg = KnowledgeDialog(self)
        if tab == "entries":
            dlg._tabs.setCurrentIndex(1)
        dlg.exec()
        self._refresh_knowledge_stats()

    def _on_save(self):
        provider = self._provider.currentText().strip()
        model = self._model_combo.currentText().strip()
        old_settings = get_settings()

        save_settings({
            "api_key": self._api_key.text().strip(),
            "provider": provider,
            "model_id": model,
            "knowledge_enabled": self._knowledge_check.isChecked(),
            # Vision settings
            "vision_provider": self._vision_provider.currentText().strip(),
            "vision_model_id": self._vision_model.currentText().strip(),
            "vision_api_key": self._vision_api_key.text().strip(),
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
            rpc = _main_window._rpc_client

            # Check if restart is needed (API key or vision config changed)
            old_key = old_settings.get("api_key", "")
            new_key = self._api_key.text().strip()
            old_vp = old_settings.get("vision_provider", "")
            new_vp = self._vision_provider.currentText().strip()
            old_vm = old_settings.get("vision_model_id", "")
            new_vm = self._vision_model.currentText().strip()

            needs_restart = (old_key != new_key or old_vp != new_vp or old_vm != new_vm)

            # Always send set_model to Pi first (works without restart)
            rpc.send_set_model(provider, model)

            if needs_restart:
                # Connect a one-shot handler: after restart completes, re-send model
                try:
                    rpc.status_changed.disconnect(self._on_restart_done)
                except TypeError:
                    pass
                rpc.status_changed.connect(self._on_restart_done)
                rpc.restart()
            else:
                # Model only — no restart needed, set_model already sent
                pass

        self.accept()

    def _on_restart_done(self, status: str):
        """After Pi restarts, re-send the model config."""
        if status == "connected":
            from edini.ui.windows import _main_window
            if _main_window:
                settings = get_settings()
                rpc = _main_window._rpc_client
                rpc.send_set_model(
                    settings.get("provider", "deepseek"),
                    settings.get("model_id", "deepseek-chat"),
                )
            # Disconnect after use
            try:
                from edini.ui.windows import _main_window
                if _main_window:
                    _main_window._rpc_client.status_changed.disconnect(self._on_restart_done)
            except TypeError:
                pass


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


def _test_btn_style() -> str:
    return """
        QPushButton {
            background: #1e293b;
            color: #93c5fd;
            border: 1px solid #334155;
            border-radius: 4px;
            padding: 6px 12px;
            font-size: 10pt;
        }
        QPushButton:hover {
            background: #334155;
            border-color: #3b82f6;
        }
        QPushButton:disabled {
            color: #52525b;
            background: #18181b;
            border-color: #27272a;
        }
    """


def _test_result_style(ok: bool) -> str:
    if ok:
        return """
            QPushButton {
                background: #052e16;
                color: #86efac;
                border: 1px solid #166534;
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 10pt;
            }
        """
    return """
        QPushButton {
            background: #450a0a;
            color: #fca5a5;
            border: 1px solid #7f1d1d;
            border-radius: 4px;
            padding: 6px 12px;
            font-size: 10pt;
        }
    """


def _populate_vision_models(provider: str, combo: QtWidgets.QComboBox):
    """Fill the vision model combo with common models for the selected provider."""
    combo.clear()
    models = {
        "deepseek": ["deepseek-v4-flash", "deepseek-v4-pro"],
        "anthropic": [
            "claude-sonnet-4-20250514", "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022",
        ],
        "openai": [
            "gpt-4.1-mini", "gpt-4o", "gpt-4o-mini",
            "o3", "o4-mini",
        ],
        "google": [
            "gemini-2.5-flash", "gemini-2.5-flash-lite",
            "gemini-2.5-pro", "gemini-2.0-flash",
        ],
        "aliyun": [
            "qwen-vl-max", "qwen-vl-plus", "qwen2.5-vl-72b-instruct",
        ],
        "openrouter": [
            "openai/gpt-4o", "anthropic/claude-sonnet-4",
            "google/gemini-2.5-flash", "qwen/qwen-vl-plus",
        ],
        "zhipu": [
            "glm-5.1", "glm-5", "glm-4.7", "glm-4.6v", "glm-4.5",
        ],
    }
    for m in models.get(provider, []):
        combo.addItem(m)
    combo.setCurrentText(combo.itemText(0) if combo.count() > 0 else "")


def _call_test_api_via_tool_executor(provider: str, model: str, api_key: str) -> tuple[str, bool]:
    """Test API via the tool executor HTTP server (runs inside Houdini's Python).
    Returns (result_text, is_error).
    """
    try:
        import urllib.request
        port = os.environ.get("EDINI_TOOL_PORT", "9876")
        url = f"http://127.0.0.1:{port}/test_model"
        body = json.dumps({
            "provider": provider,
            "model": model,
            "api_key": api_key,
        }).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        resp = urllib.request.urlopen(req, timeout=20)
        data = json.loads(resp.read().decode("utf-8"))

        if data.get("success"):
            reply = data.get("reply", "")
            return f"✅ Connected! Response: {reply[:60]}", False
        else:
            return f"❌ {data.get('error', 'Unknown error')}", True

    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")[:200]
        return f"❌ HTTP {e.code}: {err_body}", True
    except urllib.error.URLError as e:
        return f"❌ Network error: cannot reach tool executor (port {os.environ.get('EDINI_TOOL_PORT', '9876')}): {e.reason}", True
    except Exception as e:
        return f"❌ Error: {e}", True


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
