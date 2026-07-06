"""InputBar — message input + send button."""
from tests.qt_helpers import qapp, SignalSpy
from edini.ui.components.input_bar import InputBar


def test_input_bar_text_methods():
    bar = InputBar()
    assert bar.text() == ""
    bar.set_text("hello")
    assert bar.text() == "hello"
    bar.clear()
    assert bar.text() == ""


def test_input_bar_submit_emits_signal():
    bar = InputBar()
    spy = SignalSpy(bar.submit_requested)
    bar.set_text("test message")
    bar.submit()
    assert len(spy) == 1
    assert spy.calls[0][0] == "test message"  # first arg = text


def test_input_bar_empty_submit_does_not_emit():
    bar = InputBar()
    spy = SignalSpy(bar.submit_requested)
    bar.submit()
    assert len(spy) == 0


def test_input_bar_busy_state():
    bar = InputBar()
    assert bar.is_busy() is False
    bar.set_busy(True)
    assert bar.is_busy() is True
    bar.set_busy(False)
    assert bar.is_busy() is False
