"""Edini Panel — PySide6 chat UI for Houdini.

Provides the main panel widget that users interact with.
Layout: Chat Area | Input Bar + Buttons | Status Bar
"""
from __future__ import annotations

import json
import html
import re

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit,
    QScrollArea, QLabel, QFrame, QToolButton, QSizePolicy,
    QDialog, QFormLayout, QDialogButtonBox,
)

from edini.config import (
    PANEL_DEFAULT_WIDTH, PANEL_DEFAULT_HEIGHT,
    get_settings, save_settings,
)
from edini.rpc_client import RpcClient
from edini.tool_executor import ToolExecutor


class EdiniPanel(QWidget):
    """Main Edini chat panel widget."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._tool_executor = ToolExecutor()
        self._rpc_client = RpcClient()
        self._current_assistant_bubble: _ChatBubble | None = None
        self._tool_cards: list[_ToolCard] = []  # ordered list, newest last

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
        self._chat_scroll.verticalScrollBar().actionTriggered.connect(self._on_user_scroll_action)
        self._user_scrolled_up = False
        main_layout.addWidget(self._chat_scroll, stretch=1)

        # --- Header bar (settings button) ---
        header = QHBoxLayout()
        header.addStretch()
        self._settings_btn = QToolButton()
        self._settings_btn.setText("⚙")
        self._settings_btn.setToolTip("Settings: API Key, Provider, Model")
        self._settings_btn.clicked.connect(self._on_settings)
        header.addWidget(self._settings_btn)
        main_layout.addLayout(header)

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

        settings = get_settings()
        self._model_label = QLabel(f"Model: {settings.get('model_id', '?')}")
        self._model_label.setStyleSheet("color: #888; font-size: 11px;")
        status_layout.addWidget(self._model_label)

        status_layout.addStretch()

        self._node_count_label = QLabel("Nodes: -")
        self._node_count_label.setStyleSheet("color: #888; font-size: 11px;")
        status_layout.addWidget(self._node_count_label)

        self._token_label = QLabel("Tokens: -")
        self._token_label.setStyleSheet("color: #888; font-size: 11px;")
        status_layout.addWidget(self._token_label)

        main_layout.addLayout(status_layout)

    def _connect_signals(self) -> None:
        self._rpc_client.text_delta.connect(self._on_text_delta)
        self._rpc_client.tool_call.connect(self._on_tool_start)
        self._rpc_client.agent_started.connect(self._on_agent_start)
        self._rpc_client.agent_finished.connect(self._on_agent_finish)
        self._rpc_client.error_occurred.connect(self._on_error)
        self._rpc_client.status_changed.connect(self._on_status_changed)
        self._rpc_client.stats_updated.connect(self._on_stats_updated)

    def _on_settings(self) -> None:
        """Open the settings dialog."""
        dlg = _SettingsDialog(self)
        if dlg.exec() == QDialog.Accepted:
            data = dlg.get_values()
            api_changed = "api_key" in data and data["api_key"]
            model_changed = "provider" in data or "model_id" in data

            save_settings(data)

            if "model_id" in data:
                self._model_label.setText(f"Model: {data['model_id']}")

            if api_changed:
                self._add_system_message("⚙ API key updated. Restarting Pi...")
                self._rpc_client.restart()

            if model_changed and not api_changed:
                s = get_settings()
                self._rpc_client.send_set_model(s["provider"], s["model_id"])
                self._add_system_message(
                    f"⚙ Switched to {s['provider']}/{s['model_id']}"
                )

    # ------------------------------------------------------------------
    # Signal Handlers
    # ------------------------------------------------------------------

    def _on_send(self) -> None:
        text = self._input_field.text().strip()
        if not text:
            return
        self._input_field.clear()
        self._user_scrolled_up = False
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
        args_str = json.dumps(args, indent=2, ensure_ascii=False)
        card = _ToolCard(tool_name, args_str)
        self._chat_layout.insertWidget(self._chat_layout.count() - 1, card)
        self._tool_cards.append(card)
        self._trim_tool_cards()
        self._scroll_to_bottom()

    def _trim_tool_cards(self) -> None:
        """Keep only the last 3 tool cards visible, hide older ones."""
        max_visible = 3
        if len(self._tool_cards) <= max_visible:
            return
        for card in self._tool_cards[:-max_visible]:
            card.setVisible(False)

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
        # Request latest stats from Pi
        self._rpc_client.send_get_stats()

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

    def _on_stats_updated(self, data: dict) -> None:
        """Update token/cost display from Pi session stats."""
        tokens = data.get("tokens", {})
        cost = data.get("cost", 0)
        ctx = data.get("contextUsage")

        parts = []
        total = tokens.get("total", 0)
        if total:
            parts.append(f"{total:,} tok")

        if cost and cost > 0:
            parts.append(f"${cost:.3f}")

        if ctx:
            pct = ctx.get("percent")
            if pct is not None:
                parts.append(f"ctx {pct}%")

        if parts:
            self._token_label.setText(" · ".join(parts))
        else:
            self._token_label.setText("Tokens: -")

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

    def _on_user_scroll_action(self, action: int) -> None:
        """Called ONLY on user-initiated scroll (wheel, drag, arrow keys)."""
        sb = self._chat_scroll.verticalScrollBar()
        self._user_scrolled_up = (sb.maximum() - sb.value()) > 30

    def _scroll_to_bottom(self) -> None:
        if self._user_scrolled_up:
            return
        sb = self._chat_scroll.verticalScrollBar()
        sb.blockSignals(True)
        sb.setValue(sb.maximum())
        sb.blockSignals(False)

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
        plain = html.escape(self._raw_text).replace("\n", "<br>")
        self._label.setText(f"{plain}<span style='color:#aaa;'>▊</span>")

    def finish_streaming(self) -> None:
        formatted = _format_message(self._raw_text)
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

def _format_message(text: str) -> str:
    """Convert plain text with markdown-ish syntax to simple HTML."""
    # Escape HTML first
    out = html.escape(text)

    # Code blocks: ``` ... ```
    out = re.sub(
        r'```(\w*)\n(.*?)```',
        r'<pre style="background:#1e1e1e;color:#d4d4d4;padding:8px;'
        r'border-radius:4px;font-family:monospace;font-size:11px;'
        r'overflow-x:auto;">\2</pre>',
        out, flags=re.DOTALL,
    )

    # Inline code: `...`
    out = re.sub(
        r'`([^`]+)`',
        r'<code style="background:#333;padding:1px 4px;border-radius:3px;'
        r'font-family:monospace;font-size:11px;">\1</code>',
        out,
    )

    # Bold: **...**
    out = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', out)

    # Lines starting with ## → header
    out = re.sub(r'^## (.+)$', r'<h4 style="margin:4px 0;color:#ccc;">\1</h4>', out, flags=re.MULTILINE)

    # Lines starting with - or * → list item
    out = re.sub(r'^(\s*)[-*] (.+)$', r'\1• \2', out, flags=re.MULTILINE)

    # Numbered lists: 1. → preserve

    # Newlines → <br>
    out = out.replace("\n", "<br>")

    return out


class _ToolCard(QFrame):
    """A collapsible card showing a tool call. Click header to expand/collapse."""

    def __init__(self, tool_name: str, args_json: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._expanded = False

        self.setFrameShape(QFrame.StyledPanel)
        self.setMaximumWidth(500)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("""
            _ToolCard {
                background-color: #2a332a;
                border-radius: 6px;
                margin-left: 20px;
                margin-right: 40px;
            }
            _ToolCard:hover { background-color: #334433; }
            QLabel { color: #80c080; font-size: 11px; }
        """)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(10, 4, 10, 4)

        # Header: always visible
        self._header = QLabel(f"▸ 🔧 <b>{html.escape(tool_name)}</b>")
        self._header.setCursor(Qt.PointingHandCursor)
        self._layout.addWidget(self._header)

        # Detail: hidden by default
        self._detail = QLabel(html.escape(args_json).replace("\n", "<br>"))
        self._detail.setWordWrap(True)
        self._detail.setStyleSheet(
            "color:#a0c0a0; font-family:monospace; font-size:10px;"
            "background:#222; padding:6px; border-radius:4px; margin-top:2px;"
        )
        self._detail.setVisible(False)
        self._layout.addWidget(self._detail)

    def mousePressEvent(self, event) -> None:
        self._expanded = not self._expanded
        self._detail.setVisible(self._expanded)
        arrow = "▾" if self._expanded else "▸"
        # Extract tool name from header text (after arrow+icon+space)
        text = self._header.text()
        text = arrow + text[1:]  # replace first char (arrow)
        self._header.setText(text)
        super().mousePressEvent(event)


# ==========================================================================
# Settings Dialog
# ==========================================================================

class _SettingsDialog(QDialog):
    """Dialog for configuring API key, provider, and model."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Edini Settings")
        self.setMinimumWidth(400)

        settings = get_settings()

        layout = QVBoxLayout(self)

        form = QFormLayout()

        self._api_key = QLineEdit()
        self._api_key.setEchoMode(QLineEdit.Password)
        self._api_key.setPlaceholderText("sk-...")
        self._api_key.setText(settings.get("api_key", ""))
        form.addRow("API Key:", self._api_key)

        self._provider = QLineEdit()
        self._provider.setPlaceholderText("deepseek")
        self._provider.setText(settings.get("provider", ""))
        form.addRow("Provider:", self._provider)

        self._model_id = QLineEdit()
        self._model_id.setPlaceholderText("deepseek-chat")
        self._model_id.setText(settings.get("model_id", ""))
        form.addRow("Model ID:", self._model_id)

        layout.addLayout(form)

        # Preset buttons
        preset_layout = QHBoxLayout()
        for label, prov, model in [
            ("DeepSeek V3", "deepseek", "deepseek-chat"),
            ("DeepSeek R1", "deepseek", "deepseek-reasoner"),
            ("Claude Sonnet", "anthropic", "claude-sonnet-4-5"),
        ]:
            btn = QPushButton(label)
            btn.clicked.connect(
                lambda checked, p=prov, m=model: self._set_preset(p, m)
            )
            preset_layout.addWidget(btn)
        layout.addLayout(preset_layout)

        # Info label
        info = QLabel(
            "<b>DeepSeek:</b> create ~/.pi/agent/models.json first (see README).<br>"
            "<b>Anthropic:</b> no extra config needed."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #aaa; font-size: 11px;")
        layout.addWidget(info)

        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _set_preset(self, provider: str, model_id: str) -> None:
        self._provider.setText(provider)
        self._model_id.setText(model_id)

    def _on_accept(self) -> None:
        """Validate and accept."""
        if not self._provider.text().strip():
            self._provider.setFocus()
            return
        if not self._model_id.text().strip():
            self._model_id.setFocus()
            return
        self.accept()

    def get_values(self) -> dict[str, str]:
        """Return changed values only."""
        old = get_settings()
        result: dict[str, str] = {}
        new_api = self._api_key.text().strip()
        if new_api != old.get("api_key", ""):
            result["api_key"] = new_api
        new_prov = self._provider.text().strip()
        if new_prov != old.get("provider", ""):
            result["provider"] = new_prov
        new_model = self._model_id.text().strip()
        if new_model != old.get("model_id", ""):
            result["model_id"] = new_model
        return result
