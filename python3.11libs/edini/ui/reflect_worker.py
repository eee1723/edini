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

    reflection_done = Signal(list)
    reflection_failed = Signal(str)
    reflection_status = Signal(str)

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
                    content = " ".join(
                        p.get("text", "") for p in content
                        if isinstance(p, dict) and p.get("type") == "text"
                    )
                if role in ("user", "assistant") and content:
                    if len(content) > 500:
                        content = content[:500] + "..."
                    lines.append(f"[{role}] {content}")
        return "\n".join(lines[:40])

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
                choices = data.get("choices", [])
                if choices:
                    return choices[0].get("message", {}).get("content", "")
                return ""
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"API HTTP {e.code}: {body}")

    def _resolve_url(self) -> str | None:
        """Resolve the chat completions URL for the provider."""
        if self._base_url:
            base = self._base_url.rstrip("/")
            if "/chat/completions" not in base:
                return f"{base}/chat/completions"
            return base
        return _PROVIDER_URLS.get(self._provider.lower())

    def _parse_response(self, text: str) -> list[dict[str, Any]]:
        """Parse the JSON response from the model."""
        from edini.ui.knowledge_store import parse_extraction_response
        items, _ = parse_extraction_response(text)
        return items
