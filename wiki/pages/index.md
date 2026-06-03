# 📊 仪表盘

> **当前阶段**：UI 重构 — Houdini 原生菜单 + 三栏面板 + 暗色主题 &nbsp;|&nbsp; **状态**：16 tools 就绪，Houdini 实机运行 &nbsp;|&nbsp; **最后更新**：2026-06-03

## 快速导航

| 页面 | 说明 |
|------|------|
| [架构地图](architecture.html) | Edini 三层架构（Houdini ↔ JSON-RPC ↔ Pi Agent）及数据流 |
| [开发进度](progress.html) | 进度看板 · 已完成工作 · 下一步任务 |
| [工具清单](tools.html) | 16 个 Houdini 工具的完整目录 |
| [踩坑记录](pitfalls.html) | 开发中的踩坑记录，支持分类/优先级/状态筛选 |
| [参考资料](references.html) | 外部文档 · 设计决策 · API 参考 |
| [Agent交接](handoff.html) | 给新 Agent 和开发者的快速上下文 |

## 当前阶段

| 模块 | 状态 |
|------|------|
| UI 面板 | ✅ 三栏布局 · 时间线 · Pi面板 · 场景面板 · 暗色主题(16px) |
| Houdini 集成 | ✅ MainMenuCommon.xml · 包注册 · Alt+Shift+E 热键 |
| 工具执行器 | ✅ HTTP Server · 16 工具路由 · 健康检查 |
| Houdini 操作 | ✅ 场景查询 · 节点 CRUD · 参数读写 · 布局 · 搜索 |
| Pi 扩展 | ✅ 工具注册 · 系统提示注入 · TypeBox 参数校验 |
| 安装部署 | ✅ install.py · setup_pi.bat · settings.json 持久化 |
| 多模型 | ⚠️ DeepSeek V3/R1 ok，待加 Anthropic/Qwen |
| 测试 | ⬜ 无自动化测试 |
| 多模态 | ⬜ 图片输入未实现 |

## 技术栈

| 层级 | 技术 |
|------|------|
| 宿主应用 | Houdini 21 / Python 3 / PySide6 |
| UI 层 | QWidget · QScrollArea · QLineEdit · QThread |
| 通信层 | JSON-RPC (stdin/stdout) · HTTP (localhost:9876) |
| AI 后端 | Pi Coding Agent (Node.js) · DeepSeek V3/R1 · TypeBox |
| 扩展 | Pi Extensions (TypeScript) · edini-tools · edini-context |
| 部署 | npm global · install.py 包注册 · settings.json |

---

*本 Wiki 由 AI Agent 维护。说"更新 wiki"可刷新内容，说"继续项目"可从当前状态接着做。*
