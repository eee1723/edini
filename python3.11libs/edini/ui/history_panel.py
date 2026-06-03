"""History panel — session list with create/select/delete."""
import uuid
from PySide6 import QtCore, QtWidgets
from edini.ui.session_store import list_sessions, delete_session


class HistoryPanel(QtWidgets.QWidget):
    session_selected = QtCore.Signal(str)
    session_deleted = QtCore.Signal(str)
    new_session_requested = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        title = QtWidgets.QLabel("History")
        title.setStyleSheet("font-size:12px;font-weight:700;color:#e5e5eb;")
        layout.addWidget(title)

        self.new_btn = QtWidgets.QPushButton("+ New Session")
        self.new_btn.setObjectName("PrimaryButton")
        layout.addWidget(self.new_btn)

        self.session_list = QtWidgets.QListWidget(self)
        self.session_list.setStyleSheet("""
            QListWidget {
                background-color: #0e0e15;
                border: none;
                color: #a1a1aa;
                font-size: 12px;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #1a1a24;
            }
            QListWidget::item:selected {
                background-color: rgba(6, 182, 212, 0.15);
                color: #67e8f9;
            }
            QListWidget::item:hover {
                background-color: #1a1a24;
            }
        """)
        layout.addWidget(self.session_list, 1)

        self._bind()

    def _bind(self):
        self.new_btn.clicked.connect(self._on_new)
        self.session_list.itemClicked.connect(self._on_select)
        self.session_list.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.session_list.customContextMenuRequested.connect(self._on_context_menu)

    def _on_new(self):
        self.new_session_requested.emit()

    def _on_select(self, item):
        if item and item.data(QtCore.Qt.UserRole):
            self.session_selected.emit(item.data(QtCore.Qt.UserRole))

    def _on_context_menu(self, pos):
        item = self.session_list.itemAt(pos)
        if not item:
            return
        sid = item.data(QtCore.Qt.UserRole)
        if not sid:
            return
        menu = QtWidgets.QMenu(self)
        delete_action = menu.addAction("删除")
        action = menu.exec(self.session_list.mapToGlobal(pos))
        if action == delete_action:
            delete_session(sid)
            self.session_deleted.emit(sid)

    def add_session(self, sid: str, title: str):
        item = QtWidgets.QListWidgetItem(title)
        item.setData(QtCore.Qt.UserRole, sid)
        self.session_list.insertItem(0, item)

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
            self.add_session(s["session_id"], s.get("title", "New Session"))
