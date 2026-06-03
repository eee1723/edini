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
    record.setdefault("messages", []).append(msg)
    save_session(record)


def load_messages(session_id: str) -> list:
    record = load_session(session_id)
    if record is None:
        return []
    return record.get("messages", [])
