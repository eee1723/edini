"""Sessions panel — session list with metadata, rename, delete.

Reads pi session files from ~/.pi/agent/sessions/.
"""
from PySide6 import QtCore, QtWidgets
from edini.ui.pi_sessions import (
    list_pi_sessions, delete_pi_session,
)


class HistoryPanel(QtWidgets.QWidget):
    # Emits pi session file path (not edini session id)
    session_selected = QtCore.Signal(str)
    session_deleted = QtCore.Signal(str)
    new_session_requested = QtCore.Signal()
    back_to_current_requested = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cwd = ""
        self._browsing = False
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

    def set_cwd(self, cwd: str):
        """Set the working directory for session discovery."""
        self._cwd = cwd

    def _bind(self):
        self.new_btn.clicked.connect(self._on_new)
        self.session_list.itemClicked.connect(self._on_select)
        self.session_list.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.session_list.customContextMenuRequested.connect(self._on_context_menu)

    def _on_new(self):
        if self._browsing:
            self.back_to_current_requested.emit()
        else:
            self.new_session_requested.emit()

    def _on_select(self, item):
        if item and item.data(QtCore.Qt.UserRole):
            self.session_selected.emit(item.data(QtCore.Qt.UserRole))

    def _on_context_menu(self, pos):
        item = self.session_list.itemAt(pos)
        if not item:
            return
        session_path = item.data(QtCore.Qt.UserRole)
        if not session_path:
            return
        menu = QtWidgets.QMenu(self)
        delete_action = menu.addAction("Delete")
        action = menu.exec(self.session_list.mapToGlobal(pos))
        if action == delete_action:
            if delete_pi_session(session_path):
                self.session_deleted.emit(session_path)

    def add_session(self, session_path: str, title: str, created: str,
                     updated: str, msg_count: int):
        """Add a session item with metadata."""
        item = QtWidgets.QListWidgetItem()
        item.setData(QtCore.Qt.UserRole, session_path)
        item.setSizeHint(QtCore.QSize(0, 60))

        widget = QtWidgets.QWidget()
        w_layout = QtWidgets.QVBoxLayout(widget)
        w_layout.setContentsMargins(0, 2, 0, 2)
        w_layout.setSpacing(1)

        title_label = QtWidgets.QLabel(title)
        title_label.setStyleSheet("font-size:12pt;color:#e5e5eb;font-weight:600;border:none;")
        w_layout.addWidget(title_label)

        created_short = _fmt_time(created)
        updated_short = _fmt_time(updated)
        meta = f"Created: {created_short}  ·  {msg_count} messages"
        meta_label = QtWidgets.QLabel(meta)
        meta_label.setStyleSheet("font-size:10pt;color:#71717a;border:none;")
        w_layout.addWidget(meta_label)

        updated_label = QtWidgets.QLabel(f"Updated: {updated_short}")
        updated_label.setStyleSheet("font-size:10pt;color:#52525b;border:none;")
        w_layout.addWidget(updated_label)

        self.session_list.addItem(item)
        self.session_list.setItemWidget(item, widget)

    def remove_session(self, session_path: str):
        for i in range(self.session_list.count()):
            item = self.session_list.item(i)
            if item and item.data(QtCore.Qt.UserRole) == session_path:
                self.session_list.takeItem(i)
                break

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


def _fmt_time(iso_str: str) -> str:
    """Format ISO datetime for display: '06-04 18:30'."""
    if not iso_str:
        return "?"
    try:
        dt = iso_str[:16]  # "2026-06-04T18:30"
        return dt.replace("T", " ")[5:]  # "06-04 18:30"
    except Exception:
        return iso_str[:16]
