"""Scan Pi session files to enumerate a node's versions.

True source: ~/.pi/agent/sessions/<cwd-hash>/*.jsonl
Reads each file's lines to find sessionName, filters by core_path::vN prefix,
extracts version number + first user message + file metadata.

NOTE: _pi_sessions_root is imported from pi_sessions but can be monkeypatched
in tests. We re-define a local reference so tests can patch THIS module's
binding (not the pi_sessions one).
"""
import json
import os
import time
from pathlib import Path

from edini.ui.pi_sessions import _pi_sessions_root as _imported_root
from edini.ui.components.version_naming import parse_version_session_name


def _pi_sessions_root() -> Path:
    """Local reference to pi_sessions root (monkeypatchable in tests)."""
    return _imported_root()


def scan_node_versions(core_path: str, cwd: str | None = None) -> list[dict]:
    """Return version entries for a given core_path.

    Each entry: {version, summary, meta, session_file}.
    Scans all session dirs (or the cwd-specific one if given).
    Sorted ascending by version.
    """
    root = _pi_sessions_root()
    if not root.exists():
        return []

    # Determine which dirs to scan
    if cwd:
        from edini.ui.pi_sessions import _cwd_to_dirname
        search_dirs = [root / _cwd_to_dirname(cwd)]
    else:
        search_dirs = [d for d in root.iterdir() if d.is_dir()]

    results = []
    for d in search_dirs:
        if not d.exists():
            continue
        for f in d.glob("*.jsonl"):
            entry = _scan_file(f, core_path)
            if entry is not None:
                results.append(entry)

    results.sort(key=lambda v: v["version"])
    return results


def _scan_file(path: Path, core_path: str) -> dict | None:
    """Read one session file; return entry if it matches core_path::vN, else None."""
    session_name = _read_session_name(path)
    if session_name is None:
        return None
    path_part, ver = parse_version_session_name(session_name)
    if path_part != core_path or ver is None:
        return None
    return {
        "version": ver,
        "summary": _read_first_user_msg(path),
        "meta": _file_meta(path),
        "session_file": str(path),
    }


def _read_session_name(path: Path) -> str | None:
    """Read the sessionName from a jsonl file's lines."""
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                if "sessionName" in obj:
                    return obj["sessionName"]
    except Exception:
        return None
    return None


def _read_first_user_msg(path: Path) -> str:
    """Extract the first user-role message content as a summary."""
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                if obj.get("role") == "user":
                    content = obj.get("content", "")
                    # content may be a list (multimodal) or string
                    if isinstance(content, list):
                        content = " ".join(
                            str(c.get("text", "")) if isinstance(c, dict) else str(c)
                            for c in content)
                    return str(content)[:60]
    except Exception:
        pass
    return ""


def _file_meta(path: Path) -> str:
    """Format file mtime + size as a metadata string."""
    try:
        mtime = os.path.getmtime(path)
        size = path.stat().st_size
        t = time.strftime("%m-%d %H:%M", time.localtime(mtime))
        if size < 1024:
            size_str = f"{size}b"
        elif size < 1024 * 1024:
            size_str = f"{size // 1024}k"
        else:
            size_str = f"{size / (1024*1024):.1f}M"
        return f"{t} · {size_str}"
    except Exception:
        return ""
