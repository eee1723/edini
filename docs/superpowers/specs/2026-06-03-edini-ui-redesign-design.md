# Edini UI 重构设计

> 日期: 2026-06-03
> 参考: EEEAi_Houdini 项目 (github.com/eee1723/EEEAi_Houdini)
> 当前分支: main

## 一、设计目标

将 Edini 从一个需要 Python Shell 手动启动的浮动 QWidget，重构为：
1. **Houdini 原生集成**：通过 MainMenuCommon.xml 在 Houdini 主菜单栏注册"Edini"子菜单
2. **高级三栏 UI**：History | Chat Timeline | Context（Pi 状态 + 场景信息）
3. **Pi 信息完整呈现**：将 Pi JSON-RPC 的所有事件映射到 UI 组件

### 核心差异（Edini vs EEEAi_Houdini）

| 维度 | EEEAi_Houdini | Edini |
|------|---------------|-------|
| AI 引擎 | 自建（ChatRuntime/remote_client） | Pi Agent（Node.js 子进程） |
| 工具执行 | Python 直接调用 | Pi Extension → HTTP → tool_executor |
| 流式处理 | StreamManager/StreamParser | Pi JSON-RPC JSONL |
| 会话上下文 | 服务端管理 | Pi --no-session 无状态 |
| 成本计算 | budget_manager | Pi session_stats |
| 模型配置 | settings_store 复杂配置 | settings.json + env var |

### 去掉的组件（Pi 已承担）

- ChatRuntime / remote_client / remote_transport
- StreamManager / StreamParser / ThinkingProcessor
- budget_manager / cost 计算
- Recipe / knowledge_router / RAG
- VEX assist window（独立窗口）
- remote_protocol / remote_tools

## 二、目录结构

```
edini/                                  ← 项目根
├── python3.11libs/                     ← Houdini 加载入口（新增）
│   └── edini/
│       ├── __init__.py                 ← create_panel
│       ├── config.py                   ← 适配新路径
│       ├── rpc_client.py               ← Pi JSON-RPC 通信
│       ├── tool_executor.py            ← HTTP 工具执行器
│       ├── node_utils.py               ← Houdini 操作（不变）
│       ├── settings.json               ← 用户配置
│       └── ui/                         ← 所有 UI 模块
│           ├── __init__.py             ← 导出 open_chat_window/open_settings
│           ├── windows.py              ← 窗口管理（单例模式）
│           ├── main_window.py          ← QMainWindow 三栏布局
│           ├── agent_panel.py          ← 聊天时间线面板
│           ├── history_panel.py        ← 会话历史面板（左侧）
│           ├── context_panel.py        ← Pi状态 + 场景信息（右侧）
│           ├── theme.py                ← 暗色主题 + 字体缩放 + 色彩预设
│           ├── settings_dialog.py      ← 设置对话框
│           ├── plan_progress_widget.py ← Plan-Execute 进度条
│           ├── change_tree_widget.py   ← 节点变更追踪
│           ├── session_store.py        ← 会话持久化
│           ├── chat_runtime.py         ← 轻量 Pi 事件适配层
│           ├── hotkey.py               ← 热键注册
│           └── styled_checkbox.py      ← 样式组件
├── pi-extensions/                      ← 不变
│   ├── edini-tools/
│   └── edini-context/
├── scripts/
│   ├── install.py                      ← 改写为 Houdini packages 模式
│   └── setup_pi.bat
└── wiki/
    └── ...
```

## 三、Houdini 菜单注册

### 3.1 包描述符

`scripts/install.py` 写入 `%USERPROFILE%/Documents/houdini21.x/packages/edini.json`：

```json
{
    "env": [
        { "EDINI_PATH": "<项目绝对路径>" }
    ],
    "path": "$EDINI_PATH",
    "houdini": {
        "python3.11libs": "$EDINI_PATH/python3.11libs"
    }
}
```

### 3.2 菜单 XML

`python3.11libs/MainMenuCommon.xml`（与 edini/ 包同级）：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<mainMenu>
  <menuBar>
    <subMenu id="edini_menu">
      <label>Edini</label>
      <scriptItem id="edini_open_chat">
        <label>Open Chat Panel</label>
        <hotkey>Alt+Shift+E</hotkey>
        <scriptCode><![CDATA[
from edini.ui import open_chat_window
open_chat_window()
        ]]></scriptCode>
      </scriptItem>
      <separatorItem/>
      <scriptItem id="edini_settings">
        <label>Settings</label>
        <scriptCode><![CDATA[
from edini.ui import open_settings
open_settings()
        ]]></scriptCode>
      </scriptItem>
    </subMenu>
  </menuBar>
</mainMenu>
```

### 3.3 窗口管理（windows.py）

单例模式，参照 EEEAi_Houdini：
- `open_chat_window()` — 创建/显示主窗口
- `open_settings()` — 创建设置对话框
- `smart_launcher()` — 热键智能启动（如果选中 Wrangle 节点 → 暂无特殊处理）
- `_main_parent()` — `hou.qt.mainWindow()` 作为父窗口

## 四、主窗口布局（main_window.py）

```
┌────────────────────────────────────────────────────┐
│  QMainWindow                                       │
│  标题: "Edini Agent"                               │
│  默认尺寸: 1360×860                               │
│                                                    │
│  ┌──────────┬─────────────────────┬──────────────┐ │
│  │ History  │  Chat Timeline      │  Context     │ │
│  │ Panel    │                     │  Panel       │ │
│  │ (左侧)   │                     │  (右侧)      │ │
│  │          │  ┌───────────────┐  │              │ │
│  │ 会话列表 │  │ 用户/AI 气泡  │  │  Pi 状态    │ │
│  │ [+新建] │  │ Tool Cards    │  │  ● Connected│ │
│  │          │  │ Plan 进度条   │  │  模型: DS V3│ │
│  │          │  │ Change Tree   │  │  Token 统计  │ │
│  │          │  └───────────────┘  │  上下文使用  │ │
│  │          │                     │  流式速率    │ │
│  │          │  ┌───────────────┐  │              │ │
│  │          │  │ 输入框 + 发送 │  │  ───────────│ │
│  │          │  └───────────────┘  │  场景信息    │ │
│  │          │                     │  HIP 文件名  │ │
│  │          │                     │  当前路径    │ │
│  │          │                     │  选中节点    │ │
│  │          │                     │  节点统计    │ │
│  └──────────┴─────────────────────┴──────────────┘ │
│  ┌────────────────────────────────────────────────┐ │
│  │ StatusBar: Ready | Nodes: 42 | Tok: 1,234      │ │
│  └────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────┘
```

- **QSplitter** 三栏，比例 [240, 720, 400]
- 三栏均不可折叠（`setCollapsible(False)`）
- 仅中间栏可拉伸（`setStretchFactor(1, 1)`）

## 五、聊天时间线面板（agent_panel.py）

### 5.1 Pi 事件 → UI 映射

| Pi JSON-RPC 事件 | UI 渲染 |
|---|---|
| `message_update / text_delta` | AI 气泡（左对齐，流式追加，打字机效果） |
| `tool_execution_start` | Tool Card（可折叠，显示工具名+参数） |
| `tool_execution_end` | Tool Card 状态更新（✅ 完成 / ❌ 失败 + 结果摘要） |
| `agent_start` | 状态切换 "Processing..." |
| `agent_finished` | 关闭流式光标，刷新场景信息，请求 session_stats |
| `error_occurred` | 红色错误横幅 ❌ |
| `response / session_stats` | 更新右栏 token/成本 |

### 5.2 消息类型

```python
# 用户消息（右对齐，蓝色/深蓝底）
"👤 创建 smoke 模拟效果"
# AI 消息（左对齐，暗底，流式追加 Markdown）
"🤖 我来帮你创建烟雾效果..."
# 系统消息（居中，灰色斜体）
"─ 本轮结束 · 3 tools · 1,234 tok ─"
# 错误消息（红色）
"⚠️ 连接超时，请检查网络"
```

### 5.3 Markdown 渲染

使用 QTextBrowser 或自定义 HTML 渲染：
- **代码块**：`<pre>` 深色背景，等宽字体，复制按钮
- **行内代码**：`<code>` 背景高亮
- **表格**：`<table>` 带边框
- **加粗**/列表/标题
- **图片**（后续 P3 支持 viewport 截图）

### 5.4 Tool Card

```python
class ToolCard(QFrame):
    """可折叠工具调用卡片"""
    # Header: "▸ 🔧 houdini_create_node" (点击展开)
    # Detail: JSON 参数 + 执行结果
    # 状态: ⏳ executing → ✅ done / ❌ failed
```

### 5.5 流式文本优化

- 80 字符批量刷新（STREAM_FLUSH_CHARS=80）
- 80ms 定时器强制刷新
- 闪烁光标 ▊（streaming 模式）
- 完成后渲染完整 Markdown

## 六、Pi 状态面板（context_panel.py 上部）

数据来源：Pi JSON-RPC 事件 + 定时轮询

```
┌─────────────────────┐
│ Pi Status           │
│ ● Connected         │  ← status_changed 事件
│                     │
│ Provider  deepseek  │  ← settings.json
│ Model     deepseek  │  ← settings.json
│           -chat     │
│                     │
│ ─────────────────── │
│ Token Usage         │
│ In        234       │  ← session_stats.tokens
│ Out     1,532       │
│ Total   1,766       │
│ Cost   $0.003      │  ← session_stats.cost
│                     │
│ Context Window      │
│ ████░░░░░░ 12%     │  ← session_stats.contextUsage
│                     │
│ Stream Rate         │
│ 85 tok/s           │  ← 实时计算或 stats
└─────────────────────┘
```

### 6.1 刷新策略

| 数据 | 刷新方式 |
|------|---------|
| 连接状态 | `status_changed` 事件即时更新 |
| Provider/Model | settings.json 读取，模型切换时刷新 |
| Token/成本 | `agent_finished` 时 `send_get_stats()` |
| 上下文使用 | 同上 |
| 流式速率 | 本地计时（字符数/时间），agent_finished 显示 |

## 七、场景信息面板（context_panel.py 下部）

数据来源：`node_utils.get_scene_info()`（已实现）

```
┌─────────────────────┐
│ Scene Info          │
│                     │
│ HIP File            │
│ scene_v3.hip       │  ← hou.hipFile.name()
│                     │
│ Current Path        │
│ /obj                │  ← hou.pwd().path()
│                     │
│ Selected Node       │
│ /obj/geo1          │  ← hou.selectedNodes()[0]
│ Type: geo           │
│ Children: 3         │
│                     │
│ ─────────────────── │
│ Scene Stats         │
│ /obj        12      │  ← 按层级展开
│ /out         2      │
│ ────────           │
│ Total       14      │
│                     │
│ [⟳ Refresh]        │  ← 手动刷新按钮
└─────────────────────┘
```

刷新策略：QTimer 每 3 秒 + `agent_finished` 时立即刷新。

## 八、会话管理（history_panel.py）

### 8.1 存储

- 路径：`edini/sessions/`（gitignored）
- 格式：每个会话一个 JSON 文件 `{session_id}.json`
- 结构：
```json
{
    "session_id": "sess-a1b2c3d4",
    "title": "烟雾模拟",
    "created_at": "2026-06-03T12:00:00",
    "updated_at": "2026-06-03T12:05:00",
    "messages": [
        {"role": "user", "content": "创建 smoke", "timestamp": "..."},
        {"role": "assistant", "content": "我来帮你...", "timestamp": "..."},
        {"role": "tool", "tool_name": "houdini_create_node", "args": {...}, "result": {...}}
    ]
}
```

### 8.2 操作

| 操作 | 实现 |
|------|------|
| 新建会话 | `session_store.create_session()` → 生成新 session_id |
| 切换会话 | 加载 messages → agent_panel.render_messages() |
| 删除会话 | `session_store.delete_session()` → 刷新列表 |
| 追加消息 | `session_store.append_message(sid, msg)` |
| 切换回当前 | 如果正在看历史，点击"New"回到当前活跃会话 |

### 8.3 Pi 无状态处理

- 每次 `send_prompt()` 发送当前消息
- 不传递历史上下文给 Pi（`--no-session` 模式）
- 如需要上下文延续，可以将最近 N 条历史放入 system prompt 的一部分
- 会话列表仅用于历史浏览和记录

## 九、主题系统（theme.py）

### 9.1 暗色基础

```python
DARK_THEME = {
    "bg": "#111118",
    "sidebar_bg": "#0e0e15",
    "surface": "#1a1a24",
    "surface_hover": "#222233",
    "border": "#2a2a3c",
    "text": "#e5e5eb",
    "text_muted": "#71717a",
    "text_dim": "#52525b",
    "code_bg": "#1e1e2e",
}
```

### 9.2 色彩预设

| 预设 | 主色 | 适用 |
|------|------|------|
| 北极青（默认） | `#06b6d4` | 科技感 |
| Houdini 橙 | `#f59e0b` | 贴近 SideFX |
| 深海蓝 | `#3b82f6` | 低对比度 |
| 极光紫 | `#8b5cf6` | 个性 |

每个预设包含：accent, accent_light, accent_dark, accent_text, accent_bg, accent_bg_hover, accent_border, selection

### 9.3 字体缩放

- 全局缩放因子 0.8~1.4
- `settings_store.get_font_scale()` / `set_font_scale()`
- Qt stylesheet 中动态计算 font-size

### 9.4 Qt 样式应用

- 通过 `app.setStyleSheet()` 应用全局暗色主题
- 每个组件独立样式覆盖

## 十、设置对话框（settings_dialog.py）

参照 EEEAi_Houdini 的 settings_dialog.py，简化为 Edini 需要的：

| Tab | 内容 |
|------|------|
| **Provider** | API Key / Provider / Model ID（当前 QLineEdit 三件套），增加预设按钮 |
| **Appearance** | 主题色下拉 + 字体缩放滑块 |

## 十一、开发阶段

### P0: 基础设施（1-2 天）
- [ ] 创建 `python3.11libs/` 目录结构
- [ ] 迁移 `edini/` 源码到 `python3.11libs/edini/`
- [ ] 创建 `MainMenuCommon.xml`
- [ ] 改写 `install.py` 写入 Houdini packages JSON
- [ ] 调整 config.py 路径计算
- [ ] 验证 Houdini 菜单出现

### P1: 核心 UI（2-3 天）
- [ ] `main_window.py` — QMainWindow 三栏 QSplitter 框架
- [ ] `theme.py` — 暗色主题系统 + 4 色预设 + 字体缩放
- [ ] `agent_panel.py` — 时间线视图（QTextBrowser + Markdown 渲染）
- [ ] `chat_runtime.py` — Pi 事件适配层
- [ ] Tool Card 组件
- [ ] 输入栏 + 发送按钮 + Enter 快捷键
- [ ] 流式文本追加 + 闪烁光标

### P2: 功能面板（2-3 天）
- [ ] `context_panel.py` — Pi 状态面板（连接、模型、token、成本、上下文进度条）
- [ ] `context_panel.py` — 场景信息面板（HIP、选中节点、统计）
- [ ] `history_panel.py` — 会话列表 + 操作
- [ ] `session_store.py` — JSON 文件读写
- [ ] `settings_dialog.py` — Provider + 主题设置
- [ ] `plan_progress_widget.py` — Plan 进度条组件
- [ ] `change_tree_widget.py` — 节点变更树组件

### P3: 打磨（1-2 天）
- [ ] `hotkey.py` — Alt+Shift+E 热键注册
- [ ] 错误处理完善（Pi 断连重试、工具执行超时）
- [ ] 场景信息 QTimer 自动刷新
- [ ] 更新 wiki 文档
- [ ] 实机 Houdini 21 验证

## 十二、文件清单

### 新增文件
- `python3.11libs/MainMenuCommon.xml`
- `python3.11libs/edini/__init__.py`
- `python3.11libs/edini/config.py`
- `python3.11libs/edini/rpc_client.py`（迁移+适配）
- `python3.11libs/edini/tool_executor.py`（迁移）
- `python3.11libs/edini/node_utils.py`（迁移）
- `python3.11libs/edini/ui/__init__.py`
- `python3.11libs/edini/ui/windows.py`
- `python3.11libs/edini/ui/main_window.py`
- `python3.11libs/edini/ui/agent_panel.py`
- `python3.11libs/edini/ui/history_panel.py`
- `python3.11libs/edini/ui/context_panel.py`
- `python3.11libs/edini/ui/theme.py`
- `python3.11libs/edini/ui/settings_dialog.py`
- `python3.11libs/edini/ui/chat_runtime.py`
- `python3.11libs/edini/ui/plan_progress_widget.py`
- `python3.11libs/edini/ui/change_tree_widget.py`
- `python3.11libs/edini/ui/session_store.py`
- `python3.11libs/edini/ui/hotkey.py`
- `python3.11libs/edini/ui/styled_checkbox.py`

### 修改文件
- `scripts/install.py` — 改写为 Houdini packages 模式

### 移除文件
- `edini/__init__.py` — 迁移到 `python3.11libs/edini/`
- `edini/config.py` — 迁移
- `edini/panel.py` — 拆分为 main_window + agent_panel
- `edini/rpc_client.py` — 迁移
- `edini/tool_executor.py` — 迁移
- `edini/node_utils.py` — 迁移
- `edini/settings.json` — 迁移
