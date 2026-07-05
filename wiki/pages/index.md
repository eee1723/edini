# 📊 仪表盘

> **当前阶段**：统一对话窗口架构完成 + 工具链全量修复&nbsp;|&nbsp; **状态**：主 Agent 窗口 + HDA 窗口共享组件库，HDA 窗口三面板升级（橙色 + 版本列表 + workspace lock），15+ 工具链 bug 修复&nbsp;|&nbsp; **最后更新**：2026-07-05

## 快速导航

| 页面 | 说明 |
|------|------|
| [架构地图](architecture.html) | Edini 三层架构（Houdini ↔ JSON-RPC ↔ Pi Agent）及数据流 |
| [开发进度](progress.html) | 进度看板 · 已完成工作 · 下一步任务 |
| [统一对话窗口](unified-chat.html) | 主 Agent + HDA 窗口共享组件库架构（13 组件 + 5 装配层 + workspace lock） |
| [工具清单](tools.html) | 27 个 Houdini 工具的完整目录 |
| [Procedural Harness](procedural-harness.html) | 程序化建模沙盒、诊断、验证、提交流程与手测重点 |
| [踩坑记录](pitfalls.html) | 开发中的踩坑记录，支持分类/优先级/状态筛选 |
| [参考资料](references.html) | 外部文档 · 设计决策 · API 参考 |
| [组件地基验证](project-component-foundation.html) | Project HDA 组件建模地基的 GUI 验证指南（subnet 组件 + 端口信息点 + 输入/输出脚手架 + promote）|
| [Agent交接](handoff.html) | 给新 Agent 和开发者的快速上下文 |
| [评估系统](evaluation.html) | 智能体评估系统的设计理念与迭代记录 |
| [知识→Skills演化](skills-evolution.html) | Hivemind 式持续学习：Traces → Knowledge → Pi Skills 闭环设计 |

## 当前阶段

| 模块 | 状态 |
|------|------|
| UI 面板 | ✅ 三栏布局 · Thinking 面板 · Tool Call 面板 · 时间线 Widget bubble · Markdown 双格式化器（完整解析 + 流式安全）· 文本选择 · 历史气泡合并 · 知识过滤 · 智能滚动 · 4 层统一字号 · 无文字裁切 |
| Houdini 集成 | ✅ MainMenuCommon.xml · 包注册 |
| 工具执行器 | ✅ HTTP Server · 27 工具路由 · Procedural Harness handlers · 健康检查 · 实时工具卡片 |
| Houdini 操作 | ✅ 场景查询 · 节点 CRUD · 参数读写 · 布局 · 搜索 |
| Pi 扩展 | ✅ 27 tools (TypeBox) · harness tool schema · edini-context 铁律注入 + Houdini 上下文 |
| 安装部署 | ✅ install.py · setup_pi.bat · settings.json 持久化 |
| Session 管理 | ✅ pi 接管会话（cwd=HIP）· pi_sessions.py 读 JSONL · 浏览模式 · new/switch/set_name/get_state RPC |
| 多模型 | ✅ DeepSeek · Anthropic · OpenAI · Google · 智谱(ZhipuAI Coding Plan) · 阿里云百炼(aliyun) · 35 内置供应商自动同步 · 自定义供应商支持 · 视觉模型独立配置 |
| 设置系统 | ✅ Providers & Models + Appearance + Knowledge 三标签 · Login/Logout pi CLI 风格 · 供应商列表自动同步 pi-ai · Chat Model + Vision Model 独立选择 · 主题/字体 · 知识开关 |
| 知识沉淀 | ✅ 两层架构（铁律 rules.json ≤20 + 知识库 entries.json）· AI 反思 → 用户确认 · 类型可切换 · 只提取会重复犯的错 |
| 多模态 | ✅ pi-visionizer 视觉代理 + Qwen-VL · 📷 截图 + 📁 上传按钮 · 全渠道图片输入（Ctrl+V + 右键粘贴 + 拖拽 + 文件选择）· 附件预览栏（真实缩略图）· 视觉描述气泡（可折叠+查看原图）· 识别中状态提示 · Houdini 20 API 适配（saveImage/grabFrameBuffer→flipbook）· QImage.save() QBuffer/BytesIO 兼容修复 · 剪贴板多模式探测（image/mimeData/URL/raw）|
| 变更树 | ✅ QTreeWidget 面板（diff · undo/redo · 节点跳转 · 参数折叠 · 空时不展开 · 自变参数过滤 · 切换清除） |
| 节点创建 | ✅ namespace 自动解析 · shelf tool 预设应用 · diff 过滤内部子节点 |
| 按钮布局 | ✅ 📷 截图 + 📁 上传（文本标签按钮，minHeight 34px，hover/pressed 动效）· 仅对话右对齐 · 执行按钮 minWidth 90px · 6px/8px 间距优化 |
| 剪贴板 | ✅ Ctrl+V 图片粘贴 · 右键粘贴图片到附件栏 · 右键粘贴文本（defer focus+paste）· 多模式探测（QImage→mimeData→URL→raw png/jpeg）· Houdini PySide6 枚举兼容（整数 mode 值）|
| 测试 | ✅ 382 测试通过（mock_hou 脱机 + harness/recipe/orientation/health 单测 + 真实 Houdini manual_verify_fixes.py 13/13）|
| 知识检索 | ✅ edini_search_knowledge 工具已实现 |
| 知识→Skills | ⬜ Traces → Skills 自动提取（规划中） |
| 评估系统 | ✅ 5 维度评分 · LogParser · SQLite · EvalDashboard · edini_get_eval_stats · LLM-as-Judge (deepseek-chat) |
| Recipe Library | ✅ **schema v2** · 5 工具（list/read/capture/**capture_tree**/rebuild）· 递归树抓取（树路径 recipe_id 防撞名）· kind（network\|vex）· vex_snippets（wrangle 代码+runover 可搜）· tree_path 分类面包屑 · 自动忽略 output/stashed 节点 · 空 Notes 自动生成 · 真实 Houdini 闭环已验证（6 叶子分类树一次性抓取）· popnet 穿透 bug 已修 · 30+2 subtests 全绿 · **2026-06-26 manifest 精度大修**（向量真实分量名/multiparm/版本别名/中英检索/孤儿清理）|
| 声明式资产管道 | ✅ **里程碑2 完整交付** · 2 backend（native_chain + python 值注入）· 3 placement（attach / instances / **from-to 两点连接**）· orient 旋转 · 真机生成桌子/椅子/**自行车**（4 管材 + 2 轮子，224 点）· 实战测试暴露并修复 3 真实缺陷 · [路线图](progress.html#下一步计划) |
| **Project HDA**（新主线） | 🚧 **组件建模地基已交付（子系统 1），待 GUI 验证 → 子系统 2/3/4** · 范式重构：subnet 组件 + 端口信息点协议（`out[0]`=主几何 / `out[1..n]`=带属性锚点云）+ 输入脚手架（`in_<from>_<anchor>`）+ 组件流水线协作 + promote 参数提取 · 旧 rooted assembly 范式已移除 · 声明即知识图谱，drift = diff 意图 vs 实际网络（子系统 4）· builder=脚手架（确定性）/ 几何=LLM 自由活 · hython 决定性验证 6 测全过（subnet output 节点机制 + indirectInputs 输入 + spare parm 真实 API 三项真机发现）· [地基 spec](../docs/superpowers/specs/2026-07-02-project-component-foundation-design.md) · [地基计划](../docs/superpowers/plans/2026-07-02-project-component-foundation.md) · [GUI 验证指南](project-component-foundation.html) · 分支 `feat/project-component-foundation`（已合并 master）|
| Procedural Harness（已关闭） | ⚰️ **已备份到 `_disabled_backup/`**，部分高质量前身（exprs/component_registry）被资产管道复活复用。旧版：`houdini_run_python_sandbox` · 声明式 Recipe Builder（`houdini_build_procedural_asset`）· 构造轴 · commit/discard lifecycle · [手测清单](procedural-harness.html) |

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
