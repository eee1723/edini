"""ThinkingPanel live render throttle — coalesced onto _thinking_render_timer.

Regression (2026-07-09): add_thinking_step called _update_live_thinking() (→
ThinkingPanel.render_live) on EVERY thinking token. render_live does a full
QTextEdit setHtml reflow of the ENTIRE accumulated thinking — O(N) per token,
O(K²) over a long high-thinking stream. With glm-class models emitting
thousands of thinking tokens per turn, this monopolized the Houdini main
thread and froze the UI for the whole (often minutes-long) thinking stream.

The text bubble was already coalesced (_stream_flush_timer, 2026-07-08); the
thinking path was not. The fix mirrors it: add_thinking_step only arms a
singleShot _thinking_render_timer; render_live happens in _update_live_thinking
on the timer cadence (~8/sec), not once per token. These tests lock that.
"""
from tests.qt_helpers import qapp
from edini.ui.agent_panel import AgentPanel


def test_thinking_tokens_coalesce_not_per_token_render():
    """Per-token thinking chunks must NOT call render_live — only buffer + arm
    the timer. Before the fix, N tokens → N full QTextEdit reflows."""
    p = AgentPanel()
    calls = []
    p._thinking_panel.render_live = lambda buf: calls.append(buf)

    # Emit many thinking tokens, as a high-thinking model does.
    for i in range(30):
        p.add_thinking_step(i, f"tok{i} ")

    # Buffered, but NOT eagerly rendered per token…
    assert len(calls) == 0, f"render_live called {len(calls)}× per-token (must defer)"
    # …and the coalescing timer is armed (renders on the next event-loop tick).
    assert p._thinking_render_timer.isActive() is True

    # The timer callback is what renders — once, with the full accumulated buf.
    p._update_live_thinking()
    assert len(calls) == 1
    assert "tok0" in calls[0] and "tok29" in calls[0]


def test_thinking_render_interval_is_coarse():
    """The interval must be coarse enough to give the main thread headroom over
    a long stream (not per-token / not tiny). 120ms ≈ 8 renders/sec."""
    assert AgentPanel.THINKING_RENDER_INTERVAL_MS >= 100


def test_begin_assistant_message_clears_accumulated_thinking():
    """Regression (2026-07-09 progressive-freeze): a single user request spans
    many tool-call turns, and begin_assistant_message fires PER turn. The
    ThinkingPanel's _thinking_full used to persist across all of them —
    render_live/append reflow the entire _thinking_full each render, so it grew
    unbounded over a session (observed 60K+ chars) and every reflow got slower
    → Houdini UI froze progressively worse. Each turn must start with an empty
    panel (the prior turn's thinking is already pinned into its timeline bubble
    by finish_streaming)."""
    p = AgentPanel()
    for i in range(10):
        p.add_thinking_step(i, f"reasoning {i} ")
    p.finish_streaming()
    assert p._thinking_panel._thinking_full != ""   # accumulated during the turn

    p.begin_assistant_message()                      # next turn begins
    assert p._thinking_panel._thinking_full == ""    # panel cleared, not carried
    assert p._thinking_buf == ""


def test_finish_streaming_stops_thinking_timer_and_flushes():
    """finish_streaming must stop the coalescing timer (no late reflow) and
    finalize the buffered thinking into the panel so it isn't lost when the
    timer is stopped mid-stream."""
    p = AgentPanel()
    for i in range(5):
        p.add_thinking_step(i, f"step{i} ")
    assert p._thinking_render_timer.isActive() is True   # armed during stream

    p.finish_streaming()
    # Timer stopped — no further deferred renders can fire.
    assert p._thinking_render_timer.isActive() is False
    # The buffered thinking was finalized into the panel's persistent store
    # (via _flush_thinking_buf → _append_thinking_text → panel.append).
    assert "step0" in p._thinking_panel._thinking_full
    assert "step4" in p._thinking_panel._thinking_full


def test_render_live_caps_large_thinking():
    """A huge thinking turn must NOT reflow the whole document. render_live
    caps to a bounded tail so each QTextEdit.setHtml stays cheap even at
    multi-thousand chars (without the cap, every throttled render froze
    Houdini's main thread during a long thinking stream)."""
    p = AgentPanel()
    big = "a reasoning line of thought\n" * 1000   # ~28K chars, well over cap
    p._thinking_panel.render_live(big)
    rendered = p._thinking_panel._view.toPlainText()
    assert len(rendered) < 3500                      # capped, NOT ~28K
    assert "折叠" in rendered or "完整内容" in rendered   # cap marker visible


def test_append_keeps_full_store_but_renders_capped():
    """append must keep _thinking_full COMPLETE (source of truth → timeline)
    but only RENDER a bounded tail, so finalizing many paragraphs doesn't
    reflow an ever-growing document."""
    p = AgentPanel()
    for _ in range(400):
        p._thinking_panel.append("paragraph of reasoning " * 10)  # ~28K total
    assert len(p._thinking_panel._thinking_full) > 20000   # full store preserved
    rendered = p._thinking_panel._view.toPlainText()
    assert len(rendered) < 4000                              # render is capped
