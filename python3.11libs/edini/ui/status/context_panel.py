"""ContextPanel — Pi Status card + Scene card + Knowledge Zone. Data-driven.

Migrated here from ``edini/ui/context_panel.py`` (Task 2.1). The Scene card
is now a standalone :class:`~edini.ui.status.scene_card.SceneCard` driven by a
dict, so the panel no longer depends on the global ``hou`` module — callers
gather the data and feed it via :meth:`ContextPanel.set_scene_info`.
"""
from PySide6 import QtCore, QtWidgets
from edini.ui.theme import fs
from edini.ui.status.scene_card import (
    SceneCard,
    _make_card,
    _card_label,
    _card_value,
    _card_spacer,
)


class ContextPanel(QtWidgets.QWidget):
    """Right-side status panel: Pi Status + Scene + Knowledge Zone.

    The panel is hou-free. The owner (e.g. ``EdiniMainWindow``) supplies scene
    data via :meth:`set_scene_info`. The in-card "Refresh" button emits
    :attr:`refresh_requested`; the owner connects to it and calls
    ``set_scene_info`` with freshly gathered data.
    """

    refresh_requested = QtCore.Signal()  # owner connects → calls set_scene_info

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

        # Model row: label + value
        model_header = QtWidgets.QLabel("Chat Model")
        model_header.setStyleSheet(f"color:#525298;font-size:{fs(10)};font-weight:600;border:none;")
        pi_layout.addWidget(model_header)

        self.provider_model_label = QtWidgets.QLabel("—")
        self.provider_model_label.setStyleSheet(f"color:#c0c0d0;font-size:{fs(11)};border:none;")
        pi_layout.addWidget(self.provider_model_label)

        # Vision model row
        vision_header = QtWidgets.QLabel("Vision Model")
        vision_header.setStyleSheet(f"color:#525298;font-size:{fs(10)};font-weight:600;border:none;")
        pi_layout.addWidget(vision_header)

        self.vision_model_label = QtWidgets.QLabel("⚠ Not configured")
        self.vision_model_label.setStyleSheet(
            f"color:#ef4444;font-size:{fs(11)};font-weight:600;border:none;"
            f"background:#1c0c0c;border-radius:3px;padding:2px 6px;"
        )
        pi_layout.addWidget(self.vision_model_label)

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

        # ── Card 2: Scene (now data-driven SceneCard) ──
        self._scene_card = SceneCard(self)

        # Keep a "Refresh" button so the user can re-pull scene data; it now
        # emits refresh_requested instead of querying hou directly.
        self.refresh_btn = QtWidgets.QPushButton("Refresh")
        self.refresh_btn.setObjectName("GhostButton")
        self.refresh_btn.clicked.connect(self.refresh_requested)
        # Place the button inside the scene card's layout (below the labels).
        self._scene_card._card.layout().addWidget(self.refresh_btn)

        layout.addWidget(self._scene_card)

        # Expose the scene labels at the panel level for any legacy callers
        # that read them directly (the old ContextPanel exposed them).
        self.hip_label = self._scene_card.hip_label
        self.path_label = self._scene_card.path_label
        self.selected_label = self._scene_card.selected_label
        self.node_count_label = self._scene_card.node_count_label

        # ── Card 3: Knowledge Zone ──
        from edini.ui.status.knowledge_zone import KnowledgeZone
        self.knowledge_zone = KnowledgeZone(self)
        layout.addWidget(self.knowledge_zone)
        layout.addStretch(1)

    # ── Scene (data-driven) ──
    def set_scene_info(self, info: dict) -> None:
        """Update the scene card from a dict (called by owner after gathering data)."""
        self._scene_card.set_scene_info(info)

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

    def set_vision_model(self, provider: str = "", model: str = ""):
        """Update vision model display. Empty = not configured (shows warning)."""
        if provider and model:
            self.vision_model_label.setText(f"✓ {provider} / {model}")
            self.vision_model_label.setStyleSheet(
                f"color:#16a34a;font-size:{fs(11)};border:none;"
                f"background:#0c1c0c;border-radius:3px;padding:2px 6px;"
            )
        else:
            self.vision_model_label.setText("⚠ Not configured")
            self.vision_model_label.setStyleSheet(
                f"color:#ef4444;font-size:{fs(11)};font-weight:600;border:none;"
                f"background:#1c0c0c;border-radius:3px;padding:2px 6px;"
            )

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
        """Refresh knowledge zone."""
        self.knowledge_zone.refresh()

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
