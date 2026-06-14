"""Unified screenshot directory for Edini.

All images (user uploads, viewport captures, tool captures) land under:
    $HIP/Edini_screenshots/<task_name>/

where task_name is derived from the first user message of the session.
Filename pattern: <prefix>_<NNN>.<ext> with monotonically increasing seq.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

try:
    import hou
except Exception:
    hou = None

_MAX_TASK_LEN = 40
_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_SEQ_RE = re.compile(r"^(.*?)_(\d+)$")

_SCREENSHOT_ROOT_NAME = "Edini_screenshots"

# session_path -> sanitized task name (in-process cache)
_task_cache: dict[str, str] = {}

# Module-level current session, set by main_window on session switch.
# Used by tool_executor (which doesn't receive session context per-call).
_current_session: str = ""


def set_current_session(session_path: str) -> None:
    global _current_session
    _current_session = session_path or ""


def current_session() -> str:
    return _current_session


def _hip_dir() -> Path:
    if hou is not None:
        try:
            hip = hou.expandString("$HIP")
            if hip and os.path.isdir(hip):
                return Path(hip)
        except Exception:
            pass
    return Path.cwd()


def sanitize_task_name(text: str) -> str:
    if not text:
        return "untitled"
    s = re.sub(r"\s+", " ", text.strip())
    s = _INVALID_CHARS.sub("", s)
    s = s.rstrip(" .")
    if len(s) > _MAX_TASK_LEN:
        s = s[:_MAX_TASK_LEN].rstrip()
    return s or "untitled"


def _read_first_user_message(session_path: str) -> str:
    p = Path(session_path)
    if not p.is_file():
        return ""
    try:
        with p.open("r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("type") not in (None, "message"):
                    continue
                msg = entry.get("message", entry)
                if msg.get("role") != "user":
                    continue
                content = msg.get("content", "")
                if isinstance(content, list):
                    texts = [
                        b.get("text", "")
                        for b in content
                        if isinstance(b, dict) and b.get("type") == "text"
                    ]
                    content = "".join(texts)
                if isinstance(content, str) and content.strip():
                    return content.strip()
    except OSError:
        pass
    return ""


def get_task_name(session_path: str) -> str:
    if session_path and session_path in _task_cache:
        return _task_cache[session_path]
    if not session_path:
        return "untitled"
    text = _read_first_user_message(session_path)
    name = sanitize_task_name(text)
    _task_cache[session_path] = name
    return name


def set_task_name(session_path: str, name: str) -> None:
    if session_path:
        _task_cache[session_path] = sanitize_task_name(name)


def get_screenshot_root() -> Path:
    return _hip_dir() / _SCREENSHOT_ROOT_NAME


def get_screenshot_dir(session_path: str) -> Path:
    d = get_screenshot_root() / get_task_name(session_path)
    d.mkdir(parents=True, exist_ok=True)
    return d


def next_filename(
    session_path: str, prefix: str, ext: str = ".png"
) -> Path:
    """Return next available <prefix>_<NNN><ext> path inside the session's screenshot dir."""
    d = get_screenshot_dir(session_path)
    if not prefix:
        prefix = "image"
    ext = ext if ext.startswith(".") else f".{ext}"
    stem_base = _SEQ_RE.match(prefix)
    if stem_base:
        # AI supplied something like "review_001" — keep its stem as the prefix
        prefix = stem_base.group(1)
    i = 1
    while True:
        candidate = d / f"{prefix}_{i:03d}{ext}"
        if not candidate.exists():
            return candidate
        i += 1


def relocate_filepath(
    filepath: str, session_path: str, default_prefix: str = "capture"
) -> str:
    """Move an AI-supplied filepath into the session screenshot dir with seq numbering.

    'review.png'              -> <dir>/review_001.png
    'screenshots/foo.png'     -> <dir>/foo_001.png
    'C:/abs/bar_007.png'      -> <dir>/bar_007.png   (existing seq preserved)
    ''                        -> <dir>/capture_001.png
    """
    if not filepath:
        return str(next_filename(session_path, default_prefix, ".png"))

    base = os.path.basename(filepath)
    stem, ext = os.path.splitext(base)
    if not ext:
        ext = ".png"
    if not stem:
        stem = default_prefix

    # If the stem already ends with _NNN, treat it as authoritative
    m = _SEQ_RE.match(stem)
    if m:
        prefix = m.group(1)
        seq = int(m.group(2))
        d = get_screenshot_dir(session_path)
        candidate = d / f"{prefix}_{seq:03d}{ext}"
        if not candidate.exists():
            return str(candidate)
        # Fall through to next_filename if there's an unlikely collision
        return str(next_filename(session_path, prefix, ext))

    return str(next_filename(session_path, stem, ext))
