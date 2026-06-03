"""Edini - Houdini AI Assistant powered by Pi."""
__version__ = "0.2.0"

def create_panel():
    from edini.ui.main_window import EdiniMainWindow
    return EdiniMainWindow()
