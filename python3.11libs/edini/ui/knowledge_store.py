"""Knowledge store — persistent pitfall/tip/workflow/limitation entries.

Stored globally at ~/.pi/agent/edini-knowledge.json.
Max 100 entries, LRU eviction.
"""
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

KNOWLEDGE_FILE = Path.home() / ".pi" / "agent" / "edini-knowledge.json"
MAX_ENTRIES = 100
CATEGORIES = {
    "避坑": "🐛",
    "技巧": "💡",
    "工作流": "📋",
    "模型局限": "⚠️",
}


def _load() -> list[dict[str, Any]]:
    """Load knowledge entries from JSON file."""
    if KNOWLEDGE_FILE.exists():
        try:
            with open(KNOWLEDGE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return []


def _save(entries: list[dict[str, Any]]) -> None:
    """Atomically write knowledge entries."""
    KNOWLEDGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = KNOWLEDGE_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)
    tmp.replace(KNOWLEDGE_FILE)


def get_all() -> list[dict[str, Any]]:
    """Return all knowledge entries, newest first."""
    entries = _load()
    entries.sort(key=lambda e: e.get("created_at", ""), reverse=True)
    return entries


def get_by_category(category: str) -> list[dict[str, Any]]:
    """Return entries filtered by category."""
    return [e for e in get_all() if e.get("category") == category]


def add_entry(category: str, title: str, content: str,
              source_session: str = "") -> dict[str, Any]:
    """Add a new knowledge entry. Keeps at most MAX_ENTRIES."""
    if category not in CATEGORIES:
        raise ValueError(f"Unknown category: {category}. Use: {list(CATEGORIES.keys())}")

    entries = _load()

    # Deduplication: skip if same title already exists
    for e in entries:
        if e.get("title", "").strip() == title.strip():
            return e  # Already exists

    entry = {
        "id": uuid.uuid4().hex[:12],
        "category": category,
        "title": title.strip(),
        "content": content.strip(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_session": source_session,
    }
    entries.append(entry)

    # Enforce max entries (keep newest)
    if len(entries) > MAX_ENTRIES:
        entries = entries[-MAX_ENTRIES:]

    _save(entries)
    return entry


def delete_entry(entry_id: str) -> bool:
    """Delete an entry by id. Returns True if found and deleted."""
    entries = _load()
    new_entries = [e for e in entries if e.get("id") != entry_id]
    if len(new_entries) == len(entries):
        return False
    _save(new_entries)
    return True


def clear_all() -> None:
    """Remove all knowledge entries."""
    _save([])


def count() -> int:
    """Return total number of entries."""
    return len(_load())


def build_context_text() -> str:
    """Build the knowledge context text for system prompt injection.

    Returns empty string if no entries or knowledge is disabled.
    """
    entries = get_all()
    if not entries:
        return ""

    lines = ["## 知识库（来自之前对话的沉淀）", ""]
    for e in entries:
        icon = CATEGORIES.get(e.get("category", ""), "📌")
        lines.append(f"- [{icon} {e.get('category', '')}] {e.get('title', '')}: {e.get('content', '')}")

    return "\n".join(lines)


def parse_agent_response(text: str) -> list[dict[str, Any]]:
    """Parse agent response for JSON knowledge entries.

    Looks for JSON array containing objects with category/title/content fields.
    Returns list of parsed entries suitable for add_entry().
    """
    import re

    # Find the outermost JSON array using balanced bracket matching.
    # Start from the LAST '[' to avoid matching earlier inline brackets.
    json_str = _extract_json_array(text)
    if not json_str:
        # Try code block with JSON
        m = re.search(r'```(?:json)?\s*(\[[\s\S]*?\])\s*```', text)
        if m:
            json_str = _extract_json_array(m.group(1))

    if not json_str:
        return []

    try:
        parsed = json.loads(json_str)
    except json.JSONDecodeError:
        return []

    results = []
    for item in parsed if isinstance(parsed, list) else [parsed]:
        if isinstance(item, dict) and "title" in item and "content" in item:
            category = item.get("category", "技巧")
            if category not in CATEGORIES:
                # Map common variations
                cat_map = {
                    "pitfall": "避坑", "bug": "避坑", "陷阱": "避坑",
                    "tip": "技巧", "trick": "技巧",
                    "workflow": "工作流", "流程": "工作流",
                    "limitation": "模型局限", "limit": "模型局限", "限制": "模型局限",
                }
                category = cat_map.get(category.lower() if isinstance(category, str) else "", "技巧")
            results.append({
                "category": category,
                "title": str(item["title"]),
                "content": str(item["content"]),
            })
    return results


def _extract_json_array(text: str) -> str:
    """Extract the outermost JSON array from text using balanced bracket matching.

    Finds the last '[' and tracks bracket balance to find matching ']',
    accounting for brackets inside strings.
    """
    start = text.rfind('[')
    if start < 0:
        return ""

    depth = 0
    in_string = False
    escape_next = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape_next:
            escape_next = False
            continue
        if ch == '\\':
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == '[':
            depth += 1
        elif ch == ']':
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return ""
