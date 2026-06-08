# 📊 仪表盘

> **当前阶段**：评估系统完成 — 5 维度评分 + LLM-as-Judge + EvalDashboard &nbsp;|&nbsp; **状态**：17 tools 就绪，Houdini 实机运行，评估系统已上线 &nbsp;|&nbsp; **最后更新**：2026-06-08

## 快速导航

| 页面 | 说明 |
|------|------|
| [架构地图](architecture.html) | Edini 三层架构（Houdini ↔ JSON-RPC ↔ Pi Agent）及数据流 |
| [开发进度](progress.html) | 进度看板 · 已完成工作 · 下一步任务 |
| [工具清单](tools.html) | 16 个 Houdini 工具的完整目录 |
| [踩坑记录](pitfalls.html) | 开发中的踩坑记录，支持分类/优先级/状态筛选 |
| [参考资料](references.html) | 外部文档 · 设计决策 · API 参考 |
| [Agent交接](handoff.html) | 给新 Agent 和开发者的快速上下文 |
| [评估系统](evaluation.html) | 智能体评估系统的设计理念与迭代记录 |

## 当前阶段

| 模块 | 状态 |
|------|------|
| UI 面板 | ✅ 三栏布局 · Thinking 面板 · Tool Call 面板 · 时间线 Widget bubble · Markdown 双格式化器（完整解析 + 流式安全）· 文本选择 · 历史气泡合并 · 知识过滤 · 智能滚动 · 4 层统一字号 · 无文字裁切 |
| Houdini 集成 | ✅ MainMenuCommon.xml · 包注册 |
| 工具执行器 | ✅ HTTP Server · 16 工具路由 · 健康检查 · 实时工具卡片 |
| Houdini 操作 | ✅ 场景查询 · 节点 CRUD · 参数读写 · 布局 · 搜索 |
| Pi 扩展 | ✅ 16 tools (TypeBox) · edini-context 铁律注入 + Houdini 上下文 |
| 安装部署 | ✅ install.py · setup_pi.bat · settings.json 持久化 |
| Session 管理 | ✅ pi 接管会话（cwd=HIP）· pi_sessions.py 读 JSONL · 浏览模式 · new/switch/set_name/get_state RPC |
| 多模型 | ✅ DeepSeek V3/R1 · Anthropic · Provider 下拉 + Model 历史记忆 |
| 设置系统 | ✅ General + Knowledge 双标签 · 主题/字体 · 知识开关/统计/管理 |
| 知识沉淀 | ✅ 两层架构（铁律 rules.json ≤20 + 知识库 entries.json）· AI 反思 → 用户确认 · 类型可切换 · 只提取会重复犯的错 |
| 多模态 | ✅ pi-visionizer 视觉代理 + Qwen-VL · 📷 截图 + 📁 上传按钮 · 全渠道图片输入（Ctrl+V + 右键粘贴 + 拖拽 + 文件选择）· 附件预览栏（真实缩略图）· 视觉描述气泡（可折叠+查看原图）· 识别中状态提示 · Houdini 20 API 适配（saveImage/grabFrameBuffer→flipbook）· QImage.save() QBuffer/BytesIO 兼容修复 · 剪贴板多模式探测（image/mimeData/URL/raw）|
| 变更树 | ✅ QTreeWidget 面板（diff · undo/redo · 节点跳转 · 参数折叠 · 空时不展开 · 自变参数过滤 · 切换清除） |
| 节点创建 | ✅ namespace 自动解析 · shelf tool 预设应用 · diff 过滤内部子节点 |
| 按钮布局 | ✅ 📷 截图 + 📁 上传（文本标签按钮，minHeight 34px，hover/pressed 动效）· 仅对话右对齐 · 执行按钮 minWidth 90px · 6px/8px 间距优化 |
| 剪贴板 | ✅ Ctrl+V 图片粘贴 · 右键粘贴图片到附件栏 · 右键粘贴文本（defer focus+paste）· 多模式探测（QImage→mimeData→URL→raw png/jpeg）· Houdini PySide6 枚举兼容（整数 mode 值）|
| 测试 | ⬜ 无自动化测试 |
| 知识检索 | ⬜ search_knowledge 工具待实现 |
| 评估系统 | ✅ 5 维度评分 · LogParser · SQLite · EvalDashboard · edini_get_eval_stats · LLM-as-Judge (deepseek-chat) |

## 技术栈

| 层级 | 技术 |
|------|------|
| 宿主应用 | Houdini 21 / Python 3 / PySide6 |
| UI 层 | QMainWindow · QSplitter · QTextEdit · QThread |
| 通信层 | JSON-RPC (stdin/stdout) · HTTP (localhost:9876) |
| AI 后端 | Pi Coding Agent (Node.js) · DeepSeek V3/R1 · TypeBox |
| 扩展 | Pi Extensions (TypeScript) · edini-tools · edini-context |
| 存储 | settings.json · rules.json · entries.json · pi JSONL sessions · edini_images/ 图片缓存 |
| 部署 | npm global · install.py 包注册 |

---

*本 Wiki 由 AI Agent 维护。说"更新 wiki"可刷新内容，说"继续项目"可从当前状态接着做。*
