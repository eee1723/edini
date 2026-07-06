"""AiBubble streaming state machine — plain text during stream, markdown on finalize."""
from tests.qt_helpers import qapp
from edini.ui.components.bubbles import AiBubble


def test_append_chunk_accumulates_plain_text():
    b = AiBubble()
    b.append_chunk("hello ")
    b.append_chunk("world")
    assert b._raw_text == "hello world"


def test_append_chunk_is_plain_text_no_html():
    """During streaming, label is PlainText (no HTML parsing)."""
    b = AiBubble()
    b.append_chunk("**bold**")
    # The literal text "**bold**" should appear; NOT rendered as <b>
    txt = b._label.text()
    assert "**bold**" in txt
    assert "<b>" not in txt


def test_finalize_renders_markdown_once():
    b = AiBubble()
    b.append_chunk("**bold**")
    # during streaming, no <b>
    assert "<b>" not in b._label.text()
    b.finalize()
    # after finalize, mistune renders <b>bold</b>
    assert "<b>bold</b>" in b._label.text()


def test_finalize_switches_to_rich_text():
    b = AiBubble()
    b.append_chunk("x")
    b.finalize()
    assert b._streaming is False


def test_legacy_update_streaming_still_works():
    """Backward-compat: old update_streaming(full_text) API still functions."""
    b = AiBubble()
    b.update_streaming("partial **x**")
    assert b._raw_text == "partial **x**"


def test_get_raw_text():
    b = AiBubble()
    b.append_chunk("abc")
    assert b.get_raw_text() == "abc"


def test_set_stored_content_renders_full():
    """History messages: set_stored_content renders full markdown immediately."""
    b = AiBubble()
    b.set_stored_content("**done**")
    assert "<b>done</b>" in b._label.text()


def test_constructed_with_rich_html_is_complete():
    """AiBubble(rich_html=...) starts in completed (non-streaming) state."""
    b = AiBubble(rich_html="<p>history</p>")
    assert b._streaming is False
