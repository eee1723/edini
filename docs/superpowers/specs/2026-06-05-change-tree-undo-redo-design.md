# Change Tree + Undo/Redo Stack — Design Spec

> Date: 2026-06-05 | Status: Approved | Reference: EEEAi_Houdini

## Overview

Replace Edini's placeholder `ChangeTreeWidget` with a fully functional change tree panel that:

1. **Tracks scene changes** per conversation round via snapshot diffing (SnapshotEngine)
2. **Renders a hierarchical tree** at the bottom of the AgentPanel (sibling of Thinking/Tool panels)
3. **Supports undo/redo** at round granularity — each conversation round is one atomic transaction
4. **Auto-expands** when a conversation round finishes, **auto-collapses** during active conversation
5. **Navigates to nodes** in the Houdini viewport on click

## Architecture

```
                        ┌─────────────────────────────┐
                        │     ChangeTreeWidget         │
                        │   (底部可折叠面板，和 Thinking  │
                        │    / Tool Panel 同级)         │
                        │                              │
                        │  Round 3  创建2 修改1         │  ← current (highlighted)
                        │    + /obj/geo1/pyro1 (创建)   │  ← clickable → jump
                        │    ~ /obj/geo1/pyro1 (修改)   │  ← expandable → params
                        │  Round 2  创建1 删除1         │  ← collapsible
                        │  Round 1  创建1               │
                        │                              │
                        │  [撤销本轮] [重做]             │  ← header buttons
                        └──────────────┬──────────────┘
                                       │
              ┌────────────────────────┼────────────────────────┐
              │                        │                        │
     snapshot()               diff(before, after)        restore(before, after)
              │                        │                        │
              └────────────────────────┼────────────────────────┘
                                       │
                        ┌──────────────v──────────────┐
                        │     SnapshotEngine           │
                        │  (python3.11libs/edini/ui/   │
                        │   snapshot_engine.py)        │
                        │                              │
                        │  snapshot(root) → dict       │
                        │  diff(before, after) →       │
                        │    {created, deleted,        │
                        │     modified}                │
                        │  restore(before, after)      │
                        └──────────────────────────────┘
```

## Data Flow

```
_on_send()
  ├── pre_snapshot = snapshot_engine.snapshot()
  └── emit submit_requested

_on_agent_done()
  ├── post_snapshot = snapshot_engine.snapshot()
  ├── diff = snapshot_engine.diff(pre_snapshot, post_snapshot)
  ├── if diff has meaningful changes:
  │     _undo_stack.append({pre, post, diff, round_num, ts})
  │     _undo_pointer = len(stack) - 1
  │     change_tree_widget.add_round(diff)
  └── change_tree_widget.expand()

undo:
  ├── entry = _undo_stack[_undo_pointer]
  ├── snapshot_engine.restore(entry.post, entry.pre)
  ├── _undo_pointer -= 1
  └── change_tree_widget.mark_undone(round_index)

redo:
  ├── _undo_pointer += 1
  ├── entry = _undo_stack[_undo_pointer]
  ├── snapshot_engine.restore(entry.pre, entry.post)
  └── change_tree_widget.mark_redone(round_index)
```

## File Plan

| File | Action | Purpose |
|------|--------|---------|
| `python3.11libs/edini/ui/snapshot_engine.py` | **New** | Snapshot capture, diff, restore |
| `python3.11libs/edini/ui/change_tree_widget.py` | **Rewrite** | Full QTreeWidget panel from placeholder |
| `python3.11libs/edini/ui/main_window.py` | **Modify** | Undo/redo stack, auto collapse/expand logic |
| `python3.11libs/edini/ui/agent_panel.py` | **Modify** | Add change_tree_widget below timeline |

## SnapshotEngine API

### `snapshot(root: str = "/obj") -> dict[str, dict]`

Traverse `hou.node(root)` and all descendants. For each node, capture:

```python
{
    "path": "/obj/geo1",
    "type": "geo",
    "parent": "/obj",
    "params": {"tx": 0.0, "ty": 0.0, ...},
    "inputs": {0: "/obj/geo1/null1", 1: None},
    "children": ["/obj/geo1/null1", "/obj/geo1/scatter1"]
}
```

- Capture all current param values (needed for accurate rebuild in Phase 3)
- `inputs` maps input index → source node path (or None)
- `children` is a shallow list of child paths (not recursive dicts)
- Returns `{}` if `hou` module unavailable
- Target: <50ms for <100 nodes; use `QApplication.processEvents()` for large scenes

### `diff(before: dict, after: dict) -> dict`

```python
{
    "created": [
        {"path": "/obj/geo1/new_node", "type": "null", "parent": "/obj/geo1"}
    ],
    "deleted": [
        {"path": "/obj/geo1/old_node", "type": "null"}
    ],
    "modified": [
        {
            "path": "/obj/geo1/pyro1",
            "type": "pyro",
            "changes": [
                {"param": "gridsize", "old": 0.1, "new": 0.05},
                {"param": "divisions", "old": 40, "new": 80}
            ]
        }
    ],
    "summary": {"created": 1, "deleted": 1, "modified": 1}
}
```

- Returns all-empty if no changes
- Connections changes are treated as modified entries

### `restore(before: dict, after: dict) -> None`

Restore from `after` state back to `before` state. **Three-phase atomic approach:**

1. **Delete**: remove all nodes in `set(after) - set(before)`
2. **Restore modified**: for shared nodes, reset changed params and reconnect inputs
3. **Rebuild**: recreate nodes in `set(before) - set(after)`, including params and connections

Node rebuild is recursive — if a parent node needs rebuilding, its children from `before` are also rebuilt. Each phase logs errors but does not abort on individual failure.

## ChangeTreeWidget

### Signals

```python
node_path_requested = Signal(str)    # Click node path → jump to viewport
undo_round_requested = Signal(int)   # Undo round N
redo_requested = Signal()            # Redo next round
```

### Layout

```
┌─────────────────────────────────────────────┐
│  ▾ 变更树 (N 轮, M 节点)              [撤销本轮] [重做] │  ← header
├─────────────────────────────────────────────┤
│  QTreeWidget                                │
│    Round root items (sorted by time, newest first)   │
│      Action group items (创建/修改/删除)              │
│        Node items (clickable path, expandable)        │
│          Param change items (name, old→new)            │
└─────────────────────────────────────────────┘
```

### Tree Structure

```
▼ Round 3 ── 2026-06-05 15:32 ── 创建2 修改1     ← root item
  ▼ 创建 (2)                                      ← action group
    + /obj/geo1/pyro1       创建 Pyro 节点          ← node item (clickable)
    + /obj/geo1/pyro1/smoke 创建 Smoke 节点
  ▼ 修改 (1)                                      ← action group
    ~ /obj/geo1/pyro1       修改 3 个参数           ← node item (expandable)
      · gridsize: 0.1 → 0.05                      ← param item
      · divisions: 40 → 80
      · timestep: 1/24 → 1/48
```

### Interaction Rules

| Action | Trigger | Effect |
|--------|---------|--------|
| Expand/collapse panel | Click header arrow | Toggle visibility, no undo/redo effect |
| Auto-collapse | `_on_send` | Panel folded, tree hidden |
| Auto-expand | `_on_agent_done` | Panel expanded, new round visible |
| Jump to node | Click blue underlined path | `hou.node(path).setCurrent(True, clear_all_selected=True)` + frame viewport |
| Undo round | Click [撤销本轮] | Restore post→pre of current pointer round |
| Redo | Click [重做] | Restore pre→post of pointer+1 round |
| Expand round | Click ▼ arrow | Show node list for that round |
| Expand params | Click ~ modified entry | Show parameter change details |

### Undo Visual State

- Undone round: gray text + strikethrough
- Current pointer round: highlighted background
- [撤销本轮] label shows: "撤销 Round N"
- When at stack bottom (no more to undo): button disabled
- When at stack top (no more to redo): button disabled

## MainWindow Undo/Redo Stack

```python
_undo_stack: list[dict]   # [{"pre", "post", "diff", "round_num", "timestamp"}]
_undo_pointer: int         # -1 = empty, N = stack index
```

- New round → append, truncate any redo entries beyond pointer
- Undo → `_undo_pointer -= 1`, restore
- Redo → `_undo_pointer += 1`, restore
- Manual scene modification detected → clear stack, set pointer to -1

## Edge Cases

| Scenario | Handling |
|----------|----------|
| Round has no meaningful changes | Don't push to undo stack, don't display in tree |
| User manually modifies scene between rounds | Next `_on_send` pre_snapshot diffs against last post_snapshot; if non-empty → clear undo stack + show warning |
| New conversation during undo (stack truncated) | `_undo_stack = _undo_stack[:_undo_pointer+1]` then append new round |
| restore() rebuild fails | Log error, continue with remaining nodes; don't abort |
| Large scene (>1000 nodes) | `QApplication.processEvents()` in snapshot loop to prevent UI freeze |
| `hou` module unavailable | All snapshot/restore methods return empty/no-op |
| Rapid successive sends | pre_snapshot captured synchronously in `_on_send`; no race |

## Snapshot Scope

- Default root: `/obj` (where most user-created nodes live)
- Configurable via `EDINI_SNAPSHOT_ROOT` env var
- Does NOT recurse into subnet children for performance (only direct descendants)

## Testing

| Level | Test | Method |
|-------|------|--------|
| Unit | `diff()` correctness | Create/modify/delete nodes in Houdini, verify diff output |
| Unit | `diff()` empty case | Two snapshots with no changes → all-empty result |
| Unit | `restore()` round-trip | snapshot → modify → snapshot → restore → verify back to original |
| Integration | Undo/redo full flow | 2 rounds → undo round 1 → verify scene → redo → verify scene |
| Integration | Manual modification detection | Round → manual create → new round → verify stack cleared |
| UI | Panel collapse/expand/jump | Click node path → verify viewport selection |

## Dependencies

- `hou` module (Houdini Python API) — for all snapshot/restore operations
- `PySide6.QtWidgets.QTreeWidget` — for change tree display
- Existing: `agent_panel.py`, `main_window.py`
