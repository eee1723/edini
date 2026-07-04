"""Lightweight adapter between Pi RpcClient signals and the agent panel UI."""
from PySide6.QtCore import QObject, Signal


class ChatRuntime(QObject):
    """Wraps RpcClient, providing structured signals for the UI panel."""

    started = Signal(dict)
    stream_chunk = Signal(str)
    thinking_chunk = Signal(str)
    completed = Signal(dict)
    failed = Signal(str)
    tool_started = Signal(str, str, dict)
    tool_completed = Signal(str, str, str)
    stats_updated = Signal(dict)
    busy_changed = Signal(bool)
    # NEW passthrough signals (Stage 3):
    status_changed = Signal(str)
    models_received = Signal(object)
    session_switched = Signal(str)

    def __init__(self, rpc_client, parent=None):
        super().__init__(parent)
        self._rpc = rpc_client
        self._bind()

    @property
    def rpc(self):
        """Expose the underlying RpcClient (drivers need send_prompt etc.)."""
        return self._rpc

    def _bind(self):
        r = self._rpc
        r.text_delta.connect(self._on_text_delta)
        r.thinking_delta.connect(self._on_thinking_delta)
        r.tool_call.connect(self._on_tool_call)
        r.tool_result.connect(self._on_tool_result)
        r.agent_started.connect(self._on_agent_start)
        r.agent_finished.connect(self._on_agent_finish)
        r.error_occurred.connect(self._on_error)
        r.stats_updated.connect(self._on_stats)
        # NEW passthrough bindings:
        r.status_changed.connect(self.status_changed)
        r.models_received.connect(self.models_received)
        r.session_switched.connect(self.session_switched)

    def _on_text_delta(self, text: str):
        self.stream_chunk.emit(text)

    def _on_thinking_delta(self, text: str):
        self.thinking_chunk.emit(text)

    def _on_tool_call(self, tool_name: str, tool_call_id: str, args: dict):
        self.tool_started.emit(tool_name, tool_call_id, args)

    def _on_tool_result(self, tool_name: str, tool_call_id: str, result: str):
        self.tool_completed.emit(tool_name, tool_call_id, result)

    def _on_agent_start(self):
        self.started.emit({})
        self.busy_changed.emit(True)

    def _on_agent_finish(self):
        self.completed.emit({})
        self.busy_changed.emit(False)

    def _on_error(self, msg: str):
        self.failed.emit(msg)
        self.busy_changed.emit(False)

    def _on_stats(self, data: dict):
        self.stats_updated.emit(data)
