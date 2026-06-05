"""Media manager — unified image input handling for Edini.

Captures images from viewport, file pick, clipboard, and drag-drop.
Normalizes everything to MediaItem for the attachment bar and RPC transport.
"""
import io
import os
import base64
import tempfile
from dataclasses import dataclass, field
from enum import Enum

from PySide6 import QtCore, QtGui
from PySide6.QtCore import Qt

try:
    import hou
except Exception:
    hou = None

# ── Data types ──

class MediaSource(Enum):
    VIEWPORT = "viewport"
    DRAG_DROP = "drag"
    CLIPBOARD = "paste"
    FILE_PICK = "pick"
    TOOL = "tool"


@dataclass
class MediaItem:
    base64: str
    mime_type: str          # "image/jpeg" | "image/png" | ...
    source: MediaSource
    filename: str
    thumbnail: str | None = None   # 120px-wide JPEG base64, q=30
    file_path: str | None = None
    size_bytes: int = 0


# ── Validation ──

MAX_SIZE_BYTES = 5 * 1024 * 1024       # 5 MB
MAX_ATTACHMENTS = 5

ALLOWED_MIME = {"image/jpeg", "image/jpg", "image/png", "image/gif",
                "image/webp", "image/bmp"}

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}

_MIME_MAP = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".png": "image/png",   ".gif": "image/gif",
    ".webp": "image/webp", ".bmp": "image/bmp",
}


def validate(item: MediaItem) -> tuple[bool, str]:
    """Check a MediaItem is valid for sending. Returns (ok, reason)."""
    if not item.base64 or not item.base64.strip():
        return False, "Empty image data"
    if item.size_bytes > MAX_SIZE_BYTES:
        size_mb = item.size_bytes / (1024 * 1024)
        return False, f"Image too large: {size_mb:.1f} MB (max 5 MB)"
    if item.mime_type not in ALLOWED_MIME:
        return False, f"Unsupported format: {item.mime_type}"
    return True, ""


# ── Thumbnail ──

def make_thumbnail(full_base64: str, mime_type: str = "image/jpeg") -> str:
    """Generate a 120px-wide JPEG thumbnail (quality 30) from a base64 image.

    Returns base64 string (no data: prefix).
    """
    try:
        raw = base64.b64decode(full_base64)
        img = QtGui.QImage()
        if not img.loadFromData(raw):
            return ""
        scaled = img.scaledToWidth(120, Qt.SmoothTransformation)
        buf = io.BytesIO()
        scaled.save(buf, "JPEG", quality=30)
        return base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        return ""


# ── Helpers ──

def _guess_mime(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    return _MIME_MAP.get(ext, "image/png")


def _read_file_base64(path: str) -> tuple[str, int]:
    """Read a file and return (base64, size_bytes)."""
    with open(path, "rb") as f:
        data = f.read()
    return base64.b64encode(data).decode("ascii"), len(data)


def _make_media_item(
    b64: str, source: MediaSource, filename: str,
    mime_type: str = "image/jpeg", file_path: str | None = None,
    size_bytes: int | None = None,
) -> MediaItem:
    if size_bytes is None:
        size_bytes = len(base64.b64decode(b64))
    thumb = make_thumbnail(b64, mime_type)
    return MediaItem(
        base64=b64, mime_type=mime_type, source=source,
        filename=filename, thumbnail=thumb, file_path=file_path,
        size_bytes=size_bytes,
    )
