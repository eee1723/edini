"""PythonPanelInterface for the Project HDA panel.

Houdini's Python Panel system instantiates this and calls createInterface()
to get the widget shown in the pane tab.
"""
from __future__ import annotations

import hou
from PySide2 import QtWidgets

from edini.project.panel.project_widget import ProjectPanelWidget


class ProjectPanelInterface(hou.pypanel.PythonPanelInterface):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._widget: ProjectPanelWidget | None = None

    def createInterface(self) -> QtWidgets.QWidget:
        self._widget = ProjectPanelWidget(self.parent())
        self._widget.refresh_project_list()
        return self._widget
