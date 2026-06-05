# UI 字体协调优化 — 设计文档

**日期**: 2026-06-05
**目标**: 解决文字显示不全/裁切问题，统一字号层级，让整体 UI 更协调。

---

## 问题诊断

1. **字号层级混乱** — 6 种字号 (fs(9)~fs(13))，同语义元素大小不一致
2. **历史面板不用 `fs()`** — `history_panel.py` 直接写 raw pt 值，字体缩放滑块对其无效
3. **代码块字号硬编码** — `agent_panel.py` 中 `_format_message` 的 code/pre 使用 `font-size:10pt/11pt`
4. **固定高度裁切** — 面板的 `COLLAPSED_H`、`EXPANDED_H`、`input_edit.setFixedHeight` 不随字号变化
5. **固定宽度溢出** — 知识徽章 `setFixedWidth(32/36)` 在字号放大后文字跑出边界

---

## 字号层级方案

统一为 4 层，全部使用 `fs()` 缩放：

| 层级 | 基准 | 适用元素 |
|------|------|---------|
| **标题 (header)** | `fs(13)` | 面板标题、Section 标签 |
| **正文 (body)** | `fs(12)` | 聊天气泡、QLabel、按钮、菜单、列表、输入框 |
| **辅文 (detail)** | `fs(11)` | Thinking 内容、工具卡片、卡片标签/值、知识详情、树节点、选项卡 |
| **注释 (caption)** | `fs(10)` | 状态栏、进度条、分隔符、折叠头文字、徽章小字、tooltip |

**关键变化**：取消 `fs(9)`，所有 fs(9) 元素提升为 fs(10)。

---

## 逐文件修改清单

### 1. `theme.py` (全局样式表)

- `QStatusBar`: `fs(11)` → `fs(10)`
- `QProgressBar`: 保持 `fs(10)`
- `QCheckBox`: `fs(11)` → `fs(10)`
- `QToolTip`: 保持 `fs(10)`
- 其余保持 `fs(12)`

### 2. `history_panel.py`

- 所有硬编码 `"12pt"`、`"11pt"`、`"10pt"` → `fs(12)`、`fs(11)`、`fs(10)`
- title：`fs(13)`
- session title：`fs(12)`
- meta：`fs(11)`（原 `10pt`）
- updated：`fs(10)`（原 `10pt`）

### 3. `agent_panel.py`

- `_format_message` 代码块：`font-size:10pt/11pt` → `fs(10)`/`fs(11)`
- `_thinking_collapsed_style`: `fs(11)` → `fs(10)`
- `_thinking_expanded_style`: `fs(11)` → `fs(10)`
- Tool card name: `fs(11)` → `fs(11)` 不变
- Tool card status/args/result: `fs(10)` → `fs(10)` 不变
- Thinking/tool toggle: `fs(10)` → `fs(10)` 不变
- Knowledge title: `fs(11)` → 保持
- Knowledge detail: `fs(10)` → 保持
- Type toggle badge: `fs(9)` → `fs(10)`
- Category label: `fs(9)` → `fs(10)`
- 知识徽章 `setFixedWidth(36)` → `setFixedWidth(40)`（容纳 fs(10) 的"铁律"两字）
- 分类标签 `setFixedWidth(32)` → `setFixedWidth(40)`
- Error banner: `fs(11)` → 保持

### 4. `change_tree_widget.py`

- Toggle label: `fs(10)` → 保持
- Undo/Redo buttons: `fs(10)` → 保持
- Tree widget: `fs(11)` → 保持
- `COLLAPSED_H = 22` → `24`
- `EXPANDED_H = 260` → `280`

### 5. `context_panel.py`

- Card header: `fs(11)` → `fs(12)`
- Card label/value: `fs(11)` → 保持
- 微调 `_card_row` 的 `lbl.setFixedWidth(50)` → `56`

### 6. `knowledge_dialog.py`

- 对话框标签/输入框: `fs(11)` → `fs(12)`
- 列表/搜索/过滤: `fs(11)` → `fs(12)`
- 详情区域: `fs(11)` → 保持
- 选项卡: `fs(11)` → `fs(12)`

---

## 验证清单

- [ ] `fs()` 缩放滑块 0.8~1.4 全范围内无裁切
- [ ] 历史面板标题和元数据响应缩放
- [ ] 代码块字号响应缩放
- [ ] 知识徽章文字不溢出
- [ ] 面板折叠头文字完整显示
- [ ] 无视觉回归（控件对齐、间距不变）
