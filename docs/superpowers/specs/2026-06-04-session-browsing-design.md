# Session Browsing Mode — Design

**Date:** 2026-06-04  
**Status:** approved

## Overview

优化 Edini 会话管理系统，解决两个核心问题：

1. 新建会话后旧会话不出现在历史列表（Pi 会话发现逻辑）
2. 浏览历史会话时，"+ 新对话"按钮应变为"← 回到当前"，支持在历史会话上继续聊天

## Data Flow

```
用户点击"+ 新对话"
    │
    ▼
保存当前会话路径为 _active_session_path
清空时间线、重置统计
通知 Pi 创建新会话 (new_session)
    │
    ▼
Pi 写入新 JSONL → 刷新 HistoryPanel 列表

用户发送消息交互
    │
    ▼
Pi 更新同一 JSONL 文件
对话结束后刷新列表（更新消息数）

用户点击历史会话 B
    │
    ▼
_active_session_path = 当前活跃会话路径 (A)
_browsing_session_path = B
HistoryPanel 进入浏览模式，按钮变为"← 回到当前"
时间线渲染 B 的消息（load_pi_messages）
通知 Pi 切换到 B (switch_session)
用户可在 B 上继续聊天

用户点击"← 回到当前"
    │
    ▼
清空 _browsing_session_path
恢复 _active_session_path (A) 到时间线
通知 Pi 切换回 A
HistoryPanel 退出浏览模式，按钮恢复"+ 新对话"
```

## States & Transitions

### HistoryPanel 模式

| 模式 | 按钮文案 | 按钮行为 | 列表选中态 |
|------|---------|---------|-----------|
| 普通模式（默认） | + 新对话 | 创建新会话 | _active_session_path 高亮 |
| 浏览模式 | ← 回到当前 | 恢复 _active_session_path | _browsing_session_path 高亮 |

### MainWindow 状态字段

- `_active_session_path` — 进入浏览模式前的活跃会话路径（普通模式下为当前会话）
- `_browsing_session_path` — 正在浏览的历史会话路径（空 = 非浏览模式）

### 状态转换规则

| 触发 | 条件 | 行为 |
|------|------|------|
| 点击"+ 新对话" | 普通模式 | 保存当前会话为 _active，创建新会话 |
| 点击历史会话 | 普通模式 | 保存当前会话为 _active，进入浏览模式 |
| 点击历史会话 | 浏览模式 | 更新 _browsing，时间线切换到新选中的历史会话 |
| 点击"← 回到当前" | 浏览模式 | 恢复 _active 到时间线，退出浏览模式 |
| 发送消息 | 任意模式 | 消息发到当前显示的会话，不改变模式 |

## File Changes

### 1. `ui/history_panel.py`

**新增方法：**
- `set_browsing_mode(enabled: bool)` — 公共方法，切换按钮文案和行为；同时更新列表高亮
- `highlight_session(session_path: str)` — 高亮指定会话条目

**新增信号：**
- `back_to_current_requested` — 浏览模式下点击按钮时 emit

**行为变更：**
- `_on_new()` — 如果当前是浏览模式，emit `back_to_current_requested` 而非 `new_session_requested`

### 2. `ui/main_window.py`

**新增字段：**
- `_active_session_path: str`
- `_browsing_session_path: str`

**新增/修改方法：**

- `_on_new_session()` — 保存当前 `_current_session_path` 为 `_active_session_path`（如果不在浏览模式）；清空 `_browsing_session_path`；退出浏览模式
- `_on_session_selected(session_path)` — 如果不在浏览模式：保存当前为 `_active`；设置 `_browsing = session_path`；通知 HistoryPanel 进入浏览模式；加载消息；通知 Pi 切换
- `_on_back_to_current()` — 清空 `_browsing_session_path`；调用 `_on_session_selected(_active_session_path)` 恢复；通知 HistoryPanel 退出浏览模式
- `_on_session_deleted(session_path)` — 如果删除的是 `_browsing_session_path`：回退到 `_active_session_path`；如果删除的是 `_active_session_path`：清空 `_active_session_path`

**信号绑定：**
- `history_panel.back_to_current_requested.connect(self._on_back_to_current)`

### 3. `ui/pi_sessions.py`

无需改动。已按 `$HIP`（CWD）隔离会话目录。

### 4. `ui/agent_panel.py`

无需改动。

## Cleanup

- 删除 `python3.11libs/edini/sessions/` 目录下所有旧 JSON 文件
- 检查项目中是否还有引用旧 `edini/sessions/` 路径的代码，如有则移除

## Edge Cases

| 场景 | 行为 |
|------|------|
| 浏览模式下点击另一个历史会话 | 更新 _browsing，时间线切换到新会话，保持浏览模式 |
| 删除正在浏览的会话 | 自动回退到 _active_session_path；如果 _active 也被删除，回退到空白 |
| Pi 未连接时浏览历史 | 本地 JSONL 可读，时间线正常渲染；继续聊天不可用（输入框可禁用） |
| 浏览模式下发消息 | 消息发到 _browsing 会话，不退出浏览模式 |
| _active 与 _browsing 相同 | 不应发生，前端不响应"点击当前会话" |
| 启动时无任何会话 | _active 和 _browsing 均为空，普通模式，列表为空 |
