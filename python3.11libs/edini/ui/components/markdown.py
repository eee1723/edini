"""Markdown rendering: dark-themed mistune renderer + lite/full formatters."""
import html
import mistune as _mistune
from mistune import HTMLRenderer as _HTMLRenderer

from edini.ui.theme import fs


class _DarkRenderer(_HTMLRenderer):
    """Custom HTML renderer that injects dark-theme inline styles."""

    # ── Block elements ──

    def heading(self, text, level, **attrs):
        sizes = {1: 20, 2: 17, 3: 15, 4: 14, 5: 13, 6: 12}
        margins = {1: '10px 0 4px 0', 2: '8px 0 3px 0', 3: '6px 0 2px 0',
                   4: '5px 0 2px 0', 5: '4px 0 2px 0', 6: '4px 0 2px 0'}
        sz = fs(sizes.get(level, 14))
        mg = margins.get(level, '4px 0 2px 0')
        return (
            f'<h{level} style="font-size:{sz};font-weight:600;'
            f'color:#e5e5eb;margin:{mg};line-height:1.3;">'
            f'{text}</h{level}>\n'
        )

    def paragraph(self, text):
        return f'<p style="margin:6px 0;line-height:1.45;">{text}</p>'

    def block_code(self, code, info=None, **attrs):
        esc = html.escape(code.rstrip('\n'))
        lang_cls = f' class="language-{info}"' if info else ''
        return (
            '<pre style="background:#0e0e15;color:#d4d4d4;padding:8px;'
            f'border-radius:4px;font-family:monospace;font-size:{fs(11)};'
            f'overflow-x:auto;margin:4px 0;"><code{lang_cls}>'
            f'{esc}</code></pre>\n'
        )

    def list(self, text, ordered, **attrs):
        tag = 'ol' if ordered else 'ul'
        return f'<{tag} style="padding-left:20px;margin:2px 0;">{text}</{tag}>\n'

    def list_item(self, text, **attrs):
        return f'<li style="margin:1px 0;line-height:1.45;">{text}</li>\n'

    def table(self, text):
        return (
            f'<table style="border-collapse:collapse;margin:4px 0;'
            f'font-size:{fs(11)};width:100%;">{text}</table>\n'
        )

    def table_head(self, text):
        return f'<thead>{text}</thead>'

    def table_body(self, text):
        return f'<tbody>{text}</tbody>'

    def table_row(self, text):
        return f'<tr>{text}</tr>'

    def table_cell(self, text, align=None, head=False):
        tag = 'th' if head else 'td'
        align_style = f'text-align:{align};' if align else 'text-align:left;'
        return (
            f'<{tag} style="padding:2px 8px;{align_style}'
            f'border:1px solid #2a2a3c;">{text}</{tag}>'
        )

    def thematic_break(self):
        return '<hr style="border:none;border-top:1px solid #2a2a3c;margin:6px 0;">\n'

    def block_quote(self, text):
        return (
            '<blockquote style="border-left:3px solid #3a3a4c;'
            f'margin:4px 0;padding:4px 12px;color:#a1a1aa;font-size:{fs(12)};">'
            f'{text}</blockquote>\n'
        )

    # ── Inline elements ──

    def codespan(self, text):
        esc = html.escape(text)
        return (
            '<code style="background:#1a1a24;color:#67e8f9;padding:1px 4px;'
            f'border-radius:3px;font-family:monospace;font-size:{fs(11)};">'
            f'{esc}</code>'
        )

    def link(self, text, url, title=None):
        return f'<a href="{url}" style="color:#60a5fa;text-decoration:none;">{text}</a>'

    def image(self, text, url, title=None):
        return (
            f'<img src="{url}" alt="{text}" style="max-width:100%;'
            f'border-radius:4px;margin:4px 0;"' +
            (f' title="{title}"' if title else '') +
            ' />'
        )

    def emphasis(self, text):
        return f'<i>{text}</i>'

    def strong(self, text):
        return f'<b>{text}</b>'

    def strikethrough(self, text):
        return f'<del style="color:#71717a;">{text}</del>'

    def linebreak(self):
        return '<br>'

    def softbreak(self):
        return '<br>'

    # Task list items (from task_lists plugin)
    def task_list_item(self, text, checked=False):
        inner = '\u2705 ' if checked else '\u2610 '
        return f'<li style="margin:1px 0;line-height:1.45;">{inner}{text}</li>\n'


# ── Singleton parser instance ──

_md_parser = _mistune.create_markdown(
    renderer=_DarkRenderer(),
    escape=True,
    hard_wrap=True,
    plugins=['table', 'strikethrough', 'task_lists'],
)


def _format_lite(text: str) -> str:
    """Streaming formatter — identical output to _format_full.

    Uses the same mistune parser so streaming and finalized display are
    pixel-identical at every chunk boundary.
    """
    try:
        return _format_full(text)
    except Exception:
        # If mistune fails, fall back to inline formatting
        return _format_inline_fallback(text)


def _format_full(text: str) -> str:
    """Convert Markdown to rich HTML with dark-theme inline styles.

    Full GFM support via mistune: headers, bold, italic, inline code,
    code blocks, ordered/unordered lists, task lists, tables, links,
    images, strikethrough, blockquotes, horizontal rules.
    """
    return _md_parser(text)

def _format_inline_fallback(text: str) -> str:
    """Fallback: lightweight inline formatter if mistune fails."""
    import html as _html
    out = _html.escape(text)
    out = out.replace('\n', '<br>')
    return out
