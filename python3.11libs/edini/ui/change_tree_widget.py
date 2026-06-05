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
        self._round_index = 0
        self._undo_pointer = -1

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
            detail = self._format_detail(action, row)

            # Compact label: path + brief description
            label = f"  {path}  · {detail}"
            item = QtWidgets.QTreeWidgetItem([label])
            item.setData(0, ROLE_ITEM_KIND, "change-node")
            item.setData(0, ROLE_ACTION_KEY, action)
            item.setData(1, ROLE_NODE_PATH, path)
            _style_path_item(item)
            group.addChild(item)

            if show_params:
                changes = row.get("changes", [])
                for change in changes:
                    old_str = _fmt_val(change.get("old"))
                    new_str = _fmt_val(change.get("new"))
                    parm_label = f"    {change['param']}: {old_str} → {new_str}"
                    parm_item = QtWidgets.QTreeWidgetItem([parm_label])
                    parm_item.setData(0, ROLE_ITEM_KIND, "param-change")
                    parm_item.setData(1, ROLE_NODE_PATH, path)
                    parm_item.setForeground(0, QtGui.QBrush(QtGui.QColor("#8b8fa8")))
                    item.addChild(parm_item)
                # Collapse modified nodes by default — user clicks to see params
                item.setExpanded(False)

        group.setExpanded(True)

    @staticmethod
    def _format_detail(action: str, row: dict) -> str:
        if action == "创建":
            node_type = row.get("type", "")
            parent = row.get("parent", "")
            if node_type and parent:
                return f"创建 {node_type}，位于 {parent}"
            if node_type:
                return f"创建 {node_type}"
            return "创建节点"
        if action == "删除":
            node_type = row.get("type", "")
            if node_type:
                return f"删除 {node_type}"
            return "删除节点"
        # Modified: show first 2 param names, or count
        changes = row.get("changes", [])
        if not changes:
            return "修改参数"
        if len(changes) <= 2:
            parts = []
            for c in changes:
                old_str = _fmt_val(c.get("old"))
                new_str = _fmt_val(c.get("new"))
                parts.append(f"{c['param']}: {old_str} → {new_str}")
            return ", ".join(parts)
        names = [c["param"] for c in changes[:3]]
        return f"{', '.join(names)} 等 {len(changes)} 个参数"

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
            is_current = (round_num - 1 == pointer)
            color = "#a78bfa" if is_current else "#c8ccd4"
            item.setForeground(0, QtGui.QBrush(QtGui.QColor(color)))
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
            round_num = total - self._undo_pointer
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


def _fmt_val(val) -> str:
    """Format a value for display, truncating long values."""
    if val is None:
        return "<none>"
    s = str(val)
    if len(s) > 60:
        return s[:57] + "..."
    return s
