"""Image cache for Edini sessions.

Stores user-uploaded images alongside Pi session JSONL files so they
can be displayed in the timeline during both live sessions and history browsing.

Cache layout:
    ~/.pi/agent/sessions/<cwd_dir>/edini_images/<session_id>/
        manifest.json    # [{index, hash, mime_type, filename, size_bytes, cache_path}]
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
        print(f"[Edini:img] save_images SKIP: session_path={session_path!r}, images_count={len(images or [])}", flush=True)
        return []

    cache_dir = get_image_cache_dir(session_path)
    print(f"[Edini:img] save_images START: session_path={session_path}, cache_dir={cache_dir}, image_count={len(images)}", flush=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    meta_list: list[dict] = []
    mime_to_ext = {
        "image/jpeg": ".jpg", "image/jpg": ".jpg",
        "image/png": ".png", "image/gif": ".gif",
        "image/webp": ".webp", "image/bmp": ".bmp",
    }

    for i, img in enumerate(images):
        b64_data = img.get("data", "")
        b64_len = len(b64_data) if b64_data else 0
        print(f"[Edini:img] save_images img[{i}]: b64_len={b64_len}, mime={img.get('mimeType', '?')}, filename={img.get('filename', '?')}", flush=True)
        if not b64_data:
            print(f"[Edini:img] save_images img[{i}] SKIP: empty data", flush=True)
            continue
        try:
            raw = base64.b64decode(b64_data)
        except Exception as e:
            print(f"[Edini:img] save_images img[{i}] FAIL: base64 decode error: {e}", flush=True)
            continue

        mime = img.get("mimeType", "image/png")
        ext = mime_to_ext.get(mime, ".jpg")
        content_hash = hashlib.sha256(raw).hexdigest()[:12]
        filename = f"{i}_{content_hash}{ext}"
        filepath = cache_dir / filename

        try:
            filepath.write_bytes(raw)
            print(f"[Edini:img] save_images img[{i}] WRITTEN: {filepath} ({len(raw)} bytes)", flush=True)
        except OSError as e:
            print(f"[Edini:img] save_images img[{i}] FAIL: write error: {e}", flush=True)
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

    # Write manifest.json for history loading
    manifest_path = cache_dir / "manifest.json"
    try:
        manifest_path.write_text(
            json.dumps(meta_list, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[Edini:img] save_images MANIFEST WRITTEN: {manifest_path}, entries={len(meta_list)}", flush=True)
    except OSError as e:
        print(f"[Edini:img] save_images MANIFEST FAIL: {e}", flush=True)

    print(f"[Edini:img] save_images DONE: saved {len(meta_list)}/{len(images)} images", flush=True)
    return meta_list


def load_image_meta(session_path: str) -> Optional[list[dict]]:
    """Load cached image metadata for a session. Returns None if no cache."""
    if not session_path:
        print(f"[Edini:img] load_image_meta SKIP: empty session_path", flush=True)
        return None
    cache_dir = get_image_cache_dir(session_path)
    manifest_path = cache_dir / "manifest.json"
    print(f"[Edini:img] load_image_meta: session_path={session_path}, manifest_path={manifest_path}, exists={manifest_path.exists()}", flush=True)
    if not manifest_path.exists():
        print(f"[Edini:img] load_image_meta MISS: manifest not found at {manifest_path}", flush=True)
        return None
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        print(f"[Edini:img] load_image_meta: manifest loaded, entries={len(data) if isinstance(data, list) else 'not-a-list'}", flush=True)
        if isinstance(data, list) and data:
            # Filter out entries whose files no longer exist
            valid = []
            for meta in data:
                cp = meta.get("cache_path", "")
                file_ok = cp and os.path.isfile(cp)
                print(f"[Edini:img] load_image_meta entry: cache_path={cp}, exists={file_ok}, filename={meta.get('filename', '?')}", flush=True)
                if file_ok:
                    valid.append(meta)
            print(f"[Edini:img] load_image_meta: valid entries={len(valid)}/{len(data)}", flush=True)
            return valid if valid else None
    except (json.JSONDecodeError, OSError) as e:
        print(f"[Edini:img] load_image_meta FAIL: {e}", flush=True)
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
        print(f"[Edini:img] save_descriptions SKIP: session_path={session_path!r}, desc_count={len(descriptions or [])}", flush=True)
        return False
    cache_dir = get_image_cache_dir(session_path)
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        desc_path = cache_dir / "descriptions.json"
        desc_path.write_text(
            json.dumps(descriptions, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[Edini:img] save_descriptions OK: {desc_path}, entries={len(descriptions)}", flush=True)
        return True
    except OSError as e:
        print(f"[Edini:img] save_descriptions FAIL: {e}", flush=True)
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
