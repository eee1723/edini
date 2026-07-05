"""BaseChatDriver — wires ChatRuntime signals to ChatWindowShell components.

Plain QObject (NOT a QWidget base class). Holds runtime + shell. Common chat
behavior lives here; subclasses override hooks for scope-specific concerns
(left panel, scene data, session switching).
"""
from PySide6 import QtCore, QtWidgets
from edini.ui.components.bubbles import AiBubble, UserBubble


class BaseChatDriver(QtCore.QObject):
    """Connects a ChatRuntime to a ChatWindowShell's components.

    Handles: stream_chunk → AiBubble (append_chunk + finalize),
             thinking_chunk → ThinkingPanel, tool_call/result → ToolPanel,
             stats/status → ContextPanel, send → UserBubble + rpc.send_prompt.
    """

    def __init__(self, runtime, shell):
        super().__init__(shell)
        self._runtime = runtime
        self._shell = shell
        self._current_ai = None
        # Thinking buffer: Pi sends thinking_delta as word-level increments;
        # we accumulate into _thinking_buf and render live, then flush to a
        # finalized paragraph on turn end. (Mirrors main-window add_thinking_step.)
        self._thinking_buf = ""
        self._bind_runtime()
        self._bind_input()

    def _bind_runtime(self):
        r, s = self._runtime, self._shell
        r.stream_chunk.connect(self._on_stream_chunk)
        r.thinking_chunk.connect(self._on_thinking_chunk)
        r.tool_started.connect(self._on_tool_started)
        r.tool_completed.connect(self._on_tool_completed)
        r.completed.connect(self._on_turn_done)
        r.stats_updated.connect(s.context_panel.set_usage)
        r.status_changed.connect(s.context_panel.set_pi_status)
        r.started.connect(self._on_started)
        r.failed.connect(self._on_failed)

    def _bind_input(self):
        self._shell.input_bar.submit_requested.connect(self.send)

    # ── Stream handling ──
    def _on_stream_chunk(self, chunk: str):
        if self._current_ai is None and chunk.strip():
            self._current_ai = AiBubble()
            self._shell.timeline.add_widget(self._current_ai)
        if self._current_ai is not None:
            self._current_ai.append_chunk(chunk)

    # ── Thinking handling (buffered — Pi sends word-level deltas) ──
    def _on_thinking_chunk(self, chunk: str):
        """Accumulate thinking deltas into a buffer; render live with cursor.

        Pi's thinking_delta is incremental (word-by-word), NOT paragraph-by-
        paragraph. So we must accumulate (like stream_chunk), not call append()
        per chunk (which would treat each word as a separate paragraph).
        Paragraph breaks (\n\n) in the buffer split into finalized paragraphs.
        """
        panel = self._shell.thinking_panel
        if not chunk:
            return
        # Append to buffer; split off any completed paragraphs (\n\n).
        self._thinking_buf += chunk
        if "\n\n" in self._thinking_buf:
            parts = self._thinking_buf.split("\n\n")
            # All but the last are complete paragraphs — finalize them.
            for para in parts[:-1]:
                if para.strip():
                    panel.append(para)
            self._thinking_buf = parts[-1]
        # Render the in-progress tail with a live cursor.
        if self._thinking_buf:
            panel.auto_expand()
            panel.render_live(self._thinking_buf)

    def _flush_thinking(self):
        """Finalize any pending thinking buffer at turn end."""
        if self._thinking_buf.strip():
            self._shell.thinking_panel.append(self._thinking_buf)
        self._thinking_buf = ""

    def _on_turn_done(self, _payload=None):
        self._flush_thinking()
        if self._current_ai is not None:
            self._current_ai.finalize()
            self._current_ai = None

    # ── Tool handling ──
    def _on_tool_started(self, tool_name: str, tool_call_id: str, args: dict):
        self._shell.tool_panel.add_card(tool_name, tool_call_id, args)

    def _on_tool_completed(self, tool_name: str, tool_call_id: str, result: str):
        self._shell.tool_panel.update_result(tool_call_id, result, True)

    # ── Lifecycle ──
    def _on_started(self, _payload=None):
        self._thinking_buf = ""
        self._shell.thinking_panel.reset()
        self._shell.tool_panel.clear()
        self._shell.input_bar.set_busy(True)

    def _on_failed(self, msg: str):
        self._shell.input_bar.set_busy(False)

    # ── Send ──
    def send(self, text: str, images=None):
        if not text or not text.strip():
            return
        self._shell.timeline.add_widget(UserBubble(text, images))
        self._runtime.rpc.send_prompt(text, images=images)

    # ── Hooks for subclasses (default no-op) ──
    def build_left_panel(self) -> QtWidgets.QWidget:
        """Override to provide the left panel (session list / version list)."""
        return None

    def collect_scene_info(self) -> dict:
        """Override to provide scene data for ContextPanel."""
        return {}

    def on_session_changed(self, session_id: str):
        """Override to handle session/version switching."""
        pass
