"""SceneCard — data-driven scene info card. NO hou.pwd() dependency.

Moved out of ContextPanel (Task 2.1) so the HDA window can supply its own
node-level scene data via a dict, instead of relying on the global
``hou.pwd()`` that the main window's panel used to call directly.
"""
from PySide6 import QtWidgets
from edini.ui.theme import fs


def _make_card(title: str, parent=None) -> tuple[QtWidgets.QFrame, QtWidgets.QVBoxLayout]:
    """Create a card-style frame with title header and separator.

    Shared with ContextPanel (moved verbatim from the old context_panel module).
    """
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
    header.setStyleSheet(f"font-size:{fs(12)};font-weight:600;color:#71717a;border:none;")
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
    lbl.setFixedWidth(56)
    row_layout.addWidget(lbl)
    row_layout.addWidget(value_widget, 1)
    return row


def _card_spacer(h: int = 4) -> QtWidgets.QWidget:
    w = QtWidgets.QWidget()
    w.setFixedHeight(h)
    w.setStyleSheet("background:transparent;border:none;")
    return w


class SceneCard(QtWidgets.QWidget):
    """Scene info card driven by a dict. No ``hou`` import.

    :meth:`set_scene_info` updates the four labels from a scene-info dict of
    the shape ``{hip, path, selected, nodes, ...}``. ``None`` values display
    ``'—'``. Unknown keys are ignored (forward-compat for future fields such
    as graph data).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._card, layout = _make_card("Scene", self)

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._card)

        self.hip_label = _card_label("HIP: —")
        self.path_label = _card_label("Path: —")
        self.selected_label = _card_label("Selected: —")
        self.node_count_label = _card_label("Nodes: —")
        for lbl in [self.hip_label, self.path_label, self.selected_label, self.node_count_label]:
            layout.addWidget(lbl)

    def set_scene_info(self, info: dict) -> None:
        """Update labels from a scene-info dict. ``None`` → ``'—'``."""
        self.hip_label.setText(f"HIP: {info.get('hip') or '—'}")
        self.path_label.setText(f"Path: {info.get('path') or '—'}")
        self.selected_label.setText(f"Selected: {info.get('selected') or '—'}")
        self.node_count_label.setText(f"Nodes: {info.get('nodes') or '—'}")
