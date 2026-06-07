"""Edini startup script — runs on Houdini launch to install global hotkey.

Houdini automatically executes 456.py from the scripts/ directory
of any loaded package.
"""
import os
import sys
import importlib

_INIT_ATTEMPT = 0
_INIT_MAX_ATTEMPTS = 12
_INIT_START_DELAY_MS = 10000
_INIT_RETRY_DELAY_MS = 2500


def _log(message):
    pass  # quiet mode


def _import_qt_modules():
    for prefix in ("PySide6", "PySide2"):
        try:
            qt_core = importlib.import_module(prefix + ".QtCore")
            qt_widgets = importlib.import_module(prefix + ".QtWidgets")
            return qt_core, qt_widgets
        except Exception:
            continue
    return None, None


def _ui_ready(qt_widgets):
    """Check if Houdini's QApplication and main window are ready."""
    try:
        app = qt_widgets.QApplication.instance()
    except Exception:
        app = None
    if app is None:
        return False

    try:
        active = app.activeWindow()
    except Exception:
        active = None
    if active is not None:
        return True

    try:
        hou_mod = importlib.import_module("hou")
        main_window = hou_mod.qt.mainWindow()
        if main_window is not None:
            return True
    except Exception:
        pass
    return False


def _delayed_init():
    """Import edini.ui and install the global hotkey filter."""
    try:
        ui_module = importlib.import_module("edini.ui.hotkey")
        install_event_filter = getattr(ui_module, "install_event_filter")
        if install_event_filter():
            _log("Global hotkey installed: Alt+Shift+E")
            return True
        else:
            _log("Failed to install hotkey filter (QApp not ready?)")
            return False
    except Exception as exc:
        _log("Failed to import edini.ui: %s" % exc)
        return False


def _attempt_init():
    global _INIT_ATTEMPT
    _INIT_ATTEMPT += 1

    qt_core, qt_widgets = _import_qt_modules()
    if qt_core is None or qt_widgets is None:
        _log("Qt modules unavailable, skip hotkey auto init")
        return

    if not _ui_ready(qt_widgets):
        if _INIT_ATTEMPT >= _INIT_MAX_ATTEMPTS:
            _log("Hotkey auto init aborted: UI not ready")
            return
        _log("UI not ready, retry hotkey auto init (%d/%d)" % (_INIT_ATTEMPT, _INIT_MAX_ATTEMPTS))
        qt_core.QTimer.singleShot(_INIT_RETRY_DELAY_MS, _attempt_init)
        return

    ok = _delayed_init()
    if ok:
        return

    if _INIT_ATTEMPT >= _INIT_MAX_ATTEMPTS:
        _log("Hotkey auto init failed after retries")
        return
    _log("Retry hotkey auto init (%d/%d)" % (_INIT_ATTEMPT, _INIT_MAX_ATTEMPTS))
    qt_core.QTimer.singleShot(_INIT_RETRY_DELAY_MS, _attempt_init)


def _schedule_init():
    qt_core, _ = _import_qt_modules()
    if qt_core is None:
        _log("Qt modules unavailable, cannot schedule hotkey auto init")
        return
    qt_core.QTimer.singleShot(_INIT_START_DELAY_MS, _attempt_init)


_schedule_init()
