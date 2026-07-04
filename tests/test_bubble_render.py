"""Baseline snapshot: _AiBubble markdown rendering behavior.

Locks the contract so the Stage-1 bubble merge cannot silently change
rendering. Tests the format functions directly (no QApplication needed
for pure string functions).
"""
import sys
sys.path.insert(0, "python3.11libs")

from edini.ui.agent_panel import _format_full, _format_lite


def test_format_full_renders_code_block():
    out = _format_full("```python\nprint('hi')\n```")
    assert "<code" in out or "<pre" in out
    assert "print" in out


def test_format_full_renders_bold():
    # The vendored mistune renderer emits <b>, not <strong>.
    out = _format_full("**bold**")
    assert "<b>bold</b>" in out


def test_format_lite_does_not_crash_on_complex_input():
    # lite is a degraded renderer; just assert it returns a string
    out = _format_lite("# title\n- item\n```code\n```")
    assert isinstance(out, str)
    assert len(out) > 0


def test_format_full_handles_empty():
    assert isinstance(_format_full(""), str)


def test_format_full_handles_plain_text():
    out = _format_full("just plain text")
    assert "just plain text" in out
