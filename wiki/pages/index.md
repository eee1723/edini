# 📊 仪表盘

> **当前阶段**：UI 优化 — 双层折叠思考 · 实时工具面板 · Session 管理 · Viewport 截图 &nbsp;|&nbsp; **状态**：16 tools 就绪，Houdini 实机运行 &nbsp;|&nbsp; **最后更新**：2026-06-04

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
| UI 面板 | ✅ 三栏布局 · Pi CLI 风格思考交错 · 流式 Thinking · 可折叠 Tool Call 面板 · 执行/中止按钮切换 · 卡片式 Context · 统一字号(10-13pt) · 智能滚动 |
| Houdini 集成 | ✅ MainMenuCommon.xml · 包注册 · Alt+Shift+E 热键 |
| 工具执行器 | ✅ HTTP Server · 16 工具路由 · 健康检查 · 实时工具卡片 |
| Houdini 操作 | ✅ 场景查询 · 节点 CRUD · 参数读写 · 布局 · 搜索 |
| Pi 扩展 | ✅ 工具注册 · 系统提示注入 · TypeBox 参数校验 · thinking_delta / tool_result 事件 |
| 安装部署 | ✅ install.py · setup_pi.bat · settings.json 持久化 |
| Session 管理 | ✅ 会话持久化 · 自动命名 · 上下文重建 · 摘要压缩 · 历史切换 |
| 多模型 | ✅ DeepSeek V3/R1 · Anthropic · Provider 下拉 + Model 历史记忆 |
| 设置系统 | ✅ Provider/Model/API Key · 4 色主题实时预览 · 字体缩放 0.8-1.4 |
| 测试 | ⬜ 无自动化测试 |
| 多模态 | ✅ Viewport 截图（vision 模型支持） |

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
