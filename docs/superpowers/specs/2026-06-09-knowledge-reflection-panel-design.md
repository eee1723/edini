# Knowledge Reflection Panel — Design Spec

**Date**: 2026-06-09
**Phase**: 21
**Depends on**: Phase 20 (testing + knowledge infrastructure)

## Problem Statement

Current knowledge extraction has 4 critical flaws:

1. **Pollutes conversation timeline** — Reflection prompt + AI response appear in the main chat, requiring `_filter_knowledge_extraction()` to hide them from display
2. **Reuses Pi process** — Reflection competes with user's next message; model has to hold the entire conversation context just to reflect
3. **No deduplication** — `accept_extracted()` blindly appends, causing knowledge bloat and near-duplicate entries
4. **Extraction quality uncontrolled** — Model often extracts overly specific node paths or generic LLM-known facts, ignoring the prompt's constraints

## Design Decisions

### D1: HTTP Direct Call (not Pi process)

Reflection needs no tool access — just pure text reasoning on conversation history. A direct HTTP call to the LLM API is simpler, cheaper, and avoids Pi session conflicts.

**Implementation**: `ReflectWorker(QThread)` makes a single HTTP POST to the provider's chat completions endpoint. Runs in background, emits signals on completion. Zero interaction with Pi's JSON-RPC protocol.

### D2: Context Panel → Knowledge Zone

Right panel (340–400px) currently has:
- Pi Status card
- Usage card
- Scene Info card
- Knowledge card (just counts + "管理" button)

**Change**: Replace the Knowledge card with a **Knowledge Zone** that has two modes:

| Mode | When active | Shows |
|------|-------------|-------|
| **Browse** | Default | Iron rules list + entries list, collapsible, with delete/disable |
| **Reflecting** | After conversation ends | Progress spinner → extracted items → accept/reject per item |

The Knowledge Zone uses the same vertical space — rules and entries are in collapsible groups that default to collapsed. When reflection finishes, the "Reflecting" overlay expands to show results.

### D3: Two-Phase Deduplication

**Phase A (pure Python, always runs)**: Title Jaccard similarity > 0.5 against all existing rules/entries. If match found, flag for merge rather than create.

**Phase B (LLM-assisted, optional)**: For flagged items, ask the reflection model: "Given existing item X and new item Y, produce a single merged item that preserves both insights." Only runs when Phase A finds a potential duplicate.

This ensures:
- Exact duplicates are always caught (Phase A)
- Near-duplicates get intelligently merged (Phase B)
- No standalone "is this knowledge correct?" check (too risky — LLM may wrongly reject valid knowledge)

### D4: Settings Panel Extension

Add "反思模型" row in the Knowledge tab of settings:
- Provider dropdown (populated from pi's configured providers)
- Model dropdown (populated from provider's models)
- Default: same as conversation model

Stored in `settings.json` as `reflection_provider` / `reflection_model`.

### D5: Reflect Prompt Design

The prompt includes:
1. The full conversation messages (user + assistant turns) as context
2. The current knowledge store contents (rules + entries) so the model can assess duplication
3. The extraction criteria (same as current, tightened)
4. Instruction to prefer merging with existing items over creating new ones

## Affected Files & Changes

### New files
| File | Purpose |
|------|---------|
| `python3.11libs/edini/ui/reflect_worker.py` | `ReflectWorker(QThread)` — HTTP call to LLM for reflection |
| `python3.11libs/edini/ui/knowledge_zone.py` | Knowledge Zone widget (browse + reflection overlay) |
| `python3.11libs/edini/ui/dedup.py` | Jaccard similarity + LLM merge logic |
| `tests/test_dedup.py` | Tests for deduplication |
| `tests/test_reflect_worker.py` | Tests for ReflectWorker (mock HTTP) |

### Modified files
| File | Change | Risk |
|------|--------|------|
| `python3.11libs/edini/ui/main_window.py` | Remove `_maybe_extract_knowledge()`, `_handle_extraction_response()`, `_filter_knowledge_extraction()`, `_KNOWLEDGE_PROMPT_PREFIX`. Replace with `ReflectWorker` trigger on agent done. | **High** — main orchestrator |
| `python3.11libs/edini/ui/context_panel.py` | Replace Knowledge card with `KnowledgeZone` widget. Add `begin_reflection()`, `show_reflection_results()`, `reflection_finished()` signals. | **Medium** |
| `python3.11libs/edini/ui/agent_panel.py` | Remove `show_extraction_results()`, `knowledge_accepted`, `knowledge_rejected` signals, knowledge card UI. | **Medium** — 90 lines removed |
| `python3.11libs/edini/ui/settings_dialog.py` | Add reflection model selection in Knowledge tab. | **Low** |
| `python3.11libs/edini/config.py` | Add `reflection_provider`/`reflection_model` to defaults. Add `get_reflection_model()` helper. | **Low** |
| `python3.11libs/edini/ui/knowledge_store.py` | Add `find_similar()` for Jaccard search. Add `merge_entries()` for combining duplicates. | **Medium** |
| `edini/` mirror | All changed files synced to `edini/` package. | **Low** — copy |

### Removed code
- `main_window._maybe_extract_knowledge()` — 37 lines
- `main_window._handle_extraction_response()` — 19 lines
- `main_window._filter_knowledge_extraction()` — 15 lines
- `main_window._KNOWLEDGE_PROMPT_PREFIX` — 1 line
- `agent_panel.show_extraction_results()` — 10 lines
- `agent_panel._make_knowledge_card()` — 45 lines
- `agent_panel._knowledge_area` widget and related — 30 lines
- `agent_panel.knowledge_accepted/rejected` signals — 2 lines

**Net**: ~160 lines removed from main_window + agent_panel, replaced by ~50 lines of ReflectWorker wiring.

## Architecture

```
Conversation ends
    │
    ▼
main_window._on_agent_done()
    │
    ├─ Existing: snapshot, eval, UI updates
    │
    └─ NEW: _trigger_reflection()
         │
         ▼
    ReflectWorker(QThread)
         │
         ├─ Reads conversation from Pi session .jsonl
         ├─ Reads current knowledge store (rules + entries)
         ├─ Builds prompt with context + criteria + existing knowledge
         ├─ HTTP POST to provider API (chat completions)
         │   Provider: reflection_provider || conversation provider
         │   Model: reflection_model || conversation model
         │   API key: from pi auth.json
         ├─ Parses JSON response → list of items
         ├─ Dedup: Jaccard check against existing → flag merges
         ├─ [If merges needed] Second HTTP call for LLM merge
         └─ Emits: reflection_done(items, merges)
              │
              ▼
    KnowledgeZone in ContextPanel
         │
         ├─ Shows "Reflecting..." spinner while worker runs
         ├─ Displays extracted items (with merge suggestions)
         ├─ User accepts/rejects per item
         └─ On accept: write to rules.json / entries.json
              │
              ▼
    edini-context picks up new rules on next conversation
```

## Reflect Prompt

```
你是一个知识反思引擎。分析以下 Houdini 对话，提取值得长期记住的知识。

## 当前知识库内容
{existing_rules_and_entries}

## 对话历史
{conversation_messages}

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

## 去重要求
检查每条新提取是否与"当前知识库内容"中的已有条目高度相似。
如果相似，用 type:"merge" 并指定 merge_with_id 为已有条目的 id。
合并后的内容应该更通用、更准确。

## 输出格式
JSON 数组，空对话返回 []
[
  {
    "type": "rule" | "entry" | "merge",
    "category": "避坑" | "技巧" | "工作流" | "配置",
    "title": "中文标题（≤30字，要足够通用）",
    "content": "什么问题 + 为什么 + 怎么避免（1-3句，要足够通用）",
    "tags": ["关键词"],
    "merge_with_id": "已有条目id"  // 仅 merge 类型
  }
]
```

## Knowledge Zone UI Layout

```
┌─────────────────────────┐
│ 📚 Knowledge            │  ← Section header
├─────────────────────────┤
│ ▼ Iron Rules (10)       │  ← Collapsible, collapsed by default
│   [避坑] Hou API 主线程  │
│   [避坑] BBox 无 .size() │
│   ... (scrollable)      │
│                         │
│ ▼ Entries (6)           │  ← Collapsible, collapsed by default
│   [技巧] AttribTransfer  │
│   ... (scrollable)      │
├─────────────────────────┤
│ 🔄 Reflecting...        │  ← Only visible during reflection
│ ┌─────────────────────┐ │
│ │ [避坑] New finding   │ │
│ │ 内容摘要...          │ │
│ │ [✓ Accept] [✕ Skip] │ │
│ └─────────────────────┘ │
│ ┌─────────────────────┐ │
│ │ [merge→] 与已有条目  │ │
│ │ 合并后内容...        │ │
│ │ [✓ Accept] [✕ Skip] │ │
│ └─────────────────────┘ │
│ [✓ All] [✕ None]       │
└─────────────────────────┘
```

## API Provider Abstraction

ReflectWorker needs to call different provider APIs. Instead of implementing each provider's protocol, we use a thin adapter:

```python
# Supported providers: deepseek, openai, anthropic, openrouter
def _call_chat_api(provider: str, api_key: str, model: str,
                   messages: list[dict]) -> str:
    """Call provider's chat completions endpoint. Returns assistant content."""
```

Providers supported:
- **deepseek**: `https://api.deepseek.com/v1/chat/completions` (OpenAI-compatible)
- **openai**: `https://api.openai.com/v1/chat/completions`
- **anthropic**: `https://api.anthropic.com/v1/messages` (different format)
- **openrouter**: `https://openrouter.ai/api/v1/chat/completions` (OpenAI-compatible)
- **Custom**: User-added providers with custom base URL

Most providers are OpenAI-compatible. Anthropic needs a separate adapter (2 header differences + message format).

## Reading Conversation Context

ReflectWorker needs the full conversation. Two approaches:

**Option A**: Read from Pi's session .jsonl file directly.  
✅ No Pi RPC dependency. ❌ Need to know the session file path.

**Option B**: Use `rpc_client.send_get_messages()` to fetch from Pi.  
✅ Always current. ❌ Asynchronous, needs callback.

**Chosen: Option A** — `main_window._current_session_path` already tracks the .jsonl path. Read it directly with Python's json module (one JSON object per line).

## Synchronization Checklist

After implementation:
1. Sync all changed files from `python3.11libs/edini/` to `edini/`
2. Run `python -m pytest tests/ -v` — all tests pass
3. Manual test: open Houdini → start conversation → finish → verify reflection runs in Knowledge Zone
4. Verify knowledge extraction no longer appears in main timeline
5. Verify settings dialog shows reflection model selector
6. Verify `_filter_knowledge_extraction` removal doesn't break message display
7. Verify dedup: trigger reflection on same conversation twice → second time should find no new items

## Open Questions (resolved during implementation)

- Q: Should reflection auto-run or require button press?  
  A: Auto-run (same as current), with setting to disable. The "knowledge_enabled" setting already exists.

- Q: What if reflection fails (API error, timeout)?  
  A: Silent failure — show error in Knowledge Zone, don't block user. Timeout: 30 seconds.

- Q: Max items per reflection?  
  A: 5. Prompt says "prefer 0-3 high-quality items over many mediocre ones."

- Q: Should merge suggestions be auto-applied or require confirmation?  
  A: Require confirmation — user sees both old and merged content, accepts or rejects.
