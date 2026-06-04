"""Knowledge management dialog — view, filter, delete knowledge entries."""
from PySide6 import QtCore, QtWidgets
from edini.ui.theme import fs
from edini.ui.knowledge_store import get_all, delete_entry, CATEGORIES, count


class KnowledgeDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("知识库管理")
        self.setMinimumSize(500, 400)
        self.setStyleSheet(f"""
            QDialog {{ background-color: #0c0c14; }}
            QLabel {{ color: #c8ccd4; font-size:{fs(12)}; background:transparent; }}
        """)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        # Header with stats
        header = QtWidgets.QHBoxLayout()
        self._stats_label = QtWidgets.QLabel()
        self._stats_label.setStyleSheet(f"color:#a1a1aa;font-size:{fs(11)};")
        header.addWidget(self._stats_label)
        header.addStretch()

        clear_btn = QtWidgets.QPushButton("清空全部")
        clear_btn.setStyleSheet(f"""
            QPushButton {{ color:#ef4444; border:1px solid #3a1a1a; border-radius:4px;
            padding:4px 10px; font-size:{fs(11)}; background:transparent; }}
            QPushButton:hover {{ background:rgba(239,68,68,0.08); }}
        """)
        clear_btn.clicked.connect(self._on_clear_all)
        header.addWidget(clear_btn)
        layout.addLayout(header)

        # Category filter
        filter_row = QtWidgets.QHBoxLayout()
        filter_row.addWidget(QtWidgets.QLabel("分类:"))
        self._filter_combo = QtWidgets.QComboBox()
        self._filter_combo.addItem("全部", "")
        for cat, icon in CATEGORIES.items():
            self._filter_combo.addItem(f"{icon} {cat}", cat)
        self._filter_combo.currentIndexChanged.connect(self._refresh)
        self._filter_combo.setStyleSheet(f"""
            QComboBox {{ background:#10101a; color:#c8ccd4; border:1px solid #1e1e2c;
            border-radius:4px; padding:4px 8px; font-size:{fs(11)}; }}
        """)
        filter_row.addWidget(self._filter_combo)
        filter_row.addStretch()
        layout.addLayout(filter_row)

        # Entry list
        self._list = QtWidgets.QListWidget()
        self._list.setStyleSheet(f"""
            QListWidget {{ background:#0e0e15; border:1px solid #1a1a24; border-radius:4px;
            color:#a1a1aa; font-size:{fs(11)}; }}
            QListWidget::item {{ padding:8px 10px; border-bottom:1px solid #1a1a24; }}
            QListWidget::item:hover {{ background:#141420; }}
        """)
        layout.addWidget(self._list, 1)

        # Close button
        close_btn = QtWidgets.QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        close_btn.setStyleSheet(f"""
            QPushButton {{ background:#1a1a24; color:#c8ccd4; border:none; border-radius:4px;
            padding:6px 20px; font-size:{fs(12)}; }}
            QPushButton:hover {{ background:#2a2a3c; }}
        """)
        layout.addWidget(close_btn, alignment=QtCore.Qt.AlignRight)

        # Context menu for delete
        self._list.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._on_context_menu)

        self._refresh()

    def _refresh(self):
        self._list.clear()
        filter_cat = self._filter_combo.currentData()
        entries = get_all()

        if filter_cat:
            entries = [e for e in entries if e.get("category") == filter_cat]

        self._stats_label.setText(f"共 {count()} 条知识")

        for e in entries:
            icon = CATEGORIES.get(e.get("category", ""), "📌")
            cat = e.get("category", "")
            title = e.get("title", "")
            content = e.get("content", "")
            created = e.get("created_at", "")[:10]

            text = f"[{icon} {cat}] {title}\n{content}\n{created}"
            item = QtWidgets.QListWidgetItem(text)
            item.setData(QtCore.Qt.UserRole, e.get("id", ""))
            item.setSizeHint(QtCore.QSize(0, 60))
            self._list.addItem(item)

    def _on_context_menu(self, pos):
        item = self._list.itemAt(pos)
        if not item:
            return
        entry_id = item.data(QtCore.Qt.UserRole)
        menu = QtWidgets.QMenu(self)
        delete_action = menu.addAction("删除")
        action = menu.exec(self._list.mapToGlobal(pos))
        if action == delete_action:
            delete_entry(entry_id)
            self._refresh()

    def _on_clear_all(self):
        from edini.ui.knowledge_store import clear_all
        reply = QtWidgets.QMessageBox.question(
            self, "确认", "确定要清空全部知识条目吗？",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        )
        if reply == QtWidgets.QMessageBox.Yes:
            clear_all()
            self._refresh()
