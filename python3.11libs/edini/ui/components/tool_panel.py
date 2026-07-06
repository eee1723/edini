"""ToolPanel — collapsible container of tool-call cards.

Promoted out of AgentPanel._build_ui() (Stage 2, Task 1.4). The visible
behavior — card styling, auto-expand on first card, real-time result
updates, clear semantics — is preserved verbatim from the original inline
implementation.
"""
import html

from PySide6 import QtCore, QtWidgets

from edini.ui.theme import fs


# ═══════════════════════════════════════════════════════════════════════
# Formatting helpers (moved verbatim from agent_panel.py)
# ═══════════════════════════════════════════════════════════════════════

def _format_args(args: dict) -> str:
    if not args:
        return ""
    parts = []
    for k, v in args.items():
        parts.append(f"<b>{html.escape(k)}</b>: {html.escape(str(v))}")
    return "  ·  ".join(parts)


def _format_tool_result_short(result: str, success: bool) -> str:
    if not result:
        return ""
    try:
        import json
        d = json.loads(result) if isinstance(result, str) else result
        if isinstance(d, dict):
            if d.get("success"):
                out = d.get("path", d.get("output", d.get("name", "")))
                return html.escape(str(out)[:80])
            else:
                return html.escape(d.get("error", "Unknown error")[:80])
    except Exception:
        pass
    return html.escape(str(result)[:80])


# ═══════════════════════════════════════════════════════════════════════
# Tool Card Widget (moved verbatim from agent_panel.py — internal)
# ═══════════════════════════════════════════════════════════════════════

class _ToolCardWidget(QtWidgets.QFrame):
    """A single collapsible tool call card. Added/updated in real-time."""

    def __init__(self, tool_name: str, args: dict, tool_call_id: str, parent=None):
        super().__init__(parent)
        self._tool_call_id = tool_call_id
        self._expanded = False

        self.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.setStyleSheet(f"""
            _ToolCardWidget {{
                background: rgba(0,188,212,0.03);
                border: 1px solid #181830;
                border-radius: 4px;
            }}
            _ToolCardWidget:hover {{
                background: rgba(0,188,212,0.06);
                border-color: #253545;
            }}
        """)
        self.setCursor(QtCore.Qt.PointingHandCursor)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(1)

        # Header row: icon + name + status
        header_row = QtWidgets.QHBoxLayout()
        header_row.setSpacing(2)
        self._arrow = QtWidgets.QLabel("▸")
        self._arrow.setStyleSheet(f"color:#80cbc4;font-size:{fs(11)};border:none;")
        self._arrow.setFixedWidth(16)
        header_row.addWidget(self._arrow)

        self._name_label = QtWidgets.QLabel(f"🔧 {html.escape(tool_name)}")
        self._name_label.setStyleSheet(f"color:#80cbc4;font-size:{fs(11)};font-weight:600;border:none;")
        header_row.addWidget(self._name_label, 1)

        self._status_label = QtWidgets.QLabel("⏳")
        self._status_label.setStyleSheet(f"color:#d97706;font-size:{fs(10)};border:none;")
        self._status_label.setFixedWidth(30)
        self._status_label.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        header_row.addWidget(self._status_label)

        layout.addLayout(header_row)

        # Detail area (hidden by default)
        self._detail = QtWidgets.QWidget()
        detail_layout = QtWidgets.QVBoxLayout(self._detail)
        detail_layout.setContentsMargins(20, 2, 0, 2)
        detail_layout.setSpacing(2)

        args_str = _format_args(args)
        self._args_label = QtWidgets.QLabel(args_str)
        self._args_label.setWordWrap(True)
        self._args_label.setStyleSheet(f"color:#78909c;font-size:{fs(10)};font-family:monospace;border:none;")
        detail_layout.addWidget(self._args_label)

        self._result_label = QtWidgets.QLabel("")
        self._result_label.setWordWrap(True)
        self._result_label.setStyleSheet(f"color:#94a3b8;font-size:{fs(10)};border:none;")
        self._result_label.setVisible(False)
        detail_layout.addWidget(self._result_label)

        self._detail.setVisible(False)
        layout.addWidget(self._detail)

    def mousePressEvent(self, event):
        self._expanded = not self._expanded
        self._arrow.setText("▾" if self._expanded else "▸")
        self._detail.setVisible(self._expanded)
        super().mousePressEvent(event)

    def set_result(self, result_text: str, success: bool = True):
        self._status_label.setText("✅" if success else "❌")
        self._status_label.setStyleSheet(
            f"color:{'#16a34a' if success else '#ef4444'};font-size:{fs(10)};border:none;"
        )
        self._result_label.setText(_format_tool_result_short(result_text, success))
        self._result_label.setVisible(True)

    def set_error(self, error_msg: str):
        self._status_label.setText("❌")
        self._status_label.setStyleSheet(f"color:#ef4444;font-size:{fs(10)};border:none;")
        self._result_label.setText(f"Error: {html.escape(error_msg)}")
        self._result_label.setVisible(True)

    @property
    def tool_call_id(self) -> str:
        return self._tool_call_id


# ═══════════════════════════════════════════════════════════════════════
# ToolPanel
# ═══════════════════════════════════════════════════════════════════════

class ToolPanel(QtWidgets.QFrame):
    """Holds tool-call cards; auto-expands on first card; updates in real-time."""

    COLLAPSED_H = 24
    EXPANDED_H = 200

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cards: "dict[str, _ToolCardWidget]" = {}
        self._expanded = False
        self.setStyleSheet("""
            QFrame {
                background: #0a0a12;
                border-top: 1px solid #1c1c2a;
                border-bottom: 1px solid #1c1c2a;
            }
            _ToolCardWidget {
                background: rgba(0,188,212,0.04);
                border: 1px solid #1a1a2e;
                border-radius: 4px;
                margin: 1px 0;
            }
            _ToolCardWidget:hover {
                background: rgba(0,188,212,0.08);
                border-color: #253545;
            }
        """)
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(10, 3, 10, 4)
        outer.setSpacing(0)

        header = QtWidgets.QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        self._toggle_lbl = QtWidgets.QLabel("▸ Tool Calls (0)")
        self._toggle_lbl.setCursor(QtCore.Qt.PointingHandCursor)
        self._toggle_lbl.setStyleSheet(
            f"color:#4a4a5a;font-size:{fs(10)};border:none;padding:1px 0;"
        )
        self._toggle_lbl.mousePressEvent = lambda e: self.toggle()
        header.addWidget(self._toggle_lbl)
        header.addStretch()
        outer.addLayout(header)

        self._scroll = QtWidgets.QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self._container = QtWidgets.QWidget()
        self._container.setStyleSheet("background: transparent;")
        self._layout = QtWidgets.QVBoxLayout(self._container)
        self._layout.setAlignment(QtCore.Qt.AlignTop)
        self._layout.setSpacing(1)
        self._layout.setContentsMargins(0, 4, 0, 0)
        self._layout.addStretch()
        self._scroll.setWidget(self._container)

        self._scroll.setVisible(False)
        outer.addWidget(self._scroll)

        self.setFixedHeight(self.COLLAPSED_H)

    def toggle(self):
        self._expanded = not self._expanded
        self._scroll.setVisible(self._expanded)
        arrow = "▾" if self._expanded else "▸"
        count = len(self._cards)
        self._toggle_lbl.setText(f"{arrow} Tool Calls ({count})")
        if self._expanded:
            self.setFixedHeight(self.EXPANDED_H)
        else:
            self.setFixedHeight(self.COLLAPSED_H)

    def is_expanded(self) -> bool:
        return self._expanded

    def toggle_text(self) -> str:
        return self._toggle_lbl.text()

    def card_count(self) -> int:
        return len(self._cards)

    def add_card(self, tool_name: str, tool_call_id: str, args: dict):
        """Add a tool card; auto-expand on first card (mirrors _add_tool_card_ui).

        NOTE: arg order is (tool_name, tool_call_id, args) — the original
        _add_tool_card_ui(tool_name, args, tool_call_id) had args last.
        """
        card = _ToolCardWidget(tool_name, args, tool_call_id)
        self._cards[tool_call_id] = card
        self._layout.insertWidget(self._layout.count() - 1, card)
        self._scroll.verticalScrollBar().setValue(
            self._scroll.verticalScrollBar().maximum())
        count = len(self._cards)
        arrow = "▾" if self._expanded else "▸"
        self._toggle_lbl.setText(f"{arrow} Tool Calls ({count})")
        if not self._expanded and count == 1:
            self.toggle()

    def update_result(self, tool_call_id: str, result_text: str, success: bool = True):
        card = self._cards.get(tool_call_id)
        if card:
            card.set_result(result_text, success)

    def collapse(self):
        """Collapse the panel if currently expanded (mirrors _collapse_tool_panel)."""
        if self._expanded:
            self.toggle()

    def clear(self):
        """Remove all cards (mirrors _clear_tool_cards).

        NOTE: original kept the scroll visible if the panel was expanded;
        we preserve that.
        """
        for card in self._cards.values():
            self._layout.removeWidget(card)
            card.deleteLater()
        self._cards.clear()
        self._toggle_lbl.setText("▸ Tool Calls (0)")
        if self._expanded:
            self._scroll.setVisible(True)
