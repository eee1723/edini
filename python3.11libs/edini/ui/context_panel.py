"""Context panel — card-based Pi Status (top) + Scene Info (bottom)."""
import importlib
from PySide6 import QtCore, QtWidgets
from edini.ui.theme import fs

try:
    hou = importlib.import_module("hou")
except Exception:
    hou = None


def _make_card(title: str, parent=None) -> tuple[QtWidgets.QFrame, QtWidgets.QVBoxLayout]:
    """Create a card-style frame with title header and separator."""
    card = QtWidgets.QFrame(parent)
    card.setStyleSheet("""
        QFrame {
            background: #0e0e15;
            border: 1px solid #2a2a3c;
            border-radius: 6px;
        }
    """)
    layout = QtWidgets.QVBoxLayout(card)
    layout.setContentsMargins(10, 8, 10, 8)
    layout.setSpacing(4)

    header = QtWidgets.QLabel(title)
    header.setStyleSheet(f"font-size:{fs(11)};font-weight:600;color:#71717a;border:none;")
    layout.addWidget(header)

    sep = QtWidgets.QFrame()
    sep.setFrameShape(QtWidgets.QFrame.HLine)
    sep.setStyleSheet("border:none;border-top:1px solid #2a2a3c;margin:2px 0;")
    layout.addWidget(sep)

    return card, layout


def _card_label(text: str) -> QtWidgets.QLabel:
    lbl = QtWidgets.QLabel(text)
    lbl.setStyleSheet(f"color:#a1a1aa;font-size:{fs(11)};border:none;")
    return lbl


def _card_value(text: str) -> QtWidgets.QLabel:
    lbl = QtWidgets.QLabel(text)
    lbl.setStyleSheet(f"color:#e5e5eb;font-size:{fs(11)};border:none;")
    return lbl


def _card_row(label: str, value_widget: QtWidgets.QWidget, parent=None) -> QtWidgets.QWidget:
    row = QtWidgets.QWidget(parent)
    row_layout = QtWidgets.QHBoxLayout(row)
    row_layout.setContentsMargins(0, 0, 0, 0)
    row_layout.setSpacing(8)
    lbl = QtWidgets.QLabel(label)
    lbl.setStyleSheet(f"color:#a1a1aa;font-size:{fs(11)};border:none;")
    lbl.setFixedWidth(50)
    row_layout.addWidget(lbl)
    row_layout.addWidget(value_widget, 1)
    return row


def _card_spacer(h: int = 4) -> QtWidgets.QWidget:
    w = QtWidgets.QWidget()
    w.setFixedHeight(h)
    w.setStyleSheet("background:transparent;border:none;")
    return w


class ContextPanel(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._last_ctx_pct = None

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # ── Card 1: Pi Status ──
        pi_card, pi_layout = _make_card("Pi Status", self)

        self.status_label = _card_value("● Connecting...")
        pi_layout.addWidget(self.status_label)

        self.provider_model_label = QtWidgets.QLabel("deepseek / deepseek-chat")
        self.provider_model_label.setStyleSheet(f"color:#71717a;font-size:{fs(11)};border:none;")
        pi_layout.addWidget(self.provider_model_label)

        pi_layout.addWidget(_card_spacer())

        self.token_in_label = _card_label("In: -")
        self.token_out_label = _card_label("Out: -")
        self.token_total_label = _card_label("Total: -")
        self.cost_label = _card_label("Cost: -")
        for lbl in [self.token_in_label, self.token_out_label, self.token_total_label, self.cost_label]:
            pi_layout.addWidget(lbl)

        pi_layout.addWidget(_card_spacer())

        pi_layout.addWidget(_card_spacer())

        self.tools_label = _card_label("Tools: -")
        pi_layout.addWidget(self.tools_label)

        self.round_time_label = _card_label("Round: —")
        pi_layout.addWidget(self.round_time_label)

        self.ctx_label = _card_label("Context: -")
        pi_layout.addWidget(self.ctx_label)

        self.ctx_progress = QtWidgets.QProgressBar()
        self.ctx_progress.setMinimum(0)
        self.ctx_progress.setMaximum(100)
        self.ctx_progress.setValue(0)
        self.ctx_progress.setTextVisible(True)
        self.ctx_progress.setFormat("0%")
        self.ctx_progress.setFixedHeight(14)
        pi_layout.addWidget(self.ctx_progress)

        layout.addWidget(pi_card)

        # ── Card 2: Scene ──
        scene_card, scene_layout = _make_card("Scene", self)

        self.hip_label = _card_label("HIP: -")
        self.path_label = _card_label("Path: -")
        self.selected_label = _card_label("Selected: -")
        self.node_count_label = _card_label("Nodes: -")
        for lbl in [self.hip_label, self.path_label, self.selected_label, self.node_count_label]:
            scene_layout.addWidget(lbl)

        self.refresh_btn = QtWidgets.QPushButton("Refresh")
        self.refresh_btn.setObjectName("GhostButton")
        self.refresh_btn.clicked.connect(self.refresh_scene_info)
        scene_layout.addWidget(self.refresh_btn)

        layout.addWidget(scene_card)

        # ── Card 3: Knowledge ──
        kn_card, kn_layout = _make_card("Knowledge", self)

        self.rules_count_label = _card_label("Rules: -")
        kn_layout.addWidget(self.rules_count_label)

        self.entries_count_label = _card_label("Entries: -")
        kn_layout.addWidget(self.entries_count_label)

        manage_btn = QtWidgets.QPushButton("管理")
        manage_btn.setObjectName("GhostButton")
        manage_btn.clicked.connect(self._open_knowledge_manager)
        kn_layout.addWidget(manage_btn)

        layout.addWidget(kn_card)
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
        self.provider_model_label.setText(f"{provider} / {model}")

    def set_usage(self, stats: dict):
        tokens = stats.get("tokens", {})
        cost = stats.get("cost", 0)
        ctx = stats.get("contextUsage")
        self.token_in_label.setText(f"In: {tokens.get('input', 0):,}")
        self.token_out_label.setText(f"Out: {tokens.get('output', 0):,}")
        self.token_total_label.setText(f"Total: {tokens.get('total', 0):,}")
        self.cost_label.setText(f"Cost: ${cost:.3f}" if cost else "Cost: -")
        if ctx:
            pct = ctx.get("percent", 0)
            self._last_ctx_pct = pct
            self.ctx_progress.setValue(int(pct))
            self.ctx_progress.setFormat(f"{pct}%")
            self.ctx_label.setText(f"Context: {pct}%")

    def set_tools_info(self, info: str):
        """Set tools info in Pi Status card (e.g., '16 tools, port 9876')."""
        self.tools_label.setText(f"Tools: {info}")

    def set_round_time(self, elapsed_sec: float):
        """Show the current round duration."""
        mins = int(elapsed_sec // 60)
        secs = int(elapsed_sec % 60)
        self.round_time_label.setText(f"Round: {mins}:{secs:02d}")

    def reset_round_time(self):
        """Clear the round time display."""
        self.round_time_label.setText("Round: —")

    def refresh_knowledge(self):
        """Update knowledge counts in the card."""
        from edini.ui.knowledge_store import rules_count, entries_count
        r = rules_count()
        e = entries_count()
        self.rules_count_label.setText(f"Rules: {r}" if r else "Rules: -")
        self.entries_count_label.setText(f"Entries: {e}" if e else "Entries: -")

    def _open_knowledge_manager(self):
        from edini.ui.knowledge_dialog import KnowledgeDialog
        dlg = KnowledgeDialog(self)
        dlg.exec()
        self.refresh_knowledge()

    def reset_stats(self):
        """Reset all stats labels to defaults (used on session create/switch)."""
        self.token_in_label.setText("In: -")
        self.token_out_label.setText("Out: -")
        self.token_total_label.setText("Total: -")
        self.cost_label.setText("Cost: -")
        self.ctx_label.setText("Context: -")
        self.ctx_progress.setValue(0)
        self.ctx_progress.setFormat("0%")
        self._last_ctx_pct = None
        self.reset_round_time()

    def set_stream_rate(self, rate: float):
        pass  # Removed for cleaner UI per spec

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
                self.selected_label.setText(
                    f"Selected: {n.name()} ({n.type().name()})"
                )
            else:
                self.selected_label.setText("Selected: -")
            root = hou.node("/")
            count = len(root.allSubChildren()) if root else 0
            self.node_count_label.setText(f"Nodes: {count}")
        except Exception:
            pass
