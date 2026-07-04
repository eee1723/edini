"""Bubble widget behavior — verify extraction preserved behavior."""
import sys
sys.path.insert(0, "python3.11libs")
from tests.qt_helpers import qapp
from edini.ui.components.bubbles import UserBubble, AiBubble


def test_user_bubble_stores_text():
    b = UserBubble("hello world")
    assert "hello world" in b._label.text()


def test_aibubble_finalize_renders_markdown():
    b = AiBubble()
    b._raw_text = "**bold**"
    b.finalize()
    txt = b._label.text()
    # vendored mistune emits <b> not <strong> (verified in T0.2)
    assert "<b>bold</b>" in txt


def test_aibubble_update_streaming_uses_lite():
    b = AiBubble()
    b.update_streaming("**x**")
    assert b._raw_text == "**x**"
