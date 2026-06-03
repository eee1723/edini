"""Window singleton management for Edini within Houdini."""
import importlib

try:
    hou = importlib.import_module("hou")
except Exception:
    hou = None

_main_window = None
_settings_dialog = None


def _main_parent():
    if hou is None:
        return None
    try:
        return hou.qt.mainWindow()
    except Exception:
        return None


def open_chat_window(toggle=False):
    global _main_window
    if _main_window is None:
        from edini.ui.main_window import EdiniMainWindow
        _main_window = EdiniMainWindow(_main_parent())

    if toggle and _main_window.isVisible() and _main_window.isActiveWindow():
        _main_window.showMinimized()
        return _main_window

    _main_window.show()
    _main_window.raise_()
    _main_window.activateWindow()
    return _main_window


def open_settings():
    global _settings_dialog
    if _settings_dialog is None:
        from edini.ui.settings_dialog import SettingsDialog
        _settings_dialog = SettingsDialog(_main_parent() if _main_window else None)
    _settings_dialog.show()
    _settings_dialog.raise_()
    _settings_dialog.activateWindow()
    return _settings_dialog
