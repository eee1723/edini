"""Pi session store — reads pi-managed session files.

Pi saves sessions as JSONL files under:
    ~/.pi/agent/sessions/--<cwd-with-slash-replaced>--/<timestamp>_<uuid>.jsonl

This module provides functions to list, load metadata, rename, and delete
pi sessions, replacing the old edini session_store.py.
"""
import json
import os
import re
from pathlib import Path
from typing import Optional


def _pi_sessions_root() -> Path:
    """Get the pi sessions root directory."""
    home = os.environ.get("HOME") or os.environ.get("USERPROFILE") or "~"
    return Path(home) / ".pi" / "agent" / "sessions"


def _cwd_to_dirname(cwd: str) -> str:
    """Convert a filesystem path to pi's session directory name.

    pi replaces '/' with '-' and prepends/append '--'.
    Example: /home/user/project → --home-user-project--
    Example: C:/Users/EEE/Desktop/hip → --C:-Users-EEE-Desktop-hip--
    """
    norm = os.path.normpath(cwd).replace("\\", "/")
    # Strip trailing slash
    norm = norm.rstrip("/")
    # Replace leading / for Unix paths
    if norm.startswith("/"):
        norm = norm[1:]
    # Pi replaces both '/' and ':' with '-'
    name = norm.replace("/", "-").replace(":", "-")
    return f"--{name}--"


def get_pi_session_dir(cwd: str) -> Path:
    """Get the directory where pi stores sessions for a given working directory."""
    return _pi_sessions_root() / _cwd_to_dirname(cwd)


def _extract_title(msg: dict) -> str:
    """Extract a title from a message dict, handling both string and list content."""
    content = msg.get("content", "")
    if isinstance(content, str):
        return content[:60]
    elif isinstance(content, list) and content:
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                return block.get("text", "")[:60]
    return ""


def _parse_session_file(path: Path) -> Optional[dict]:
    """Parse a pi JSONL session file and extract metadata.

    Returns dict with: path, session_id, title, created_at, updated_at, message_count.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        if not lines:
            return None

        header = json.loads(lines[0])
        htype = header.get("type", "")
        # Support both old ("header") and new ("session") pi formats
        if htype not in ("header", "session"):
            return None

        # Count user+assistant messages and extract metadata
        msg_count = 0
        title = ""
        updated_at = header.get("updatedAt") or header.get("timestamp", "")
        for line in lines[1:]:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("type") == "message":
                msg = entry.get("message", {})
                role = msg.get("role", "")
                if role in ("user", "assistant"):
                    msg_count += 1
                    # Track last message timestamp as updated_at
                    ts = entry.get("timestamp") or msg.get("timestamp")
                    if ts:
                        if isinstance(ts, (int, float)):
                            from datetime import datetime, timezone
                            updated_at = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat()
                        else:
                            updated_at = str(ts)
                # Extract title from first user message
                if not title and role == "user":
                    title = _extract_title(msg)

        if not title:
            title = "New Session"

        created_at = header.get("createdAt") or header.get("timestamp", "")

        return {
            "path": str(path),
            "session_id": path.stem,
            "title": title,
            "created_at": created_at,
            "updated_at": updated_at,
            "message_count": msg_count,
        }
    except Exception:
        return None


def list_pi_sessions(cwd: str) -> list[dict]:
    """List all pi sessions for a working directory, newest first."""
    session_dir = get_pi_session_dir(cwd)
    if not session_dir.exists():
        return []

    result = []
    for p in sorted(session_dir.glob("*.jsonl"), key=os.path.getmtime, reverse=True):
        meta = _parse_session_file(p)
        if meta:
            result.append(meta)
    return result


def load_pi_messages(session_path: str) -> list[dict]:
    """Load all messages from a pi session file.

    Returns a flat list of message dicts with role and content,
    suitable for rendering in the agent panel.
    """
    try:
        with open(session_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return []

    messages = []
    for line in lines[1:]:  # Skip header
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("type") != "message":
            continue
        msg = entry.get("message", {})
        role = msg.get("role", "")
        if role == "user":
            content = msg.get("content", "")
            if isinstance(content, list):
                texts = [
                    b.get("text", "") for b in content
                    if isinstance(b, dict) and b.get("type") == "text"
                ]
                content = "".join(texts)
            messages.append({"role": "user", "content": content})
        elif role == "assistant":
            content = msg.get("content", [])
            texts = []
            thinkings = []
            if isinstance(content, list):
                for b in content:
                    if isinstance(b, dict):
                        if b.get("type") == "text":
                            texts.append(b.get("text", ""))
                        elif b.get("type") == "thinking":
                            thinkings.append(b.get("thinking", ""))
            messages.append({
                "role": "assistant",
                "content": "\n".join(texts),
                "thinking": thinkings,
            })
    return messages


def delete_pi_session(session_path: str) -> bool:
    """Delete a pi session file."""
    try:
        os.remove(session_path)
        return True
    except OSError:
        return False
