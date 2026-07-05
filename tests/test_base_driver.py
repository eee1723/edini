"""BaseChatDriver binds ChatRuntime signals to ChatWindowShell components."""
import sys
sys.path.insert(0, "python3.11libs")
from tests.qt_helpers import qapp, SignalSpy
from PySide6 import QtCore
from edini.ui.chat_runtime import ChatRuntime
from edini.ui.chat.scope import ScopeConfig
from edini.ui.chat.window_shell import ChatWindowShell
from edini.ui.chat.base_driver import BaseChatDriver


class _FakeRpc(QtCore.QObject):
    text_delta = QtCore.Signal(str)
    thinking_delta = QtCore.Signal(str)
    tool_call = QtCore.Signal(str, str, object)
    tool_result = QtCore.Signal(str, str, str)
    agent_started = QtCore.Signal()
    agent_finished = QtCore.Signal()
    error_occurred = QtCore.Signal(str)
    stats_updated = QtCore.Signal(object)
    status_changed = QtCore.Signal(str)
    models_received = QtCore.Signal(object)
    session_switched = QtCore.Signal(str)
    def send_prompt(self, *a, **k): pass


def _make_setup():
    rpc = _FakeRpc()
    rt = ChatRuntime(rpc)
    scope = ScopeConfig(scope_id="agent", window_title="T", accent_override=None,
                        header_badge=None, left_panel_kind="global_sessions",
                        show_change_tree=True, show_eval_button=True,
                        show_attachment_bar=True, show_param_snapshot=False,
                        scene_data_provider=lambda: {})
    shell = ChatWindowShell(scope)
    drv = BaseChatDriver(rt, shell)
    return drv, rpc, shell


def test_stream_chunk_creates_ai_bubble():
    drv, rpc, shell = _make_setup()
    from edini.ui.components.bubbles import AiBubble
    # before: no AiBubble in timeline
    rpc.text_delta.emit("hello")
    # an AiBubble should now exist and have accumulated text
    bubbles = shell.timeline._container.findChildren(AiBubble)
    assert len(bubbles) == 1
    assert bubbles[0]._raw_text == "hello"


def test_stream_chunk_then_finish_renders():
    drv, rpc, shell = _make_setup()
    rpc.text_delta.emit("**bold**")
    rpc.agent_finished.emit()
    from edini.ui.components.bubbles import AiBubble
    bubbles = shell.timeline._container.findChildren(AiBubble)
    assert len(bubbles) == 1
    assert bubbles[0]._streaming is False
    assert "<b>bold</b>" in bubbles[0]._label.text()


def test_thinking_chunk_buffers_until_paragraph_break():
    """Thinking deltas are word-level; they buffer until \\n\\n or turn end."""
    drv, rpc, shell = _make_setup()
    rpc.thinking_delta.emit("reasoning ")
    rpc.thinking_delta.emit("here")
    # Still in buffer (no \n\n) — paragraph count stays 0, but live view shows text
    assert "Thinking (0" in shell.thinking_panel.toggle_text()
    assert shell.thinking_panel.has_content() is False  # _thinking_full still empty


def test_thinking_paragraph_break_finalizes():
    """A \\n\\n in the stream splits off a finalized paragraph."""
    drv, rpc, shell = _make_setup()
    rpc.thinking_delta.emit("first paragraph\n\nsecond")
    # "first paragraph" is now a finalized paragraph
    assert "Thinking (1" in shell.thinking_panel.toggle_text()


def test_thinking_flushed_on_turn_done():
    """Pending buffer is finalized into a paragraph when the turn ends."""
    drv, rpc, shell = _make_setup()
    rpc.thinking_delta.emit("some reasoning")
    assert "Thinking (0" in shell.thinking_panel.toggle_text()  # buffered
    rpc.agent_finished.emit()  # turn done → flush
    assert "Thinking (1" in shell.thinking_panel.toggle_text()


def test_tool_call_adds_card():
    drv, rpc, shell = _make_setup()
    rpc.tool_call.emit("build_node", "call_1", {"path": "/x"})
    assert shell.tool_panel.card_count() == 1


def test_tool_result_updates_card():
    drv, rpc, shell = _make_setup()
    rpc.tool_call.emit("build_node", "call_1", {})
    rpc.tool_result.emit("build_node", "call_1", "result text")
    # should not crash; card still present
    assert shell.tool_panel.card_count() == 1


def test_stats_updates_context_panel():
    drv, rpc, shell = _make_setup()
    rpc.stats_updated.emit({"tokens": {"input": 100, "output": 50, "total": 150},
                            "cost": 0.01})
    # ContextPanel.set_usage updates token labels — check it didn't crash
    # and a label contains the value
    assert "100" in shell.context_panel.token_in_label.text() or "150" in shell.context_panel.token_total_label.text()


def test_status_updates_context_panel():
    drv, rpc, shell = _make_setup()
    rpc.status_changed.emit("connected")
    assert "onnected" in shell.context_panel.status_label.text()  # "Connected" (case varies)


def test_send_calls_rpc_send_prompt():
    drv, rpc, shell = _make_setup()
    called = []
    rpc.send_prompt = lambda t, images=None: called.append((t, images))
    drv.send("hi there")
    assert called == [("hi there", None)]


def test_send_creates_user_bubble():
    drv, rpc, shell = _make_setup()
    from edini.ui.components.bubbles import UserBubble
    rpc.send_prompt = lambda *a, **k: None
    drv.send("user msg")
    bubbles = shell.timeline._container.findChildren(UserBubble)
    assert len(bubbles) == 1


def test_empty_send_does_nothing():
    drv, rpc, shell = _make_setup()
    called = []
    rpc.send_prompt = lambda *a, **k: called.append(a)
    drv.send("   ")
    assert called == []
