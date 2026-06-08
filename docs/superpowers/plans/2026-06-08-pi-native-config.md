# Pi-Native Model Config Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Edini's custom provider/model/API-key configuration with pi's native config files (`~/.pi/agent/auth.json`, `models.json`, `settings.json`) and add a model selector dropdown in the UI.

**Architecture:** Edini reads/writes pi's standard JSON config files directly from Python. Model discovery uses the RPC `get_available_models` command. Model switching uses `set_model` at runtime without restart. The settings dialog gains an API Keys tab (manages `auth.json`) and a Model tab (manages `models.json` + `settings.json`). Vision tab is removed — pi-visionizer uses the same models.

**Tech Stack:** Python 3.11 / PySide6 / Pi RPC (stdin/stdout JSONL)

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `python3.11libs/edini/config.py` | **Rewrite** | Pi config file read/write helpers, remove old provider/key management |
| `python3.11libs/edini/rpc_client.py` | **Extend** | Add `get_available_models`, `cycle_model`, `set_thinking_level` RPC methods |
| `python3.11libs/edini/ui/settings_dialog.py` | **Rewrite** | 3 tabs: API Keys, Models, Knowledge (remove Vision tab) |
| `python3.11libs/edini/ui/agent_panel.py` | **Extend** | Add model selector dropdown in header bar |

---

## Task 1: Rewrite `config.py` — Pi Config File Helpers

**Files:**
- Modify: `python3.11libs/edini/config.py`

**Reference:** See current `~/.pi/agent/auth.json` format:
```json
{
  "deepseek": { "type": "api_key", "key": "sk-xxx" },
  "zai-coding-cn": { "type": "api_key", "key": "41fc37..." }
}
```

See current `~/.pi/agent/models.json` format:
```json
{
  "providers": {
    "deepseek": {
      "baseUrl": "https://api.deepseek.com/v1",
      "api": "openai-completions",
      "apiKey": "$DEEPSEEK_API_KEY",
      "models": [{ "id": "deepseek-v4-pro", "name": "DeepSeek V4 Pro", ... }]
    }
  }
}
```

See current `~/.pi/agent/settings.json` format:
```json
{
  "defaultProvider": "zai-coding-cn",
  "defaultModel": "glm-5.1",
  "defaultThinkingLevel": "high"
}
```

- [ ] **Step 1: Add pi agent dir constant and file read/write helpers**

Add these to `config.py` (keep existing constants like `PROJECT_ROOT`, `PI_EXECUTABLE`, `PI_EXTENSIONS_DIR`, `TOOL_EXECUTOR_HOST/PORT`, panel dimensions, `_find_pi`):

```python
# Pi agent directory (shared config with pi CLI)
PI_AGENT_DIR = Path.home() / ".pi" / "agent"
PI_AUTH_FILE = PI_AGENT_DIR / "auth.json"
PI_MODELS_FILE = PI_AGENT_DIR / "models.json"
PI_SETTINGS_FILE = PI_AGENT_DIR / "settings.json"

# Edini's own local settings (theme, font, knowledge — NOT provider/model/key)
EDINI_SETTINGS_FILE = Path(__file__).resolve().parent / "settings.json"
```

- [ ] **Step 2: Add pi config read functions**

```python
def read_pi_auth() -> dict:
    """Read ~/.pi/agent/auth.json. Returns {} if missing."""
    if PI_AUTH_FILE.exists():
        try:
            with open(PI_AUTH_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}

def read_pi_models() -> dict:
    """Read ~/.pi/agent/models.json. Returns {} if missing."""
    if PI_MODELS_FILE.exists():
        try:
            with open(PI_MODELS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}

def read_pi_settings() -> dict:
    """Read ~/.pi/agent/settings.json. Returns {} if missing."""
    if PI_SETTINGS_FILE.exists():
        try:
            with open(PI_SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}
```

- [ ] **Step 3: Add pi config write functions (atomic write)**

```python
import tempfile

def _atomic_write_json(path: Path, data: dict) -> None:
    """Write JSON to file atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    tmp.replace(path)

def write_pi_auth(data: dict) -> None:
    """Overwrite ~/.pi/agent/auth.json."""
    _atomic_write_json(PI_AUTH_FILE, data)

def write_pi_models(data: dict) -> None:
    """Overwrite ~/.pi/agent/models.json."""
    _atomic_write_json(PI_MODELS_FILE, data)

def write_pi_settings(data: dict) -> None:
    """Overwrite ~/.pi/agent/settings.json."""
    _atomic_write_json(PI_SETTINGS_FILE, data)
```

- [ ] **Step 4: Simplify Edini's own settings**

Replace `_DEFAULTS` and related functions. Edini's `settings.json` now only holds non-model UI settings:

```python
_EDINI_DEFAULTS: dict[str, Any] = {
    "theme_color": "cyan",
    "font_scale": 1.0,
    "knowledge_enabled": True,
    "vision_provider": "",
    "vision_model_id": "",
}

def _load_edini_settings() -> dict[str, Any]:
    """Load Edini's own UI settings (not provider/model)."""
    if EDINI_SETTINGS_FILE.exists():
        try:
            with open(EDINI_SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {**_EDINI_DEFAULTS, **data}
        except (json.JSONDecodeError, OSError):
            pass
    return dict(_EDINI_DEFAULTS)

def get_settings() -> dict[str, Any]:
    """Get Edini UI settings."""
    return _load_edini_settings()

def save_settings(updates: dict[str, Any]) -> None:
    """Merge updates into Edini settings file."""
    current = _load_edini_settings()
    current.update(updates)
    _atomic_write_json(EDINI_SETTINGS_FILE, current)
```

- [ ] **Step 5: Remove old provider/key code, simplify `get_pi_env()`**

Remove: `_DEFAULTS` (old), `_ENV_MAP`, `_set_provider_api_key()`.

Replace `get_pi_env()` with a simple version that does NOT inject API keys (pi reads auth.json itself):

```python
def get_pi_env() -> dict[str, str]:
    """Build environment dict for Pi subprocess."""
    env = {
        **os.environ,
        "EDINI_TOOL_PORT": str(TOOL_EXECUTOR_PORT),
    }
    # Pi reads ~/.pi/agent/auth.json itself — no env-var key injection needed.
    # But pass vision config for pi-visionizer backward compat during transition.
    settings = get_settings()
    vision_provider = settings.get("vision_provider", "")
    vision_model = settings.get("vision_model_id", "")
    if vision_provider and vision_model:
        env["VISIONIZER_PROVIDER"] = vision_provider
        env["VISIONIZER_MODEL_ID"] = vision_model
    return env
```

- [ ] **Step 6: Add migration helper**

```python
def migrate_legacy_settings() -> str | None:
    """Migrate old api_key/provider/model_id to pi config files.
    Returns migration message or None if nothing to migrate.
    """
    old = _load_edini_settings()
    old_key = old.get("api_key", "")
    old_provider = old.get("provider", "")
    old_model = old.get("model_id", "")

    if not old_key or not old_provider:
        return None

    # Write API key to auth.json
    auth = read_pi_auth()
    if old_provider not in auth:
        auth[old_provider] = {"type": "api_key", "key": old_key}
        write_pi_auth(auth)

    # Write default model to pi settings.json
    pi_settings = read_pi_settings()
    if "defaultProvider" not in pi_settings:
        pi_settings["defaultProvider"] = old_provider
        pi_settings["defaultModel"] = old_model
        write_pi_settings(pi_settings)

    # Remove legacy keys from edini settings
    old.pop("api_key", None)
    old.pop("provider", None)
    old.pop("model_id", None)
    old.pop("vision_api_key", None)
    _atomic_write_json(EDINI_SETTINGS_FILE, old)

    return f"✅ Migrated: {old_provider}/{old_model} → ~/.pi/agent/"
```

- [ ] **Step 7: Commit**

```bash
git add python3.11libs/edini/config.py
git commit -m "refactor: config.py uses pi native config files"
```

---

## Task 2: Extend `rpc_client.py` — Model Discovery RPC

**Files:**
- Modify: `python3.11libs/edini/rpc_client.py`

- [ ] **Step 1: Add new signals to RpcClient**

Add after existing signal definitions in `RpcClient`:

```python
    models_received = Signal(object)        # list of model dicts from get_available_models
    model_changed = Signal(object)          # model dict from set_model / cycle_model
    thinking_changed = Signal(str)          # thinking level from set_thinking_level
```

Add same signals to `_RpcWorker`.

- [ ] **Step 2: Add new RPC send methods to RpcClient**

```python
    def send_get_available_models(self) -> None:
        """Request list of all configured models from Pi."""
        if self._worker:
            self._worker.send_command({"type": "get_available_models"})

    def send_cycle_model(self) -> None:
        """Cycle to the next available model."""
        if self._worker:
            self._worker.send_command({"type": "cycle_model"})

    def send_set_thinking_level(self, level: str) -> None:
        """Set thinking level: off, minimal, low, medium, high, xhigh."""
        if self._worker:
            self._worker.send_command({"type": "set_thinking_level", "level": level})
```

- [ ] **Step 3: Handle new response types in `_RpcWorker._dispatch_event`**

Add to the `elif event_type == "response"` block, after existing response handlers:

```python
            elif event.get("command") == "get_available_models":
                data = event.get("data", {})
                self.models_received.emit(data.get("models", []))
            elif event.get("command") == "set_model":
                data = event.get("data", {})
                if data:
                    self.model_changed.emit(data)
            elif event.get("command") == "cycle_model":
                data = event.get("data", {})
                if data and data.get("model"):
                    self.model_changed.emit(data.get("model"))
                    self.thinking_changed.emit(data.get("thinkingLevel", ""))
            elif event.get("command") == "set_thinking_level":
                # success response — no extra data, level was applied
                pass
            elif event.get("command") == "get_thinking_level":
                data = event.get("data", {})
                if data:
                    self.thinking_changed.emit(data.get("level", ""))
```

- [ ] **Step 4: Wire new signals in `RpcClient.start()`**

Add after existing signal connections:

```python
        self._worker.models_received.connect(self.models_received)
        self._worker.model_changed.connect(self.model_changed)
        self._worker.thinking_changed.connect(self.thinking_changed)
```

- [ ] **Step 5: Commit**

```bash
git add python3.11libs/edini/rpc_client.py
git commit -m "feat: add model discovery RPC methods to rpc_client"
```

---

## Task 3: Rewrite `settings_dialog.py` — Pi-Native Tabs

**Files:**
- Modify: `python3.11libs/edini/ui/settings_dialog.py`

**Reference:** This file currently has 3 tabs: General (provider/model/key), Vision, Knowledge. We replace General with API Keys, Vision with Model Selection, keep Knowledge.

Known pi providers (for the "Add Provider" dropdown):
```python
KNOWN_PROVIDERS = [
    "anthropic", "openai", "deepseek", "google", "mistral", "groq",
    "cerebras", "xai", "openrouter", "nvidia", "fireworks", "together",
    "huggingface", "kimi-coding", "minimax", "minimax-cn", "zai",
    "zai-coding-cn", "xiaomi", "opencode", "aliyun", "zhipu",
]
```

- [ ] **Step 1: Rewrite the class header and constructor**

Keep `SettingsDialog.__init__` structure with tabs, but change tab names:
- Tab 0: "🔑 API Keys" (was General)
- Tab 1: "🤖 Models" (was Vision)
- Tab 2: "📚 Knowledge" (unchanged)

```python
class SettingsDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edini Settings")
        self.setMinimumSize(560, 600)
        # ... same dark theme stylesheet ...
        
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self._tabs = QtWidgets.QTabWidget()
        self._tabs.addTab(self._build_api_keys_tab(), "🔑 API Keys")
        self._tabs.addTab(self._build_models_tab(), "🤖 Models")
        self._tabs.addTab(self._build_knowledge_tab(get_settings()), "📚 Knowledge")
        layout.addWidget(self._tabs, 1)
        
        # Buttons (same as before)
        # ...
```

- [ ] **Step 2: Build API Keys tab**

Read from `read_pi_auth()`, show configured providers with key (masked), add/remove:

```python
    def _build_api_keys_tab(self) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(w)
        layout.setSpacing(10)
        layout.setContentsMargins(12, 12, 12, 12)

        # Header
        header = QtWidgets.QLabel(
            "API keys are stored in <code>~/.pi/agent/auth.json</code><br>"
            "Shared with <b>pi</b> CLI — configure once, use everywhere."
        )
        header.setWordWrap(True)
        header.setStyleSheet(f"color:#71717a;font-size:{fs(10)};padding:4px 0;")
        layout.addWidget(header)

        # Configured providers list
        layout.addWidget(_section_label("Configured Providers"))
        self._auth_table = QtWidgets.QTableWidget(0, 3)
        self._auth_table.setHorizontalHeaderLabels(["Provider", "API Key", ""])
        self._auth_table.horizontalHeader().setStretchLastSection(True)
        self._auth_table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self._auth_table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        self._auth_table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.Fixed)
        self._auth_table.horizontalHeader().resizeSection(2, 80)
        self._auth_table.verticalHeader().setVisible(False)
        self._auth_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self._auth_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self._auth_table.setMaximumHeight(200)
        # Populate
        auth = read_pi_auth()
        self._populate_auth_table(auth)
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
        hint = QtWidgets.QLabel("💡 Advanced: run <code>pi /login</code> in terminal for OAuth providers (Claude Pro, ChatGPT Plus, GitHub Copilot)")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color:#52525b;font-size:{fs(9)};padding:4px 0;")
        layout.addWidget(hint)

        layout.addStretch()
        return w

    def _populate_auth_table(self, auth: dict) -> None:
        self._auth_table.setRowCount(0)
        for provider, entry in auth.items():
            if not isinstance(entry, dict) or entry.get("type") != "api_key":
                continue  # skip OAuth entries
            row = self._auth_table.rowCount()
            self._auth_table.insertRow(row)
            self._auth_table.setItem(row, 0, QtWidgets.QTableWidgetItem(provider))
            key = entry.get("key", "")
            masked = key[:8] + "..." + key[-4:] if len(key) > 12 else key
            self._auth_table.setItem(row, 1, QtWidgets.QTableWidgetItem(masked))
            # Remove button
            btn = QtWidgets.QPushButton("Remove")
            btn.setStyleSheet("color:#ef4444;border:none;font-size:10px;")
            btn.clicked.connect(lambda checked, p=provider: self._on_remove_provider(p))
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
```

- [ ] **Step 3: Build Models tab**

```python
    def _build_models_tab(self) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(w)
        layout.setSpacing(10)
        layout.setContentsMargins(12, 12, 12, 12)

        # Default model section
        layout.addWidget(_section_label("Default Model"))
        pi_sett = read_pi_settings()

        model_row = QtWidgets.QHBoxLayout()
        model_row.addWidget(QtWidgets.QLabel("Provider:"))
        self._default_provider = QtWidgets.QComboBox()
        self._default_provider.setEditable(False)
        # Populate from auth.json keys + models.json provider keys
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
        self._populate_models_for_provider(
            self._default_provider.currentText(), self._default_model)
        current_model = pi_sett.get("defaultModel", "")
        if current_model:
            self._default_model.setCurrentText(current_model)
        model_row.addWidget(self._default_model, 1)
        layout.addLayout(model_row)

        thinking_row = QtWidgets.QHBoxLayout()
        thinking_row.addWidget(QtWidgets.QLabel("Thinking:"))
        self._thinking_combo = QtWidgets.QComboBox()
        self._thinking_combo.addItems(["off", "minimal", "low", "medium", "high", "xhigh"])
        current_thinking = pi_sett.get("defaultThinkingLevel", "medium")
        idx = self._thinking_combo.findText(current_thinking)
        if idx >= 0:
            self._thinking_combo.setCurrentIndex(idx)
        thinking_row.addWidget(self._thinking_combo)
        thinking_row.addStretch()
        layout.addLayout(thinking_row)

        self._default_provider.currentTextChanged.connect(
            lambda p: self._populate_models_for_provider(p, self._default_model))

        # Separator
        sep = QtWidgets.QFrame()
        sep.setFrameShape(QtWidgets.QFrame.HLine)
        sep.setStyleSheet("color:#1e1e2c;")
        layout.addWidget(sep)

        # Custom providers section
        layout.addWidget(_section_label("Custom Providers"))
        layout.addWidget(QtWidgets.QLabel(
            f"From <code>{PI_MODELS_FILE}</code>"
        ))

        self._providers_table = QtWidgets.QTableWidget(0, 3)
        self._providers_table.setHorizontalHeaderLabels(["Provider", "API Type", "Models"])
        self._providers_table.horizontalHeader().setStretchLastSection(True)
        self._providers_table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        self._providers_table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        self._providers_table.verticalHeader().setVisible(False)
        self._providers_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self._providers_table.setMaximumHeight(200)
        self._populate_providers_table()
        layout.addWidget(self._providers_table)

        # Add custom provider button
        add_cp_btn = QtWidgets.QPushButton("+ Add Custom Provider")
        add_cp_btn.setStyleSheet(_btn_style("#0E7490"))
        add_cp_btn.clicked.connect(self._on_add_custom_provider)
        layout.addWidget(add_cp_btn)

        hint = QtWidgets.QLabel("💡 Advanced: edit <code>~/.pi/agent/models.json</code> directly for full control")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color:#52525b;font-size:{fs(9)};padding:4px 0;")
        layout.addWidget(hint)

        layout.addStretch()
        return w

    def _get_all_provider_names(self) -> list[str]:
        """Get all provider names from auth.json + models.json."""
        names = set()
        names.update(read_pi_auth().keys())
        models = read_pi_models()
        names.update(models.get("providers", {}).keys())
        # Also include built-in providers user might want to configure
        for p in KNOWN_PROVIDERS:
            names.add(p)
        return sorted(names)

    def _populate_models_for_provider(self, provider: str, combo: QtWidgets.QComboBox) -> None:
        """Fill model combo with known models for a provider."""
        current = combo.currentText()
        combo.clear()
        models_config = read_pi_models()
        provider_config = models_config.get("providers", {}).get(provider, {})
        for m in provider_config.get("models", []):
            name = m.get("name", m.get("id", ""))
            combo.addItem(name, m.get("id", ""))
        if current:
            combo.setCurrentText(current)

    def _populate_providers_table(self) -> None:
        self._providers_table.setRowCount(0)
        models = read_pi_models()
        for name, config in models.get("providers", {}).items():
            row = self._providers_table.rowCount()
            self._providers_table.insertRow(row)
            self._providers_table.setItem(row, 0, QtWidgets.QTableWidgetItem(name))
            self._providers_table.setItem(row, 1, QtWidgets.QTableWidgetItem(config.get("api", "")))
            model_names = ", ".join(m.get("id", "") for m in config.get("models", []))
            self._providers_table.setItem(row, 2, QtWidgets.QTableWidgetItem(model_names))

    def _on_add_custom_provider(self) -> None:
        """Open a simple dialog to add a custom provider to models.json."""
        dlg = _AddProviderDialog(self)
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            data = dlg.get_provider_data()
            models = read_pi_models()
            providers = models.setdefault("providers", {})
            providers[data["name"]] = {
                "baseUrl": data["baseUrl"],
                "api": data["api"],
                "apiKey": f"${data['name'].upper().replace('-', '_')}_API_KEY",
                "models": [{"id": m.strip()} for m in data["models"].split(",") if m.strip()],
            }
            write_pi_models(models)
            self._populate_providers_table()
            # Refresh provider combo
            self._default_provider.clear()
            self._default_provider.addItems(self._get_all_provider_names())
            self._needs_restart = True
```

- [ ] **Step 4: Add `_AddProviderDialog` helper class**

```python
class _AddProviderDialog(QtWidgets.QDialog):
    """Simple dialog for adding a custom provider to models.json."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Custom Provider")
        self.setMinimumWidth(400)
        # ... dark theme stylesheet ...
        
        layout = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QFormLayout()

        self._name = QtWidgets.QLineEdit()
        self._name.setPlaceholderText("e.g. ollama")
        form.addRow("Name:", self._name)

        self._base_url = QtWidgets.QLineEdit()
        self._base_url.setPlaceholderText("e.g. http://localhost:11434/v1")
        form.addRow("Base URL:", self._base_url)

        self._api_type = QtWidgets.QComboBox()
        self._api_type.addItems(["openai-completions", "anthropic-messages", "google-generative-ai", "openai-responses"])
        form.addRow("API Type:", self._api_type)

        self._models = QtWidgets.QLineEdit()
        self._models.setPlaceholderText("e.g. llama3.1:8b, qwen2.5-coder:7b")
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
```

- [ ] **Step 5: Keep Knowledge tab unchanged**

Copy the existing `_build_knowledge_tab` method verbatim from current code. No changes needed.

- [ ] **Step 6: Rewrite `_on_save` to write pi config files**

```python
    def _on_save(self):
        # Write default model to pi settings.json
        pi_sett = read_pi_settings()
        provider = self._default_provider.currentText()
        model_text = self._default_model.currentText().strip()
        # Get model ID from combo data
        model_id = self._default_model.currentData() or model_text
        thinking = self._thinking_combo.currentText()

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

        # Notify main window
        from edini.ui.windows import _main_window
        if _main_window:
            _main_window.refresh_theme()
            rpc = _main_window._rpc_client

            # Try to set model without restart
            rpc.send_set_model(provider, model_id)

            if getattr(self, '_needs_restart', False):
                self._needs_restart = False
                rpc.restart()

        self.accept()
```

- [ ] **Step 7: Remove Vision tab entirely**

Delete `_build_vision_tab`, `_populate_vision_models`, `_on_test_vision`, `_call_test_api_via_tool_executor`. Remove all vision-related imports and UI elements. Vision model selection is now just "pick an image-capable model" from the Models tab.

- [ ] **Step 8: Commit**

```bash
git add python3.11libs/edini/ui/settings_dialog.py
git commit -m "feat: rewrite settings dialog with pi-native config tabs"
```

---

## Task 4: Add Model Selector Dropdown to Agent Panel

**Files:**
- Modify: `python3.11libs/edini/ui/agent_panel.py`

**Reference:** Read the current agent_panel.py to understand the header layout before editing. The model selector goes in the header area near the settings button.

- [ ] **Step 1: Read current agent_panel.py to understand layout**

```bash
head -150 python3.11libs/edini/ui/agent_panel.py
```

- [ ] **Step 2: Add model dropdown to header**

Find the header section in `_setup_ui` and add a model selector combo:

```python
        # In the header area, add model selector
        self._model_combo = QtWidgets.QComboBox()
        self._model_combo.setMinimumWidth(180)
        self._model_combo.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self._model_combo.setStyleSheet("""
            QComboBox {
                background: #10101a;
                color: #c8ccd4;
                border: 1px solid #1e1e2c;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 11px;
            }
            QComboBox::drop-down { border: none; width: 16px; }
            QComboBox QAbstractItemView {
                background: #101018;
                border: 1px solid #1e1e2c;
                color: #c8ccd4;
                selection-background-color: #1a1a2a;
            }
        """)
        self._model_combo.addItem("Loading models...")
        self._model_combo.currentIndexChanged.connect(self._on_model_selected)
        header.insertWidget(0, self._model_combo)  # before settings button
```

- [ ] **Step 3: Connect RPC signals for model data**

In `_connect_signals`, add:

```python
        self._rpc_client.models_received.connect(self._on_models_received)
        self._rpc_client.model_changed.connect(self._on_model_changed)
        self._rpc_client.status_changed.connect(self._on_rpc_status)
```

- [ ] **Step 4: Implement model handler methods**

```python
    def _on_rpc_status(self, status: str) -> None:
        """When Pi connects, request available models."""
        if status == "connected":
            self._rpc_client.send_get_available_models()

    def _on_models_received(self, models: list) -> None:
        """Populate model dropdown from Pi's model list."""
        self._model_combo.blockSignals(True)
        self._model_combo.clear()

        # Group models by provider
        by_provider: dict[str, list] = {}
        for m in models:
            provider = m.get("provider", "unknown")
            by_provider.setdefault(provider, []).append(m)

        for provider in sorted(by_provider.keys()):
            for m in by_provider[provider]:
                name = m.get("name", m.get("id", ""))
                label = f"{name} ({provider})"
                self._model_combo.addItem(label, m)

        # Try to select the default model
        pi_sett = read_pi_settings()
        default_provider = pi_sett.get("defaultProvider", "")
        default_model = pi_sett.get("defaultModel", "")
        if default_provider and default_model:
            for i in range(self._model_combo.count()):
                m = self._model_combo.itemData(i)
                if (m and m.get("provider") == default_provider 
                        and m.get("id") == default_model):
                    self._model_combo.setCurrentIndex(i)
                    break

        self._model_combo.blockSignals(False)

    def _on_model_selected(self, index: int) -> None:
        """Switch model via RPC when user selects from dropdown."""
        m = self._model_combo.itemData(index)
        if m:
            self._rpc_client.send_set_model(m["provider"], m["id"])

    def _on_model_changed(self, model: dict) -> None:
        """Update status bar after model change."""
        name = model.get("name", model.get("id", "?"))
        provider = model.get("provider", "?")
        self._model_label.setText(f"Model: {name}")
```

- [ ] **Step 5: Commit**

```bash
git add python3.11libs/edini/ui/agent_panel.py
git commit -m "feat: add model selector dropdown in agent panel header"
```

---

## Task 5: Sync `edini/config.py` (simpler version)

**Files:**
- Modify: `edini/config.py`

The `edini/` directory contains a simpler version that's used by the `edini/panel.py` (for quick testing outside Houdini). Sync the key changes:

- [ ] **Step 1: Mirror config.py changes**

Apply the same changes from Task 1 to `edini/config.py`:
- Add `PI_AGENT_DIR`, `PI_AUTH_FILE`, etc. constants
- Add `read_pi_auth()`, `read_pi_models()`, `read_pi_settings()`
- Add `write_pi_auth()`, `write_pi_models()`, `write_pi_settings()`
- Simplify `get_pi_env()` — remove API key injection
- Keep `get_pi_command()` as-is

- [ ] **Step 2: Commit**

```bash
git add edini/config.py
git commit -m "refactor: sync edini/config.py with pi native config helpers"
```

---

## Task 6: Run Migration and Test

**Files:**
- No new files

- [ ] **Step 1: Check current settings.json for legacy keys**

```bash
cat python3.11libs/edini/settings.json
```

If it contains `api_key`, `provider`, `model_id` — migration is needed.

- [ ] **Step 2: Add migration call to startup**

In `python3.11libs/edini/ui/main_window.py` or `__init__.py`, add:

```python
from edini.config import migrate_legacy_settings
msg = migrate_legacy_settings()
if msg:
    print(msg)  # or show as a notification in UI
```

Find the appropriate startup point by reading:

```bash
grep -n "def __init__" python3.11libs/edini/ui/main_window.py | head -5
```

- [ ] **Step 3: Verify config files are correct**

```bash
cat ~/.pi/agent/auth.json
cat ~/.pi/agent/models.json
cat ~/.pi/agent/settings.json
```

- [ ] **Step 4: Manual smoke test**

Launch Houdini, open Edini panel:
1. Check model dropdown populates
2. Switch models via dropdown
3. Open settings → verify API Keys tab shows configured providers
4. Open settings → verify Models tab shows providers from models.json
5. Add a new API key → verify auth.json updates
6. Send a chat message → verify model responds

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: add legacy config migration on startup"
```
