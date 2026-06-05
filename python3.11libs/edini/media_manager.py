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


# ═══════════════════════════════════════════════════════════════════════
# Viewport Capture — three-tier fallback
# ═══════════════════════════════════════════════════════════════════════


def capture_viewport() -> MediaItem | None:
    """Capture the Houdini Scene Viewer as a JPEG screenshot.

    Tries three approaches in order:
    1. saveImage — direct viewport JPEG export (needs Commercial license)
    2. grabFrameBuffer — grab framebuffer pixels → QImage → JPEG
    3. flipbook single frame — render single frame to temp file → read → delete

    Returns MediaItem with source=VIEWPORT, or None if all methods fail.
    """
    if hou is None:
        return None

    vp = _find_scene_viewer()
    if vp is None:
        return None

    # ── Method 1: saveImage ──
    result = _capture_save_image(vp)
    if result is not None:
        return result

    # ── Method 2: grabFrameBuffer ──
    result = _capture_framebuffer(vp)
    if result is not None:
        return result

    # ── Method 3: flipbook single frame ──
    result = _capture_flipbook(vp)
    if result is not None:
        return result

    return None


def _find_scene_viewer():
    """Find the current Scene Viewer pane tab."""
    try:
        desktop = hou.ui.curDesktop()
        return desktop.paneTabOfType(hou.paneTabType.SceneViewer)
    except Exception:
        return None


def _capture_save_image(vp) -> MediaItem | None:
    """Method 1: viewport.saveImage → BytesIO → base64."""
    try:
        buf = io.BytesIO()
        vp.saveImage(buf, "JPEG", width=1280, height=720)
        if buf.tell() == 0:
            return None
        buf.seek(0)
        data = buf.getvalue()
        b64 = base64.b64encode(data).decode("ascii")
        return _make_media_item(
            b64, MediaSource.VIEWPORT, "viewport.jpg",
            mime_type="image/jpeg", size_bytes=len(data),
        )
    except Exception:
        return None


def _capture_framebuffer(vp) -> MediaItem | None:
    """Method 2: grabFrameBuffer → QImage → JPEG bytes → base64."""
    try:
        fb = vp.grabFrameBuffer()
        if fb is None:
            return None
        img = fb.image()
        if img is None or img.isNull():
            return None
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=85)
        data = buf.getvalue()
        if len(data) == 0:
            return None
        b64 = base64.b64encode(data).decode("ascii")
        return _make_media_item(
            b64, MediaSource.VIEWPORT, "viewport.jpg",
            mime_type="image/jpeg", size_bytes=len(data),
        )
    except Exception:
        return None


def _capture_flipbook(vp) -> MediaItem | None:
    """Method 3: flipbook single-frame render to temp file → read → delete."""
    tmp_path = None
    try:
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".jpg", prefix="edini_vp_")
        os.close(tmp_fd)

        settings = vp.flipbookSettings()
        settings.output(tmp_path)
        settings.frameRange(1, 1)             # single frame
        settings.resolution((1280, 720))
        settings.useResolution(True)
        vp.flipbook(settings=settings, open_dialog=False)

        if not os.path.exists(tmp_path):
            return None

        b64, size = _read_file_base64(tmp_path)
        if size == 0:
            return None

        return _make_media_item(
            b64, MediaSource.VIEWPORT, "viewport.jpg",
            mime_type="image/jpeg", size_bytes=size,
        )
    except Exception:
        return None
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def is_viewport_available() -> bool:
    """Check if a Scene Viewer is currently available."""
    return _find_scene_viewer() is not None
