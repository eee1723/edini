"""Styled checkbox widget matching the dark theme."""
from PySide6 import QtCore, QtWidgets


class StyledCheckBox(QtWidgets.QCheckBox):
    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setStyleSheet("""
            QCheckBox {
                color: #a1a1aa;
                font-size: 11px;
                spacing: 4px;
            }
            QCheckBox::indicator {
                width: 14px;
                height: 14px;
                border: 1px solid #3d3d55;
                border-radius: 3px;
                background: #1a1a24;
            }
            QCheckBox::indicator:checked {
                background: #06b6d4;
                border-color: #06b6d4;
            }
        """)
