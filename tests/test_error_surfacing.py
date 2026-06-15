"""Tests for model-error surfacing (no more silent failures).

Covers:
1. rpc_client._dispatch_event emits error_occurred on message_end with
   stopReason="error" (the event pi sends for 400 / insufficient quota / 429).
2. _merge_consecutive_assistants preserves errorMessage/stopReason so the UI
   can show why a failed turn produced no output.
"""
import sys
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# python3.11libs MUST come before ROOT: both contain an `edini` package, but
# only python3.11libs/edini has the ui/ subpackage (main_window, agent_panel).
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "python3.11libs"))

from tests.mock_hou import create_mock_hou  # noqa: E402
from unittest.mock import MagicMock  # noqa: E402

# Inject a mock hou so importing edini.ui.main_window doesn't require Houdini.
sys.modules["hou"] = create_mock_hou()


def test_dispatch_message_end_error_emits_error_occurred():
    from edini.rpc_client import _RpcWorker

    worker = _RpcWorker.__new__(_RpcWorker)  # bypass __init__ (no subprocess)
    captured = []
    worker.error_occurred = MagicMock()
    worker.error_occurred.emit = captured.append

    # pi emits this exact shape when a model call fails.
    worker._dispatch_event({
        "type": "message_end",
        "message": {
            "stopReason": "error",
            "errorMessage": "400 API 调用参数有误，请检查文档。",
        },
    })

    assert captured, "error_occurred was not emitted for a failed message_end"
    assert "400 API" in captured[0], f"unexpected error text: {captured[0]!r}"
    print("PASS: message_end with stopReason=error -> error_occurred emitted")


def test_dispatch_message_end_success_no_error():
    from edini.rpc_client import _RpcWorker

    worker = _RpcWorker.__new__(_RpcWorker)
    captured = []
    worker.error_occurred = MagicMock()
    worker.error_occurred.emit = captured.append

    # A normal completion must NOT raise an error.
    worker._dispatch_event({
        "type": "message_end",
        "message": {"stopReason": "stop", "content": "hello"},
    })

    assert not captured, f"unexpected error for successful turn: {captured}"
    print("PASS: message_end with stopReason=stop -> no error emitted")


def test_dispatch_message_end_missing_error_message_has_fallback():
    from edini.rpc_client import _RpcWorker

    worker = _RpcWorker.__new__(_RpcWorker)
    captured = []
    worker.error_occurred = MagicMock()
    worker.error_occurred.emit = captured.append

    # stopReason=error but no errorMessage text — must still surface something.
    worker._dispatch_event({
        "type": "message_end",
        "message": {"stopReason": "error"},
    })

    assert captured, "error_occurred should still fire even without errorMessage"
    print("PASS: message_end stopReason=error without message -> fallback text")


# ── _merge_consecutive_assistants lives on the MainWindow; test the logic
# in isolation without constructing a full Qt window. ──
def test_merge_preserves_error_message():
    """A failed assistant turn must keep its errorMessage through merge so
    history rendering can show it."""
    from edini.ui.main_window import EdiniMainWindow

    # Call the static-ish method on the class without instantiating.
    merge = EdiniMainWindow._merge_consecutive_assistants

    # __get__(None, cls) gives an unbound-style callable; but it's an instance
    # method, so pass a dummy self — it only uses `self` for nothing here.
    class _Dummy:
        _merge_consecutive_assistants = merge

    dummy = _Dummy()

    messages = [
        {"role": "user", "content": "做一个程序化自行车"},
        {
            "role": "assistant",
            "content": "",
            "stopReason": "error",
            "errorMessage": "余额不足或无可用资源包,请充值。",
        },
    ]
    merged = dummy._merge_consecutive_assistants(messages)

    assert len(merged) == 2, merged
    asst = merged[1]
    assert asst["role"] == "assistant"
    assert asst.get("stopReason") == "error", "stopReason lost in merge"
    assert asst.get("errorMessage") == "余额不足或无可用资源包,请充值。", \
        "errorMessage lost in merge"
    print("PASS: _merge_consecutive_assistants preserves stopReason/errorMessage")


def test_merge_normal_turn_has_no_error_flag():
    from edini.ui.main_window import EdiniMainWindow
    merge = EdiniMainWindow._merge_consecutive_assistants

    class _Dummy:
        _merge_consecutive_assistants = merge
    dummy = _Dummy()

    messages = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello there"},
    ]
    merged = dummy._merge_consecutive_assistants(messages)
    asst = merged[1]
    assert "stopReason" not in asst, "normal turn wrongly flagged as error"
    assert "errorMessage" not in asst
    print("PASS: normal assistant turn has no error flag after merge")


if __name__ == "__main__":
    test_dispatch_message_end_error_emits_error_occurred()
    test_dispatch_message_end_success_no_error()
    test_dispatch_message_end_missing_error_message_has_fallback()
    test_merge_preserves_error_message()
    test_merge_normal_turn_has_no_error_flag()
    print("\nAll error-surfacing tests passed.")
