# Timeline History, Knowledge Filter, Change Tree — Design Spec

**Date:** 2026-06-05
**Status:** Draft

---

## 1. 问题总览

| # | 问题 | 根因 | 严重程度 |
|---|------|------|---------|
| 1 | 切换历史再切回后气泡分裂、间距大 | `_render_stored_assistant_message` 中每个 JSONL entry 单独生成 bubble + separator；流式对话只有一个大 bubble | 高 |
| 2 | 知识提取对话出现在历史中 | `_maybe_extract_knowledge()` 走正常 `send_prompt`，pi 将其写入 JSONL；加载历史时一并渲染 | 中 |
| 3 | 变更树误报参数修改（agent 只读节点也显示大量修改） | `diff_snapshots()` 对比所有参数，包括 Houdini 自变参数（time、frame、自动计算值等） | 高 |
| 4 | 切换/新建对话时变更树不清 | `_on_session_selected` / `_on_new_session` / `_on_back_to_current` 只清 timeline，不清 change tree | 中 |

---

## 2. 方案设计

### 2.1 气泡合并（问题 1）

**改 `main_window.py` 中的消息加载逻辑**（而非 agent_panel.py）：

当前：
```python
for m in messages:
    if role == "user":
        self.agent_panel._append_user_message(content)
    elif role == "assistant":
        self.agent_panel._render_stored_assistant_message(m)
```

改为：遍历 messages 时，将**连续的 assistant messages（中间无 user 打断）合并为一个**：

```
[messages list]
user: "创建烟雾"
assistant: "好的..." (text block 1)
assistant: "继续..." (text block 2 — tool call 导致的第二个 entry)
user: "改成红色"

↓ 合并后 ↓

user: "创建烟雾"
assistant: "好的...\n\n继续..."  ← 合并为一个 bubble
user: "改成红色"
```

合并后调用现有的 `_append_assistant_message()`（直接用 `_format_full` 渲染单个气泡）。

thinking 段落也合并，附加到 assistant bubble 的 thinking panel 中。

**影响**：修改 `_on_session_selected`、`_on_back_to_current`、`_on_pi_messages_received` 三处加载逻辑。

### 2.2 知识提取过滤（问题 2）

在 `load_pi_messages()` 或加载后的过滤阶段，识别并移除知识提取的对话。

**识别规则**：
- User message 以 `"Review the conversation above and identify mistakes"` 开头
- 紧随其后的 assistant response 也一并移除

**插桩位置**：在 `main_window.py` 的三处加载点，收到 messages 列表后、渲染前，调用 `_filter_knowledge_extraction(messages)` 过滤。

```python
def _filter_knowledge_extraction(messages: list) -> list:
    """Remove knowledge extraction turns from message list."""
    result = []
    skip_next = False
    for m in messages:
        role = m.get("role", "")
        content = m.get("content", "")
        if role == "user" and isinstance(content, str):
            if content.startswith("Review the conversation above and identify mistakes"):
                skip_next = True
                continue
        if skip_next and role == "assistant":
            skip_next = False
            continue
        result.append(m)
    return result
```

### 2.3 变更树误报过滤（问题 3）

在 `snapshot_engine.py` 的 `diff()` 函数里，对参数变更做过滤：

**排除的自变参数**（Houdini 自动更新，非用户行为）：
- `time` — 时间相关
- `*frame*` — 任何含 "frame" 的参数
- `*seed*` — 随机种子类
- `*cache*` — 缓存相关

**浮点微差合并**：如果 `old` 和 `new` 都是数值，差值 < 1e-6 则视为未变更。

**新增辅助函数** `_is_auto_param(name)` 判断参数是否应忽略。

### 2.4 变更树清除（问题 4）

在以下三处添加 `self.agent_panel.change_tree_widget.clear_all()`：
- `_on_new_session()` — 新建对话
- `_on_session_selected()` — 点击历史对话
- `_on_back_to_current()` — 从浏览模式返回

同时 `_undo_stack` 和 `_undo_pointer` 也需要重置。

---

## 3. 涉及文件

| 文件 | 改动 |
|------|------|
| `python3.11libs/edini/ui/main_window.py` | ① 消息合并逻辑（气泡合并）；② 知识提取过滤；③ 三处添加 `clear_all` + undo 栈重置 |
| `python3.11libs/edini/ui/snapshot_engine.py` | `diff()` 添加自变参数过滤 + 浮点微差合并 |

---

## 4. 不变项

- `agent_panel.py` 不修改（`_render_stored_assistant_message` 保留但不再被调用，或者保留给 `_on_pi_messages_received` 的 fallback 路径）
- Timeline 智能滚动逻辑
- Tool card / Thinking panel / Knowledge area
- Pi RPC 协议

---

## 5. 测试要点

1. **气泡合并** — 一个有 tool call 的对话，切到历史再切回，应显示为单个大气泡 + thinking + tool cards，不走样
2. **知识过滤** — 开启 knowledge extraction 后完成一轮对话，再切换到该会话历史，"Review..." 开头的对话不应出现
3. **误报过滤** — agent 只调用 `houdini_get_scene_info` 并描述节点后，变更树应显示 "No changes"，而非一堆 modified params
4. **变更树清除** — 新建对话 → 历史列表为空；切历史 → 变更树显示对应会话的改动；切回当前 → 变更树正确
5. **undo/reset** — undo 栈在切换/新建时重置，旧的 undo entry 不可用
