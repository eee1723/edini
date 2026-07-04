"""ChatRuntime signal-adapter baseline."""
import sys
sys.path.insert(0, "python3.11libs")

from PySide6 import QtCore
from tests.qt_helpers import qapp, SignalSpy

from edini.ui.chat_runtime import ChatRuntime


class _FakeRpc(QtCore.QObject):
    """Minimal stand-in exposing only the signals ChatRuntime binds to."""
    text_delta = QtCore.Signal(str)
    thinking_delta = QtCore.Signal(str)
    tool_call = QtCore.Signal(str, str, object)
    tool_result = QtCore.Signal(str, str, str)
    agent_started = QtCore.Signal()
    agent_finished = QtCore.Signal()
    error_occurred = QtCore.Signal(str)
    stats_updated = QtCore.Signal(object)


def test_text_delta_becomes_stream_chunk():
    rpc = _FakeRpc()
    rt = ChatRuntime(rpc)
    spy = SignalSpy(rt.stream_chunk)
    rpc.text_delta.emit("hello")
    assert spy.calls == ["hello"]


def test_agent_started_emits_started_and_busy_true():
    rpc = _FakeRpc()
    rt = ChatRuntime(rpc)
    started_spy = SignalSpy(rt.started)
    busy_spy = SignalSpy(rt.busy_changed)
    rpc.agent_started.emit()
    assert len(started_spy) == 1
    assert busy_spy.calls == [True]


def test_agent_finished_emits_completed_and_busy_false():
    rpc = _FakeRpc()
    rt = ChatRuntime(rpc)
    completed_spy = SignalSpy(rt.completed)
    busy_spy = SignalSpy(rt.busy_changed)
    rpc.agent_finished.emit()
    assert len(completed_spy) == 1
    assert busy_spy.calls == [False]


def test_stats_passthrough():
    rpc = _FakeRpc()
    rt = ChatRuntime(rpc)
    spy = SignalSpy(rt.stats_updated)
    rpc.stats_updated.emit({"tokens": {"total": 100}})
    assert spy.calls == [{"tokens": {"total": 100}}]
