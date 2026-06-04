# 🏗️ 架构地图

> Edini 三层架构全景及数据流。最后更新：2026-06-03。

## 架构总览

```
╔═══════════════════════════════╗   ╔══════════════════════════════╗
║    Houdini 21 (Python)       ║   ║   Pi Agent (Node.js)         ║
║                              ║   ║                              ║
║  ┌────────────────────────┐  ║   ║  ┌────────────────────────┐  ║
║  │  EdiniPanel (PySide6)  │  ║   ║  │  Agent Core            │  ║
║  │  · 聊天视图          │  ║   ║  │  · Model (DeepSeek)    │  ║
║  │  · 输入栏            │  ║   ║  │  · Tool System          │  ║
║  │  · 设置对话框        │  ║   ║  │  · Streaming            │  ║
║  │  · 状态栏            │  ║   ║  └───────────┬────────────┘  ║
║  └───────────┬────────────┘  ║   ║              │               ║
║              │               ║   ║  ┌───────────v────────────┐  ║
║  ┌───────────v────────────┐  ║   ║  │  Extensions            │  ║
║  │  RpcClient (QThread)   │  ║   ║  │  · edini-tools (16)    │  ║
║  │  · subprocess.Popen    │◄─╫─stdin/stdout─╫─▶│  · edini-context (prompt)│  ║
║  │  · JSON-RPC 事件       │  ║   ║  └────────────────────────┘  ║
║  └───────────┬────────────┘  ║   ║                              ║
║              │               ║   ╚══════════════════════════════╝
║  ┌───────────v────────────┐  ║
║  │  ToolExecutor (HTTP)   │◄─╫── HTTP POST /execute
║  │  · 127.0.0.1:9876     │  ║    (Pi extension → server)
║  └───────────┬────────────┘  ║
║              │               ║
║  ┌───────────v────────────┐  ║
║  │  node_utils.py (houp)  │  ║
║  │  · 16 handler functions│  ║
║  └────────────────────────┘  ║
╚═══════════════════════════════╝
```

## 目录结构

```
Edini/
├── edini/                    # Python 包（Houdini 内运行）
│   ├── __init__.py           # createPanel() 入口
│   ├── config.py             # 配置 · 设置持久化 · env overrides
│   ├── panel.py              # PySide6 聊天面板 UI
│   ├── rpc_client.py         # Pi 子进程管理 + JSON-RPC 通信
│   ├── tool_executor.py      # HTTP server + 工具路由 (16 handlers)
│   ├── node_utils.py         # Houdini node 操作 (纯 houp API)
│   └── settings.json         # 用户设置 (api_key, provider, model)
├── pi-extensions/            # Pi 扩展（TypeScript，在 Node.js 中运行）
│   ├── edini-tools/          # 工具注册 (16 tools，带 TypeBox 参数校验)
│   │   ├── index.ts
│   │   ├── tools/
│   │   │   ├── scene.ts      # 8 场景/节点工具
│   │   │   ├── query.ts      # 4 查询/检查工具
│   │   │   └── script.ts     # 4 VEX/Python/HDA 工具
│   │   └── package.json
│   └── edini-context/        # 系统提示注入 (before_agent_start hook)
│       ├── index.ts          # Houdini 上下文 + 行为准则
│       └── package.json
├── scripts/                  # 部署脚本
│   ├── install.py            # Houdini 包注册（写入 packages/edini.json）
│   └── setup_pi.bat          # Windows Pi 安装向导
└── wiki/                     # 项目 Wiki（本文档系统）
    ├── wiki.json
    ├── pages/
    ├── scripts/build.py
    └── html/
```

## 数据流

### 1. 用户输入 → AI 响应

```
用户输入 (QLineEdit)
  → EdiniPanel.send_message()
    → RpcClient.send_prompt(text)
      → JSON-RPC {"type":"prompt","message":"..."} writer.write() → stdin
        → Pi Agent 接收 prompt → LLM 推理 → 流式输出
          → stdout JSONL: {"type":"message_update","assistantMessageEvent":{"type":"text_delta","delta":"..."}}
            → RpcClient.text_delta signal
              → EdiniPanel._on_text_delta(text) → chat_area.append(text)
```

### 2. 工具调用流程

```
Pi Agent 决定调用工具
  → Pi Extension edini-tools: forwardTool(name, params)
    → HTTP POST http://127.0.0.1:9876/execute {"tool":"houdini_create_node","params":{...}}
      → ToolExecutor._ToolHandler.do_POST()
        → TOOL_HANDLERS["houdini_create_node"](**params)
          → node_utils.create_node()
            → hou.node().createNode()  (Houdini Python API)
              → 返回 {"success":true,"node":"/obj/geo1"}
                → HTTP Response → Pi Extension → LLM 继续推理
```

### 3. API Key / 模型切换流程

```
用户点击 ⚙ → SettingsDialog
  → 填写 api_key, provider, model_id
    → 保存到 settings.json (config.py: save_settings)
      → RpcClient.restart() → stop() + start()
        → 新 Pi 子进程读取 DEEPSEEK_API_KEY env var
```

### 4. 安装流程

```
python scripts/install.py
  → 检测 Houdini 用户目录 (Documents/houdini21.0 或 houdini21.5)
    → 写入 packages/edini.json 指向 Edini 目录
      → Houdini 启动时自动加载 edini 包
```

## 关键设计决策

| 决策 | 原因 |
|------|------|
| JSON-RPC 走 stdin/stdout | 无需网络端口、零配置、进程生命周期绑定 |
| 工具执行走 HTTP localhost | Pi 扩展在 Node.js 进程，需跨进程调用 Houdini Python |
| QThread 管理子进程 | 避免阻塞 Houdini UI 主线程 |
| 工具代理模式 (proxy) | TypeScript 定义工具 schema (TypeBox 校验)，HTTP 转发到 Python 执行 |
| settings.json 本地持久化 | API key 不应写入 Houdini 包文件，支持 .gitignore |
| Pi --no-session 模式 | 每次对话独立，不累积上下文失控 |

## 模块边界

| 模块 | 职责 | 禁止 |
|------|------|------|
| config.py | 配置读取/写入/环境变量 | 不依赖 hou |
| panel.py | UI 渲染/事件处理 | 不调用 hou API 直接操作 |
| rpc_client.py | 子进程生命周期/事件分发 | 不操作 UI 组件 |
| tool_executor.py | HTTP 服务/路由 | 不包含业务逻辑 |
| node_utils.py | Houdini node 操作 | 不引入 UI 依赖 |
| edini-tools/ | 工具注册/schema/HTTP 转发 | 不直接操作 Houdini |
| edini-context/ | 系统提示注入 | 不注册工具 |
