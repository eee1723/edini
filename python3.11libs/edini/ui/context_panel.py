"""Context panel — Pi status (top) + Scene info (bottom)."""
import importlib
from PySide6 import QtCore, QtWidgets

try:
    hou = importlib.import_module("hou")
except Exception:
    hou = None


class ContextPanel(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)

        # ── Pi Status ──
        pi_title = QtWidgets.QLabel("Pi Status")
        pi_title.setStyleSheet("font-size:11px;font-weight:600;color:#71717a;")
        layout.addWidget(pi_title)

        self.panel = QtWidgets.QWidget(self)
        pi_layout = QtWidgets.QVBoxLayout(self.panel)
        pi_layout.setContentsMargins(0, 0, 0, 0)
        pi_layout.setSpacing(4)

        self.status_label = QtWidgets.QLabel("● Connecting...")
        self.status_label.setStyleSheet("color:#a1a1aa;font-size:12px;")
        pi_layout.addWidget(self.status_label)

        self.provider_model_label = QtWidgets.QLabel("Model: -")
        self.provider_model_label.setStyleSheet("color:#71717a;font-size:11px;")
        pi_layout.addWidget(self.provider_model_label)

        pi_layout.addWidget(_section_divider())

        self.token_in_label = QtWidgets.QLabel("Input: -")
        self.token_out_label = QtWidgets.QLabel("Output: -")
        self.token_total_label = QtWidgets.QLabel("Total: -")
        self.cost_label = QtWidgets.QLabel("Cost: -")
        for lbl in [self.token_in_label, self.token_out_label, self.token_total_label, self.cost_label]:
            lbl.setStyleSheet("color:#71717a;font-size:11px;")
            pi_layout.addWidget(lbl)

        pi_layout.addWidget(_section_divider())

        self.ctx_label = QtWidgets.QLabel("Context: -")
        self.ctx_label.setStyleSheet("color:#71717a;font-size:11px;")
        pi_layout.addWidget(self.ctx_label)

        self.ctx_progress = QtWidgets.QProgressBar(self)
        self.ctx_progress.setMinimum(0)
        self.ctx_progress.setMaximum(100)
        self.ctx_progress.setValue(0)
        self.ctx_progress.setTextVisible(True)
        self.ctx_progress.setFormat("0%")
        self.ctx_progress.setFixedHeight(12)
        pi_layout.addWidget(self.ctx_progress)

        self.stream_rate_label = QtWidgets.QLabel("Stream Rate: -")
        self.stream_rate_label.setStyleSheet("color:#71717a;font-size:11px;")
        pi_layout.addWidget(self.stream_rate_label)

        layout.addWidget(self.panel)

        # ── Scene Info ──
        layout.addWidget(_section_divider())

        scene_title = QtWidgets.QLabel("Scene Info")
        scene_title.setStyleSheet("font-size:11px;font-weight:600;color:#71717a;")
        layout.addWidget(scene_title)

        self.scene_panel = QtWidgets.QWidget(self)
        scene_layout = QtWidgets.QVBoxLayout(self.scene_panel)
        scene_layout.setContentsMargins(0, 0, 0, 0)
        scene_layout.setSpacing(4)

        self.hip_label = QtWidgets.QLabel("HIP: -")
        self.path_label = QtWidgets.QLabel("Path: -")
        self.selected_label = QtWidgets.QLabel("Selected: -")
        self.node_count_label = QtWidgets.QLabel("Nodes: -")
        for lbl in [self.hip_label, self.path_label, self.selected_label, self.node_count_label]:
            lbl.setStyleSheet("color:#71717a;font-size:11px;")
            scene_layout.addWidget(lbl)

        self.refresh_btn = QtWidgets.QPushButton("⟳ Refresh")
        self.refresh_btn.setObjectName("GhostButton")
        self.refresh_btn.clicked.connect(self.refresh_scene_info)
        scene_layout.addWidget(self.refresh_btn)

        layout.addWidget(self.scene_panel)
        layout.addStretch(1)

    def set_pi_status(self, status: str):
        colors = {
            "connected": "#16a34a",
            "connecting": "#d97706",
            "disconnected": "#ef4444",
            "error": "#ef4444",
        }
        color = colors.get(status, "#71717a")
        self.status_label.setText(f"<span style='color:{color};'>●</span> {status.title()}")

    def set_provider_model(self, provider: str, model: str):
        self.provider_model_label.setText(f"Model: {provider}/{model}")

    def set_usage(self, stats: dict):
        tokens = stats.get("tokens", {})
        cost = stats.get("cost", 0)
        ctx = stats.get("contextUsage")
        self.token_in_label.setText(f"Input: {tokens.get('input', 0):,}")
        self.token_out_label.setText(f"Output: {tokens.get('output', 0):,}")
        self.token_total_label.setText(f"Total: {tokens.get('total', 0):,}")
        self.cost_label.setText(f"Cost: ${cost:.4f}" if cost else "Cost: -")
        if ctx:
            pct = ctx.get("percent", 0)
            self.ctx_progress.setValue(int(pct))
            self.ctx_progress.setFormat(f"{pct}%")
            self.ctx_label.setText(f"Context: {pct}% used")

    def set_stream_rate(self, rate: float):
        self.stream_rate_label.setText(f"Stream Rate: {rate:.0f} tok/s")

    def refresh_scene_info(self):
        if hou is None:
            return
        try:
            hip = hou.hipFile.name() or "Untitled"
            self.hip_label.setText(f"HIP: {hip}")
            pwd = hou.pwd()
            self.path_label.setText(f"Path: {pwd.path()}" if pwd else "Path: -")
            sel = hou.selectedNodes()
            if sel:
                n = sel[0]
                children = len(n.allSubChildren())
                self.selected_label.setText(
                    f"Selected: {n.path()} ({n.type().name()}, {children} children)"
                )
            else:
                self.selected_label.setText("Selected: -")
            root = hou.node("/")
            count = len(root.allSubChildren()) if root else 0
            self.node_count_label.setText(f"Nodes: {count}")
        except Exception:
            pass


def _section_divider():
    div = QtWidgets.QFrame()
    div.setFrameShape(QtWidgets.QFrame.HLine)
    div.setStyleSheet("border:none;border-top:1px solid #2a2a3c;margin:4px 0;")
    return div
