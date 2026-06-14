# Custom Models Manager — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Master-Detail dialog for managing custom providers/models in `models.json` with validation and connection testing.

**Architecture:** A single new file `custom_models_dialog.py` containing `CustomModelsDialog` (main dialog with splitter), `EditModelDialog` (sub-dialog for model CRUD), and validation/test-connection logic. Entry point is a button in the existing settings dialog tab 1.

**Tech Stack:** PySide6 (Qt 6), Python `urllib.request` for connection testing, existing `edini.config` read/write helpers.

---

### Task 1: Create CustomModelsDialog Shell with Splitter Layout

**Files:**
- Create: `python3.11libs/edini/ui/custom_models_dialog.py`

- [ ] **Step 1: Create the dialog file with imports and class skeleton**

```python
"""Custom Models Manager — Master-Detail dialog for models.json providers."""
from __future__ import annotations

import json
import ssl
import time
import urllib.request
import urllib.error
from typing import Any

from PySide6 import QtCore, QtWidgets

from edini.config import (
    read_pi_models, write_pi_models,
    read_pi_auth, write_pi_auth,
    get_pi_ai_providers,
)
from edini.ui.theme import fs


# ═══════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════

API_TYPES = [
    "openai-completions",
    "openai-responses",
    "anthropic-messages",
    "google-generative-ai",
]

_BUILT_IN_PROVIDERS: set[str] | None = None


def _get_built_in_providers() -> set[str]:
    global _BUILT_IN_PROVIDERS
    if _BUILT_IN_PROVIDERS is None:
        try:
            providers = get_pi_ai_providers()
            _BUILT_IN_PROVIDERS = {p["id"] for p in providers if "id" in p}
        except Exception:
            _BUILT_IN_PROVIDERS = set()
    return _BUILT_IN_PROVIDERS
```

- [ ] **Step 2: Add the main dialog class with splitter layout**

Append to the file:

```python
# ═══════════════════════════════════════════════════════════════════════
# Main Dialog
# ═══════════════════════════════════════════════════════════════════════

class CustomModelsDialog(QtWidgets.QDialog):
    """Master-Detail dialog for managing custom providers in models.json."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Custom Models Manager")
        self.setMinimumSize(720, 500)
        self._needs_restart = False
        self._data: dict[str, Any] = {}
        self._current_provider: str = ""

        self._apply_styles()
        self._build_ui()
        self._load_data()

    def _apply_styles(self):
        self.setStyleSheet(f"""
            QDialog {{ background-color: #0c0c14; }}
            QLabel {{ color: #c8ccd4; font-size:{fs(12)}; background:transparent; }}
            QLineEdit {{
                background-color: #10101a; color: #c8ccd4;
                border: 1px solid #1e1e2c; border-radius: 4px;
                padding: 6px 10px; font-size:{fs(12)};
            }}
            QLineEdit:focus {{ border-color: #06b6d4; }}
            QLineEdit:read-only {{
                background-color: #08080e; color: #71717a;
            }}
            QComboBox {{
                background-color: #10101a; color: #c8ccd4;
                border: 1px solid #1e1e2c; border-radius: 4px;
                padding: 6px 10px; font-size:{fs(12)};
            }}
            QComboBox:focus {{ border-color: #06b6d4; }}
            QComboBox::drop-down {{ border: none; width: 24px; }}
            QComboBox QAbstractItemView {{
                background-color: #181824; border: 1px solid #2a2a3c;
                selection-background-color: rgba(6,182,212,0.2);
                color: #c8ccd4; outline: none;
            }}
            QListWidget {{
                background-color: #0e0e16; color: #c8ccd4;
                border: 1px solid #1e1e2c; border-radius: 4px;
                font-size:{fs(12)}; outline: none;
            }}
            QListWidget::item {{
                padding: 6px 10px; border-radius: 3px;
            }}
            QListWidget::item:selected {{
                background-color: rgba(6,182,212,0.15);
                color: #e5e5eb;
            }}
            QTableWidget {{
                background-color: #0e0e16; color: #c8ccd4;
                border: 1px solid #1e1e2c; border-radius: 4px;
                gridline-color: #1a1a2a; font-size:{fs(11)};
            }}
            QTableWidget::item {{ padding: 4px 8px; background: transparent; }}
            QHeaderView::section {{
                background-color: #0c0c14; color: #71717a;
                padding: 4px 8px; border: none;
                border-bottom: 1px solid #1e1e2c; font-size:{fs(10)};
            }}
            QSpinBox {{
                background-color: #10101a; color: #c8ccd4;
                border: 1px solid #1e1e2c; border-radius: 4px;
                padding: 4px 8px; font-size:{fs(12)};
            }}
            QCheckBox {{ color: #c8ccd4; font-size:{fs(12)}; }}
            QCheckBox::indicator {{
                width: 14px; height: 14px;
                border: 1px solid #3f3f50; border-radius: 3px;
                background: #10101a;
            }}
            QCheckBox::indicator:checked {{
                background: #06b6d4; border-color: #06b6d4;
            }}
            QPushButton {{
                background: #1e1e2c; color: #e5e5eb;
                border: none; border-radius: 4px;
                padding: 6px 16px; font-size:{fs(11)};
            }}
            QPushButton:hover {{ background: #2a2a3c; }}
            QPushButton:pressed {{ background: #151520; }}
        """)

    def _build_ui(self):
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet("QSplitter::handle { background: #1e1e2c; }")

        # ── Left panel ──
        left = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 6, 0)

        left_layout.addWidget(self._make_section_label("Providers"))
        self._provider_list = QtWidgets.QListWidget()
        self._provider_list.currentRowChanged.connect(self._on_provider_selected)
        left_layout.addWidget(self._provider_list, 1)

        btn_row = QtWidgets.QHBoxLayout()
        self._add_btn = QtWidgets.QPushButton("+ Add")
        self._add_btn.clicked.connect(self._on_add_provider)
        btn_row.addWidget(self._add_btn)
        self._del_btn = QtWidgets.QPushButton("Delete")
        self._del_btn.setStyleSheet(
            "QPushButton { color: #ef4444; } QPushButton:hover { background: #1c0c0c; }")
        self._del_btn.clicked.connect(self._on_delete_provider)
        btn_row.addWidget(self._del_btn)
        btn_row.addStretch()
        left_layout.addLayout(btn_row)

        # ── Right panel ──
        right = QtWidgets.QWidget()
        self._right_layout = QtWidgets.QVBoxLayout(right)
        self._right_layout.setContentsMargins(6, 0, 0, 0)
        self._build_detail_panel()

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([200, 500])
        root.addWidget(splitter, 1)

        # ── Bottom buttons ──
        bottom = QtWidgets.QHBoxLayout()
        bottom.addStretch()
        cancel_btn = QtWidgets.QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        bottom.addWidget(cancel_btn)
        save_btn = QtWidgets.QPushButton("Save")
        save_btn.setStyleSheet(
            "QPushButton { background: #0E7490; } QPushButton:hover { background: #0e8da6; }")
        save_btn.clicked.connect(self._on_save)
        bottom.addWidget(save_btn)
        root.addLayout(bottom)

    @staticmethod
    def _make_section_label(text: str) -> QtWidgets.QLabel:
        lbl = QtWidgets.QLabel(f"<b>{text}</b>")
        lbl.setStyleSheet(f"color:#c8ccd4; font-size:{fs(12)}; font-weight:600;")
        return lbl

    # Placeholder methods (implemented in later tasks)
    def _build_detail_panel(self): pass
    def _load_data(self): pass
    def _on_provider_selected(self, row: int): pass
    def _on_add_provider(self): pass
    def _on_delete_provider(self): pass
    def _on_save(self): pass
```

- [ ] **Step 3: Verify the file imports correctly**

Run from the Edini python3.11libs directory:
```powershell
cd F:\zz\Edini\python3.11libs; python -c "from edini.ui.custom_models_dialog import CustomModelsDialog; print('OK')"
```

Expected: `OK` (no import errors)

- [ ] **Step 4: Commit**

```bash
git add python3.11libs/edini/ui/custom_models_dialog.py
git commit -m "feat(settings): add CustomModelsDialog shell with splitter layout"
```

---

### Task 2: Build the Detail Panel (Provider Fields + Models Table + Validation)

**Files:**
- Modify: `python3.11libs/edini/ui/custom_models_dialog.py`

- [ ] **Step 1: Implement `_build_detail_panel`**

Replace the placeholder `_build_detail_panel` with:

```python
    def _build_detail_panel(self):
        layout = self._right_layout

        # ── Provider fields ──
        form = QtWidgets.QFormLayout()
        form.setSpacing(6)

        self._id_edit = QtWidgets.QLineEdit()
        self._id_edit.setPlaceholderText("e.g. aliyun")
        form.addRow("Provider ID:", self._id_edit)

        self._url_edit = QtWidgets.QLineEdit()
        self._url_edit.setPlaceholderText("https://api.example.com/v1")
        self._url_edit.textChanged.connect(self._on_field_changed)
        form.addRow("Base URL:", self._url_edit)

        self._api_combo = QtWidgets.QComboBox()
        self._api_combo.addItems(API_TYPES)
        form.addRow("API Type:", self._api_combo)

        key_row = QtWidgets.QHBoxLayout()
        self._key_edit = QtWidgets.QLineEdit()
        self._key_edit.setEchoMode(QtWidgets.QLineEdit.Password)
        self._key_edit.setPlaceholderText("sk-... or $ENV_VAR")
        self._key_edit.textChanged.connect(self._on_field_changed)
        key_row.addWidget(self._key_edit, 1)
        self._eye_btn = QtWidgets.QPushButton("\U0001f441")
        self._eye_btn.setFixedWidth(32)
        self._eye_btn.setCheckable(True)
        self._eye_btn.toggled.connect(self._toggle_key_visibility)
        key_row.addWidget(self._eye_btn)
        form.addRow("API Key:", key_row)

        layout.addLayout(form)

        # ── Models section ──
        layout.addWidget(self._make_section_label("Models"))
        self._models_table = QtWidgets.QTableWidget(0, 5)
        self._models_table.setHorizontalHeaderLabels(
            ["ID", "Name", "Input", "Context", "MaxTokens"])
        self._models_table.horizontalHeader().setStretchLastSection(True)
        self._models_table.horizontalHeader().setSectionResizeMode(
            0, QtWidgets.QHeaderView.Stretch)
        self._models_table.verticalHeader().setVisible(False)
        self._models_table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectRows)
        self._models_table.setEditTriggers(
            QtWidgets.QAbstractItemView.NoEditTriggers)
        self._models_table.setMaximumHeight(180)
        layout.addWidget(self._models_table)

        model_btns = QtWidgets.QHBoxLayout()
        add_model_btn = QtWidgets.QPushButton("+ Add Model")
        add_model_btn.clicked.connect(self._on_add_model)
        model_btns.addWidget(add_model_btn)
        edit_model_btn = QtWidgets.QPushButton("Edit")
        edit_model_btn.clicked.connect(self._on_edit_model)
        model_btns.addWidget(edit_model_btn)
        del_model_btn = QtWidgets.QPushButton("Delete")
        del_model_btn.setStyleSheet(
            "QPushButton { color: #ef4444; } QPushButton:hover { background: #1c0c0c; }")
        del_model_btn.clicked.connect(self._on_delete_model)
        model_btns.addWidget(del_model_btn)
        model_btns.addStretch()
        layout.addLayout(model_btns)

        # ── Validation section ──
        layout.addWidget(self._make_section_label("Validation"))
        self._validation_area = QtWidgets.QVBoxLayout()
        self._validation_area.setSpacing(2)
        layout.addLayout(self._validation_area)

        test_row = QtWidgets.QHBoxLayout()
        self._test_btn = QtWidgets.QPushButton("Test Connection")
        self._test_btn.setStyleSheet(
            "QPushButton { background: #1a1a2a; } QPushButton:hover { background: #252538; }")
        self._test_btn.clicked.connect(self._on_test_connection)
        test_row.addWidget(self._test_btn)
        self._test_result = QtWidgets.QLabel("")
        test_row.addWidget(self._test_result, 1)
        test_row.addStretch()
        layout.addLayout(test_row)

        layout.addStretch()

    def _toggle_key_visibility(self, visible: bool):
        self._key_edit.setEchoMode(
            QtWidgets.QLineEdit.Normal if visible else QtWidgets.QLineEdit.Password)

    def _on_field_changed(self):
        self._sync_fields_to_data()
        self._run_validation()

    # Placeholder methods for model CRUD (Task 3)
    def _on_add_model(self): pass
    def _on_edit_model(self): pass
    def _on_delete_model(self): pass
    def _on_test_connection(self): pass
```

- [ ] **Step 2: Verify import still works**

```powershell
cd F:\zz\Edini\python3.11libs; python -c "from edini.ui.custom_models_dialog import CustomModelsDialog; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add python3.11libs/edini/ui/custom_models_dialog.py
git commit -m "feat(settings): add detail panel with provider fields, models table, validation area"
```

---

### Task 3: Data Loading, Provider Selection, and Field Sync

**Files:**
- Modify: `python3.11libs/edini/ui/custom_models_dialog.py`

- [ ] **Step 1: Implement `_load_data` and provider list population**

Replace the placeholder `_load_data`:

```python
    def _load_data(self):
        raw = read_pi_models()
        all_providers = raw.get("providers", {})
        built_in = _get_built_in_providers()
        self._data = {
            k: v for k, v in all_providers.items()
            if k not in built_in
        }
        self._refresh_provider_list()

    def _refresh_provider_list(self):
        self._provider_list.blockSignals(True)
        self._provider_list.clear()
        for name in self._data:
            issues = self._validate_provider(name)
            if any(i[0] == "error" for i in issues):
                icon = "✗"
            elif any(i[0] == "warning" for i in issues):
                icon = "⚠"
            else:
                icon = "✓"
            item = QtWidgets.QListWidgetItem(f"{icon}  {name}")
            self._provider_list.addItem(item)
        self._provider_list.blockSignals(False)
        if self._provider_list.count() > 0:
            self._provider_list.setCurrentRow(0)
        else:
            self._clear_detail()
```

- [ ] **Step 2: Implement `_on_provider_selected` and `_populate_detail`**

```python
    def _on_provider_selected(self, row: int):
        if row < 0:
            self._clear_detail()
            return
        names = list(self._data.keys())
        if row >= len(names):
            return
        self._current_provider = names[row]
        self._populate_detail()

    def _populate_detail(self):
        prov = self._data.get(self._current_provider, {})
        self._id_edit.blockSignals(True)
        self._id_edit.setText(self._current_provider)
        self._id_edit.setReadOnly(True)
        self._id_edit.blockSignals(False)

        self._url_edit.blockSignals(True)
        self._url_edit.setText(prov.get("baseUrl", ""))
        self._url_edit.blockSignals(False)

        api = prov.get("api", "openai-completions")
        idx = self._api_combo.findText(api)
        if idx >= 0:
            self._api_combo.setCurrentIndex(idx)

        self._key_edit.blockSignals(True)
        self._key_edit.setText(prov.get("apiKey", ""))
        self._key_edit.blockSignals(False)

        self._populate_models_table(prov.get("models", []))
        self._run_validation()
        self._test_result.setText("")

    def _populate_models_table(self, models: list[dict]):
        self._models_table.setRowCount(0)
        for m in models:
            row = self._models_table.rowCount()
            self._models_table.insertRow(row)
            self._models_table.setItem(row, 0, self._ro_item(m.get("id", "")))
            self._models_table.setItem(row, 1, self._ro_item(m.get("name", "")))
            inp = ", ".join(m.get("input", ["text"]))
            self._models_table.setItem(row, 2, self._ro_item(inp))
            self._models_table.setItem(row, 3, self._ro_item(
                str(m.get("contextWindow", ""))))
            self._models_table.setItem(row, 4, self._ro_item(
                str(m.get("maxTokens", ""))))

    def _clear_detail(self):
        self._current_provider = ""
        self._id_edit.clear()
        self._id_edit.setReadOnly(False)
        self._url_edit.clear()
        self._key_edit.clear()
        self._api_combo.setCurrentIndex(0)
        self._models_table.setRowCount(0)
        self._clear_validation()
        self._test_result.setText("")

    @staticmethod
    def _ro_item(text: str) -> QtWidgets.QTableWidgetItem:
        item = QtWidgets.QTableWidgetItem(text)
        item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEditable)
        return item

    def _sync_fields_to_data(self):
        if not self._current_provider:
            return
        prov = self._data.setdefault(self._current_provider, {})
        prov["baseUrl"] = self._url_edit.text().strip()
        prov["api"] = self._api_combo.currentText()
        prov["apiKey"] = self._key_edit.text().strip()
```

- [ ] **Step 3: Verify import**

```powershell
cd F:\zz\Edini\python3.11libs; python -c "from edini.ui.custom_models_dialog import CustomModelsDialog; print('OK')"
```

- [ ] **Step 4: Commit**

```bash
git add python3.11libs/edini/ui/custom_models_dialog.py
git commit -m "feat(settings): implement data loading, provider selection, field sync"
```

---

### Task 4: Add/Delete Provider

**Files:**
- Modify: `python3.11libs/edini/ui/custom_models_dialog.py`

- [ ] **Step 1: Implement `_on_add_provider`**

Replace the placeholder:

```python
    def _on_add_provider(self):
        name, ok = QtWidgets.QInputDialog.getText(
            self, "New Provider", "Provider ID (e.g. ollama, aliyun):")
        if not ok or not name.strip():
            return
        name = name.strip().lower()
        if name in self._data:
            QtWidgets.QMessageBox.warning(
                self, "Duplicate", f"Provider '{name}' already exists.")
            return
        if name in _get_built_in_providers():
            QtWidgets.QMessageBox.warning(
                self, "Built-in",
                f"'{name}' is a built-in provider. Use 'Login Provider' instead.")
            return
        self._data[name] = {
            "baseUrl": "",
            "api": "openai-completions",
            "apiKey": "",
            "models": [],
        }
        self._refresh_provider_list()
        # Select the new one (last item)
        self._provider_list.setCurrentRow(self._provider_list.count() - 1)
        self._id_edit.setReadOnly(False)
        self._id_edit.setFocus()
```

- [ ] **Step 2: Implement `_on_delete_provider`**

Replace the placeholder:

```python
    def _on_delete_provider(self):
        if not self._current_provider:
            return
        reply = QtWidgets.QMessageBox.question(
            self, "Delete Provider",
            f"Delete provider '{self._current_provider}' and all its models?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        if reply != QtWidgets.QMessageBox.Yes:
            return
        del self._data[self._current_provider]
        self._current_provider = ""
        self._refresh_provider_list()
```

- [ ] **Step 3: Commit**

```bash
git add python3.11libs/edini/ui/custom_models_dialog.py
git commit -m "feat(settings): implement add/delete provider in custom models dialog"
```

---

### Task 5: EditModelDialog and Model CRUD

**Files:**
- Modify: `python3.11libs/edini/ui/custom_models_dialog.py`

- [ ] **Step 1: Add `EditModelDialog` class**

Add before `CustomModelsDialog`:

```python
# ═══════════════════════════════════════════════════════════════════════
# Edit Model Dialog
# ═══════════════════════════════════════════════════════════════════════

class EditModelDialog(QtWidgets.QDialog):
    """Form dialog for adding or editing a single model definition."""

    def __init__(self, parent=None, model_data: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("Edit Model" if model_data else "Add Model")
        self.setMinimumWidth(380)
        self.setStyleSheet("""
            QDialog { background-color: #0c0c14; }
            QLabel { color: #c8ccd4; font-size:12px; background:transparent; }
            QLineEdit {
                background-color: #10101a; color: #c8ccd4;
                border: 1px solid #1e1e2c; border-radius: 4px;
                padding: 6px 10px; font-size:12px;
            }
            QLineEdit:focus { border-color: #06b6d4; }
            QSpinBox {
                background-color: #10101a; color: #c8ccd4;
                border: 1px solid #1e1e2c; border-radius: 4px;
                padding: 4px 8px; font-size:12px;
            }
            QCheckBox { color: #c8ccd4; font-size:12px; }
        """)

        data = model_data or {}
        layout = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QFormLayout()
        form.setSpacing(8)

        self._id_edit = QtWidgets.QLineEdit(data.get("id", ""))
        self._id_edit.setPlaceholderText("e.g. qwen3-vl-plus")
        form.addRow("Model ID:", self._id_edit)

        self._name_edit = QtWidgets.QLineEdit(data.get("name", ""))
        self._name_edit.setPlaceholderText("Optional display name")
        form.addRow("Name:", self._name_edit)

        input_list = data.get("input", ["text"])
        self._input_text = QtWidgets.QCheckBox("text")
        self._input_text.setChecked("text" in input_list)
        self._input_image = QtWidgets.QCheckBox("image")
        self._input_image.setChecked("image" in input_list)
        input_row = QtWidgets.QHBoxLayout()
        input_row.addWidget(self._input_text)
        input_row.addWidget(self._input_image)
        input_row.addStretch()
        form.addRow("Input:", input_row)

        self._ctx_spin = QtWidgets.QSpinBox()
        self._ctx_spin.setRange(1024, 2_000_000)
        self._ctx_spin.setSingleStep(1024)
        self._ctx_spin.setValue(data.get("contextWindow", 32768))
        form.addRow("Context Window:", self._ctx_spin)

        self._max_spin = QtWidgets.QSpinBox()
        self._max_spin.setRange(256, 1_000_000)
        self._max_spin.setSingleStep(256)
        self._max_spin.setValue(data.get("maxTokens", 8192))
        form.addRow("Max Tokens:", self._max_spin)

        self._reasoning_check = QtWidgets.QCheckBox("Reasoning model")
        self._reasoning_check.setChecked(data.get("reasoning", False))
        form.addRow("", self._reasoning_check)

        layout.addLayout(form)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _validate_and_accept(self):
        if not self._id_edit.text().strip():
            self._id_edit.setFocus()
            return
        self.accept()

    def get_model_data(self) -> dict:
        inputs = []
        if self._input_text.isChecked():
            inputs.append("text")
        if self._input_image.isChecked():
            inputs.append("image")
        data: dict[str, Any] = {
            "id": self._id_edit.text().strip(),
            "input": inputs or ["text"],
            "contextWindow": self._ctx_spin.value(),
            "maxTokens": self._max_spin.value(),
        }
        name = self._name_edit.text().strip()
        if name:
            data["name"] = name
        if self._reasoning_check.isChecked():
            data["reasoning"] = True
        return data
```

- [ ] **Step 2: Implement model CRUD methods in `CustomModelsDialog`**

Replace the three placeholder methods:

```python
    def _on_add_model(self):
        if not self._current_provider:
            return
        dlg = EditModelDialog(self)
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            model = dlg.get_model_data()
            prov = self._data[self._current_provider]
            models = prov.setdefault("models", [])
            models.append(model)
            self._populate_models_table(models)
            self._run_validation()
            self._refresh_provider_list()

    def _on_edit_model(self):
        if not self._current_provider:
            return
        row = self._models_table.currentRow()
        if row < 0:
            return
        models = self._data[self._current_provider].get("models", [])
        if row >= len(models):
            return
        dlg = EditModelDialog(self, model_data=models[row])
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            models[row] = dlg.get_model_data()
            self._populate_models_table(models)
            self._run_validation()
            self._refresh_provider_list()

    def _on_delete_model(self):
        if not self._current_provider:
            return
        row = self._models_table.currentRow()
        if row < 0:
            return
        models = self._data[self._current_provider].get("models", [])
        if row >= len(models):
            return
        models.pop(row)
        self._populate_models_table(models)
        self._run_validation()
        self._refresh_provider_list()
```

- [ ] **Step 3: Verify import**

```powershell
cd F:\zz\Edini\python3.11libs; python -c "from edini.ui.custom_models_dialog import CustomModelsDialog, EditModelDialog; print('OK')"
```

- [ ] **Step 4: Commit**

```bash
git add python3.11libs/edini/ui/custom_models_dialog.py
git commit -m "feat(settings): add EditModelDialog and model CRUD operations"
```

---

### Task 6: Validation Engine

**Files:**
- Modify: `python3.11libs/edini/ui/custom_models_dialog.py`

- [ ] **Step 1: Implement `_validate_provider` and `_run_validation`**

Add these methods to `CustomModelsDialog`:

```python
    def _validate_provider(self, name: str) -> list[tuple[str, str]]:
        """Validate a provider. Returns list of (severity, message) tuples.
        severity: 'error', 'warning', 'info'
        """
        issues: list[tuple[str, str]] = []
        prov = self._data.get(name, {})

        api_key = prov.get("apiKey", "")
        if not api_key:
            issues.append(("error",
                "API key required — Pi cannot load models.json without it"))

        base_url = prov.get("baseUrl", "")
        if not base_url:
            issues.append(("error", "Base URL is required"))
        elif not base_url.startswith("http://") and not base_url.startswith("https://"):
            issues.append(("warning",
                "Base URL should start with http:// or https://"))

        models = prov.get("models", [])
        if not models:
            issues.append(("warning", "Provider has no models defined"))

        for m in models:
            if not m.get("id"):
                issues.append(("error", "A model is missing its ID"))
                break

        return issues

    def _run_validation(self):
        self._clear_validation()
        if not self._current_provider:
            return
        issues = self._validate_provider(self._current_provider)
        if not issues:
            self._add_validation_line("success", "✓ All checks passed")
            return
        for severity, msg in issues:
            self._add_validation_line(severity, msg)

    def _add_validation_line(self, severity: str, msg: str):
        colors = {
            "error": "#ef4444",
            "warning": "#d97706",
            "info": "#3b82f6",
            "success": "#16a34a",
        }
        icons = {
            "error": "✗",
            "warning": "⚠",
            "info": "ℹ",
            "success": "✓",
        }
        color = colors.get(severity, "#c8ccd4")
        icon = icons.get(severity, "")
        lbl = QtWidgets.QLabel(f"{icon} {msg}")
        lbl.setStyleSheet(f"color:{color}; font-size:{fs(11)};")
        self._validation_area.addWidget(lbl)

    def _clear_validation(self):
        while self._validation_area.count():
            item = self._validation_area.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
```

- [ ] **Step 2: Commit**

```bash
git add python3.11libs/edini/ui/custom_models_dialog.py
git commit -m "feat(settings): add real-time validation engine for custom providers"
```

---

### Task 7: Test Connection

**Files:**
- Modify: `python3.11libs/edini/ui/custom_models_dialog.py`

- [ ] **Step 1: Implement `_on_test_connection`**

Replace the placeholder:

```python
    def _on_test_connection(self):
        if not self._current_provider:
            return
        prov = self._data.get(self._current_provider, {})
        base_url = prov.get("baseUrl", "").rstrip("/")
        api_key = prov.get("apiKey", "")
        api_type = prov.get("api", "openai-completions")
        models = prov.get("models", [])
        model_id = models[0]["id"] if models else "test"

        if not base_url or not api_key:
            self._test_result.setText("✗ Missing baseUrl or apiKey")
            self._test_result.setStyleSheet(f"color:#ef4444; font-size:{fs(11)};")
            return

        self._test_result.setText("Testing...")
        self._test_result.setStyleSheet(f"color:#a1a1aa; font-size:{fs(11)};")
        QtCore.QCoreApplication.processEvents()

        # Resolve API key (handle $ENV_VAR)
        resolved_key = api_key
        if api_key.startswith("$"):
            import os
            env_name = api_key[1:]
            resolved_key = os.environ.get(env_name, "")
            if not resolved_key:
                self._test_result.setText(f"✗ Env var {env_name} not set")
                self._test_result.setStyleSheet(f"color:#ef4444; font-size:{fs(11)};")
                return

        try:
            url, headers, body = self._build_test_request(
                base_url, api_type, model_id, resolved_key)
            t0 = time.time()
            req = urllib.request.Request(
                url, data=body.encode("utf-8"), headers=headers, method="POST")
            ctx = ssl.create_default_context()
            with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
                status = resp.status
            elapsed = int((time.time() - t0) * 1000)
            self._test_result.setText(f"✓ {status} OK ({elapsed}ms)")
            self._test_result.setStyleSheet(f"color:#16a34a; font-size:{fs(11)};")
        except urllib.error.HTTPError as e:
            self._test_result.setText(f"✗ {e.code} {e.reason}")
            self._test_result.setStyleSheet(f"color:#ef4444; font-size:{fs(11)};")
        except Exception as e:
            msg = str(e)[:60]
            self._test_result.setText(f"✗ {msg}")
            self._test_result.setStyleSheet(f"color:#ef4444; font-size:{fs(11)};")

    @staticmethod
    def _build_test_request(
        base_url: str, api_type: str, model_id: str, api_key: str
    ) -> tuple[str, dict, str]:
        """Build a minimal API request for connection testing."""
        if api_type == "anthropic-messages":
            url = f"{base_url}/messages"
            headers = {
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            }
            body = json.dumps({
                "model": model_id,
                "max_tokens": 1,
                "messages": [{"role": "user", "content": "hi"}],
            })
        elif api_type == "google-generative-ai":
            url = f"{base_url}/models/{model_id}:generateContent?key={api_key}"
            headers = {"Content-Type": "application/json"}
            body = json.dumps({
                "contents": [{"parts": [{"text": "hi"}]}],
                "generationConfig": {"maxOutputTokens": 1},
            })
        elif api_type == "openai-responses":
            url = f"{base_url}/responses"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            }
            body = json.dumps({
                "model": model_id,
                "input": "hi",
                "max_output_tokens": 1,
            })
        else:
            # openai-completions (default)
            url = f"{base_url}/chat/completions"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            }
            body = json.dumps({
                "model": model_id,
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 1,
            })
        return url, headers, body
```

- [ ] **Step 2: Commit**

```bash
git add python3.11libs/edini/ui/custom_models_dialog.py
git commit -m "feat(settings): add test connection with multi-API-type support"
```

---

### Task 8: Save Logic with Validation Gate and auth.json Sync

**Files:**
- Modify: `python3.11libs/edini/ui/custom_models_dialog.py`

- [ ] **Step 1: Implement `_on_save`**

Replace the placeholder:

```python
    def _on_save(self):
        # Validate all providers
        all_errors: list[str] = []
        all_warnings: list[str] = []
        for name in self._data:
            issues = self._validate_provider(name)
            for severity, msg in issues:
                tagged = f"[{name}] {msg}"
                if severity == "error":
                    all_errors.append(tagged)
                elif severity == "warning":
                    all_warnings.append(tagged)

        if all_errors:
            QtWidgets.QMessageBox.critical(
                self, "Cannot Save",
                "Fix the following errors before saving:\n\n"
                + "\n".join(f"• {e}" for e in all_errors))
            return

        # Merge custom providers back into models.json (preserve built-in overrides)
        raw = read_pi_models()
        all_providers = raw.get("providers", {})
        built_in = _get_built_in_providers()

        # Remove old custom providers, keep built-in overrides
        to_remove = [k for k in all_providers if k not in built_in]
        for k in to_remove:
            del all_providers[k]

        # Add updated custom providers
        all_providers.update(self._data)
        raw["providers"] = all_providers
        write_pi_models(raw)

        # Sync literal API keys to auth.json
        auth = read_pi_auth()
        for name, prov in self._data.items():
            api_key = prov.get("apiKey", "")
            if api_key and not api_key.startswith("$") and not api_key.startswith("!"):
                auth[name] = {"type": "api_key", "key": api_key}
        write_pi_auth(auth)

        self._needs_restart = True
        self.accept()

    @property
    def needs_restart(self) -> bool:
        return self._needs_restart
```

- [ ] **Step 2: Commit**

```bash
git add python3.11libs/edini/ui/custom_models_dialog.py
git commit -m "feat(settings): implement save with validation gate and auth.json sync"
```

---

### Task 9: Integrate into Settings Dialog

**Files:**
- Modify: `python3.11libs/edini/ui/settings_dialog.py`

- [ ] **Step 1: Add import**

At line 26 (after the `ApiKeyDialog` import), add:

```python
from edini.ui.custom_models_dialog import CustomModelsDialog
```

- [ ] **Step 2: Replace the "+ Custom Provider" button**

In `_build_providers_models_tab()`, replace lines 188-191:

```python
        custom_btn = QtWidgets.QPushButton("+ Custom Provider")
        custom_btn.setStyleSheet(_btn_style("#1e1e2c", "#a1a1aa"))
        custom_btn.clicked.connect(self._on_add_custom_provider)
        btn_row.addWidget(custom_btn)
```

With:

```python
        custom_btn = QtWidgets.QPushButton("Manage Custom Models")
        custom_btn.setStyleSheet(_btn_style("#1e1e2c", "#a1a1aa"))
        custom_btn.clicked.connect(self._on_manage_custom_models)
        btn_row.addWidget(custom_btn)
```

- [ ] **Step 3: Add the handler method**

Add to the `SettingsDialog` class (near `_on_add_custom_provider`):

```python
    def _on_manage_custom_models(self) -> None:
        """Open the Custom Models Manager dialog."""
        dlg = CustomModelsDialog(self)
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            if dlg.needs_restart:
                self._needs_restart = True
            self._populate_configured_providers()
            self._populate_chat_and_vision()
```

- [ ] **Step 4: Remove old `_on_add_custom_provider` method**

Delete the `_on_add_custom_provider` method (lines 503-524) since it's replaced by the new dialog. Also remove the `_AddProviderDialog` class (lines 898-987) which is no longer needed.

- [ ] **Step 5: Verify import chain**

```powershell
cd F:\zz\Edini\python3.11libs; python -c "from edini.ui.settings_dialog import SettingsDialog; print('OK')"
```

- [ ] **Step 6: Commit**

```bash
git add python3.11libs/edini/ui/settings_dialog.py
git commit -m "feat(settings): wire CustomModelsDialog into settings, remove old AddProviderDialog"
```

---

### Task 10: Copy to edini/ Mirror

**Files:**
- Modify: `edini/ui/` (if mirror pattern exists)

- [ ] **Step 1: Check if edini/ mirror needs updating**

The project has two copies of source: `python3.11libs/edini/` (runtime) and `edini/` (development). Check git status for the pattern:

```powershell
git diff --name-only HEAD
```

If `edini/` files track `python3.11libs/edini/`, copy the new file:

```powershell
Copy-Item "F:\zz\Edini\python3.11libs\edini\ui\custom_models_dialog.py" "F:\zz\Edini\edini\ui\custom_models_dialog.py"
```

- [ ] **Step 2: Commit**

```bash
git add edini/ui/custom_models_dialog.py
git commit -m "chore: sync custom_models_dialog.py to edini/ mirror"
```

---

### Task 11: Manual Smoke Test

- [ ] **Step 1: Launch Edini and open Settings**

Open Houdini with Edini loaded, open Settings dialog.

- [ ] **Step 2: Verify "Manage Custom Models" button is visible**

In the Providers & Models tab, confirm the button replaced "+ Custom Provider".

- [ ] **Step 3: Open the dialog and verify provider list**

Click "Manage Custom Models". Verify:
- Custom providers (aliyun, gmn, GMN, ali) appear in the list
- Built-in providers (deepseek) do NOT appear
- Status icons show correctly (✓ for properly configured, ⚠/✗ for issues)

- [ ] **Step 4: Select a provider and verify detail panel**

Click "aliyun" in the list. Verify:
- Provider ID is shown and read-only
- Base URL, API Type, API Key are populated
- Models table shows the 3 vision models with correct Input tags

- [ ] **Step 5: Test Connection**

Click "Test Connection" for aliyun. Verify it shows "✓ 200 OK (XXXms)" or a meaningful error.

- [ ] **Step 6: Test Add Model flow**

Click "+ Add Model", fill in a test model, confirm it appears in the table.

- [ ] **Step 7: Test Save with validation**

Remove apiKey from a provider, try to Save. Verify error dialog blocks the save. Restore the key, save successfully.

- [ ] **Step 8: Verify Pi restart picks up changes**

After save, confirm Pi restarts and the new configuration is active (vision model works).
