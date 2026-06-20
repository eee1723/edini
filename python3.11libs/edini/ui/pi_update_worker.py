"""Background worker that updates the vendored Pi version.

Runs on a QThread so the npm-tarball install (which can take a few minutes
downloading 100+ packages) never blocks the Houdini UI. Streams progress as
(pct, stage) signals and emits finished(success, message) on completion.

The caller is responsible for stopping the live Pi subprocess BEFORE starting
this worker (Pi locks files under node_modules on Windows) and for restarting
it AFTER finished() fires.
"""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal


class PiUpdateWorker(QThread):
    """Background thread that runs config.update_pi()."""

    # (pct 0..100, human-readable stage text)
    progress = Signal(float, str)
    # (success, message) — always emitted exactly once at the end
    finished_result = Signal(bool, str)

    def __init__(self, version: str = "latest", parent=None):
        super().__init__(parent)
        self._version = version

    def run(self) -> None:
        try:
            from edini import config

            def cb(pct: float, stage: str) -> None:
                self.progress.emit(pct, stage)

            self.progress.emit(0.0, "Starting update…")
            ok, msg = config.update_pi(self._version, progress_cb=cb)
            self.finished_result.emit(ok, msg)
        except Exception as e:  # pragma: no cover — defensive
            self.finished_result.emit(False, f"Update failed: {e}")
