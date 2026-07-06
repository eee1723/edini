"""ThinkingPanel + ToolPanel extracted classes.

These tests lock the behavior of the panels promoted out of
AgentPanel._build_ui() in Stage 2, Task 1.4. The visible behavior
(toggle, auto-expand, reset, paragraph counting, live cursor) must be
IDENTICAL to the original inline implementation.
"""
from tests.qt_helpers import qapp
from edini.ui.components.thinking_panel import ThinkingPanel
from edini.ui.components.tool_panel import ToolPanel


# ── ThinkingPanel ──

def test_thinking_panel_starts_collapsed():
    p = ThinkingPanel()
    assert p.is_expanded() is False


def test_thinking_panel_append_increments_count():
    p = ThinkingPanel()
    p.append("thinking chunk")
    # Real format uses paragraph counting: "▸ Thinking (1 ¶)".
    # Assert the count token "(1" rather than "(1)" because of the "¶" suffix.
    assert "(1" in p.toggle_text()


def test_thinking_panel_append_two_paragraphs():
    p = ThinkingPanel()
    p.append("first paragraph")
    p.append("second paragraph")
    # Two finalized paragraphs -> "(2 ¶)"
    assert "(2" in p.toggle_text()


def test_thinking_panel_toggle_changes_expanded():
    p = ThinkingPanel()
    assert p.is_expanded() is False
    p.toggle()
    assert p.is_expanded() is True
    p.toggle()
    assert p.is_expanded() is False


def test_thinking_panel_reset():
    p = ThinkingPanel()
    p.append("a")
    p.append("b")
    p.reset()
    assert "(0)" in p.toggle_text()
    assert p.is_expanded() is False


def test_thinking_panel_clear_keeps_expand_state():
    """_clear_thinking() clears content but does NOT collapse the panel."""
    p = ThinkingPanel()
    p.toggle()              # expand
    assert p.is_expanded() is True
    p.append("a")
    p.clear()
    assert "(0)" in p.toggle_text()
    assert p.is_expanded() is True   # expand state preserved
    assert p.has_content() is False


def test_thinking_panel_render_live_shows_cursor():
    """Live preview appends a blinking cursor to the buffered text."""
    p = ThinkingPanel()
    p.render_live("partial thought")
    html = p.view_html()
    assert "partial thought" in html
    assert "▊" in html   # live cursor


def test_thinking_panel_collapse_and_auto_expand():
    p = ThinkingPanel()
    assert p.is_expanded() is False
    p.auto_expand()
    assert p.is_expanded() is True
    p.collapse()
    assert p.is_expanded() is False
    # collapse when already collapsed is a no-op
    p.collapse()
    assert p.is_expanded() is False


# ── ToolPanel ──

def test_tool_panel_starts_empty():
    p = ToolPanel()
    assert p.card_count() == 0
    assert p.is_expanded() is False


def test_tool_panel_add_card():
    p = ToolPanel()
    p.add_card("build_node", "call_1", {"path": "/obj/x"})
    assert p.card_count() == 1
    assert "(1)" in p.toggle_text()


def test_tool_panel_add_card_auto_expands_on_first():
    p = ToolPanel()
    p.add_card("build_node", "call_1", {})
    assert p.is_expanded() is True  # auto-expand on first card


def test_tool_panel_update_result():
    p = ToolPanel()
    p.add_card("build_node", "call_1", {})
    p.update_result("call_1", "done", True)  # should not crash


def test_tool_panel_clear():
    p = ToolPanel()
    p.add_card("x", "c1", {})
    p.add_card("y", "c2", {})
    p.clear()
    assert p.card_count() == 0
    assert "(0)" in p.toggle_text()
