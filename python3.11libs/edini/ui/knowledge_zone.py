"""Knowledge Zone widget for the right panel.

Two modes:
- Browse: Collapsible lists of iron rules and knowledge entries
- Reflecting: Shows reflection progress and extracted items for review
"""

from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from edini.ui.theme import fs


def _section_btn(text: str) -> QtWidgets.QPushButton:
    """Collapsible section toggle button."""
    btn = QtWidgets.QPushButton(text)
    btn.setFlat(True)
    btn.setStyleSheet(f"""
        QPushButton {{
            color: #80cbc4; font-size: {fs(11)}; font-weight: 600;
            border: none; text-align: left; padding: 4px 2px;
        }}
        QPushButton:hover {{ color: #0bc; }}
    """)
    return btn


def _item_label(text: str, color: str = "#94a3b8") -> QtWidgets.QLabel:
    lbl = QtWidgets.QLabel(text)
    lbl.setStyleSheet(f"color: {color}; font-size: {fs(10)}; border: none;")
    lbl.setWordWrap(True)
    return lbl


def _action_btn(text: str, bg: str) -> QtWidgets.QPushButton:
    btn = QtWidgets.QPushButton(text)
    btn.setFixedHeight(22)
    btn.setStyleSheet(f"""
        QPushButton {{
            background: {bg}; color: #e5e5eb; border: none;
            border-radius: 3px; font-size: {fs(10)}; padding: 0 8px;
        }}
        QPushButton:hover {{ background: {bg}cc; }}
    """)
    return btn


class KnowledgeZone(QtWidgets.QWidget):
    """Knowledge panel with browse + reflection overlay."""

    items_accepted = QtCore.Signal(list)
    reflection_requested = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rules_expanded = False
        self._entries_expanded = False
        self._pending_items: list[dict] = []

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Header
        header = QtWidgets.QHBoxLayout()
        self._title = QtWidgets.QLabel("📚 Knowledge")
        self._title.setStyleSheet(
            f"color: #80cbc4; font-size: {fs(12)}; font-weight: 700; border: none;")
        header.addWidget(self._title)
        header.addStretch()
        layout.addLayout(header)

        # Browse container
        self._browse = QtWidgets.QWidget()
        self._browse_layout = QtWidgets.QVBoxLayout(self._browse)
        self._browse_layout.setContentsMargins(0, 0, 0, 0)
        self._browse_layout.setSpacing(2)

        # Rules section
        self._rules_btn = _section_btn("▶ Iron Rules (0)")
        self._rules_btn.clicked.connect(self._toggle_rules)
        self._browse_layout.addWidget(self._rules_btn)
        self._rules_list = QtWidgets.QWidget()
        self._rules_list.setVisible(False)
        self._rules_list_layout = QtWidgets.QVBoxLayout(self._rules_list)
        self._rules_list_layout.setContentsMargins(8, 0, 0, 0)
        self._rules_list_layout.setSpacing(1)
        self._browse_layout.addWidget(self._rules_list)

        # Entries section
        self._entries_btn = _section_btn("▶ Entries (0)")
        self._entries_btn.clicked.connect(self._toggle_entries)
        self._browse_layout.addWidget(self._entries_btn)
        self._entries_list = QtWidgets.QWidget()
        self._entries_list.setVisible(False)
        self._entries_list_layout = QtWidgets.QVBoxLayout(self._entries_list)
        self._entries_list_layout.setContentsMargins(8, 0, 0, 0)
        self._entries_list_layout.setSpacing(1)
        self._browse_layout.addWidget(self._entries_list)

        layout.addWidget(self._browse)

        # Reflection overlay (hidden by default)
        self._reflect_area = QtWidgets.QFrame()
        self._reflect_area.setStyleSheet("""
            QFrame {
                background: #0a0a12;
                border: 1px solid #1e2e2e;
                border-radius: 4px;
            }
        """)
        self._reflect_layout = QtWidgets.QVBoxLayout(self._reflect_area)
        self._reflect_layout.setContentsMargins(8, 6, 8, 6)
        self._reflect_layout.setSpacing(4)

        self._reflect_status = QtWidgets.QLabel("")
        self._reflect_status.setStyleSheet(
            f"color: #80cbc4; font-size: {fs(11)}; border: none;")
        self._reflect_layout.addWidget(self._reflect_status)

        self._reflect_items = QtWidgets.QWidget()
        self._reflect_items_layout = QtWidgets.QVBoxLayout(self._reflect_items)
        self._reflect_items_layout.setContentsMargins(0, 0, 0, 0)
        self._reflect_items_layout.setSpacing(3)
        self._reflect_items_layout.addStretch()
        self._reflect_layout.addWidget(self._reflect_items)

        btn_row = QtWidgets.QHBoxLayout()
        self._accept_all_btn = _action_btn("✓ 全部接受", "#16a34a")
        self._accept_all_btn.clicked.connect(self._on_accept_all)
        self._reject_all_btn = _action_btn("✕ 全部放弃", "#555")
        self._reject_all_btn.clicked.connect(self._on_reject_all)
        btn_row.addWidget(self._accept_all_btn)
        btn_row.addWidget(self._reject_all_btn)
        self._reflect_layout.addLayout(btn_row)

        self._reflect_area.setVisible(False)
        layout.addWidget(self._reflect_area)

    # ── Browse mode ──

    def refresh(self) -> None:
        from edini.ui.knowledge_store import load_rules, load_entries
        rules = load_rules()
        entries = load_entries()
        self._rules_btn.setText(f"▶ Iron Rules ({len(rules)})")
        self._entries_btn.setText(f"▶ Entries ({len(entries)})")
        self._populate_list(self._rules_list_layout, rules)
        self._populate_list(self._entries_list_layout, entries)

    def _populate_list(self, layout, items):
        while layout.count() > 1:
            w = layout.takeAt(0).widget()
            if w:
                w.deleteLater()
        for item in items:
            cat = item.get("category", "")
            title = item.get("title", "")
            lbl = _item_label(f"[{cat}] {title}", "#c0c0cc")
            layout.insertWidget(layout.count() - 1, lbl)

    def _toggle_rules(self):
        self._rules_expanded = not self._rules_expanded
        self._rules_list.setVisible(self._rules_expanded)
        arrow = "▼" if self._rules_expanded else "▶"
        from edini.ui.knowledge_store import rules_count
        self._rules_btn.setText(f"{arrow} Iron Rules ({rules_count()})")

    def _toggle_entries(self):
        self._entries_expanded = not self._entries_expanded
        self._entries_list.setVisible(self._entries_expanded)
        arrow = "▼" if self._entries_expanded else "▶"
        from edini.ui.knowledge_store import entries_count
        self._entries_btn.setText(f"{arrow} Entries ({entries_count()})")

    # ── Reflecting mode ──

    def show_reflection_status(self, text: str):
        self._reflect_status.setText(text)
        self._reflect_area.setVisible(True)
        self._accept_all_btn.setVisible(False)
        self._reject_all_btn.setVisible(False)
        self._clear_reflect_items()

    def show_reflection_results(self, items: list):
        self._pending_items = items
        self._reflect_status.setText(
            f"🧠 知识提取 — {len(items)} 条发现" if items else "✅ 无新知识")

        if not items:
            QtCore.QTimer.singleShot(2000, lambda: self._reflect_area.setVisible(False))
            return

        self._clear_reflect_items()
        for i, item in enumerate(items):
            card = self._make_result_card(item, i)
            self._reflect_items_layout.insertWidget(
                self._reflect_items_layout.count() - 1, card)

        self._accept_all_btn.setVisible(True)
        self._reject_all_btn.setVisible(True)

    def _clear_reflect_items(self):
        while self._reflect_items_layout.count() > 1:
            w = self._reflect_items_layout.takeAt(0).widget()
            if w:
                w.deleteLater()
        self._pending_items = []

    def _make_result_card(self, item: dict, index: int) -> QtWidgets.QWidget:
        card = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(card)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4)

        action = item.get("_action", "new")
        if action == "merge":
            badge_text = "🔄"
            tooltip = f"合并到: {item.get('_merge_target', {}).get('title', '?')}"
        else:
            badge_text = "🆕"
            tooltip = "新条目"

        badge = QtWidgets.QLabel(badge_text)
        badge.setToolTip(tooltip)
        badge.setFixedWidth(18)
        badge.setStyleSheet(f"font-size: {fs(11)}; border: none;")
        layout.addWidget(badge)

        cat = item.get("category", "")
        cat_lbl = QtWidgets.QLabel(cat)
        cat_lbl.setStyleSheet(f"color:#71717a;font-size:{fs(10)};border:none;")
        cat_lbl.setFixedWidth(32)
        layout.addWidget(cat_lbl)

        content_w = QtWidgets.QWidget()
        cl = QtWidgets.QVBoxLayout(content_w)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)
        title_lbl = QtWidgets.QLabel(item.get("title", ""))
        title_lbl.setStyleSheet(
            f"color:#e5e5eb;font-size:{fs(10)};font-weight:600;border:none;")
        title_lbl.setWordWrap(True)
        cl.addWidget(title_lbl)
        desc = item.get("content", "")[:80]
        desc_lbl = QtWidgets.QLabel(desc)
        desc_lbl.setStyleSheet(f"color:#71717a;font-size:{fs(9)};border:none;")
        desc_lbl.setWordWrap(True)
        cl.addWidget(desc_lbl)
        layout.addWidget(content_w, 1)

        accept_btn = _action_btn("✓", "#16a34a")
        accept_btn.setFixedSize(22, 22)
        accept_btn.clicked.connect(
            lambda checked=False, idx=index: self._on_accept_one(idx))
        layout.addWidget(accept_btn)

        reject_btn = _action_btn("✕", "#555")
        reject_btn.setFixedSize(22, 22)
        reject_btn.clicked.connect(
            lambda checked=False, idx=index: self._on_reject_one(idx))
        layout.addWidget(reject_btn)

        return card

    def _on_accept_one(self, index: int):
        if 0 <= index < len(self._pending_items):
            item = self._pending_items.pop(index)
            self.items_accepted.emit([item])
            self.show_reflection_results(self._pending_items)

    def _on_reject_one(self, index: int):
        if 0 <= index < len(self._pending_items):
            self._pending_items.pop(index)
            self.show_reflection_results(self._pending_items)

    def _on_accept_all(self):
        items = list(self._pending_items)
        self.items_accepted.emit(items)
        self._clear_reflect_items()
        self._reflect_area.setVisible(False)

    def _on_reject_all(self):
        self._clear_reflect_items()
        self._reflect_area.setVisible(False)
