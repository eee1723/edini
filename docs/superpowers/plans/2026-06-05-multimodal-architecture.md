# 多模态架构实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Edini's complete multimodal pipeline — screenshot/drag/paste/file-pick → Qwen-VL visual description → DeepSeek reasoning, with attachment preview bar and VisionDescriptionBubble in the timeline.

**Architecture:** Three new Python modules (media_manager, image_attachment, vision_overlay) plus modifications to pi-visionizer (TypeScript) and agent_panel (Python). Images are captured/selected via MediaManager, previewed in ImageAttachmentWidget, sent to Pi via existing RPC, intercepted by pi-visionizer which proxies to Qwen-VL and notifies Edini via extension_ui_request + custom entry.

**Tech Stack:** Python 3.11 (PySide6, hou, dataclasses), TypeScript (pi-visionizer), JSON-RPC

**Spec:** `docs/superpowers/specs/2026-06-05-multimodal-architecture-design.md`

---

### Task 1: media_manager.py — MediaItem dataclass + validate + thumbnail

**Files:**
- Create: `python3.11libs/edini/media_manager.py`

- [ ] **Step 1: Create media_manager.py with MediaItem, MediaSource, validate, and thumbnail generator**

```python
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
```

- [ ] **Step 2: Verify the module imports cleanly**

```bash
cd F:/zz/Edini && python -c "from edini.media_manager import MediaItem, MediaSource, validate, make_thumbnail; print('OK')"
```
Expected output: `OK`

- [ ] **Step 3: Commit**

```bash
git add python3.11libs/edini/media_manager.py
git commit -m "feat(media): add MediaManager — MediaItem, validate, thumbnail helpers"
```

---

### Task 2: media_manager.py — capture_viewport (three-tier fallback)

**Files:**
- Modify: `python3.11libs/edini/media_manager.py` — append at end

- [ ] **Step 1: Add capture_viewport with three-tier fallback**

Append this code after the `_make_media_item` function:

```python
# ── Viewport Capture ──

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
```

- [ ] **Step 2: Verify the module still imports with new code**

```bash
cd F:/zz/Edini && python -c "from edini.media_manager import capture_viewport, is_viewport_available; print('capture_viewport imported OK')"
```
Expected output: `capture_viewport imported OK`

- [ ] **Step 3: Commit**

```bash
git add python3.11libs/edini/media_manager.py
git commit -m "feat(media): add capture_viewport with three-tier fallback (saveImage→framebuffer→flipbook)"
```

---

### Task 3: media_manager.py — from_files, from_clipboard, from_drop

**Files:**
- Modify: `python3.11libs/edini/media_manager.py` — append at end (before validation section ideally, but can append at end)

- [ ] **Step 1: Add file pick, clipboard, and drag-drop input methods**

Append after the `is_viewport_available` function:

```python
# ── File Selection ──

def from_files(paths: list[str]) -> list[MediaItem]:
    """Read one or more image files from disk.

    Skips non-image extensions and files over MAX_SIZE_BYTES.
    Returns list of MediaItem (may be empty).
    """
    items: list[MediaItem] = []
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


# ── Clipboard ──

def from_clipboard() -> MediaItem | None:
    """Read an image from the system clipboard.

    Returns MediaItem with source=CLIPBOARD, or None if no image on clipboard.
    """
    try:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is None:
            return None
        clipboard = app.clipboard()
        image = clipboard.image()
        if image.isNull():
            return None
        buf = io.BytesIO()
        image.save(buf, "PNG")
        data = buf.getvalue()
        if len(data) == 0:
            return None
        b64 = base64.b64encode(data).decode("ascii")
        return _make_media_item(
            b64, MediaSource.CLIPBOARD, "clipboard.png",
            mime_type="image/png", size_bytes=len(data),
        )
    except Exception:
        return None


def clipboard_has_image() -> bool:
    """Check if the clipboard currently contains an image."""
    try:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is None:
            return False
        return not app.clipboard().image().isNull()
    except Exception:
        return False


# ── Drag-Drop ──

def from_mime_data(mime_data: QtCore.QMimeData) -> list[MediaItem]:
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


def mime_has_images(mime_data: QtCore.QMimeData) -> bool:
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
```

- [ ] **Step 2: Verify imports**

```bash
cd F:/zz/Edini && python -c "from edini.media_manager import from_files, from_clipboard, from_mime_data, mime_has_images; print('all input methods imported OK')"
```
Expected output: `all input methods imported OK`

- [ ] **Step 3: Commit**

```bash
git add python3.11libs/edini/media_manager.py
git commit -m "feat(media): add from_files, from_clipboard, from_mime_data input methods"
```

---

### Task 4: image_attachment.py — ImageAttachmentWidget

**Files:**
- Create: `python3.11libs/edini/ui/image_attachment.py`

- [ ] **Step 1: Create ImageAttachmentWidget with thumbnail cards**

```python
"""Image attachment preview bar for agent panel input area.

Shows up to 5 thumbnail cards above the text input when images are added
via screenshot, file pick, clipboard paste, or drag-drop.
"""
from __future__ import annotations

import base64
from typing import Callable

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt

from edini.media_manager import MediaItem, MediaSource, MAX_ATTACHMENTS
from edini.ui.theme import fs

# Source icon per MediaSource
_SOURCE_ICONS = {
    MediaSource.VIEWPORT: "📸",
    MediaSource.DRAG_DROP: "📁",
    MediaSource.CLIPBOARD: "📋",
    MediaSource.FILE_PICK: "📁",
    MediaSource.TOOL: "🔧",
}


class _AttachmentCard(QtWidgets.QFrame):
    """Single image attachment card: thumbnail + filename + source icon + remove button."""

    removed = QtCore.Signal(int)  # index

    THUMB_W = 120
    THUMB_H = 68
    CARD_W = 136

    def __init__(self, item: MediaItem, index: int, parent=None):
        super().__init__(parent)
        self._index = index
        self.setFixedWidth(self.CARD_W)
        self.setStyleSheet(f"""
            _AttachmentCard {{
                background: #141420;
                border: 1px solid #252540;
                border-radius: 4px;
            }}
        """)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 2)
        layout.setSpacing(2)

        # Thumbnail
        thumb_label = QtWidgets.QLabel()
        thumb_label.setFixedSize(self.THUMB_W, self.THUMB_H)
        thumb_label.setAlignment(Qt.AlignCenter)
        thumb_label.setStyleSheet(
            "QLabel { background: #0a0a14; border-radius: 2px; border: none; }"
        )
        if item.thumbnail:
            pixmap = _base64_to_pixmap(item.thumbnail)
            if pixmap:
                scaled = pixmap.scaled(
                    self.THUMB_W, self.THUMB_H,
                    Qt.KeepAspectRatio, Qt.SmoothTransformation,
                )
                thumb_label.setPixmap(scaled)
        else:
            thumb_label.setText("🖼️")
        layout.addWidget(thumb_label)

        # Info row: source icon + filename
        info_row = QtWidgets.QHBoxLayout()
        info_row.setSpacing(2)
        source_icon = _SOURCE_ICONS.get(item.source, "📁")
        icon_label = QtWidgets.QLabel(source_icon)
        icon_label.setStyleSheet(
            f"QLabel {{ color:#71717a; font-size:{fs(9)}; border:none; }}"
        )
        icon_label.setFixedWidth(16)
        info_row.addWidget(icon_label)

        name_label = QtWidgets.QLabel(_truncate_name(item.filename, 14))
        name_label.setStyleSheet(
            f"QLabel {{ color:#a1a1aa; font-size:{fs(10)}; border:none; }}"
        )
        info_row.addWidget(name_label, 1)
        layout.addLayout(info_row)

        # Remove button (overlayed in top-right)
        remove_btn = QtWidgets.QPushButton("✕")
        remove_btn.setFixedSize(18, 18)
        remove_btn.setCursor(Qt.PointingHandCursor)
        remove_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(0,0,0,0.6);
                color: #a1a1aa;
                border: none;
                border-radius: 9px;
                font-size: {fs(9)};
            }}
            QPushButton:hover {{
                background: #ef4444;
                color: #fff;
            }}
        """)
        remove_btn.clicked.connect(lambda: self.removed.emit(self._index))
        # Float the remove button
        remove_btn.setParent(self)
        remove_btn.move(self.CARD_W - 20, 2)

    def update_index(self, new_index: int):
        self._index = new_index


def _base64_to_pixmap(b64: str) -> QtGui.QPixmap | None:
    try:
        data = base64.b64decode(b64)
        pixmap = QtGui.QPixmap()
        pixmap.loadFromData(data)
        return pixmap if not pixmap.isNull() else None
    except Exception:
        return None


def _truncate_name(name: str, max_len: int) -> str:
    if len(name) <= max_len:
        return name
    return name[:max_len - 1] + "…"


class ImageAttachmentWidget(QtWidgets.QWidget):
    """Horizontal bar of image attachment cards above the text input.

    Signals:
        attachments_changed() — emitted when items are added or removed
    """

    attachments_changed = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: list[MediaItem] = []
        self._cards: list[_AttachmentCard] = []

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignLeft)
        self.setFixedHeight(104)
        self.setVisible(False)

        self.setStyleSheet(
            "ImageAttachmentWidget { background: transparent; border: none; }"
        )

    def items(self) -> list[MediaItem]:
        return list(self._items)

    def count(self) -> int:
        return len(self._items)

    def is_full(self) -> bool:
        return len(self._items) >= MAX_ATTACHMENTS

    def add(self, item: MediaItem) -> bool:
        """Add a MediaItem. Returns True if added, False if rejected (full/invalid)."""
        from edini.media_manager import validate
        ok, _ = validate(item)
        if not ok:
            return False
        if self.is_full():
            return False
        self._items.append(item)
        self._rebuild_cards()
        self.setVisible(True)
        self.attachments_changed.emit()
        return True

    def remove(self, index: int):
        if 0 <= index < len(self._items):
            self._items.pop(index)
            self._rebuild_cards()
            if not self._items:
                self.setVisible(False)
            self.attachments_changed.emit()

    def clear(self):
        self._items.clear()
        self._rebuild_cards()
        self.setVisible(False)
        self.attachments_changed.emit()

    def _rebuild_cards(self):
        # Remove all existing cards
        for card in self._cards:
            self.layout().removeWidget(card)
            card.deleteLater()
        self._cards.clear()

        # Rebuild
        for i, item in enumerate(self._items):
            card = _AttachmentCard(item, i, self)
            card.removed.connect(self.remove)
            self._cards.append(card)
            self.layout().addWidget(card)
```

- [ ] **Step 2: Verify the widget can be instantiated**

```bash
cd F:/zz/Edini && python -c "
from PySide6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])
from edini.ui.image_attachment import ImageAttachmentWidget
w = ImageAttachmentWidget()
print(f'Created ImageAttachmentWidget, count={w.count()}, visible={w.isVisible()}')
"
```
Expected output: `Created ImageAttachmentWidget, count=0, visible=False`

- [ ] **Step 3: Commit**

```bash
git add python3.11libs/edini/ui/image_attachment.py
git commit -m "feat(ui): add ImageAttachmentWidget — thumbnail preview bar for attachments"
```

---

### Task 5: vision_overlay.py — VisionDescriptionBubble

**Files:**
- Create: `python3.11libs/edini/ui/vision_overlay.py`

- [ ] **Step 1: Create VisionDescriptionBubble**

```python
"""Vision description bubble — rendered in the chat timeline when pi-visionizer
describes images before the main model processes them.
"""
from __future__ import annotations

import base64
import io
import tempfile
import os
import subprocess
import sys
from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt

from edini.ui.theme import fs


class VisionDescriptionBubble(QtWidgets.QFrame):
    """Collapsible bubble showing vision model's image description.

    Rendered in the timeline after a user message with images,
    before the AI's main response.
    """

    def __init__(
        self,
        descriptions: list[dict[str, Any]],
        parent=None,
    ):
        """
        Args:
            descriptions: list of dicts with keys:
                mimeType, description, model, elapsedMs
        """
        super().__init__(parent)
        self._descriptions = descriptions
        self._expanded = True
        self._image_base64: str | None = None   # for "view original" feature

        self.setStyleSheet("""
            VisionDescriptionBubble {
                background: rgba(167,139,250,0.06);
                border: 1px solid rgba(167,139,250,0.15);
                border-radius: 6px;
            }
        """)

        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(10, 6, 10, 6)
        self._layout.setSpacing(4)

        self._build_header()
        self._build_content()

    def _build_header(self):
        header_row = QtWidgets.QHBoxLayout()
        header_row.setSpacing(6)

        model_name = self._descriptions[0].get("model", "vision-model") if self._descriptions else "vision"
        total_ms = sum(d.get("elapsedMs", 0) for d in self._descriptions)
        elapsed_str = f"{total_ms / 1000:.1f}s" if total_ms > 0 else ""

        parts = ["👁️ 图片描述"]
        if model_name:
            parts.append(f"· {model_name}")
        if elapsed_str:
            parts.append(f"· {elapsed_str}")

        self._header_label = QtWidgets.QLabel(" ".join(parts))
        self._header_label.setStyleSheet(
            f"QLabel {{ color:#a78bfa; font-size:{fs(11)}; font-weight:600; border:none; }}"
        )
        header_row.addWidget(self._header_label, 1)

        self._toggle_btn = QtWidgets.QPushButton("▲ 收起")
        self._toggle_btn.setCursor(Qt.PointingHandCursor)
        self._toggle_btn.setFixedHeight(20)
        self._toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(167,139,250,0.12);
                color: #a78bfa;
                border: none;
                border-radius: 3px;
                padding: 0px 6px;
                font-size: {fs(10)};
            }}
            QPushButton:hover {{
                background: rgba(167,139,250,0.22);
            }}
        """)
        self._toggle_btn.clicked.connect(self._toggle)
        header_row.addWidget(self._toggle_btn)

        self._layout.addLayout(header_row)

    def _build_content(self):
        """Build the description text area."""
        self._content_widget = QtWidgets.QWidget()
        content_layout = QtWidgets.QVBoxLayout(self._content_widget)
        content_layout.setContentsMargins(4, 2, 4, 2)
        content_layout.setSpacing(6)

        for d in self._descriptions:
            desc_text = d.get("description", "")
            if not desc_text:
                continue

            label = QtWidgets.QLabel(desc_text)
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            label.setStyleSheet(
                f"QLabel {{ color:#c4b5fd; font-size:{fs(11)}; line-height:1.5; "
                f"border:none; background:transparent; }}"
            )
            content_layout.addWidget(label)

        # "View original" link
        view_btn = QtWidgets.QPushButton("📸 查看原图")
        view_btn.setCursor(Qt.PointingHandCursor)
        view_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: #71717a;
                border: none;
                font-size: {fs(10)};
                text-align: left;
                padding: 0;
            }}
            QPushButton:hover {{
                color: #a78bfa;
            }}
        """)
        view_btn.clicked.connect(self._on_view_original)
        content_layout.addWidget(view_btn)

        self._layout.addWidget(self._content_widget)

    def _toggle(self):
        self._expanded = not self._expanded
        self._content_widget.setVisible(self._expanded)
        if self._expanded:
            self._toggle_btn.setText("▲ 收起")
        else:
            self._toggle_btn.setText("▼ 展开")

    def _on_view_original(self):
        """Open the original image in the OS default viewer via a temp file."""
        if not self._image_base64:
            return
        try:
            mime_type = self._descriptions[0].get("mimeType", "image/jpeg") if self._descriptions else "image/jpeg"
            ext = _mime_to_ext(mime_type)
            tmp_fd, tmp_path = tempfile.mkstemp(suffix=ext, prefix="edini_view_")
            with os.fdopen(tmp_fd, "wb") as f:
                f.write(base64.b64decode(self._image_base64))
            # Open with default viewer (cross-platform)
            if sys.platform == "win32":
                os.startfile(tmp_path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", tmp_path])
            else:
                subprocess.Popen(["xdg-open", tmp_path])
        except Exception:
            pass

    def set_original_image(self, base64_data: str):
        """Provide the original image data for 'view original' feature."""
        self._image_base64 = base64_data

    @staticmethod
    def create_from_notification(
        descriptions: list[dict[str, Any]],
        image_base64: str | None = None,
    ) -> "VisionDescriptionBubble":
        """Factory: create a bubble from the vision_description notification data."""
        bubble = VisionDescriptionBubble(descriptions)
        if image_base64:
            bubble.set_original_image(image_base64)
        return bubble

    @staticmethod
    def create_error_bubble(error_msg: str) -> "VisionDescriptionBubble":
        """Factory: create a bubble showing a vision model error."""
        bubble = VisionDescriptionBubble([{
            "description": error_msg,
            "model": "vision-error",
            "elapsedMs": 0,
        }])
        bubble.setStyleSheet("""
            VisionDescriptionBubble {
                background: rgba(239,68,68,0.06);
                border: 1px solid rgba(239,68,68,0.2);
                border-radius: 6px;
            }
        """)
        bubble._header_label.setStyleSheet(
            f"QLabel {{ color:#f87171; font-size:{fs(11)}; font-weight:600; border:none; }}"
        )
        return bubble


def _mime_to_ext(mime: str) -> str:
    m = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "image/bmp": ".bmp",
    }
    return m.get(mime, ".jpg")
```

- [ ] **Step 2: Verify the widget can be instantiated**

```bash
cd F:/zz/Edini && python -c "
from PySide6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])
from edini.ui.vision_overlay import VisionDescriptionBubble
b = VisionDescriptionBubble.create_from_notification([
    {'description': 'A smoke simulation with low density and blue color.', 'model': 'qwen-vl-max', 'elapsedMs': 2300, 'mimeType': 'image/jpeg'}
])
print(f'Created VisionDescriptionBubble, expanded={b._expanded}')
"
```
Expected output: `Created VisionDescriptionBubble, expanded=True`

- [ ] **Step 3: Commit**

```bash
git add python3.11libs/edini/ui/vision_overlay.py
git commit -m "feat(ui): add VisionDescriptionBubble — collapsible vision description in timeline"
```

---

### Task 6: rpc_client.py — vision_description signal

**Files:**
- Modify: `python3.11libs/edini/rpc_client.py`

- [ ] **Step 1: Add vision_description signal and dispatch logic**

**Edit 1**: Add the new signal to RpcClient class (after existing `extension_info` signal):

```python
    extension_info = Signal(str)            # info/warning from pi extensions (tools loaded, etc.)
    vision_description = Signal(object)     # vision model descriptions from pi-visionizer
```

**Edit 2**: Wire it in `start()` method — after `self._worker.extension_info.connect(self.extension_info)`, add:

```python
        self._worker.extension_info.connect(self.extension_info)
        self._worker.vision_description.connect(self.vision_description)
```

**Edit 3**: Add the signal to `_RpcWorker` class (after `extension_info`):

```python
    extension_info = Signal(str)            # info/warning from pi extensions (tools loaded, etc.)
    vision_description = Signal(object)      # vision model descriptions from pi-visionizer
```

**Edit 4**: Add dispatch logic in `_dispatch_event` — modify the `extension_ui_request` handler:

Old code:
```python
        elif event_type == "extension_ui_request":
            if event.get("method") == "notify":
                notify_type = event.get("notifyType", "info")
                message = event.get("message", "")
                if notify_type == "error":
                    self.error_occurred.emit(f"[{notify_type}] {message}")
                else:
                    self.extension_info.emit(message)
```

New code:
```python
        elif event_type == "extension_ui_request":
            if event.get("method") == "notify":
                notify_type = event.get("notifyType", "info")
                message = event.get("message", "")
                # Check for vision_description payload
                try:
                    payload = json.loads(message)
                    if isinstance(payload, dict) and payload.get("event") == "vision_description":
                        self.vision_description.emit(payload.get("descriptions", []))
                        return
                except (json.JSONDecodeError, TypeError):
                    pass
                if notify_type == "error":
                    self.error_occurred.emit(f"[{notify_type}] {message}")
                else:
                    self.extension_info.emit(message)
```

- [ ] **Step 2: Verify the module imports**

```bash
cd F:/zz/Edini && python -c "from edini.rpc_client import RpcClient; c=RpcClient(); print('vision_description' in dir(c))"
```
Expected output: `True`

- [ ] **Step 3: Commit**

```bash
git add python3.11libs/edini/rpc_client.py
git commit -m "feat(rpc): add vision_description signal for pi-visionizer notifications"
```

---

### Task 7: pi-visionizer — default model to aliyun/qwen-vl-max

**Files:**
- Modify: `pi-extensions/pi-visionizer/src/config.ts`

- [ ] **Step 1: Change hardcoded default vision model**

Old code:
```typescript
export const DEFAULT_VISION_MODEL: VisionizerConfig = {
  provider: "google",
  modelId: "gemini-3.1-flash-lite",
};
```

New code:
```typescript
export const DEFAULT_VISION_MODEL: VisionizerConfig = {
  provider: "aliyun",
  modelId: "qwen-vl-max",
};
```

- [ ] **Step 2: Verify the file reads correctly**

```bash
cd F:/zz/Edini && node -e "console.log(require('./pi-extensions/pi-visionizer/src/config.ts'))" 2>&1 || echo "(TypeScript file — check manually)"
```
Note: TypeScript won't `require()` directly. Just verify the text change is correct by reading the file.

- [ ] **Step 3: Commit**

```bash
git add pi-extensions/pi-visionizer/src/config.ts
git commit -m "feat(visionizer): change default vision model from google/gemini to aliyun/qwen-vl-max"
```

---

### Task 8: pi-visionizer — context hook writes custom entry + notifies Edini

**Files:**
- Modify: `pi-extensions/pi-visionizer/src/index.ts`

- [ ] **Step 1: Add custom entry write + extension_ui_request notification in context hook**

Locate the context hook (pi.on("context", ...)). In the `processMessages` call and the return statement area, replace with this enhanced version:

In the context hook, after the `processMessages` call returns the processed messages, add the notification logic. The key section to modify is inside the pi.on("context", ...) handler, right before `return { messages: processed }`:

Old code (the processMessages call and return):
```typescript
      const processed = await processMessages(
        event.messages,
        visionModel,
        auth.apiKey,
        prompt,
        requireHttps,
      );

      return { messages: processed };
```

New code (add description tracking and notification):
```typescript
      // Track descriptions for custom entry + notification
      const descriptions: Array<{
        mimeType: string;
        description: string;
        model: string;
        elapsedMs: number;
      }> = [];

      const processed = await processMessages(
        event.messages,
        visionModel,
        auth.apiKey,
        prompt,
        requireHttps,
        descriptions,      // passed by reference to collect timing data
      );

      // Write custom entry for persistence
      if (descriptions.length > 0) {
        try {
          ctx.sessionManager.appendEntry({
            type: "custom",
            customType: "vision-description",
            data: {
              timestamp: Date.now(),
              descriptions,
            },
          });
        } catch {
          // Never block the conversation because of entry write failure
        }

        // Notify Edini UI via extension_ui_request
        try {
          await pi.sendUiRequest({
            method: "notify",
            notifyType: "info",
            message: JSON.stringify({
              event: "vision_description",
              descriptions,
            }),
          });
        } catch {
          // Notification is best-effort; don't block
        }
      }

      return { messages: processed };
```

- [ ] **Step 2: Update processMessages signature and body to accept descriptions array**

Change the `processMessages` function signature from:
```typescript
async function processMessages(
  messages: readonly ContextMessage[],
  visionModel: { ... },
  apiKey: string,
  prompt: string,
  requireHttps: boolean,
): Promise<ContextMessage[]>
```

To:
```typescript
async function processMessages(
  messages: readonly ContextMessage[],
  visionModel: { id: string; baseUrl: string; api: string; name?: string; provider: string; input: string[]; reasoning: boolean; cost: Record<string, number>; contextWindow: number; maxTokens: number },
  apiKey: string,
  prompt: string,
  requireHttps: boolean,
  descriptionsOut?: Array<{ mimeType: string; description: string; model: string; elapsedMs: number }>,
): Promise<ContextMessage[]>
```

Then inside the loop where `describeImage` is called, add timing:

Old code:
```typescript
          const visionResult = await describeImage({
            imageBase64: block.data,
            mediaType: mimeType,
            model: visionModel as any,
            apiKey,
            prompt,
            requireHttps,
          });
```

New code:
```typescript
          const t0 = Date.now();
          const visionResult = await describeImage({
            imageBase64: block.data,
            mediaType: mimeType,
            model: visionModel as any,
            apiKey,
            prompt,
            requireHttps,
          });
          const elapsedMs = Date.now() - t0;

          if (descriptionsOut) {
            descriptionsOut.push({
              mimeType,
              description: visionResult.description || visionResult.error || "",
              model: `${visionModel.provider}/${visionModel.id}`,
              elapsedMs,
            });
          }
```

- [ ] **Step 3: Commit**

```bash
git add pi-extensions/pi-visionizer/src/index.ts
git commit -m "feat(visionizer): write vision-description custom entry + notify Edini via extension_ui_request"
```

---

### Task 9: viewport.py — remove capture_viewport (moved to media_manager)

**Files:**
- Modify: `python3.11libs/edini/ui/viewport.py`

- [ ] **Step 1: Replace capture_viewport with re-export from media_manager**

Old `viewport.py`:
```python
"""Houdini Viewport screenshot capture for Edini."""
import io
import base64
import importlib

try:
    hou = importlib.import_module("hou")
except Exception:
    hou = None


def capture_viewport() -> str | None:
    """Capture current Houdini viewport as base64 JPEG.

    Returns base64-encoded JPEG string, or None if not in Houdini.
    """
    if hou is None:
        return None

    try:
        desktop = hou.ui.curDesktop()
        viewport = desktop.paneTabOfType(hou.paneTabType.SceneViewer)
        if viewport is None:
            return None

        buf = io.BytesIO()
        viewport.saveImage(buf, "JPEG", width=1280, height=720)
        buf.seek(0)
        img_bytes = buf.getvalue()

        if len(img_bytes) == 0:
            return None

        return base64.b64encode(img_bytes).decode("ascii")
    except Exception:
        return None


def is_vision_capable(provider: str, model: str) -> bool:
    """Check if the current model supports image input."""
    vision_providers = {"anthropic", "openai", "google"}
    return provider.lower() in vision_providers
```

New `viewport.py`:
```python
"""Houdini Viewport utilities for Edini.

Viewport capture has moved to edini.media_manager for unified image handling.
This module keeps backward-compatible re-exports.
"""
import importlib

try:
    hou = importlib.import_module("hou")
except Exception:
    hou = None


# Re-export from media_manager for backward compatibility
from edini.media_manager import capture_viewport, is_viewport_available


def is_vision_capable(provider: str, model: str) -> bool:
    """Check if the current model supports image input natively.

    Note: With pi-visionizer, even text-only models can handle images.
    This function only checks native support.
    """
    vision_providers = {"anthropic", "openai", "google"}
    return provider.lower() in vision_providers
```

- [ ] **Step 2: Verify both imports work**

```bash
cd F:/zz/Edini && python -c "
from edini.ui.viewport import capture_viewport, is_viewport_available, is_vision_capable
print('capture_viewport:', capture_viewport)
print('is_viewport_available:', is_viewport_available)
print('is_vision_capable("openai","gpt4"):', is_vision_capable('openai', 'gpt4'))
"
```
Expected output: all functions print without error

- [ ] **Step 3: Commit**

```bash
git add python3.11libs/edini/ui/viewport.py
git commit -m "refactor(viewport): delegate capture_viewport to media_manager, keep backward-compat re-export"
```

---

### Task 10: agent_panel.py — full multimodal integration

**Files:**
- Modify: `python3.11libs/edini/ui/agent_panel.py`
- Modify: `python3.11libs/edini/ui/main_window.py` (Step 9 only)

This is the largest integration task. It modifies:
1. Import statements
2. `_build_ui` — add ImageAttachmentWidget + file pick button + drag/paste event filter
3. `_on_send` — merge attachment images with screenshot
4. `_on_capture_viewport` — use MediaItem instead of raw base64
5. New drag-drop keyPress handlers
6. vision_description signal listener

- [ ] **Step 1: Add new imports at top of agent_panel.py**

Add after the existing imports (`from edini.ui.theme import accent_color, fs`):

```python
from edini.media_manager import (
    MediaItem, MediaSource, capture_viewport,
    from_files, from_clipboard, from_mime_data,
    mime_has_images, MAX_ATTACHMENTS,
)
from edini.ui.image_attachment import ImageAttachmentWidget
from edini.ui.vision_overlay import VisionDescriptionBubble
```

- [ ] **Step 2: Replace screenshot-related member variables in `__init__`**

Old code:
```python
        # Screenshot
        self._screenshot_data: str | None = None
```

New code:
```python
        # Screenshot (kept as separate quick-capture, stored as MediaItem)
        self._screenshot_item: MediaItem | None = None
```

- [ ] **Step 3: Add ImageAttachmentWidget and file-pick button to `_build_ui`**

Add the attachment bar between the timeline panels and the input row. Also add a file-pick button next to the screenshot button.

**Edit A**: Add attachment bar before the input row section. Find:
```python
        # ── Input row ──
        input_row = QtWidgets.QHBoxLayout()
```

Replace with:
```python
        # ── Attachment preview bar ──
        self._attachment_bar = ImageAttachmentWidget()
        root.addWidget(self._attachment_bar)

        # ── Input row ──
        input_row = QtWidgets.QHBoxLayout()
```

**Edit B**: Add file pick button next to screenshot button. After the `_screenshot_remove_btn` section, add:

Old code (around line 654-662, the action_col section):
```python
        self._screenshot_btn = QtWidgets.QPushButton("📷")
        self._screenshot_btn.setToolTip("Capture viewport screenshot")
        self._screenshot_btn.setFixedSize(32, 32)
        self._screenshot_btn.clicked.connect(self._on_capture_viewport)
        # Always show screenshot button — pi-visionizer routes images to vision model
        self._screenshot_btn.setVisible(True)
        action_col.addWidget(self._screenshot_btn)

        self._screenshot_remove_btn = QtWidgets.QPushButton("✕")
        self._screenshot_remove_btn.setObjectName("GhostButton")
        self._screenshot_remove_btn.setToolTip("Remove screenshot")
        self._screenshot_remove_btn.clicked.connect(self._on_remove_screenshot)
        self._screenshot_remove_btn.setVisible(False)
        self._screenshot_remove_btn.setFixedSize(32, 20)
        action_col.addWidget(self._screenshot_remove_btn)
```

New code:
```python
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.setSpacing(2)

        self._screenshot_btn = QtWidgets.QPushButton("📷")
        self._screenshot_btn.setToolTip("Capture viewport screenshot")
        self._screenshot_btn.setFixedSize(32, 32)
        self._screenshot_btn.clicked.connect(self._on_capture_viewport)
        self._screenshot_btn.setVisible(True)
        btn_row.addWidget(self._screenshot_btn)

        self._file_pick_btn = QtWidgets.QPushButton("📁")
        self._file_pick_btn.setToolTip("Select image files")
        self._file_pick_btn.setFixedSize(32, 32)
        self._file_pick_btn.clicked.connect(self._on_pick_files)
        btn_row.addWidget(self._file_pick_btn)

        self._paste_btn = QtWidgets.QPushButton("📋")
        self._paste_btn.setToolTip("Paste image from clipboard")
        self._paste_btn.setFixedSize(32, 32)
        self._paste_btn.clicked.connect(self._on_paste_image)
        btn_row.addWidget(self._paste_btn)

        action_col.addLayout(btn_row)

        self._screenshot_remove_btn = QtWidgets.QPushButton("✕")
        self._screenshot_remove_btn.setObjectName("GhostButton")
        self._screenshot_remove_btn.setToolTip("Remove screenshot")
        self._screenshot_remove_btn.clicked.connect(self._on_remove_screenshot)
        self._screenshot_remove_btn.setVisible(False)
        self._screenshot_remove_btn.setFixedSize(32, 20)
        action_col.addWidget(self._screenshot_remove_btn)
```

- [ ] **Step 4: Add drag-drop event filter and paste handler in `_bind_events`**

After `self._knowledge_reject_all.clicked.connect(self._on_knowledge_reject_all)`, add:

```python
        # Drag-drop on input_edit
        self.input_edit.setAcceptDrops(True)
        self.input_edit.dragEnterEvent = self._on_drag_enter
        self.input_edit.dragMoveEvent = self._on_drag_move
        self.input_edit.dropEvent = self._on_drop
```

- [ ] **Step 5: Modify `eventFilter` to handle Ctrl+V paste of images**

In the `eventFilter` method, before the `return super().eventFilter(watched, event)`, add a check for Ctrl+V with image on clipboard:

Right before `return super().eventFilter(watched, event)`, add:
```python
                if key in (int(QtCore.Qt.Key_V),):
                    if modifiers & QtCore.Qt.ControlModifier:
                        if clipboard_has_image():
                            self._on_paste_image()
                            return True
        return super().eventFilter(watched, event)
```

But wait — we need to import `clipboard_has_image`. Actually, we already import `from_clipboard` from media_manager. Let me add `clipboard_has_image` to the imports too.

Actually, let me add it to the import line:
```python
from edini.media_manager import (
    MediaItem, MediaSource, capture_viewport,
    from_files, from_clipboard, from_mime_data,
    mime_has_images, MAX_ATTACHMENTS, clipboard_has_image,
)
```

- [ ] **Step 6: Replace `_on_send` to include attachment images**

Old `_on_send` (around line 723):
```python
        images = None
        if self._screenshot_data:
            images = [{"type": "image", "data": self._screenshot_data, "mimeType": "image/jpeg"}]
            self._on_remove_screenshot()

        self.submit_requested.emit(text, images)
```

New code:
```python
        # Collect all images: attachment bar items + screenshot
        images: list[dict] = []
        for item in self._attachment_bar.items():
            images.append({
                "type": "image",
                "data": item.base64,
                "mimeType": item.mime_type,
            })
        if self._screenshot_item:
            images.append({
                "type": "image",
                "data": self._screenshot_item.base64,
                "mimeType": self._screenshot_item.mime_type,
            })
            self._on_remove_screenshot()

        self._attachment_bar.clear()

        self.submit_requested.emit(text, images if images else None)
```

- [ ] **Step 7: Replace screenshot capture/remove methods**

**Edit A**: Replace `_on_capture_viewport`:

Old:
```python
    def _on_capture_viewport(self):
        from edini.ui.viewport import capture_viewport
        b64 = capture_viewport()
        if b64 is None:
            self._screenshot_btn.setText("❌")
            QtCore.QTimer.singleShot(1500, lambda: self._screenshot_btn.setText("📷"))
            return
        self._screenshot_data = b64
        self._screenshot_btn.setText("📸")
        self._screenshot_remove_btn.setVisible(True)
```

New:
```python
    def _on_capture_viewport(self):
        item = capture_viewport()
        if item is None:
            self._screenshot_btn.setText("❌")
            QtCore.QTimer.singleShot(1500, lambda: self._screenshot_btn.setText("📷"))
            return
        # If attachment bar has room, add there instead of old screenshot slot
        if not self._attachment_bar.is_full():
            self._attachment_bar.add(item)
        else:
            self._screenshot_item = item
            self._screenshot_btn.setText("📸")
            self._screenshot_remove_btn.setVisible(True)
```

**Edit B**: Replace `_on_remove_screenshot`:

Old:
```python
    def _on_remove_screenshot(self):
        self._screenshot_data = None
        self._screenshot_btn.setText("📷")
        self._screenshot_remove_btn.setVisible(False)
```

New:
```python
    def _on_remove_screenshot(self):
        self._screenshot_item = None
        self._screenshot_btn.setText("📷")
        self._screenshot_remove_btn.setVisible(False)
```

- [ ] **Step 8: Add file pick, paste, and drag-drop handlers**

Add after the `_on_remove_screenshot` method:

```python
    def _on_pick_files(self):
        """Open file dialog to select image files."""
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self,
            "Select Images",
            "",
            "Images (*.png *.jpg *.jpeg *.gif *.webp *.bmp);;All Files (*)",
        )
        if not paths:
            return
        items = from_files(paths)
        added = 0
        for item in items:
            if self._attachment_bar.is_full():
                break
            if self._attachment_bar.add(item):
                added += 1
        if added == 0 and self._attachment_bar.is_full():
            self.add_error(f"最多 {MAX_ATTACHMENTS} 张图片")

    def _on_paste_image(self):
        """Paste image from clipboard into attachment bar."""
        if self._attachment_bar.is_full():
            self.add_error(f"最多 {MAX_ATTACHMENTS} 张图片")
            return
        item = from_clipboard()
        if item is None:
            return
        self._attachment_bar.add(item)

    def _on_drag_enter(self, event):
        if mime_has_images(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def _on_drag_move(self, event):
        if mime_has_images(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def _on_drop(self, event):
        items = from_mime_data(event.mimeData())
        for item in items:
            if self._attachment_bar.is_full():
                break
            self._attachment_bar.add(item)
        if items:
            event.acceptProposedAction()
        else:
            event.ignore()
```

- [ ] **Step 9: Add vision_description listener**

In `main_window.py` (not agent_panel.py), add the listener connection. Since the vision_description comes from rpc_client → main_window, and we want to render the bubble in the agent_panel's timeline.

**Edit main_window.py** — in `_bind_events`, after the existing `_rpc_client.extension_info.connect(...)` line:

```python
        self._rpc_client.vision_description.connect(self._on_vision_description)
```

And add the handler method to `EdiniMainWindow`:

```python
    def _on_vision_description(self, descriptions: list):
        """Handle vision_description notification from pi-visionizer."""
        if not descriptions:
            return
        # Check if any description is an error
        has_error = any(
            d.get("description", "").startswith("[Error:") or
            d.get("description", "").startswith("[Image: unable")
            for d in descriptions
        )
        if has_error:
            error_msg = descriptions[0].get("description", "Vision model error")
            bubble = VisionDescriptionBubble.create_error_bubble(error_msg)
        else:
            bubble = VisionDescriptionBubble.create_from_notification(descriptions)
        self.agent_panel.timeline_view.add_widget(bubble)
```

- [ ] **Step 10: Verify imports are consistent**

```bash
cd F:/zz/Edini && python -c "
from edini.ui.agent_panel import AgentPanel
from edini.media_manager import MediaItem, MediaSource, capture_viewport
from edini.ui.image_attachment import ImageAttachmentWidget
from edini.ui.vision_overlay import VisionDescriptionBubble
print('All imports OK')
"
```
Expected output: `All imports OK`

- [ ] **Step 11: Commit**

```bash
git add python3.11libs/edini/ui/agent_panel.py python3.11libs/edini/ui/main_window.py
git commit -m "feat(ui): integrate multimodal — attachment bar, file pick, paste, drag-drop, vision description bubble"
```

---

### Task 11: End-to-end verification checklist

- [ ] **Step 1: Verify all modules import without errors**

```bash
cd F:/zz/Edini && python -c "
from edini.media_manager import (MediaItem, MediaSource, validate, make_thumbnail,
    capture_viewport, from_files, from_clipboard, from_mime_data,
    mime_has_images, clipboard_has_image, is_viewport_available)
from edini.ui.image_attachment import ImageAttachmentWidget
from edini.ui.vision_overlay import VisionDescriptionBubble
from edini.ui.viewport import capture_viewport as vp_cap, is_vision_capable
from edini.ui.agent_panel import AgentPanel
from edini.rpc_client import RpcClient
print('✅ ALL MODULES IMPORTED SUCCESSFULLY')
"
```

Expected: prints success message

- [ ] **Step 2: Verify pi-visionizer default model change**

```bash
cd F:/zz/Edini && grep -n "DEFAULT_VISION_MODEL" pi-extensions/pi-visionizer/src/config.ts
```
Expected: shows `aliyun` provider and `qwen-vl-max` modelId

- [ ] **Step 3: Verify git status is clean**

```bash
cd F:/zz/Edini && git status
```

- [ ] **Step 4: Commit final state**

```bash
git add -A && git commit -m "feat(multimodal): complete multimodal pipeline — MediaManager + AttachmentBar + VisionBubble + pi-visionizer Qwen-VL"
```
```

- [ ] **Step 5: Update progress.md to reflect completion**

In `wiki/pages/progress.md`, update the multimodal section:
- Change status from `status-wip` to `status-done`
- Add: ✅ 截图链路修复（三级降级）· ✅ 拖拽/粘贴/文件选择 · ✅ 附件预览栏 · ✅ 视觉描述气泡 · ✅ pi-visionizer 默认 Qwen-VL

- [ ] **Step 6: Commit progress update**

```bash
git add wiki/pages/progress.md
git commit -m "docs: mark multimodal phase as complete in progress.md"
```
