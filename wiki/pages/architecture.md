# 🏗️ 架构地图

> Edini 三层架构全景及数据流。最后更新：2026-06-05（QScrollArea Widget 时间线重构）。

## 架构总览

```
╔════════════════════════════════╗   ╔══════════════════════════════╗
║    Houdini 21 (Python)        ║   ║   Pi Agent (Node.js)         ║
║                               ║   ║                              ║
║  ┌─────────────────────────┐  ║   ║  ┌────────────────────────┐  ║
║  │  EdiniMainWindow        │  ║   ║  │  Agent Core            │  ║
║  │  · QSplitter 三栏       │  ║   ║  │  · Model (DeepSeek)    │  ║
║  │  · History | Timeline   │  ║   ║  │  · Tool System          │  ║
║  │    | Pi+Scene+Knowledge │  ║   ║  │  · Streaming            │  ║
║  └───────────┬─────────────┘  ║   ║  └───────────┬────────────┘  ║
║              │                ║   ║              │               ║
║  ┌───────────v─────────────┐  ║   ║  ┌───────────v────────────┐  ║
║  │  RpcClient (QThread)    │  ║   ║  │  Extensions            │  ║
║  │  · subprocess.Popen     │◄─╫─stdin/stdout─╫─▶│  · edini-tools (16)     │  ║
║  │  · 会话 RPC             │  ║   ║  │  · edini-context        │  ║
║  │  · cwd=HIP目录          │  ║   ║  │    (铁律注入 + 上下文) │  ║
║  └───────────┬─────────────┘  ║   ║  └────────────────────────┘  ║
║              │                ║   ║                              ║
║  ┌───────────v─────────────┐  ║   ╚══════════════════════════════╝
║  │  ToolExecutor (HTTP)    │◄─╫── HTTP POST /execute
║  │  · 127.0.0.1:9876      │  ║    (Pi extension → server)
║  └───────────┬─────────────┘  ║
║              │                ║
║  ┌───────────v─────────────┐  ║
║  │  node_utils.py (houp)   │  ║
║  │  · 16 handler functions │  ║
║  └─────────────────────────┘  ║
║                               ║
║  ┌─────────────────────────┐  ║
║  │  Knowledge Store         │  ║
║  │  ~/.pi/agent/            │  ║
║  │  edini-knowledge/        │  ║
║  │  ├── rules.json ≤20     │  ║
║  │  └── entries.json       │  ║
║  └─────────────────────────┘  ║
╚════════════════════════════════╝
```

## 目录结构

```
Edini/
├── python3.11libs/edini/     # Houdini 包（Python 3.11）
│   ├── __init__.py           # createPanel() 入口
│   ├── config.py             # 配置 · 设置持久化 · env overrides · knowledge_enabled
│   ├── rpc_client.py         # Pi 子进程管理 + JSON-RPC 通信 · 会话 RPC · extension_info
│   ├── tool_executor.py      # HTTP server + 工具路由 (16 handlers)
│   ├── node_utils.py         # Houdini node 操作 (纯 houp API)
│   └── ui/
│       ├── __init__.py       # open_chat_window()
│       ├── main_window.py    # QMainWindow 三栏 + 信号绑定 + 知识提取流程
│       ├── agent_panel.py    # 对话面板（QScrollArea Widget 时间线 + Thinking + Tool + 知识确认区）
│       ├── context_panel.py  # 右侧面板（Pi Status + Scene + Knowledge）
│       ├── history_panel.py  # 会话列表（浏览模式 + 新建/切换/删除）
│       ├── settings_dialog.py # 设置（General + Knowledge 双标签）
│       ├── chat_runtime.py   # Pi 事件适配层
│       ├── theme.py          # 暗色主题系统 + 字体缩放
│       ├── hotkey.py         # 快捷键
│       ├── viewport.py       # Houdini Viewport 截图
│       ├── pi_sessions.py    # Pi JSONL 会话读取
│       ├── knowledge_store.py # 知识存储 CRUD + JSON 解析
│       ├── knowledge_dialog.py # 知识管理弹窗（双标签）
│       ├── windows.py        # 窗口单例管理
│       ├── styled_checkbox.py
│       ├── plan_progress_widget.py
│       ├── change_tree_widget.py
│       └── settings.json     # 用户设置
├── edini/                    # 旧版 Python 包（panel.py 模式）
├── pi-extensions/            # Pi 扩展（TypeScript，Node.js 运行）
│   ├── edini-tools/          # 工具注册 (16 tools，TypeBox 参数校验)
│   │   ├── index.ts
│   │   ├── tools/
│   │   │   ├── scene.ts      # 场景/节点操作
│   │   │   ├── query.ts      # 查询/检查
│   │   │   └── script.ts     # VEX/Python/HDA
│   │   └── package.json
│   └── edini-context/        # 系统提示注入 (before_agent_start hook)
│       ├── index.ts          # Houdini 上下文 + 铁律（rules.json）注入
│       └── package.json
├── scripts/                  # 部署脚本
│   ├── install.py            # Houdini 包注册
│   └── setup_pi.bat          # Windows Pi 安装
├── MainMenuCommon.xml        # Houdini 主菜单注册
└── wiki/                     # 项目 Wiki
```

## 数据流

### 1. 用户输入 → AI 响应

```
用户输入 (QPlainTextEdit)
  → AgentPanel._on_send()
    → submit_requested signal
      → main_window._on_agent_submit(text)
        → RpcClient.send_prompt(text)
          → JSON-RPC stdin → Pi Agent → LLM 推理
            → stdout JSONL 流式事件
              → RpcClient text_delta / thinking_delta / tool_call / tool_result signals
                → AgentPanel 渲染（时间线 bubble / Thinking 面板 / Tool 卡片）
```

### 2. 工具调用流程

```
Pi Agent 决定调用工具
  → edini-tools 扩展: forwardTool(name, params)
    → HTTP POST http://127.0.0.1:9876/execute
      → ToolExecutor → TOOL_HANDLERS[name](**params)
        → node_utils.xxx()
          → hou.node().xxx()  (Houdini Python API)
            → 返回 JSON → HTTP Response → Pi → LLM 继续推理
```

### 3. 知识提取流程

```
对话结束 (_on_agent_done)
  → _maybe_extract_knowledge()
    → knowledge_enabled? → 发送反思 prompt
      → AI 返回 JSON
        → _handle_extraction_response()
          → get_raw_stream_text()（从内存 buffer 读，不渲染进时间线）
          → cancel_current_stream()（恢复时间线到提取前状态）
          → parse_extraction_response()（代码块提取 → 单引号修复 → 尾逗号修复 → json.loads）
            → show_extraction_results(items)
              → 知识确认区展示（铁律/知识徽章可切换 + ✓✕ 按钮）
                → 用户确认
                  → accept_extracted() → rules.json / entries.json
```

### 4. 铁律上下文注入

```
每次对话开始 (before_agent_start hook)
  → edini-context/index.ts
    → 读取 ~/.pi/agent/edini-knowledge/rules.json
      → 过滤 enabled: true 的规则
        → 注入 system prompt（铁律 + Houdini 上下文）
```

## 关键设计决策

| 决策 | 原因 |
|------|------|
| JSON-RPC 走 stdin/stdout | 无需网络端口、零配置、进程生命周期绑定 |
| 工具执行走 HTTP localhost | Pi 扩展在 Node.js 进程，需跨进程调用 Houdini Python |
| QThread 管理子进程 | 避免阻塞 Houdini UI 主线程 |
| Pi 以 cwd=HIP 启动 | Session JSONL 按项目目录归档 |
| 知识两层架构 | 铁律（通用原则，≤20条，每次注入）vs 知识库（细节知识，可检索） |
| 用户确认提取结果 | 避免 AI 判断不准，最终决定权在用户 |
| 提取响应不渲染进时间线 | get_raw_stream_text + cancel_current_stream，避免 HTML 解析脆弱 |
| settings.json 本地持久化 | API key 不应写入 Houdini 包文件 |

## 模块边界

| 模块 | 职责 | 禁止 |
|------|------|------|
| config.py | 配置读取/写入/环境变量 | 不依赖 hou |
| main_window.py | 窗口布局/信号绑定/知识提取流程 | 不直接渲染 UI 细节 |
| agent_panel.py | 对话渲染（Widget 时间线）/Thinking/Tool/知识确认区 | 不调用 hou API 直接操作 |
| rpc_client.py | 子进程生命周期/事件分发 | 不操作 UI 组件 |
| tool_executor.py | HTTP 服务/路由 | 不包含业务逻辑 |
| node_utils.py | Houdini node 操作 | 不引入 UI 依赖 |
| knowledge_store.py | 知识 CRUD/JSON 解析 | 不引入 UI 依赖 |
| knowledge_dialog.py | 知识管理弹窗 | 不直接操作存储 |
| context_panel.py | 右侧信息卡片 | 不发起 RPC 请求 |
| edini-tools/ | 工具注册/schema/HTTP 转发 | 不直接操作 Houdini |
| edini-context/ | 系统提示注入/铁律读取 | 不注册工具 |
