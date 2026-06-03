# Edini Design Spec

**日期：** 2026-06-03
**状态：** draft

## 概述

Edini 是一个在 Houdini 内部运行的综合性 AI 助手。用户通过 Houdini 内置的 PySide6 面板，用自然语言与 AI 对话，AI 可以操控节点、设置参数、编写 VEX/Python 脚本、操作 HDA，以及回答 Houdini 相关问题。

技术方案：以 **Pi 开源 Agent 框架** 为基础，通过 **Pi RPC 模式**（JSON-RPC 2.0 over stdin/stdout）与 Houdini 通信。Pi 负责 Agent 核心逻辑、模型管理和工具系统，Houdini 端负责 UI 面板和 houp 操作执行。

## 架构

```
┌─────────────────────────────────────────────────────────┐
│                    Houdini Process                       │
│                                                         │
│  ┌──────────────────────────────────────────────────┐  │
│  │              Edini Panel (PySide6/Qt 6)          │  │
│  │                                                  │  │
│  │  ┌────────────┐  ┌──────────────────────────┐   │  │
│  │  │  Chat View │  │   Node/Tool Feedback     │   │  │
│  │  │  (对话区域) │  │   (节点操作可视化反馈)    │   │  │
│  │  └────────────┘  └──────────────────────────┘   │  │
│  │                                                  │  │
│  │  ┌──────────────────────────────────────────┐   │  │
│  │  │         RPC Client (jsonrpc-2.0)         │   │  │
│  │  │         stdin/stdout 通信                 │   │  │
│  │  └──────────────────────────────────────────┘   │  │
│  └──────────────────────────────────────────────────┘  │
│                         │                              │
│         ┌───────────────┴───────────────┐              │
│         │   Tool Executor (houp)        │              │
│         │   - 创建/连接/删除节点         │              │
│         │   - 场景查询                  │              │
│         │   - 参数读写                  │              │
│         │   - VEX/Python 执行           │              │
│         │   - HDA 操作                  │              │
│         └───────────────────────────────┘              │
└─────────────────────────────────────────────────────────┘
                           │
                     stdin/stdout
                    (JSON-RPC 2.0)
                           │
┌─────────────────────────────────────────────────────────┐
│                  Pi Process (Node.js)                   │
│                                                         │
│  ┌──────────────────────────────────────────────────┐  │
│  │              pi --mode rpc                       │  │
│  │                                                  │  │
│  │  - Agent Session 管理                            │  │
│  │  - 模型调度 (Claude / GPT / ...)                 │  │
│  │  - 工具注册 → Houdini 工具转发到 Python 侧       │  │
│  │  - 扩展系统                                       │  │
│  │  - Session 持久化                                 │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### 关键设计决策

| 层级 | 职责 | 技术 |
|------|------|------|
| Edini Panel | 聊天 UI、消息展示、工具调用可视化 | PySide6 (Qt 6, Houdini 21) |
| RPC Client | 与 Pi 进程的 JSON-RPC 通信 | Python subprocess + JSON |
| Tool Executor | 将工具调用翻译为 Houdini 操作 | hou / houp 模块 |
| Pi Process | Agent 核心、模型管理、工具路由 | Pi --mode rpc |

### 方案选择理由

采用方案一（Pi RPC 模式 + Houdini Python 面板），因为：
1. Pi RPC 模式专门为跨语言集成设计
2. 充分利用 Pi 的工具系统、事件钩子、session 管理、扩展生态
3. Node.js 和 Houdini Python 完全隔离，各自发挥优势
4. Houdini 侧聚焦于 UI + houp 操作，逻辑清晰

## 通信协议

### 消息流

```
Python (面板)                          Pi (Node.js)
    │                                      │
    ├──► {"method":"prompt",               │
    │     "params":{"text":"创建..."}}      │
    │                                      ├─ 开始 Agent 循环
    │   ◄── {"type":"message_update",      │
    │         "delta":"我来帮你创建..."}     │
    │   ◄── {"type":"message_update",      │
    │         "delta":"..."}               │
    │                                      ├─ Agent 决定调用工具
    │   ◄── {"type":"tool_call",           │
    │         "tool":"houdini_create_node",│
    │         "args":{"type":"geo",        │
    │                 "name":"my_geo"}}    │
    │                                      │
    │   [Python 执行 houp 创建节点]          │
    │                                      │
    │   ──► {"type":"tool_result",         │
    │         "content":"创建成功",          │
    │         "details":{...}}             │
    │                                      ├─ Agent 继续处理
    │   ◄── {"type":"message_end"}          │
```

### 消息类型

| 方向 | 类型 | 用途 |
|------|------|------|
| Python→Pi | `prompt` | 发送用户输入 |
| Python→Pi | `abort` | 终止当前 Agent 响应 |
| Python→Pi | `tool_result` | 返回工具执行结果 |
| Python→Pi | `steer` / `followUp` | 中途插入/排队指令 |
| Pi→Python | `message_update` | 流式文本增量 (text_delta) |
| Pi→Python | `message_start` / `message_end` | 消息生命周期 |
| Pi→Python | `tool_call` | 要求 Python 侧执行 Houdini 操作 |
| Pi→Python | `agent_start` / `agent_end` | Agent 周期通知 |

## 工具设计

### Houdini 专用工具集

#### 场景/节点操作

| 工具名 | 描述 |
|--------|------|
| `houdini_get_scene_info` | 获取当前场景概览（节点数、当前路径等） |
| `houdini_get_node` | 获取节点详情（类型、参数、连接关系） |
| `houdini_create_node` | 创建节点 |
| `houdini_delete_node` | 删除节点 |
| `houdini_connect_nodes` | 连接节点（输入输出） |
| `houdini_set_param` | 设置节点参数 |
| `houdini_get_param` | 读取节点参数 |
| `houdini_list_nodes` | 列出场景所有节点（可过滤类型/路径） |
| `houdini_layout_nodes` | 自动布局节点 |

#### 查询/分析

| 工具名 | 描述 |
|--------|------|
| `houdini_get_help` | 查询节点类型或参数的帮助文档 |
| `houdini_inspect_geo` | 检查几何体信息（点数、面数、属性等） |
| `houdini_search_nodes` | 按关键词搜索可用节点类型 |

#### 脚本/HDA

| 工具名 | 描述 |
|--------|------|
| `houdini_run_vex` | 执行 VEX snippet（Attribute Wrangle 上下文） |
| `houdini_run_python` | 执行 Houdini Python snippet |
| `houdini_create_hda` | 创建/打包 HDA |
| `houdini_get_hda_info` | 查询 HDA 定义信息 |

### 工具执行流程

所有工具在 Pi 侧注册为 **代理工具（proxy tools）**——只定义 schema 和描述，不实现 execute 逻辑。实际执行通过 RPC `tool_call` 事件转发到 Houdini Python 侧，由 `tool_executor.py` 分发到具体 houp 操作。

示例流程（用户说"帮我创建一个烟模拟"）：

1. Pi Agent 收到 prompt
2. Pi 调用 `houdini_search_nodes({"keyword": "smoke"})` → RPC 转发
3. Python 侧查询 `hou.nodeTypeCategories()` 返回可用节点列表
4. Pi 调用 `houdini_create_node({"node_type":"smoke", "name":"smoke_sim"})` → RPC 转发
5. Python 侧 `hou.node("/obj").createNode("smoke", "smoke_sim")` 创建节点
6. 面板高亮新节点
7. Pi 流式输出回复

## 面板 UI

### 布局

```
┌───────────────────────────────────────────────────────────┐
│  Edini - Houdini AI Assistant                    [⚙] [✕]  │
├───────────────────────────────────────────────────────────┤
│                                                           │
│   聊天消息区（QScrollArea + Markdown 渲染）                  │
│                                                           │
│   - 用户消息：右对齐气泡                                    │
│   - AI 消息：左对齐气泡，流式渲染                            │
│   - 工具调用：可折叠卡片，显示工具名、参数、结果              │
│   - 节点操作：附带"跳转到节点"按钮                           │
│                                                           │
├───────────────────────────────────────────────────────────┤
│  │ 📝 输入消息...                    [📎] [⏹] [▶ 发送]  │
├───────────────────────────────────────────────────────────┤
│  模型: claude-sonnet-4-5  │  节点: 12  │  ⬤ 已连接         │
└───────────────────────────────────────────────────────────┘
```

### 交互细节

| 区域 | 功能 |
|------|------|
| 聊天区 | 流式文本输出 + Markdown 渲染 + 工具调用卡片（可折叠） |
| 输入栏 | Enter 发送、Shift+Enter 换行、历史记录 (`↑` `↓`) |
| 状态栏 | 当前模型、场景节点数、连接状态、处理中指示器 |
| 工具卡片 | 显示工具名称、参数、执行结果；节点创建时附带"跳转到节点"按钮 |
| ⚙ 设置 | 切换模型、清空对话、导出/导入 session |

## 生命周期

```
Houdini 启动 → createPanel() 注册到 Houdini 面板系统
     ↓
用户打开 Edini 面板 → 自动启动 Pi 子进程 (pi --mode rpc --no-session)
     ↓
用户输入问题 → RPC prompt → Pi Agent 处理
     ↓
Pi 调用工具 → RPC tool_call → tool_executor 分发 → houp 执行
     ↓
Pi 生成回复 → RPC 事件流 → 面板流式渲染
     ↓
Houdini 关闭 → panel closeEvent → Pi 子进程终止
```

## 项目文件结构

```
F:/zz/Edini/
│
├── edini/                          # Houdini 侧 Python 包
│   ├── __init__.py
│   ├── panel.py                    # PySide6 主面板 (ChatView + InputBar + StatusBar)
│   ├── rpc_client.py              # Pi RPC 通信客户端 (subprocess + JSON-RPC)
│   ├── tool_executor.py           # 工具执行器 (Pi tool_call → houp 操作)
│   ├── node_utils.py              # houp 节点操作统一封装
│   ├── session_store.py           # 对话历史本地缓存
│   └── config.py                  # Pi 路径、默认模型等配置
│
├── pi-extensions/                  # Pi 扩展 (Node.js/TypeScript)
│   ├── edini-tools/
│   │   ├── index.ts               # 入口：注册所有 Houdini 工具
│   │   ├── tools/
│   │   │   ├── scene.ts           # 场景/节点操作工具
│   │   │   ├── query.ts           # 查询/搜索工具
│   │   │   └── script.ts          # VEX/Python/HDA 工具
│   │   └── package.json
│   │
│   └── edini-context/
│       ├── index.ts               # 入口：注入 Houdini 上下文到 system prompt
│       └── package.json
│
├── scripts/
│   ├── install.py                 # 一键安装：注册面板到 Houdini
│   └── setup_pi.bat               # Windows：安装 pi + 配置 extensions
│
└── README.md
```

## 模块职责

| 模块 | 职责 | 关键依赖 |
|------|------|----------|
| `panel.py` | 聊天 UI、Markdown 渲染、工具卡片、输入处理 | PySide6, QTextEdit, QThread |
| `rpc_client.py` | 管理 Pi 子进程、JSON-RPC 编解码、异步消息分发 | subprocess, asyncio, json |
| `tool_executor.py` | 将 Pi 工具调用分发到具体 houp 操作 | hou, node_utils |
| `node_utils.py` | houp 操作的统一封装和错误处理 | hou |
| `pi-extensions/` | Pi 侧的工具 schema 定义 + Houdini 上下文注入 | TypeScript, Pi SDK |

## 限制与已知问题

1. **单面板实例**：同一时间只允许一个 Edini 面板实例，因为 Pi 进程需要独占 stdin/stdout
2. **Pi 进程生命周期**：需要处理 Pi 进程意外崩溃后的自动重启
3. **工具调用阻塞**：Houdini 侧执行工具时可能阻塞 UI 线程（解决方案：工具执行放在 QThread 中）
4. **网络依赖**：模型调用需要访问外部 API（Anthropic/OpenAI），离线时降级为纯本地回答
5. **Houdini 21 专用**：面板依赖 PySide6，对应 Houdini 21+，不考虑向后兼容

## 后续扩展

- 支持图像输入（截图场景发给 AI 分析）
- 预设工作流模板（一键创建常见效果：烟、火、水、破碎等）
- 多轮对话的面包屑导航（Pi session tree 可视化）
- 节点网络的 AI 智能建议（分析当前网络结构，推荐下一步操作）
