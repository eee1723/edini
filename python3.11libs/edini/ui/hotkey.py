"""Global hotkey event filter for Alt+Shift+E smart launcher."""
import importlib
from PySide6 import QtCore, QtWidgets

try:
    hou = importlib.import_module("hou")
except Exception:
    hou = None

_filter_instance = None


def install_event_filter():
    global _filter_instance
    if _filter_instance is not None:
        return True
    if hou is None:
        return False
    try:
        app = QtWidgets.QApplication.instance()
    except Exception:
        return False
    _filter_instance = _HotkeyFilter()
    app.installEventFilter(_filter_instance)
    return True


class _HotkeyFilter(QtCore.QObject):
    def eventFilter(self, watched, event):
        if event.type() == QtCore.QEvent.KeyPress:
            key = event.key()
            mods = event.modifiers()
            if (
                key == QtCore.Qt.Key_E
                and mods & QtCore.Qt.AltModifier
                and mods & QtCore.Qt.ShiftModifier
            ):
                from edini.ui import open_chat_window
                open_chat_window(toggle=True)
                return True
        return False
