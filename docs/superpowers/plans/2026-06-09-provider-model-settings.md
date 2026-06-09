# Provider & Model Settings Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure settings dialog into 3 tabs (Providers & Models, Appearance, Knowledge) with pi CLI-inspired login/logout/model flow, vision model support, and auto-synced provider data from pi-ai.

**Architecture:** Node.js bridge (`pi_data_bridge.js`) reads installed pi-ai package data. Python calls it via subprocess and caches results. Settings dialog uses searchable list dialogs for provider selection (like pi CLI's OAuthSelectorComponent). Chat and vision model dropdowns are populated from bridge data, filtered by auth status.

**Tech Stack:** PySide6 (Qt), Node.js subprocess, pi-ai models.generated.js

---

## File Structure

| Action | File | Responsibility |
|--------|------|---------------|
| Existing | `python3.11libs/edini/pi_data_bridge.js` | Node.js bridge to read pi-ai provider/model data |
| Modify | `python3.11libs/edini/config.py` | Add bridge call helpers + caching |
| Modify | `python3.11libs/edini/ui/settings_dialog.py` | Major rewrite: 3 tabs, new layout |
| Unchanged | `python3.11libs/edini/ui/windows.py` | No changes needed (singleton pattern works as-is) |
| Unchanged | `python3.11libs/edini/ui/theme.py` | No changes needed |
| Unchanged | `python3.11libs/edini/ui/knowledge_store.py` | No changes needed |

---

### Task 1: Add Python bridge helpers to config.py

**Files:**
- Modify: `python3.11libs/edini/config.py` (add after the existing `get_model_history` function at end of file)

- [ ] **Step 1: Add bridge helpers**

Add these functions after the existing code at the end of `config.py`:

```python
# ═══════════════════════════════════════════════════════════════════════
# Pi-AI Data Bridge (auto-synced provider/model data)
# ═══════════════════════════════════════════════════════════════════════

import subprocess

_BRIDGE_SCRIPT = Path(__file__).resolve().parent / "pi_data_bridge.js"
_providers_cache: list[dict] | None = None
_models_cache: dict[str, list[dict]] = {}
_vision_models_cache: list[dict] | None = None


def _run_bridge(*args: str) -> Any:
    """Run pi_data_bridge.js and return parsed JSON output."""
    cmd = ["node", str(_BRIDGE_SCRIPT)] + list(args)
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout.strip())
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        pass
    return None


def get_pi_ai_providers() -> list[dict]:
    """Get all providers from pi-ai. Cached for process lifetime.
    Returns list of {id, name, modelCount, imageModelCount}."""
    global _providers_cache
    if _providers_cache is None:
        _providers_cache = _run_bridge("providers") or []
    return _providers_cache


def get_pi_ai_models(provider: str) -> list[dict]:
    """Get models for a provider from pi-ai. Cached per provider.
    Returns list of {id, name, reasoning, input}."""
    if provider not in _models_cache:
        data = _run_bridge("models", provider) or []
        _models_cache[provider] = data
    return _models_cache[provider]


def get_pi_ai_vision_models() -> list[dict]:
    """Get all vision-capable models from pi-ai. Cached.
    Returns list of {provider, id, name, reasoning}."""
    global _vision_models_cache
    if _vision_models_cache is None:
        _vision_models_cache = _run_bridge("vision-models") or []
    return _vision_models_cache


def get_provider_auth_status(provider: str) -> dict:
    """Check auth status for a provider.
    Returns {configured: bool, source: str|None, hint: str|None}.
    Priority: auth.json > models.json > env var."""
    # Check auth.json
    auth = read_pi_auth()
    if provider in auth:
        entry = auth[provider]
        if isinstance(entry, dict) and entry.get("type") == "api_key":
            key = entry.get("key", "")
            hint = key[:8] + "..." + key[-4:] if len(key) > 12 else key
            return {"configured": True, "source": "auth.json", "hint": hint}

    # Check models.json
    models = read_pi_models()
    prov_config = models.get("providers", {}).get(provider, {})
    if prov_config.get("apiKey"):
        return {"configured": True, "source": "models.json",
                "hint": prov_config["apiKey"][:20] + "..."}

    # Check env vars
    env_map = {
        "anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY", "google": "GEMINI_API_KEY",
        "mistral": "MISTRAL_API_KEY", "groq": "GROQ_API_KEY",
        "cerebras": "CEREBRAS_API_KEY", "xai": "XAI_API_KEY",
        "openrouter": "OPENROUTER_API_KEY", "nvidia": "NVIDIA_API_KEY",
        "fireworks": "FIREWORKS_API_KEY", "together": "TOGETHER_API_KEY",
        "huggingface": "HF_TOKEN", "zai": "ZAI_API_KEY",
        "zai-coding-cn": "ZAI_CODING_CN_API_KEY",
        "opencode": "OPENCODE_API_KEY",
        "kimi-coding": "KIMI_API_KEY",
        "minimax": "MINIMAX_API_KEY", "minimax-cn": "MINIMAX_CN_API_KEY",
        "xiaomi": "XIAOMI_API_KEY",
    }
    env_var = env_map.get(provider, "")
    if env_var and os.environ.get(env_var):
        return {"configured": True, "source": "env", "hint": env_var}

    return {"configured": False, "source": None, "hint": None}


def get_configured_providers() -> list[dict]:
    """Get list of providers that have auth configured.
    Returns list of {id, name, source, hint}."""
    all_providers = get_pi_ai_providers()
    # Also include providers from auth.json/models.json not in pi-ai
    extra_ids = set()
    for p in read_pi_auth().keys():
        extra_ids.add(p)
    for p in read_pi_models().get("providers", {}).keys():
        extra_ids.add(p)

    result = []
    for p in all_providers:
        status = get_provider_auth_status(p["id"])
        if status["configured"]:
            result.append({
                "id": p["id"], "name": p["name"],
                "source": status["source"], "hint": status["hint"],
            })

    # Add custom providers from models.json not in pi-ai list
    pi_ai_ids = {p["id"] for p in all_providers}
    for pid in sorted(extra_ids - pi_ai_ids):
        status = get_provider_auth_status(pid)
        if status["configured"]:
            display = read_pi_models().get("providers", {}).get(pid, {})
            result.append({
                "id": pid,
                "name": display.get("name", pid),
                "source": status["source"],
                "hint": status["hint"],
            })

    return result
```

- [ ] **Step 2: Add `import sys` if not already present**

Check the top of `config.py` — it already has `import os` and `import json`. Add `import sys` to the existing imports block if missing:

```python
import json
import os
import sys
from pathlib import Path
from typing import Any
```

- [ ] **Step 3: Verify bridge works from Python**

```bash
cd E:/edini && python -c "from python3.11libs.edini.config import get_pi_ai_providers; print(len(get_pi_ai_providers()), 'providers')"
```

Expected: `35 providers`

- [ ] **Step 4: Commit**

```bash
git add python3.11libs/edini/config.py
git commit -m "feat: add pi-ai data bridge helpers to config.py"
```

---

### Task 2: Create ProviderListDialog (searchable provider selector)

**Files:**
- Create: `python3.11libs/edini/ui/provider_list_dialog.py`

This is the pi CLI-style selector used for both login (pick a provider to add) and model selection (pick provider to configure model for).

- [ ] **Step 1: Create the dialog**

Create `python3.11libs/edini/ui/provider_list_dialog.py`:

```python
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
            # Use a label for rich text
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
```

- [ ] **Step 2: Commit**

```bash
git add python3.11libs/edini/ui/provider_list_dialog.py
git commit -m "feat: add searchable provider list dialog"
```

---

### Task 3: Create ApiKeyDialog

**Files:**
- Create: `python3.11libs/edini/ui/api_key_dialog.py`

Simple dialog that asks for an API key after a provider is selected.

- [ ] **Step 1: Create the dialog**

Create `python3.11libs/edini/ui/api_key_dialog.py`:

```python
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
```

- [ ] **Step 2: Commit**

```bash
git add python3.11libs/edini/ui/api_key_dialog.py
git commit -m "feat: add API key input dialog"
```

---

### Task 4: Rewrite settings_dialog.py — full rewrite

**Files:**
- Rewrite: `python3.11libs/edini/ui/settings_dialog.py`

This is the main task. Complete rewrite of the settings dialog with 3 tabs.

- [ ] **Step 1: Write the complete new settings_dialog.py**

```python
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
    PI_MODELS_FILE,
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

        self._chat_provider.currentTextChanged.connect(
            self._on_chat_provider_changed)

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
        self._vision_model.setEditable(False)
        vision_row.addWidget(self._vision_model, 1)
        layout.addLayout(vision_row)

        self._vision_provider.currentTextChanged.connect(
            self._on_vision_provider_changed)

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
                lambda checked, pid=p["id"]: self._on_logout_provider(pid))
            self._auth_table.setCellWidget(row, 2, btn)

    def _populate_chat_and_vision(self) -> None:
        """Initialize chat model and vision model dropdowns."""
        pi_sett = read_pi_settings()
        settings = get_settings()

        # ── Chat model ──
        configured = get_configured_providers()
        self._chat_provider.clear()
        for p in configured:
            self._chat_provider.addItem(p["name"], p["id"])

        current_provider = pi_sett.get("defaultProvider", "")
        idx = self._chat_provider.findData(current_provider)
        if idx >= 0:
            self._chat_provider.setCurrentIndex(idx)

        # Populate models for current provider
        if current_provider:
            self._on_chat_provider_changed(current_provider)
            current_model = pi_sett.get("defaultModel", "")
            midx = self._chat_model.findData(current_model)
            if midx >= 0:
                self._chat_model.setCurrentIndex(midx)
            elif current_model:
                self._chat_model.setCurrentText(current_model)

        current_thinking = pi_sett.get("defaultThinkingLevel", "medium")
        tidx = self._thinking_combo.findText(current_thinking)
        if tidx >= 0:
            self._thinking_combo.setCurrentIndex(tidx)

        # ── Vision model ──
        self._vision_provider.clear()
        # Only show providers that have vision-capable models
        vision_all = get_pi_ai_vision_models()
        vision_provider_ids = sorted({m["provider"] for m in vision_all})
        # Also include configured custom providers
        for p in configured:
            if p["id"] not in vision_provider_ids:
                vision_provider_ids.append(p["id"])

        provider_names = {p["id"]: p["name"]
                          for p in get_pi_ai_providers()}
        for pid in vision_provider_ids:
            name = provider_names.get(pid, pid)
            self._vision_provider.addItem(name, pid)

        vision_provider = settings.get("vision_provider", "")
        vidx = self._vision_provider.findData(vision_provider)
        if vidx >= 0:
            self._vision_provider.setCurrentIndex(vidx)

        if vision_provider:
            self._on_vision_provider_changed(vision_provider)
            vision_model = settings.get("vision_model_id", "")
            vmidx = self._vision_model.findData(vision_model)
            if vmidx >= 0:
                self._vision_model.setCurrentIndex(vmidx)

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
                name += " ✦"
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
        # Get all vision models and filter by provider
        all_vision = get_pi_ai_vision_models()
        provider_models = [m for m in all_vision if m["provider"] == provider_id]
        # Also check custom models from models.json
        custom = read_pi_models().get("providers", {}).get(provider_id, {})
        for m in custom.get("models", []):
            mid = m.get("id", "")
            mname = m.get("name", mid)
            inputs = m.get("input", ["text"])
            if "image" in inputs and not any(
                    vm["id"] == mid for vm in provider_models):
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
        # Get all pi-ai providers, mark which are already configured
        all_providers = get_pi_ai_providers()
        configured_ids = {p["id"] for p in get_configured_providers()}
        # Show all providers (user can see which they haven't configured yet)
        providers = []
        for p in all_providers:
            p_copy = dict(p)
            p_copy["_configured"] = p["id"] in configured_ids
            providers.append(p_copy)

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
                auth = read_pi_auth()
                auth[provider_id] = {
                    "type": "api_key", "key": key_dlg.api_key}
                write_pi_auth(auth)
                self._needs_restart = True
                # Refresh UI
                self._populate_configured_providers()
                self._populate_chat_and_vision()

    def _on_logout_provider(self, provider_id: str) -> None:
        """Remove provider credentials."""
        auth = read_pi_auth()
        if provider_id in auth:
            del auth[provider_id]
            write_pi_auth(auth)
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
                "apiKey": (
                    "$" + data["name"].upper().replace("-", "_") + "_API_KEY"
                ),
                "models": [
                    {"id": m.strip()}
                    for m in data["models"].split(",") if m.strip()
                ],
            }
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
        f"#{max(0, int(b * (1 - a))):02x}"
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
```

- [ ] **Step 2: Verify no import errors**

```bash
cd E:/edini && python -c "from python3.11libs.edini.ui.settings_dialog import SettingsDialog; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add python3.11libs/edini/ui/settings_dialog.py
git commit -m "feat: rewrite settings dialog with providers & models + appearance + vision model"
```

---

### Task 5: Fix windows.py — reset singleton on settings close

**Files:**
- Modify: `python3.11libs/edini/ui/windows.py`

The settings dialog singleton should be reset on close so it picks up new data on next open.

- [ ] **Step 1: Update open_settings to always create fresh dialog**

Replace the `open_settings` function in `windows.py`:

```python
def open_settings():
    global _settings_dialog
    # Always create fresh to pick up latest auth/model data
    from edini.ui.settings_dialog import SettingsDialog
    _settings_dialog = SettingsDialog(
        _main_parent() if _main_window else None)
    _settings_dialog.show()
    _settings_dialog.raise_()
    _settings_dialog.activateWindow()
    return _settings_dialog
```

- [ ] **Step 2: Commit**

```bash
git add python3.11libs/edini/ui/windows.py
git commit -m "fix: always create fresh settings dialog to reflect latest data"
```

---

### Task 6: Smoke test and fix issues

- [ ] **Step 1: Run bridge from Python**

```bash
cd E:/edini && python -c "
from python3.11libs.edini.config import (
    get_pi_ai_providers, get_pi_ai_models,
    get_pi_ai_vision_models, get_configured_providers
)
providers = get_pi_ai_providers()
print(f'{len(providers)} providers from bridge')
configured = get_configured_providers()
print(f'{len(configured)} configured: {[p[\"id\"] for p in configured]}')
models = get_pi_ai_models('deepseek')
print(f'DeepSeek models: {[m[\"id\"] for m in models]}')
vision = get_pi_ai_vision_models()
print(f'{len(vision)} vision models')
"
```

Expected: Provider count, configured providers matching auth.json, model lists.

- [ ] **Step 2: Run import check for all modified modules**

```bash
cd E:/edini && python -c "
from python3.11libs.edini.config import get_pi_ai_providers, get_configured_providers
from python3.11libs.edini.ui.provider_list_dialog import ProviderListDialog
from python3.11libs.edini.ui.api_key_dialog import ApiKeyDialog
from python3.11libs.edini.ui.settings_dialog import SettingsDialog
print('All imports OK')
"
```

Expected: `All imports OK`

- [ ] **Step 3: Fix any issues found, then commit**

```bash
git add -A
git commit -m "fix: resolve smoke test issues"
```

---

## Self-Review Checklist

1. **Spec coverage:**
   - ✅ 3 tabs (Providers & Models, Appearance, Knowledge)
   - ✅ Login flow with searchable provider list
   - ✅ Logout per provider
   - ✅ Chat model with provider→model cascade
   - ✅ Vision model with provider→model cascade (image-only filter)
   - ✅ Auto-sync via pi_data_bridge.js
   - ✅ Custom provider support preserved
   - ✅ Appearance (theme + font) in separate tab
   - ✅ Knowledge tab unchanged

2. **Placeholder scan:** No TBDs, TODOs, or vague steps.

3. **Type consistency:** All function signatures match across tasks. `get_configured_providers()` returns `list[dict]` with `{id, name, source, hint}` — consistent with usage in settings_dialog.py.
