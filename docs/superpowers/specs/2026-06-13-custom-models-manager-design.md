# Custom Models Manager — Design Spec

**Date:** 2026-06-13
**Scope:** New "Manage Custom Models" dialog accessible from Settings → Providers & Models tab

## Problem

Pi's `models.json` validation is strict: if any non-built-in provider is missing `apiKey`, the entire file fails to load and all custom models become unavailable. The current "Add Custom Provider" dialog is a one-shot form that doesn't validate, doesn't show existing providers, and provides no way to edit or delete. Users have no visibility into configuration issues until runtime fails silently.

## Solution

A Master-Detail management dialog for custom providers in `models.json`, with real-time validation and connection testing.

## Architecture

### Entry Point

Replace the existing "+ Custom Provider" button (line 188 of `settings_dialog.py`) with a "Manage Custom Models" button that opens `CustomModelsDialog`.

### Dialog Layout

```
┌─ Custom Models Manager ─────────────────────────────────────────┐
│                                                                   │
│ ┌─ Providers ──────┐  ┌─ Detail ──────────────────────────────┐ │
│ │                   │  │                                        │ │
│ │  deepseek     ✓   │  │  Provider ID:  [aliyun         ]      │ │
│ │  aliyun       ✓   │  │  Base URL:     [https://dash... ]      │ │
│ │  gmn          ⚠   │  │  API Type:     [openai-completions ▼]  │ │
│ │                   │  │  API Key:      [sk-****cc     ] [👁]   │ │
│ │                   │  │                                        │ │
│ │                   │  │  ── Models ─────────────────────────── │ │
│ │                   │  │  ┌──────────────────────────────────┐  │ │
│ │                   │  │  │ ID            │ Input   │ Ctx    │  │ │
│ │                   │  │  ├──────────────────────────────────┤  │ │
│ │                   │  │  │ qwen3-vl-plus │txt,img  │131072  │  │ │
│ │                   │  │  │ qwen-vl-max   │txt,img  │ 32768  │  │ │
│ │                   │  │  └──────────────────────────────────┘  │ │
│ │                   │  │  [+ Add Model] [Edit] [Delete]         │ │
│ │                   │  │                                        │ │
│ │                   │  │  ── Validation ─────────────────────── │ │
│ │                   │  │  ✓ apiKey configured                   │ │
│ │                   │  │  ✓ baseUrl is valid HTTPS              │ │
│ │                   │  │  ✓ All models have required fields     │ │
│ │                   │  │  [Test Connection]  ✓ 200 OK (340ms)   │ │
│ │                   │  │                                        │ │
│ │  [+ Add]          │  │                                        │ │
│ │  [Delete]         │  │                                        │ │
│ └───────────────────┘  └────────────────────────────────────────┘ │
│                                                                   │
│                                          [Save]  [Cancel]         │
└───────────────────────────────────────────────────────────────────┘
```

### Components

**File:** `python3.11libs/edini/ui/custom_models_dialog.py` (new file)

#### 1. `CustomModelsDialog(QDialog)`

Main dialog. 700x500 minimum. Contains:
- `QSplitter` with left panel (provider list) and right panel (detail)
- Bottom button bar: Save, Cancel

State management:
- Loads `models.json` on open into an in-memory dict
- All edits modify the in-memory dict only
- Save writes back to disk after validation passes
- Cancel discards all changes

#### 2. Left Panel: Provider List

- `QListWidget` showing provider names
- Status icon per item: ✓ green (valid), ⚠ yellow (warning), ✗ red (error)
- Buttons below: [+ Add Provider], [Delete Provider]
- Selecting a provider updates the right panel
- Only shows non-built-in providers (filter out providers in Pi's built-in list)

#### 3. Right Panel: Provider Detail

**Provider fields (top section):**
| Field | Widget | Editable | Notes |
|-------|--------|----------|-------|
| Provider ID | QLineEdit | Only on create | Becomes read-only after first save |
| Base URL | QLineEdit | Yes | Placeholder: `https://api.example.com/v1` |
| API Type | QComboBox | Yes | Options: openai-completions, openai-responses, anthropic-messages, google-generative-ai |
| API Key | QLineEdit (password mode) | Yes | Eye toggle button. Supports `$ENV_VAR` syntax |

**Models table (middle section):**
- `QTableWidget` with columns: ID, Name, Input, Context Window, Max Tokens
- Input column displays as comma-separated tags (text, image)
- Row selection with [Edit], [Delete] buttons
- [+ Add Model] opens `EditModelDialog`

**Validation status (bottom section):**
- `QVBoxLayout` with validation result labels
- Each check is a single line: icon + description
- [Test Connection] button with result display

#### 4. `EditModelDialog(QDialog)`

Small form dialog for adding/editing a single model:
- Model ID (QLineEdit, required)
- Display Name (QLineEdit, optional)
- Input capabilities (QCheckBox group: text, image)
- Context Window (QSpinBox, default 32768, range 1024-2000000)
- Max Tokens (QSpinBox, default 8192, range 256-1000000)
- Reasoning (QCheckBox, default off)

## Validation Rules

Validation runs on every field change (debounced) and on Save.

| Rule | Severity | Message | Blocks Save |
|------|----------|---------|-------------|
| apiKey is empty | Error | "API key required for custom providers — Pi cannot load models.json without it" | Yes |
| baseUrl is empty | Error | "Base URL is required" | Yes |
| baseUrl doesn't start with `http://` or `https://` | Warning | "Base URL should start with http:// or https://" | No |
| Provider has zero models | Warning | "Provider has no models defined" | No |
| Model ID is empty | Error | "Model ID is required" | Yes |
| Vision-intended model missing `image` in input | Info | "Add 'image' to input for vision model capability" | No |
| Duplicate provider ID | Error | "Provider ID already exists" | Yes |

### Error Severity Levels

- **Error (✗ red):** Configuration will cause Pi's `validateConfig()` to throw, breaking all custom model loading. Must fix before save.
- **Warning (⚠ yellow):** Configuration might cause unexpected behavior but won't break loading.
- **Info (ℹ blue):** Helpful hints, no action required.

## Test Connection

Implementation in the dialog itself (no separate module needed):

1. User clicks [Test Connection]
2. Read current provider's baseUrl, apiKey, api type from the form
3. Based on api type:
   - `openai-completions`: POST to `{baseUrl}/chat/completions` with minimal payload (`model: first_model_id, messages: [{role:"user", content:"hi"}], max_tokens: 1`)
   - `openai-responses`: POST to `{baseUrl}/responses` with minimal payload
   - `anthropic-messages`: POST to `{baseUrl}/messages` with minimal payload
   - `google-generative-ai`: POST to `{baseUrl}/models/{model_id}:generateContent` with minimal payload
4. Timeout: 10 seconds
5. Show result: "✓ 200 OK (340ms)" or "✗ 401 Unauthorized" or "✗ Connection refused"

Use Python `urllib.request` (already available in Houdini's Python) to avoid adding dependencies.

## Save Flow

1. Run all validation rules
2. If any Error-level issues exist → show QMessageBox with list of problems, abort save
3. If only Warnings → show brief inline notice, proceed
4. Write updated providers dict to `models.json` via `write_pi_models()`
5. Sync API keys to `auth.json`: for each provider with a literal (non-`$ENV_VAR`) apiKey, ensure a matching entry exists in `auth.json`
6. Set `self._needs_restart = True` on parent dialog (Pi must restart to reload models.json)
7. Close dialog

## Integration with Existing Code

- **Entry point:** Replace `custom_btn` in `_build_providers_models_tab()` (line 188) with "Manage Custom Models" button that opens `CustomModelsDialog`
- **After save:** Call `self._populate_configured_providers()` and `self._populate_chat_and_vision()` on the parent settings dialog to reflect changes in the provider/model dropdowns
- **Config functions used:** `read_pi_models()`, `write_pi_models()`, `read_pi_auth()`, `write_pi_auth()` from `edini.config`
- **Built-in provider list:** Obtained via `get_pi_ai_providers()` from the data bridge, used to filter which providers appear in this dialog (only custom ones)

## Styling

Match existing Edini dark theme:
- Background: `#0c0c14`
- Surface: `#10101a`
- Border: `#1e1e2c`
- Text: `#c8ccd4`
- Accent: `#06b6d4` (cyan, focus states)
- Success: `#16a34a`
- Warning: `#d97706`
- Error: `#ef4444`
- Info: `#3b82f6`

## Files to Create/Modify

| File | Action |
|------|--------|
| `python3.11libs/edini/ui/custom_models_dialog.py` | Create — new dialog |
| `python3.11libs/edini/ui/settings_dialog.py` | Modify — replace "+ Custom Provider" button with "Manage Custom Models" |
| `python3.11libs/edini/config.py` | No changes needed (existing read/write helpers suffice) |

## Out of Scope

- Managing built-in provider auth (handled by existing "Login Provider" flow)
- Editing Pi's `settings.json` (handled by existing Chat Model section)
- Auto-discovery of models from provider API (future enhancement)
