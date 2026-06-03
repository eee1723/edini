"""Plan-Execute progress widget."""
from PySide6 import QtCore, QtWidgets


class PlanProgressWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._label = QtWidgets.QLabel("Plan Progress")
        self._label.setStyleSheet("font-size:11px;font-weight:600;color:#a1a1aa;")
        self._label.setVisible(False)
        layout.addWidget(self._label)

        self._progress = QtWidgets.QProgressBar(self)
        self._progress.setMinimum(0)
        self._progress.setMaximum(1)
        self._progress.setValue(0)
        self._progress.setTextVisible(True)
        self._progress.setFormat("")
        self._progress.setFixedHeight(14)
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        self.setVisible(False)

    def begin_plan(self, plan_id: str, strategy: str = ""):
        self._progress.setMaximum(1)
        self._progress.setValue(0)
        self._progress.setFormat("计划已创建")
        self._progress.setVisible(True)
        self._label.setVisible(True)
        self.setVisible(True)

    def set_run_progress(self, executed: int, estimated: int, stage: str = ""):
        if estimated > 0:
            self._progress.setMaximum(estimated)
            self._progress.setValue(executed)
            self._progress.setFormat(f"{executed} / ~{estimated}")

    def reset_plan_state(self):
        self._progress.setVisible(False)
        self._label.setVisible(False)
        self.setVisible(False)
