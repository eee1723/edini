# Timeline Bugs — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix four bugs: history bubble splitting, knowledge extraction visible in history, change tree false positives, change tree not clearing on session switch.

**Architecture:** Two-file change. `main_window.py` gets message merging/filtering logic and change tree clearing. `snapshot_engine.py` gets auto-param filtering in `diff()`.

**Tech Stack:** Python 3.11 + PySide6, `hou` module

---

## File Structure

| File | Action | Purpose |
|------|--------|---------|
| `python3.11libs/edini/ui/main_window.py` | Modify | Bubble merging, knowledge filter, change tree clear on session switch |
| `python3.11libs/edini/ui/snapshot_engine.py` | Modify | Filter self-changing params in `diff()` |

---

### Task 1: Merge consecutive assistant messages when loading history

**Files:**
- Modify: `python3.11libs/edini/ui/main_window.py` — `_on_session_selected`, `_on_back_to_current`, `_on_pi_messages_received`

- [ ] **Step 1: Add `_merge_consecutive_assistants()` helper**

Add this method to `EdiniMainWindow` class, before `_on_new_session` (around line 474):

```python
    def _merge_consecutive_assistants(self, messages: list) -> list:
        """Merge consecutive assistant messages into single entries.

        Pi stores each assistant content block as a separate JSONL entry
        when tool calls split the response. For display, consecutive
        assistant messages (no user between them) should render as one bubble.
        """
        merged = []
        i = 0
        while i < len(messages):
            m = messages[i]
            role = m.get("role", "")
            if role != "assistant":
                merged.append(m)
                i += 1
                continue

            # Collect consecutive assistant messages
            texts = []
            thinkings = []

            # Extract content from current message
            content = m.get("content", "")
            if content:
                texts.append(content)
            for t in m.get("thinking", []):
                if t.strip():
                    thinkings.append(t.strip())

            j = i + 1
            while j < len(messages) and messages[j].get("role") == "assistant":
                nm = messages[j]
                nc = nm.get("content", "")
                if nc:
                    texts.append(nc)
                for t in nm.get("thinking", []):
                    if t.strip():
                        thinkings.append(t.strip())
                j += 1

            merged.append({
                "role": "assistant",
                "content": "\n\n".join(texts),
                "thinking": thinkings,
            })
            i = j
        return merged
```

- [ ] **Step 2: Apply merge in `_on_session_selected`**

In `_on_session_selected`, after `messages = load_pi_messages(session_path)`, add:

```python
        messages = self._merge_consecutive_assistants(messages)
        messages = self._filter_knowledge_extraction(messages)
```

And replace the rendering loop with a single `_append_assistant_message` call instead of per-entry `_render_stored_assistant_message`:

Current rendering loop (lines 507-514):
```python
        for m in messages:
            role = m.get("role", "")
            content = m.get("content", "")
            if role == "user":
                self.agent_panel._append_user_message(content)
            elif role == "assistant":
                self.agent_panel._render_stored_assistant_message(m)
```

Replace with:
```python
        for m in messages:
            role = m.get("role", "")
            content = m.get("content", "")
            if role == "user":
                self.agent_panel._append_user_message(content)
            elif role == "assistant":
                thinking = m.get("thinking", [])
                for t in thinking:
                    self.agent_panel._append_thinking_text(t)
                if content:
                    self.agent_panel._append_assistant_message(content)
```

- [ ] **Step 3: Apply same merge in `_on_back_to_current`**

In `_on_back_to_current`, after `messages = load_pi_messages(target)`, add:
```python
            messages = self._merge_consecutive_assistants(messages)
            messages = self._filter_knowledge_extraction(messages)
```

Replace the same rendering loop as in Step 2.

- [ ] **Step 4: Apply merge in `_on_pi_messages_received`** (fallback path)

Replace the rendering loop the same way.

---

### Task 2: Filter knowledge extraction from history

**Files:**
- Modify: `python3.11libs/edini/ui/main_window.py` — add `_filter_knowledge_extraction()`

- [ ] **Step 1: Add `_filter_knowledge_extraction()` method**

Insert before `_merge_consecutive_assistants`:

```python
    _KNOWLEDGE_PROMPT_PREFIX = "Review the conversation above and identify mistakes"

    def _filter_knowledge_extraction(self, messages: list) -> list:
        """Remove knowledge extraction prompt/response pairs from display."""
        result = []
        skip_next = False
        for m in messages:
            role = m.get("role", "")
            content = m.get("content", "")
            if role == "user" and isinstance(content, str):
                if content.startswith(self._KNOWLEDGE_PROMPT_PREFIX):
                    skip_next = True
                    continue
            if skip_next and role == "assistant":
                skip_next = False
                continue
            result.append(m)
        return result
```

- [ ] **Step 2: Verify filter inserted at load points**

Search for each occurrence of `load_pi_messages` in `main_window.py` and confirm `_filter_knowledge_extraction` is called immediately after.

Run:
```bash
grep -n "load_pi_messages\|_filter_knowledge" F:/zz/Edini/python3.11libs/edini/ui/main_window.py
```

Expected: each `load_pi_messages(...)` is immediately followed by `self._filter_knowledge_extraction(messages)`.

---

### Task 3: Filter self-changing params in snapshot diff

**Files:**
- Modify: `python3.11libs/edini/ui/snapshot_engine.py` — `diff()` function

- [ ] **Step 1: Add `_is_auto_param()` helper**

Insert at module level, before `diff()`:

```python
# Params that Houdini auto-updates — not user modifications
_AUTO_PARAM_PATTERNS = [
    "time",
    "frame",
    "*frame*",
    "*seed*",
    "*cache*",
    "*t*",          # shorthand for time
    "display*",     # viewport display flags
]

def _is_auto_param(name: str) -> bool:
    """Return True if param is auto-managed by Houdini (not user-visible change)."""
    import fnmatch
    for pat in _AUTO_PARAM_PATTERNS:
        if fnmatch.fnmatch(name, pat):
            return True
    return False
```

- [ ] **Step 2: Filter auto-params in `diff()` param comparison**

In `diff()`, inside the param comparison loop (around line 118), after `if old_val != new_val:`, add:

```python
            if old_val != new_val:
                # Skip Houdini auto-managed params (time, frame, seed, etc.)
                if _is_auto_param(parm):
                    continue
                # Skip tiny floating-point differences (< 1e-6)
                if isinstance(old_val, (int, float)) and isinstance(new_val, (int, float)):
                    try:
                        if abs(float(new_val) - float(old_val)) < 1e-6:
                            continue
                    except (ValueError, TypeError):
                        pass
                changes.append({"param": parm, "old": old_val, "new": new_val})
```

- [ ] **Step 3: Verify diff still works**

Run a quick logic test:

```bash
cd F:/zz/Edini && python -c "
from python3.11libs.edini.ui.snapshot_engine import _is_auto_param
assert _is_auto_param('time') == True
assert _is_auto_param('frame') == True
assert _is_auto_param('seed') == True
assert _is_auto_param('my_cache_path') == True
assert _is_auto_param('display_flag') == True
assert _is_auto_param('gridsize') == False
assert _is_auto_param('color') == False
print('All _is_auto_param tests passed')
"
```

---

### Task 4: Clear change tree on session switch/new

**Files:**
- Modify: `python3.11libs/edini/ui/main_window.py` — `_on_new_session`, `_on_session_selected`, `_on_back_to_current`

- [ ] **Step 1: Add `_reset_change_tree()` helper**

```python
    def _reset_change_tree(self):
        """Clear change tree and undo stack (on session switch)."""
        self.agent_panel.change_tree_widget.clear_all()
        self._undo_stack.clear()
        self._undo_pointer = -1
        self._round_counter = 0
```

- [ ] **Step 2: Call in `_on_new_session`**

In `_on_new_session`, after `self.agent_panel.clear_timeline()`, add:
```python
        self._reset_change_tree()
```

- [ ] **Step 3: Call in `_on_session_selected`**

In `_on_session_selected`, after `self.agent_panel.clear_timeline()`, add:
```python
        self._reset_change_tree()
```

- [ ] **Step 4: Call in `_on_back_to_current`**

In `_on_back_to_current`, after `self.agent_panel.clear_timeline()`, add:
```python
            self._reset_change_tree()
```

---

### Task 5: Verify and commit

- [ ] **Step 1: Syntax check**

```bash
cd F:/zz/Edini && python -c "import py_compile; py_compile.compile('python3.11libs/edini/ui/main_window.py', doraise=True); py_compile.compile('python3.11libs/edini/ui/snapshot_engine.py', doraise=True)" && echo "COMPILE OK"
```

- [ ] **Step 2: Commit**

```bash
git add python3.11libs/edini/ui/main_window.py python3.11libs/edini/ui/snapshot_engine.py
git commit -m "fix: merge history bubbles, filter knowledge extraction, fix change tree false positives and clearing"
```
