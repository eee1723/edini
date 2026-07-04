"""Chat bubble widgets: UserBubble (right-aligned) + AiBubble (left-aligned).

AiBubble supports streaming (update_streaming/append_chunk) and finalize.
Includes style helpers, _ClickableCard for image thumbnails, and the
thumb-pixmap/truncate-name/open-image utilities used by UserBubble.

Pure relocation from edini/ui/agent_panel.py (Stage 1, Task 1.3).
Public names are ``UserBubble`` / ``AiBubble``; ``_UserBubble`` / ``_AiBubble``
are kept as backward-compat aliases for existing imports.
"""
import html
import os
import subprocess
import sys

from PySide6 import QtCore, QtGui, QtWidgets
from edini.ui.theme import fs
from edini.ui.components.markdown import _format_lite, _format_full


# ═══════════════════════════════════════════════════════════════════════
# Style helpers (unchanged)
# ═══════════════════════════════════════════════════════════════════════

def _user_bubble_bg() -> str:
    return '#1a3a5c'

def _ai_bubble_bg() -> str:
    return '#1a1a24'

def _user_bubble_style() -> str:
    return (
        f'color:#e5e5eb;font-size:{fs(12)};line-height:1.45;'
        f'padding:8px 14px;background:{_user_bubble_bg()};border-radius:8px;'
    )

def _ai_bubble_style() -> str:
    return (
        f'color:#e5e5eb;font-size:{fs(12)};line-height:1.45;'
        f'padding:8px 14px;background:{_ai_bubble_bg()};border-radius:8px;'
    )


# ═══════════════════════════════════════════════════════════════════════
# Timeline — QScrollArea + widget-based
# ═══════════════════════════════════════════════════════════════════════

class _ClickableCard(QtWidgets.QFrame):
    """A card that opens a file/image on click. Reliable mouse handling."""

    def __init__(self, open_path: str, tooltip: str = "", parent=None):
        super().__init__(parent)
        self._open_path = open_path
        self.setCursor(QtCore.Qt.PointingHandCursor)
        if tooltip:
            self.setToolTip(tooltip)

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            _open_image_file(self._open_path)
        super().mouseReleaseEvent(event)


class UserBubble(QtWidgets.QFrame):
    """Right-aligned user message bubble — text + optional image references."""
    def __init__(self, text: str, images: list[dict] | None = None, parent=None):
        super().__init__(parent)
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(2)

        # Text bubble (right-aligned with 48px left margin)
        text_frame = QtWidgets.QFrame()
        text_layout = QtWidgets.QHBoxLayout(text_frame)
        text_layout.setContentsMargins(48, 0, 0, 0)
        text_layout.setSpacing(0)

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
        self._label.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        text_layout.addWidget(self._label)
        outer.addWidget(text_frame)

        # Image references (if any) — clickable chips below text
        if images:
            self._add_image_refs(outer, images)
        else:
            pass

        self.setStyleSheet("QFrame { background: transparent; border: none; }")

    def _add_image_refs(self, outer: QtWidgets.QVBoxLayout, images: list[dict]):
        """Add clickable thumbnail previews below the text bubble."""
        img_frame = QtWidgets.QFrame()
        img_frame.setStyleSheet("QFrame { background: transparent; border: none; }")
        img_layout = QtWidgets.QHBoxLayout(img_frame)
        img_layout.setContentsMargins(54, 2, 8, 2)
        img_layout.setSpacing(6)
        img_layout.addStretch(1)

        for img_meta in images:
            filename = img_meta.get("filename", "image")
            size_kb = img_meta.get("size_bytes", 0) / 1024
            size_str = f"{size_kb:.0f}KB" if size_kb < 1024 else f"{size_kb/1024:.1f}MB"
            cache_path = img_meta.get("cache_path", "")
            b64_fallback = img_meta.get("_b64_pending", "")
            open_path = cache_path if cache_path and os.path.isfile(cache_path) else b64_fallback

            # Card container — QFrame for proper child widget rendering
            card = _ClickableCard(open_path, f"点击查看原图 — {filename} ({size_str})")
            card.setFixedSize(100, 90)
            card.setStyleSheet(f"""
                _ClickableCard {{
                    background: #0e0e15;
                    border: 1px solid #252540;
                    border-radius: 4px;
                }}
                _ClickableCard:hover {{
                    border-color: #4a4a6a;
                    background: #14141e;
                }}
            """)

            card_layout = QtWidgets.QVBoxLayout(card)
            card_layout.setContentsMargins(2, 2, 2, 0)
            card_layout.setSpacing(1)

            # Thumbnail image — use QLabel with pixmap scaled to fill
            thumb = QtWidgets.QLabel()
            thumb.setFixedSize(96, 68)
            thumb.setAlignment(QtCore.Qt.AlignCenter)
            thumb.setScaledContents(False)
            thumb.setStyleSheet(
                "QLabel { background: #06060c; border-radius: 2px; border: none; }"
            )
            pixmap = _load_thumb_pixmap(open_path)
            if pixmap and not pixmap.isNull():
                scaled = pixmap.scaled(
                    96, 68,
                    QtCore.Qt.AspectRatioMode.IgnoreAspectRatio,
                    QtCore.Qt.TransformationMode.SmoothTransformation,
                )
                thumb.setPixmap(scaled)
            else:
                thumb.setText("🖼️")
            card_layout.addWidget(thumb)

            # Filename label
            name_label = QtWidgets.QLabel(_truncate_name(filename, 13))
            name_label.setStyleSheet(
                f"QLabel {{ color:#a1a1aa; font-size:{fs(9)}; border:none; background:transparent; }}"
            )
            name_label.setAlignment(QtCore.Qt.AlignCenter)
            card_layout.addWidget(name_label)

            img_layout.addWidget(card)

        outer.addWidget(img_frame)


class AiBubble(QtWidgets.QFrame):
    """Left-aligned AI message bubble — fills available width with right margin."""
    def __init__(self, rich_html: str = "", parent=None):
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 48, 0)  # 48px right margin (left-aligned look)
        layout.setSpacing(0)

        self._label = QtWidgets.QLabel()
        self._label.setWordWrap(True)
        self._label.setTextFormat(QtCore.Qt.RichText)
        self._label.setOpenExternalLinks(False)
        self._label.setTextInteractionFlags(
            QtCore.Qt.TextSelectableByMouse
        )
        self._label.setStyleSheet(
            f"QLabel {{ "
            f"color:#e5e5eb; font-size:{fs(12)}; line-height:1.45; "
            f"padding:8px 14px; background:{_ai_bubble_bg()}; "
            f"border-radius:10px; border:none; "
            f"}}"
        )
        self._label.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        layout.addWidget(self._label)

        self._raw_text = ""
        if rich_html:
            wrapped = f'<div style="{_ai_bubble_style()}">{rich_html}</div>'
            self._label.setText(wrapped)

        self.setStyleSheet("QFrame { background: transparent; border: none; }")

    def update_streaming(self, full_text: str):
        """Update with full accumulated text during streaming. Uses light formatter."""
        self._raw_text = full_text
        rendered = _format_lite(full_text)
        wrapped = f'<div style="{_ai_bubble_style()}">{rendered}</div>'
        self._label.setText(wrapped)

    def get_raw_text(self) -> str:
        return self._raw_text

    def finalize(self):
        """Called when streaming is complete. Applies full Markdown formatting."""
        rendered = _format_full(self._raw_text)
        wrapped = f'<div style="{_ai_bubble_style()}">{rendered}</div>'
        self._label.setText(wrapped)

    def set_stored_content(self, content: str):
        """Set content from a stored message. Applies full Markdown formatting."""
        self._raw_text = content
        rendered = _format_full(content)
        wrapped = f'<div style="{_ai_bubble_style()}">{rendered}</div>'
        self._label.setText(wrapped)

    @staticmethod
    def _on_link(url: str):
        pass


# ═══════════════════════════════════════════════════════════════════════
# Helpers used by UserBubble image thumbnails (unchanged)
# ═══════════════════════════════════════════════════════════════════════

def _truncate_name(name: str, max_len: int) -> str:
    if len(name) <= max_len:
        return name
    return name[:max_len - 1] + "…"


def _load_thumb_pixmap(path_or_b64: str) -> QtGui.QPixmap | None:
    """Load a QPixmap from a file path or base64 string.

    Returns None on any failure (safe to call in Houdini's PySide6).
    """
    if not path_or_b64:
        return None
    try:
        pixmap = QtGui.QPixmap()
        if os.path.isfile(path_or_b64):
            pixmap.load(path_or_b64)
        else:
            import base64 as _b64
            data = _b64.b64decode(path_or_b64)
            pixmap.loadFromData(data)
        if pixmap.isNull():
            return None
        return pixmap
    except Exception:
        return None


def _open_image_file(path: str):
    """Open an image file in the OS default viewer.

    If path is not a valid file path, treats it as base64 data and
    writes to a temp file first.
    """
    if not path:
        return

    actual_path = path
    if not os.path.isfile(path):
        # Try to decode as base64 (fallback before cache is written)
        try:
            import base64 as _b64
            import tempfile
            data = _b64.b64decode(path)
            fd, tmp = tempfile.mkstemp(suffix=".jpg", prefix="edini_view_")
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            actual_path = tmp
        except Exception:
            return

    try:
        if sys.platform == "win32":
            os.startfile(actual_path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", actual_path])
        else:
            subprocess.Popen(["xdg-open", actual_path])
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════
# Backward-compat aliases (existing code imports _UserBubble / _AiBubble)
# ═══════════════════════════════════════════════════════════════════════
_UserBubble = UserBubble
_AiBubble = AiBubble
