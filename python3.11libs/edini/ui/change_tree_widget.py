"""Change tree widget — shows node modifications made by Edini."""
from PySide6 import QtCore, QtWidgets


class ChangeTreeWidget(QtWidgets.QWidget):
    node_path_requested = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._label = QtWidgets.QLabel("Changes")
        self._label.setStyleSheet("font-size:11px;font-weight:600;color:#a1a1aa;")
        self._label.setVisible(False)
        layout.addWidget(self._label)

        self.change_tree = QtWidgets.QTreeWidget(self)
        self.change_tree.setHeaderHidden(True)
        self.change_tree.setVisible(False)
        self.change_tree.setMaximumHeight(180)
        layout.addWidget(self.change_tree)

        self.setVisible(False)

    def add_change(self, action: str, node_path: str, detail: str):
        self._label.setVisible(True)
        self.change_tree.setVisible(True)
        self.setVisible(True)
        item = QtWidgets.QTreeWidgetItem([f"{action}: {node_path}"])
        item.setToolTip(0, detail)
        self.change_tree.addTopLevelItem(item)

    def clear_changes(self):
        self.change_tree.clear()
        self._label.setVisible(False)
        self.change_tree.setVisible(False)
        self.setVisible(False)
