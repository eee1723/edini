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
    model_changed = QtCore.Signal(object)
    extension_info = QtCore.Signal(str)
    def send_prompt(self, *a, **k): pass
    def send_abort(self): pass
    def send_get_state(self): pass
    def send_get_stats(self): pass


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
    """Base driver (no core_path) sends text as-is — no context prefix."""
    drv, rpc, shell = _make_setup()
    called = []
    rpc.send_prompt = lambda t, images=None: called.append((t, images))
    drv.send("hi there")
    assert called == [("hi there", None)]


def test_send_hda_driver_injects_context_prefix():
    """HDA-scoped driver prefixes messages with [Current Houdini Context]."""
    from edini.project.panel.chat_driver import ProjectChatDriver
    rpc = _FakeRpc()
    rt = ChatRuntime(rpc)
    scope = ScopeConfig(scope_id="project_hda", window_title="T", accent_override="#f59e0b",
                        header_badge="b", left_panel_kind="node_versions",
                        show_change_tree=True, show_eval_button=False,
                        show_attachment_bar=False, show_param_snapshot=True,
                        scene_data_provider=lambda: {})
    shell = ChatWindowShell(scope)
    drv = ProjectChatDriver(rt, shell, core_path="/obj/geo1/project_core")
    called = []
    rpc.send_prompt = lambda t, images=None: called.append(t)
    drv.send("做一个桌子")
    assert len(called) == 1
    assert "[Current Houdini Context]" in called[0]
    assert "/obj/geo1/project_core" in called[0]
    assert "做一个桌子" in called[0]
    # The user bubble should show the ORIGINAL text (not the prefixed version)
    from edini.ui.components.bubbles import UserBubble
    bubbles = shell.timeline._container.findChildren(UserBubble)
    assert len(bubbles) == 1
    assert "做一个桌子" in bubbles[0]._label.text()
    assert "[Current Houdini Context]" not in bubbles[0]._label.text()


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


def test_busy_changed_resets_input_bar_on_finish():
    """Regression: agent_finished must reset the input bar to idle.

    Without the busy_changed wiring, the button got stuck on '中止' after a
    turn finished, blocking multi-turn chat.
    """
    drv, rpc, shell = _make_setup()
    rpc.agent_started.emit()   # busy=True via busy_changed
    assert shell.input_bar.is_busy() is True
    rpc.agent_finished.emit()  # busy=False via busy_changed
    assert shell.input_bar.is_busy() is False


def test_abort_button_calls_send_abort():
    """Regression: clicking '中止' must actually stop Pi (was a no-op)."""
    drv, rpc, shell = _make_setup()
    called = []
    rpc.send_abort = lambda: called.append(True)
    # Simulate the busy state then the abort click
    rpc.agent_started.emit()
    shell.input_bar.abort_requested.emit()
    assert called == [True]


def test_model_changed_updates_context_panel():
    """Regression: model name must show in Pi Status card.

    BaseChatDriver must connect rpc.model_changed → set_provider_model,
    otherwise the Pi Status card shows '—' forever.
    """
    drv, rpc, shell = _make_setup()
    rpc.model_changed.emit({"provider": "deepseek", "name": "deepseek-v4"})
    assert "deepseek" in shell.context_panel.provider_model_label.text()


def test_stats_requested_on_turn_start_and_end():
    """Regression: token usage must update (driver requests send_get_stats)."""
    drv, rpc, shell = _make_setup()
    state_calls = []
    stats_calls = []
    rpc.send_get_state = lambda: state_calls.append(True)
    rpc.send_get_stats = lambda: stats_calls.append(True)
    rpc.agent_started.emit()   # should call send_get_state + start polling
    assert len(state_calls) == 1
    rpc.agent_finished.emit()  # should call send_get_stats (final fetch)
    assert len(stats_calls) >= 1


def test_round_timer_starts_on_turn_start():
    """Regression: the round timer must start when a turn begins (mirrors
    main_window). The QTimer drives a 1s-tick label update."""
    drv, rpc, shell = _make_setup()
    rpc.send_get_state = lambda: None
    rpc.send_get_stats = lambda: None
    rpc.agent_started.emit()
    # The round QTimer should now be running and the elapsed stopwatch valid.
    assert drv._round_timer.isActive() is True
    assert drv._round_elapsed.isValid() is True
    # A manual tick must push the elapsed time into the label.
    drv._on_round_tick()
    assert "Round: 0:" in shell.context_panel.round_time_label.text()


def test_round_timer_stops_on_turn_done():
    """The round timer must stop when the turn completes, freezing the time."""
    drv, rpc, shell = _make_setup()
    rpc.send_get_state = lambda: None
    rpc.send_get_stats = lambda: None
    rpc.agent_started.emit()
    assert drv._round_timer.isActive() is True
    rpc.agent_finished.emit()
    assert drv._round_timer.isActive() is False


def test_round_timer_stops_on_failure():
    """The round timer must also stop when a turn fails (error path)."""
    drv, rpc, shell = _make_setup()
    rpc.send_get_state = lambda: None
    rpc.send_get_stats = lambda: None
    rpc.agent_started.emit()
    assert drv._round_timer.isActive() is True
    rpc.error_occurred.emit("boom")
    assert drv._round_timer.isActive() is False


def test_round_timer_resets_each_turn():
    """Each new turn resets the elapsed counter so the clock starts from 0."""
    drv, rpc, shell = _make_setup()
    rpc.send_get_state = lambda: None
    rpc.send_get_stats = lambda: None
    rpc.agent_started.emit()
    first = drv._round_elapsed.elapsed()
    rpc.agent_finished.emit()
    rpc.agent_started.emit()
    second = drv._round_elapsed.elapsed()
    # The second turn's elapsed should be near-zero (just started), definitely
    # not larger than the first turn's accumulated time.
    assert second <= first + 50  # 50ms tolerance for test timing
