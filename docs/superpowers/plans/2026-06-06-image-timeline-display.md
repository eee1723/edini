# Image Timeline Display — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show user-uploaded images in the chat timeline (both live and historical sessions) as clickable references that open in the OS default image viewer.

**Architecture:** Edini-side image cache alongside Pi sessions (`~/.pi/agent/sessions/<cwd>/edini_images/<session_id>/`). Images decoded from base64 to files. `_UserBubble` gains optional image display. `load_pi_messages` reads cache for history. `VisionDescriptionBubble` supports multi-image "view original". All image viewing routed through OS viewer to avoid Houdini PySide6 QPixmap instability.

**Tech Stack:** Python 3.11, PySide6, os.startfile (Windows), subprocess (macOS/Linux)

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `python3.11libs/edini/image_cache.py` | **Create** | ImageCacheManager — save/load/prune image cache alongside Pi sessions |
| `python3.11libs/edini/ui/agent_panel.py` | **Modify** | `_UserBubble` accepts images; `_append_user_message` passes images; `_on_send` saves to cache |
| `python3.11libs/edini/ui/main_window.py` | **Modify** | `_on_agent_submit` saves images to cache; `_on_vision_description` passes all images |
| `python3.11libs/edini/ui/pi_sessions.py` | **Modify** | `load_pi_messages` returns image metadata from cache |
| `python3.11libs/edini/ui/vision_overlay.py` | **Modify** | Multi-image "view original" support |
| `python3.11libs/edini/media_manager.py` | **Modify** | Expose `_read_file_base64` → `decode_image` public helper |

---

### Task 1: ImageCacheManager — save/load image cache

**Files:**
- Create: `python3.11libs/edini/image_cache.py`

- [ ] **Step 1: Create the module**

```python
"""Image cache for Edini sessions.

Stores user-uploaded images alongside Pi session JSONL files so they
can be displayed in the timeline during both live sessions and history browsing.

Cache layout:
    ~/.pi/agent/sessions/<cwd_dir>/edini_images/<session_id>/
        manifest.json    # [{index, hash, mime_type, filename, size_bytes, source}]
        0_a1b2c3d4.jpg
        1_e5f6g7h8.png
        ...
"""

import base64
import hashlib
import json
import os
from pathlib import Path
from typing import Optional


def _pi_sessions_root() -> Path:
    home = os.environ.get("USERPROFILE") or os.environ.get("HOME") or "~"
    return Path(home) / ".pi" / "agent" / "sessions"


def get_image_cache_dir(session_path: str) -> Path:
    """Get the image cache directory for a given session JSONL path.

    Example:
        session: ~/.pi/agent/sessions/--F--zz-Edini--/2026-..._uuid.jsonl
        cache:   ~/.pi/agent/sessions/--F--zz-Edini--/edini_images/2026-..._uuid/
    """
    p = Path(session_path)
    session_id = p.stem  # filename without .jsonl
    return p.parent / "edini_images" / session_id


def save_images(session_path: str, images: list[dict]) -> list[dict]:
    """Save base64-encoded images to cache directory. Returns metadata list.

    Each image dict: {type, data (base64), mimeType}
    Returns: [{index, hash, mime_type, filename, size_bytes, cache_path}]

    If session_path is empty, returns empty list (no-op).
    """
    if not session_path or not images:
        return []

    cache_dir = get_image_cache_dir(session_path)
    cache_dir.mkdir(parents=True, exist_ok=True)

    meta_list: list[dict] = []
    mime_to_ext = {
        "image/jpeg": ".jpg", "image/jpg": ".jpg",
        "image/png": ".png", "image/gif": ".gif",
        "image/webp": ".webp", "image/bmp": ".bmp",
    }

    for i, img in enumerate(images):
        b64_data = img.get("data", "")
        if not b64_data:
            continue
        try:
            raw = base64.b64decode(b64_data)
        except Exception:
            continue

        mime = img.get("mimeType", "image/png")
        ext = mime_to_ext.get(mime, ".jpg")
        content_hash = hashlib.sha256(raw).hexdigest()[:12]
        filename = f"{i}_{content_hash}{ext}"
        filepath = cache_dir / filename

        try:
            filepath.write_bytes(raw)
        except OSError:
            continue

        # Write manifest alongside
        meta = {
            "index": i,
            "hash": content_hash,
            "mime_type": mime,
            "filename": filename,
            "size_bytes": len(raw),
            "cache_path": str(filepath),
        }
        meta_list.append(meta)

    # Write manifest.json for history loading
    manifest_path = cache_dir / "manifest.json"
    try:
        manifest_path.write_text(
            json.dumps(meta_list, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass

    return meta_list


def load_image_meta(session_path: str) -> Optional[list[dict]]:
    """Load cached image metadata for a session. Returns None if no cache."""
    if not session_path:
        return None
    cache_dir = get_image_cache_dir(session_path)
    manifest_path = cache_dir / "manifest.json"
    if not manifest_path.exists():
        return None
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        if isinstance(data, list) and data:
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return None


def has_image_cache(session_path: str) -> bool:
    """Check if image cache exists for a session."""
    if not session_path:
        return False
    return (get_image_cache_dir(session_path) / "manifest.json").exists()


def prune_orphan_caches(session_dir: str) -> int:
    """Remove image cache dirs whose session JSONL no longer exists. Returns count removed."""
    import shutil
    sessions_root = Path(session_dir)
    images_root = sessions_root / "edini_images"
    if not images_root.exists():
        return 0

    removed = 0
    for cache_dir in images_root.iterdir():
        if not cache_dir.is_dir():
            continue
        session_id = cache_dir.name
        jsonl_path = sessions_root / f"{session_id}.jsonl"
        if not jsonl_path.exists():
            try:
                shutil.rmtree(cache_dir)
                removed += 1
            except OSError:
                pass
    return removed
```

- [ ] **Step 2: Verify module imports cleanly**

```bash
python -c "from edini.image_cache import save_images, load_image_meta; print('OK')"
```

---

### Task 2: Enhanced _UserBubble with image references

**Files:**
- Modify: `python3.11libs/edini/ui/agent_panel.py` (the `_UserBubble` class and `_append_user_message`)

- [ ] **Step 1: Add image support to _UserBubble**

Replace the existing `_UserBubble.__init__` and class with:

```python
class _UserBubble(QtWidgets.QFrame):
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
        self._label.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
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

        # Image references (if any)
        if images:
            self._add_image_refs(outer, images)

        self.setStyleSheet("QFrame { background: transparent; border: none; }")

    def _add_image_refs(self, outer: QtWidgets.QVBoxLayout, images: list[dict]):
        """Add clickable image reference chips below the text bubble."""
        img_frame = QtWidgets.QFrame()
        img_frame.setStyleSheet("QFrame { background: transparent; border: none; }")
        img_layout = QtWidgets.QHBoxLayout(img_frame)
        img_layout.setContentsMargins(54, 2, 8, 2)  # indent slightly from text
        img_layout.setSpacing(4)
        img_layout.addStretch(1)  # push chips to right

        for img_meta in images:
            source_icon = _source_icon(img_meta.get("source", "unknown"))
            filename = img_meta.get("filename", "image")
            size_kb = img_meta.get("size_bytes", 0) / 1024
            size_str = f"{size_kb:.0f}KB" if size_kb < 1024 else f"{size_kb/1024:.1f}MB"

            chip = QtWidgets.QPushButton(f"{source_icon} {filename} ({size_str})")
            chip.setCursor(QtCore.Qt.PointingHandCursor)
            chip.setToolTip(f"点击查看原图 — {filename}")
            chip.setStyleSheet(f"""
                QPushButton {{
                    background: rgba(37,37,55,0.6);
                    color: #a1a1aa;
                    border: 1px solid #2a2a3c;
                    border-radius: 3px;
                    padding: 2px 6px;
                    font-size: {fs(10)};
                    text-align: left;
                }}
                QPushButton:hover {{
                    background: rgba(80,80,120,0.5);
                    color: #c4b5fd;
                    border-color: #4a4a6a;
                }}
            """)
            # Capture cache_path in closure
            cache_path = img_meta.get("cache_path", "")
            chip.clicked.connect(
                lambda checked=False, p=cache_path: _open_image_file(p)
            )
            img_layout.addWidget(chip)

        outer.addWidget(img_frame)


_SOURCE_ICON_MAP = {
    "viewport": "📸",
    "file_pick": "📁",
    "drag": "📁",
    "paste": "📋",
    "clipboard": "📋",
}

def _source_icon(source: str) -> str:
    return _SOURCE_ICON_MAP.get(source, "🖼️")


def _open_image_file(path: str):
    """Open an image file in the OS default viewer."""
    if not path or not os.path.isfile(path):
        return
    try:
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass
```

Note: Need to add `import subprocess` at the top of agent_panel.py if not already present.

- [ ] **Step 2: Update `_append_user_message` to accept images**

Change the method signature and body:

```python
def _append_user_message(self, text: str, images: list[dict] | None = None):
    """Append a user message bubble to the timeline."""
    self.timeline_view.add_widget(_UserBubble(text, images))
```

- [ ] **Step 3: Update `_on_send` to save images to cache and pass to bubble**

In `_on_send`, after collecting images and emitting `submit_requested`, also save to cache:

Find this section:
```python
        self._attachment_bar.clear()

        self.submit_requested.emit(text, images if images else None)
```

Replace with:
```python
        self._attachment_bar.clear()

        # Save images to cache for timeline display
        image_meta: list[dict] = []
        if images:
            from edini.image_cache import save_images
            # Build richer metadata from original MediaItems before they're lost
            for i, img in enumerate(images):
                meta = {
                    "index": i,
                    "mime_type": img.get("mimeType", "image/png"),
                    "filename": f"image_{i+1}",
                    "size_bytes": len(base64.b64decode(img.get("data", ""))) if img.get("data") else 0,
                    "source": "unknown",
                }
                image_meta.append(meta)

        self.submit_requested.emit(text, images if images else None)

        # Show image chips in the user bubble (even before cache save completes)
        if image_meta:
            # We need the session path, which isn't available yet. Save
            # a placeholder - the actual cache write happens in main_window.
            pass
```

**Design note:** The user message is currently appended in `_on_send()` (agent_panel), before `_on_agent_submit()` (main_window) runs. To save images to cache before displaying them, we MOVE the `_append_user_message` call from `_on_send` to `_on_agent_submit`. This ensures the session path is available and cache is written first.

### Task 3: MainWindow integration — save to cache on submit

- [ ] **Step 1: Remove _append_user_message from _on_send**

In `agent_panel.py`, `_on_send` method, remove this line:
```python
        self._append_user_message(text)
```

- [ ] **Step 2: Add cache save + user message to _on_agent_submit**

In `main_window.py`, `_on_agent_submit`, add after the existing code:

```python
    def _on_agent_submit(self, text: str, images=None):
        # Take pre-snapshot for change tracking
        self._pre_snapshot = snap_scene()
        self.agent_panel.begin_assistant_message()

        # Save images for vision_description bubble
        self._pending_images = images

        # Save images to cache and show in user bubble
        if images and self._current_session_path:
            from edini.image_cache import save_images
            image_meta = save_images(self._current_session_path, images)
            self.agent_panel._append_user_message(text, image_meta)
        else:
            self.agent_panel._append_user_message(text)

        # Add "recognizing" placeholder if images are attached
        if images:
            self._recognizing_placeholder = _RecognizingPlaceholder()
            self.agent_panel.timeline_view.add_widget(self._recognizing_placeholder)

        self._rpc_client.send_prompt(text, images=images)
```

---

### Task 4: History loading — load image cache alongside messages

**Files:**
- Modify: `python3.11libs/edini/ui/pi_sessions.py`

- [ ] **Step 1: Add `load_pi_messages_with_images` function**

Add to `pi_sessions.py`:

```python
def load_pi_messages_with_images(session_path: str) -> list[dict]:
    """Load messages from a pi session file, with image metadata from cache.

    Returns same format as load_pi_messages, but user messages with images
    will have an additional 'images' key with cached image metadata.
    """
    from edini.image_cache import load_image_meta

    messages = load_pi_messages(session_path)
    image_meta = load_image_meta(session_path)

    if not image_meta:
        return messages

    # Annotate user messages with their images
    # Map: message index among user messages → image metadata
    user_idx = 0
    for msg in messages:
        if msg.get("role") == "user":
            # Simple heuristic: first user message gets images
            # In practice, only the first user message in a round has images
            if user_idx == 0:
                msg["images"] = image_meta
                break  # Only first user message for now
            user_idx += 1

    return messages
```

- [ ] **Step 2: Update main_window to use new loader**

In `main_window.py`, update `_on_session_selected` and `_on_back_to_current` and `_on_pi_messages_received`:

Change:
```python
messages = load_pi_messages(session_path)
```
To:
```python
messages = load_pi_messages_with_images(session_path)
```

And in `_append_user_message` call (in `_on_pi_messages_received`), pass images:

```python
def _on_pi_messages_received(self, messages: list):
    messages = self._merge_consecutive_assistants(messages)
    messages = self._filter_knowledge_extraction(messages)
    self.agent_panel.clear_timeline()
    for m in messages:
        role = m.get("role", "")
        content = m.get("content", "")
        images = m.get("images")  # NEW
        if role == "user":
            self.agent_panel._append_user_message(content, images)  # UPDATED
        elif role == "assistant":
            ...
```

Similarly update the two places in `_on_session_selected` and `_on_back_to_current`.

---

### Task 5: Multi-image support in VisionDescriptionBubble

**Files:**
- Modify: `python3.11libs/edini/ui/vision_overlay.py`
- Modify: `python3.11libs/edini/ui/main_window.py`

- [ ] **Step 1: Extend VisionDescriptionBubble for multiple original images**

In `vision_overlay.py`, change `set_original_image` → `set_original_images`:

```python
    def __init__(self, descriptions, parent=None):
        ...
        self._image_base64_list: list[str] = []  # was: _image_base64: str | None

    def set_original_images(self, base64_list: list[str]):
        """Provide original image data for 'view original' feature (multiple images)."""
        self._image_base64_list = base64_list

    def set_original_image(self, base64_data: str):
        """Backward-compat: single image."""
        self._image_base64_list = [base64_data]

    def _on_view_original(self):
        """Open all original images in OS default viewers."""
        if not self._image_base64_list:
            return
        mime_type = self._descriptions[0].get("mimeType", "image/jpeg") if self._descriptions else "image/jpeg"
        ext = _mime_to_ext(mime_type)
        for i, b64 in enumerate(self._image_base64_list):
            try:
                fd, path = tempfile.mkstemp(suffix=ext, prefix=f"edini_view_{i}_")
                with os.fdopen(fd, "wb") as f:
                    f.write(base64.b64decode(b64))
                _open_with_os(path)
            except Exception:
                pass

    # Update the "view original" button text to reflect count
    def _build_content(self):
        ...
        count = len(self._image_base64_list) if self._image_base64_list else 0
        btn_text = f"📸 查看原图 ({count})" if count > 1 else "📸 查看原图"
        view_btn = QtWidgets.QPushButton(btn_text)
        ...
```

Add helper:
```python
def _open_with_os(path: str):
    if sys.platform == "win32":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])
```

- [ ] **Step 2: Update main_window to pass all images**

In `main_window.py`, `_on_vision_description`:

```python
    def _on_vision_description(self, descriptions: list):
        # Save all image data before cleanup
        all_image_data: list[str] = []
        if self._pending_images:
            all_image_data = [img.get("data", "") for img in self._pending_images if img.get("data")]

        self._cleanup_recognizing()

        if not descriptions:
            return
        ...
        # Pass all images instead of just first
        if all_image_data:
            bubble.set_original_images(all_image_data)
        ...
```

---

### Task 6: Prune orphan caches on session delete

**Files:**
- Modify: `python3.11libs/edini/ui/main_window.py`

- [ ] **Step 1: Prune cache when session is deleted**

In `_on_session_deleted`, add cache pruning:

```python
    def _on_session_deleted(self, session_path: str):
        self.history_panel.remove_session(session_path)

        # Prune orphaned image cache
        from edini.image_cache import prune_orphan_caches
        from edini.ui.pi_sessions import get_pi_session_dir
        try:
            cwd = _get_working_dir()
            prune_orphan_caches(str(get_pi_session_dir(cwd)))
        except Exception:
            pass
        
        ...rest of existing code...
```

---

### Task 7: Import fixes and verification

- [ ] **Step 1: Add missing imports to agent_panel.py**

At top of `agent_panel.py`, add:
```python
import subprocess
import base64
```

Check if `os` is already imported (it should be for `os.startfile` usage).

- [ ] **Step 2: End-to-end verification checklist**

```bash
# 1. Module imports
python -c "from edini.image_cache import save_images, load_image_meta, prune_orphan_caches; print('OK')"

# 2. Cache save/load round-trip
python -c "
from edini.image_cache import save_images, load_image_meta
import tempfile, os
# Create a temp session path
d = tempfile.mkdtemp()
sp = os.path.join(d, 'test_session.jsonl')
# Save a dummy image
import base64
dummy = base64.b64encode(b'test123').decode()
meta = save_images(sp, [{'type':'image','data':dummy,'mimeType':'image/png'}])
assert len(meta) == 1
assert meta[0]['filename'].endswith('.png')
# Load back
loaded = load_image_meta(sp)
assert loaded == meta
# Cleanup
import shutil
shutil.rmtree(d, ignore_errors=True)
print('OK - cache round-trip works')
"
```
