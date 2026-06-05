"""Knowledge store for Edini — two-layer architecture.

Layer 1: Iron Rules (铁律)
    - Injected into every session's system prompt via edini-context
    - Small set of global rules (pinned knowledge)
    - Stored in ~/.pi/agent/edini-knowledge/rules.json

Layer 2: Knowledge Entries (知识库)
    - Searchable collection of learned knowledge
    - Agent can query via search_knowledge tool
    - Stored in ~/.pi/agent/edini-knowledge/entries.json

Both layers share categories: 避坑, 技巧, 工作流, 配置
"""

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any


# ── Paths ──

def _knowledge_dir() -> Path:
    """Get the knowledge storage directory (~/.pi/agent/edini-knowledge/)."""
    base = os.environ.get("USERPROFILE", os.environ.get("HOME", str(Path.home())))
    return Path(base) / ".pi" / "agent" / "edini-knowledge"


def _ensure_dir() -> None:
    _knowledge_dir().mkdir(parents=True, exist_ok=True)


def _rules_path() -> Path:
    return _knowledge_dir() / "rules.json"


def _entries_path() -> Path:
    return _knowledge_dir() / "entries.json"


CATEGORIES = ["避坑", "技巧", "工作流", "配置"]
MAX_RULES = 20


def _now() -> str:
    return datetime.now().isoformat()


# ==========================================================================
# Layer 1: Iron Rules (铁律)
# ==========================================================================

def load_rules() -> list[dict[str, Any]]:
    """Load all iron rules, sorted by created_at descending."""
    path = _rules_path()
    if not path.exists():
        return _default_rules()
    try:
        with open(path, "r", encoding="utf-8") as f:
            rules = json.load(f)
        return sorted(rules, key=lambda r: r.get("created_at", ""), reverse=True)
    except (json.JSONDecodeError, OSError):
        return _default_rules()


def save_rules(rules: list[dict[str, Any]]) -> None:
    _ensure_dir()
    with open(_rules_path(), "w", encoding="utf-8") as f:
        json.dump(rules, f, ensure_ascii=False, indent=2)


def add_rule(category: str, title: str, content: str, enabled: bool = True) -> dict:
    """Add a rule, enforcing MAX_RULES limit by removing oldest."""
    rules = load_rules()
    rule = {
        "id": uuid.uuid4().hex[:8],
        "category": category,
        "title": title,
        "content": content,
        "enabled": enabled,
        "created_at": _now(),
    }
    rules.append(rule)
    # Enforce max: remove oldest rules if over limit
    if len(rules) > MAX_RULES:
        # Sort by created_at ascending, remove oldest extra items
        rules.sort(key=lambda r: r.get("created_at", ""))
        rules = rules[-(MAX_RULES):]
    save_rules(rules)
    return rule


def update_rule(rule_id: str, **kwargs) -> dict | None:
    rules = load_rules()
    for r in rules:
        if r["id"] == rule_id:
            r.update(kwargs)
            save_rules(rules)
            return r
    return None


def delete_rule(rule_id: str) -> bool:
    rules = load_rules()
    filtered = [r for r in rules if r["id"] != rule_id]
    if len(filtered) < len(rules):
        save_rules(filtered)
        return True
    return False


def get_enabled_rules() -> list[dict[str, Any]]:
    """Return only enabled rules for system prompt injection."""
    return [r for r in load_rules() if r.get("enabled", True)]


def rules_count() -> int:
    return len(load_rules())


def _default_rules() -> list[dict[str, Any]]:
    """Seed rules from wiki pitfalls on first run."""
    now = datetime.now().isoformat()
    return [
        {
            "id": "rule001",
            "category": "避坑",
            "title": "Hou API 只能在主线程调用",
            "content": "Houdini 的 hou 模块只能在主线程调用。RpcClient 使用 QThread 管理 Pi 子进程，但所有 UI 操作和 hou API 调用必须在主线程。信号通过 Qt queued connection 自动跨线程安全。",
            "enabled": True,
            "created_at": now,
        },
        {
            "id": "rule002",
            "category": "避坑",
            "title": "TypeBox 参数保持宽松，Python 端做校验",
            "content": "TypeBox 定义的参数类型与 Python houp API 期望类型不完全对应。工具设计上保持参数类型宽松（Type.Unknown() 用于 set_param value），让 Python 端做最终的类型转换和校验。",
            "enabled": True,
            "created_at": now,
        },
        {
            "id": "rule003",
            "category": "工作流",
            "title": "操作节点前先检查存在性",
            "content": "在修改或删除节点前，先通过 query_node 检查节点是否存在。避免对不存在的路径操作导致错误。创建节点时使用唯一名称避免冲突。",
            "enabled": True,
            "created_at": now,
        },
        {
            "id": "rule004",
            "category": "配置",
            "title": "Houdini Python 环境与系统 Python 隔离",
            "content": "Houdini 自带 Python 解释器，pip install 对 Houdini 内运行的代码无效。Edini 所有依赖在 Houdini Python 环境中可用（PySide6 自带），Pi 作为外部 Node.js 进程独立运行。配置文件使用标准库 json/os/pathlib，无外部 PyPI 依赖。",
            "enabled": True,
            "created_at": now,
        },
    ]


# ==========================================================================
# Layer 2: Knowledge Entries (知识库)
# ==========================================================================

def load_entries() -> list[dict[str, Any]]:
    """Load all knowledge entries, sorted by created_at descending."""
    path = _entries_path()
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            entries = json.load(f)
        return sorted(entries, key=lambda e: e.get("created_at", ""), reverse=True)
    except (json.JSONDecodeError, OSError):
        return []


def save_entries(entries: list[dict[str, Any]]) -> None:
    _ensure_dir()
    with open(_entries_path(), "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)


def add_entry(category: str, title: str, content: str,
              tags: list[str] | None = None,
              source_session: str = "") -> dict:
    entries = load_entries()
    entry = {
        "id": uuid.uuid4().hex[:8],
        "category": category,
        "title": title,
        "content": content,
        "tags": tags or [],
        "source_session": source_session,
        "created_at": _now(),
    }
    entries.append(entry)
    save_entries(entries)
    return entry


def update_entry(entry_id: str, **kwargs) -> dict | None:
    entries = load_entries()
    for e in entries:
        if e["id"] == entry_id:
            e.update(kwargs)
            save_entries(entries)
            return e
    return None


def delete_entry(entry_id: str) -> bool:
    entries = load_entries()
    filtered = [e for e in entries if e["id"] != entry_id]
    if len(filtered) < len(entries):
        save_entries(filtered)
        return True
    return False


def search_entries(query: str = "", category: str = "",
                   tags: list[str] | None = None,
                   limit: int = 20) -> list[dict[str, Any]]:
    """Search knowledge entries by query, category, and/or tags.
    
    Simple substring match on title and content. Returns newest first.
    """
    entries = load_entries()
    results = []
    q_lower = query.lower()
    for e in entries:
        if category and e.get("category") != category:
            continue
        if tags:
            entry_tags = set(e.get("tags", []))
            if not entry_tags.intersection(tags):
                continue
        if q_lower:
            title = e.get("title", "").lower()
            content = e.get("content", "").lower()
            if q_lower not in title and q_lower not in content:
                continue
        results.append(e)
        if len(results) >= limit:
            break
    return results


def entries_count() -> int:
    return len(load_entries())


# ==========================================================================
# Extraction: parse AI reflection response
# ==========================================================================

def parse_extraction_response(text: str) -> list[dict[str, Any]]:
    """Parse the AI's knowledge extraction JSON response.
    
    Expected format:
    [
      {
        "type": "rule" | "entry",
        "category": "避坑" | "技巧" | "工作流" | "配置",
        "title": "short summary (max 30 chars)",
        "content": "detailed description (1-3 sentences)",
        "tags": ["optional", "search", "keywords"]
      }
    ]
    
    Returns empty list if nothing to extract or parsing fails.
    """
    if not text:
        return [], ""

    text = text.strip()

    # Strip markdown code blocks first
    json_str = _extract_json_block(text)
    if json_str is None:
        # Fallback: find first [ and balance brackets
        start = text.find("[")
        if start == -1:
            return [], text
        depth = 0
        end = -1
        for i in range(start, len(text)):
            if text[i] == "[":
                depth += 1
            elif text[i] == "]":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end == -1:
            return [], text
        json_str = text[start:end + 1]

    # Try direct parse
    items = _try_parse_json(json_str)
    if items is not None:
        return _normalize_items(items), ""

    # Try fixing common AI JSON issues: single quotes, trailing commas
    fixed = json_str.replace("'", '"')  # single → double quotes
    items = _try_parse_json(fixed)
    if items is not None:
        return _normalize_items(items), ""

    # Try removing trailing commas
    import re
    fixed2 = re.sub(r',\s*([}\]])', r'\1', json_str)
    items = _try_parse_json(fixed2)
    if items is not None:
        return _normalize_items(items), ""

    # Both fixes combined
    fixed3 = re.sub(r',\s*([}\]])', r'\1', json_str.replace("'", '"'))
    items = _try_parse_json(fixed3)
    if items is not None:
        return _normalize_items(items), ""

    return [], json_str


def _extract_json_block(text: str) -> str | None:
    """Extract JSON from markdown code block ```json ... ``` or ``` ... ```."""
    import re
    m = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if m:
        inner = m.group(1).strip()
        if inner.startswith('['):
            return inner
    return None


def _try_parse_json(s: str) -> list | None:
    """Try to parse a JSON array, return None on failure."""
    try:
        result = json.loads(s)
        if isinstance(result, list):
            return result
    except (json.JSONDecodeError, ValueError):
        pass
    return None


def _normalize_items(items: list) -> list[dict[str, Any]]:
    """Validate and normalize parsed items."""
    valid = []
    for item in items:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type", "entry")
        category = item.get("category", "")
        title = item.get("title", "").strip()
        content = item.get("content", "").strip()
        if not title or not content:
            continue
        if category not in CATEGORIES:
            category = "技巧"
        valid.append({
            "type": item_type if item_type in ("rule", "entry") else "entry",
            "category": category,
            "title": title[:60],
            "content": content[:500],
            "tags": item.get("tags", []) if isinstance(item.get("tags"), list) else [],
        })
    return valid


def accept_extracted(items: list[dict[str, Any]], session_path: str = "") -> tuple[int, int]:
    """Accept extracted items: rules go to rules.json, entries go to entries.json.
    Returns (rules_saved, entries_saved).
    """
    r = 0
    e = 0
    for item in items:
        if item.get("type") == "rule":
            add_rule(item["category"], item["title"], item["content"])
            r += 1
        else:
            add_entry(item["category"], item["title"], item["content"],
                      tags=item.get("tags", []),
                      source_session=session_path)
            e += 1
    return r, e
