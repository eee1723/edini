"""Session storage — JSON file per session, local persistence."""
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

SESSIONS_DIR = Path(__file__).resolve().parent.parent / "sessions"


def _ensure_dir():
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


def _session_path(session_id: str) -> Path:
    return SESSIONS_DIR / f"{session_id}.json"


def create_session(session_id: str, title: str = "New Session") -> dict:
    _ensure_dir()
    now = datetime.now().isoformat()
    record = {
        "session_id": session_id,
        "title": title,
        "created_at": now,
        "updated_at": now,
        "compressed_summary": "",
        "compressed_at": "",
        "compressed_round": 0,
        "messages": [],
    }
    with open(_session_path(session_id), "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    return record


def load_session(session_id: str) -> Optional[dict]:
    path = _session_path(session_id)
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_session(record: dict):
    _ensure_dir()
    record["updated_at"] = datetime.now().isoformat()
    sid = record["session_id"]
    with open(_session_path(sid), "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)


def delete_session(session_id: str):
    path = _session_path(session_id)
    if path.exists():
        os.remove(path)


def list_sessions() -> list:
    _ensure_dir()
    result = []
    for p in sorted(SESSIONS_DIR.glob("*.json"), key=os.path.getmtime, reverse=True):
        try:
            with open(p, "r", encoding="utf-8") as f:
                record = json.load(f)
            result.append(record)
        except Exception:
            pass
    return result


def append_message(session_id: str, msg: dict):
    record = load_session(session_id)
    if record is None:
        record = create_session(session_id)
    if "timestamp" not in msg:
        msg["timestamp"] = datetime.now().isoformat()
    record.setdefault("messages", []).append(msg)
    save_session(record)


def load_messages(session_id: str) -> list:
    record = load_session(session_id)
    if record is None:
        return []
    return record.get("messages", [])


def rename_session(session_id: str, new_title: str) -> None:
    record = load_session(session_id)
    if record is None:
        return
    record["title"] = new_title
    save_session(record)


def compress_session(session_id: str, summary: str, compressed_round: int) -> None:
    """Store compression summary without deleting any messages."""
    record = load_session(session_id)
    if record is None:
        return
    record["compressed_summary"] = summary
    record["compressed_at"] = datetime.now().isoformat()
    record["compressed_round"] = compressed_round
    save_session(record)


def is_compressed(session_id: str) -> bool:
    """Check if a session has been compressed."""
    record = load_session(session_id)
    if record is None:
        return False
    return bool(record.get("compressed_summary", ""))


def build_context_messages(session_id: str, recent_rounds: int = 6) -> list[dict]:
    """Build messages to send to Pi as context.

    Returns full messages if no compression; summary + last N rounds if compressed.
    """
    record = load_session(session_id)
    if record is None:
        return []
    summary = record.get("compressed_summary", "")
    messages = record.get("messages", [])
    if summary:
        summary_msg = {
            "role": "user",
            "content": f"[Previous session context: {summary}]",
            "is_context_summary": True,
        }
        recent = messages[-(recent_rounds * 2):]
        return [summary_msg] + recent
    return messages


def get_session_stats(session_id: str) -> dict:
    """Return metadata: rounds, created, updated, compressed."""
    record = load_session(session_id)
    if record is None:
        return {}
    messages = record.get("messages", [])
    user_msgs = [m for m in messages if m.get("role") == "user"]
    return {
        "rounds": len(user_msgs),
        "created_at": record.get("created_at", ""),
        "updated_at": record.get("updated_at", ""),
        "compressed": bool(record.get("compressed_summary", "")),
    }
