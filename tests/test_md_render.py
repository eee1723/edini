"""Regression tests for the production markdown renderer."""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python3.11libs"))

from edini.ui.agent_panel import _format_full, _format_lite


def test_renders_common_markdown_blocks():
    html = _format_full("""## Changes Made

### File: `agent_panel.py`

- Fixed **double HTML escaping** in code blocks
- Added [link](https://example.com) support
- Improved math expression handling: `5 * 3`

```python
def format_md(text):
    return html.escape(text)
```

| Feature | Status |
| --- | --- |
| Headers | Done |
| Lists | Done |

> This is a blockquote with **bold**.

---

End of message.""")

    assert "<h2" in html
    assert "<h3" in html
    assert "<ul" in html
    assert "<pre" in html
    assert "<table" in html
    assert "<blockquote" in html
    assert "<hr" in html
    assert '<a href="https://example.com"' in html
    assert "<b>double HTML escaping</b>" in html
    assert "def format_md" in html


def test_escapes_code_blocks_once():
    html = _format_full("```\n<div>& value\n```")

    assert "&lt;div&gt;&amp; value" in html
    assert "&amp;lt;div&amp;gt;" not in html


def test_math_stars_do_not_trigger_italic():
    html = _format_full("5 * 3 * 2 = 30")

    assert "<i>" not in html


def test_task_lists_render_state_symbols():
    html = _format_full("- [ ] todo\n- [x] done")

    assert "\u2610" in html
    assert "\u2705" in html


def test_unclosed_code_block_renders_as_code():
    html = _format_full("```python\nprint(")

    assert "<pre" in html
    assert "print(" in html


def test_lite_matches_full_for_streaming_chunks():
    chunks = [
        "##",
        "## Summary",
        "## Summary\n\nHere is some **bold** text",
        "## Summary\n\nHere is some **bold** text\n\n- item 1",
        "## Summary\n\nHere is some **bold** text\n\n- item 1\n- item 2",
    ]

    for chunk in chunks:
        assert _format_lite(chunk) == _format_full(chunk)


def test_lite_rendering_has_no_debug_file_side_effect(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setenv("TEMP", tmp)
        _format_lite("Hello **world**")

        assert not (Path(tmp) / "edini_md_debug.log").exists()
