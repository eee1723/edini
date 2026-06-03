"""Edini Panel — PySide6 chat UI for Houdini.

Provides the main panel widget that users interact with.
Layout: Chat Area | Input Bar + Buttons | Status Bar
"""
from __future__ import annotations

import json
import html

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit,
    QScrollArea, QLabel, QFrame, QToolButton, QSizePolicy,
)

from edini.config import PANEL_DEFAULT_WIDTH, PANEL_DEFAULT_HEIGHT
from edini.rpc_client import RpcClient
from edini.tool_executor import ToolExecutor


class EdiniPanel(QWidget):
    """Main Edini chat panel widget."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._tool_executor = ToolExecutor()
        self._rpc_client = RpcClient()
        self._current_assistant_bubble: _ChatBubble | None = None
        self._tool_cards: dict[str, _ToolCard] = {}

        self._setup_ui()
        self._connect_signals()

        self._tool_executor.start()
        self._rpc_client.start()

    # ------------------------------------------------------------------
    # UI Setup
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        self.setMinimumSize(350, 400)
        self.resize(PANEL_DEFAULT_WIDTH, PANEL_DEFAULT_HEIGHT)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)

        # --- Chat area ---
        self._chat_scroll = QScrollArea()
        self._chat_scroll.setWidgetResizable(True)
        self._chat_scroll.setFrameShape(QFrame.NoFrame)
        self._chat_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._chat_container = QWidget()
        self._chat_layout = QVBoxLayout(self._chat_container)
        self._chat_layout.setAlignment(Qt.AlignTop)
        self._chat_layout.setSpacing(8)
        self._chat_layout.addStretch()

        self._chat_scroll.setWidget(self._chat_container)
        main_layout.addWidget(self._chat_scroll, stretch=1)

        self._add_system_message(
            "🤖 <b>Edini</b> ready. I can help you create nodes, set parameters, "
            "write VEX/Python, and more. What would you like to do in Houdini?"
        )

        # --- Input area ---
        input_layout = QHBoxLayout()
        input_layout.setSpacing(4)

        self._input_field = QLineEdit()
        self._input_field.setPlaceholderText("Type your message... (Enter to send)")
        self._input_field.returnPressed.connect(self._on_send)
        input_layout.addWidget(self._input_field, stretch=1)

        self._abort_btn = QToolButton()
        self._abort_btn.setText("⏹")
        self._abort_btn.setToolTip("Abort current response")
        self._abort_btn.clicked.connect(self._on_abort)
        self._abort_btn.setVisible(False)
        input_layout.addWidget(self._abort_btn)

        self._send_btn = QPushButton("Send")
        self._send_btn.clicked.connect(self._on_send)
        input_layout.addWidget(self._send_btn)

        main_layout.addLayout(input_layout)

        # --- Status bar ---
        status_layout = QHBoxLayout()
        status_layout.setSpacing(12)

        self._status_label = QLabel("⬤ Connecting...")
        self._status_label.setStyleSheet("color: #888; font-size: 11px;")
        status_layout.addWidget(self._status_label)
        status_layout.addStretch()

        self._node_count_label = QLabel("Nodes: -")
        self._node_count_label.setStyleSheet("color: #888; font-size: 11px;")
        status_layout.addWidget(self._node_count_label)

        main_layout.addLayout(status_layout)

    def _connect_signals(self) -> None:
        self._rpc_client.text_delta.connect(self._on_text_delta)
        self._rpc_client.tool_call.connect(self._on_tool_start)
        self._rpc_client.agent_started.connect(self._on_agent_start)
        self._rpc_client.agent_finished.connect(self._on_agent_finish)
        self._rpc_client.error_occurred.connect(self._on_error)
        self._rpc_client.status_changed.connect(self._on_status_changed)

    # ------------------------------------------------------------------
    # Signal Handlers
    # ------------------------------------------------------------------

    def _on_send(self) -> None:
        text = self._input_field.text().strip()
        if not text:
            return
        self._input_field.clear()
        self._add_user_message(text)

        self._current_assistant_bubble = self._add_assistant_message("")
        self._current_assistant_bubble.set_streaming()

        self._rpc_client.send_prompt(text)

    def _on_abort(self) -> None:
        self._rpc_client.send_abort()

    def _on_text_delta(self, text: str) -> None:
        if self._current_assistant_bubble:
            self._current_assistant_bubble.append_text(text)
            self._scroll_to_bottom()

    def _on_tool_start(self, tool_name: str, tool_call_id: str, args: dict) -> None:
        card = _ToolCard(tool_name, json.dumps(args, indent=2, ensure_ascii=False))
        self._chat_layout.insertWidget(self._chat_layout.count() - 1, card)
        self._tool_cards[tool_call_id] = card
        self._scroll_to_bottom()

    def _on_agent_start(self) -> None:
        self._abort_btn.setVisible(True)
        self._send_btn.setEnabled(False)
        self._status_label.setText("⬤ Processing...")

    def _on_agent_finish(self) -> None:
        self._abort_btn.setVisible(False)
        self._send_btn.setEnabled(True)
        self._status_label.setText("⬤ Connected")
        if self._current_assistant_bubble:
            self._current_assistant_bubble.finish_streaming()
        self._refresh_node_count()

    def _on_error(self, message: str) -> None:
        self._add_system_message(f"⚠️ {html.escape(message)}", is_error=True)

    def _on_status_changed(self, status: str) -> None:
        status_map = {
            "connecting": "⬤ Connecting...",
            "connected": "⬤ Connected",
            "disconnected": "⬤ Disconnected",
            "error": "⬤ Error",
        }
        self._status_label.setText(status_map.get(status, f"⬤ {status}"))

    # ------------------------------------------------------------------
    # Chat Helpers
    # ------------------------------------------------------------------

    def _add_user_message(self, text: str) -> _ChatBubble:
        bubble = _ChatBubble(text, is_user=True)
        self._chat_layout.insertWidget(self._chat_layout.count() - 1, bubble)
        self._scroll_to_bottom()
        return bubble

    def _add_assistant_message(self, text: str) -> _ChatBubble:
        bubble = _ChatBubble(text, is_user=False)
        self._chat_layout.insertWidget(self._chat_layout.count() - 1, bubble)
        self._scroll_to_bottom()
        return bubble

    def _add_system_message(self, text: str, is_error: bool = False) -> _ChatBubble:
        bubble = _ChatBubble(text, is_user=False, is_system=True)
        if is_error:
            bubble.set_error_style()
        self._chat_layout.insertWidget(self._chat_layout.count() - 1, bubble)
        self._scroll_to_bottom()
        return bubble

    def _scroll_to_bottom(self) -> None:
        QTimer.singleShot(10, lambda: self._chat_scroll.verticalScrollBar().setValue(
            self._chat_scroll.verticalScrollBar().maximum()
        ))

    def _refresh_node_count(self) -> None:
        try:
            import hou
            root = hou.node("/")
            count = len(root.allSubChildren()) if root else 0
            self._node_count_label.setText(f"Nodes: {count}")
        except Exception:
            self._node_count_label.setText("Nodes: -")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def closeEvent(self, event) -> None:
        self._rpc_client.stop()
        self._tool_executor.stop()
        super().closeEvent(event)


# ==========================================================================
# Chat Bubble Widget
# ==========================================================================

class _ChatBubble(QFrame):
    """A single chat message bubble.

    Modes: user (right-aligned, blue), assistant (left-aligned, dark, streaming),
    system (centered, gray, italic).
    """

    def __init__(
        self,
        text: str,
        is_user: bool = False,
        is_system: bool = False,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._is_user = is_user
        self._is_system = is_system
        self._raw_text = text

        self.setFrameShape(QFrame.StyledPanel)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setMaximumWidth(500)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)

        self._label = QLabel(text)
        self._label.setWordWrap(True)
        self._label.setTextFormat(Qt.RichText)
        self._label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self._label)

        self._apply_style()

    def _apply_style(self) -> None:
        if self._is_user:
            self.setStyleSheet("""
                _ChatBubble {
                    background-color: #2a5f8a;
                    border-radius: 8px;
                    margin-left: 40px;
                }
                QLabel { color: #ffffff; font-size: 12px; }
            """)
        elif self._is_system:
            self.setStyleSheet("""
                _ChatBubble { background-color: transparent; border: none; }
                QLabel { color: #888888; font-size: 11px; font-style: italic; }
            """)
        else:
            self.setStyleSheet("""
                _ChatBubble {
                    background-color: #333333;
                    border-radius: 8px;
                    margin-right: 40px;
                }
                QLabel { color: #e0e0e0; font-size: 12px; }
            """)

    def set_streaming(self) -> None:
        self._raw_text = ""
        self._label.setText('<span style="color:#aaa;">▊</span>')

    def append_text(self, delta: str) -> None:
        self._raw_text += delta
        formatted = html.escape(self._raw_text).replace("\n", "<br>")
        self._label.setText(f"{formatted}<span style='color:#aaa;'>▊</span>")

    def finish_streaming(self) -> None:
        formatted = html.escape(self._raw_text).replace("\n", "<br>")
        self._label.setText(formatted)

    def set_error_style(self) -> None:
        self.setStyleSheet("""
            _ChatBubble {
                background-color: #5a2a2a;
                border-radius: 8px;
            }
            QLabel { color: #ffaaaa; font-size: 12px; }
        """)


# ==========================================================================
# Tool Card Widget
# ==========================================================================

class _ToolCard(QFrame):
    """A card showing a tool call with its name."""

    def __init__(self, tool_name: str, args_json: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self.setMaximumWidth(500)
        self.setStyleSheet("""
            _ToolCard {
                background-color: #2a332a;
                border-radius: 6px;
                margin-left: 20px;
                margin-right: 40px;
            }
            QLabel { color: #80c080; font-size: 11px; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.addWidget(QLabel(f"🔧 <b>{html.escape(tool_name)}</b>"))
