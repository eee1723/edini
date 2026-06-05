# Timeline Rendering & Selection — Design Spec

**Date:** 2026-06-05
**Status:** Draft

---

## 1. Motivation

当前 Edini Agent Panel 的时间线渲染存在三个问题：

1. **Markdown 渲染不完整** — 仅支持 `**粗体**`、行内代码、代码块。缺标题、列表、表格、分隔线、斜体。
2. **流式与历史消息渲染不一致** — 流式过程中对不完整文本调用完整解析器，可能出现渲染异常；且完成后的 `finalize()` 效果与历史加载的 `set_stored_content()` 视觉不统一。
3. **文本不可选中** — QLabel 未启用 `TextSelectableByMouse`，用户无法拖选复制文本。
4. **间距过大** — `line-height:1.55` + 双 `<br>` 替换 `\n` 导致段落间视觉松散。

---

## 2. Design

### 2.1 双格式化器策略

```
┌──────────────────────────────────────────────────────────┐
│                     _format_full(text)                    │
│  完整 Markdown → HTML。用于历史加载 + 流式完成后的最终渲染。│
│  支持: 标题/列表/表格/代码块/行内代码/粗体/斜体/分隔线/段落│
└──────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────┐
│                     _format_lite(text)                    │
│  轻量渲染。用于流式过程中的实时展示。                       │
│  支持: 粗体/斜体/行内代码/escape/<br>换行                  │
│  拒绝: 代码块/标题/列表/表格 （不完整语法会导致布局错乱）   │
└──────────────────────────────────────────────────────────┘
```

**调用关系：**

```
流式 chunk → _AiBubble.update_streaming() → _format_lite()
流式结束   → _AiBubble.finalize()         → _format_full()
历史加载   → _AiBubble.set_stored_content() → _format_full()
```

### 2.2 `_format_full()` 规则

处理管道：`\n\n` 分段 → 逐段解析 → `<p>` 包裹 → 全局替换

| 语法 | 优先级 | HTML 输出 |
|------|--------|-----------|
| `# Title` | 段首 | `<h1>` 24px, #e5e5eb, margin:6px 0 |
| `## H2` | 段首 | `<h2>` 20px, #e5e5eb, margin:4px 0 |
| `### H3` | 段首 | `<h3>` 16px, #e5e5eb, margin:2px 0 |
| `---` | 段首（单行） | `<hr>` 1px solid #2a2a3c |
| `- item` / `* item` | 段内多行 | `<ul style="padding-left:20px;margin:2px 0">` 含多个 `<li>` |
| `1. item` | 段内多行 | `<ol style="padding-left:20px;margin:2px 0">` 含多个 `<li>` |
| `\| a \| b \|` | 段内多行（含 `|` 分隔行） | `<table>` 带斑马纹，单元格 `<td>` 左右 padding |
| `` ```lang\n...\n``` `` | 全局（跨段落） | `<pre><code>` + 复制按钮 |
| `**bold**` | 行内 | `<b>` |
| `*italic*` | 行内 | `<i>` |
| `` `code` `` | 行内 | `<code>` #1a1a24 底 + #67e8f9 字色 |
| 普通段落 | 段 | `<p style="margin:2px 0;line-height:1.45;">` |

**处理顺序：**

1. 先提取所有 ` ``` ` 代码块，用占位符 `__CODE_BLOCK_{i}__` 替换，避免内部语法被误解析
2. 按 `\n\n` 分段（代码块占位符不参与分段）
3. 逐段判断类型（header / list / table / hr / paragraph），转为对应 HTML
4. 恢复代码块占位符为完整的 `<pre>` HTML
5. 行内替换（`**bold**`、`*italic*`、行内代码）
6. 行内单个 `\n` → `<br>`

### 2.3 `_format_lite()` 规则

流式过程中的轻量渲染，**不解析多行结构**：

1. `html.escape(text)` 转义全部内容
2. `**bold**` → `<b>bold</b>`
3. `*italic*` → `<i>italic</i>`（需防止匹配到 `**` 内部的 `*`）
4. `` `code` `` → `<code>code</code>`
5. `\n` → `<br>`

不解析代码块——不闭合的 ` ``` ` 会导致后续 `<pre>` 标签错乱，影响后续文本显示。

### 2.4 文本选择

所有气泡 QLabel 统一设置：

```python
self._label.setTextInteractionFlags(
    Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse
)
```

- 鼠标拖选 → Ctrl+C 或右键复制
- 代码块 📋 按钮继续走 `linkActivated` 信号，互不冲突

`_UserBubble` 从 `PlainText` 改为 `RichText` + 相同样式背景，保证选中高亮色一致。

### 2.5 间距调整

| 位置 | 旧值 | 新值 |
|------|------|------|
| bubble `line-height` | `1.55` | `1.45` |
| 段落分隔 | 双 `<br>`（等同一个空行） | `<p>` 自然段落间隔（margin: 2px 0） |
| bubble padding | `10px 16px` | `8px 14px` |

在不拥挤的前提下收窄间距，保持 ChatGPT 风格的舒适感。

### 2.6 代码块 Copy 保持

代码块右上角的 📋 Copy 按钮保持不变。点击后通过 `linkActivated` 信号 + Base64 解码写入剪贴板。

---

## 3. 涉及文件

| 文件 | 改动 |
|------|------|
| `python3.11libs/edini/ui/agent_panel.py` | 重写 `_format_message()` → `_format_full()` + `_format_lite()`；修改 `_AiBubble` / `_UserBubble` 添加选择交互；调整样式常量 |
| `edini/panel.py` | 旧版 panel，可选同步更新（如果仍在使用） |

核心改动只在一个文件：`python3.11libs/edini/ui/agent_panel.py`。

---

## 4. 不变项

- `_TimelineView` 的智能滚动逻辑不修改
- `_ToolCardWidget` 不受影响
- Thinking 面板不受影响
- Knowledge 提取区域不受影响
- 信号连接和事件处理不受影响

---

## 5. 测试要点

1. **流式渲染** — 发一条消息，观察流式过程中文本是否平滑更新，无渲染异常
2. **最终渲染** — 流式完成后，观察 Markdown 格式是否正确渲染（标题/列表/代码块）
3. **历史一致性** — 切换到历史会话，观察渲染效果是否与刚完成的消息一致
4. **代码块半闭合** — 在 ` ``` ` 内发送不完整代码，流式过程不应出现布局错乱
5. **文本选择** — 鼠标拖选气泡内任意文字，右键/Ctrl+C 应能复制
6. **代码块复制** — 点击代码块 📋 Copy 按钮，验证剪贴板内容正确
7. **表格** — 如果 AI 输出表格内容（`| col1 | col2 |`），应正常渲染
8. **列表嵌套** — `- item\n  - subitem` 应正确缩进
