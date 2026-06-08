# Edini Session Architecture: pi as Source of Truth

**Date**: 2026-06-04
**Status**: approved, implementing

## Problem

Edini managed its own session store (`python3.11libs/edini/sessions/*.json`) while pi had its own separate session management. This caused:

1. **Pistatus stale**: Switching/creating sessions in edini didn't update the right-side Pi Status panel — pi's stats were tied to pi's own session, which didn't change.
2. **Dual storage**: Two incompatible session stores, always out of sync.
3. **No pi features**: /tree, /fork, /compact, branch summaries — all unavailable.
4. **`--no-session`**: pi was started with `--no-session`, so it didn't persist anything.

## Solution

Make pi the **sole source of truth** for sessions. Edini becomes a thin Qt UI wrapper over pi's RPC interface.

```
pi --mode rpc --cwd $HIP
  └─ ~/.pi/agent/sessions/--hip-path--/*.jsonl  ← only session store
```

## Architecture

```
┌─────────────────────────────────────────┐
│  Edini Qt Panel (薄 UI 层)              │
│                                         │
│  ┌──────────┐ ┌──────────┐ ┌─────────┐ │
│  │History   │ │Agent     │ │Context  │ │
│  │Panel     │ │Panel     │ │Panel    │ │
│  │          │ │          │ │         │ │
│  │pi_sess.  │ │prompt RPC│ │stats    │ │
│  │list files│ │streaming │ │RPC      │ │
│  └──────────┘ └──────────┘ └─────────┘ │
│                    │                    │
│            pi --mode rpc --cwd $HIP     │
│                    │                    │
│     ~/.pi/agent/sessions/--hip--/      │
└─────────────────────────────────────────┘
```

## Component Changes

### 1. `edini/config.py`

- `get_pi_command(cwd: str | None = None)` — accepts optional cwd
- Remove `--no-session` flag
- Add `--cwd <path>` when cwd provided

### 2. `edini/rpc_client.py`

New methods:
- `start(cwd: str | None = None)` — pass cwd to worker
- `send_new_session()` — added in previous iteration
- `send_switch_session(session_path: str)`
- `send_set_session_name(name: str)`
- `send_get_messages()` — get all messages for rendering

Worker changes:
- `_RpcWorker.__init__` accepts `cwd` parameter
- `_RpcWorker.run()` sets `cwd` on subprocess.Popen

### 3. NEW: `python3.11libs/edini/ui/pi_sessions.py`

Pure functions to read pi's session directory (no Qt):

```python
def list_pi_sessions(cwd: str) -> list[dict]
def get_pi_session_dir(cwd: str) -> Path
def delete_pi_session(session_path: str)
def get_pi_session_meta(session_path: str) -> dict
```

Reads `~/.pi/agent/sessions/--<cwd-slash-replaced>--/*.jsonl`, parses JSONL header for metadata.

### 4. `python3.11libs/edini/ui/history_panel.py`

- Replace `from edini.ui.session_store import ...` → `from edini.ui.pi_sessions import ...`
- `load_sessions()` reads pi session directory
- `_on_new` → emits `new_session_requested` (unchanged)
- Selection emits pi session file **path** (not edini session ID)
- Delete directly removes jsonl file

### 5. `python3.11libs/edini/ui/main_window.py`

Key handler changes:

```python
_bootstrap():
    cwd = hou.hipFile.path() if hou else os.getcwd()
    self._rpc_client.start(cwd=cwd)
    self.history_panel.load_sessions()

_on_new_session():
    self.agent_panel.clear_timeline()
    self.context_panel.reset_stats()
    self._rpc_client.send_new_session()
    # Wait for response, then reload session list

_on_session_selected(session_path: str):
    self.agent_panel.clear_timeline()
    self.context_panel.reset_stats()
    self._rpc_client.send_switch_session(session_path)
    # On success: get_messages → render, get_stats → update context

_on_agent_submit():
    # REMOVE: session_store.append_message()
    # REMOVE: session_store.rename_session()
    self._rpc_client.send_prompt(text, images)

_on_agent_done():
    # REMOVE: session_store.append_message() for assistant message
    # REMOVE: _check_compression() (pi handles this)
    self._rpc_client.send_get_stats()
```

### 6. DELETE: `python3.11libs/edini/ui/session_store.py`

No longer needed.

### 7. `python3.11libs/edini/ui/context_panel.py`

Already has `reset_stats()`. No further changes needed.

## Data Flow

```
New Session:
  [+ New] → send_new_session() → pi creates JSONL
  → response → load_sessions() → HistoryPanel refreshes
  → get_stats → ContextPanel shows 0%

Switch Session:
  [click] → send_switch_session(path)
  → success → send_get_messages() → render in AgentPanel
  → send_get_stats() → update ContextPanel

Send Message:
  [Enter] → send_prompt(text)
  → streaming events → AgentPanel renders in real-time
  → agent_end → send_get_stats() → ContextPanel updates

Delete Session:
  [right-click Delete] → os.remove(jsonl_path)
  → load_sessions() → HistoryPanel refreshes

Rename Session:
  [right-click Rename] → send_set_session_name(name)
  → load_sessions() → HistoryPanel refreshes
```

## pi Session Directory Structure

```
~/.pi/agent/sessions/
  └─ --Users--EEE--project--hipfile--/
       ├─ 1733123456789_abc123.jsonl    ← session file
       ├─ 1733987654321_def456.jsonl
       └─ ...
```

Session file format (JSONL, version 3):
```
{"type":"header","version":3,"createdAt":1733...,"updatedAt":1733...}
{"type":"message","message":{"role":"user","content":"..."},...}
{"type":"message","message":{"role":"assistant","content":[...]},...}
...
```

pi automatically creates the session directory and manages the JSONL tree structure.

## Migration

No migration. Old edini sessions in `python3.11libs/edini/sessions/` are left in place but no longer used. Users start fresh with pi-managed sessions.

## Out of Scope (future)

- Loading old edini sessions into pi format
- `/tree`, `/fork`, `/clone` UI in edini
- Exposing pi compaction controls in edini UI
