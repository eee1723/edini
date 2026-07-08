"""AgentPanel streaming render throttle — coalesced onto _stream_flush_timer.

Regression (2026-07-08): append_stream_chunk called bubble.update_streaming(
full_text) on EVERY token, re-laying-out the entire growing QLabel text each
time (O(N) per chunk). With the agent firing graph-mutating tools on the same
Houdini main thread, an open chat panel monopolized it → severe UI lag. The
_stream_flush_timer + _flush_stream throttle already existed but was DEAD CODE
(_flush_stream was a no-op "in widget mode"). The fix reactivated it:
append_stream_chunk only buffers + arms a singleShot timer; QLabel.setText
happens in _flush_stream, ~12 renders/sec instead of one per token. These
tests lock that contract.
"""
from tests.qt_helpers import qapp
from edini.ui.agent_panel import AgentPanel


def test_chunks_buffer_without_eager_render():
    """Per-token chunks must NOT render into the bubble — only buffer + arm the
    timer. Before the fix the bubble's _raw_text mirrored the full stream after
    every chunk (a full QLabel relayout per token)."""
    p = AgentPanel()
    for t in ["hel", "lo ", "wor", "ld"]:
        p.append_stream_chunk(t)
    # All text is buffered in the panel...
    assert p._streaming_full_text == "hello world"
    # ...the bubble exists but has NOT been rendered into yet (deferred)...
    assert p._streaming_bubble is not None
    assert p._streaming_bubble._raw_text == ""
    # ...and the coalescing timer is armed (renders on the next event-loop tick).
    assert p._stream_flush_timer.isActive() is True


def test_flush_stream_renders_the_buffer():
    """_flush_stream (the timer callback) is what actually writes the bubble."""
    p = AgentPanel()
    for t in ["hel", "lo ", "wor", "ld"]:
        p.append_stream_chunk(t)
    p._flush_stream()
    assert p._streaming_bubble._raw_text == "hello world"


def test_finish_streaming_does_not_lose_buffered_tail():
    """A fast final burst can leave text buffered when finish_streaming fires
    (timer stopped, never ticked). finish_streaming must flush once before the
    one-shot markdown finalize — which reads bubble._raw_text — or that tail
    vanishes from the rendered output."""
    p = AgentPanel()
    for t in ["hel", "lo ", "wor", "ld"]:
        p.append_stream_chunk(t)
    # Spy on the bubble's finalize to capture _raw_text at finalize time
    # (finish_streaming destroys the bubble right after).
    bubble = p._streaming_bubble
    captured = {}
    orig_finalize = bubble.finalize

    def spy():
        captured["raw"] = bubble._raw_text
        orig_finalize()

    bubble.finalize = spy
    p.finish_streaming()
    assert captured["raw"] == "hello world"
