"""Global hotkey event filter, modeled after EEEAi_Houdini's approach."""
from PySide6 import QtCore, QtGui, QtWidgets

_event_filter = None
_hotkey_enabled = True


class HotkeyFilter(QtCore.QObject):
    _HOTKEY = QtGui.QKeySequence("Alt+Shift+E")

    def eventFilter(self, obj, event):
        if not _hotkey_enabled:
            return False
        if event.type() != QtCore.QEvent.KeyPress:
            return False
        if event.isAutoRepeat():
            return False

        # Houdini may provide keyCombination(); fall back to modifiers|key
        try:
            matches = self._HOTKEY.matches(
                QtGui.QKeySequence(event.modifiers() | event.key())
            ) == QtGui.QKeySequence.ExactMatch
        except Exception:
            matches = False

        if matches:
            from edini.ui import open_chat_window
            open_chat_window(toggle=True)
            return True
        return False


def install_event_filter():
    global _event_filter
    if _event_filter is not None:
        return True
    app = QtWidgets.QApplication.instance()
    if app is None:
        return False
    _event_filter = HotkeyFilter()
    app.installEventFilter(_event_filter)
    return True
