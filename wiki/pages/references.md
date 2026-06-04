# 📚 参考资料

> Edini 相关的内部设计文档和外部技术参考。最后更新：2026-06-03。

## 内部文档

| 文档 | 路径 | 说明 |
|------|------|------|
| README | `README.md` | 项目概述、快速开始、架构图 |
| 配置说明 | `edini/config.py` | 配置系统、env var 优先级、设置持久化 |
| 面板 UI | `edini/panel.py` | PySide6 聊天面板完整实现 |
| RPC 客户端 | `edini/rpc_client.py` | Pi 子进程管理 + JSON-RPC 协议 |
| 工具执行器 | `edini/tool_executor.py` | HTTP server + 16 工具路由 |
| 节点操作 | `edini/node_utils.py` | Houdini houp API 封装 |
| 安装脚本 | `scripts/install.py` | Houdini 包注册逻辑 |
| 工具扩展 | `pi-extensions/edini-tools/tools/*.ts` | TypeBox schema 定义 |
| 上下文扩展 | `pi-extensions/edini-context/index.ts` | 系统提示注入 |

## 外部参考

### Houdini API

| 资源 | 链接 | 说明 |
|------|------|------|
| Houdini Python API | SideFX 官方文档 | hou 模块完整参考 |
| Houdini Node Types | SideFX 文档 | 所有节点类型和参数说明 |
| Houdini Packages | SideFX 文档 | JSON 包注册格式 |

### Pi Coding Agent

| 资源 | 链接 | 说明 |
|------|------|------|
| Pi GitHub | github.com/earendil-works/pi-coding-agent | Pi 主仓库 |
| Pi Extensions | Pi 文档 | 扩展开发 API (registerTool, hooks) |
| Pi RPC Mode | Pi 文档 | JSON-RPC stdin/stdout 协议规范 |
| Pi Models Config | Pi 文档 | models.json 格式和 provider 配置 |

### PySide6 / Qt

| 资源 | 链接 | 说明 |
|------|------|------|
| PySide6 文档 | Qt for Python | 官方 API 参考 |
| Qt Signals & Slots | Qt 文档 | 跨线程信号机制 |
| QThread 文档 | Qt 文档 | 工作线程最佳实践 |

### 相关项目

| 项目 | 说明 |
|------|------|
| MCP (Model Context Protocol) | Anthropic 的跨应用 AI 工具协议，Edini 的 Pi Extension 架构与其理念相似 |
| Axiom (Houdini AI Tool) | 社区 Houdini AI 助手，使用 OpenAI API |
| Houdini-ML | SideFX 的机器学习集成 |

## 设计参考

### 架构决策记录 (ADR)

1. **ADR-001: 双通道通信**
   - JSON-RPC (stdin/stdout) 用于 AI 对话流
   - HTTP (localhost) 用于工具执行
   - 原因：Pi 扩展和 Houdini Python 在不同进程，需要不同的 IPC 机制

2. **ADR-002: 代理工具模式**
   - Pi 端定义工具 schema (TypeBox) + HTTP 转发
   - Houdini 端只负责执行
   - 原因：保持工具定义的灵活性（TypeScript 类型安全），执行的安全性（Python 端校验）

3. **ADR-003: 无外部 PyPI 依赖**
   - edini 包只依赖 Python 标准库 + Houdini 自带的 PySide6
   - 原因：简化部署，用户无需在 Houdini Python 中 pip install

4. **ADR-004: settings.json 本地持久化**
   - API key 存在项目目录而非系统目录
   - 原因：多项目隔离，方便 gitignore
