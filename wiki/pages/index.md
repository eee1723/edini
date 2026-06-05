# 📊 仪表盘

> **当前阶段**：变更树 QTreeWidget 面板 + SnapshotEngine · Undo/Redo 栈 · Shelf Tool 预设 · 节点 namespace 解析 · UI 字体协调优化 &nbsp;|&nbsp; **状态**：16 tools 就绪，Houdini 实机运行 &nbsp;|&nbsp; **最后更新**：2026-06-05

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
| UI 面板 | ✅ 三栏布局 · Thinking 面板（内联 QTextEdit，可折叠，实时流展开/收拢）· Tool Call 面板（fixedHeight 折叠/展开）· 时间线 QScrollArea + Widget bubble（_UserBubble / _AiBubble / _Separator / _ErrorBanner）· 知识确认区（铁律/知识徽章可切换 + ✓✕）· 卡片式 Context · 智能滚动（rangeChanged + _pinned_to_bottom）· 代码 Copy（QLabel linkActivated + base64）· 气泡窗口自适应（Expanding + margin）· 完成后自动折叠面板 · 4 层统一字号体系（header fs13 / body fs12 / detail fs11 / caption fs10）· 全局 fs() 缩放 · 无文字裁切 |
| Houdini 集成 | ✅ MainMenuCommon.xml · 包注册 |
| 工具执行器 | ✅ HTTP Server · 16 工具路由 · 健康检查 · 实时工具卡片 |
| Houdini 操作 | ✅ 场景查询 · 节点 CRUD · 参数读写 · 布局 · 搜索 |
| Pi 扩展 | ✅ 16 tools (TypeBox) · edini-context 铁律注入 + Houdini 上下文 |
| 安装部署 | ✅ install.py · setup_pi.bat · settings.json 持久化 |
| Session 管理 | ✅ pi 接管会话（cwd=HIP）· pi_sessions.py 读 JSONL · 浏览模式 · new/switch/set_name/get_state RPC |
| 多模型 | ✅ DeepSeek V3/R1 · Anthropic · Provider 下拉 + Model 历史记忆 |
| 设置系统 | ✅ General + Knowledge 双标签 · 主题/字体 · 知识开关/统计/管理 |
| 知识沉淀 | ✅ 两层架构（铁律 rules.json ≤20 + 知识库 entries.json）· AI 反思 → 用户确认 · 类型可切换 · 只提取会重复犯的错 |
| 多模态 | ✅ Viewport 截图（vision 模型） |
| 变更树 | ✅ QTreeWidget 面板（snapshot diff · undo/redo 栈 · 节点跳转 · 参数折叠显示 · 自动折叠/展开） |
| 节点创建 | ✅ namespace 自动解析 · shelf tool 预设应用 · diff 过滤内部子节点 |
| 测试 | ⬜ 无自动化测试 |
| 知识检索 | ⬜ search_knowledge 工具待实现 |

## 技术栈

| 层级 | 技术 |
|------|------|
| 宿主应用 | Houdini 21 / Python 3 / PySide6 |
| UI 层 | QMainWindow · QSplitter · QTextEdit · QThread |
| 通信层 | JSON-RPC (stdin/stdout) · HTTP (localhost:9876) |
| AI 后端 | Pi Coding Agent (Node.js) · DeepSeek V3/R1 · TypeBox |
| 扩展 | Pi Extensions (TypeScript) · edini-tools · edini-context |
| 存储 | settings.json · rules.json · entries.json · pi JSONL sessions |
| 部署 | npm global · install.py 包注册 |

---

*本 Wiki 由 AI Agent 维护。说"更新 wiki"可刷新内容，说"继续项目"可从当前状态接着做。*
