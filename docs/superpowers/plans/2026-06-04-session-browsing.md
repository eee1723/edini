# Session Browsing Mode — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add browsing mode to session history panel so users can revisit historical sessions, continue chatting in them, and return to the active session via a "← Back to Current" button that replaces "+ New Session" while browsing.

**Architecture:** HistoryPanel gains a `set_browsing_mode(enabled)` toggle that swaps button text and behavior. MainWindow gains `_active_session_path` and `_browsing_session_path` to track which session was active before entering browse mode, enabling lossless return.

**Tech Stack:** Python 3.11, PySide6, Pi JSONL session files

---

## File Structure

| File | Role | Change |
|------|------|--------|
| `python3.11libs/edini/ui/history_panel.py` | Session list widget + button | Add browsing mode toggle, back-to-current signal, highlight |
| `python3.11libs/edini/ui/main_window.py` | Orchestrator connecting panels | Add state fields, modify/create handlers |
| `python3.11libs/edini/sessions/` | Old edini session files (JSON) | Delete all files |

---

### Task 1: HistoryPanel — add browsing mode support

**Files:**
- Modify: `python3.11libs/edini/ui/history_panel.py`

- [ ] **Step 1: Add `back_to_current_requested` signal and browsing state**

In `HistoryPanel.__init__`, add the new signal and state variable right after `new_session_requested`:

```python
# In the signal declarations at class level:
back_to_current_requested = QtCore.Signal()
```

In `__init__`, after `self._cwd = ""`:

```python
self._browsing = False
self._active_session_path = ""
```

- [ ] **Step 2: Modify `_on_new` to dispatch based on browsing mode**

Replace the existing `_on_new` method:

```python
def _on_new(self):
    if self._browsing:
        self.back_to_current_requested.emit()
    else:
        self.new_session_requested.emit()
```

- [ ] **Step 3: Add `set_browsing_mode` and `highlight_session` public methods**

Add these methods after `set_cwd`:

```python
def set_browsing_mode(self, enabled: bool):
    """Toggle between normal mode (+ New Session) and browsing mode (← Back to Current)."""
    self._browsing = enabled
    if enabled:
        self.new_btn.setText("← 回到当前")
    else:
        self.new_btn.setText("+ 新对话")

def highlight_session(self, session_path: str):
    """Highlight a specific session item in the list by its path."""
    self.session_list.clearSelection()
    if not session_path:
        return
    for i in range(self.session_list.count()):
        item = self.session_list.item(i)
        if item and item.data(QtCore.Qt.UserRole) == session_path:
            self.session_list.setCurrentItem(item)
            break
```

- [ ] **Step 4: Modify `load_sessions` to accept optional highlight path and restore highlights**

Update `load_sessions` to optionally highlight a session after loading, and to remember which session to highlight:

```python
def load_sessions(self, highlight_path: str = ""):
    self.session_list.clear()
    if not self._cwd:
        return
    sessions = list_pi_sessions(self._cwd)
    for s in sessions:
        self.add_session(
            s["path"],
            s.get("title", "New Session"),
            s.get("created_at", ""),
            s.get("updated_at", ""),
            s.get("message_count", 0),
        )
    if highlight_path:
        self.highlight_session(highlight_path)
```

- [ ] **Step 5: Commit**

```bash
git add python3.11libs/edini/ui/history_panel.py
git commit -m "feat(history): add browsing mode toggle and back-to-current signal"
```

---

### Task 2: MainWindow — add browsing mode state and transitions

**Files:**
- Modify: `python3.11libs/edini/ui/main_window.py`

- [ ] **Step 1: Add state fields in `__init__`**

In `EdiniMainWindow.__init__`, after `self._current_session_path = ""`:

```python
self._active_session_path = ""
self._browsing_session_path = ""
```

- [ ] **Step 2: Bind the new `back_to_current_requested` signal**

In `_bind_events`, after the line `self.history_panel.session_deleted.connect(self._on_session_deleted)`:

```python
self.history_panel.back_to_current_requested.connect(self._on_back_to_current)
```

- [ ] **Step 3: Replace `_on_new_session` with browsing-mode-aware version**

Replace the existing `_on_new_session` method:

```python
def _on_new_session(self):
    # Save current session as active before creating new one (only if not already browsing)
    if not self._browsing_session_path:
        self._active_session_path = self._current_session_path
    self._browsing_session_path = ""
    self.history_panel.set_browsing_mode(False)

    self._current_session_path = ""
    self.agent_panel.clear_timeline()
    self.context_panel.reset_stats()
    self._rpc_client.send_new_session()
    # Schedule a reload after pi creates the session
    QtCore.QTimer.singleShot(500, lambda: self.history_panel.load_sessions(
        highlight_path=self._current_session_path))
```

- [ ] **Step 4: Replace `_on_session_selected` with browsing-mode-aware version**

Replace the existing `_on_session_selected` method:

```python
def _on_session_selected(self, session_path: str):
    if session_path == self._current_session_path and not self._browsing_session_path:
        return  # Already viewing this session in normal mode, no-op

    # Enter browsing mode if not already in it
    if not self._browsing_session_path:
        self._active_session_path = self._current_session_path
    self._browsing_session_path = session_path
    self.history_panel.set_browsing_mode(True)
    self.history_panel.highlight_session(session_path)

    self._current_session_path = session_path
    self.agent_panel.clear_timeline()
    self.context_panel.reset_stats()

    # Load messages directly from local JSONL for instant rendering
    messages = load_pi_messages(session_path)
    for m in messages:
        role = m.get("role", "")
        content = m.get("content", "")
        if role == "user":
            self.agent_panel._append_user_message(content)
        elif role == "assistant":
            self.agent_panel._render_stored_assistant_message(m)

    # Tell pi to switch session (async, updates stats)
    self._rpc_client.send_switch_session(session_path)
```

- [ ] **Step 5: Add `_on_back_to_current` handler**

Add a new method after `_on_session_selected`:

```python
def _on_back_to_current(self):
    """Exit browsing mode and restore the previously active session."""
    target = self._active_session_path
    self._browsing_session_path = ""
    self.history_panel.set_browsing_mode(False)

    if target:
        self._current_session_path = target
        self.agent_panel.clear_timeline()
        self.context_panel.reset_stats()

        messages = load_pi_messages(target)
        for m in messages:
            role = m.get("role", "")
            content = m.get("content", "")
            if role == "user":
                self.agent_panel._append_user_message(content)
            elif role == "assistant":
                self.agent_panel._render_stored_assistant_message(m)

        self._rpc_client.send_switch_session(target)
        self.history_panel.highlight_session(target)
    else:
        self._current_session_path = ""
        self.agent_panel.clear_timeline()
```

- [ ] **Step 6: Modify `_on_session_deleted` to handle browsing/active session cleanup**

Replace the existing `_on_session_deleted` method:

```python
def _on_session_deleted(self, session_path: str):
    self.history_panel.remove_session(session_path)
    
    # If deleted session was the one being browsed, fall back to active
    if session_path == self._browsing_session_path:
        self._browsing_session_path = ""
        self.history_panel.set_browsing_mode(False)
        if self._active_session_path and self._active_session_path != session_path:
            self._on_session_selected(self._active_session_path)
            self.history_panel.set_browsing_mode(False)
        else:
            self._current_session_path = ""
            self.agent_panel.clear_timeline()
        return
    
    # If deleted session was the active one, clear it
    if session_path == self._active_session_path:
        self._active_session_path = ""
    
    if session_path == self._current_session_path:
        self._current_session_path = ""
        self.agent_panel.clear_timeline()
```

- [ ] **Step 7: Modify `_on_pi_session_switched` to update highlights**

Replace the existing `_on_pi_session_switched` method:

```python
def _on_pi_session_switched(self, session_path: str):
    """Called when pi confirms a session switch (new or resumed)."""
    self._current_session_path = session_path
    self._rpc_client.send_get_stats()
    # Update list highlight to match active session
    highlight = self._browsing_session_path or session_path
    self.history_panel.highlight_session(highlight)
```

- [ ] **Step 8: Commit**

```bash
git add python3.11libs/edini/ui/main_window.py
git commit -m "feat(main): add session browsing mode with active/browsing state tracking"
```

---

### Task 3: Clean up old edini session files

**Files:**
- Delete: `python3.11libs/edini/sessions/*.json`

- [ ] **Step 1: Delete all old JSON session files**

```bash
rm python3.11libs/edini/sessions/sess-*.json
```

- [ ] **Step 2: Verify no code references the old sessions directory**

```bash
grep -r "edini/sessions" python3.11libs/ --include="*.py" || echo "No references found"
```

If any references are found, remove them.

- [ ] **Step 3: Commit**

```bash
git add python3.11libs/edini/sessions/
git commit -m "chore: remove old edini JSON session files"
```

---

### Task 4: End-to-end verification

- [ ] **Step 1: Start Houdini, open Edini panel**

Expected: History panel loads with session list from Pi. Button shows "+ 新对话".

- [ ] **Step 2: Send a message to create a session**

Expected: Message appears in timeline. After agent finishes, session appears in history list.

- [ ] **Step 3: Click "+ 新对话" to create a second session**

Expected: Timeline clears. Old session appears in history list. Button still shows "+ 新对话".

- [ ] **Step 4: Click the old session in the history list**

Expected: Timeline loads old messages. Button changes to "← 回到当前". Old session is highlighted.

- [ ] **Step 5: While in browsing mode, send a new message**

Expected: Message is added to the browsed session's timeline. Button stays "← 回到当前". Agent can process normally.

- [ ] **Step 6: While in browsing mode, click another history session**

Expected: Timeline switches to the new selection. Button stays "← 回到当前".

- [ ] **Step 7: Click "← 回到当前"**

Expected: Timeline restores the session that was active before entering browsing mode. Button reverts to "+ 新对话". That session is highlighted.
