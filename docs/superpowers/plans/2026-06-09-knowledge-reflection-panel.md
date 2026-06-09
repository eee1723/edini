# Knowledge Reflection Panel — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the in-conversation knowledge extraction with a background HTTP reflection worker and a Knowledge Zone in the right panel, with deduplication.

**Architecture:** ReflectWorker (QThread) reads session .jsonl, builds a prompt, calls the provider's chat completions API directly via urllib, and emits results to a KnowledgeZone widget embedded in ContextPanel. Deduplication uses Jaccard similarity on titles before writing to the knowledge store.

**Tech Stack:** Python 3.11 (stdlib only: urllib, json, threading), PySide6 (Qt widgets/signals)

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `python3.11libs/edini/ui/dedup.py` | CREATE | Jaccard similarity + merge detection |
| `python3.11libs/edini/ui/reflect_worker.py` | CREATE | QThread worker: HTTP call to LLM |
| `python3.11libs/edini/ui/knowledge_zone.py` | CREATE | Knowledge Zone widget (browse + reflection overlay) |
| `python3.11libs/edini/ui/knowledge_store.py` | MODIFY | Add `find_similar()`, `merge_entry()` |
| `python3.11libs/edini/ui/context_panel.py` | MODIFY | Replace Knowledge card with KnowledgeZone |
| `python3.11libs/edini/ui/agent_panel.py` | MODIFY | Remove knowledge extraction UI (~90 lines) |
| `python3.11libs/edini/ui/main_window.py` | MODIFY | Replace old extraction with ReflectWorker trigger |
| `python3.11libs/edini/ui/settings_dialog.py` | MODIFY | Add reflection model selector in Knowledge tab |
| `python3.11libs/edini/config.py` | MODIFY | Add `reflection_provider`/`reflection_model` to defaults |
| `tests/test_dedup.py` | CREATE | Tests for Jaccard + dedup logic |
| `tests/test_reflect_worker.py` | CREATE | Tests for ReflectWorker (mock HTTP) |
| `edini/` mirror | SYNC | All changed files copied to top-level `edini/` |

---

### Task 1: Dedup Module

**Files:**
- Create: `python3.11libs/edini/ui/dedup.py`
- Create: `tests/test_dedup.py`

- [ ] **Step 1: Create `dedup.py`**

```python
"""Deduplication logic for knowledge entries.

Uses Jaccard similarity on tokenized titles to detect near-duplicates.
"""

import re
from typing import Any

_SIMILARITY_THRESHOLD = 0.5


def _tokenize(text: str) -> set[str]:
    """Tokenize text into a set of lowercase words (Chinese char = 1 token)."""
    # Split on whitespace + split CJK chars individually
    tokens: set[str] = set()
    # Extract CJK characters as individual tokens
    for ch in text:
        if '\u4e00' <= ch <= '\u9fff' or '\u3400' <= ch <= '\u4dbf':
            tokens.add(ch)
    # Extract word tokens (Latin words, numbers)
    for word in re.findall(r'[a-zA-Z0-9]+', text.lower()):
        tokens.add(word)
    return tokens


def jaccard_similarity(a: str, b: str) -> float:
    """Compute Jaccard similarity between two strings."""
    ta = _tokenize(a)
    tb = _tokenize(b)
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def find_similar(
    title: str,
    existing: list[dict[str, Any]],
    threshold: float = _SIMILARITY_THRESHOLD,
) -> dict[str, Any] | None:
    """Find the most similar existing entry to the given title.

    Returns the best match if similarity >= threshold, else None.
    """
    best_score = 0.0
    best_match = None
    for item in existing:
        score = jaccard_similarity(title, item.get("title", ""))
        if score > best_score and score >= threshold:
            best_score = score
            best_match = item
    return best_match


def classify_items(
    new_items: list[dict[str, Any]],
    existing_rules: list[dict[str, Any]],
    existing_entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Classify each new item as 'new', 'merge', or skip.

    For each item, check similarity against existing rules/entries.
    If a match is found, set '_action': 'merge' and '_merge_target'.
    Otherwise, '_action': 'new'.
    Returns annotated items (shallow copy).
    """
    all_existing = existing_rules + existing_entries
    results = []
    for item in new_items:
        match = find_similar(item.get("title", ""), all_existing)
        annotated = dict(item)
        if match:
            annotated["_action"] = "merge"
            annotated["_merge_target"] = match
            annotated["_similarity"] = jaccard_similarity(
                item.get("title", ""), match.get("title", ""))
        else:
            annotated["_action"] = "new"
        results.append(annotated)
    return results
```

- [ ] **Step 2: Create `tests/test_dedup.py`**

```python
"""Tests for knowledge deduplication logic."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'python3.11libs'))

import unittest
from edini.ui.dedup import jaccard_similarity, find_similar, classify_items


class TestJaccard(unittest.TestCase):
    def test_identical(self):
        self.assertAlmostEqual(jaccard_similarity("hello world", "hello world"), 1.0)

    def test_no_overlap(self):
        self.assertAlmostEqual(jaccard_similarity("aaa", "bbb"), 0.0)

    def test_partial_overlap(self):
        score = jaccard_similarity("hou API error", "hou API warning")
        self.assertGreater(score, 0.3)
        self.assertLess(score, 1.0)

    def test_chinese_chars(self):
        score = jaccard_similarity("避坑Hou主线程", "避坑Hou多线程")
        self.assertGreater(score, 0.3)

    def test_empty_both(self):
        self.assertAlmostEqual(jaccard_similarity("", ""), 1.0)

    def test_empty_one(self):
        self.assertAlmostEqual(jaccard_similarity("hello", ""), 0.0)


class TestFindSimilar(unittest.TestCase):
    def setUp(self):
        self.existing = [
            {"id": "a1", "title": "hou.BoundingBox 没有 size 方法"},
            {"id": "b2", "title": "Wrangle批量操作用AttribTransfer"},
        ]

    def test_find_exact_match(self):
        result = find_similar("hou.BoundingBox 没有 size 方法", self.existing)
        self.assertIsNotNone(result)
        self.assertEqual(result["id"], "a1")

    def test_find_near_match(self):
        result = find_similar("hou.BoundingBox 缺少 size", self.existing)
        self.assertIsNotNone(result)
        self.assertEqual(result["id"], "a1")

    def test_no_match(self):
        result = find_similar("完全无关的标题xyz", self.existing)
        self.assertIsNone(result)


class TestClassifyItems(unittest.TestCase):
    def test_new_item(self):
        items = [{"type": "rule", "title": "全新的知识", "content": "内容"}]
        result = classify_items(items, [], [])
        self.assertEqual(result[0]["_action"], "new")

    def test_merge_item(self):
        existing = [{"id": "x1", "title": "hou.BoundingBox 没有 size"}]
        items = [{"type": "rule", "title": "hou.BoundingBox 没有 size 方法", "content": "更新"}]
        result = classify_items(items, existing, [])
        self.assertEqual(result[0]["_action"], "merge")
        self.assertEqual(result[0]["_merge_target"]["id"], "x1")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run tests**

Run: `cd E:/edini && python -m pytest tests/test_dedup.py -v`
Expected: All pass

- [ ] **Step 4: Commit**

```bash
git add python3.11libs/edini/ui/dedup.py tests/test_dedup.py
git commit -m "feat: add dedup module with Jaccard similarity for knowledge entries"
```

---

### Task 2: ReflectWorker

**Files:**
- Create: `python3.11libs/edini/ui/reflect_worker.py`
- Create: `tests/test_reflect_worker.py`

- [ ] **Step 1: Create `reflect_worker.py`**

```python
"""Background worker that calls LLM API for knowledge reflection.

Runs on a QThread, reads the session .jsonl directly, builds a prompt
with conversation context + existing knowledge, calls the provider API
via urllib, parses the JSON response, and runs dedup classification.
"""

from __future__ import annotations

import json
import os
import urllib.request
import urllib.error
from typing import Any

from PySide6.QtCore import QThread, Signal

# Provider base URLs for known providers
_PROVIDER_URLS: dict[str, str] = {
    "deepseek": "https://api.deepseek.com/v1/chat/completions",
    "openai": "https://api.openai.com/v1/chat/completions",
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
    "ali": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
    "zai": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
    "zai-coding-cn": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
}

_REFLECT_PROMPT = """你是一个知识反思引擎。分析以下 Houdini 对话，提取值得长期记住的知识。

## 当前知识库内容
{existing_knowledge}

## 对话历史
{conversation}

## 提取标准（全部满足才提取）
1. 发生了具体的错误或意外失败
2. 解决方案不是显而易见的 — 有经验的 Houdini 用户也可能遇到
3. 没有这个提醒，下次很可能犯同样的错
4. 知识足够通用，不依赖特定的节点名或路径

## 不要提取
- 任何 LLM 已经知道的 Houdini 通用知识
- 一次就成功的事情
- 标准文档知识
- 过于具体的节点路径或参数值
- 显而易见的提示
- 纯粹的 API 语法（如 hou.node(path) 的用法）

## 去重要求
检查每条新提取是否与"当前知识库内容"中的已有条目高度相似。
如果相似，用 type:"merge" 并指定 merge_with_id 为已有条目的 id。
合并后的内容应该更通用、更准确。

## 输出格式
JSON 数组，没有值得提取的内容时返回 []
最多5条。宁少勿滥，优先0-3条高质量条目。
[
  {{
    "type": "rule" | "entry" | "merge",
    "category": "避坑" | "技巧" | "工作流" | "配置",
    "title": "中文标题（≤30字，要足够通用）",
    "content": "什么问题 + 为什么 + 怎么避免（1-3句，要足够通用）",
    "tags": ["关键词"],
    "merge_with_id": "已有条目id"
  }}
]"""


class ReflectWorker(QThread):
    """Background thread that runs knowledge reflection."""

    # Emitted when reflection finishes successfully with classified items
    reflection_done = Signal(list)  # list of annotated items (with _action)
    # Emitted on error
    reflection_failed = Signal(str)  # error message
    # Emitted for status updates
    reflection_status = Signal(str)  # status text

    def __init__(
        self,
        session_path: str,
        provider: str,
        model: str,
        api_key: str,
        base_url: str | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._session_path = session_path
        self._provider = provider
        self._model = model
        self._api_key = api_key
        self._base_url = base_url

    def run(self) -> None:
        try:
            self.reflection_status.emit("Reading conversation...")
            conversation = self._read_conversation()
            if not conversation:
                self.reflection_failed.emit("No conversation to reflect on")
                return

            self.reflection_status.emit("Loading knowledge base...")
            existing_knowledge = self._load_existing_knowledge()

            self.reflection_status.emit("Reflecting...")
            prompt = _REFLECT_PROMPT.format(
                existing_knowledge=existing_knowledge,
                conversation=conversation,
            )

            raw_response = self._call_api(prompt)
            if not raw_response:
                self.reflection_failed.emit("Empty response from model")
                return

            items = self._parse_response(raw_response)
            if not items:
                self.reflection_status.emit("No new knowledge to extract")
                self.reflection_done.emit([])
                return

            # Classify with dedup
            from edini.ui.dedup import classify_items
            from edini.ui.knowledge_store import load_rules, load_entries

            classified = classify_items(items, load_rules(), load_entries())
            self.reflection_done.emit(classified)

        except Exception as e:
            self.reflection_failed.emit(str(e))

    def _read_conversation(self) -> str:
        """Read conversation from session .jsonl, format as text."""
        if not self._session_path or not os.path.exists(self._session_path):
            return ""
        lines = []
        with open(self._session_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                role = msg.get("role", "")
                content = msg.get("content", "")
                if isinstance(content, list):
                    # Multi-part content — concatenate text parts
                    content = " ".join(
                        p.get("text", "") for p in content
                        if isinstance(p, dict) and p.get("type") == "text"
                    )
                if role in ("user", "assistant") and content:
                    # Truncate long messages to keep prompt manageable
                    if len(content) > 500:
                        content = content[:500] + "..."
                    lines.append(f"[{role}] {content}")
        return "\n".join(lines[:40])  # Max 40 messages

    def _load_existing_knowledge(self) -> str:
        """Load and format existing knowledge for the prompt."""
        try:
            from edini.ui.knowledge_store import load_rules, load_entries
            parts = []
            for r in load_rules():
                parts.append(f"  [铁律][{r['category']}] {r['title']}: {r['content']}")
            for e in load_entries():
                parts.append(f"  [知识][{e['category']}] {e['title']}: {e['content']}")
            return "\n".join(parts) if parts else "  (空)"
        except Exception:
            return "  (无法加载)"

    def _call_api(self, prompt: str) -> str:
        """Call the provider's chat completions API."""
        url = self._resolve_url()
        if not url:
            raise ValueError(f"No API URL for provider: {self._provider}")

        body = json.dumps({
            "model": self._model,
            "messages": [
                {"role": "system", "content": "Output ONLY a valid JSON array. No other text."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
            "max_tokens": 2000,
        }).encode("utf-8")

        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {self._api_key}")

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                # OpenAI-compatible response format
                choices = data.get("choices", [])
                if choices:
                    return choices[0].get("message", {}).get("content", "")
                return ""
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"API HTTP {e.code}: {body}")

    def _resolve_url(self) -> str | None:
        """Resolve the chat completions URL for the provider."""
        # Explicit base_url takes priority
        if self._base_url:
            base = self._base_url.rstrip("/")
            if "/chat/completions" not in base:
                return f"{base}/chat/completions"
            return base
        # Known provider mapping
        return _PROVIDER_URLS.get(self._provider.lower())

    def _parse_response(self, text: str) -> list[dict[str, Any]]:
        """Parse the JSON response from the model."""
        from edini.ui.knowledge_store import parse_extraction_response
        items, _ = parse_extraction_response(text)
        return items
```

- [ ] **Step 2: Create `tests/test_reflect_worker.py`**

```python
"""Tests for ReflectWorker."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'python3.11libs'))

import json
import unittest
from unittest.mock import patch, MagicMock
from edini.ui.reflect_worker import ReflectWorker, _PROVIDER_URLS


class TestProviderUrls(unittest.TestCase):
    def test_known_providers_have_urls(self):
        for p in ["deepseek", "openai", "qwen", "zai-coding-cn"]:
            self.assertIn(p, _PROVIDER_URLS)

    def test_unknown_provider_no_url(self):
        w = ReflectWorker("", "unknown_provider", "model", "key")
        self.assertIsNone(w._resolve_url())

    def test_custom_base_url(self):
        w = ReflectWorker("", "custom", "model", "key",
                          base_url="https://example.com/v1")
        self.assertEqual(w._resolve_url(), "https://example.com/v1/chat/completions")


class TestReadConversation(unittest.TestCase):
    def test_read_jsonl(self):
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl',
                                         delete=False, encoding='utf-8') as f:
            f.write(json.dumps({"role": "user", "content": "hello"}) + "\n")
            f.write(json.dumps({"role": "assistant", "content": "world"}) + "\n")
            path = f.name
        try:
            w = ReflectWorker(path, "deepseek", "model", "key")
            text = w._read_conversation()
            self.assertIn("hello", text)
            self.assertIn("world", text)
        finally:
            os.unlink(path)

    def test_missing_file(self):
        w = ReflectWorker("/nonexistent/file.jsonl", "deepseek", "model", "key")
        self.assertEqual(w._read_conversation(), "")

    def test_multipart_content(self):
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl',
                                         delete=False, encoding='utf-8') as f:
            f.write(json.dumps({
                "role": "user",
                "content": [
                    {"type": "text", "text": "part1"},
                    {"type": "text", "text": "part2"},
                ]
            }) + "\n")
            path = f.name
        try:
            w = ReflectWorker(path, "deepseek", "model", "key")
            text = w._read_conversation()
            self.assertIn("part1", text)
            self.assertIn("part2", text)
        finally:
            os.unlink(path)


class TestParseResponse(unittest.TestCase):
    def test_valid_json(self):
        w = ReflectWorker("", "deepseek", "model", "key")
        items = w._parse_response('[{"type":"rule","category":"避坑","title":"test","content":"desc","tags":[]}]')
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "test")

    def test_empty_array(self):
        w = ReflectWorker("", "deepseek", "model", "key")
        items = w._parse_response('[]')
        self.assertEqual(len(items), 0)


class TestCallApi(unittest.TestCase):
    @patch("edini.ui.reflect_worker.urllib.request.urlopen")
    def test_successful_call(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "choices": [{"message": {"content": "[]"}}]
        }).encode("utf-8")
        mock_resp.__enter__ = lambda s: mock_resp
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        w = ReflectWorker("", "deepseek", "deepseek-chat", "sk-test")
        result = w._call_api("test prompt")
        self.assertEqual(result, "[]")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run tests**

Run: `cd E:/edini && python -m pytest tests/test_reflect_worker.py tests/test_dedup.py -v`
Expected: All pass

- [ ] **Step 4: Commit**

```bash
git add python3.11libs/edini/ui/reflect_worker.py tests/test_reflect_worker.py
git commit -m "feat: add ReflectWorker for background knowledge reflection"
```

---

### Task 3: Knowledge Store — Add `find_similar` and `merge_entry`

**Files:**
- Modify: `python3.11libs/edini/ui/knowledge_store.py`

- [ ] **Step 1: Add two functions to knowledge_store.py**

Append after the existing `entries_count()` function (before the Extraction section):

```python
def find_similar(title: str, threshold: float = 0.5) -> dict[str, Any] | None:
    """Find the most similar existing rule or entry to a given title."""
    from edini.ui.dedup import find_similar as _find_similar
    all_items = load_rules() + load_entries()
    return _find_similar(title, all_items, threshold)


def merge_entry(entry_id: str, new_title: str, new_content: str,
                new_tags: list[str] | None = None) -> dict | None:
    """Update an existing entry with merged content. Returns updated entry."""
    # Try entries first, then rules
    entries = load_entries()
    for e in entries:
        if e["id"] == entry_id:
            e["title"] = new_title
            e["content"] = new_content
            if new_tags is not None:
                existing_tags = set(e.get("tags", []))
                e["tags"] = list(existing_tags | set(new_tags))
            save_entries(entries)
            return e
    rules = load_rules()
    for r in rules:
        if r["id"] == entry_id:
            r["title"] = new_title
            r["content"] = new_content
            save_rules(rules)
            return r
    return None
```

- [ ] **Step 2: Run existing tests to verify no regression**

Run: `cd E:/edini && python -m pytest tests/test_knowledge_store.py -v`
Expected: All 33 tests pass

- [ ] **Step 3: Commit**

```bash
git add python3.11libs/edini/ui/knowledge_store.py
git commit -m "feat: add find_similar and merge_entry to knowledge store"
```

---

### Task 4: KnowledgeZone Widget

**Files:**
- Create: `python3.11libs/edini/ui/knowledge_zone.py`

- [ ] **Step 1: Create `knowledge_zone.py`**

This is the largest new file. It has two modes:
1. **Browse mode**: Collapsible lists of rules and entries
2. **Reflecting mode**: Shows progress + extracted items + accept/reject

```python
"""Knowledge Zone widget for the right panel.

Two modes:
- Browse: Collapsible lists of iron rules and knowledge entries
- Reflecting: Shows reflection progress and extracted items for review
"""

from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from edini.ui.theme import fs, accent_color


def _section_btn(text: str) -> QtWidgets.QPushButton:
    """Collapsible section toggle button."""
    btn = QtWidgets.QPushButton(f"▶ {text}")
    btn.setFlat(True)
    btn.setStyleSheet(f"""
        QPushButton {{
            color: #80cbc4; font-size: {fs(11)}; font-weight: 600;
            border: none; text-align: left; padding: 4px 2px;
        }}
        QPushButton:hover {{ color: {accent_color()}; }}
    """)
    return btn


def _item_label(text: str, color: str = "#94a3b8") -> QtWidgets.QLabel:
    lbl = QtWidgets.QLabel(text)
    lbl.setStyleSheet(f"color: {color}; font-size: {fs(10)}; border: none;")
    lbl.setWordWrap(True)
    return lbl


def _action_btn(text: str, bg: str) -> QtWidgets.QPushButton:
    btn = QtWidgets.QPushButton(text)
    btn.setFixedHeight(22)
    btn.setStyleSheet(f"""
        QPushButton {{
            background: {bg}; color: #e5e5eb; border: none;
            border-radius: 3px; font-size: {fs(10)}; padding: 0 8px;
        }}
        QPushButton:hover {{ background: {bg}cc; }}
    """)
    return btn


class KnowledgeZone(QtWidgets.QWidget):
    """Knowledge panel with browse + reflection overlay."""

    # Signals
    items_accepted = Signal(list)   # list of accepted items
    reflection_requested = Signal()  # manual trigger

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rules_expanded = False
        self._entries_expanded = False
        self._pending_items: list[dict] = []

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Header
        header = QtWidgets.QHBoxLayout()
        self._title = QtWidgets.QLabel("📚 Knowledge")
        self._title.setStyleSheet(
            f"color: #80cbc4; font-size: {fs(12)}; font-weight: 700; border: none;")
        header.addWidget(self._title)
        header.addStretch()
        layout.addLayout(header)

        # Browse container (rules + entries)
        self._browse = QtWidgets.QWidget()
        self._browse_layout = QtWidgets.QVBoxLayout(self._browse)
        self._browse_layout.setContentsMargins(0, 0, 0, 0)
        self._browse_layout.setSpacing(2)

        # Rules section
        self._rules_btn = _section_btn("Iron Rules (0)")
        self._rules_btn.clicked.connect(self._toggle_rules)
        self._browse_layout.addWidget(self._rules_btn)
        self._rules_list = QtWidgets.QWidget()
        self._rules_list.setVisible(False)
        self._rules_list_layout = QtWidgets.QVBoxLayout(self._rules_list)
        self._rules_list_layout.setContentsMargins(8, 0, 0, 0)
        self._rules_list_layout.setSpacing(1)
        self._browse_layout.addWidget(self._rules_list)

        # Entries section
        self._entries_btn = _section_btn("Entries (0)")
        self._entries_btn.clicked.connect(self._toggle_entries)
        self._browse_layout.addWidget(self._entries_btn)
        self._entries_list = QtWidgets.QWidget()
        self._entries_list.setVisible(False)
        self._entries_list_layout = QtWidgets.QVBoxLayout(self._entries_list)
        self._entries_list_layout.setContentsMargins(8, 0, 0, 0)
        self._entries_list_layout.setSpacing(1)
        self._browse_layout.addWidget(self._entries_list)

        layout.addWidget(self._browse)

        # Reflection overlay (hidden by default)
        self._reflect_area = QtWidgets.QFrame()
        self._reflect_area.setStyleSheet("""
            QFrame {
                background: #0a0a12;
                border: 1px solid #1e2e2e;
                border-radius: 4px;
            }
        """)
        self._reflect_layout = QtWidgets.QVBoxLayout(self._reflect_area)
        self._reflect_layout.setContentsMargins(8, 6, 8, 6)
        self._reflect_layout.setSpacing(4)

        self._reflect_status = QtWidgets.QLabel("")
        self._reflect_status.setStyleSheet(
            f"color: #80cbc4; font-size: {fs(11)}; border: none;")
        self._reflect_layout.addWidget(self._reflect_status)

        self._reflect_items = QtWidgets.QWidget()
        self._reflect_items_layout = QtWidgets.QVBoxLayout(self._reflect_items)
        self._reflect_items_layout.setContentsMargins(0, 0, 0, 0)
        self._reflect_items_layout.setSpacing(3)
        self._reflect_items_layout.addStretch()
        self._reflect_layout.addWidget(self._reflect_items)

        btn_row = QtWidgets.QHBoxLayout()
        self._accept_all_btn = _action_btn("✓ 全部接受", "#16a34a")
        self._accept_all_btn.clicked.connect(self._on_accept_all)
        self._reject_all_btn = _action_btn("✕ 全部放弃", "#555")
        self._reject_all_btn.clicked.connect(self._on_reject_all)
        btn_row.addWidget(self._accept_all_btn)
        btn_row.addWidget(self._reject_all_btn)
        self._reflect_layout.addLayout(btn_row)

        self._reflect_area.setVisible(False)
        layout.addWidget(self._reflect_area)

    # ── Browse mode ──

    def refresh(self) -> None:
        """Reload and display rules/entries counts."""
        from edini.ui.knowledge_store import load_rules, load_entries

        rules = load_rules()
        entries = load_entries()
        self._rules_btn.setText(f"▶ Iron Rules ({len(rules)})")
        self._entries_btn.setText(f"▶ Entries ({len(entries)})")

        # Populate lists if expanded
        self._populate_list(self._rules_list_layout, rules)
        self._populate_list(self._entries_list_layout, entries)

    def _populate_list(self, layout: QtWidgets.QVBoxLayout,
                       items: list[dict]) -> None:
        # Clear existing widgets (keep the stretch at end)
        while layout.count() > 1:
            w = layout.takeAt(0).widget()
            if w:
                w.deleteLater()
        # Insert items before the stretch
        for item in items:
            cat = item.get("category", "")
            title = item.get("title", "")
            lbl = _item_label(f"[{cat}] {title}", "#c0c0cc")
            layout.insertWidget(layout.count() - 1, lbl)

    def _toggle_rules(self) -> None:
        self._rules_expanded = not self._rules_expanded
        self._rules_list.setVisible(self._rules_expanded)
        arrow = "▼" if self._rules_expanded else "▶"
        from edini.ui.knowledge_store import rules_count
        self._rules_btn.setText(f"{arrow} Iron Rules ({rules_count()})")

    def _toggle_entries(self) -> None:
        self._entries_expanded = not self._entries_expanded
        self._entries_list.setVisible(self._entries_expanded)
        arrow = "▼" if self._entries_expanded else "▶"
        from edini.ui.knowledge_store import entries_count
        self._entries_btn.setText(f"{arrow} Entries ({entries_count()})")

    # ── Reflecting mode ──

    def show_reflection_status(self, text: str) -> None:
        """Show reflection progress status."""
        self._reflect_status.setText(text)
        self._reflect_area.setVisible(True)
        self._accept_all_btn.setVisible(False)
        self._reject_all_btn.setVisible(False)
        # Clear any previous items
        self._clear_reflect_items()

    def show_reflection_results(self, items: list[dict]) -> None:
        """Display extracted items for user review."""
        self._pending_items = items
        self._reflect_status.setText(
            f"🧠 知识提取 — {len(items)} 条发现" if items else "✅ 无新知识")

        if not items:
            QtCore.QTimer.singleShot(2000, lambda: self._reflect_area.setVisible(False))
            return

        self._clear_reflect_items()
        for i, item in enumerate(items):
            card = self._make_result_card(item, i)
            self._reflect_items_layout.insertWidget(
                self._reflect_items_layout.count() - 1, card)

        self._accept_all_btn.setVisible(True)
        self._reject_all_btn.setVisible(True)

    def _clear_reflect_items(self) -> None:
        while self._reflect_items_layout.count() > 1:
            w = self._reflect_items_layout.takeAt(0).widget()
            if w:
                w.deleteLater()
        self._pending_items = []

    def _make_result_card(self, item: dict, index: int) -> QtWidgets.QWidget:
        card = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(card)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4)

        action = item.get("_action", "new")
        if action == "merge":
            badge_text = "🔄"
            tooltip = f"合并到: {item.get('_merge_target', {}).get('title', '?')}"
        else:
            badge_text = "🆕"
            tooltip = "新条目"

        badge = QtWidgets.QLabel(badge_text)
        badge.setToolTip(tooltip)
        badge.setFixedWidth(18)
        badge.setStyleSheet(f"font-size: {fs(11)}; border: none;")
        layout.addWidget(badge)

        cat = item.get("category", "")
        cat_lbl = QtWidgets.QLabel(cat)
        cat_lbl.setStyleSheet(f"color:#71717a;font-size:{fs(10)};border:none;")
        cat_lbl.setFixedWidth(32)
        layout.addWidget(cat_lbl)

        content_w = QtWidgets.QWidget()
        cl = QtWidgets.QVBoxLayout(content_w)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)
        title_lbl = QtWidgets.QLabel(item.get("title", ""))
        title_lbl.setStyleSheet(
            f"color:#e5e5eb;font-size:{fs(10)};font-weight:600;border:none;")
        title_lbl.setWordWrap(True)
        cl.addWidget(title_lbl)
        desc = item.get("content", "")[:80]
        desc_lbl = QtWidgets.QLabel(desc)
        desc_lbl.setStyleSheet(f"color:#71717a;font-size:{fs(9)};border:none;")
        desc_lbl.setWordWrap(True)
        cl.addWidget(desc_lbl)
        layout.addWidget(content_w, 1)

        accept_btn = _action_btn("✓", "#16a34a")
        accept_btn.setFixedSize(22, 22)
        accept_btn.clicked.connect(
            lambda checked=False, idx=index: self._on_accept_one(idx))
        layout.addWidget(accept_btn)

        reject_btn = _action_btn("✕", "#555")
        reject_btn.setFixedSize(22, 22)
        reject_btn.clicked.connect(
            lambda checked=False, idx=index: self._on_reject_one(idx))
        layout.addWidget(reject_btn)

        return card

    def _on_accept_one(self, index: int) -> None:
        if 0 <= index < len(self._pending_items):
            item = self._pending_items.pop(index)
            self.items_accepted.emit([item])
            self.show_reflection_results(self._pending_items)

    def _on_reject_one(self, index: int) -> None:
        if 0 <= index < len(self._pending_items):
            self._pending_items.pop(index)
            self.show_reflection_results(self._pending_items)

    def _on_accept_all(self) -> None:
        items = list(self._pending_items)
        self.items_accepted.emit(items)
        self._clear_reflect_items()
        self._reflect_area.setVisible(False)

    def _on_reject_all(self) -> None:
        self._clear_reflect_items()
        self._reflect_area.setVisible(False)
```

- [ ] **Step 2: Commit**

```bash
git add python3.11libs/edini/ui/knowledge_zone.py
git commit -m "feat: add KnowledgeZone widget with browse + reflection overlay"
```

---

### Task 5: Wire KnowledgeZone into ContextPanel

**Files:**
- Modify: `python3.11libs/edini/ui/context_panel.py`

- [ ] **Step 1: Replace Knowledge card with KnowledgeZone**

In `_build_ui`, replace the "Card 3: Knowledge" block. The old code creates `kn_card, kn_layout = _make_card(...)` with rules/entries counts + "管理" button. Replace it with:

```python
        # ── Card 3: Knowledge Zone ──
        self.knowledge_zone = KnowledgeZone(self)
        layout.addWidget(self.knowledge_zone)
```

Add the import at top:
```python
from edini.ui.knowledge_zone import KnowledgeZone
```

- [ ] **Step 2: Update `refresh_knowledge()`**

Replace the method body:

```python
    def refresh_knowledge(self):
        """Refresh knowledge zone."""
        self.knowledge_zone.refresh()
```

- [ ] **Step 3: Update `_open_knowledge_manager()`**

Keep the dialog but add refresh:

```python
    def _open_knowledge_manager(self):
        from edini.ui.knowledge_dialog import KnowledgeDialog
        dlg = KnowledgeDialog(self)
        dlg.exec()
        self.refresh_knowledge()
```

- [ ] **Step 4: Run existing tests**

Run: `cd E:/edini && python -m pytest tests/ -v`
Expected: All pass (context_panel has no unit tests currently)

- [ ] **Step 5: Commit**

```bash
git add python3.11libs/edini/ui/context_panel.py
git commit -m "feat: replace Knowledge card with KnowledgeZone in ContextPanel"
```

---

### Task 6: Remove Knowledge UI from AgentPanel

**Files:**
- Modify: `python3.11libs/edini/ui/agent_panel.py`

- [ ] **Step 1: Remove knowledge signals**

Delete these lines:
```python
    knowledge_accepted = QtCore.Signal(list)        # list of accepted items
    knowledge_rejected = QtCore.Signal()            # all rejected
```

- [ ] **Step 2: Remove knowledge area widget (~40 lines)**

Delete the entire "Knowledge Extraction Area" section in `_build_ui` — from `self._knowledge_area = QtWidgets.QFrame()` through `root.addWidget(self._knowledge_area)`. This is lines 695–736.

- [ ] **Step 3: Remove knowledge methods (~60 lines)**

Delete these methods entirely:
- `show_extraction_results()`
- `_clear_knowledge_items()`
- `hide_extraction_results()`
- `_make_knowledge_card()`
- `_on_knowledge_accept_one()`
- `_on_knowledge_reject_one()`
- `_on_toggle_item_type()`
- `_on_knowledge_accept_all()`
- `_on_knowledge_reject_all()`

Also remove `_refresh_knowledge_cards()` if it exists.

Delete these instance attributes from `__init__` (if present):
- `self._pending_knowledge_items`

- [ ] **Step 4: Remove the helper function `_knowledge_btn_style`** (defined near top of file, ~8 lines)

- [ ] **Step 5: Verify file still valid**

Run: `cd E:/edini && python -c "from edini.ui.agent_panel import AgentPanel; print('OK')"`
Expected: OK

- [ ] **Step 6: Commit**

```bash
git add python3.11libs/edini/ui/agent_panel.py
git commit -m "refactor: remove knowledge extraction UI from AgentPanel"
```

---

### Task 7: Wire ReflectWorker into MainWindow

**Files:**
- Modify: `python3.11libs/edini/ui/main_window.py`

This is the most delicate change. We need to:
1. Remove old extraction methods
2. Add ReflectWorker trigger
3. Wire KnowledgeZone signals

- [ ] **Step 1: Add imports**

Add to imports:
```python
from edini.ui.reflect_worker import ReflectWorker
```

- [ ] **Step 2: Remove old methods**

Delete entirely:
- `_KNOWLEDGE_PROMPT_PREFIX = "Review the conversation above..."` (class variable)
- `_maybe_extract_knowledge()` (method, ~37 lines)
- `_handle_extraction_response()` (method, ~19 lines)
- `_filter_knowledge_extraction()` (method, ~15 lines)

- [ ] **Step 3: Remove old state variable**

Delete: `self._extracting_knowledge = False`

- [ ] **Step 4: Remove old signal connections**

In `_bind_events`, delete:
```python
        self.agent_panel.knowledge_accepted.connect(self._on_knowledge_accepted)
        self.agent_panel.knowledge_rejected.connect(self._on_knowledge_rejected)
```

- [ ] **Step 5: Remove old handler methods**

Delete:
- `_on_knowledge_accepted()`
- `_on_knowledge_rejected()`

- [ ] **Step 6: Remove old extraction trigger in `_on_agent_done`**

Delete the block:
```python
        # If this was an extraction response, handle separately
        if self._extracting_knowledge:
            self._handle_extraction_response()
            return
```

Delete at the bottom of `_on_agent_done`:
```python
        # Auto knowledge extraction
        self._maybe_extract_knowledge()
```

- [ ] **Step 7: Remove `_filter_knowledge_extraction` usage**

In `_render_messages` / `_on_pi_session_switched`, remove calls to `_filter_knowledge_extraction(messages)`. Search for all references and remove them (the function is deleted).

- [ ] **Step 8: Add new reflection trigger**

In `_on_agent_done`, after the existing eval logic and before the final status updates, add:

```python
        # Trigger knowledge reflection in background
        self._trigger_reflection()
```

- [ ] **Step 9: Add new methods**

```python
    def _trigger_reflection(self):
        """Start background knowledge reflection after conversation ends."""
        settings = get_settings()
        if not settings.get("knowledge_enabled", True):
            return
        if not self._current_session_path:
            return

        # Resolve reflection model config
        try:
            from edini.config import read_pi_auth, read_pi_settings
            pi_settings = read_pi_settings()
            pi_auth = read_pi_auth()

            provider = (settings.get("reflection_provider")
                       or pi_settings.get("defaultProvider", "deepseek"))
            model = (settings.get("reflection_model")
                    or pi_settings.get("defaultModel", "deepseek-chat"))

            # Get API key
            provider_auth = pi_auth.get(provider, {})
            if isinstance(provider_auth, dict):
                api_key = provider_auth.get("key", "")
            elif isinstance(provider_auth, str):
                api_key = provider_auth
            else:
                api_key = ""

            # Check for custom base_url in models.json
            base_url = None
            from edini.config import read_pi_models
            models_conf = read_pi_models()
            prov_conf = models_conf.get("providers", {}).get(provider, {})
            if isinstance(prov_conf, dict) and "baseUrl" in prov_conf:
                base_url = prov_conf["baseUrl"]

            if not api_key:
                return

        except Exception:
            return

        self.context_panel.knowledge_zone.show_reflection_status(
            "🔄 Reflecting...")

        self._reflect_worker = ReflectWorker(
            session_path=self._current_session_path,
            provider=provider,
            model=model,
            api_key=api_key,
            base_url=base_url,
        )
        self._reflect_worker.reflection_done.connect(
            self._on_reflection_done)
        self._reflect_worker.reflection_failed.connect(
            self._on_reflection_failed)
        self._reflect_worker.reflection_status.connect(
            self.context_panel.knowledge_zone.show_reflection_status)
        self._reflect_worker.start()

    def _on_reflection_done(self, items: list):
        """Handle reflection results."""
        if items:
            self.context_panel.knowledge_zone.show_reflection_results(items)
            # Connect accept signal for saving
            self.context_panel.knowledge_zone.items_accepted.connect(
                self._on_knowledge_items_accepted, QtCore.Qt.UniqueConnection)
        else:
            self.context_panel.knowledge_zone._reflect_area.setVisible(False)
        self.status.showMessage("Ready")

    def _on_reflection_failed(self, error: str):
        """Handle reflection failure silently."""
        self.context_panel.knowledge_zone.show_reflection_status(
            f"⚠️ Reflection failed: {error[:50]}")
        QtCore.QTimer.singleShot(
            3000,
            lambda: self.context_panel.knowledge_zone._reflect_area.setVisible(False))
        self.status.showMessage("Ready")

    def _on_knowledge_items_accepted(self, items: list):
        """Save accepted knowledge items."""
        from edini.ui.knowledge_store import (
            add_rule, add_entry, merge_entry, update_rule
        )
        for item in items:
            action = item.get("_action", "new")
            if action == "merge":
                target = item.get("_merge_target", {})
                target_id = target.get("id", "")
                if target_id:
                    merge_entry(
                        target_id,
                        item.get("title", ""),
                        item.get("content", ""),
                        item.get("tags"),
                    )
            else:
                if item.get("type") == "rule":
                    add_rule(
                        item.get("category", "避坑"),
                        item.get("title", ""),
                        item.get("content", ""))
                else:
                    add_entry(
                        item.get("category", "技巧"),
                        item.get("title", ""),
                        item.get("content", ""),
                        tags=item.get("tags", []),
                        source_session=self._current_session_path)
        self.context_panel.knowledge_zone.refresh()
```

- [ ] **Step 10: Verify file parses**

Run: `cd E:/edini && python -c "from edini.ui.main_window import EdiniMainWindow; print('OK')"`
Expected: OK (will fail if hou not available, but import check is sufficient)

- [ ] **Step 11: Run full tests**

Run: `cd E:/edini && python -m pytest tests/ -v`
Expected: All pass

- [ ] **Step 12: Commit**

```bash
git add python3.11libs/edini/ui/main_window.py
git commit -m "feat: replace in-conversation extraction with ReflectWorker in MainWindow"
```

---

### Task 8: Settings — Reflection Model Selector

**Files:**
- Modify: `python3.11libs/edini/ui/settings_dialog.py`
- Modify: `python3.11libs/edini/config.py`

- [ ] **Step 1: Add defaults to config.py**

Add to `_EDINI_DEFAULTS`:
```python
_EDINI_DEFAULTS: dict[str, Any] = {
    "knowledge_enabled": True,
    "reflection_provider": "",   # empty = use conversation provider
    "reflection_model": "",      # empty = use conversation model
}
```

- [ ] **Step 2: Add reflection model row in settings_dialog.py**

In `_build_knowledge_tab`, after the `knowledge_check` and before the `stats_card`, add:

```python
        # Reflection model
        model_row = QtWidgets.QHBoxLayout()
        model_label = QtWidgets.QLabel("反思模型:")
        model_label.setStyleSheet(f"color:#e5e5eb;font-size:{fs(11)};")
        model_row.addWidget(model_label)

        self._reflect_provider_combo = QtWidgets.QComboBox()
        self._reflect_provider_combo.addItem("默认（对话模型）", "")
        self._reflect_provider_combo.setStyleSheet(f"""
            QComboBox {{
                background: #1a1a24; color: #e5e5eb;
                border: 1px solid #2a2a3c; border-radius: 4px;
                padding: 3px 6px; font-size: {fs(11)};
            }}
        """)
        # Populate from pi auth
        from edini.config import read_pi_auth
        for pid in read_pi_auth().keys():
            self._reflect_provider_combo.addItem(pid, pid)
        # Restore saved value
        saved_prov = settings.get("reflection_provider", "")
        idx = self._reflect_provider_combo.findData(saved_prov)
        if idx >= 0:
            self._reflect_provider_combo.setCurrentIndex(idx)
        model_row.addWidget(self._reflect_provider_combo, 1)

        self._reflect_model_edit = QtWidgets.QLineEdit()
        self._reflect_model_edit.setPlaceholderText("默认（对话模型）")
        self._reflect_model_edit.setText(settings.get("reflection_model", ""))
        self._reflect_model_edit.setStyleSheet(f"""
            QLineEdit {{
                background: #1a1a24; color: #e5e5eb;
                border: 1px solid #2a2a3c; border-radius: 4px;
                padding: 3px 6px; font-size: {fs(11)};
            }}
        """)
        model_row.addWidget(self._reflect_model_edit, 1)
        layout.addLayout(model_row)
```

- [ ] **Step 3: Save reflection settings**

In `_on_save`, add before the existing `save_settings(updates)` call:

```python
        updates["reflection_provider"] = self._reflect_provider_combo.currentData()
        updates["reflection_model"] = self._reflect_model_edit.text().strip()
```

- [ ] **Step 4: Commit**

```bash
git add python3.11libs/edini/config.py python3.11libs/edini/ui/settings_dialog.py
git commit -m "feat: add reflection model selector in settings"
```

---

### Task 9: Sync and Final Validation

**Files:**
- All modified files → `edini/` mirror
- `wiki/pages/progress.md`, `wiki/pages/handoff.md`

- [ ] **Step 1: Sync all files to `edini/` package**

```bash
for f in config.py rpc_client.py tool_executor.py node_utils.py __init__.py; do
    cp "python3.11libs/edini/$f" "edini/$f"
done
# Sync new UI files
for f in dedup.py reflect_worker.py knowledge_zone.py knowledge_store.py; do
    cp "python3.11libs/edini/ui/$f" "edini/ui/$f" 2>/dev/null || true
done
```

Note: `edini/ui/` may not exist as a directory. Only sync files that exist in the top-level `edini/` package. The `dedup.py`, `reflect_worker.py`, `knowledge_zone.py` are new — only need to exist in `python3.11libs/edini/ui/` since that's where Houdini loads from.

- [ ] **Step 2: Run full test suite**

Run: `cd E:/edini && python -m pytest tests/ -v`
Expected: All pass (should be ~140+ tests)

- [ ] **Step 3: Verify no broken imports**

```bash
python -c "
from edini.ui.dedup import jaccard_similarity, find_similar, classify_items
from edini.ui.reflect_worker import ReflectWorker
from edini.ui.knowledge_zone import KnowledgeZone
from edini.ui.knowledge_store import find_similar as ks_find, merge_entry
print('All imports OK')
"
```

- [ ] **Step 4: Update wiki pages**

Update `wiki/pages/progress.md` Phase 21 section.
Update `wiki/pages/handoff.md` with new architecture.

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "Phase 21 complete: knowledge reflection panel with dedup"
```

---

## Self-Review Checklist

- [x] **Spec coverage**: Every spec requirement maps to a task (D1→T2, D2→T4+T5, D3→T1+T3, D4→T8, D5→T2 prompt)
- [x] **No placeholders**: All code blocks contain actual implementation
- [x] **Type consistency**: `ReflectWorker.reflection_done` emits `list`, `KnowledgeZone.items_accepted` emits `list`, `_on_knowledge_items_accepted` accepts `list`
- [x] **Removed code accounted for**: Task 6+7 list every removed method/variable
- [x] **Synchronization**: Task 9 handles `edini/` mirror + test verification
