"""Sessions panel — session list with metadata, rename, delete."""
from PySide6 import QtCore, QtWidgets
from edini.ui.session_store import (
    list_sessions, delete_session, rename_session, get_session_stats,
)


class HistoryPanel(QtWidgets.QWidget):
    session_selected = QtCore.Signal(str)
    session_deleted = QtCore.Signal(str)
    new_session_requested = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        title = QtWidgets.QLabel("Sessions")
        title.setStyleSheet("font-size:12pt;font-weight:700;color:#e5e5eb;")
        layout.addWidget(title)

        self.new_btn = QtWidgets.QPushButton("+ New Session")
        self.new_btn.setObjectName("PrimaryButton")
        layout.addWidget(self.new_btn)

        self.session_list = QtWidgets.QListWidget(self)
        self.session_list.setStyleSheet("""
            QListWidget {
                background-color: #0e0e15;
                border: 1px solid #1a1a24;
                border-radius: 4px;
                color: #a1a1aa;
                font-size: 12pt;
            }
            QListWidget::item {
                padding: 8px 12px;
                border-bottom: 1px solid #1a1a24;
            }
            QListWidget::item:selected {
                background-color: rgba(6, 182, 212, 0.12);
                color: #67e8f9;
                border-left: 2px solid #06b6d4;
            }
            QListWidget::item:hover {
                background-color: #141420;
            }
        """)
        layout.addWidget(self.session_list, 1)

        self._bind()

    def _bind(self):
        self.new_btn.clicked.connect(self._on_new)
        self.session_list.itemClicked.connect(self._on_select)
        self.session_list.itemDoubleClicked.connect(self._on_double_click)
        self.session_list.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.session_list.customContextMenuRequested.connect(self._on_context_menu)

    def _on_new(self):
        self.new_session_requested.emit()

    def _on_select(self, item):
        if item and item.data(QtCore.Qt.UserRole):
            self.session_selected.emit(item.data(QtCore.Qt.UserRole))

    def _on_double_click(self, item):
        sid = item.data(QtCore.Qt.UserRole)
        if sid:
            self._rename_dialog(sid)

    def _on_context_menu(self, pos):
        item = self.session_list.itemAt(pos)
        if not item:
            return
        sid = item.data(QtCore.Qt.UserRole)
        if not sid:
            return
        menu = QtWidgets.QMenu(self)
        rename_action = menu.addAction("Rename")
        delete_action = menu.addAction("Delete")
        action = menu.exec(self.session_list.mapToGlobal(pos))
        if action == delete_action:
            delete_session(sid)
            self.session_deleted.emit(sid)
        elif action == rename_action:
            self._rename_dialog(sid)

    def _rename_dialog(self, sid: str):
        from edini.ui.session_store import load_session
        record = load_session(sid)
        if record is None:
            return
        current = record.get("title", "")
        text, ok = QtWidgets.QInputDialog.getText(
            self, "Rename Session", "Name:", text=current
        )
        if ok and text.strip():
            rename_session(sid, text.strip())
            self.load_sessions()

    def add_session(self, sid: str, title: str, created: str,
                     updated: str, rounds: int, compressed: bool):
        """Add a session item with full metadata display."""
        item = QtWidgets.QListWidgetItem()
        item.setData(QtCore.Qt.UserRole, sid)
        item.setSizeHint(QtCore.QSize(0, 56))

        widget = QtWidgets.QWidget()
        w_layout = QtWidgets.QVBoxLayout(widget)
        w_layout.setContentsMargins(0, 2, 0, 2)
        w_layout.setSpacing(2)

        title_label = QtWidgets.QLabel(title)
        title_label.setStyleSheet("font-size:12pt;color:#e5e5eb;font-weight:600;border:none;")
        w_layout.addWidget(title_label)

        created_short = created[:10] if created else "?"
        updated_short = updated[:10] if updated else "?"
        meta = f"Created: {created_short}  ·  Updated: {updated_short}  ·  {rounds} rounds"
        if compressed:
            meta += "  ·  compressed"
        meta_label = QtWidgets.QLabel(meta)
        meta_label.setStyleSheet("font-size:11pt;color:#71717a;border:none;")
        w_layout.addWidget(meta_label)

        self.session_list.addItem(item)
        self.session_list.setItemWidget(item, widget)

    def remove_session(self, sid: str):
        for i in range(self.session_list.count()):
            item = self.session_list.item(i)
            if item and item.data(QtCore.Qt.UserRole) == sid:
                self.session_list.takeItem(i)
                break

    def load_sessions(self):
        self.session_list.clear()
        sessions = list_sessions()
        for s in sessions:
            sid = s["session_id"]
            stats = get_session_stats(sid)
            self.add_session(
                sid,
                s.get("title", "New Session"),
                stats.get("created_at", ""),
                stats.get("updated_at", ""),
                stats.get("rounds", 0),
                stats.get("compressed", False),
            )
