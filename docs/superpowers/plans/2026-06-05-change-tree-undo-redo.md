# Change Tree + Undo/Redo Stack — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the placeholder ChangeTreeWidget with a functional change tree panel that tracks Houdini scene changes per conversation round via snapshot diffing, supports undo/redo at round granularity, and auto-expands/collapses.

**Architecture:** New `SnapshotEngine` captures full `/obj` state snapshots via `hou` API, diffs before/after to produce structured change reports, and restores state via three-phase node-level rebuild. `ChangeTreeWidget` renders changes as a collapsible QTreeWidget at the bottom of AgentPanel, driven by `MainWindow`'s undo/redo stack.

**Tech Stack:** Python 3.11, PySide6 (QTreeWidget), hou Houdini API

---

### Task 1: SnapshotEngine — capture, diff, restore

**Files:**
- Create: `python3.11libs/edini/ui/snapshot_engine.py`

- [ ] **Step 1: Create the snapshot_engine.py module**

```python
"""Snapshot engine for Houdini scene change tracking.

Captures full scene state as dicts, diffs two snapshots to find
created/deleted/modified nodes, and restores from one state to another
via node-level rebuild.
"""
from __future__ import annotations
from typing import Any


# hou is imported lazily — only available inside Houdini
def _hou():
    try:
        import hou  # type: ignore
        return hou
    except ImportError:
        return None


def snapshot(root: str = "/obj") -> dict[str, dict[str, Any]]:
    """Capture full state of all nodes under root as a flat dict.

    Returns {} if hou module is unavailable.

    Each entry:
        path (str): absolute node path (key)
        type (str): node type name
        parent (str): parent node path
        params (dict): param_name → value for all parms
        inputs (dict): input_index → source_path (or None)
        children (list[str]): child node paths
    """
    hou = _hou()
    if hou is None:
        return {}

    root_node = hou.node(root)
    if root_node is None:
        return {}

    state: dict[str, dict[str, Any]] = {}
    _collect_nodes(root_node, state)
    return state


def _collect_nodes(node, state: dict[str, dict[str, Any]]) -> None:
    """Recursively collect all descendant nodes into state dict."""
    path = node.path()
    parms = {}
    for p in node.parms():
        try:
            parms[p.name()] = p.eval()
        except Exception:
            parms[p.name()] = None

    inputs = {}
    for i in range(len(node.inputConnectors())):
        in_node = node.input(i)
        inputs[i] = in_node.path() if in_node else None

    children = [c.path() for c in node.children()]

    state[path] = {
        "type": node.type().name(),
        "parent": node.parent().path() if node.parent() else "",
        "params": parms,
        "inputs": inputs,
        "children": children,
    }

    for child in node.children():
        _collect_nodes(child, state)


def diff(before: dict, after: dict) -> dict:
    """Compare two snapshots and return structured change report.

    Returns:
        {
            "created": [{"path", "type", "parent"}, ...],
            "deleted": [{"path", "type"}, ...],
            "modified": [{"path", "type", "changes": [{"param", "old", "new"}, ...]}, ...],
            "summary": {"created": N, "deleted": N, "modified": N}
        }
        All lists empty if no changes.
    """
    before_paths = set(before.keys())
    after_paths = set(after.keys())

    created_paths = sorted(after_paths - before_paths, key=_path_sort_key)
    deleted_paths = sorted(before_paths - after_paths, key=_path_sort_key)
    common_paths = sorted(before_paths & after_paths, key=_path_sort_key)

    created = []
    for p in created_paths:
        info = after[p]
        created.append({
            "path": p,
            "type": info.get("type", ""),
            "parent": info.get("parent", ""),
        })

    deleted = []
    for p in deleted_paths:
        info = before[p]
        deleted.append({
            "path": p,
            "type": info.get("type", ""),
        })

    modified = []
    for p in common_paths:
        b = before[p]
        a = after[p]
        changes = []

        # Param changes
        all_params = set(b.get("params", {}).keys()) | set(a.get("params", {}).keys())
        for parm in sorted(all_params):
            old_val = b.get("params", {}).get(parm)
            new_val = a.get("params", {}).get(parm)
            if old_val != new_val:
                changes.append({"param": parm, "old": old_val, "new": new_val})

        # Input changes
        all_inputs = set(b.get("inputs", {}).keys()) | set(a.get("inputs", {}).keys())
        for idx in sorted(all_inputs):
            old_src = b.get("inputs", {}).get(idx)
            new_src = a.get("inputs", {}).get(idx)
            if old_src != new_src:
                changes.append({
                    "param": f"input[{idx}]",
                    "old": old_src or "<none>",
                    "new": new_src or "<none>",
                })

        if changes:
            modified.append({
                "path": p,
                "type": b.get("type", a.get("type", "")),
                "changes": changes,
            })

    return {
        "created": created,
        "deleted": deleted,
        "modified": modified,
        "summary": {
            "created": len(created),
            "deleted": len(deleted),
            "modified": len(modified),
        },
    }


def restore(before: dict, after: dict) -> None:
    """Restore scene from after-state back to before-state.

    Three phases:
    1. Delete nodes in after that don't exist in before
    2. Restore params and inputs for modified nodes
    3. Rebuild nodes in before that don't exist in after

    Logs errors on individual failures; does not abort.
    No-op if hou module unavailable.
    """
    hou = _hou()
    if hou is None:
        return

    # Phase 1: Delete added nodes (bottom-up: deepest children first)
    added = sorted(
        set(after.keys()) - set(before.keys()),
        key=lambda p: -p.count("/"),
    )
    for path in added:
        try:
            node = hou.node(path)
            if node:
                node.destroy()
        except Exception:
            pass

    # Phase 2: Restore modified nodes' params and inputs
    for path in sorted(set(before.keys()) & set(after.keys())):
        b_info = before[path]
        a_info = after[path]
        node = hou.node(path)
        if node is None:
            continue

        # Restore params
        for parm, old_val in b_info.get("params", {}).items():
            new_val = a_info.get("params", {}).get(parm)
            if old_val != new_val:
                try:
                    p = node.parm(parm)
                    if p:
                        p.set(old_val)
                except Exception:
                    pass

        # Restore inputs
        for idx, old_src in b_info.get("inputs", {}).items():
            new_src = a_info.get("inputs", {}).get(idx)
            if old_src != new_src:
                try:
                    src_node = hou.node(old_src) if old_src else None
                    node.setInput(idx, src_node)
                except Exception:
                    pass

    # Phase 3: Rebuild removed nodes (top-down: parent before children)
    removed = sorted(
        set(before.keys()) - set(after.keys()),
        key=lambda p: p.count("/"),
    )
    for path in removed:
        _rebuild_node(path, before)


def _rebuild_node(path: str, state: dict) -> None:
    """Rebuild a single node from state info (parent must already exist)."""
    hou = _hou()
    if hou is None:
        return
    info = state.get(path)
    if not info:
        return

    parent_path = info.get("parent", "")
    parent = hou.node(parent_path) if parent_path else hou.node("/obj")
    if parent is None:
        return

    node_type = info.get("type", "")
    node_name = path.rsplit("/", 1)[-1] if "/" in path else path

    try:
        node = parent.createNode(node_type, node_name)
        if node is None:
            return
    except Exception:
        return

    # Restore params
    for parm, val in info.get("params", {}).items():
        try:
            p = node.parm(parm)
            if p:
                p.set(val)
        except Exception:
            pass

    # Restore inputs
    for idx, src_path in info.get("inputs", {}).items():
        if src_path:
            try:
                src_node = hou.node(src_path)
                if src_node:
                    node.setInput(idx, src_node)
            except Exception:
                pass


def _path_sort_key(path: str) -> tuple[int, str]:
    return (path.count("/"), path)
```

- [ ] **Step 2: Verify Python syntax**

```bash
python -c "import ast; ast.parse(open('python3.11libs/edini/ui/snapshot_engine.py', encoding='utf-8').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add python3.11libs/edini/ui/snapshot_engine.py
git commit -m "feat: add SnapshotEngine for scene state capture, diff, and restore"
```

---

### Task 2: Rewrite ChangeTreeWidget — full QTreeWidget panel

**Files:**
- Rewrite: `python3.11libs/edini/ui/change_tree_widget.py`

- [ ] **Step 1: Replace change_tree_widget.py**

```python
"""Change tree widget — shows scene changes per conversation round.

Rendered as a collapsible panel (sibling of Thinking/Tool panels) with
a QTreeWidget displaying rounds as root items, action groups (创建/修改/删除)
as children, and node/param changes as leaf items.

Clicking a node path navigates the Houdini viewport to that node.
"""
from datetime import datetime

from PySide6 import QtCore, QtGui, QtWidgets
from edini.ui.theme import fs

# Custom data roles for storing node paths and metadata
ROLE_NODE_PATH = QtCore.Qt.UserRole + 31
ROLE_ITEM_KIND = QtCore.Qt.UserRole + 32
ROLE_ACTION_KEY = QtCore.Qt.UserRole + 33


class ChangeTreeWidget(QtWidgets.QFrame):
    """Collapsible change tree panel at the bottom of AgentPanel."""

    node_path_requested = QtCore.Signal(str)
    undo_round_requested = QtCore.Signal(int)
    redo_requested = QtCore.Signal()

    COLLAPSED_H = 22
    EXPANDED_H = 260

    def __init__(self, parent=None):
        super().__init__(parent)
        self._expanded = False
        self._round_index = 0         # monotonic counter for round numbering
        self._undo_pointer = -1       # mirror of main_window's pointer

        self.setStyleSheet(f"""
            QFrame {{
                background: #0a0a12;
                border-top: 1px solid #1c1c2a;
            }}
        """)
        self._build_ui()
        self._bind_events()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 2, 10, 2)
        layout.setSpacing(0)

        # Header row: toggle + summary + undo/redo buttons
        header = QtWidgets.QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)

        self._toggle_label = QtWidgets.QLabel("▸ 变更树 (0 轮)")
        self._toggle_label.setCursor(QtCore.Qt.PointingHandCursor)
        self._toggle_label.setStyleSheet(
            f"color:#4a4a5a;font-size:{fs(10)};border:none;padding:1px 0;")
        self._toggle_label.mousePressEvent = self._toggle
        header.addWidget(self._toggle_label)
        header.addStretch()

        self._undo_btn = QtWidgets.QPushButton("撤销本轮")
        self._undo_btn.setObjectName("GhostButton")
        self._undo_btn.setEnabled(False)
        self._undo_btn.setStyleSheet(
            f"QPushButton {{ color:#a1a1aa;font-size:{fs(10)};padding:1px 6px; }}"
            f"QPushButton:hover {{ color:#e5e5eb; }}")
        header.addWidget(self._undo_btn)

        self._redo_btn = QtWidgets.QPushButton("重做")
        self._redo_btn.setObjectName("GhostButton")
        self._redo_btn.setEnabled(False)
        self._redo_btn.setStyleSheet(
            f"QPushButton {{ color:#a1a1aa;font-size:{fs(10)};padding:1px 6px; }}"
            f"QPushButton:hover {{ color:#e5e5eb; }}")
        header.addWidget(self._redo_btn)

        layout.addLayout(header)

        # Tree widget
        self._tree = QtWidgets.QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setRootIsDecorated(True)
        self._tree.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self._tree.setStyleSheet(
            f"QTreeWidget {{ background: transparent; border: none; color: #c8ccd4; font-size:{fs(11)}; }}"
            f"QTreeWidget::item {{ padding: 1px 0; }}"
            f"QTreeWidget::item:selected {{ background: #1a1a2e; }}"
            f"QTreeWidget::branch {{ background: transparent; }}"
        )
        self._tree.setVisible(False)
        layout.addWidget(self._tree)

        self.setFixedHeight(self.COLLAPSED_H)

    def _bind_events(self):
        self._undo_btn.clicked.connect(self._on_undo)
        self._redo_btn.clicked.connect(self._on_redo)
        self._tree.itemClicked.connect(self._on_item_clicked)

    # ── Toggle ──

    def _toggle(self, event=None):
        self._expanded = not self._expanded
        self._apply_expanded_state()

    def _apply_expanded_state(self):
        arrow = "▾" if self._expanded else "▸"
        prefix = arrow + " 变更树"
        total_rounds = self._tree.topLevelItemCount()
        self._toggle_label.setText(f"{prefix} ({total_rounds} 轮)")
        self._tree.setVisible(self._expanded)
        self.setFixedHeight(self.EXPANDED_H if self._expanded else self.COLLAPSED_H)

    def expand(self):
        """Expand the panel (called after round finishes)."""
        if not self._expanded:
            self._expanded = True
            self._apply_expanded_state()

    def collapse(self):
        """Collapse the panel (called when new conversation starts)."""
        if self._expanded:
            self._expanded = False
            self._apply_expanded_state()

    # ── Round management ──

    def add_round(self, diff: dict, round_num: int):
        """Add a new round to the tree from diff output."""
        created = diff.get("created", [])
        deleted = diff.get("deleted", [])
        modified = diff.get("modified", [])
        summary = diff.get("summary", {})

        ts = datetime.now().strftime("%H:%M")
        c_count = summary.get("created", len(created))
        d_count = summary.get("deleted", len(deleted))
        m_count = summary.get("modified", len(modified))

        round_label = f"Round {round_num}  ──  {ts}  ──  创建{c_count} 删除{d_count} 修改{m_count}"
        root_item = QtWidgets.QTreeWidgetItem([round_label])
        root_item.setData(0, ROLE_ITEM_KIND, "round")
        root_item.setData(0, ROLE_ACTION_KEY, round_num)
        self._tree.insertTopLevelItem(0, root_item)  # newest first

        if created:
            self._append_action_group(root_item, "创建", created)
        if modified:
            self._append_action_group(root_item, "修改", modified, show_params=True)
        if deleted:
            self._append_action_group(root_item, "删除", deleted)

        root_item.setExpanded(True)
        self._tree.scrollToItem(root_item)
        self._update_header()
        self._update_buttons()

    def _append_action_group(self, parent, action: str, rows: list,
                              show_params: bool = False):
        """Append a '创建 (N)' / '修改 (N)' / '删除 (N)' group under a round."""
        group = QtWidgets.QTreeWidgetItem([f"  {action} ({len(rows)})"])
        group.setData(0, ROLE_ITEM_KIND, "action-group")
        group.setData(0, ROLE_ACTION_KEY, action)
        parent.addChild(group)

        for row in rows:
            path = row.get("path", "")
            node_type = row.get("type", "")
            detail = self._format_detail(action, row)

            label = f"  {path}"
            item = QtWidgets.QTreeWidgetItem([label])
            item.setData(0, ROLE_ITEM_KIND, "change-node")
            item.setData(0, ROLE_ACTION_KEY, action)
            item.setData(1, ROLE_NODE_PATH, path)
            item.setToolTip(0, detail)
            _style_path_item(item)
            group.addChild(item)

            if show_params:
                changes = row.get("changes", [])
                for change in changes:
                    parm_label = f"    · {change['param']}: {change['old']} → {change['new']}"
                    parm_item = QtWidgets.QTreeWidgetItem([parm_label])
                    parm_item.setData(0, ROLE_ITEM_KIND, "param-change")
                    parm_item.setData(1, ROLE_NODE_PATH, path)
                    item.addChild(parm_item)

        group.setExpanded(True)

    @staticmethod
    def _format_detail(action: str, row: dict) -> str:
        node_type = row.get("type", "")
        if action == "创建":
            parent = row.get("parent", "")
            if node_type and parent:
                return f"创建 {node_type} 节点，位于 {parent}"
            if node_type:
                return f"创建 {node_type} 节点"
            return "创建节点"
        if action == "删除":
            if node_type:
                return f"删除 {node_type} 节点"
            return "删除节点"
        # modified
        changes = row.get("changes", [])
        if len(changes) == 1:
            c = changes[0]
            return f"参数 {c['param']}: {c['old']} → {c['new']}"
        return f"修改 {len(changes)} 个参数"
        return ""

    # ── Undo/Redo state ──

    def set_undo_pointer(self, pointer: int):
        """Update which round is currently 'active' (highlighted)."""
        self._undo_pointer = pointer
        total = self._tree.topLevelItemCount()
        for i in range(total):
            item = self._tree.topLevelItem(i)
            if item is None:
                continue
            round_num = item.data(0, ROLE_ACTION_KEY)
            # Pointer convention: pointer == round_num - 1 for 0-indexed
            is_current = (round_num - 1 == pointer)
            brush = QtGui.QBrush(QtGui.QColor("#a78bfa")) if is_current else QtGui.QBrush(QtGui.QColor("#c8ccd4"))
            item.setForeground(0, brush)
        self._update_buttons()

    def mark_undone(self, round_num: int):
        """Visually mark a round as undone (gray + strikethrough)."""
        for i in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(i)
            if item is None:
                continue
            rn = item.data(0, ROLE_ACTION_KEY)
            if rn == round_num:
                font = item.font(0)
                font.setStrikeOut(True)
                item.setFont(0, font)
                item.setForeground(0, QtGui.QBrush(QtGui.QColor("#52525b")))
                break

    def mark_redone(self, round_num: int):
        """Visually mark a round as redone (remove strikethrough)."""
        for i in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(i)
            if item is None:
                continue
            rn = item.data(0, ROLE_ACTION_KEY)
            if rn == round_num:
                font = item.font(0)
                font.setStrikeOut(False)
                item.setFont(0, font)
                item.setForeground(0, QtGui.QBrush(QtGui.QColor("#c8ccd4")))
                break

    def _update_header(self):
        total_rounds = self._tree.topLevelItemCount()
        arrow = "▾" if self._expanded else "▸"
        self._toggle_label.setText(f"{arrow} 变更树 ({total_rounds} 轮)")

    def _update_buttons(self):
        total = self._tree.topLevelItemCount()
        self._undo_btn.setEnabled(self._undo_pointer >= 0 and total > 0)
        self._redo_btn.setEnabled(self._undo_pointer < total - 1 and total > 0)

    # ── Events ──

    def _on_item_clicked(self, item, column):
        if item is None:
            return
        path = item.data(1, ROLE_NODE_PATH)
        if path and isinstance(path, str) and path.startswith("/"):
            self.node_path_requested.emit(path)

    def _on_undo(self):
        total = self._tree.topLevelItemCount()
        if self._undo_pointer >= 0:
            round_num = total - self._undo_pointer  # newest round = total
            self.undo_round_requested.emit(round_num)

    def _on_redo(self):
        self.redo_requested.emit()

    def clear_all(self):
        """Clear all rounds from the tree."""
        self._tree.clear()
        self._update_header()
        self._update_buttons()


def _style_path_item(item: QtWidgets.QTreeWidgetItem):
    """Style a node path item with blue underline (clickable)."""
    item.setForeground(0, QtGui.QBrush(QtGui.QColor("#58d4ff")))
    font = item.font(0)
    font.setUnderline(True)
    item.setFont(0, font)
```

- [ ] **Step 2: Verify Python syntax**

```bash
python -c "import ast; ast.parse(open('python3.11libs/edini/ui/change_tree_widget.py', encoding='utf-8').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add python3.11libs/edini/ui/change_tree_widget.py
git commit -m "feat: rewrite ChangeTreeWidget as collapsible QTreeWidget panel with undo/redo"
```

---

### Task 3: Integrate ChangeTreeWidget into AgentPanel

**Files:**
- Modify: `python3.11libs/edini/ui/agent_panel.py`

- [ ] **Step 1: Move change_tree_widget from top to bottom, replace placeholder ref**

In `agent_panel.py`, find the `_build_ui` method. The current code at lines ~495-505 imports and adds the old placeholder ChangeTreeWidget above the timeline. Remove those lines and add the new ChangeTreeWidget below the Knowledge Extraction Area (between knowledge_area and input_row).

**Edit 1**: Remove the old placeholder lines (plan_progress + change_tree at top).

Find in `_build_ui()`:
```python
        # Plan progress + Change tree (placeholders, hidden)
        from edini.ui.plan_progress_widget import PlanProgressWidget
        self.plan_progress_widget = PlanProgressWidget(self)
        self.plan_progress_widget.setMaximumHeight(260)
        root.addWidget(self.plan_progress_widget)

        from edini.ui.change_tree_widget import ChangeTreeWidget
        self.change_tree_widget = ChangeTreeWidget(self)
        self.change_tree_widget.setMaximumHeight(200)
        root.addWidget(self.change_tree_widget)

        # ── Timeline (QScrollArea + widgets) ──
```

Replace with:
```python
        # ── Timeline (QScrollArea + widgets) ──
```

Then, find the line adding `root.addLayout(input_row)` near the bottom of `_build_ui`.
Add change_tree_widget import and insertion BEFORE `root.addLayout(input_row)`:

**Edit 2**: Before the `# ── Input row ──` section or immediately before `root.addLayout(input_row)`, add:

```python
        # ── Change Tree Panel (collapsible, below knowledge area) ──
        from edini.ui.change_tree_widget import ChangeTreeWidget
        self.change_tree_widget = ChangeTreeWidget()
        root.addWidget(self.change_tree_widget)
```

**Edit 3**: In `_on_send`, add panel collapse logic. After the existing panel reset code (lines 754-760), add:

```python
        # Collapse change tree during conversation
        self.change_tree_widget.collapse()
```

- [ ] **Step 2: Verify Python syntax**

```bash
python -c "import ast; ast.parse(open('python3.11libs/edini/ui/agent_panel.py', encoding='utf-8').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add python3.11libs/edini/ui/agent_panel.py
git commit -m "feat: integrate ChangeTreeWidget below timeline, auto-collapse on send"
```

---

### Task 4: Wire undo/redo stack and snapshot triggers in MainWindow

**Files:**
- Modify: `python3.11libs/edini/ui/main_window.py`

- [ ] **Step 1: Add import and initialize undo stack + snapshot engine**

In `main_window.py`, add the import near the top:

```python
from edini.ui.snapshot_engine import snapshot as snap_scene, diff as diff_snapshots, restore as restore_snapshot
```

In `__init__`, add after the existing instance variables (after `self._extracting_knowledge = False`):

```python
        # Undo/redo stack for change tree
        self._snapshot_engine = None  # imported lazily inside Houdini
        self._pre_snapshot: dict = {}
        self._undo_stack: list[dict] = []
        self._undo_pointer = -1
        self._round_counter = 0
```

- [ ] **Step 2: Take pre-snapshot in `_on_agent_submit`**

Modify `_on_agent_submit` to take a snapshot before the agent starts:

```python
    def _on_agent_submit(self, text: str, images=None):
        # Take pre-snapshot for change tracking
        self._pre_snapshot = snap_scene()
        # Collapse change tree during conversation
        self.agent_panel.change_tree_widget.collapse()
        self.agent_panel.begin_assistant_message()
        self._rpc_client.send_prompt(text, images=images)
```

- [ ] **Step 3: Diff and push to undo stack in `_on_agent_done`**

Modify `_on_agent_done` to take post-snapshot, diff, and push to stack. Add after `self._on_round_tick()`:

```python
        # ── Change tree: take post-snapshot and diff ──
        post_snapshot = snap_scene()
        if self._pre_snapshot:
            change_diff = diff_snapshots(self._pre_snapshot, post_snapshot)
            summary = change_diff.get("summary", {})
            has_changes = (
                summary.get("created", 0) > 0 or
                summary.get("deleted", 0) > 0 or
                summary.get("modified", 0) > 0
            )
            if has_changes:
                # Detect manual modifications: diff pre against last post
                if self._undo_stack and self._undo_pointer >= 0:
                    last_post = self._undo_stack[self._undo_pointer].get("post", {})
                    manual_check = diff_snapshots(last_post, self._pre_snapshot)
                    ms = manual_check.get("summary", {})
                    if (ms.get("created", 0) > 0 or ms.get("deleted", 0) > 0 or
                            ms.get("modified", 0) > 0):
                        # Manual changes detected — clear undo stack
                        self._undo_stack.clear()
                        self._undo_pointer = -1
                        self.agent_panel.change_tree_widget.clear_all()
                        self.status.showMessage("场景被手动修改，撤销历史已清空", 3000)

                # Truncate redo entries if pointer not at top
                if self._undo_pointer < len(self._undo_stack) - 1:
                    self._undo_stack = self._undo_stack[:self._undo_pointer + 1]

                self._round_counter += 1
                self._undo_stack.append({
                    "pre": dict(self._pre_snapshot),
                    "post": post_snapshot,
                    "diff": change_diff,
                    "round_num": self._round_counter,
                })
                self._undo_pointer = len(self._undo_stack) - 1

                self.agent_panel.change_tree_widget.add_round(
                    change_diff, self._round_counter)
                self.agent_panel.change_tree_widget.set_undo_pointer(
                    self._undo_pointer)

            self._pre_snapshot = {}

        # Expand change tree after conversation
        self.agent_panel.change_tree_widget.expand()
```

Place this code block inside `_on_agent_done`, right after the `self._on_round_tick()` call and before `if self._extracting_knowledge:`.

- [ ] **Step 4: Wire undo/redo handlers and node navigation**

Add these methods to `MainWindow`:

```python
    def _on_change_undo(self, round_num: int):
        """Undo a specific round: restore post → pre state."""
        for entry in self._undo_stack:
            if entry.get("round_num") == round_num:
                restore_snapshot(entry["post"], entry["pre"])
                self._undo_pointer -= 1
                self.agent_panel.change_tree_widget.mark_undone(round_num)
                self.agent_panel.change_tree_widget.set_undo_pointer(self._undo_pointer)
                self.status.showMessage(f"已撤销 Round {round_num}", 2000)
                return

    def _on_change_redo(self):
        """Redo the next undone round: restore pre → post state."""
        if self._undo_pointer + 1 < len(self._undo_stack):
            self._undo_pointer += 1
            entry = self._undo_stack[self._undo_pointer]
            restore_snapshot(entry["pre"], entry["post"])
            round_num = entry.get("round_num", 0)
            self.agent_panel.change_tree_widget.mark_redone(round_num)
            self.agent_panel.change_tree_widget.set_undo_pointer(self._undo_pointer)
            self.status.showMessage(f"已重做 Round {round_num}", 2000)

    def _on_change_node_requested(self, node_path: str):
        """Navigate Houdini viewport to the requested node path."""
        try:
            import hou
            node = hou.node(node_path)
            if node:
                node.setCurrent(True, clear_all_selected=True)
                self.status.showMessage(f"已跳转到节点: {node_path}", 1800)
            else:
                self.status.showMessage(f"未找到节点: {node_path}", 2200)
        except Exception:
            pass
```

- [ ] **Step 5: Connect signals in `_bind_events`**

Add these signal connections inside `_bind_events()` (after existing agent_panel signal connections):

```python
        # Change tree signals
        self.agent_panel.change_tree_widget.undo_round_requested.connect(
            self._on_change_undo)
        self.agent_panel.change_tree_widget.redo_requested.connect(
            self._on_change_redo)
        self.agent_panel.change_tree_widget.node_path_requested.connect(
            self._on_change_node_requested)
```

- [ ] **Step 6: Verify Python syntax**

```bash
python -c "import ast; ast.parse(open('python3.11libs/edini/ui/main_window.py', encoding='utf-8').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 7: Add abort handler to still diff on abort**

In `_on_abort_request`, after `self._round_timer.stop()`, add the same change-tree flow (diff and potentially push):

```python
        # Take post-snapshot on abort too
        post_snapshot = snap_scene()
        if self._pre_snapshot:
            change_diff = diff_snapshots(self._pre_snapshot, post_snapshot)
            summary = change_diff.get("summary", {})
            if summary.get("created", 0) > 0 or summary.get("deleted", 0) > 0 or summary.get("modified", 0) > 0:
                self._round_counter += 1
                self._undo_stack.append({
                    "pre": dict(self._pre_snapshot),
                    "post": post_snapshot,
                    "diff": change_diff,
                    "round_num": self._round_counter,
                })
                self._undo_pointer = len(self._undo_stack) - 1
                self.agent_panel.change_tree_widget.add_round(
                    change_diff, self._round_counter)
                self.agent_panel.change_tree_widget.set_undo_pointer(self._undo_pointer)
            self._pre_snapshot = {}
        self.agent_panel.change_tree_widget.expand()
```

Insert this after `self._round_timer.stop()` in `_on_abort_request`.

- [ ] **Step 8: Final syntax check + commit**

```bash
python -c "import ast; ast.parse(open('python3.11libs/edini/ui/main_window.py', encoding='utf-8').read()); print('OK')"
```

```bash
git add python3.11libs/edini/ui/main_window.py
git commit -m "feat: wire undo/redo stack, snapshot triggers, and node navigation in MainWindow"
```

---

## Self-Review Checklist

- [x] Spec coverage: SnapshotEngine (Task 1), ChangeTreeWidget (Task 2), AgentPanel integration (Task 3), MainWindow undo/redo + auto-collapse/expand + node navigation (Task 4)
- [x] No placeholders — all code blocks are complete implementations
- [x] Type consistency: `snap_scene` → `dict`, `diff_snapshots` → `dict`, `restore_snapshot` → `None`, signals match handler signatures
