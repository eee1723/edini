# Timeline Rendering & Selection — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade timeline Markdown rendering to full GPT-style formatting (headers, lists, tables), unify streaming/history display paths with dual formatter strategy, enable text selection, and tighten spacing.

**Architecture:** Single-file change to `python3.11libs/edini/ui/agent_panel.py`. Replace `_format_message()` with `_format_full()` (complete Markdown→HTML) and `_format_lite()` (streaming-safe light render). Hook `update_streaming()`→`_format_lite()`, `finalize()`/`set_stored_content()`→`_format_full()`. Add `TextSelectableByMouse` to all bubbles, switch `_UserBubble` to RichText, tighten line-height/padding.

**Tech Stack:** Python 3.11 + PySide6, `re`, `html`, `base64` (no new dependencies)

---

## File Structure

| File | Action | Purpose |
|------|--------|---------|
| `python3.11libs/edini/ui/agent_panel.py` | Modify | All rendering changes: formatter functions, bubble widgets |

---

### Task 1: Write `_format_lite()` — streaming-safe light formatter

**Files:**
- Modify: `python3.11libs/edini/ui/agent_panel.py` — append new function near `_format_message`

- [ ] **Step 1: Add `_format_lite()` function**

Insert immediately before the existing `_format_message` function (around line 1250):

```python
def _format_lite(text: str) -> str:
    """Lightweight streaming-safe formatter.

    Only applies inline formatting that works on incomplete text.
    Does NOT parse code blocks, lists, headers, or tables — incomplete
    versions of these would produce broken HTML.
    """
    out = html.escape(text)

    # **bold** (after escape, the ** are literal)
    out = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', out)

    # *italic* — but not **, and not * inside words
    out = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<i>\1</i>', out)

    # `inline code`
    out = re.sub(
        r'`([^`]+)`',
        r'<code style="background:#1a1a24;color:#67e8f9;padding:1px 4px;'
        r'border-radius:3px;font-family:monospace;font-size:11px;">\1</code>',
        out,
    )

    # newlines → <br>
    out = out.replace('\n', '<br>')

    return out
```

---

### Task 2: Rewrite `_format_message()` → `_format_full()` — complete Markdown parser

**Files:**
- Modify: `python3.11libs/edini/ui/agent_panel.py` — replace `_format_message` function

- [ ] **Step 1: Replace `_format_message()` with `_format_full()`**

Replace the entire `_format_message` function (around line 1228–1258) with:

```python
def _format_full(text: str) -> str:
    """Convert Markdown-ish text to rich HTML for final display."""
    esc = html.escape(text)

    # ── Step 1: Extract code blocks and protect with placeholders ──
    code_blocks: list[str] = []

    def _extract_code_block(m):
        lang = m.group(1)
        code = html.escape(m.group(2))
        encoded = base64.b64encode(m.group(2).encode('utf-8')).decode('ascii')
        idx = len(code_blocks)
        html_block = (
            '<div style="position:relative;margin:4px 0;">'
            f'<a href="edini:copy:{encoded}" '
            'style="position:absolute;right:4px;top:4px;background:#2a2a3c;'
            'color:#a1a1aa;text-decoration:none;border-radius:3px;padding:2px 8px;'
            f'font-size:{fs(10)};">'
            '📋 Copy</a>'
            '<pre style="background:#0e0e15;color:#d4d4d4;padding:8px 24px 8px 8px;'
            f'border-radius:4px;font-family:monospace;font-size:{fs(11)};'
            'overflow-x:auto;margin:0;"><code>' + code + '</code></pre>'
            '</div>'
        )
        code_blocks.append(html_block)
        return f'__CODE_BLOCK_{idx}__'

    esc = re.sub(r'```(\w*)\n(.*?)```', _extract_code_block, esc, flags=re.DOTALL)

    # ── Step 2: Split into paragraphs ──
    paragraphs = esc.split('\n\n')

    # ── Step 3: Classify and render each paragraph ──
    rendered: list[str] = []
    for para in paragraphs:
        if not para.strip():
            continue
        lines = para.strip().split('\n')

        # Header: # / ## / ###
        if len(lines) == 1:
            m = re.match(r'^(#{1,3})\s+(.+)$', lines[0])
            if m:
                level = len(m.group(1))
                size = {1: f'{fs(20)}', 2: f'{fs(17)}', 3: f'{fs(15)}'}[level]
                margin = {1: '10px 0 4px 0', 2: '8px 0 3px 0', 3: '6px 0 2px 0'}[level]
                rendered.append(
                    f'<h{level} style="font-size:{size};font-weight:600;'
                    f'color:#e5e5eb;margin:{margin};line-height:1.3;">'
                    f'{m.group(2)}</h{level}>'
                )
                continue

        # Horizontal rule: ---
        if len(lines) == 1 and re.match(r'^-{3,}$', lines[0].strip()):
            rendered.append(
                '<hr style="border:none;border-top:1px solid #2a2a3c;margin:6px 0;">'
            )
            continue

        # Unordered list: all lines start with - or *
        if all(re.match(r'^[\-\*]\s+', line) for line in lines):
            items = ''.join(
                f'<li style="margin:1px 0;line-height:1.45;">'
                f'{re.sub(r"^[\-\*]\s+", "", line)}</li>'
                for line in lines
            )
            rendered.append(
                f'<ul style="padding-left:20px;margin:2px 0;">{items}</ul>'
            )
            continue

        # Ordered list: all lines start with N.
        if all(re.match(r'^\d+\.\s+', line) for line in lines):
            items = ''.join(
                f'<li style="margin:1px 0;line-height:1.45;">'
                f'{re.sub(r"^\d+\.\s+", "", line)}</li>'
                for line in lines
            )
            rendered.append(
                f'<ol style="padding-left:20px;margin:2px 0;">{items}</ol>'
            )
            continue

        # Table: has | separators and a header-separator row
        if len(lines) >= 2 and all('|' in line for line in lines):
            # Detect separator row: must contain only | - : and spaces
            has_sep = any(
                re.match(r'^[\|\s\-\:]+$', line.strip()) for line in lines
            )
            if has_sep:
                # Split into header, separator, body
                sep_idx = None
                for i, line in enumerate(lines):
                    if re.match(r'^[\|\s\-\:]+$', line.strip()):
                        sep_idx = i
                        break
                if sep_idx is not None:
                    header_rows = lines[:sep_idx]
                    body_rows = lines[sep_idx + 1:]

                    def _build_table_rows(rows, cell_tag):
                        result = ''
                        for row in rows:
                            cells = row.strip().strip('|').split('|')
                            result += '<tr>'
                            for cell in cells:
                                result += (
                                    f'<{cell_tag} style="padding:2px 8px;text-align:left;'
                                    f'border:1px solid #2a2a3c;">{cell.strip()}</{cell_tag}>'
                                )
                            result += '</tr>'
                        return result

                    rendered.append(
                        '<table style="border-collapse:collapse;margin:4px 0;'
                        f'font-size:{fs(11)};width:100%;">'
                        f'<thead>{_build_table_rows(header_rows, "th")}</thead>'
                        f'<tbody>{_build_table_rows(body_rows, "td")}</tbody>'
                        '</table>'
                    )
                    continue

        # Nested list: indented sub-items (leading 2+ spaces before -, *, or digit.)
        # For simplicity, treat as normal paragraph if not all lines are list markers
        # (nested lists are rendered as paragraphs with per-line <br>)

        # Plain paragraph
        body = '\n'.join(lines)
        rendered.append(
            f'<p style="margin:2px 0;line-height:1.45;">{body}</p>'
        )

    out = ''.join(rendered)

    # ── Step 4: Inline formatting on the assembled HTML ──
    # (applied after block-level rendering so inline code inside lists works)

    # **bold**
    out = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', out)

    # *italic* — careful not to match ** or * inside words
    out = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<i>\1</i>', out)

    # `inline code` (but NOT inside <pre> blocks — the CODE_BLOCK placeholders are
    # already resolved to HTML, and inline code inside pre is already escaped)
    out = re.sub(
        r'`([^`]+)`',
        r'<code style="background:#1a1a24;color:#67e8f9;padding:1px 4px;'
        r'border-radius:3px;font-family:monospace;font-size:11px;">\1</code>',
        out,
    )

    # ── Step 5: Restore code block placeholders ──
    for i, block_html in enumerate(code_blocks):
        out = out.replace(f'__CODE_BLOCK_{i}__', block_html)

    # ── Step 6: Remaining single newlines → <br> ──
    out = out.replace('\n', '<br>')

    return out
```

---

### Task 3: Enable text selection on `_AiBubble`

**Files:**
- Modify: `python3.11libs/edini/ui/agent_panel.py` — `_AiBubble.__init__`

- [ ] **Step 1: Add selection flags to `_AiBubble._label`**

In `_AiBubble.__init__`, after `self._label.linkActivated.connect(self._on_link)`, add:

```python
        self._label.setTextInteractionFlags(
            QtCore.Qt.TextSelectableByMouse | QtCore.Qt.LinksAccessibleByMouse
        )
```

The exact location is after the line:
```python
        self._label.linkActivated.connect(self._on_link)
```
Add the two lines immediately after.

- [ ] **Step 2: Verify `_AiBubble` remains RichText**

`_AiBubble` already uses `Qt.RichText` — no change needed here.

---

### Task 4: Switch `_UserBubble` to RichText + add selection

**Files:**
- Modify: `python3.11libs/edini/ui/agent_panel.py` — `_UserBubble.__init__`

- [ ] **Step 1: Change `_UserBubble` to RichText with consistent styling**

Replace the `_UserBubble.__init__` label creation block. The current code:

```python
        self._label = QtWidgets.QLabel(html.escape(text))
        self._label.setWordWrap(True)
        self._label.setTextFormat(QtCore.Qt.PlainText)
        self._label.setStyleSheet(
            f"QLabel {{ "
            f"color:#e5e5eb; font-size:{fs(12)}; line-height:1.55; "
            f"padding:10px 16px; background:{_user_bubble_bg()}; "
            f"border-radius:10px; border:none; "
            f"}}"
        )
```

Change to:

```python
        self._label = QtWidgets.QLabel(html.escape(text))
        self._label.setWordWrap(True)
        self._label.setTextFormat(QtCore.Qt.RichText)
        self._label.setTextInteractionFlags(
            QtCore.Qt.TextSelectableByMouse
        )
        self._label.setStyleSheet(
            f"QLabel {{ "
            f"color:#e5e5eb; font-size:{fs(12)}; line-height:1.45; "
            f"padding:8px 14px; background:{_user_bubble_bg()}; "
            f"border-radius:10px; border:none; "
            f"}}"
        )
```

Note changes:
- `Qt.PlainText` → `Qt.RichText`
- Added `setTextInteractionFlags`
- `line-height:1.55` → `1.45`
- `padding:10px 16px` → `8px 14px`

---

### Task 5: Adjust `_AiBubble` spacing and layout styles

**Files:**
- Modify: `python3.11libs/edini/ui/agent_panel.py` — `_AiBubble.__init__`

- [ ] **Step 1: Tighten existing `_AiBubble` label styles**

Update the `_AiBubble._label` style sheet. Replace:

```python
        self._label.setStyleSheet(
            f"QLabel {{ "
            f"color:#e5e5eb; font-size:{fs(12)}; line-height:1.55; "
            f"padding:10px 16px; background:{_ai_bubble_bg()}; "
            f"border-radius:10px; border:none; "
            f"}}"
        )
```

With:

```python
        self._label.setStyleSheet(
            f"QLabel {{ "
            f"color:#e5e5eb; font-size:{fs(12)}; line-height:1.45; "
            f"padding:8px 14px; background:{_ai_bubble_bg()}; "
            f"border-radius:10px; border:none; "
            f"}}"
        )
```

Note changes:
- `line-height:1.55` → `1.45`
- `padding:10px 16px` → `8px 14px`

---

### Task 6: Wire `update_streaming()` to `_format_lite()`

**Files:**
- Modify: `python3.11libs/edini/ui/agent_panel.py` — `_AiBubble.update_streaming`

- [ ] **Step 1: Switch streaming rendering to light formatter**

In `_AiBubble.update_streaming`, replace:

```python
    def update_streaming(self, full_text: str):
        """Update with full accumulated text during streaming. Re-renders markdown."""
        self._raw_text = full_text
        rendered = _format_message(html.escape(full_text))
        wrapped = f'<div style="{_ai_bubble_style()}">{rendered}</div>'
        self._label.setText(wrapped)
```

With:

```python
    def update_streaming(self, full_text: str):
        """Update with full accumulated text during streaming. Uses light formatter."""
        self._raw_text = full_text
        rendered = _format_lite(full_text)
        wrapped = f'<div style="{_ai_bubble_style()}">{rendered}</div>'
        self._label.setText(wrapped)
```

Change: `_format_message(html.escape(full_text))` → `_format_lite(full_text)`
(`_format_lite` already calls `html.escape` internally.)

---

### Task 7: Wire `finalize()` and `set_stored_content()` to `_format_full()`

**Files:**
- Modify: `python3.11libs/edini/ui/agent_panel.py` — `_AiBubble.finalize` and `_AiBubble.set_stored_content`

- [ ] **Step 1: Switch `finalize()` to full formatter**

In `_AiBubble.finalize`, replace:

```python
    def finalize(self):
        """Called when streaming is complete."""
        rendered = _format_message(html.escape(self._raw_text))
        wrapped = f'<div style="{_ai_bubble_style()}">{rendered}</div>'
        self._label.setText(wrapped)
```

With:

```python
    def finalize(self):
        """Called when streaming is complete. Applies full Markdown formatting."""
        rendered = _format_full(self._raw_text)
        wrapped = f'<div style="{_ai_bubble_style()}">{rendered}</div>'
        self._label.setText(wrapped)
```

- [ ] **Step 2: Switch `set_stored_content()` to full formatter**

In `_AiBubble.set_stored_content`, replace:

```python
    def set_stored_content(self, content: str):
        """Set content from a stored message (already plain text, no streaming)."""
        self._raw_text = content
        rendered = _format_message(html.escape(content))
        wrapped = f'<div style="{_ai_bubble_style()}">{rendered}</div>'
        self._label.setText(wrapped)
```

With:

```python
    def set_stored_content(self, content: str):
        """Set content from a stored message. Applies full Markdown formatting."""
        self._raw_text = content
        rendered = _format_full(content)
        wrapped = f'<div style="{_ai_bubble_style()}">{rendered}</div>'
        self._label.setText(wrapped)
```

---

### Task 8: Remove old `_format_message()` and verify deduplication

**Files:**
- Modify: `python3.11libs/edini/ui/agent_panel.py`

- [ ] **Step 1: Delete the old `_format_message` function**

After confirming that all calls to `_format_message` have been replaced by either `_format_lite` or `_format_full`, delete the old `_format_message` function entirely.

- [ ] **Step 2: Search for any remaining references**

Run:
```bash
grep -n "_format_message\|_format_lite\|_format_full" F:/zz/Edini/python3.11libs/edini/ui/agent_panel.py
```

Expected: only `_format_lite` and `_format_full` appear; `_format_message` should be gone.

---

### Task 9: Manual visual verification

- [ ] **Step 1: Send a multi-format test prompt**

In Houdini Edini panel, send:
```
Please output the following formatting test:

# Header 1
## Header 2
### Header 3

This is **bold** and *italic* and `inline code`.

- Unordered item 1
- Unordered item 2

1. Ordered item 1
2. Ordered item 2

---

| Column A | Column B |
|----------|----------|
| Value 1  | Value 2  |
| Value 3  | Value 4  |

---

```python
def hello():
    print("world")
```

Thank you!
```

- [ ] **Step 2: Verify streaming appearance**

Observe during streaming: text should appear smoothly, no broken HTML or layout jumps. Code blocks may appear as raw ``` until completion (expected behavior with `_format_lite`).

- [ ] **Step 3: Verify final rendering**

After agent_end, verify:
- H1/H2/H3 headers render at distinct sizes with margins
- Bold and italic render correctly
- Inline code shows with dark background + cyan text
- Unordered list has bullet markers and indentation
- Ordered list has numbered markers
- Horizontal rule appears as a thin gray line
- Table renders with borders and cells
- Code block has dark background + 📋 Copy button

- [ ] **Step 4: Verify text selection**

- Drag-select text inside assistant bubbles → should highlight
- Right-click → Copy (or Ctrl+C) → paste elsewhere → text should match
- Click code block 📋 Copy button → paste → code should match
- Drag-select text inside user bubbles → should highlight and copyable

- [ ] **Step 5: Verify history consistency**

Switch to a historical session:
- Messages should render with the same formatting as freshly received messages
- No layout differences between history and live messages

- [ ] **Step 6: Verify spacing**

Visual check:
- Gap between user bubble and assistant bubble should feel comfortable but not loose
- Paragraphs within a single bubble should have small spacing (2px via `<p>` margin)
- Headers should have clear but not excessive separation from preceding text

---

### Task 10: Commit

- [ ] **Step 1: Stage and commit**

```bash
git add python3.11libs/edini/ui/agent_panel.py
git commit -m "feat: upgrade timeline rendering — full Markdown, text selection, tighter spacing"
```
