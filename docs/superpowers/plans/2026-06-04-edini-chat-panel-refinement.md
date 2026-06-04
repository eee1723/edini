# Edini 对话面板优化 - 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Edini 对话面板从基础流式气泡 UI，升级为 Pi CLI 风格的双层折叠消息时间线 + 独立 Session 管理 + 卡片式 Context + 完整设置系统

**Architecture:** 修改现有 `python3.11libs/edini/ui/` 下的 6 个核心文件，新增 model_history 存储和 viewport 截图模块。保持现有三栏 QSplitter 框架，重写 agent_panel（双层折叠 + 智能滚动 + Copy 按钮），增强 session_store（压缩摘要），重构 context_panel（卡片式），重做 settings_dialog（Provider 下拉 + Model 历史记忆），修复 theme/font 设置不生效问题。

**Tech Stack:** Python 3.11 / PySide6 / Hou Module / JSON 本地存储

---

## 文件结构

```
python3.11libs/edini/
├── config.py                    ← 修改: 增加 theme_color/font_scale/model_history 持久化
├── ui/
│   ├── theme.py                 ← 修改: 字体分层常量 + refresh_window_theme()
│   ├── agent_panel.py           ← 重写: 双层折叠/Copy/智能滚动
│   ├── context_panel.py         ← 重写: 卡片式 Pi Status + Scene
│   ├── history_panel.py         ← 修改: 会话元数据展示 + 重命名 + 压缩标记
│   ├── settings_dialog.py       ← 重写: Provider 下拉 + Model 历史
│   ├── session_store.py         ← 修改: 压缩摘要 + 上下文重建辅助
│   ├── main_window.py           ← 修改: 信号适配 + Theme 刷新 + Session 切换增强
│   ├── viewport.py              ← 新增: Houdini Viewport 截图
│   └── model_history.json       ← 新增: model name 历史记录
```

---

## Phase 1: 基础设施 — Theme/Font 修复 + Config 扩展

### Task 1.1: 扩展 config.py — theme_color / font_scale / model_history

**Files:**
- Modify: `python3.11libs/edini/config.py`

- [ ] **Step 1: 在 _DEFAULTS 中增加新字段**

在 `_DEFAULTS` 字典中添加 `theme_color` 和 `font_scale`:

```python
_DEFAULTS: dict[str, Any] = {
    "api_key": "",
    "provider": "deepseek",
    "model_id": "deepseek-chat",
    "theme_color": "cyan",
    "font_scale": 1.0,
}
```

- [ ] **Step 2: 增加 model_history 读写函数**

在文件末尾添加:

```python
_MODEL_HISTORY_FILE = Path(__file__).resolve().parent / "model_history.json"
_MAX_MODEL_HISTORY = 10


def get_model_history() -> list[str]:
    """Return list of previously used model names, newest first."""
    if _MODEL_HISTORY_FILE.exists():
        try:
            with open(_MODEL_HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return []


def add_model_history(model_name: str) -> None:
    """Add a model name to history, keeping last 10 unique entries."""
    history = get_model_history()
    if model_name in history:
        history.remove(model_name)
    history.insert(0, model_name)
    history = history[:_MAX_MODEL_HISTORY]
    with open(_MODEL_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)
```

- [ ] **Step 3: Commit**

```bash
git add python3.11libs/edini/config.py
git commit -m "feat: add theme_color/font_scale to config defaults and model_history storage"
```

### Task 1.2: 修复 theme.py — 字体分层常量 + 强制刷新

**Files:**
- Modify: `python3.11libs/edini/ui/theme.py`

- [ ] **Step 1: 重写 set_font_scale — 从 config 读取并持久化**

将现有的 `set_font_scale` 扩展为从 config 同步:

```python
def set_font_scale(v: float):
    global _font_scale
    _font_scale = max(0.8, min(1.4, v))
    # Persist to settings
    from edini.config import save_settings
    save_settings({"font_scale": v})
```

- [ ] **Step 2: 重写 set_theme — 从 config 持久化**

```python
def set_theme(key: str):
    global _theme_key
    if key in THEMES:
        _theme_key = key
        from edini.config import save_settings
        save_settings({"theme_color": key})
```

- [ ] **Step 3: 增加 refresh_window_theme() 函数**

在文件末尾添加:

```python
def refresh_window_theme(window) -> None:
    """Force reapply stylesheet on the window (used after settings change)."""
    window.setStyleSheet(build_stylesheet())
    window.repaint()
```

- [ ] **Step 4: 增加 init_theme_from_config() 启动初始化函数**

在文件末尾添加:

```python
def init_theme_from_config() -> None:
    """Load theme/font_scale from config at startup."""
    from edini.config import get_settings
    settings = get_settings()
    global _theme_key, _font_scale
    tc = settings.get("theme_color", "cyan")
    if tc in THEMES:
        _theme_key = tc
    fs_val = settings.get("font_scale", 1.0)
    _font_scale = max(0.8, min(1.4, float(fs_val)))
```

- [ ] **Step 5: 修正 build_stylesheet — 用 pt 替代 px，移除全局 font-size 覆盖，改为元素级**

将 `build_stylesheet()` 中的 `QWidget` 行（全局 font-size）改为元素独立:
- `QTextBrowser`: `font-size: {fs(12)}`
- `QPlainTextEdit`: `font-size: {fs(13)}`
- `QPushButton`: `font-size: {fs(12)}`
- `QStatusBar`: `font-size: {fs(11)}`
- `QListWidget`: `font-size: {fs(12)}`
- `QComboBox`: `font-size: {fs(12)}`
- `QCheckBox`: `font-size: {fs(11)}`
- `QLabel`: `font-size: {fs(12)}` (基础)

将 `fs()` 改为输出 pt 而非 px:
```python
def fs(base: int) -> str:
    return f"{int(base * _font_scale)}pt"
```

- [ ] **Step 6: 验证 Python 导入**

```bash
cd /e/edini && python -c "
import sys; sys.path.insert(0, 'python3.11libs')
from edini.ui.theme import init_theme_from_config, build_stylesheet, fs
init_theme_from_config()
print('fs(12)=', fs(12))
print('OK')
"
```
Expected: `fs(12)= 12pt` (or `10pt` if scale 0.8)

- [ ] **Step 7: Commit**

```bash
git add python3.11libs/edini/ui/theme.py
git commit -m "fix: theme font layering with pt units, config persistence, refresh_window_theme()"
```

### Task 1.3: 更新 main_window.py — 启动时加载 theme 配置 + 信号连接 theme 刷新

**Files:**
- Modify: `python3.11libs/edini/ui/main_window.py`

- [ ] **Step 1: 在 _build_ui 开头调用 init_theme_from_config**

在 `_build_ui` 方法第一行添加:

```python
def _build_ui(self):
    from edini.ui.theme import init_theme_from_config
    init_theme_from_config()
    apply_theme(self)
    # ... rest unchanged
```

- [ ] **Step 2: 在 _bootstrap 中从 config 加载并应用到 Context Panel**

修改现有 `_bootstrap` 中的 settings 使用:

```python
def _bootstrap(self):
    self._tool_executor.start()
    self._rpc_client.start()
    self.history_panel.load_sessions()
    self.context_panel.refresh_scene_info()
    settings = get_settings()
    self.context_panel.set_provider_model(
        settings.get("provider", "deepseek"),
        settings.get("model_id", "deepseek-chat"),
    )
    from edini.ui.hotkey import install_event_filter
    install_event_filter()
```

保持现有代码不变（已正确）。

- [ ] **Step 3: 增加 _on_settings_changed() 信号处理 — settings_dialog 保存后主窗口收到通知**

在 `_bind_events` 中不需要额外绑定（通过 windows.py 单例处理）。但需要在打开设置保存后调用 `refresh_window_theme`。

修改 `_bootstrap` 或新增一个方法供 windows.py 调用:

```python
def refresh_theme(self):
    """Called externally after settings change to reapply theme."""
    from edini.ui.theme import init_theme_from_config, refresh_window_theme
    init_theme_from_config()
    refresh_window_theme(self)
```

- [ ] **Step 4: Commit**

```bash
git add python3.11libs/edini/ui/main_window.py
git commit -m "feat: integrate theme config loading at startup and add refresh_theme()"
```

---

## Phase 2: 消息时间线 — 双层折叠 + Copy + 智能滚动

### Task 2.1: 重写 agent_panel.py — 核心消息单元结构

**Files:**
- Modify: `python3.11libs/edini/ui/agent_panel.py`

- [ ] **Step 1: 定义消息单元 HTML 渲染常量（气泡结构）**

在文件顶部添加消息结构常量:

```python
# ── Bubble style constants (matching spec ──
BUBBLE_USER_STYLE = (
    'color:#e5e5eb;font-size:{fs};line-height:1.6;'
    'padding:8px 12px;background:#1a3a5c;border-radius:8px;'
    'margin:6px 0 6px 48px;'
)
BUBBLE_AI_STYLE = (
    'color:#e5e5eb;font-size:{fs};line-height:1.6;'
    'padding:8px 12px;background:#1a1a24;border-radius:8px;'
    'margin:6px 48px 6px 0;'
)
THINKING_COLLAPSED_STYLE = (
    'color:{accent};font-size:{fs};cursor:pointer;'
    'background:rgba(0,188,212,0.06);padding:4px 8px;'
    'border-radius:4px;margin:4px 32px 4px 0;display:inline-block;'
)
THINKING_EXPANDED_STYLE = (
    'color:#71717a;font-size:{fs};'
    'background:#0e0e15;padding:4px 8px;'
    'border-left:2px solid {accent};margin:4px 32px 4px 8px;'
)
TOOL_COLLAPSED_STYLE = (
    'color:#80cbc4;font-size:{fs};cursor:pointer;'
    'background:rgba(0,188,212,0.06);padding:4px 8px;'
    'border-radius:4px;margin:4px 32px 4px 0;display:inline-block;'
)
TOOL_EXPANDED_STYLE = (
    'color:#94a3b8;font-size:{fs};'
    'background:#0e0e15;padding:4px 8px;'
    'border-left:2px solid #06b6d4;margin:4px 32px 4px 8px;'
)
SEPARATOR_STYLE = (
    'text-align:center;color:#52525b;font-size:{fs};'
    'margin:10px 0;border-top:1px solid #2a2a3c;padding-top:6px;'
)
```

其中 `{fs}` 和 `{accent}` 在渲染时替换。

- [ ] **Step 2: 添加 thinkings/tools 状态存储**

在 `__init__` 中添加:

```python
self._pending_thinkings: list[str] = []      # thinking steps not yet rendered
self._pending_tools: list[dict] = []          # tool calls not yet rendered
self._thinking_count = 0
```

- [ ] **Step 3: 修改 begin_assistant_message — 初始化本轮缓冲**

```python
def begin_assistant_message(self):
    self._raw_stream_text = ""
    self._streaming = True
    self._pending_thinkings.clear()
    self._pending_tools.clear()
    self._thinking_count = 0
    self._ai_bubble_base = self.timeline_view.toHtml()
```

- [ ] **Step 4: 新增 add_thinking_step() — 追加思考步骤**

```python
def add_thinking_step(self, step_num: int, text: str):
    """Add a thinking step to the current AI response."""
    self._thinking_count += 1
    self._pending_thinkings.append(f"{step_num}. {text}")
```

- [ ] **Step 5: 新增 finalize_ai_message() — 流式结束后渲染完整 AI 单元**

```python
def finalize_ai_message(self):
    """Build the complete AI response unit with thinking/tool fold blocks + final reply."""
    from edini.ui.theme import accent_color, fs
    a = accent_color()
    parts = []

    # Thinking block (collapsed by default)
    if self._pending_thinkings:
        thinking_text = "\n".join(self._pending_thinkings)
        collapsed = (
            f'<div style="{THINKING_COLLAPSED_STYLE.format(accent=a, fs=fs(11))}" '
            f'onclick="document.getElementById(\'thinking_{self._request_count}\').style.display=\'block\';'
            f'this.style.display=\'none\';">'
            f'▸ Thinking ({self._thinking_count} steps)</div>'
        )
        expanded = (
            f'<div id="thinking_{self._request_count}" style="display:none;{THINKING_EXPANDED_STYLE.format(accent=a, fs=fs(11))}">'
            f'<pre style="margin:0;color:#71717a;font-size:{fs(11)};white-space:pre-wrap;background:transparent;">'
            f'{html.escape(thinking_text)}</pre>'
            f'</div>'
        )
        parts.append(collapsed + expanded)

    # Tool blocks (collapsed by default)
    for i, tool in enumerate(self._pending_tools):
        tid = f"tool_{self._request_count}_{i}"
        tool_name = html.escape(tool["name"])
        args_str = html.escape(str(tool.get("args", {})))
        result = tool.get("result", "")
        result_str = html.escape(str(result)) if result else "⏳"

        collapsed = (
            f'<div style="{TOOL_COLLAPSED_STYLE.format(fs=fs(11))}" '
            f'onclick="document.getElementById(\'{tid}\').style.display=\'block\';'
            f'this.style.display=\'none\';">'
            f'▸ 🔧 {tool_name}</div>'
        )
        expanded = (
            f'<div id="{tid}" style="display:none;{TOOL_EXPANDED_STYLE.format(fs=fs(11))}">'
            f'🔧 <b>{tool_name}</b><br>'
            f'<pre style="margin:2px 0;color:#94a3b8;font-size:{fs(11)};white-space:pre-wrap;background:transparent;">'
            f'{args_str}</pre>'
            f'Result: {result_str}'
            f'</div>'
        )
        parts.append(collapsed + expanded)

    # Final reply
    if self._raw_stream_text:
        escaped = html.escape(self._raw_stream_text)
        rendered = _format_message(escaped)
        reply = (
            f'<div style="{BUBBLE_AI_STYLE.format(fs=fs(12))}">{rendered}</div>'
        )
        parts.append(reply)

    # Separator
    parts.append(f'<div style="{SEPARATOR_STYLE.format(fs=fs(10))}">── 本轮结束 ──</div>')

    # Assemble
    unit_html = "".join(parts)
    self.timeline_view.setHtml(self._ai_bubble_base + unit_html)
    self._scroll_to_bottom()
```

- [ ] **Step 6: 修改 add_tool_card — 存储工具调用而非直接渲染**

```python
def add_tool_card(self, tool_name: str, args: dict, tool_call_id: str = ""):
    """Store tool call for final rendering in AI unit."""
    self._pending_tools.append({
        "name": tool_name,
        "call_id": tool_call_id,
        "args": args,
        "result": "",
    })
```

- [ ] **Step 7: 新增 set_tool_result() — 工具执行完毕后更新结果**

```python
def set_tool_result(self, tool_call_id: str, result: str):
    """Update the result of a tool call."""
    for tool in self._pending_tools:
        if tool["call_id"] == tool_call_id:
            tool["result"] = result
            break
```

- [ ] **Step 8: 修改 finish_streaming — 调用 finalize_ai_message**

```python
def finish_streaming(self):
    self._streaming = False
    self._stream_flush_timer.stop()
    if hasattr(self, '_pending_thinkings'):
        self.finalize_ai_message()
    else:
        # Fallback: old-style single bubble
        if self._raw_stream_text:
            escaped = html.escape(self._raw_stream_text)
            rendered = _format_message(escaped)
            bubble = (
                f'<div style="{BUBBLE_AI_STYLE.format(fs=fs(12))}">{rendered}</div>'
            )
            self.timeline_view.setHtml(self._ai_bubble_base + bubble)
    self._raw_stream_text = ""
```

### Task 2.2: 智能滚动 — 用户手动上滚时停止自动跟随

**Files:**
- Modify: `python3.11libs/edini/ui/agent_panel.py`

- [ ] **Step 1: 在 _build_ui 中连接滚动条信号**

在 `_build_ui` 的 Timeline 创建后添加:

```python
self.timeline_view.verticalScrollBar().valueChanged.connect(self._on_user_scroll)
self._user_scrolled_up = False
```

- [ ] **Step 2: 添加 _on_user_scroll handler**

```python
def _on_user_scroll(self, value: int):
    sb = self.timeline_view.verticalScrollBar()
    max_val = sb.maximum()
    self._user_scrolled_up = (max_val - value) > 50
```

- [ ] **Step 3: 修改 _scroll_to_bottom — 尊重用户意图**

```python
def _scroll_to_bottom(self):
    if not self._user_scrolled_up:
        sb = self.timeline_view.verticalScrollBar()
        sb.setValue(sb.maximum())
```

- [ ] **Step 4: 修改 _flush_stream — 结尾调 _scroll_to_bottom**

在 `_flush_stream` 的最后添加 `self._scroll_to_bottom()`.

### Task 2.3: Copy 按钮 — 代码块复制功能

**Files:**
- Modify: `python3.11libs/edini/ui/agent_panel.py`

- [ ] **Step 1: 增加 _format_message — 在代码块右上角嵌入 Copy 按钮**

修改 `_format_message` 函数中的代码块替换:

```python
def _format_message(text: str) -> str:
    out = text
    # Code blocks with Copy button
    def _code_block_replacer(m):
        lang = m.group(1) or ""
        code = html.escape(m.group(2))
        copy_btn = (
            f'<button onclick="navigator.clipboard.writeText(this.parentElement'
            f'.querySelector(\'code\').innerText)" '
            f'style="float:right;background:#2a2a3c;color:#a1a1aa;border:none;'
            f'border-radius:3px;padding:2px 8px;cursor:pointer;font-size:10pt;">'
            f'📋 Copy</button>'
        )
        return (
            f'<div style="position:relative;margin:4px 0;">'
            f'{copy_btn}'
            f'<pre style="background:#0e0e15;color:#d4d4d4;padding:8px;'
            f'border-radius:4px;font-family:monospace;font-size:11pt;'
            f'overflow-x:auto;margin:0;"><code>{code}</code></pre>'
            f'</div>'
        )
    out = re.sub(r'```(\w*)\n(.*?)```', _code_block_replacer, out, flags=re.DOTALL)
    # ... rest unchanged
```

- [ ] **Step 2: Commit**

```bash
git add python3.11libs/edini/ui/agent_panel.py
git commit -m "feat: double-layer collapse timeline, smart scroll, Copy buttons on code blocks"
```

### Task 2.4: main_window 适配 — Thinking 事件传递 + Tool Result 传递

**Files:**
- Modify: `python3.11libs/edini/ui/main_window.py`
- Check: `python3.11libs/edini/ui/chat_runtime.py`
- Check: `python3.11libs/edini/rpc_client.py`

- [ ] **Step 1: 在 chat_runtime.py 中增加 thinking_chunk 信号**

在 `ChatRuntime` 类中添加信号和绑定:

```python
thinking_chunk = Signal(str)  # thinking delta text

# In _bind():
r.text_delta.connect(self._on_text_delta)
def _on_text_delta(self, text: str):
    self.stream_chunk.emit(text)
```

如果 Pi 的 JSON-RPC 协议中有 thinking 事件（即 `assistantMessageEvent.type == "thinking_delta"`），需要在 rpc_client.py 中区分:

```python
# In _dispatch_event:
if delta.get("type") == "thinking_delta":
    self.thinking_delta.emit(delta.get("delta", ""))
elif delta.get("type") == "text_delta":
    self.text_delta.emit(delta.get("delta", ""))
```

如果 Pi 当前协议没有区分 thinking/text，则此步骤跳过，留到 Phase 5 补充。

- [ ] **Step 2: 在 main_window 中连接 tool_execution_end 信号**

当前设计: Pi 发送 `tool_execution_start` → `tool_execution_end`（含 result）。需要在 rpc_client.py 中添加:

```python
tool_result = Signal(str, str, str)  # tool_name, tool_call_id, result

# In _dispatch_event:
elif event_type == "tool_execution_end":
    self.tool_result.emit(
        event.get("toolName", ""),
        event.get("toolCallId", ""),
        event.get("result", ""),
    )
```

然后在 main_window 中连接:

```python
self._chat_runtime.tool_completed.connect(self._on_tool_result)

def _on_tool_result(self, tool_name: str, tool_call_id: str, result: str):
    self.agent_panel.set_tool_result(tool_call_id, result)
```

如果 Pi 当前协议没有 `tool_execution_end`，则此步骤跳过，留到后续版本。

- [ ] **Step 3: Commit**

```bash
git add python3.11libs/edini/ui/main_window.py python3.11libs/edini/ui/chat_runtime.py python3.11libs/edini/rpc_client.py
git commit -m "feat: wire thinking_delta and tool_completed through chat runtime"
```

---

## Phase 3: Session 管理 — 压缩摘要 + 上下文重建 + 面板元数据

### Task 3.1: 增强 session_store.py — 压缩摘要和上下文重建

**Files:**
- Modify: `python3.11libs/edini/ui/session_store.py`

- [ ] **Step 1: 扩展 create_session — 增加 compressed_summary 字段**

修改 `create_session` 返回的 record:

```python
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
```

- [ ] **Step 2: 新增 compress_session() — 前 N 轮生成摘要**

```python
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
```

- [ ] **Step 3: 新增 build_context_messages() — 上下文重建辅助**

```python
def build_context_messages(session_id: str, recent_rounds: int = 6) -> list[dict]:
    """Build the list of messages to send to Pi as context.
    
    Returns full messages list if no compression exists.
    Returns [summary_message] + last N rounds if compressed.
    """
    record = load_session(session_id)
    if record is None:
        return []
    
    summary = record.get("compressed_summary", "")
    messages = record.get("messages", [])
    
    if summary:
        # Insert summary as a system context message
        summary_msg = {
            "role": "user",
            "content": f"[Previous session context: {summary}]",
            "is_context_summary": True,
        }
        # Take last N user+assistant pairs
        recent = messages[-(recent_rounds * 2):]
        return [summary_msg] + recent
    else:
        return messages


def get_session_stats(session_id: str) -> dict:
    """Return metadata for session list: rounds, created, updated, compressed."""
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
```

- [ ] **Step 4: 修改 append_message — 增加 timestamp**

```python
def append_message(session_id: str, msg: dict):
    record = load_session(session_id)
    if record is None:
        record = create_session(session_id)
    if "timestamp" not in msg:
        msg["timestamp"] = datetime.now().isoformat()
    record.setdefault("messages", []).append(msg)
    save_session(record)
```

- [ ] **Step 5: 新增 rename_session()**

```python
def rename_session(session_id: str, new_title: str) -> None:
    record = load_session(session_id)
    if record is None:
        return
    record["title"] = new_title
    save_session(record)
```

- [ ] **Step 6: Commit**

```bash
git add python3.11libs/edini/ui/session_store.py
git commit -m "feat: add compression summary, context rebuild helper, rename, stats to session_store"
```

### Task 3.2: 增强 history_panel.py — 会话元数据展示

**Files:**
- Modify: `python3.11libs/edini/ui/history_panel.py`

- [ ] **Step 1: 重写 add_session — 使用富文本显示完整元数据**

将 `add_session` 改为使用自定义 widget（非 QListWidgetItem 纯文本），或者使用 QListWidgetItem 的 HTML:

当前 `QListWidgetItem` 可以 setText 为 HTML... 需要确认 PySide6 是否支持。或者改用自定义 QWidget + QVBoxLayout 的方案。

使用 `QListWidget` + 自定义 widget item:

```python
def add_session(self, sid: str, title: str, created: str, updated: str, rounds: int, compressed: bool):
    item = QtWidgets.QListWidgetItem()
    item.setData(QtCore.Qt.UserRole, sid)
    item.setSizeHint(QtCore.QSize(0, 66))
    
    # Build rich text widget
    widget = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(widget)
    layout.setContentsMargins(8, 6, 8, 6)
    layout.setSpacing(2)
    
    title_label = QtWidgets.QLabel(title)
    title_label.setStyleSheet("font-size:12pt;color:#e5e5eb;font-weight:600;")
    layout.addWidget(title_label)
    
    meta_text = f"Created: {created[:10]}  ·  Updated: {updated[:10]}  ·  {rounds} rounds"
    if compressed:
        meta_text += "  ·  ✓ compressed"
    meta_label = QtWidgets.QLabel(meta_text)
    meta_label.setStyleSheet("font-size:11pt;color:#71717a;")
    layout.addWidget(meta_label)
    
    self.session_list.addItem(item)
    self.session_list.setItemWidget(item, widget)
```

- [ ] **Step 2: 修改 load_sessions — 调用 get_session_stats**

```python
def load_sessions(self):
    self.session_list.clear()
    sessions = list_sessions()
    for s in sessions:
        sid = s["session_id"]
        stats = get_session_stats(sid)
        self.add_session(
            sid,
            s.get("title", "New Session"),
            stats.get("created_at", ""),
            stats.get("updated_at", ""),
            stats.get("rounds", 0),
            stats.get("compressed", False),
        )
```

- [ ] **Step 3: 修改右键菜单 — 增加重命名**

```python
def _on_context_menu(self, pos):
    item = self.session_list.itemAt(pos)
    if not item:
        return
    sid = item.data(QtCore.Qt.UserRole)
    if not sid:
        return
    menu = QtWidgets.QMenu(self)
    rename_action = menu.addAction("Rename")
    delete_action = menu.addAction("Delete")
    action = menu.exec(self.session_list.mapToGlobal(pos))
    if action == delete_action:
        delete_session(sid)
        self.session_deleted.emit(sid)
    elif action == rename_action:
        self._rename_dialog(sid)
```

- [ ] **Step 4: 添加 _rename_dialog**

```python
def _rename_dialog(self, sid: str):
    from edini.ui.session_store import load_session, rename_session
    record = load_session(sid)
    if record is None:
        return
    current = record.get("title", "")
    text, ok = QtWidgets.QInputDialog.getText(
        self, "Rename Session", "Name:", text=current
    )
    if ok and text.strip():
        rename_session(sid, text.strip())
        self.load_sessions()
```

- [ ] **Step 5: 在 _bind 中添加双击重命名**

```python
self.session_list.itemDoubleClicked.connect(self._on_double_click)

def _on_double_click(self, item):
    sid = item.data(QtCore.Qt.UserRole)
    if sid:
        self._rename_dialog(sid)
```

- [ ] **Step 6: Commit**

```bash
git add python3.11libs/edini/ui/history_panel.py
git commit -m "feat: session metadata display, rename via double-click/context menu, compressed badge"
```

### Task 3.3: 更新 main_window.py — Session 上下文重建

**Files:**
- Modify: `python3.11libs/edini/ui/main_window.py`

- [ ] **Step 1: 修改 _on_session_selected — 加载完整消息格式 + 上下文重建**

```python
def _on_session_selected(self, sid: str):
    from edini.ui.session_store import load_session, build_context_messages
    self._current_session_id = sid
    self.agent_panel.clear_timeline()
    
    record = load_session(sid)
    if record is None:
        return
    
    # Load messages into timeline
    msgs = record.get("messages", [])
    for m in msgs:
        role = m.get("role", "")
        content = m.get("content", "")
        if role == "user":
            self.agent_panel._append_user_message(content)
        elif role == "assistant":
            # Re-render with full AI unit structure
            self.agent_panel._render_stored_assistant_message(m)
    
    self.agent_panel.set_session_id(sid)
```

- [ ] **Step 2: 在 _on_send 前构建上下文**

修改 `_on_agent_submit`:

```python
def _on_agent_submit(self, text: str):
    from edini.ui.session_store import build_context_messages, append_message
    
    self.agent_panel.begin_assistant_message()
    
    # Store user message
    if self._current_session_id:
        append_message(self._current_session_id, {
            "role": "user",
            "content": text,
        })
    
    # Build context if switching back to a session
    if self._current_session_id:
        context_msgs = build_context_messages(self._current_session_id)
        # Send context + current prompt to Pi
        for ctx_msg in context_msgs:
            if ctx_msg.get("is_context_summary"):
                # Send as system prompt context
                self._rpc_client.send_command({
                    "type": "set_system_message",
                    "message": ctx_msg["content"],
                })
    
    self._rpc_client.send_prompt(text)
```

- [ ] **Step 3: 在 _on_agent_done 中存储 assistant 消息**

```python
def _on_agent_done(self, _):
    from edini.ui.session_store import append_message
    
    self.agent_panel.finish_streaming()
    self.agent_panel.set_busy(False)
    self.context_panel.refresh_scene_info()
    self._rpc_client.send_get_stats()
    self.status.showMessage("Ready")
    
    # Store assistant message
    if self._current_session_id:
        msg = {
            "role": "assistant",
            "content": self.agent_panel._raw_stream_text,
            "thinking": list(self.agent_panel._pending_thinkings),
            "tools": list(self.agent_panel._pending_tools),
        }
        append_message(self._current_session_id, msg)
    
    # Check context usage for compression trigger
    self._check_compression()
```

- [ ] **Step 4: 添加 _check_compression**

```python
def _check_compression(self):
    """Check if context usage >= 60% and trigger compression if needed."""
    from edini.ui.session_store import compress_session, load_session, get_session_stats
    
    if not self._current_session_id:
        return
    
    # Get latest context usage from context_panel
    ctx_pct = self.context_panel._last_ctx_pct
    if ctx_pct is None or ctx_pct < 60:
        return
    
    record = load_session(self._current_session_id)
    if record is None:
        return
    
    # Already compressed? skip
    if record.get("compressed_summary", ""):
        return
    
    stats = get_session_stats(self._current_session_id)
    rounds = stats.get("rounds", 0)
    if rounds < 5:
        return  # Not enough rounds to compress
    
    messages = record.get("messages", [])
    # Take first 60% of messages for summary
    cutoff = max(1, int(len(messages) * 0.6))
    early_msgs = messages[:cutoff]
    
    # Build summary prompt
    conversation_text = ""
    for m in early_msgs:
        role = m.get("role", "")
        content = m.get("content", "")[:200]
        conversation_text += f"[{role}] {content}\n"
    
    summary = f"Conversation history ({len(early_msgs)} messages):\n{conversation_text}"
    summary = summary[:500]
    
    compress_session(self._current_session_id, summary, cutoff)
```

- [ ] **Step 5: 在 context_panel 中暴露 ctx_pct**

在 `context_panel.py` 的 `set_usage` 中:

```python
self._last_ctx_pct = ctx.get("percent", 0) if ctx else None
```

- [ ] **Step 6: Commit**

```bash
git add python3.11libs/edini/ui/main_window.py python3.11libs/edini/ui/context_panel.py
git commit -m "feat: session context rebuild, message storage, auto-compression at 60% ctx"
```

---

## Phase 4: Context Panel — 卡片式重构 + Settings 改进 + Viewport 截图

### Task 4.1: 重写 context_panel.py — 卡片式分组

**Files:**
- Modify: `python3.11libs/edini/ui/context_panel.py`

- [ ] **Step 1: 创建卡片封装函数 _make_card()**

```python
def _make_card(title: str, parent=None) -> tuple[QtWidgets.QFrame, QtWidgets.QVBoxLayout]:
    """Create a card-style frame with a title header."""
    card = QtWidgets.QFrame(parent)
    card.setStyleSheet("""
        QFrame {
            background: #0e0e15;
            border: 1px solid #2a2a3c;
            border-radius: 6px;
        }
    """)
    layout = QtWidgets.QVBoxLayout(card)
    layout.setContentsMargins(10, 8, 10, 8)
    layout.setSpacing(4)
    
    header = QtWidgets.QLabel(title)
    header.setStyleSheet("font-size:11pt;font-weight:600;color:#71717a;border:none;")
    layout.addWidget(header)
    
    sep = QtWidgets.QFrame()
    sep.setFrameShape(QtWidgets.QFrame.HLine)
    sep.setStyleSheet("border:none;border-top:1px solid #2a2a3c;margin:2px 0;")
    layout.addWidget(sep)
    
    return card, layout
```

- [ ] **Step 2: 重建 ContextPanel._build_ui — 两张卡片**

```python
def __init__(self, parent=None):
    super().__init__(parent)
    self._last_ctx_pct = None
    
    layout = QtWidgets.QVBoxLayout(self)
    layout.setContentsMargins(8, 8, 8, 8)
    layout.setSpacing(8)
    
    # Card 1: Pi Status
    pi_card, pi_layout = _make_card("Pi Status", self)
    
    self.status_label = QtWidgets.QLabel("● Connecting...")
    self.status_label.setStyleSheet("color:#a1a1aa;font-size:12pt;border:none;")
    pi_layout.addWidget(self.status_label)
    
    self.provider_model_label = QtWidgets.QLabel("deepseek / deepseek-chat")
    self.provider_model_label.setStyleSheet("color:#71717a;font-size:11pt;border:none;")
    pi_layout.addWidget(self.provider_model_label)
    
    pi_layout.addWidget(_card_space(4))
    
    # Token row
    self.token_in_label = QtWidgets.QLabel("In: -")
    self.token_out_label = QtWidgets.QLabel("Out: -")
    self.token_total_label = QtWidgets.QLabel("Total: -")
    self.cost_label = QtWidgets.QLabel("Cost: -")
    for lbl in [self.token_in_label, self.token_out_label, self.token_total_label, self.cost_label]:
        lbl.setStyleSheet("color:#a1a1aa;font-size:11pt;border:none;")
        pi_layout.addWidget(lbl)
    
    pi_layout.addWidget(_card_space(4))
    
    self.ctx_label = QtWidgets.QLabel("Context: -")
    self.ctx_label.setStyleSheet("color:#a1a1aa;font-size:11pt;border:none;")
    pi_layout.addWidget(self.ctx_label)
    
    self.ctx_progress = QtWidgets.QProgressBar()
    self.ctx_progress.setMinimum(0)
    self.ctx_progress.setMaximum(100)
    self.ctx_progress.setValue(0)
    self.ctx_progress.setTextVisible(True)
    self.ctx_progress.setFormat("0%")
    self.ctx_progress.setFixedHeight(14)
    pi_layout.addWidget(self.ctx_progress)
    
    layout.addWidget(pi_card)
    
    # Card 2: Scene Info
    scene_card, scene_layout = _make_card("Scene", self)
    
    self.hip_label = QtWidgets.QLabel("HIP: -")
    self.path_label = QtWidgets.QLabel("Path: -")
    self.selected_label = QtWidgets.QLabel("Selected: -")
    self.node_count_label = QtWidgets.QLabel("Nodes: -")
    for lbl in [self.hip_label, self.path_label, self.selected_label, self.node_count_label]:
        lbl.setStyleSheet("color:#a1a1aa;font-size:11pt;border:none;")
        scene_layout.addWidget(lbl)
    
    self.refresh_btn = QtWidgets.QPushButton("⟳ Refresh")
    self.refresh_btn.setObjectName("GhostButton")
    self.refresh_btn.clicked.connect(self.refresh_scene_info)
    scene_layout.addWidget(self.refresh_btn)
    
    layout.addWidget(scene_card)
    layout.addStretch(1)


def _card_space(h: int) -> QtWidgets.QWidget:
    w = QtWidgets.QWidget()
    w.setFixedHeight(h)
    w.setStyleSheet("background:transparent;border:none;")
    return w
```

- [ ] **Step 3: 保持其余方法不变（set_pi_status, set_provider_model, set_usage, refresh_scene_info）**

以上方法已经正确，不需要修改。只需在 `set_usage` 中添加 `self._last_ctx_pct` 赋值（已在 Phase 3 中完成）。

- [ ] **Step 4: Commit**

```bash
git add python3.11libs/edini/ui/context_panel.py
git commit -m "refactor: card-based context panel with Pi Status and Scene sections"
```

### Task 4.2: 重写 settings_dialog.py — Provider 下拉 + Model 历史记忆 + Theme 实时生效

**Files:**
- Modify: `python3.11libs/edini/ui/settings_dialog.py`

- [ ] **Step 1: 重写 Provider 选择为 QComboBox 下拉**

```python
# Replace QLineEdit for provider with QComboBox
PROVIDERS = ["deepseek", "anthropic", "openai", "google"]

self._provider = QtWidgets.QComboBox()
for p in PROVIDERS:
    self._provider.addItem(p)
current_provider = settings.get("provider", "deepseek")
idx = self._provider.findText(current_provider)
if idx >= 0:
    self._provider.setCurrentIndex(idx)
```

- [ ] **Step 2: Model Name 使用可编辑 QComboBox + 历史记忆**

```python
from edini.config import get_model_history

self._model_combo = QtWidgets.QComboBox()
self._model_combo.setEditable(True)
self._model_combo.setInsertPolicy(QtWidgets.QComboBox.NoInsert)
self._model_combo.lineEdit().setPlaceholderText("model name...")

# Load history
history = get_model_history()
for h in history:
    self._model_combo.addItem(h)
self._model_combo.setCurrentText(settings.get("model_id", "deepseek-chat"))
```

- [ ] **Step 3: Appearance 从 config 读取当前值**

```python
# Theme combo - read from config
current_theme = settings.get("theme_color", "cyan")
self._theme_combo = QtWidgets.QComboBox()
for key, info in THEMES.items():
    self._theme_combo.addItem(info["name"], key)
    if key == current_theme:
        self._theme_combo.setCurrentIndex(self._theme_combo.count() - 1)

# Font scale combo - read from config
current_scale = str(settings.get("font_scale", 1.0))
self._font_scale = QtWidgets.QComboBox()
for val in ["0.8", "0.9", "1.0", "1.1", "1.2", "1.3", "1.4"]:
    self._font_scale.addItem(val)
self._font_scale.setCurrentText(current_scale)
```

- [ ] **Step 4: Save 时存储 model_history 并触发主题刷新**

```python
def _on_save(self):
    from edini.config import save_settings, add_model_history
    
    provider = self._provider.currentText().strip()
    model = self._model_combo.currentText().strip()
    
    save_settings({
        "api_key": self._api_key.text().strip(),
        "provider": provider,
        "model_id": model,
    })
    
    # Save model to history
    if model:
        add_model_history(model)
    
    # Theme and font scale
    theme_key = self._theme_combo.currentData()
    font_val = float(self._font_scale.currentText())
    save_settings({
        "theme_color": theme_key,
        "font_scale": font_val,
    })
    
    # Apply theme changes
    set_theme(theme_key)
    set_font_scale(font_val)
    
    # Notify main window to refresh
    from edini.ui.windows import _main_window
    if _main_window:
        _main_window.refresh_theme()
    
    self.accept()
```

- [ ] **Step 5: 去除 Tabs，改为单页表单（更简洁）**

将 Provider + Appearance 合并到一页:

```python
layout = QtWidgets.QVBoxLayout(self)
layout.setSpacing(12)

# Provider section
layout.addWidget(QtWidgets.QLabel("<b>Provider</b>"))
layout.addWidget(self._provider)
layout.addWidget(QtWidgets.QLabel("<b>Model Name</b>"))
layout.addWidget(self._model_combo)
layout.addWidget(QtWidgets.QLabel("<b>API Key</b>"))
layout.addWidget(self._api_key)

layout.addSpacing(12)

# Appearance section
layout.addWidget(QtWidgets.QLabel("<b>Appearance</b>"))
app_row = QtWidgets.QHBoxLayout()
app_row.addWidget(QtWidgets.QLabel("Theme:"))
app_row.addWidget(self._theme_combo)
app_row.addWidget(QtWidgets.QLabel("Font:"))
app_row.addWidget(self._font_scale)
layout.addLayout(app_row)
```

- [ ] **Step 6: Commit**

```bash
git add python3.11libs/edini/ui/settings_dialog.py
git commit -m "refactor: Provider dropdown, model history ComboBox, theme live refresh on save"
```

### Task 4.3: 新增 viewport.py — Houdini Viewport 截图

**Files:**
- Create: `python3.11libs/edini/ui/viewport.py`

- [ ] **Step 1: 写 viewport.py**

```python
"""Houdini Viewport screenshot capture for Edini."""
import io
import base64
import importlib

try:
    hou = importlib.import_module("hou")
except Exception:
    hou = None


def capture_viewport() -> str | None:
    """Capture current Houdini viewport as base64 JPEG.
    
    Returns base64-encoded JPEG string, or None if not in Houdini.
    """
    if hou is None:
        return None
    
    try:
        desktop = hou.ui.curDesktop()
        viewport = desktop.paneTabOfType(hou.paneTabType.SceneViewer)
        if viewport is None:
            return None
        
        # Save viewport to temporary in-memory buffer
        buf = io.BytesIO()
        viewport.saveImage(buf, "JPEG", width=1280, height=720)
        buf.seek(0)
        img_bytes = buf.getvalue()
        
        if len(img_bytes) == 0:
            return None
        
        return base64.b64encode(img_bytes).decode("ascii")
    except Exception:
        return None


def is_vision_capable(provider: str, model: str) -> bool:
    """Check if the current model supports image input."""
    vision_providers = {"anthropic", "openai", "google"}
    return provider.lower() in vision_providers
```

- [ ] **Step 2: Commit**

```bash
git add python3.11libs/edini/ui/viewport.py
git commit -m "feat: add Houdini viewport screenshot capture and vision model check"
```

### Task 4.4: 在 agent_panel.py 输入栏集成截图按钮

**Files:**
- Modify: `python3.11libs/edini/ui/agent_panel.py`

- [ ] **Step 1: 在 _build_ui 的 input_row 中添加截图按钮**

在 "仅对话" checkbox 和 "执行" button 之间:

```python
from edini.ui.viewport import is_vision_capable, capture_viewport
from edini.config import get_settings

settings = get_settings()
provider = settings.get("provider", "")
model = settings.get("model_id", "")

self._screenshot_btn = QtWidgets.QPushButton("📷")
self._screenshot_btn.setToolTip("Capture viewport screenshot")
self._screenshot_btn.setFixedWidth(36)
self._screenshot_btn.clicked.connect(self._on_capture_viewport)
self._screenshot_btn.setVisible(is_vision_capable(provider, model))
action_col.addWidget(self._screenshot_btn)
```

- [ ] **Step 2: 添加截图缩略图预览区域**

```python
self._screenshot_preview = QtWidgets.QLabel()
self._screenshot_preview.setFixedSize(160, 90)
self._screenshot_preview.setStyleSheet("border:1px solid #2a2a3c;border-radius:4px;")
self._screenshot_preview.setVisible(False)
self._screenshot_preview.setAlignment(QtCore.Qt.AlignCenter)
action_col.addWidget(self._screenshot_preview)

self._screenshot_remove_btn = QtWidgets.QPushButton("✕ Remove")
self._screenshot_remove_btn.setObjectName("GhostButton")
self._screenshot_remove_btn.clicked.connect(self._on_remove_screenshot)
self._screenshot_remove_btn.setVisible(False)
action_col.addWidget(self._screenshot_remove_btn)
```

- [ ] **Step 3: 添加 _on_capture_viewport**

```python
def _on_capture_viewport(self):
    b64 = capture_viewport()
    if b64 is None:
        return
    self._screenshot_data = b64
    # Show preview
    pixmap = QtGui.QPixmap()
    pixmap.loadFromData(base64.b64decode(b64), "JPEG")
    self._screenshot_preview.setPixmap(pixmap.scaled(160, 90, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation))
    self._screenshot_preview.setVisible(True)
    self._screenshot_remove_btn.setVisible(True)


def _on_remove_screenshot(self):
    self._screenshot_data = None
    self._screenshot_preview.clear()
    self._screenshot_preview.setVisible(False)
    self._screenshot_remove_btn.setVisible(False)
```

- [ ] **Step 4: 修改 _on_send — 发送时附加截图**

```python
def _on_send(self):
    text = self.input_edit.toPlainText().strip()
    if not text or self._busy:
        return
    self.input_edit.clear()
    self._append_user_message(text)
    self._request_count += 1
    self._raw_stream_text = ""
    self._streaming = True
    
    # Attach screenshot if present
    images = None
    if hasattr(self, '_screenshot_data') and self._screenshot_data:
        images = [{"type": "image/jpeg", "data": self._screenshot_data}]
        self._on_remove_screenshot()
    
    self.submit_requested.emit(text)
    # Note: main_window._on_agent_submit needs to accept images
```

- [ ] **Step 5: Commit**

```bash
git add python3.11libs/edini/ui/agent_panel.py
git commit -m "feat: viewport screenshot button with preview and attach to prompt"
```

### Task 4.5: main_window 适配 — 传递 images 参数

**Files:**
- Modify: `python3.11libs/edini/ui/main_window.py`

- [ ] **Step 1: 修改 submit_requested 信号处理**

`agent_panel.submit_requested` 目前 emit(str)。改为 emit(str, list):

在 agent_panel.py 中:

```python
submit_requested = QtCore.Signal(str, object)  # text, images
```

在 main_window.py 中:

```python
self.agent_panel.submit_requested.connect(self._on_agent_submit)

def _on_agent_submit(self, text: str, images=None):
    # ... existing logic ...
    self._rpc_client.send_prompt(text, images=images)
```

- [ ] **Step 2: 修改 agent_panel _on_send emit**

```python
self.submit_requested.emit(text, images)
```

- [ ] **Step 3: Commit**

```bash
git add python3.11libs/edini/ui/agent_panel.py python3.11libs/edini/ui/main_window.py
git commit -m "feat: pass images through submit_requested signal for viewport screenshots"
```

---

## Phase 5: 打磨 — 状态栏 + Abort 反馈 + 验证

### Task 5.1: 完善状态栏信息

**Files:**
- Modify: `python3.11libs/edini/ui/main_window.py`

- [ ] **Step 1: 构建状态栏 HTML**

```python
def _update_statusbar(self):
    """Update status bar with connection, model, nodes, tokens, HIP."""
    parts = []
    
    # Pi status
    status = getattr(self, '_last_pi_status', 'connecting')
    status_icon = {"connected": "●", "connecting": "◌", "disconnected": "○"}.get(status, "●")
    parts.append(f"{status_icon} {status}")
    
    # Model
    settings = get_settings()
    parts.append(f"{settings.get('provider','?')}/{settings.get('model_id','?')}")
    
    # Nodes
    if hou:
        try:
            root = hou.node("/")
            count = len(root.allSubChildren()) if root else 0
            parts.append(f"Nodes:{count}")
        except Exception:
            pass
    
    self.status.showMessage("  │  ".join(parts))
```

- [ ] **Step 2: 在各事件中调用 _update_statusbar**

在 `_on_status_changed`, `_on_agent_done` 中调用 `self._update_statusbar()`.

- [ ] **Step 3: Commit**

```bash
git add python3.11libs/edini/ui/main_window.py
git commit -m "feat: rich status bar with connection, model, node count"
```

### Task 5.2: Abort 视觉反馈

**Files:**
- Modify: `python3.11libs/edini/ui/agent_panel.py`
- Modify: `python3.11libs/edini/ui/main_window.py`

- [ ] **Step 1: 在 agent_panel 添加 abort 状态显示**

```python
def show_aborted(self):
    """Show an abort indicator in the timeline."""
    abort_html = (
        f'<div style="text-align:center;color:#f87171;font-size:11pt;'
        f'margin:8px 0;">── Aborted ──</div>'
    )
    self.timeline_view.setHtml(self.timeline_view.toHtml() + abort_html)
    self.set_busy(False)
    self._raw_stream_text = ""
```

- [ ] **Step 2: 在 main_window 中处理 abort 事件**

```python
# In _bind_events:
self._chat_runtime.failed.connect(self._on_error)

# If there's a specific abort event from Pi, catch it:
# self._rpc_client.agent_aborted.connect(self._on_abort)

def _on_abort(self):
    self.agent_panel.show_aborted()
    self.status.showMessage("Aborted")
```

- [ ] **Step 3: Commit**

```bash
git add python3.11libs/edini/ui/agent_panel.py python3.11libs/edini/ui/main_window.py
git commit -m "feat: visual abort feedback in timeline"
```

### Task 5.3: Esc 热键绑定中止

**Files:**
- Modify: `python3.11libs/edini/ui/hotkey.py`

- [ ] **Step 1: 在 hotkey.py 中注册 Esc**

检查现有 `hotkey.py`，添加 Esc 处理:

```python
def install_event_filter():
    """Install global event filter for hotkeys."""
    try:
        import hou
        main_win = hou.qt.mainWindow()
        if main_win:
            main_win.installEventFilter(_HotkeyFilter(main_win))
    except Exception:
        pass
```

确保 Esc 键在 EdiniMainWindow 上被捕获并调用 abort。

或者更简单——在 agent_panel 的 eventFilter 中已经处理了 KeyPress，扩展:

```python
def eventFilter(self, watched, event):
    if watched is self.input_edit and event is not None:
        if int(event.type()) == int(QtCore.QEvent.KeyPress):
            key = int(event.key())
            if key == int(QtCore.Qt.Key_Escape):
                self.stop_requested.emit()
                return True
            # ... existing Enter handling
    return super().eventFilter(watched, event)
```

- [ ] **Step 2: 连接 stop_requested 到 main_window abort**

```python
# In main_window._bind_events:
self.agent_panel.stop_requested.connect(self._on_abort_request)

def _on_abort_request(self):
    self._rpc_client.send_abort()
    self.agent_panel.show_aborted()
```

- [ ] **Step 3: Commit**

```bash
git add python3.11libs/edini/ui/agent_panel.py python3.11libs/edini/ui/main_window.py
git commit -m "feat: Esc hotkey to abort AI response"
```

### Task 5.4: 完整导入验证

- [ ] **Step 1: 验证所有 Python 文件导入成功**

```bash
cd /e/edini && python -c "
import sys
sys.path.insert(0, 'python3.11libs')

from edini.ui.theme import init_theme_from_config, build_stylesheet, apply_theme, refresh_window_theme, fs
init_theme_from_config()
print('theme OK: fs(12)=', fs(12))

from edini.config import get_settings, save_settings, add_model_history, get_model_history
print('config OK')

from edini.ui.agent_panel import AgentPanel
print('agent_panel OK')

from edini.ui.context_panel import ContextPanel
print('context_panel OK')

from edini.ui.session_store import create_session, get_session_stats, build_context_messages, compress_session
print('session_store OK')

from edini.ui.viewport import is_vision_capable
print('viewport OK')

from edini.ui.settings_dialog import SettingsDialog
print('settings_dialog OK')

from edini.ui.main_window import EdiniMainWindow
print('main_window OK')

print('ALL IMPORTS PASS')
"
```

- [ ] **Step 2: Commit**

```bash
git commit -m "verify: all edini module imports pass"
```

---

## 总结

| Phase | 任务数 | 涉及文件 |
|-------|--------|---------|
| Phase 1: 基础设施 | 3 | config.py, theme.py, main_window.py |
| Phase 2: 消息时间线 | 4 | agent_panel.py, chat_runtime.py, rpc_client.py, main_window.py |
| Phase 3: Session 管理 | 3 | session_store.py, history_panel.py, main_window.py, context_panel.py |
| Phase 4: Context + Settings + 截图 | 5 | context_panel.py, settings_dialog.py, viewport.py, agent_panel.py, main_window.py |
| Phase 5: 打磨 | 4 | main_window.py, agent_panel.py, hotkey.py |

**总计: 19 个 task，修改 10 个文件，新增 1 个文件。**
