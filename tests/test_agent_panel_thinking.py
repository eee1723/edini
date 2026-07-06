"""AgentPanel.add_thinking_step — token-level streaming regression tests.

Bug context: the main-panel thinking path used to insert a separator space
between every thinking_delta, assuming word-level deltas. Pi actually streams
token-level (Chinese per-char, English per sub-word), so this corrupted text:
  "需"+"要"+"我"  →  "需 要 我"  (BUG: extra spaces)
It also stored finalized paragraphs only in AgentPanel._stream_segments,
never pinning them into the ThinkingPanel via append() — so render_live()
showed only the in-progress tail, and once the buffer flushed the reasoning
appeared to "wipe" (BUG: content not retained).

These tests lock the fix: plain concatenation (no separator) + paragraphs
pinned into the ThinkingPanel via append().
"""
from tests.qt_helpers import qapp
from edini.ui.agent_panel import AgentPanel


def _feed_tokens(panel, tokens):
    for t in tokens:
        panel.add_thinking_step(0, t)


def test_chinese_tokens_concatenate_without_spaces():
    """Regression: per-character Chinese deltas must NOT gain spaces.

    Before fix: '需'+'要'+'我' → '需 要 我'. After fix: '需要我'.
    """
    p = AgentPanel()
    _feed_tokens(p, ["需", "要", "我", "进", "一", "步", "查", "看"])
    assert p._thinking_buf == "需要我进一步查看"


def test_english_subword_tokens_concatenate_without_spaces():
    """Regression: English sub-word deltas must NOT gain spaces.

    Before fix: 'cop'+'yt'+'op'+'oints' → 'cop yt op oints'.
    """
    p = AgentPanel()
    _feed_tokens(p, ["cop", "yt", "op", "oints"])
    assert p._thinking_buf == "copytopoints"


def test_paragraph_break_pins_into_thinking_panel():
    """Regression: a \\n\\n must finalize the paragraph into the ThinkingPanel.

    Before fix, AgentPanel stored paragraphs only in its own _stream_segments
    list, never calling panel.append(), so the ThinkingPanel's _thinking_full
    stayed empty and render_live() showed nothing retained.
    """
    p = AgentPanel()
    _feed_tokens(p, ["first paragraph", "\n\n", "second"])
    # The ThinkingPanel itself should now hold one finalized paragraph.
    assert p._thinking_panel.has_content() is True
    assert "(1" in p._thinking_panel.toggle_text()
    # The tail ("second") remains buffered (not yet finalized).
    assert "second" in p._thinking_buf


def test_flush_finalizes_tail_into_panel():
    """Regression: flushing the buffer (e.g. when text arrives) must pin the
    tail paragraph into the ThinkingPanel so it doesn't vanish."""
    p = AgentPanel()
    _feed_tokens(p, ["some reasoning"])
    # Buffered, not yet pinned.
    assert p._thinking_panel.has_content() is False
    p._flush_thinking_buf()
    # Now pinned.
    assert p._thinking_panel.has_content() is True
    assert "(1" in p._thinking_panel.toggle_text()
    assert p._thinking_buf == ""


def test_multiple_paragraphs_all_pinned():
    """Multiple \\n\\n breaks finalize multiple paragraphs into the panel."""
    p = AgentPanel()
    _feed_tokens(p, ["para one\n\npara two\n\npara three"])
    assert "(2" in p._thinking_panel.toggle_text()  # 2 finalized, tail buffered
    # Tail is the third paragraph.
    assert "para three" in p._thinking_buf


def test_empty_chunk_is_noop():
    """A truly empty delta must be skipped; whitespace-only deltas are
    concatenated verbatim (token-level streaming preserves original spacing)."""
    p = AgentPanel()
    _feed_tokens(p, ["", "   ", "\n"])
    # Whitespace tokens concatenate verbatim (no corruption) — only "" is skipped.
    assert p._thinking_buf == "   \n"
    # No finalized paragraphs, nothing pinned into the panel.
    assert p._thinking_panel.has_content() is False
