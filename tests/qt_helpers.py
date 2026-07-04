"""Qt test helpers — QApplication singleton + signal spy.

The project has no pytest-qt. Tests that construct PySide6 widgets need a
QApplication; this module creates one on import (idempotent via instance()).

Usage:
    from tests.qt_helpers import qapp, SignalSpy
    spy = SignalSpy(some_object.some_signal)
    # ... trigger ...
    assert spy.calls == ["expected"]
"""
import sys
from PySide6 import QtCore, QtWidgets

_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)


def qapp() -> QtWidgets.QApplication:
    """Return the shared QApplication (created once on import)."""
    return _app


class SignalSpy:
    """Collect emissions of a Qt signal into a list.

    Connects to a SignalInstance and records each emission. For single-arg
    signals, records the arg; for multi-arg, records the args tuple.
    """
    def __init__(self, signal: QtCore.SignalInstance):
        self.calls: list = []
        signal.connect(self._on)

    def _on(self, *args):
        self.calls.append(args[0] if len(args) == 1 else args)

    def __len__(self):
        return len(self.calls)
