# Edini: Pi-Native Model Config

## Problem

Edini currently manages its own `api_key` / `provider` / `model_id` in a local `settings.json`. This duplicates what pi already does far better:

- **pi** has `~/.pi/agent/auth.json` (secure key storage), `models.json` (custom providers), `settings.json` (default model/thinking) — a complete provider ecosystem with 30+ providers
- **Edini** has a single `api_key` + `provider` + `model_id` — hardcoded, limited, insecure

Result: users configure pi once, then must re-configure in Edini. Provider/model lists are hardcoded. Adding a new provider requires editing Python code.

## Goal

**Edini's model/provider/API-key configuration should be a thin UI over pi's native config files.**

- Read from `~/.pi/agent/{auth.json, models.json, settings.json}`
- Write to the same files (so changes are visible to pi CLI too)
- Use RPC `get_available_models` to list models pi can see (after merging built-in + custom)
- Use RPC `set_model` / `cycle_model` to switch at runtime — no restart needed

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Houdini (Python / PySide6)                             │
│                                                         │
│  Settings Dialog (redesigned)                           │
│    ├── Tab 1: API Keys (read/write ~/.pi/agent/auth.json)│
│    ├── Tab 2: Models (from pi RPC + models.json editing) │
│    └── Tab 3: Knowledge (unchanged)                      │
│                                                         │
│  Model Selector (header bar dropdown)                    │
│    └── RPC get_available_models → set_model on select    │
│                                                         │
│  Pi Subprocess (--mode rpc)                             │
│    └── reads ~/.pi/agent/* on startup automatically     │
└─────────────────────────────────────────────────────────┘
```

## What Changes

### 1. `config.py` — Remove Edini's own provider/key management

**Remove:**
- `api_key`, `provider`, `model_id` from `_DEFAULTS` and `_ENV_MAP`
- `get_pi_env()` — no more env-var-based key injection
- `_set_provider_api_key()` — unnecessary

**Add:**
- `PI_AGENT_DIR` = `Path("~/.pi/agent").expanduser()` constant
- `read_pi_auth() -> dict` — read `auth.json`
- `write_pi_auth(data: dict)` — write `auth.json` atomically
- `read_pi_models() -> dict` — read `models.json`
- `write_pi_models(data: dict)` — write `models.json` atomically
- `read_pi_settings() -> dict` — read `settings.json`
- `write_pi_settings(data: dict)` — write `settings.json` atomically

### 2. `rpc_client.py` — Add model discovery RPC methods

**Add to RpcClient:**
- `send_get_available_models()` → sends `{"type": "get_available_models"}`
- `send_cycle_model()` → sends `{"type": "cycle_model"}`
- `send_set_thinking_level(level)` → sends `{"type": "set_thinking_level", "level": level}`

**Add signals:**
- `models_received = Signal(object)` — emitted when `get_available_models` response arrives
- `model_changed = Signal(object)` — emitted when `set_model` / `cycle_model` response arrives

### 3. `settings_dialog.py` — Redesign with pi-native config

**Tab 1: API Keys (auth.json)**

```
┌─────────────────────────────────────────────────────┐
│  API Key Management                                  │
│  (Stored in ~/.pi/agent/auth.json)                   │
│                                                      │
│  Configured Providers:                               │
│  ┌────────────────────────────────────────────────┐  │
│  │ deepseek     sk-ba5a...xxxx    [Edit] [Remove] │  │
│  │ zai-coding-cn 41fc37...xxxx   [Edit] [Remove] │  │
│  │ aliyun       sk-ded8...xxxx    [Edit] [Remove] │  │
│  └────────────────────────────────────────────────┘  │
│                                                      │
│  + Add Provider: [deepseek ▾] [sk-xxx...    ] [Add] │
│                                                      │
│  💡 Also configurable via terminal: pi /login        │
└─────────────────────────────────────────────────────┘
```

Reads/writes `~/.pi/agent/auth.json`. The "Add Provider" dropdown includes all known pi providers (deepseek, anthropic, openai, google, etc.) plus any custom ones from `models.json`.

**Tab 2: Model Selection**

```
┌─────────────────────────────────────────────────────┐
│  Model Configuration                                 │
│                                                      │
│  Default Model:                                      │
│  ┌────────────────────────────────────────────────┐  │
│  │ Provider: [deepseek ▾]                          │  │
│  │ Model:    [deepseek-v4-pro ▾]                   │  │
│  │ Thinking: [high ▾]                              │  │
│  └────────────────────────────────────────────────┘  │
│  (Writes to ~/.pi/agent/settings.json)               │
│                                                      │
│  ── Custom Providers (models.json) ──────────────── │
│                                                      │
│  Configured:                                         │
│  ┌────────────────────────────────────────────────┐  │
│  │ deepseek (openai-completions)                   │  │
│  │   baseUrl: https://api.deepseek.com/v1          │  │
│  │   models: deepseek-v4-pro, deepseek-chat, R1   │  │
│  │                                        [Edit]   │  │
│  ├────────────────────────────────────────────────┤  │
│  │ aliyun (openai-completions)                     │  │
│  │   baseUrl: https://dashscope.aliyuncs.com/...   │  │
│  │   models: qwen-vl-max, qwen2.5-vl-72b          │  │
│  │                                        [Edit]   │  │
│  └────────────────────────────────────────────────┘  │
│  + Add Custom Provider                               │
│                                                      │
│  💡 Advanced: edit ~/.pi/agent/models.json directly  │
└─────────────────────────────────────────────────────┘
```

Default model writes to `~/.pi/agent/settings.json`. Custom provider section reads/writes `~/.pi/agent/models.json`.

**Tab 3: Knowledge** — unchanged.

**Remove: Vision tab** — pi-visionizer should read from the same `auth.json` / `models.json`. No separate vision config needed; any model with `input: ["text", "image"]` works for vision.

### 4. `panel.py` / `agent_panel.py` — Model selector in header

Add a model selector dropdown in the header bar:

- On startup: send `get_available_models` RPC
- Populate dropdown with returned models grouped by provider
- On selection: send `set_model` RPC
- Show thinking level badge next to model name
- Support `cycle_model` via keyboard shortcut

### 5. `pi-extensions/edini-zhipu/` — Convert to models.json

The edini-zhipu extension hardcodes 智谱 as a provider. Instead:
- Move the provider definition into `~/.pi/agent/models.json` under `providers.zhipu`
- Remove the extension entirely
- Pi loads it from `models.json` automatically

### 6. `pi-extensions/pi-visionizer/` — Simplify

Remove its own provider/model config. Instead:
- Read available models from pi (all models with `input: ["text", "image"]` are candidates)
- User selects vision model from the Model tab (in models.json)
- Visionizer just picks the first image-capable model or a configured one

## Data Flow

### Startup Flow
```
1. Houdini launches → ToolExecutor starts on port 9876
2. RpcClient.start() → spawns `pi --mode rpc -e edini-tools -e edini-context ...`
3. Pi reads ~/.pi/agent/{auth.json, models.json, settings.json} automatically
4. Pi connects → "connected" status
5. Panel sends get_available_models → populates model dropdown
6. Panel sends get_state → shows current model in header
```

### API Key Change Flow
```
1. User opens Settings → API Keys tab
2. User adds/edits a provider key
3. Python writes ~/.pi/agent/auth.json directly
4. Pi RPC already running → does NOT auto-reload auth.json
   → User must restart: show "Restart required" button
5. On restart: Pi reads updated auth.json → key available
```

Actually, pi supports `set_model` without restart if the key is already in `auth.json`. The restart is only needed when adding a NEW key (because pi caches auth on startup). We can handle this by:
- Writing to `auth.json`
- Restarting pi subprocess (already supported)
- Sending `set_model` after reconnect

### Model Switch Flow
```
1. User selects model from dropdown
2. RPC set_model(provider, modelId)
3. Pi switches immediately — no restart needed
4. Header updates with new model name
```

### Custom Provider Flow
```
1. User opens Settings → Model tab → Add Custom Provider
2. Dialog: name, baseUrl, apiType, apiKey, models
3. Python writes to ~/.pi/agent/models.json
4. Python writes to ~/.pi/agent/auth.json (apiKey)
5. Restart pi subprocess to pick up new provider
6. New models appear in dropdown
```

## Migration

For existing users who have `python3.11libs/edini/settings.json` with `api_key` + `provider` + `model_id`:
- On first run after update, detect old config
- Migrate: write old key → `auth.json`, write old model → `settings.json`
- Show one-time notification: "Config migrated to ~/.pi/agent/"
- Keep old `settings.json` for non-model settings (theme, font_scale, knowledge)

## Files Changed

| File | Action | Description |
|------|--------|-------------|
| `python3.11libs/edini/config.py` | Rewrite | Remove api_key/provider/model_id management; add pi config file helpers |
| `python3.11libs/edini/rpc_client.py` | Extend | Add models/model-change RPC methods + signals |
| `python3.11libs/edini/ui/settings_dialog.py` | Rewrite | API Keys tab + Model tab + Knowledge tab (drop Vision tab) |
| `python3.11libs/edini/ui/agent_panel.py` | Extend | Add model selector dropdown in header |
| `pi-extensions/edini-zhipu/index.ts` | Remove | Provider definition moves to models.json |
| `edini/config.py` | Sync | Mirror changes from python3.11libs version |

## What Stays

- Knowledge tab and all knowledge-related features — unchanged
- Theme and font scale settings — stays in local settings.json
- pi-visionizer extension — stays but simplified (no separate config)
- Tool executor — unchanged
- edini-tools, edini-context extensions — unchanged
