"""Image cache for Edini sessions.

Stores user-uploaded images under $HIP/Edini_screenshots/<task_name>/ so they
sit alongside tool-captured screenshots and viewport snapshots.

Cache layout:
    $HIP/Edini_screenshots/<task_name>/
        manifest.json    # [{index, hash, mime_type, filename, size_bytes, cache_path}]
        upload_001_a1b2c3d4.jpg
        upload_002_e5f6g7h8.png
        ...
"""

import base64
import hashlib
import json
import os
from pathlib import Path
from typing import Optional

from edini.screenshots import get_screenshot_dir


def get_image_cache_dir(session_path: str) -> Path:
    """Get the image cache directory for a given session JSONL path.

    Resolves to $HIP/Edini_screenshots/<task_name>/ where task_name is derived
    from the first user message in the session JSONL.
    """
    if not session_path:
        return Path.cwd() / "Edini_screenshots" / "untitled"
    return get_screenshot_dir(session_path)


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

    # Find next available seq considering existing uploads in dir
    existing = {f.name for f in cache_dir.iterdir() if f.is_file()}
    seq = 1
    while any(name.startswith(f"upload_{seq:03d}") for name in existing):
        seq += 1

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
        filename = f"upload_{seq:03d}_{content_hash}{ext}"
        filepath = cache_dir / filename
        seq += 1

        try:
            filepath.write_bytes(raw)
        except OSError:
            continue

        meta = {
            "index": i,
            "hash": content_hash,
            "mime_type": mime,
            "filename": filename,
            "size_bytes": len(raw),
            "cache_path": str(filepath),
        }
        meta_list.append(meta)

    # Merge into manifest.json (multiple uploads per session accumulate)
    manifest_path = cache_dir / "manifest.json"
    prior: list[dict] = []
    if manifest_path.exists():
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                prior = [m for m in data if isinstance(m, dict)]
        except (json.JSONDecodeError, OSError):
            pass
    try:
        manifest_path.write_text(
            json.dumps(prior + meta_list, ensure_ascii=False, indent=2),
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
            # Filter out entries whose files no longer exist
            valid = []
            for meta in data:
                cp = meta.get("cache_path", "")
                file_ok = cp and os.path.isfile(cp)
                if file_ok:
                    valid.append(meta)
            return valid if valid else None
    except (json.JSONDecodeError, OSError):
        pass
    return None


def has_image_cache(session_path: str) -> bool:
    """Check if image cache exists for a session."""
    return load_image_meta(session_path) is not None


def save_descriptions(session_path: str, descriptions: list[dict]) -> bool:
    """Save vision descriptions to the image cache for history loading.

    Args:
        session_path: Path to the session JSONL file.
        descriptions: List of vision description dicts with keys:
            mimeType, description, model, elapsedMs

    Returns True if saved successfully.
    """
    if not session_path or not descriptions:
        return False
    cache_dir = get_image_cache_dir(session_path)
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        desc_path = cache_dir / "descriptions.json"
        desc_path.write_text(
            json.dumps(descriptions, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return True
    except OSError as e:
        return False


def load_descriptions(session_path: str) -> Optional[list[dict]]:
    """Load saved vision descriptions for a session. Returns None if not found."""
    if not session_path:
        return None
    desc_path = get_image_cache_dir(session_path) / "descriptions.json"
    if not desc_path.exists():
        return None
    try:
        data = json.loads(desc_path.read_text(encoding="utf-8"))
        if isinstance(data, list) and data:
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return None


def prune_orphan_caches(session_dir: str) -> int:
    """No-op under the new $HIP/Edini_screenshots layout.

    Folders are now named by task, not session_id, and a single task folder
    may be shared across multiple sessions. Manual cleanup is left to the user.
    """
    return 0
