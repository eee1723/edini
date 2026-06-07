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
    """Generate a 120px-wide JPEG thumbnail from a base64 image.

    Uses QPixmap with safety try/except. Returns empty string on failure.
    Houdini PySide6 QPixmap segfaults are rare and usually only happen with
    certain GPU drivers. If crashes occur, this function can be disabled.
    """
    if not full_base64:
        return ""
    try:
        raw = base64.b64decode(full_base64)
        pixmap = QtGui.QPixmap()
        if not pixmap.loadFromData(raw):
            return ""
        if pixmap.isNull():
            return ""
        # Scale down aggressively to avoid memory issues
        scaled = pixmap.scaledToWidth(120, QtCore.Qt.TransformationMode.SmoothTransformation)
        if scaled.isNull():
            return ""
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".jpg", prefix="edini_thumb_")
        os.close(tmp_fd)
        scaled.save(tmp_path, "JPEG", 30)
        with open(tmp_path, "rb") as f:
            data = f.read()
        os.unlink(tmp_path)
        return base64.b64encode(data).decode("ascii") if data else ""
    except Exception:
        return ""


# ── Helpers ──

def _image_to_bytes(image, fmt: str = "PNG", quality: int = -1) -> bytes:
    """Convert a QImage or QPixmap to raw bytes.

    Saves to temp file then reads back. Format is auto-detected from
    file extension — no explicit format parameter needed, avoiding all
    PySide6 cross-version compatibility issues.
    """
    import tempfile
    ext = fmt.lower()
    suffix = f".{ext}" if ext in ("png", "jpg", "jpeg", "bmp", "webp") else ".png"
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=suffix, prefix="edini_img_")
    os.close(tmp_fd)
    try:
        # QImage.save(str) — Qt auto-detects format from file extension.
        # Passing format/quality as positional args causes ValueError on
        # some PySide6 builds (e.g. Houdini 20's bundled Qt).
        ok = image.save(tmp_path)
        if not ok:
            return b""
        with open(tmp_path, "rb") as f:
            return f.read()
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


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
    """Method 1: viewport.saveImage → BytesIO → base64.
    Works on Houdini 19.x; removed in Houdini 20.x."""
    try:
        # Houdini 20.x: saveImage moved to flipbookSettings or viewport
        # Try multiple API paths
        buf = io.BytesIO()
        if hasattr(vp, 'saveImage'):
            vp.saveImage(buf, "JPEG", width=1280, height=720)
        elif hasattr(vp, 'flipbookSettings'):
            # Houdini 20+: use flipbookSettings().saveImage()
            fb_settings = vp.flipbookSettings()
            if hasattr(fb_settings, 'saveImage'):
                fb_settings.saveImage(buf, "JPEG", width=1280, height=720)
            else:
                raise AttributeError("saveImage not available on flipbookSettings")
        else:
            raise AttributeError("saveImage not available")
        size = buf.tell()
        if size == 0:
            return None
        buf.seek(0)
        data = buf.getvalue()
        b64 = base64.b64encode(data).decode("ascii")
        return _make_media_item(
            b64, MediaSource.VIEWPORT, "viewport.jpg",
            mime_type="image/jpeg", size_bytes=len(data),
        )
    except Exception as e:
        return None


def _capture_framebuffer(vp) -> MediaItem | None:
    """Method 2: grabFrameBuffer → QImage → JPEG bytes → base64.
    Works on Houdini 19.x; removed in Houdini 20.x."""
    try:
        if not hasattr(vp, 'grabFrameBuffer'):
            return None
        fb = vp.grabFrameBuffer()
        if fb is None:
            return None
        img = fb.image()
        if img is None or img.isNull():
            return None
        data = _image_to_bytes(img, "JPEG", 85)
        if len(data) == 0:
            return None
        b64 = base64.b64encode(data).decode("ascii")
        return _make_media_item(
            b64, MediaSource.VIEWPORT, "viewport.jpg",
            mime_type="image/jpeg", size_bytes=len(data),
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return None


def _capture_flipbook(vp) -> MediaItem | None:
    """Method 3: flipbook single-frame render to temp file → read → delete."""
    tmp_path = None
    try:
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".jpg", prefix="edini_vp_")
        os.close(tmp_fd)

        settings = vp.flipbookSettings()
        settings.output(tmp_path)
        settings.frameRange([1.0, 1.0])             # single frame (list of doubles)
        settings.resolution((1280, 720))
        settings.useResolution(True)
        vp.flipbook(settings=settings, open_dialog=False)

        if not os.path.exists(tmp_path):
            return None

        file_size = os.path.getsize(tmp_path)
        b64, size = _read_file_base64(tmp_path)
        if size == 0:
            return None

        return _make_media_item(
            b64, MediaSource.VIEWPORT, "viewport.jpg",
            mime_type="image/jpeg", size_bytes=size,
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return None
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError as e:
                pass


def is_viewport_available() -> bool:
    """Check if a Scene Viewer is currently available."""
    return _find_scene_viewer() is not None


# ═══════════════════════════════════════════════════════════════════════
# File Selection, Clipboard, Drag-Drop
# ═══════════════════════════════════════════════════════════════════════


def from_files(paths: list[str]) -> list:
    """Read one or more image files from disk.

    Skips non-image extensions and files over MAX_SIZE_BYTES.
    Returns list of MediaItem (may be empty).
    """
    items: list = []
    for p in paths:
        if not os.path.isfile(p):
            continue
        ext = os.path.splitext(p)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            continue
        try:
            b64, size = _read_file_base64(p)
        except (OSError, PermissionError):
            continue
        if size == 0 or size > MAX_SIZE_BYTES:
            continue
        mime = _guess_mime(p)
        filename = os.path.basename(p)
        thumb = make_thumbnail(b64, mime)
        items.append(MediaItem(
            base64=b64, mime_type=mime, source=MediaSource.FILE_PICK,
            filename=filename, thumbnail=thumb, file_path=p,
            size_bytes=size,
        ))
    return items


def from_clipboard() -> MediaItem | None:
    """Read an image from the system clipboard.

    Returns MediaItem with source=CLIPBOARD, or None if no image on clipboard.
    Tries multiple approaches for Houdini compatibility:
    1. clipboard.image() — direct QImage (screenshot tools, paint programs)
    2. clipboard.mimeData() — HTML/image URLs (browsers, file explorers)
    """
    try:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is None:
            return None

        clipboard = app.clipboard()

        # ── Approach 1: clipboard.image() ──
        image = clipboard.image()
        if not image.isNull():
            data = _image_to_bytes(image, "PNG")
            if len(data) > 0:
                b64 = base64.b64encode(data).decode("ascii")
                item = _make_media_item(
                    b64, MediaSource.CLIPBOARD, "clipboard.png",
                    mime_type="image/png", size_bytes=len(data),
                )
                return item
        else:
            pass

        # ── Approach 2: mimeData — try all clipboard modes ──
        # Use integer mode values to avoid Houdini PySide6 enum compat issues
        # QClipboard::Mode: Clipboard=0, Selection=1, FindBuffer=2
        for mode_name, mode_val in [
            ("Clipboard", 0),
            ("Selection", 1),
            ("FindBuffer", 2),
        ]:
            try:
                mime = clipboard.mimeData(mode=mode_val)
                if mime is None:
                    continue


                if mime.hasImage():
                    img_data = mime.imageData()
                    if img_data is not None and not img_data.isNull():
                        data = _image_to_bytes(img_data, "PNG")
                        if len(data) > 0:
                            b64 = base64.b64encode(data).decode("ascii")
                            item = _make_media_item(
                                b64, MediaSource.CLIPBOARD, "clipboard.png",
                                mime_type="image/png", size_bytes=len(data),
                            )
                            return item

                # Try reading image URLs (e.g., from browser copy-image)
                if mime.hasUrls():
                    urls = mime.urls()
                    for url in urls:
                        local = url.toLocalFile()
                        if local and os.path.isfile(local):
                            ext = os.path.splitext(local)[1].lower()
                            if ext in ALLOWED_EXTENSIONS:
                                b64, size = _read_file_base64(local)
                                if size > 0 and size <= MAX_SIZE_BYTES:
                                    mime_type = _guess_mime(local)
                                    filename = os.path.basename(local)
                                    thumb = make_thumbnail(b64, mime_type)
                                    item = MediaItem(
                                        base64=b64, mime_type=mime_type, source=MediaSource.CLIPBOARD,
                                        filename=filename, thumbnail=thumb, file_path=local,
                                        size_bytes=size,
                                    )
                                    return item

                # Try reading raw image bytes from mimeData
                if mime.hasFormat("image/png"):
                    raw = mime.data("image/png")
                    if raw:
                        data = bytes(raw)
                        if len(data) > 0 and len(data) <= MAX_SIZE_BYTES:
                            b64 = base64.b64encode(data).decode("ascii")
                            thumb = make_thumbnail(b64, "image/png")
                            item = MediaItem(
                                base64=b64, mime_type="image/png", source=MediaSource.CLIPBOARD,
                                filename="clipboard.png", thumbnail=thumb,
                                size_bytes=len(data),
                            )
                            return item

                if mime.hasFormat("image/jpeg"):
                    raw = mime.data("image/jpeg")
                    if raw:
                        data = bytes(raw)
                        if len(data) > 0 and len(data) <= MAX_SIZE_BYTES:
                            b64 = base64.b64encode(data).decode("ascii")
                            thumb = make_thumbnail(b64, "image/jpeg")
                            item = MediaItem(
                                base64=b64, mime_type="image/jpeg", source=MediaSource.CLIPBOARD,
                                filename="clipboard.jpg", thumbnail=thumb,
                                size_bytes=len(data),
                            )
                            return item

            except Exception as e:

                pass
        return None
    except Exception as e:
        import traceback
        traceback.print_exc()
        return None


def clipboard_has_image() -> bool:
    """Check if the clipboard currently contains an image."""
    try:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is None:
            return False
        clipboard = app.clipboard()

        # Check direct image first (fast path)
        has_img = not clipboard.image().isNull()
        if has_img:
            return True

        # Check mimeData for image formats (e.g. browser copy)
        mime = clipboard.mimeData()
        has_img_mime = mime.hasImage()
        if has_img_mime:
            return True

        # Check for raw image data formats
        for fmt in ["image/png", "image/jpeg", "image/bmp", "image/gif", "image/webp"]:
            if mime.hasFormat(fmt):
                return True

        # Check for URLs pointing to local image files
        if mime.hasUrls():
            for url in mime.urls():
                local = url.toLocalFile()
                if local:
                    ext = os.path.splitext(local)[1].lower()
                    if ext in ALLOWED_EXTENSIONS:
                        return True

        return False
    except Exception as e:
        return False


def from_mime_data(mime_data) -> list:
    """Extract image files from a QMimeData (drag-drop event).

    Only processes file URLs that have image extensions.
    """
    paths: list[str] = []
    if mime_data.hasUrls():
        for url in mime_data.urls():
            local_path = url.toLocalFile()
            if local_path and os.path.isfile(local_path):
                paths.append(local_path)
    if not paths:
        return []
    return from_files(paths)


def mime_has_images(mime_data) -> bool:
    """Check if a QMimeData contains any image file URLs."""
    if not mime_data.hasUrls():
        return False
    for url in mime_data.urls():
        local_path = url.toLocalFile()
        if local_path:
            ext = os.path.splitext(local_path)[1].lower()
            if ext in ALLOWED_EXTENSIONS:
                return True
    return False
