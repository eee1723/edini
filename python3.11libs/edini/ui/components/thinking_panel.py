"""ThinkingPanel — collapsible reasoning display.

Promoted out of AgentPanel._build_ui() (Stage 2, Task 1.4). The visible
behavior — paragraph-counting header ("▸ Thinking (N ¶)"), HTML rendering
with line-height, the live "typing" cursor (▊), toggle/auto-expand/reset
semantics — is preserved verbatim from the original inline implementation.
"""
import html

from PySide6 import QtCore, QtWidgets

from edini.ui.theme import fs


def _paragraph_count(text: str) -> int:
    """Number of paragraphs separated by blank lines (matches original)."""
    return text.count('\n\n') + 1 if text else 0


class ThinkingPanel(QtWidgets.QFrame):
    """Collapsible panel showing accumulated reasoning text.

    Collapsed by default (24px header "▸ Thinking (0 ¶)"); expands to 200px
    showing the accumulated text buffer with a live typing cursor while
    streaming. Paragraph counting matches the original: number of
    '\\n\\n'-separated paragraphs in `_thinking_full`.
    """

    COLLAPSED_H = 24
    EXPANDED_H = 200

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thinking_full = ""
        self._thinking_buf = ""
        self._expanded = False
        self.setStyleSheet("""
            QFrame {
                background: #0a0a12;
                border-top: 1px solid #1c1c2a;
            }
        """)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(10, 3, 10, 4)
        lay.setSpacing(0)

        header = QtWidgets.QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        self._toggle_lbl = QtWidgets.QLabel("▸ Thinking (0)")
        self._toggle_lbl.setCursor(QtCore.Qt.PointingHandCursor)
        self._toggle_lbl.setStyleSheet(
            f"color:#4a4a5a;font-size:{fs(10)};border:none;padding:1px 0;"
        )
        self._toggle_lbl.mousePressEvent = lambda e: self.toggle()
        header.addWidget(self._toggle_lbl)
        header.addStretch()
        lay.addLayout(header)

        self._view = QtWidgets.QTextEdit()
        self._view.setReadOnly(True)
        self._view.setStyleSheet(
            f"QTextEdit {{ background: transparent; color: #8b8fa8; "
            f"font-size:{fs(11)}; border: none; }}"
        )
        self._view.setVisible(False)
        lay.addWidget(self._view)

        self.setFixedHeight(self.COLLAPSED_H)

    # ── internal helpers (verbatim from original) ──

    def _set_toggle_text(self):
        paragraphs = _paragraph_count(self._thinking_full)
        arrow = "▾" if self._expanded else "▸"
        self._toggle_lbl.setText(f"{arrow} Thinking ({paragraphs} ¶)")

    def _render_html(self, display: str):
        self._view.setHtml(
            f'<div style="color:#8b8fa8;font-size:{fs(11)};line-height:1.5;">{display}</div>'
        )
        self._view.verticalScrollBar().setValue(
            self._view.verticalScrollBar().maximum())

    # ── public API (mirrors original AgentPanel thinking methods) ──

    def toggle(self):
        """Toggle expanded/collapsed. Header text recomputed from paragraphs."""
        self._expanded = not self._expanded
        self._view.setVisible(self._expanded)
        self.setFixedHeight(self.EXPANDED_H if self._expanded else self.COLLAPSED_H)
        paragraphs = _paragraph_count(self._thinking_full)
        arrow = "▾" if self._expanded else "▸"
        self._toggle_lbl.setText(f"{arrow} Thinking ({paragraphs} ¶)")

    def is_expanded(self) -> bool:
        return self._expanded

    def toggle_text(self) -> str:
        return self._toggle_lbl.text()

    def has_content(self) -> bool:
        return bool(self._thinking_full)

    def view_html(self) -> str:
        """Return current rendered HTML (for tests)."""
        return self._view.toHtml()

    def append(self, text: str):
        """Finalize a thinking paragraph (mirrors _append_thinking_text)."""
        if not self._thinking_full:
            self._thinking_full = text
        else:
            self._thinking_full += "\n\n" + text
        display = (
            html.escape(self._thinking_full)
            .replace("\n\n", "<br><br>")
            .replace("\n", "<br>")
        )
        self._render_html(display)
        self._set_toggle_text()

    def render_live(self, buf: str):
        """Render the in-progress buffer with a trailing cursor (mirrors _update_live_thinking)."""
        self._thinking_buf = buf
        if not self._thinking_buf:
            return
        live = html.escape(self._thinking_buf).replace("\n", "<br>")
        if self._thinking_full:
            base = (
                html.escape(self._thinking_full)
                .replace("\n\n", "<br><br>")
                .replace("\n", "<br>")
            )
            display = f'{base}<br><br>{live}'
        else:
            display = live
        self._view.setHtml(
            f'<div style="color:#8b8fa8;font-size:{fs(11)};line-height:1.5;">{display}'
            f'<span style="color:#a78bfa;">▊</span></div>'
        )
        self._view.verticalScrollBar().setValue(
            self._view.verticalScrollBar().maximum())

    def auto_expand(self):
        """Expand the panel if currently collapsed (mirrors _auto_expand_thinking)."""
        if not self._expanded:
            self.toggle()

    def collapse(self):
        """Collapse the panel if currently expanded (mirrors _collapse_thinking_panel)."""
        if self._expanded:
            self.toggle()

    def clear(self):
        """Clear accumulated content (mirrors _clear_thinking).

        NOTE: only resets content, NOT the expand state — matching the
        original, which kept the panel visible if it was open.
        """
        self._thinking_full = ""
        self._thinking_buf = ""
        self._view.clear()
        self._toggle_lbl.setText("▸ Thinking (0)")
        if self._expanded:
            self._view.setVisible(True)

    def reset(self):
        """Full reset: clear content AND collapse the panel.

        Used by AgentPanel._on_send() to return both panels to the initial
        (collapsed, empty) state at the start of a new turn.
        """
        self._thinking_full = ""
        self._thinking_buf = ""
        self._view.clear()
        self._view.setVisible(False)
        self._expanded = False
        self.setFixedHeight(self.COLLAPSED_H)
        self._toggle_lbl.setText("▸ Thinking (0)")
