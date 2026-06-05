"""Knowledge management dialog — two-tab view for rules and entries."""

from PySide6 import QtCore, QtWidgets
from edini.ui.theme import fs


class _KnowledgeTab(QtWidgets.QWidget):
    """Common tab for rules or entries with list + CRUD controls."""

    def __init__(self, tab_type: str, parent=None):
        super().__init__(parent)
        self._type = tab_type  # "rules" or "entries"
        self._items: list[dict] = []

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Search bar
        search_row = QtWidgets.QHBoxLayout()
        self._search = QtWidgets.QLineEdit()
        self._search.setPlaceholderText("搜索标题或内容...")
        self._search.setStyleSheet(f"""
            QLineEdit {{
                background: #1a1a24;
                color: #e5e5eb;
                border: 1px solid #2a2a3c;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: {fs(11)};
            }}
        """)
        self._search.textChanged.connect(self._on_search)
        search_row.addWidget(self._search)

        self._category_filter = QtWidgets.QComboBox()
        self._category_filter.addItem("全部")
        for cat in ["避坑", "技巧", "工作流", "配置"]:
            self._category_filter.addItem(cat)
        self._category_filter.setStyleSheet(f"""
            QComboBox {{
                background: #1a1a24;
                color: #e5e5eb;
                border: 1px solid #2a2a3c;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: {fs(11)};
            }}
            QComboBox::drop-down {{ border: none; }}
        """)
        self._category_filter.currentTextChanged.connect(self._on_search)
        search_row.addWidget(self._category_filter)
        layout.addLayout(search_row)

        # List
        self._list = QtWidgets.QListWidget()
        self._list.setStyleSheet(f"""
            QListWidget {{
                background: #0e0e15;
                border: 1px solid #2a2a3c;
                border-radius: 4px;
                font-size: {fs(11)};
            }}
            QListWidget::item {{
                color: #e5e5eb;
                padding: 6px 8px;
                border-bottom: 1px solid #1a1a24;
            }}
            QListWidget::item:selected {{
                background: #1a3a5c;
            }}
            QListWidget::item:hover {{
                background: #141428;
            }}
        """)
        self._list.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self._list, 1)

        # Detail area
        self._detail = QtWidgets.QTextEdit()
        self._detail.setReadOnly(True)
        self._detail.setPlaceholderText("选择条目查看详情...")
        self._detail.setMaximumHeight(120)
        self._detail.setStyleSheet(f"""
            QTextEdit {{
                background: #0e0e15;
                color: #94a3b8;
                border: 1px solid #2a2a3c;
                border-radius: 4px;
                padding: 6px 8px;
                font-size: {fs(11)};
            }}
        """)
        layout.addWidget(self._detail)

        # Button row
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.setSpacing(6)

        self._add_btn = QtWidgets.QPushButton("＋ 添加")
        self._add_btn.setStyleSheet(_btn_style())
        self._add_btn.clicked.connect(self._on_add)
        btn_row.addWidget(self._add_btn)

        self._edit_btn = QtWidgets.QPushButton("✎ 编辑")
        self._edit_btn.setStyleSheet(_btn_style())
        self._edit_btn.clicked.connect(self._on_edit)
        self._edit_btn.setEnabled(False)
        btn_row.addWidget(self._edit_btn)

        self._toggle_btn = QtWidgets.QPushButton("")
        self._toggle_btn.setStyleSheet(_btn_style())
        self._toggle_btn.clicked.connect(self._on_toggle)
        self._toggle_btn.setVisible(self._type == "rules")
        btn_row.addWidget(self._toggle_btn)

        self._delete_btn = QtWidgets.QPushButton("✕ 删除")
        self._delete_btn.setStyleSheet(_btn_style("#B91C1C"))
        self._delete_btn.clicked.connect(self._on_delete)
        self._delete_btn.setEnabled(False)
        btn_row.addWidget(self._delete_btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)

    def load(self):
        if self._type == "rules":
            from edini.ui.knowledge_store import load_rules
            self._items = load_rules()
        else:
            from edini.ui.knowledge_store import load_entries
            self._items = load_entries()
        self._refresh_list()

    def _refresh_list(self):
        query = self._search.text().lower()
        cat = self._category_filter.currentText()
        self._list.clear()
        for item in self._items:
            title = item.get("title", "")
            content = item.get("content", "")
            category = item.get("category", "")
            if query and query not in title.lower() and query not in content.lower():
                continue
            if cat != "全部" and category != cat:
                continue

            text = f"[{category}] {title}"
            if self._type == "rules" and not item.get("enabled", True):
                text = f"⊘ {text}"
            list_item = QtWidgets.QListWidgetItem(text)
            list_item.setData(QtCore.Qt.UserRole, item["id"])
            self._list.addItem(list_item)

    def _on_search(self):
        self._refresh_list()

    def _on_selection_changed(self):
        selected = self._list.currentItem()
        has_selection = selected is not None
        self._edit_btn.setEnabled(has_selection)
        self._delete_btn.setEnabled(has_selection)
        if has_selection and self._type == "rules":
            item_id = selected.data(QtCore.Qt.UserRole)
            item = self._get_item(item_id)
            if item is not None:
                enabled = item.get("enabled", True)
                self._toggle_btn.setText("⊘ 禁用" if enabled else "✓ 启用")
                self._toggle_btn.setEnabled(True)

        if selected:
            item = self._get_item(selected.data(QtCore.Qt.UserRole))
            if item:
                detail = item.get("content", "")
                if item.get("tags"):
                    detail += f"\n\n标签: {', '.join(item['tags'])}"
                self._detail.setPlainText(detail)
        else:
            self._detail.clear()
            if self._type == "rules":
                self._toggle_btn.setEnabled(False)

    def _get_item(self, item_id: str) -> dict | None:
        for item in self._items:
            if item["id"] == item_id:
                return item
        return None

    def _get_selected_id(self) -> str | None:
        item = self._list.currentItem()
        return item.data(QtCore.Qt.UserRole) if item else None

    def _on_add(self):
        dlg = _ItemEditDialog(self._type, parent=self)
        if dlg.exec():
            if self._type == "rules":
                from edini.ui.knowledge_store import add_rule
                add_rule(
                    category=dlg.category(),
                    title=dlg.title(),
                    content=dlg.content(),
                    enabled=True,
                )
            else:
                from edini.ui.knowledge_store import add_entry
                add_entry(
                    category=dlg.category(),
                    title=dlg.title(),
                    content=dlg.content(),
                    tags=dlg.tags(),
                )
            self.load()

    def _on_edit(self):
        item_id = self._get_selected_id()
        if not item_id:
            return
        item = self._get_item(item_id)
        if not item:
            return
        dlg = _ItemEditDialog(self._type, item, parent=self)
        if dlg.exec():
            kwargs = {
                "category": dlg.category(),
                "title": dlg.title(),
                "content": dlg.content(),
            }
            if self._type == "entries":
                kwargs["tags"] = dlg.tags()
            if self._type == "rules":
                from edini.ui.knowledge_store import update_rule
                update_rule(item_id, **kwargs)
            else:
                from edini.ui.knowledge_store import update_entry
                update_entry(item_id, **kwargs)
            self.load()

    def _on_toggle(self):
        item_id = self._get_selected_id()
        if not item_id:
            return
        item = self._get_item(item_id)
        if not item:
            return
        from edini.ui.knowledge_store import update_rule
        update_rule(item_id, enabled=not item.get("enabled", True))
        self.load()

    def _on_delete(self):
        item_id = self._get_selected_id()
        if not item_id:
            return
        item = self._get_item(item_id)
        if not item:
            return
        reply = QtWidgets.QMessageBox.question(
            self, "确认删除",
            f"确定要删除「{item.get('title', '')}」吗？",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        )
        if reply == QtWidgets.QMessageBox.Yes:
            if self._type == "rules":
                from edini.ui.knowledge_store import delete_rule
                delete_rule(item_id)
            else:
                from edini.ui.knowledge_store import delete_entry
                delete_entry(item_id)
            self.load()


class _ItemEditDialog(QtWidgets.QDialog):
    """Add/edit dialog for a rule or entry."""

    def __init__(self, item_type: str, existing: dict | None = None, parent=None):
        super().__init__(parent)
        self._type = item_type
        self.setWindowTitle("添加知识" if item_type == "rules" else "添加条目")
        self.resize(420, 360)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(8)

        # Category
        layout.addWidget(QtWidgets.QLabel("分类"))
        self._category = QtWidgets.QComboBox()
        for cat in ["避坑", "技巧", "工作流", "配置"]:
            self._category.addItem(cat)
        if existing:
            idx = self._category.findText(existing.get("category", ""))
            if idx >= 0:
                self._category.setCurrentIndex(idx)
        layout.addWidget(self._category)

        # Title
        layout.addWidget(QtWidgets.QLabel("标题"))
        self._title = QtWidgets.QLineEdit()
        self._title.setPlaceholderText("简洁标题...")
        if existing:
            self._title.setText(existing.get("title", ""))
        layout.addWidget(self._title)

        # Content
        layout.addWidget(QtWidgets.QLabel("内容"))
        self._content = QtWidgets.QPlainTextEdit()
        self._content.setPlaceholderText("详细描述...")
        if existing:
            self._content.setPlainText(existing.get("content", ""))
        layout.addWidget(self._content, 1)

        # Tags (entries only)
        self._tags = QtWidgets.QLineEdit()
        self._tags.setPlaceholderText("用逗号分隔，如: pyro, smoke")
        if existing and existing.get("tags"):
            self._tags.setText(", ".join(existing["tags"]))
        if item_type == "entries":
            layout.addWidget(QtWidgets.QLabel("标签"))
            layout.addWidget(self._tags)
        else:
            self._tags.setVisible(False)

        # Buttons
        btn_row = QtWidgets.QHBoxLayout()
        save_btn = QtWidgets.QPushButton("保存")
        save_btn.setStyleSheet(_btn_style())
        save_btn.clicked.connect(self.accept)
        cancel_btn = QtWidgets.QPushButton("取消")
        cancel_btn.setStyleSheet(_btn_style("#555"))
        cancel_btn.clicked.connect(self.reject)
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

        self._apply_styles()

    def _apply_styles(self):
        s = f"""
            QDialog {{ background: #0e0e18; color: #e5e5eb; }}
            QLabel {{ color: #a1a1aa; font-size: {fs(11)}; }}
            QLineEdit, QPlainTextEdit, QComboBox {{
                background: #1a1a24;
                color: #e5e5eb;
                border: 1px solid #2a2a3c;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: {fs(11)};
            }}
            QComboBox::drop-down {{ border: none; }}
        """
        self.setStyleSheet(s)

    def category(self) -> str:
        return self._category.currentText()

    def title(self) -> str:
        return self._title.text().strip()

    def content(self) -> str:
        return self._content.toPlainText().strip()

    def tags(self) -> list[str]:
        raw = self._tags.text().strip()
        return [t.strip() for t in raw.split(",") if t.strip()] if raw else []


class KnowledgeDialog(QtWidgets.QDialog):
    """Main knowledge management dialog with tabs."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("知识管理")
        self.resize(600, 500)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        self._tabs = QtWidgets.QTabWidget()
        self._tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                background: #0e0e18;
                border: 1px solid #2a2a3c;
                border-radius: 4px;
            }}
            QTabBar::tab {{
                background: #1a1a24;
                color: #a1a1aa;
                padding: 6px 16px;
                font-size: {fs(11)};
                border: 1px solid #2a2a3c;
                border-bottom: none;
            }}
            QTabBar::tab:selected {{
                background: #0e0e18;
                color: #e5e5eb;
            }}
        """)

        self._rules_tab = _KnowledgeTab("rules")
        self._entries_tab = _KnowledgeTab("entries")
        self._tabs.addTab(self._rules_tab, "铁律 (Rules)")
        self._tabs.addTab(self._entries_tab, "知识库 (Entries)")

        layout.addWidget(self._tabs, 1)

        close_btn = QtWidgets.QPushButton("关闭")
        close_btn.setStyleSheet(_btn_style())
        close_btn.clicked.connect(self.accept)
        close_row = QtWidgets.QHBoxLayout()
        close_row.addStretch()
        close_row.addWidget(close_btn)
        layout.addLayout(close_row)

        self.setStyleSheet(f"QDialog {{ background: #0e0e18; color: #e5e5eb; }}")

    def showEvent(self, event):
        """Load data when dialog becomes visible."""
        super().showEvent(event)
        self._rules_tab.load()
        self._entries_tab.load()


# ── Shared button style ──

def _btn_style(color: str = "#1E40AF") -> str:
    return f"""
        QPushButton {{
            background: {color};
            color: #e5e5eb;
            border: none;
            border-radius: 4px;
            padding: 4px 12px;
            font-size: {fs(11)};
        }}
        QPushButton:hover {{ background: {_lighter(color, 0.15)}; }}
        QPushButton:pressed {{ background: {_darker(color, 0.15)}; }}
    """


def _lighter(h: str, a: float) -> str:
    h = _expand_hex(h)
    r, g, b = int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)
    return f"#{min(255, int(r + (255 - r) * a)):02x}{min(255, int(g + (255 - g) * a)):02x}{min(255, int(b + (255 - b) * a)):02x}"


def _darker(h: str, a: float) -> str:
    h = _expand_hex(h)
    r, g, b = int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)
    return f"#{max(0, int(r * (1 - a))):02x}{max(0, int(g * (1 - a))):02x}{max(0, int(b * (1 - a))):02x}"


def _expand_hex(h: str) -> str:
    if len(h) == 4:   # #RGB
        return f"#{h[1]}{h[1]}{h[2]}{h[2]}{h[3]}{h[3]}"
    if len(h) == 5:   # #RGBA
        return f"#{h[1]}{h[1]}{h[2]}{h[2]}{h[3]}{h[3]}{h[4]}{h[4]}"
    return h
