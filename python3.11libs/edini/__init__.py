"""Edini - Houdini AI Assistant powered by Pi."""

__version__ = "0.2.0"


def createPanel():
    """Create and return the Edini main window for Houdini.

    Forwards to edini.ui.main_window.EdinMainWindow.
    """
    from edini.ui.main_window import EdiniMainWindow
    return EdiniMainWindow()
