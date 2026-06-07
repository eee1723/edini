"""Global hotkey event filter, modeled after EEEAi_Houdini's approach."""
from PySide6 import QtCore, QtGui, QtWidgets

_event_filter = None
_hotkey_enabled = True
_hotkey_combo = "Alt+Shift+E"
_hotkey_value = 0


def _combined_value(value):
    """Convert QKeyCombination (or int) to a plain int for comparison."""
    if hasattr(value, "toCombined"):
        try:
            return int(value.toCombined())
        except Exception:
            pass
    try:
        return int(value)
    except Exception:
        return 0


class HotkeyFilter(QtCore.QObject):
    def eventFilter(self, obj, event):
        if not _hotkey_enabled:
            return False
        if event.type() != QtCore.QEvent.KeyPress:
            return False
        if event.isAutoRepeat():
            return False

        event_value = 0
        # Houdini provides keyCombination() which encodes modifiers+key correctly
        if hasattr(event, "keyCombination"):
            try:
                event_value = _combined_value(event.keyCombination())
            except Exception:
                event_value = 0

        if event_value == 0:
            try:
                mods_value = int(event.modifiers())
            except Exception:
                mods_value = _combined_value(event.modifiers())
            event_value = mods_value | int(event.key())

        if event_value == _hotkey_value:
            from edini.ui import open_chat_window
            open_chat_window(toggle=True)
            return True
        return False


def parse_hotkey_combo(combo_text):
    """Parse a hotkey string (e.g. 'Alt+Shift+E') into its int value and normalized form."""
    text = str(combo_text or "").strip()
    if not text:
        raise ValueError("hotkey cannot be empty")

    sequence = QtGui.QKeySequence(text)
    if sequence.count() <= 0:
        raise ValueError("invalid hotkey sequence")

    value = _combined_value(sequence[0])
    if value == 0:
        raise ValueError("invalid hotkey sequence")

    normalized = sequence.toString(QtGui.QKeySequence.PortableText)
    if not normalized:
        normalized = text
    return value, normalized


def _apply_hotkey_config(enabled, combo):
    global _hotkey_enabled, _hotkey_combo, _hotkey_value
    value, normalized = parse_hotkey_combo(combo)
    _hotkey_enabled = bool(enabled)
    _hotkey_combo = normalized
    _hotkey_value = value


def install_event_filter():
    global _event_filter
    if _event_filter is not None:
        return True

    try:
        _apply_hotkey_config(True, "Alt+Shift+E")
    except Exception:
        return False

    if not _hotkey_enabled:
        return False

    app = QtWidgets.QApplication.instance()
    if app is None:
        return False

    _event_filter = HotkeyFilter()
    app.installEventFilter(_event_filter)
    return True


def uninstall_event_filter():
    global _event_filter
    if _event_filter is None:
        return
    app = QtWidgets.QApplication.instance()
    if app is not None:
        app.removeEventFilter(_event_filter)
    _event_filter = None
