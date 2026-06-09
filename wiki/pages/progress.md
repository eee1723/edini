# 🚀 开发进度

> 最后更新：2026-06-09 &nbsp;|&nbsp; 第二十一阶段：知识反思面板 + 去重 ✅

## 总览看板

<div class="phase-grid">

<div class="phase-card">
  <div class="phase-card-header">
    <span class="phase-card-title">🖥️ PySide6 面板 UI</span>
    <span class="status-tag status-done">完成</span>
  </div>
  <div class="progress-bar-bg"><div class="progress-bar-fill progress-done" style="width:100%"></div></div>
  <div class="phase-card-detail">三栏布局 · Thinking 面板（可折叠、QTextEdit 纯文本流、实时展开/收拢）· Tool Call 面板（fixedHeight 折叠 24px↔200px、暗色协调、自动滚底）· 时间线 QScrollArea + Widget（_UserBubble / _AiBubble / _Separator / _ErrorBanner）· 智能滚动（rangeChanged valueChanged + _pinned_to_bottom 标志位）· Markdown 完整渲染（双格式化器 _format_full / _format_lite，标题/列表/表格/代码块/分隔线）· 文本选择（TextSelectableByMouse）· 知识提取确认区（铁律/知识卡片 + ✓✕ + 全部接受/放弃 + 类型切换）· 气泡 Expanding 填满窗口 · 完成后自动折叠面板 · 4 层统一字号 · 历史气泡合并 · 知识提取过滤</div>
</div>

<div class="phase-card">
  <div class="phase-card-header">
    <span class="phase-card-title">🔌 JSON-RPC 通信</span>
    <span class="status-tag status-done">完成</span>
  </div>
  <div class="progress-bar-bg"><div class="progress-bar-fill progress-done" style="width:100%"></div></div>
  <div class="phase-card-detail">subprocess + stdin/stdout · QThread 非阻塞 · 事件分发 (text_delta/thinking_delta/tool_call/tool_result) · 会话 RPC (new/switch/set_name/get_state) · extension_info 信号 · cwd 支持 · ensure_ascii=True · CREATE_NO_WINDOW</div>
</div>

<div class="phase-card">
  <div class="phase-card-header">
    <span class="phase-card-title">⚙️ 工具执行器</span>
    <span class="status-tag status-done">完成</span>
  </div>
  <div class="progress-bar-bg"><div class="progress-bar-fill progress-done" style="width:100%"></div></div>
  <div class="phase-card-detail">HTTP Server (127.0.0.1:9876) · 22 tool handlers · /health 端点 · JSON 序列化 · 异常处理</div>
</div>

<div class="phase-card">
  <div class="phase-card-header">
    <span class="phase-card-title">🎯 Houdini 操作 (node_utils)</span>
    <span class="status-tag status-done">完成</span>
  </div>
  <div class="progress-bar-bg"><div class="progress-bar-fill progress-done" style="width:100%"></div></div>
  <div class="phase-card-detail">场景查询 · 节点 CRUD · 参数读写 · 节点搜索 · 几何检查 · Python/VEX 执行 · HDA 创建 · 布局</div>
</div>

<div class="phase-card">
  <div class="phase-card-header">
    <span class="phase-card-title">🧩 Pi 扩展</span>
    <span class="status-tag status-done">完成</span>
  </div>
  <div class="progress-bar-bg"><div class="progress-bar-fill progress-done" style="width:100%"></div></div>
  <div class="phase-card-detail">22 tools (TypeBox schema) · edini-context 注入铁律（rules.json）+ Houdini 上下文 · forwardTool HTTP 转发 · edini_search_knowledge 知识检索</div>
</div>

<div class="phase-card">
  <div class="phase-card-header">
    <span class="phase-card-title">📦 安装部署</span>
    <span class="status-tag status-done">完成</span>
  </div>
  <div class="progress-bar-bg"><div class="progress-bar-fill progress-done" style="width:100%"></div></div>
  <div class="phase-card-detail">install.py (Houdini 包注册) · setup_pi.bat · settings.json · Pi 路径自动检测 · env var 覆盖 · 隐藏 Windows 控制台</div>
</div>

<div class="phase-card">
  <div class="phase-card-header">
    <span class="phase-card-title">🎨 UI 字体</span>
    <span class="status-tag status-done">完成</span>
  </div>
  <div class="progress-bar-bg"><div class="progress-bar-fill progress-done" style="width:100%"></div></div>
  <div class="phase-card-detail">4层统一字号（header 13pt/body 12pt/detail 11pt/caption 10pt）· 全局 fs() 缩放 · 消除硬编码 pt · 面板高度/宽度适配 · 6 文件精确修改</div>
</div>

<div class="phase-card">
  <div class="phase-card-header">
    <span class="phase-card-title">🧪 测试</span>
    <span class="status-tag status-done">完成</span>
  </div>
  <div class="progress-bar-bg"><div class="progress-bar-fill progress-done" style="width:100%"></div></div>
  <div class="phase-card-detail">✅ Mock Hou 模块（MockNode/MockParm/MockNodeType/MockCategory）· ✅ 105+ 单元测试（node_utils 48 + config 24 + knowledge_store 33）· ✅ 全部 22 handler 脱机测试 · ⬜ 集成测试 · ⬜ 端到端测试</div>
</div>

<div class="phase-card">
  <div class="phase-card-header">
    <span class="phase-card-title">🌐 多模型 & 多模态</span>
    <span class="status-tag status-done">完成</span>
  </div>
  <div class="progress-bar-bg"><div class="progress-bar-fill progress-done" style="width:100%"></div></div>
  <div class="phase-card-detail">✅ DeepSeek V4 Pro/V3/R1 · ✅ Anthropic Claude · ✅ Viewport 截图（Houdini 20 flipbook 单帧 + frameRange([1.0,1.0]) 修复）· ✅ pi-visionizer 视觉代理（Qwen-VL Max）· ✅ 全渠道图片输入（截图/拖拽/粘贴/文件选择 + 右键菜单）· ✅ 附件预览栏（真实缩略图，最多5张）· ✅ 视觉描述气泡（可折叠、查看原图、错误变体）· ✅ AI 工具主动读图（describe_image）· ✅ 识别中状态提示（🔍 正在识别图片…）· ✅ 时间线缩略图卡片（96×68 点击查看原图、原始文件名保留）· ✅ 图片缓存持久化（edini_images/ 目录，切换对话可回看）· ✅ 视觉描述持久化（descriptions.json 缓存，历史气泡渲染）· ✅ Defer 缓存写入 · ✅ 📷 截图 + 📁 上传按钮优化（文本标签、hover/pressed 动效、布局重排）· ✅ Ctrl+V + 右键粘贴图片 · ✅ 剪贴板多模式探测（image/mimeData/URL/raw）· ✅ Houdini 20 API 适配（saveImage/grabFrameBuffer 移除→flipbook）· ✅ QImage.save() BytesIO/QBuffer 兼容修复 · ✅ PySide6 Qt.Clipboard 枚举兼容</div>
</div>

<div class="phase-card">
  <div class="phase-card-header">
    <span class="phase-card-title">🧠 知识沉淀系统</span>
    <span class="status-tag status-done">完成</span>
  </div>
  <div class="progress-bar-bg"><div class="progress-bar-fill progress-done" style="width:100%"></div></div>
  <div class="phase-card-detail">✅ 两层架构（铁律 rules.json ≤20条 + 知识库 entries.json）· ✅ 对话结束 AI 反思 → 用户确认（面板内 ✓✕）· ✅ 铁律自动注入 system prompt · ✅ 管理弹窗（双标签增删改搜索）· ✅ Settings Knowledge 标签页 · ✅ 类型可切换（铁律↔知识）· ✅ 只提取会重复犯的错</div>
</div>

</div>

<div class="phase-card">
  <div class="phase-card-header">
    <span class="phase-card-title">📐 评估系统</span>
    <span class="status-tag status-done">完成</span>
  </div>
  <div class="progress-bar-bg"><div class="progress-bar-fill progress-done" style="width:100%"></div></div>
  <div class="phase-card-detail">✅ 5 维度评估管道（3 确定性 + 2 LLM-as-Judge）· ✅ SQLite 评估仓库（sessions/tool_calls/judge_logs/daily_aggregates）· ✅ LogParser 从 Pi JSONL 解析会话 · ✅ 增量评估（只评未评分的会话）· ✅ EvalDashboard UI（概览卡片 + 趋势图 + 会话列表）· ✅ AgentEval 工具（edini_get_eval_stats 自省）· ✅ 后台自动评估 · ✅ 8 个真实 Houdini 会话实测通过 · ✅ Wiki 设计理念文档 · ✅ 纯确定性评估(force_no_judge)跑通16会话 / LLM Judge可选 / ⚡ Re-evaluate按钮</div>
</div>

</div>

## 近期关键节点

<div class="timeline">

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-06-09</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第二十一阶段：知识反思面板 + 去重</span>
      <span class="status-tag status-done">完成</span>
    </div>
    <div class="timeline-summary">① ReflectWorker（QThread 后台线程）：对话结束后独立 HTTP 调 LLM API 反思，不占用主时间线 ② KnowledgeZone 替代旧 Knowledge 卡片：可折叠规则/条目浏览 + 反思过程实时展示 + 条目卡片确认/拒绝 ③ Jaccard 标题去重：新条目自动检测与已有知识的相似度，≥0.5 标记为 merge ④ 合并：merge_entry 将新旧条目内容合并为一个更通用的版本 ⑤ 设置面板新增"反思模型"选择（Provider + Model），默认对话模型 ⑥ AgentPanel 移除旧的知识提取 UI（~160 行） ⑦ MainWindow 旧提取流程替换为 ReflectWorker 触发</div>
    <div class="timeline-tags">
      <span>ReflectWorker</span><span>KnowledgeZone</span><span>Jaccard去重</span><span>HTTP直调</span><span>反思模型配置</span>
    </div>
  </div>
</div>

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-06-09</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第二十阶段：测试基建 + 知识检索闭环 + 评估联动</span>
      <span class="status-tag status-done">完成</span>
    </div>
    <div class="timeline-summary">① Mock Hou 模块（MockNode/MockParm/MockNodeType/MockCategory）支持全部 22 个 handler 脱机测试 ② node_utils 单元测试 48 用例覆盖全部 handler ③ config.py 测试 24 用例覆盖读写 JSON、路径查找、legacy 迁移 ④ knowledge_store 测试 33 用例覆盖 CRUD/search/parse extraction ⑤ edini_search_knowledge Pi 工具注册，Agent 可查询知识库 ⑥ 评估低分会话自动提取知识条目 ⑦ 全部测试 105+ 通过</div>
    <div class="timeline-tags">
      <span>单元测试</span><span>Mock Hou</span><span>知识检索</span><span>评估联动</span>
    </div>
  </div>
</div>

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-06-09</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第十九阶段：供应商与模型配置重构 — pi CLI 风格 + pi-ai 自动同步</span>
      <span class="status-tag status-done">完成</span>
    </div>
    <div class="timeline-summary">① 设置面板重构为 3 Tab：Providers & Models / Appearance / Knowledge ② Login/Logout pi CLI 风格交互：可搜索供应商列表（35 内置供应商 + 自定义供应商）→ API Key 输入 ③ pi_data_bridge.js Node.js 桥接：读取已安装 pi-ai 包数据，pi 更新后自动同步 ④ Chat Model Provider→Model 级联下拉 + Vision Model 独立选择（仅 image-capable 模型） ⑤ 自定义供应商支持 API Key ⑥ 修复：models.json 无效 provider 导致 pi 拒绝加载所有自定义供应商（根本原因）→ 视觉识别从此正常工作</div>
    <div class="timeline-tags">
      <span>pi-ai同步</span><span>Login/Logout</span><span>Vision Model</span><span>35供应商</span><span>视觉识别修复</span>
    </div>
  </div>
</div>

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-06-08</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第十八阶段：评估修复 + 工具补齐 + 智谱Provider + 设置增强</span>
      <span class="status-tag status-done">完成</span>
    </div>
    <div class="timeline-summary">① 三层评估架构：数据模型（StructuredSession/ToolCallRecord/EvalResult）→ SQLite EvalStore（4 表 CRUD + 聚合）→ EvaluatorPipeline（5维度：reliability/efficiency/cost 确定性 + tool_accuracy/task_completion LLM-as-Judge）② LogParser 适配 Pi RPC JSONL 格式（message.toolName 提取工具名，content 解析 success/error）③ EvalDashboard UI（_ScoreCard 概览卡片、_TrendChart 趋势折线图、QTableWidget 会话列表、双击导航）④ edini_get_eval_stats Pi Extension 工具（自省：平均分/趋势/最弱维度/常见错误）⑤ MainWindow 集成（状态栏 📊 Eval 按钮 + 弹窗）⑥ 后台自动触发评估（finish_streaming/show_aborted → 线程评估 → 保存）⑦ LLM-as-Judge 真实 API 调用（DeepSeek deepseek-chat，2 轮/会话，～4.4s 平均）· 实测 8 个 Houdini 对话，评分合理有区分度 · 发现 V4 Pro reasoning_tokens 问题 · Wiki 记录设计理念 + 实测结果 + 经验教训</div>
    <div class="timeline-tags">
      <span>5维度评估</span><span>SQLite</span><span>LLM-as-Judge</span><span>LogParser</span><span>EvalDashboard</span><span>edini_get_eval_stats</span><span>后台评估</span><span>DeepSeek</span><span>V4 Pro推理问题</span><span>设计理念</span>
    </div>
  </div>
</div>

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-06-08</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第十八阶段：评估修复 + 工具补齐 + 智谱Provider + 设置面板增强</span>
      <span class="status-tag status-done">完成</span>
    </div>
    <div class="timeline-summary">① Eval修复：force_no_judge LLM Judge失败自动回退 / traceback完整日志 / PRAGMA d[0]→d[1]修复 / ⚡ Re-evaluate按钮 / 纯确定性评估先跑通16个历史会话 ② 缺失工具补齐：houdini_get_selection (hou.selectedNodes) / houdini_check_errors (allSubChildren errors+warnings) / houdini_set_display_flag (setDisplayFlag) — scene.ts已注册但Python handler缺失 ③ Ramp参数安全：_safe_parm_value() 检测hou.Ramp返回结构化keys / allowEditingOfContents解锁HDA子节点 / HDADefinition属性安全read ④ 智谱Coding Plan接入：新建edini-zhipu扩展(5模型: glm-5.1/5/4.7/4.6v/4.5v) / Coding专属端点 / ZHIPU_USE_CODING=1切换 ⑤ API Key修复：get_pi_env()改用_set_provider_api_key按provider分发 / send_set_model在connect+save时调用 ⑥ 设置面板增强：新增Vision标签(视觉Provider/Model/Key) / Test Model按钮(通过tool_executor:9876/test_model中转，ssl._create_unverified_context) / QTimer.singleShot替代QMetaObject.invokeMethod / 按钮状态瞬时反馈+异常捕获 ⑦ 知识库清理：合并3条重复Ramp规则→1条/更新已修复工具规则/20→18</div>
    <div class="timeline-tags">
      <span>Eval修复</span><span>3个缺失工具</span><span>Ramp安全</span><span>智谱Provider</span><span>CodingPlan</span><span>Vision设置</span><span>Test按钮</span><span>APIKey修复</span><span>知识库清理</span>
    </div>
  </div>
</div>

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-06-08</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第十七阶段补丁：端到端调试与 Python 3.11 兼容修复</span>
      <span class="status-tag status-done">完成</span>
    </div>
    <div class="timeline-summary">① 修复 f-string 反斜杠兼容问题（eval_tab.py — 改用 _EM_DASH 常量；evaluator.py — 改用变量 _json_example）② 修复 ScoreCard 按钮裁切（125px+dialog 960px+QScrollArea）③ 修复 session 路径时序竞争（agent_end 先于 session_switched — 延迟触发评估）④ 修复 _debug_log 函数缩进错误吞掉后续 AgentPanel 方法（_toggle_thinking_panel 找不到）⑤ 添加诊断日志系统（_debug_log 写入 %%TEMP%%/edini_eval_debug.log）⑥ 空数据状态显示提示文字</div>
    <div class="timeline-tags">
      <span>f-string兼容</span><span>Python3.11</span><span>时序竞争</span><span>缩进bug</span><span>诊断日志</span><span>UI适配</span>
    </div>
  </div>
</div>

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-06-06</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第十六阶段：多模态 UI 按钮优化 + 剪贴板全渠道修复</span>
      <span class="status-tag status-done">完成</span>
    </div>
    <div class="timeline-summary">① 📋 Paste 按钮移除：用户通过 Ctrl+V 或右键粘贴，不占面板空间 ② 按钮布局重排：📷 截图 + 📁 上传改为文本标签按钮（minHeight 34px, padding 4px 10px），不再被裁切，hover/pressed 动效 ③ 仅对话右对齐 · 执行按钮 minWidth 90px · 6px/8px 间距 ④ 移除旧截图槽位+移除按钮，截图统一走附件栏 ⑤ 剪贴板粘贴修复：QImage.save() 在 Houdini PySide6 中不接受 BytesIO/QBuffer → 改用 tempfile 中转 ⑥ 剪贴板多模式探测：image()→mimeData().imageData()→URLs→raw image/png image/jpeg，覆盖浏览器/截图工具/文件管理器等所有来源 ⑦ Houdini 20 视窗截图修复：saveImage() 和 grabFrameBuffer() 在 20.x 中已移除 → flipbook 方法 frameRange([1.0, 1.0]) 修复 ⑧ 右键上下文菜单：monkey-patch contextMenuEvent（Houdini 阻止 eventFilter 收到 ContextMenu 事件），图片剪贴板时显示 "📋 粘贴图片到附件栏" + "粘贴文本"（QTimer.singleShot defer focus+paste），无图片时走原生菜单 ⑨ PySide6 枚举兼容：Qt.Clipboard/Selection/FindBuffer 不存在 → 整数 mode 值 0/1/2</div>
    <div class="timeline-tags">
      <span>按钮布局</span><span>剪贴板修复</span><span>右键菜单</span><span>Houdini20适配</span><span>QImage.save</span><span>PySide6兼容</span><span>contextMenuEvent</span><span>tempfile</span>
    </div>
  </div>
</div>

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-06-06</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第十五阶段：图片时间线显示 — 缩略图卡片 + 历史持久化 + 视觉描述缓存</span>
      <span class="status-tag status-done">完成</span>
    </div>
    <div class="timeline-summary">① ImageCacheManager：图片缓存与 Pi 会话同目录（edini_images/<session_id>/manifest.json + 原始图片文件），支持 save/load/prune ② 时间线缩略图卡片：_UserBubble 中 96×68 缩略图 _ClickableCard（IgnoreAspectRatio 填满、QFrame mouseReleaseEvent 可靠点击），点击在 OS 查看器中打开 ③ 原始文件名保留：MediaItem.filename → _on_send → _on_agent_submit → 缓存 + 气泡，全链路传递 ④ 视觉描述持久化：_on_vision_description 收到通知时保存 descriptions.json，历史加载时重新渲染 VisionDescriptionBubble ⑤ Defer 缓存写入：_current_session_path 异步就绪时才写缓存，解决 Pi session 路径延迟问题 ⑥ _cleanup_recognizing 不再清除 _pending_images，避免缓存 flush 被跳过 ⑦ QPixmap 缩略图启用：make_thumbnail + _load_thumb_pixmap try/except 安全保护 ⑧ 附件栏缩略图恢复真实显示（不再 🖼️ 占位）⑨ 会话删除时自动清理孤立的图片缓存</div>
    <div class="timeline-tags">
      <span>缩略图卡片</span><span>图片缓存</span><span>历史持久化</span><span>视觉描述缓存</span><span>Defer写入</span><span>原始文件名</span><span>QPixmap</span><span>edini_images</span>
    </div>
  </div>
</div>

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-06-06</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第十四阶段：多模态调试修复 — 视觉管道打通 + UI 体验优化</span>
      <span class="status-tag status-done">完成</span>
    </div>
    <div class="timeline-summary">① 修复 pi-visionizer fetch 死锁：Windows 上 Pi 的 undici 全局代理导致 fetch() 永久挂起 → 改用 Node.js 原生 https.request() ② 修复通知 API：sendUiRequest 不存在 → 改用 ctx.ui.notify() ③ 修复 Aliyun API Key：auth.json 缺少 aliyun 条目 → 添加 sk-ded80b7... ④ 识别中状态提示：_RecognizingPlaceholder 虚线框 "🔍 正在识别图片…"，通知到达后自动替换 ⑤ 视觉描述气泡默认折叠：显示 "👁️ 图片识别完成 · qwen-vl-max · 3.2s ▶ 展开" ⑥ 查看原图：气泡内 📸 按钮用 OS 默认查看器打开原图 ⑦ 缩略图安全降级：QBuffer 导致 Houdini segfault → 改用 emoji 🖼️ 占位 ⑧ rpc_client 添加 stderr 读取线程 + vision_description 日志</div>
    <div class="timeline-tags">
      <span>https.request</span><span>undici死锁</span><span>ctx.ui.notify</span><span>识别中状态</span><span>默认折叠</span><span>查看原图</span><span>segfault修复</span>
    </div>
  </div>
</div>

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-06-05</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第十三阶段：多模态扩展 — 全渠道图片输入 + Qwen-VL</span>
      <span class="status-tag status-done">完成</span>
    </div>
    <div class="timeline-summary">① 全渠道图片输入：截图（三级降级修复 saveImage→grabFrameBuffer→flipbook）、拖拽（仅拦截图片 MIME）、粘贴（Ctrl+V 剪贴板图片）、文件选择（📁 按钮 + 多选过滤）② ImageAttachmentWidget 附件预览栏（缩略图 120×68 + 来源图标 + ✕ 删除，最多 5 张）③ VisionDescriptionBubble 视觉描述气泡（可折叠、查看原图、错误变体）④ pi-visionizer 默认视觉模型改为 aliyun/qwen-vl-max ⑤ pi-visionizer 写入 vision-description custom entry + extension_ui_request 实时通知 Edini ⑥ MediaManager 统一管理所有图片输入渠道 ⑦ rpc_client 新增 vision_description 信号</div>
    <div class="timeline-tags">
      <span>pi-visionizer</span><span>Qwen-VL</span><span>视觉代理</span><span>截图按钮</span><span>多模态</span>
    </div>
  </div>
</div>

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-06-05</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第十二阶段：时间线 Markdown 渲染 + 变更树修复</span>
      <span class="status-tag status-done">完成</span>
    </div>
    <div class="timeline-summary">① Markdown 双格式化器：_format_full（标题/列表/表格/代码块/p 段落）用于最终+历史，_format_lite（仅行内 bold/italic/code）用于流式 ② _render_body 统一 body 渲染（table/list/paragraph），header+body 组合支持（### 下跟表格/列表）③ 历史气泡合并：_merge_consecutive_assistants 合并 JSONL 中连续的 assistant entry 为单个气泡 ④ 知识提取过滤：_filter_knowledge_extraction 隐藏提取对话 ⑤ 文本选择：AiBubble/UserBubble 加 TextSelectableByMouse，UserBubble→RichText ⑥ 移除代码 Copy 按钮 ⑦ 间距收紧（line-height 1.55→1.45, padding 10/16→8/14）⑧ 标题裁切修复（COLLAPSED_H 20→24）⑨ 变更树空时不展开 ⑩ 快照 diff 过滤自变参数（time/frame/seed/cache）⑪ 切换/新建对话清除变更树+undo</div>
    <div class="timeline-tags">
      <span>双格式化器</span><span>完整Markdown</span><span>气泡合并</span><span>知识过滤</span><span>文本选择</span><span>变更树修复</span>
    </div>
  </div>
</div>

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-06-05</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第十一阶段：UI 字体协调优化</span>
      <span class="status-tag status-done">完成</span>
    </div>
    <div class="timeline-summary">统一整个 Edini UI 的字号层级为 4 层体系：① header (fs13) — 面板标题、section 标签 ② body (fs12) — 聊天气泡、标签、按钮、菜单、列表 ③ detail (fs11) — Thinking 内容、工具卡片、树节点、知识详情 ④ caption (fs10) — 状态栏、进度条、折叠头、徽章小字、tooltip。消除全部 fs(9) 和硬编码 pt 值（history_panel 原使用 raw "12pt"/"11pt"）。代码块和行内代码字号改用 fs() 缩放。放宽固定尺寸（知识徽章 36→40px，分类标签 32→40px，卡片行标签 50→56px，面板 COLLAPSED_H 22→24 / EXPANDED_H 260→280）。6 个文件精确修改，零裁切回归。</div>
    <div class="timeline-tags">
      <span>字号体系</span><span>4层统一</span><span>fs()缩放</span><span>消除硬编码pt</span><span>视觉协调</span>
    </div>
  </div>
</div>

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-06-05</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第十阶段：变更树 + Undo/Redo + 节点创建预设修复</span>
      <span class="status-tag status-done">完成</span>
    </div>
    <div class="timeline-summary">① SnapshotEngine（snapshot / diff / restore 三阶段节点级回滚）② ChangeTreeWidget 重写（QTreeWidget，按轮次分组，创建/修改/删除三级树，节点路径可点击跳转 viewport）③ Undo/Redo 栈（每轮对话一个事务，撤销=整轮回滚重建，重做=重放，手动修改场景自动清空栈）④ 对话中自动折叠、对话结束自动展开 ⑤ 节点创建 namespace 自动解析（裸名失败 → namespaceOrder → 全限定名）⑥ Shelf tool 预设自动应用（创建后查找匹配 tool 脚本，执行 pressButton/set 后处理操作）⑦ diff 过滤 Houdini 自动生成的子节点 ⑧ 参数紧凑显示（≤2参数全显示，3+ 收起为摘要，点击展开）</div>
    <div class="timeline-tags">
      <span>SnapshotEngine</span><span>变更树</span><span>Undo/Redo</span><span>视图跳转</span><span>namespace解析</span><span>tool预设</span><span>紧凑显示</span>
    </div>
  </div>
</div>

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-06-05</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第九阶段：时间线稳定性重构 — QScrollArea Widget 架构</span>
      <span class="status-tag status-done">完成</span>
    </div>
    <div class="timeline-summary">彻底重构时间线渲染引擎：① 从 QTextBrowser + setHtml 全量重绘 重构为 QScrollArea + 独立 Widget（_UserBubble / _AiBubble / _Separator / _ErrorBanner）② 智能滚动从 actionTriggered + 比例定位 改为 rangeChanged + valueChanged + _pinned_to_bottom 标志位（彻底消除抖动）③ 修复流式内容丢失 bug：_flush_thinking_buf 清空 _current_text 导致气泡只显示新 chunk，新增 _streaming_full_text 永不清空的累加器 ④ Thinking 面板实时更新：add_thinking_step 直接调用 _update_live_thinking，不再等待文字 chunk ⑤ 气泡大小固定：去掉 setMaximumWidth + stretch，改用 layout margin + Expanding sizePolicy 填满窗口 ⑥ 完成后自动折叠：_collapse_tool_panel + _collapse_thinking_panel 在 finish_streaming 和 show_aborted 中调用。修复：双 deleteLater、QLabel 选择器兼容、_raw_text 追踪。</div>
    <div class="timeline-tags">
      <span>QScrollArea</span><span>Widget架构</span><span>智能滚动</span><span>流式持久化</span><span>气泡自适应</span><span>自动折叠</span>
    </div>
  </div>
</div>

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-06-05</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第八阶段：知识沉淀系统重构 — 两层架构</span>
      <span class="status-tag status-done">完成</span>
    </div>
    <div class="timeline-summary">完全重构知识系统为两层架构：① 铁律层（rules.json，≤20条，每次会话自动注入 system prompt）② 知识库层（entries.json，无上限，细节化知识）③ 提取流程改为 AI 反思 → JSON 解析 → 聊天面板内确认区展示 → 用户逐条 ✓✕ 或全部接受/放弃 ④ 铁律/知识类型徽章可点击切换 ⑤ 提取 prompt 严格限制：只有会重复犯的错才提取，排除 LLM 已知的通用知识 ⑥ Settings Dialog 改为 General + Knowledge 双标签 ⑦ Context Panel 新增 Pi Status 工具信息 + 对话计时器 + Knowledge 卡片 ⑧ JSON 解析加固：代码块提取、单引号修复、尾逗号修复 ⑨ 提取响应不再渲染进时间线（get_raw_stream_text + cancel_current_stream）⑩ 移除调试 stderr 输出。修复：3 位 hex 颜色解析、knowledge_dialog 空指针、时间线消失 bug。</div>
    <div class="timeline-tags">
      <span>两层架构</span><span>用户确认面板</span><span>铁律上限20</span><span>类型切换</span><span>提取prompt优化</span><span>Settings双标签</span><span>JSON加固</span><span>12文件</span>
    </div>
  </div>
</div>

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-06-04</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第七阶段：知识沉淀系统初版 + Thinking 独立面板 + Windows 部署</span>
      <span class="status-tag status-done">已重构</span>
    </div>
    <div class="timeline-summary">初版知识沉淀系统（单文件 JSON、自动存储、无用户确认），已在第八阶段重构为两层架构。Thinking 面板从 _ThinkingPanelWidget 独立类重构为 AgentPanel 内联实现。部署完善：install.py + MainMenuCommon.xml + CREATE_NO_WINDOW + 进程终止加固。</div>
    <div class="timeline-tags">
      <span>已重构</span><span>初版v1</span><span>Thinking面板</span><span>部署配置</span>
    </div>
  </div>
</div>

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-06-04</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第六阶段：Session 浏览模式 + 三个 Bug 修复</span>
      <span class="status-tag status-done">完成</span>
    </div>
    <div class="timeline-summary">实现会话浏览模式并修复三个关键 Bug：① HistoryPanel 新增 set_browsing_mode() / highlight_session() / back_to_current_requested 信号 ② MainWindow 新增 _active_session_path / _browsing_session_path 状态字段 ③ 修复 Windows 盘符冒号 ④ 修复 Pi v3 session 格式兼容 ⑤ 修复 HOME vs USERPROFILE 路径问题。</div>
    <div class="timeline-tags">
      <span>浏览模式</span><span>回到当前</span><span>Windows路径修复</span><span>Pi v3兼容</span><span>HOME路径修复</span>
    </div>
  </div>
</div>

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-06-04</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第五阶段：Session 架构重构 — pi 接管会话管理</span>
      <span class="status-tag status-done">完成</span>
    </div>
    <div class="timeline-summary">彻底重构 Session 管理：① 删除 edini session_store.py，pi 成为唯一真理源 ② Popen(cwd=HIP) 启动（去掉 --no-session）③ 新建 pi_sessions.py 读 pi JSONL ④ RpcClient 新增 new/switch/set_name/get_state ⑤ ContextPanel reset_stats() ⑥ 修复窗口单例、ensure_ascii、_bootstrap 时序问题。</div>
    <div class="timeline-tags">
      <span>pi 接管 Session</span><span>删除 session_store</span><span>pi_sessions</span><span>Popen cwd</span><span>RPC 新命令</span>
    </div>
  </div>
</div>

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-06-04</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第四阶段：UI 稳定化 — Thinking 独立面板 · 纯文本流 · 滚动防抖</span>
      <span class="status-tag status-done">完成</span>
    </div>
    <div class="timeline-summary">重构 Thinking 展示：独立可折叠面板（QTextEdit 只读，自然段落分段，实时流 ▊ 光标，自动滚底）· Tool Call 面板 fixedHeight 折叠 · 智能滚动 actionTriggered + 同步比例定位 · TimelineView anchorClicked + base64 Copy · Thinking 实时分段。</div>
    <div class="timeline-tags">
      <span>Thinking 独立面板</span><span>纯文本流</span><span>防抖滚动</span><span>Copy 修复</span>
    </div>
  </div>
</div>

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-06-04 · 06-03</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第一~三阶段：基础架构 → UI 重构 → UI 精细化</span>
      <span class="status-tag status-done">完成</span>
    </div>
    <div class="timeline-summary">第一阶段：PySide6 + JSON-RPC + HTTP 工具执行器 + 16 tools + DeepSeek。第二阶段：Houdini 原生菜单 + QSplitter 三栏 + 暗色主题。第三阶段：Pi CLI 风格双层折叠 + Session 系统 + Viewport 截图 + 智能滚动。</div>
    <div class="timeline-tags">
      <span>PySide6</span><span>JSON-RPC</span><span>16 tools</span><span>三栏布局</span><span>Session管理</span>
    </div>
  </div>
</div>

</div>

## 下一步计划

| 优先级 | 任务 | 说明 |
|------|------|------|
| P1 | ~~时间线渲染~~ | ✅ Markdown 完整解析 + 气泡合并 + 文本选择 |
| P1 | ~~多模态视觉代理~~ | ✅ pi-visionizer 安装 + Qwen-VL 模型配置完成 |
| P1 | ~~截图链路修复~~ | ✅ 三级降级修复完成（saveImage → grabFrameBuffer → flipbook）|
| P1 | ~~图片时间线显示~~ | ✅ 缩略图卡片 + 缓存持久化 + 视觉描述历史渲染 |
| P2 | ~~知识库检索工具~~ | ✅ edini_search_knowledge 已实现 |
| P2 | ~~单元测试~~ | ✅ 105+ 测试通过（node_utils 48 + config 24 + knowledge_store 33） |
| P2 | Judge模型优化 | 接入 Anthropic Claude 做 Judge（结构化输出更强）、V4 Pro reasoning_tokens 兼容 |
| P3 | 效率基线优化 | 基于任务类型百分位计算效率评分，而非固定启发式 |
| P3 | ~~评估结果→知识系统~~ | ✅ 评估低分会话自动提取知识条目 |
| P3 | Python 面板 | 支持嵌入 Houdini Pane Tab |
| P2 | 多模型优化 | ~~Qwen 等更多 provider 快速切换~~ ✅ 已通过 35 内置供应商自动同步实现 |

## 已实现功能清单

- ✅ 自然语言创建节点 ("Create a smoke simulation")
- ✅ 参数控制 ("Set the grid size to 0.1")
- ✅ VEX 脚本执行 ("Write a VEX expression to scatter points")
- ✅ Python 脚本执行 ("Run a Python script to...")
- ✅ 场景检查 ("What's connected to this node?")
- ✅ HDA 创建 ("Package this network as a digital asset")
- ✅ 节点搜索 ("Find the Pyro solver node type")
- ✅ 节点帮助文档查询
- ✅ 几何体检查 (点/面/属性/包围盒)
- ✅ 流式响应 (打字机效果)
- ✅ 流式思考展示（独立 Thinking 面板、纯文本自然分段、实时流 ▊ 光标、自动滚底）
- ✅ 工具调用实时面板（fixedHeight 折叠 20px↔200px、执行状态 ✅/❌、结果预览、自动滚底）
- ✅ JavaScript-Free 文本选择（QLabel TextSelectableByMouse）
- ✅ 会话管理 (pi 接管：Popen cwd 按 HIP 归档 · JSONL 本地读取 · new/switch/set_name RPC)
- ✅ Viewport 截图（Houdini 20 flipbook 单帧 + frameRange([1.0,1.0]) 修复）
- ✅ 全渠道图片输入（截图 / 拖拽 / Ctrl+V / 右键粘贴 / 文件选择，原始文件名保留）
- ✅ 图片附件预览栏（真实缩略图 120×68，最多 5 张）
- ✅ 视觉描述气泡（可折叠，显示 Qwen-VL 分析结果，📸 查看原图 (N) 多图支持）
- ✅ 识别中状态提示（🔍 正在识别图片… 虚线框，通知到达自动替换）
- ✅ 视觉管道修复（fetch→https.request 绕过 undici 死锁，ctx.ui.notify 通知修复）
- ✅ 时间线缩略图卡片（96×68 缩略图 + 文件名 + 来源图标，点击在 OS 查看器中打开原图）
- ✅ 图片缓存持久化（edini_images/ 目录，按 session 隔离，切换历史对话可回看图片）
- ✅ 视觉描述缓存（descriptions.json，历史对话中自动渲染 VisionDescriptionBubble）
- ✅ Defer 缓存写入（session 路径异步就绪后自动刷入，解决端到端时序问题）
- ✅ API Key / Provider / Model 设置 (pi CLI 风格 Login/Logout + 35 供应商自动同步 + Vision Model 独立配置)
- ✅ 4 色主题实时预览 + 字体缩放
- ✅ 执行/中止按钮一体化切换
- ✅ 智能滚动（rangeChanged + valueChanged + _pinned_to_bottom 标志位，零抖动）
- ✅ 状态栏 (连接状态 / 模型 / 节点数)
- ✅ 多行输入 (Ctrl+Enter 换行，Enter 发送)
- ✅ 会话浏览模式（历史回看 + 回到当前）
- ✅ 对话轮次计时器（Pi Status 卡片实时显示 Round 时间）
- ✅ Pi Status 工具信息（Tools: 22 loaded, port 9876）
- ✅ 知识沉淀两层架构：铁律 (≤20, 上下文注入) + 知识库 (细节, 可检索)
- ✅ AI 反思 → 用户确认面板（✓✕ + 全部接受/放弃 + 类型切换）
- ✅ Settings Knowledge 标签页（开关 + 统计 + 管理按钮）
- ✅ 变更树 QTreeWidget 面板（按轮次分组：创建/修改/删除三级树，可折叠，对话结束自动展开）
- ✅ 4 层统一字号体系（header 13pt / body 12pt / detail 11pt / caption 10pt）
- ✅ 全局 fs() 缩放（历史面板、代码块等之前硬编码 pt 的元素全部改用 fs()）
- ✅ 消除 fs(9) 极小字号（全部提升至 fs(10)）
- ✅ 面板固定高度 + 徽章固定宽度与字号适配
- ✅ Markdown 双格式化器（_format_full 完整解析 + _format_lite 流式安全）
- ✅ 标题 #/##/### + 有序/无序列表 + 表格 + 代码块 + 分隔线 + 段落 p 分隔
- ✅ header+body 组合（### 标题下跟随表格/列表）
- ✅ 历史气泡合并（连续 assistant entry 合并为单个大气泡）
- ✅ 知识提取过滤（隐藏提取对话轮次）
- ✅ 文本选择（TextSelectableByMouse，所有气泡）
- ✅ pi-visionizer 视觉代理扩展（图片透明路由到 Qwen-VL Max，纯文本模型"看懂"截图）
- ✅ pi-visionizer 默认视觉模型改为 aliyun/qwen-vl-max
- ✅ pi-visionizer 写入 vision-description custom entry + 实时通知 Edini
- ✅ VisionDescriptionBubble 时间线内渲染（可折叠、查看原图、错误变体）
- ✅ 剪贴板多模式探测（QImage → mimeData.imageData → URLs → raw png/jpeg）
- ✅ 右键上下文菜单（图片剪贴板→粘贴图片到附件栏 + 粘贴文本，无图片→原生菜单）
- ✅ 📷 截图 + 📁 上传按钮布局优化（文本标签、hover/pressed 动效、不再被裁切）
- ✅ 视窗截图 Houdini 20 API 适配（saveImage/grabFrameBuffer 移除→flipbook 修复）
- ✅ QImage.save() PySide6 兼容（BytesIO/QBuffer 失败→tempfile 中转）
- ✅ PySide6 枚举兼容修复（Qt.Clipboard 等不存在→整数 mode 值 0/1/2）
- ✅ SnapshotEngine 场景快照 Diff（snapshot / diff / 三阶段节点级 restore）
- ✅ Undo/Redo 栈（每轮一个事务，撤销=整轮回滚重建，手动修改自动清空栈）
- ✅ 节点视图跳转（点击变更树路径 → hou.node.setCurrent + frame viewport）
- ✅ 节点创建 namespace 自动解析（裸名如 copytopoints → namespaceOrder → copytopoints::2.0）
- ✅ Shelf tool 预设自动应用（创建后匹配 tool 脚本，执行 pressButton/set）
- ✅ 变更树参数紧凑显示（≤2 参数全显，3+ 折叠摘要）
- ✅ diff 自动过滤 Houdini 内部生成的子节点
