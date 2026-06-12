"""Streaming-specific markdown renderer regressions."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python3.11libs"))

from edini.ui.agent_panel import _format_full, _format_lite


def test_streaming_layout_is_same_as_final_renderer():
    final = "## Summary\n\nHere is some **bold** text\nMore text\n\n- item 1\n- item 2\n\nDone."
    chunks = [
        "##",
        "## Summary",
        "## Summary\n\n",
        "## Summary\n\nHere is",
        "## Summary\n\nHere is some **bold** text",
        "## Summary\n\nHere is some **bold** text\nMore text",
        "## Summary\n\nHere is some **bold** text\nMore text\n\n",
        "## Summary\n\nHere is some **bold** text\nMore text\n\n- item 1",
        "## Summary\n\nHere is some **bold** text\nMore text\n\n- item 1\n- item 2",
        final,
    ]

    for chunk in chunks:
        assert _format_lite(chunk) == _format_full(chunk)


def test_streaming_single_item_list_is_stable():
    html = _format_lite("- item 1")

    assert "<ul" in html
    assert "<li" in html


def test_streaming_header_is_stable():
    html = _format_lite("## Title")

    assert "<h2" in html


def test_streaming_preserves_unclosed_code_block():
    html = _format_lite("```python\nprint(")

    assert "<pre" in html
    assert "print(" in html


def test_streaming_complex_message():
    html = _format_lite("""## Changes Made

### File: `agent_panel.py`

- Fixed **double HTML escaping** in code blocks
- Added *link* support
- Improved math expression handling: `5 * 3`

```python
def format_md(text):
    return html.escape(text)
```

| Feature | Status |
| --- | --- |
| Headers | Done |
| Lists | Done |

---

End of message.""")

    assert "<h2" in html
    assert "<h3" in html
    assert "<ul" in html
    assert "<pre" in html
    assert "<table" in html
    assert "<hr" in html
    assert "<b>" in html
    assert "<i>" in html
    assert "<code" in html
