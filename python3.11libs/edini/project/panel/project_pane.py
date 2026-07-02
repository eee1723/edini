"""Project HDA Python Panel entry point.

Houdini's Python Panel system evaluates the .pypanel <script> whenever a pane
tab of this interface is created. The script must define (or import) a module-
level function ``onCreateInterface()`` that builds and returns the root QWidget.
See the official BookmarksEditor.pypanel shipped with Houdini for the canonical
pattern.

We keep the widget construction in project_widget.py and just expose the entry
function here.
"""
from __future__ import annotations


def onCreateInterface():
    """Build and return the Project HDA panel's root widget.

    Called by Houdini each time an "Edini Project" pane tab is created.
    """
    from edini.project.panel.project_widget import ProjectPanelWidget

    widget = ProjectPanelWidget()
    widget.refresh_project_list()
    return widget
