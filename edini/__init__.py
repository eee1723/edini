"""Edini - Houdini AI Assistant powered by Pi."""

__version__ = "0.1.0"


def createPanel():
    """Create and return the Edini panel widget for Houdini.

    Called from Houdini's Python panel registration system.
    """
    from edini.panel import EdiniPanel
    return EdiniPanel()
