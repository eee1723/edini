# Provider & Model Settings Redesign

**Date:** 2026-06-09
**Status:** Approved

## Goal

Restructure the settings dialog to use a pi CLI-inspired login/logout/model flow, merge provider management and model configuration into a single panel, add vision model support, and auto-sync provider data from pi-ai.

## Current State

- 3 tabs: API Keys, Models, Knowledge
- API Keys tab: manual provider name input, raw key entry
- Models tab: default provider/model/thinking + custom providers + appearance settings
- No vision model configuration in UI
- Hardcoded `KNOWN_PROVIDERS` list in Python — goes stale when pi adds providers

## New Structure

3 tabs:

| Tab | Content |
|-----|---------|
| 🔌 **Providers & Models** | Provider management + chat model + vision model |
| 🎨 **Appearance** | Theme, font scale (extracted from old Models tab) |
| 📚 **Knowledge** | Unchanged |

## Tab 1: Providers & Models

Single-page card layout with 3 sections:

### Section 1: Configured Providers

- Table/list showing all authenticated providers with:
  - Status indicator (✅ configured)
  - Provider display name (from pi-ai)
  - Auth source (auth.json key, env var, or models.json)
  - **Logout** button per row
- **[+ Login Provider]** button below the list

**Login flow** (pi CLI style):
1. Click "+ Login Provider" → opens a searchable list dialog with all pi-ai providers
2. Provider list shows: display name, model count, vision model count
3. User selects a provider → opens API key input dialog
4. Key is written to `~/.pi/agent/auth.json`
5. Pi subprocess is restarted to pick up the new key

**Logout flow:**
1. Click "Logout" on a provider row
2. Remove entry from `auth.json`
3. Pi subprocess is restarted

### Section 2: Chat Model

- **Provider** dropdown: only shows providers with configured auth
- **Model** dropdown: populated from pi-ai data for the selected provider (via bridge)
- **Thinking** dropdown: off, minimal, low, medium, high, xhigh
- On save: writes to `~/.pi/agent/settings.json` + sends `set_model` RPC

### Section 3: Vision Model

- **Provider** dropdown: only shows providers with configured auth AND vision-capable models
- **Model** dropdown: only shows models with `input` containing `"image"`
- On save: writes `vision_provider` + `vision_model_id` to edini `settings.json`
- Passed to pi-visionizer via env vars `VISIONIZER_PROVIDER` / `VISIONIZER_MODEL_ID`

### Custom Providers

- Keep "+ Add Custom Provider" button below the provider list (for Ollama, LM Studio, etc.)
- Opens the existing `_AddProviderDialog`
- Writes to `~/.pi/agent/models.json`

## Auto-Sync via pi_data_bridge.js

New file: `python3.11libs/edini/pi_data_bridge.js`

Node.js script that reads the installed `pi-ai` package data directly:

```
node pi_data_bridge.js providers       → [{id, name, modelCount, imageModelCount}]
node pi_data_bridge.js models <prov>   → [{id, name, reasoning, input}]
node pi_data_bridge.js vision-models   → [{provider, id, name, reasoning}]
```

- Called via `subprocess` from Python, results cached for process lifetime
- When pi is updated (npm update), Edini automatically sees new providers/models
- No hardcoded provider lists in Python

## Implementation Details

### New files
- `python3.11libs/edini/pi_data_bridge.js` — already created and verified
- `python3.11libs/edini/ui/provider_list_dialog.py` — searchable provider selector dialog
- `python3.11libs/edini/ui/api_key_dialog.py` — simple API key input dialog

### Modified files
- `python3.11libs/edini/ui/settings_dialog.py` — major rewrite:
  - Tab 1: Providers & Models (merged, new layout)
  - Tab 2: Appearance (extracted from old Models tab)
  - Tab 3: Knowledge (preserved)
  - Remove hardcoded `KNOWN_PROVIDERS`
- `python3.11libs/edini/config.py` — add `get_pi_ai_providers()` and `get_provider_models()` helpers using the bridge

### Provider list dialog (pi CLI style)
- Full-width searchable list with filter input at top
- Each row: provider name, model count badge, vision badge
- Keyboard navigation (up/down, enter to select, escape to cancel)
- Fuzzy search filter on provider name/id

### Auth status detection
For each provider, check auth status in this priority:
1. `auth.json` has entry with `type: "api_key"` → show key hint
2. `models.json` has provider with `apiKey` → show "models.json"
3. Environment variable exists → show env var name
4. Not configured → not shown in configured list

### Vision model data flow
```
pi_data_bridge.js vision-models
  → Python caches list
  → UI filters by provider, shows only image-capable models
  → User selects → saved to edini settings.json
  → get_pi_env() sets VISIONIZER_PROVIDER / VISIONIZER_MODEL_ID
  → pi-visionizer reads env vars on startup
```

## Backward Compatibility

- Existing `auth.json`, `models.json`, `settings.json` formats unchanged
- Legacy migration (`migrate_legacy_settings`) preserved
- pi-visionizer env var interface unchanged
- Knowledge tab completely preserved
