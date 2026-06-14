"""Custom Models Dialog — Master-Detail UI for managing custom AI providers.

Allows adding/editing/deleting custom providers and their models,
validating configuration, testing connections, and syncing to
~/.pi/agent/models.json and auth.json.
"""
import json
import os
import urllib.request
import urllib.error

from PySide6 import QtCore, QtWidgets

from edini.config import (
    read_pi_models, write_pi_models,
    read_pi_auth, write_pi_auth,
    get_pi_ai_providers,
)
from edini.ui.theme import fs

API_TYPES = [
    "openai-completions",
    "openai-responses",
    "anthropic-messages",
    "google-generative-ai",
]

# ── Theme colors ──────────────────────────────────────────────────────
_BG = "#0c0c14"
_SURFACE = "#10101a"
_BORDER = "#1e1e2c"
_TEXT = "#c8ccd4"
_MUTED = "#71717a"
_ACCENT = "#06b6d4"
_SUCCESS = "#16a34a"
_WARNING = "#d97706"
_ERROR = "#ef4444"
_INFO = "#3b82f6"


# ══════════════════════════════════════════════════════════════════════
# EditModelDialog — small form for a single model entry
# ══════════════════════════════════════════════════════════════════════

class EditModelDialog(QtWidgets.QDialog):
    """Dialog for adding or editing a single model definition."""

    def __init__(self, parent=None, model_data: dict | None = None):
        super().__init__(parent)
        self._model = model_data or {}
        self.setWindowTitle("Edit Model" if model_data else "Add Model")
        self.setMinimumWidth(400)
        self.setStyleSheet(f"""
            QDialog {{ background-color: {_BG}; }}
            QLabel {{ color: {_TEXT}; font-size:{fs(12)}; background:transparent; }}
            QLineEdit {{
                background-color: {_SURFACE};
                color: {_TEXT};
                border: 1px solid {_BORDER};
                border-radius: 4px;
                padding: 6px 10px;
                font-size:{fs(12)};
            }}
            QLineEdit:focus {{ border-color: {_ACCENT}; }}
            QSpinBox {{
                background-color: {_SURFACE};
                color: {_TEXT};
                border: 1px solid {_BORDER};
                border-radius: 4px;
                padding: 6px 10px;
                font-size:{fs(12)};
            }}
            QCheckBox {{ color: {_TEXT}; font-size:{fs(11)}; }}
        """)

        layout = QtWidgets.QFormLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        # Model ID
        self._id_edit = QtWidgets.QLineEdit(self._model.get("id", ""))
        self._id_edit.setPlaceholderText("e.g. qwen3-vl-plus")
        layout.addRow("Model ID:", self._id_edit)

        # Display name
        self._name_edit = QtWidgets.QLineEdit(self._model.get("name", ""))
        self._name_edit.setPlaceholderText("e.g. Qwen3 VL Plus")
        layout.addRow("Name:", self._name_edit)

        # Input modalities
        self._input_edit = QtWidgets.QLineEdit(
            ", ".join(self._model.get("input", ["text"])))
        self._input_edit.setPlaceholderText("text, image")
        layout.addRow("Input:", self._input_edit)

        # Context window
        self._context_spin = QtWidgets.QSpinBox()
        self._context_spin.setRange(1024, 2_000_000)
        self._context_spin.setSingleStep(1024)
        self._context_spin.setValue(self._model.get("contextWindow", 131072))
        layout.addRow("Context Window:", self._context_spin)

        # Max tokens
        self._max_tokens_spin = QtWidgets.QSpinBox()
        self._max_tokens_spin.setRange(1, 200_000)
        self._max_tokens_spin.setSingleStep(256)
        self._max_tokens_spin.setValue(self._model.get("maxTokens", 8192))
        layout.addRow("Max Tokens:", self._max_tokens_spin)

        # Reasoning
        self._reasoning_cb = QtWidgets.QCheckBox("Supports reasoning")
        self._reasoning_cb.setChecked(self._model.get("reasoning", False))
        layout.addRow("", self._reasoning_cb)

        # Buttons
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QtWidgets.QPushButton("Cancel")
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_BORDER}; color: #a1a1aa;
                border: none; border-radius: 4px;
                padding: 6px 20px; font-size:{fs(11)};
            }}
            QPushButton:hover {{ background: #2a2a3c; }}
        """)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        ok_btn = QtWidgets.QPushButton("OK")
        ok_btn.setStyleSheet(f"""
            QPushButton {{
                background: #0E7490; color: #e5e5eb;
                border: none; border-radius: 4px;
                padding: 6px 20px; font-size:{fs(11)};
                font-weight: 600;
            }}
            QPushButton:hover {{ background: #0c8fa8; }}
        """)
        ok_btn.clicked.connect(self._on_ok)
        btn_row.addWidget(ok_btn)
        layout.addRow(btn_row)

    def _on_ok(self):
        model_id = self._id_edit.text().strip()
        if not model_id:
            QtWidgets.QMessageBox.warning(
                self, "Validation", "Model ID is required.")
            return
        self.accept()

    def get_model(self) -> dict:
        """Return the model dict from form values."""
        input_str = self._input_edit.text().strip()
        inputs = [s.strip() for s in input_str.split(",") if s.strip()]
        return {
            "id": self._id_edit.text().strip(),
            "name": self._name_edit.text().strip()
                    or self._id_edit.text().strip(),
            "input": inputs or ["text"],
            "contextWindow": self._context_spin.value(),
            "maxTokens": self._max_tokens_spin.value(),
            "reasoning": self._reasoning_cb.isChecked(),
        }



# ══════════════════════════════════════════════════════════════════════
# CustomModelsDialog — Master-Detail provider management
# ══════════════════════════════════════════════════════════════════════

def _resolve_env_key(key: str) -> str:
    """Resolve $ENV_VAR syntax in an API key string."""
    if key.startswith("$"):
        return os.environ.get(key[1:], key)
    return key


def _btn_style(bg: str, fg: str = "#e5e5eb") -> str:
    return f"""
        QPushButton {{
            background: {bg}; color: {fg};
            border: none; border-radius: 4px;
            padding: 6px 14px; font-size:{fs(11)};
        }}
        QPushButton:hover {{ background: {bg}cc; }}
    """


class CustomModelsDialog(QtWidgets.QDialog):
    """Master-Detail dialog for managing custom AI model providers."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._needs_restart = False
        self._providers: dict[str, dict] = {}  # id -> provider data
        self._current_id: str | None = None
        self._builtin_ids: set[str] = set()

        self.setWindowTitle("Custom Model Providers")
        self.setMinimumSize(780, 580)
        self._setup_stylesheet()
        self._load_data()
        self._build_ui()
        self._refresh_provider_list()
        if self._providers:
            first_id = list(self._providers.keys())[0]
            self._select_provider(first_id)

    @property
    def needs_restart(self) -> bool:
        return self._needs_restart

    def _setup_stylesheet(self):
        self.setStyleSheet(f"""
            QDialog {{ background-color: {_BG}; }}
            QLabel {{ color: {_TEXT}; font-size:{fs(12)}; background:transparent; }}
            QLineEdit {{
                background-color: {_SURFACE};
                color: {_TEXT};
                border: 1px solid {_BORDER};
                border-radius: 4px;
                padding: 6px 10px;
                font-size:{fs(12)};
            }}
            QLineEdit:focus {{ border-color: {_ACCENT}; }}
            QComboBox {{
                background-color: {_SURFACE};
                color: {_TEXT};
                border: 1px solid {_BORDER};
                border-radius: 4px;
                padding: 6px 10px;
                font-size:{fs(12)};
            }}
            QComboBox:focus {{ border-color: {_ACCENT}; }}
            QComboBox::drop-down {{ border: none; width: 24px; }}
            QComboBox::down-arrow {{
                width: 10px; height: 10px;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid #52525b;
            }}
            QComboBox QAbstractItemView {{
                background-color: #181824;
                border: 1px solid #2a2a3c;
                selection-background-color: rgba(6, 182, 212, 0.2);
                color: {_TEXT}; outline: none;
            }}
            QListWidget {{
                background-color: {_SURFACE};
                color: {_TEXT};
                border: 1px solid {_BORDER};
                border-radius: 4px;
                font-size:{fs(12)};
                outline: none;
            }}
            QListWidget::item {{
                padding: 6px 10px;
            }}
            QListWidget::item:selected {{
                background: rgba(6, 182, 212, 0.15);
                color: #e5e5eb;
            }}
            QTableWidget {{
                background-color: #0e0e16;
                color: {_TEXT};
                border: 1px solid {_BORDER};
                border-radius: 4px;
                gridline-color: #1a1a2a;
                font-size:{fs(11)};
            }}
            QTableWidget::item {{ padding: 4px 8px; background: transparent; }}
            QHeaderView::section {{
                background-color: {_BG};
                color: {_MUTED};
                padding: 4px 8px;
                border: none;
                border-bottom: 1px solid {_BORDER};
                font-size:{fs(10)};
            }}
        """)

    def _load_data(self):
        """Load providers from models.json and identify built-in IDs."""
        self._builtin_ids = {
            p["id"] for p in get_pi_ai_providers()}
        data = read_pi_models() or {}
        providers_raw = data.get("providers", {})
        # Only load custom (non-built-in) providers
        for pid, pdata in providers_raw.items():
            if pid not in self._builtin_ids:
                self._providers[pid] = dict(pdata)

    def _build_ui(self):
        """Construct the master-detail layout."""
        root = QtWidgets.QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # ── Left panel: provider list ──
        left = QtWidgets.QVBoxLayout()
        left.setSpacing(6)

        lbl = QtWidgets.QLabel("Providers")
        lbl.setStyleSheet(f"font-weight:600;font-size:{fs(13)};")
        left.addWidget(lbl)

        self._provider_list = QtWidgets.QListWidget()
        self._provider_list.currentRowChanged.connect(self._on_list_selection)
        left.addWidget(self._provider_list, 1)

        list_btns = QtWidgets.QHBoxLayout()
        add_btn = QtWidgets.QPushButton("+ Add")
        add_btn.setStyleSheet(_btn_style("#0E7490"))
        add_btn.clicked.connect(self._on_add_provider)
        list_btns.addWidget(add_btn)

        del_btn = QtWidgets.QPushButton("Delete")
        del_btn.setStyleSheet(_btn_style(_BORDER, "#a1a1aa"))
        del_btn.clicked.connect(self._on_delete_provider)
        list_btns.addWidget(del_btn)
        list_btns.addStretch()
        left.addLayout(list_btns)

        left_w = QtWidgets.QWidget()
        left_w.setLayout(left)
        left_w.setFixedWidth(200)
        root.addWidget(left_w)

        # ── Right panel: detail form ──
        right = QtWidgets.QVBoxLayout()
        right.setSpacing(8)

        # Provider fields
        form = QtWidgets.QFormLayout()
        form.setSpacing(8)

        self._id_edit = QtWidgets.QLineEdit()
        self._id_edit.setPlaceholderText("unique-provider-id")
        self._id_edit.textChanged.connect(self._on_field_changed)
        form.addRow("Provider ID:", self._id_edit)

        self._url_edit = QtWidgets.QLineEdit()
        self._url_edit.setPlaceholderText("https://api.example.com/v1")
        self._url_edit.textChanged.connect(self._on_field_changed)
        form.addRow("Base URL:", self._url_edit)

        self._api_type_combo = QtWidgets.QComboBox()
        self._api_type_combo.addItems(API_TYPES)
        self._api_type_combo.currentIndexChanged.connect(self._on_field_changed)
        form.addRow("API Type:", self._api_type_combo)

        # API Key row with eye toggle
        key_row = QtWidgets.QHBoxLayout()
        self._key_edit = QtWidgets.QLineEdit()
        self._key_edit.setEchoMode(QtWidgets.QLineEdit.Password)
        self._key_edit.setPlaceholderText("sk-... or $ENV_VAR")
        self._key_edit.textChanged.connect(self._on_field_changed)
        key_row.addWidget(self._key_edit, 1)

        self._eye_btn = QtWidgets.QPushButton("\U0001f441")
        self._eye_btn.setFixedWidth(32)
        self._eye_btn.setStyleSheet(
            f"border:none;font-size:{fs(14)};background:transparent;")
        self._eye_btn.setCheckable(True)
        self._eye_btn.toggled.connect(self._toggle_key_visibility)
        key_row.addWidget(self._eye_btn)
        form.addRow("API Key:", key_row)

        right.addLayout(form)

        # ── Models table ──
        models_lbl = QtWidgets.QLabel("Models")
        models_lbl.setStyleSheet(f"font-weight:600;font-size:{fs(12)};")
        right.addWidget(models_lbl)

        self._models_table = QtWidgets.QTableWidget(0, 4)
        self._models_table.setHorizontalHeaderLabels(
            ["ID", "Name", "Context", "MaxTok"])
        self._models_table.horizontalHeader().setSectionResizeMode(
            0, QtWidgets.QHeaderView.Stretch)
        self._models_table.horizontalHeader().setSectionResizeMode(
            1, QtWidgets.QHeaderView.Stretch)
        self._models_table.horizontalHeader().setSectionResizeMode(
            2, QtWidgets.QHeaderView.Fixed)
        self._models_table.horizontalHeader().resizeSection(2, 80)
        self._models_table.horizontalHeader().setSectionResizeMode(
            3, QtWidgets.QHeaderView.Fixed)
        self._models_table.horizontalHeader().resizeSection(3, 70)
        self._models_table.verticalHeader().setVisible(False)
        self._models_table.setEditTriggers(
            QtWidgets.QAbstractItemView.NoEditTriggers)
        self._models_table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectRows)
        self._models_table.setSelectionMode(
            QtWidgets.QAbstractItemView.SingleSelection)
        self._models_table.setMaximumHeight(180)
        right.addWidget(self._models_table)

        # Model buttons
        model_btns = QtWidgets.QHBoxLayout()
        add_model_btn = QtWidgets.QPushButton("+ Add Model")
        add_model_btn.setStyleSheet(_btn_style("#0E7490"))
        add_model_btn.clicked.connect(self._on_add_model)
        model_btns.addWidget(add_model_btn)

        edit_model_btn = QtWidgets.QPushButton("Edit")
        edit_model_btn.setStyleSheet(_btn_style(_BORDER, "#a1a1aa"))
        edit_model_btn.clicked.connect(self._on_edit_model)
        model_btns.addWidget(edit_model_btn)

        del_model_btn = QtWidgets.QPushButton("Delete")
        del_model_btn.setStyleSheet(_btn_style(_BORDER, "#a1a1aa"))
        del_model_btn.clicked.connect(self._on_delete_model)
        model_btns.addWidget(del_model_btn)
        model_btns.addStretch()
        right.addLayout(model_btns)

        # ── Validation status ──
        self._validation_label = QtWidgets.QLabel("")
        self._validation_label.setWordWrap(True)
        self._validation_label.setStyleSheet(f"font-size:{fs(10)};")
        right.addWidget(self._validation_label)

        # ── Test connection button ──
        test_row = QtWidgets.QHBoxLayout()
        self._test_btn = QtWidgets.QPushButton("Test Connection")
        self._test_btn.setStyleSheet(_btn_style("#1e1e2c", _INFO))
        self._test_btn.clicked.connect(self._on_test_connection)
        test_row.addWidget(self._test_btn)
        self._test_status = QtWidgets.QLabel("")
        self._test_status.setStyleSheet(f"font-size:{fs(10)};")
        test_row.addWidget(self._test_status, 1)
        right.addLayout(test_row)

        right.addStretch()

        # ── Bottom buttons ──
        bottom = QtWidgets.QHBoxLayout()
        bottom.addStretch()
        cancel_btn = QtWidgets.QPushButton("Cancel")
        cancel_btn.setStyleSheet(_btn_style(_BORDER, "#a1a1aa"))
        cancel_btn.clicked.connect(self.reject)
        bottom.addWidget(cancel_btn)

        save_btn = QtWidgets.QPushButton("Save")
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background: #0E7490; color: #e5e5eb;
                border: none; border-radius: 4px;
                padding: 8px 24px; font-size:{fs(12)};
                font-weight: 600;
            }}
            QPushButton:hover {{ background: #0c8fa8; }}
        """)
        save_btn.clicked.connect(self._on_save)
        bottom.addWidget(save_btn)
        right.addLayout(bottom)

        right_w = QtWidgets.QWidget()
        right_w.setLayout(right)
        root.addWidget(right_w, 1)

    # ──────────────────────────────────────────────────────────────────
    # Provider list management
    # ──────────────────────────────────────────────────────────────────

    def _refresh_provider_list(self):
        """Rebuild the left-panel list with status icons."""
        self._provider_list.blockSignals(True)
        self._provider_list.clear()
        for pid, pdata in self._providers.items():
            issues = self._validate_provider(pid, pdata)
            has_error = any(lvl == "error" for lvl, _ in issues)
            has_warning = any(lvl == "warning" for lvl, _ in issues)
            if has_error:
                icon = "✗"  # ✗
            elif has_warning:
                icon = "⚠"  # ⚠
            else:
                icon = "✓"  # ✓
            item = QtWidgets.QListWidgetItem(f"{icon} {pid}")
            item.setData(QtCore.Qt.UserRole, pid)
            self._provider_list.addItem(item)
        self._provider_list.blockSignals(False)

    def _select_provider(self, provider_id: str):
        """Select a provider in the list and populate the detail form."""
        for i in range(self._provider_list.count()):
            item = self._provider_list.item(i)
            if item.data(QtCore.Qt.UserRole) == provider_id:
                self._provider_list.setCurrentRow(i)
                return

    def _on_list_selection(self, row: int):
        """Handle provider list selection change."""
        if row < 0:
            self._current_id = None
            return
        item = self._provider_list.item(row)
        pid = item.data(QtCore.Qt.UserRole)
        self._current_id = pid
        self._populate_detail(pid)

    def _populate_detail(self, pid: str):
        """Fill the right-panel form from provider data."""
        pdata = self._providers.get(pid, {})
        # Block signals while populating to avoid recursive _on_field_changed
        self._id_edit.blockSignals(True)
        self._url_edit.blockSignals(True)
        self._key_edit.blockSignals(True)
        self._api_type_combo.blockSignals(True)

        self._id_edit.setText(pid)
        # Provider ID is read-only for existing providers
        self._id_edit.setReadOnly(True)
        self._url_edit.setText(pdata.get("baseUrl", ""))
        api_type = pdata.get("api", "openai-completions")
        idx = self._api_type_combo.findText(api_type)
        if idx >= 0:
            self._api_type_combo.setCurrentIndex(idx)
        self._key_edit.setText(pdata.get("apiKey", ""))

        self._id_edit.blockSignals(False)
        self._url_edit.blockSignals(False)
        self._key_edit.blockSignals(False)
        self._api_type_combo.blockSignals(False)

        self._populate_models_table(pdata.get("models", []))
        self._run_validation()

    def _populate_models_table(self, models: list):
        """Fill the models table from a list of model dicts."""
        self._models_table.setRowCount(0)
        for m in models:
            row = self._models_table.rowCount()
            self._models_table.insertRow(row)
            self._models_table.setItem(
                row, 0, QtWidgets.QTableWidgetItem(m.get("id", "")))
            self._models_table.setItem(
                row, 1, QtWidgets.QTableWidgetItem(m.get("name", "")))
            self._models_table.setItem(
                row, 2, QtWidgets.QTableWidgetItem(
                    str(m.get("contextWindow", ""))))
            self._models_table.setItem(
                row, 3, QtWidgets.QTableWidgetItem(
                    str(m.get("maxTokens", ""))))

    # ──────────────────────────────────────────────────────────────────
    # Provider CRUD
    # ──────────────────────────────────────────────────────────────────

    def _on_add_provider(self):
        """Add a new blank provider."""
        pid, ok = QtWidgets.QInputDialog.getText(
            self, "New Provider", "Provider ID (unique, lowercase):")
        if not ok or not pid.strip():
            return
        pid = pid.strip().lower().replace(" ", "-")
        if pid in self._providers or pid in self._builtin_ids:
            QtWidgets.QMessageBox.warning(
                self, "Duplicate",
                f"Provider '{pid}' already exists or is a built-in provider.")
            return
        self._providers[pid] = {
            "baseUrl": "",
            "api": "openai-completions",
            "apiKey": "",
            "models": [],
        }
        self._refresh_provider_list()
        self._select_provider(pid)

    def _on_delete_provider(self):
        """Delete the currently selected provider."""
        if not self._current_id:
            return
        reply = QtWidgets.QMessageBox.question(
            self, "Delete Provider",
            f"Delete provider '{self._current_id}' and all its models?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        if reply != QtWidgets.QMessageBox.Yes:
            return
        del self._providers[self._current_id]
        self._current_id = None
        self._refresh_provider_list()
        if self._providers:
            self._select_provider(list(self._providers.keys())[0])

    # ──────────────────────────────────────────────────────────────────
    # Model CRUD
    # ──────────────────────────────────────────────────────────────────

    def _on_add_model(self):
        if not self._current_id:
            return
        dlg = EditModelDialog(self)
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            model = dlg.get_model()
            self._providers[self._current_id].setdefault("models", []).append(
                model)
            self._populate_models_table(
                self._providers[self._current_id]["models"])
            self._refresh_provider_list()
            self._run_validation()

    def _on_edit_model(self):
        if not self._current_id:
            return
        row = self._models_table.currentRow()
        if row < 0:
            return
        models = self._providers[self._current_id].get("models", [])
        if row >= len(models):
            return
        dlg = EditModelDialog(self, model_data=models[row])
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            models[row] = dlg.get_model()
            self._populate_models_table(models)
            self._refresh_provider_list()
            self._run_validation()

    def _on_delete_model(self):
        if not self._current_id:
            return
        row = self._models_table.currentRow()
        if row < 0:
            return
        models = self._providers[self._current_id].get("models", [])
        if row >= len(models):
            return
        models.pop(row)
        self._populate_models_table(models)
        self._refresh_provider_list()
        self._run_validation()

    # ──────────────────────────────────────────────────────────────────
    # Field sync & visibility toggle
    # ──────────────────────────────────────────────────────────────────

    def _on_field_changed(self):
        """Sync form fields to in-memory provider data and re-validate."""
        if not self._current_id:
            return
        pdata = self._providers.get(self._current_id)
        if not pdata:
            return
        pdata["baseUrl"] = self._url_edit.text().strip()
        pdata["api"] = self._api_type_combo.currentText()
        pdata["apiKey"] = self._key_edit.text().strip()
        self._run_validation()
        self._refresh_provider_list()
        # Re-select current to keep highlight
        self._select_provider(self._current_id)

    def _toggle_key_visibility(self, checked: bool):
        if checked:
            self._key_edit.setEchoMode(QtWidgets.QLineEdit.Normal)
        else:
            self._key_edit.setEchoMode(QtWidgets.QLineEdit.Password)

    # ──────────────────────────────────────────────────────────────────
    # Validation
    # ──────────────────────────────────────────────────────────────────

    def _validate_provider(
        self, pid: str, pdata: dict
    ) -> list[tuple[str, str]]:
        """Validate a single provider. Returns list of (level, message)."""
        issues: list[tuple[str, str]] = []
        api_key = pdata.get("apiKey", "")
        base_url = pdata.get("baseUrl", "")
        models = pdata.get("models", [])

        if not api_key:
            issues.append(("error", "API key is empty"))
        if not base_url:
            issues.append(("error", "Base URL is empty"))
        elif not base_url.startswith(("http://", "https://")):
            issues.append(("warning", "Base URL should start with http(s)://"))
        if not models:
            issues.append(("warning", "No models defined"))
        for m in models:
            if not m.get("id", "").strip():
                issues.append(("error", "A model is missing its ID"))
                break
        return issues

    def _run_validation(self):
        """Validate current provider and update the status label."""
        if not self._current_id:
            self._validation_label.setText("")
            return
        pdata = self._providers.get(self._current_id, {})
        issues = self._validate_provider(self._current_id, pdata)
        if not issues:
            self._validation_label.setText(
                f"<span style='color:{_SUCCESS};'>All checks passed</span>")
            return
        parts = []
        for lvl, msg in issues:
            color = _ERROR if lvl == "error" else _WARNING
            symbol = "✗" if lvl == "error" else "⚠"
            parts.append(f"<span style='color:{color};'>{symbol} {msg}</span>")
        self._validation_label.setText("<br>".join(parts))

    # ──────────────────────────────────────────────────────────────────
    # Test Connection
    # ──────────────────────────────────────────────────────────────────

    def _on_test_connection(self):
        """Test the current provider's API connection."""
        if not self._current_id:
            return
        pdata = self._providers.get(self._current_id, {})
        base_url = pdata.get("baseUrl", "").rstrip("/")
        api_key = _resolve_env_key(pdata.get("apiKey", ""))
        api_type = pdata.get("api", "openai-completions")
        models = pdata.get("models", [])
        model_id = models[0]["id"] if models else "test"

        if not base_url or not api_key:
            self._test_status.setText(
                f"<span style='color:{_ERROR};'>"
                "Cannot test: missing URL or key</span>")
            return

        self._test_status.setText(
            f"<span style='color:{_MUTED};'>Testing...</span>")
        QtWidgets.QApplication.processEvents()

        try:
            url, headers, body = self._build_test_request(
                api_type, base_url, api_key, model_id)
            data_bytes = json.dumps(body).encode("utf-8") if body else None
            req = urllib.request.Request(
                url, data=data_bytes, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=10) as resp:
                status = resp.status
            if 200 <= status < 300:
                self._test_status.setText(
                    f"<span style='color:{_SUCCESS};'>"
                    f"Connected (HTTP {status})</span>")
            else:
                self._test_status.setText(
                    f"<span style='color:{_WARNING};'>"
                    f"HTTP {status}</span>")
        except urllib.error.HTTPError as e:
            # Some APIs return 400/401 but that still means reachable
            code = e.code
            if code == 401:
                msg = "Auth failed (401) — check API key"
                color = _ERROR
            elif code == 400:
                msg = f"Reachable but bad request ({code})"
                color = _WARNING
            else:
                msg = f"HTTP error {code}"
                color = _ERROR
            self._test_status.setText(
                f"<span style='color:{color};'>{msg}</span>")
        except Exception as e:
            self._test_status.setText(
                f"<span style='color:{_ERROR};'>"
                f"Failed: {str(e)[:80]}</span>")

    def _build_test_request(
        self, api_type: str, base_url: str, api_key: str, model_id: str
    ) -> tuple[str, dict, dict | None]:
        """Build (url, headers, body) for a test request."""
        if api_type == "openai-completions":
            url = f"{base_url}/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            body = {
                "model": model_id,
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 1,
            }
        elif api_type == "openai-responses":
            url = f"{base_url}/responses"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            body = {
                "model": model_id,
                "input": "hi",
                "max_output_tokens": 1,
            }
        elif api_type == "anthropic-messages":
            url = f"{base_url}/messages"
            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            }
            body = {
                "model": model_id,
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 1,
            }
        elif api_type == "google-generative-ai":
            url = (f"{base_url}/models/{model_id}:generateContent"
                   f"?key={api_key}")
            headers = {"Content-Type": "application/json"}
            body = {
                "contents": [{"parts": [{"text": "hi"}]}],
                "generationConfig": {"maxOutputTokens": 1},
            }
        else:
            # Fallback: generic OpenAI-style
            url = f"{base_url}/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            body = {
                "model": model_id,
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 1,
            }
        return url, headers, body

    # ──────────────────────────────────────────────────────────────────
    # Save
    # ──────────────────────────────────────────────────────────────────

    def _on_save(self):
        """Validate all providers, write models.json, sync auth.json."""
        # 1. Check for error-level issues across all providers
        all_errors: list[str] = []
        for pid, pdata in self._providers.items():
            issues = self._validate_provider(pid, pdata)
            for lvl, msg in issues:
                if lvl == "error":
                    all_errors.append(f"[{pid}] {msg}")

        if all_errors:
            QtWidgets.QMessageBox.critical(
                self, "Cannot Save",
                "Fix the following errors before saving:\n\n"
                + "\n".join(all_errors))
            return

        # 2. Re-read models.json, remove old custom providers, merge
        data = read_pi_models() or {}
        providers_dict = data.get("providers", {})

        # Remove all non-built-in providers (we'll re-add our set)
        old_custom = [
            k for k in list(providers_dict.keys())
            if k not in self._builtin_ids
        ]
        for k in old_custom:
            del providers_dict[k]

        # Add current custom providers
        for pid, pdata in self._providers.items():
            providers_dict[pid] = {
                "baseUrl": pdata.get("baseUrl", ""),
                "api": pdata.get("api", "openai-completions"),
                "apiKey": pdata.get("apiKey", ""),
                "models": pdata.get("models", []),
            }

        data["providers"] = providers_dict

        # 3. Write models.json
        write_pi_models(data)

        # 4. Sync literal API keys to auth.json (skip $ENV_VAR refs)
        auth = read_pi_auth() or {}
        for pid, pdata in self._providers.items():
            key = pdata.get("apiKey", "")
            if key and not key.startswith("$"):
                auth[pid] = {"type": "api_key", "key": key}
            elif pid in auth and key.startswith("$"):
                del auth[pid]
        write_pi_auth(auth)

        # 5. Mark restart needed and accept
        self._needs_restart = True
        self.accept()
