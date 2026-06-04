# 🚀 开发进度

> 最后更新：2026-06-04 &nbsp;|&nbsp; 第七阶段：知识沉淀系统 — 自动提取 · 上下文注入 · Thinking 独立面板 · 部署配置

## 总览看板

<div class="phase-grid">

<div class="phase-card">
  <div class="phase-card-header">
    <span class="phase-card-title">🖥️ PySide6 面板 UI</span>
    <span class="status-tag status-done">完成</span>
  </div>
  <div class="progress-bar-bg"><div class="progress-bar-fill progress-done" style="width:100%"></div></div>
  <div class="phase-card-detail">三栏布局 · Thinking 独立面板（可折叠、QTextEdit 纯文本自然分段、实时流光标）· Tool Call 面板（fixedHeight 折叠 20px↔200px、暗色协调、自动滚底）· 时间线纯对话 bubble · 智能防抖滚动（actionTriggered + 比例定位、无闪烁）· 代码 Copy（anchorClicked + base64）· Markdown 渲染 · 流式文本</div>
</div>

<div class="phase-card">
  <div class="phase-card-header">
    <span class="phase-card-title">🔌 JSON-RPC 通信</span>
    <span class="status-tag status-done">完成</span>
  </div>
  <div class="progress-bar-bg"><div class="progress-bar-fill progress-done" style="width:100%"></div></div>
  <div class="phase-card-detail">subprocess + stdin/stdout · QThread 非阻塞 · 事件分发 (text_delta/thinking_delta/tool_call/tool_result) · 重连 · 模型热切换</div>
</div>

<div class="phase-card">
  <div class="phase-card-header">
    <span class="phase-card-title">⚙️ 工具执行器</span>
    <span class="status-tag status-done">完成</span>
  </div>
  <div class="progress-bar-bg"><div class="progress-bar-fill progress-done" style="width:100%"></div></div>
  <div class="phase-card-detail">HTTP Server (127.0.0.1:9876) · 16 tool handlers · /health 端点 · JSON 序列化 · 异常处理</div>
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
  <div class="phase-card-detail">16 tools (TypeBox schema) · 系统提示注入 · forwardTool HTTP 转发 · session_start 通知</div>
</div>

<div class="phase-card">
  <div class="phase-card-header">
    <span class="phase-card-title">📦 安装部署</span>
    <span class="status-tag status-done">完成</span>
  </div>
  <div class="progress-bar-bg"><div class="progress-bar-fill progress-done" style="width:100%"></div></div>
  <div class="phase-card-detail">install.py (Houdini 包注册) · setup_pi.bat · settings.json · Pi 路径自动检测 · env var 覆盖</div>
</div>

<div class="phase-card">
  <div class="phase-card-header">
    <span class="phase-card-title">🧪 测试</span>
    <span class="status-tag status-pending">计划中</span>
  </div>
  <div class="progress-bar-bg"><div class="progress-bar-fill progress-pending" style="width:0%"></div></div>
  <div class="phase-card-detail">⬜ 单元测试 · ⬜ 集成测试 · ⬜ 端到端测试</div>
</div>

<div class="phase-card">
  <div class="phase-card-header">
    <span class="phase-card-title">🌐 多模型 & 多模态</span>
    <span class="status-tag status-done">完成</span>
  </div>
  <div class="progress-bar-bg"><div class="progress-bar-fill progress-done" style="width:100%"></div></div>
  <div class="phase-card-detail">✅ DeepSeek V3/R1 · ✅ Anthropic Claude · ✅ Viewport 截图（vision 模型）</div>
</div>

<div class="phase-card">
  <div class="phase-card-header">
    <span class="phase-card-title">🧠 知识沉淀系统</span>
    <span class="status-tag status-done">完成</span>
  </div>
  <div class="progress-bar-bg"><div class="progress-bar-fill progress-done" style="width:100%"></div></div>
  <div class="phase-card-detail">✅ 对话结束自动提取避坑/技巧/工作流/模型局限 · ✅ JSON 存储 (~/.pi/agent/edini-knowledge.json) · ✅ 新会话上下文注入 · ✅ 管理弹窗（筛选/删除/清空） · ✅ 设置开关</div>
</div>

</div>

## 近期关键节点

<div class="timeline">

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-06-04</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第七阶段：知识沉淀系统 + Thinking 独立面板 + Windows 部署</span>
      <span class="status-tag status-done">完成</span>
    </div>
    <div class="timeline-summary">实现知识沉淀闭环：① 新建 knowledge_store.py 全局知识 JSON 存储（~/.pi/agent/edini-knowledge.json），支持 4 分类（避坑/技巧/工作流/模型局限）、去重、LRU 100 条上限 ② 对话结束后自动发送反思 prompt，Agent 返回 JSON 自动解析存储（balanced bracket 状态机 + 双分隔符定位）③ edini-context 扩展读取 JSON 注入系统提示（before_agent_start 钩子）④ 新建 knowledge_dialog.py 管理弹窗（分类筛选/删除/清空）⑤ Settings 新增 knowledge_enabled 开关 ⑥ Context Panel 新增 Knowledge 卡片。Thinking 真正独立：新建 _ThinkingPanelWidget（QTextEdit 纯文本，_apply_expanded_state 管理高度，流式自动展开/结束自动收拢），从时间线 HTML 中完全剥离。部署完善：install.py 自动安装包 + MainMenuCommon.xml hconfig 注册 · Pi models.json 自动创建 · 隐藏 Windows 控制台窗口（CREATE_NO_WINDOW）· 进程终止加固。通知分流：extension_ui_request info → notification_received 信号 → Pi Status 卡片 8s 自动消失。新增对话轮次计时器（QElapsedTimer + 每秒刷新 Context Panel）。修复：History Panel 标题裁切（word wrap + 压缩时间标签）、Pi 终端多开（subprocess 窗口隐藏 + kill 兜底）。</div>
    <div class="timeline-tags">
      <span>知识沉淀</span><span>Thinking独立面板</span><span>QTextEdit</span><span>上下文注入</span><span>部署配置</span><span>通知分流</span><span>Windows修复</span><span>计时器</span><span>8文件</span>
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
    <div class="timeline-summary">实现会话浏览模式并修复三个关键 Bug：① HistoryPanel 新增 set_browsing_mode() / highlight_session() / back_to_current_requested 信号，浏览模式下按钮从"+ 新对话"变为"← 回到当前" ② MainWindow 新增 _active_session_path / _browsing_session_path 状态字段，_on_session_selected 进入浏览模式保存活跃会话，_on_back_to_current 恢复，_on_session_deleted 处理回退 ③ 修复 _cwd_to_dirname 未替换 Windows 盘符冒号 `:` 导致目录名不匹配（E:-edini vs E--edini）④ 修复 _parse_session_file 只认旧 "header" type 不兼容 Pi v3 "session" type（+ 字段名变更 createdAt→timestamp、content 数组化）⑤ 修复 _pi_sessions_root 优先用 HOME 而 Houdini 将其重写为 Documents 子目录，导致在 \Documents\.pi\ 找不到真正的 \Users\EEE\.pi\ 目录（改为 USERPROFILE 优先）。</div>
    <div class="timeline-tags">
      <span>浏览模式</span><span>回到当前</span><span>Windows路径修复</span><span>Pi v3兼容</span><span>HOME路径修复</span><span>2文件</span>
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
    <div class="timeline-summary">彻底重构 Session 管理架构：① 删除 edini 自建的 session_store.py，pi 成为唯一真理源 ② pi 进程改用 Popen(cwd=HIP) 启动（去掉 --no-session），session JSONL 按 HIP 目录归档在 ~/.pi/agent/sessions/ ③ 新建 pi_sessions.py 模块，直接读 pi JSONL 文件获取会话列表和消息 ④ HistoryPanel 改用 pi_sessions.list_pi_sessions()，发射 pi session 路径而非 edini session ID ⑤ RpcClient 新增 send_new_session / send_switch_session / send_set_session_name / send_get_messages 方法及 session_switched / messages_received 信号 ⑥ main_window 全部 session handler 重写：新建 → new_session RPC，切换 → 本地读 JSONL 即时渲染 + switch_session RPC，发送消息不再写 edini 存储 ⑦ ContextPanel 新增 reset_stats()，session 切换时归零显示 ⑧ 修复窗口关闭后重新打开显示 disconnected 的 bug（closeEvent 清空 _main_window 全局引用）⑨ 修复 ensure_ascii=False 导致 Windows pipe 写入 Errno 22 ⑩ 修复 _bootstrap 过早 send 命令（改为 status==connected 时触发）。</div>
    <div class="timeline-tags">
      <span>pi 接管 Session</span><span>删除 session_store</span><span>pi_sessions</span><span>Popen cwd</span><span>RPC 新命令</span><span>窗口单例修复</span><span>5 文件</span>
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
    <div class="timeline-summary">重构 Thinking 展示架构：① Thinking 从时间线 HTML 中完全移除，改为独立可折叠面板（QTextEdit 只读，自然段落分段，实时流 ▊ 光标，自动滚底）② Tool Call 面板移除 QSplitter，改用 fixedHeight 折叠（20px↔200px），暗色协调背景 ③ 智能滚动全面重写：actionTriggered 替代 valueChanged 防反馈、同步比例定位替代 QTimer 异步恢复（消除闪烁）、blockSignals 防信号环路 ④ 代码块 Copy 按钮从无效 JS onclick 改为 _TimelineView anchorClicked + base64 ⑤ Thinking 实时分段：add_thinking_step 检测 \n\n 即时 flush 已完成段落 ⑥ Thinking 面板和 Tool 面板均自动滚底显示最新。修复：折叠不可用、滚动抖动、内容锁定顶部、QTextBrowser 渲染残留、Copy 按钮无效。</div>
    <div class="timeline-tags">
      <span>Thinking 独立面板</span><span>纯文本流</span><span>防抖滚动</span><span>Copy 修复</span><span>无 Splitter</span><span>实时分段</span><span>1 文件</span>
    </div>
  </div>
</div>

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-06-04</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第三阶段：UI 精细化 — Pi CLI 风格 · Session 系统 · 实时反馈</span>
      <span class="status-tag status-done">完成</span>
    </div>
    <div class="timeline-summary">全面优化对话面板交互体验：① Thinking 流式渲染（单块实时增长 + 展开态光标，交错于文本之间，分段由 Pi 事件边界决定）② 可折叠 Tool Call 面板（QWidget 卡片、实时结果更新 ✅/❌、折叠时面板缩至 24px）③ 执行/中止按钮一体化切换 ④ Session 系统（会话持久化 JSON、自动命名、时间线切换回看、上下文重建、60% 压缩摘要）⑤ 卡片式 Context Panel（Pi Status + Scene 分组）⑥ Settings 对话框（Provider 下拉 + Model 历史记忆 + 主题/字体实时预览）⑦ 代码块 Copy 按钮 ⑧ 智能滚动（手动上滚不自动跳底）⑨ Viewport 截图（vision 模型）⑩ 状态栏信息（连接状态/模型/Nodes/Token/Cost）⑪ 统一字体 10-13pt + 紧凑间距 ⑫ thinking_delta / tool_result RPC 事件链路。修复：session 消息从未存储、tool panel 展开态残留、thinking R1 逐词碎裂。</div>
    <div class="timeline-tags">
      <span>Pi CLI 风格</span><span>流式Thinking</span><span>Tool Call 面板</span><span>Session 管理</span><span>Viewport 截图</span><span>Copy 按钮</span><span>智能滚动</span><span>10 文件</span>
    </div>
  </div>
</div>

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-06-03</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第二阶段：UI 重构 — Houdini 原生菜单 + 三栏高级面板 ✅ 实机运行</span>
      <span class="status-tag status-done">完成</span>
    </div>
    <div class="timeline-summary">全面 UI 重构完成并在 Houdini 实机验证通过：① python3.11libs 标准目录 + MainMenuCommon.xml 主菜单注册 ② QMainWindow + QSplitter 三栏（History | Timeline | Pi+Scene）③ 暗色主题系统（4 色预设、统一 16px 字号、8px 网格间距）④ AgentPanel 单气泡流式渲染（Tool Card / Markdown / 错误横幅）⑤ ChatRuntime Pi 事件层 ⑥ HistoryPanel + session_store 会话持久化 ⑦ ContextPanel 双面板 ⑧ SettingsDialog 双标签 ⑨ QKeySequence 热键 ⑩ 窗口单例管理。修复：流式渲染多气泡 bug、热键参数透传、import 缺失。</div>
    <div class="timeline-tags">
      <span>MainMenuCommon.xml</span><span>QSplitter三栏</span><span>暗色主题16px</span><span>单气泡流式</span><span>实机验证</span><span>19文件</span>
    </div>
  </div>
</div>

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-06-03</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第一阶段：基础架构搭建完成</span>
      <span class="status-tag status-done">16 tools 就绪</span>
    </div>
    <div class="timeline-summary">完成 Edini 完整底层架构：PySide6 聊天面板 UI（流式文本、工具卡片、设置对话框）、JSON-RPC 通信层（QThread + subprocess stdin/stdout 非阻塞管理）、HTTP 工具执行器（127.0.0.1:9876，16 个 Houdini 操作 handler）、node_utils 纯 Python houp API 封装、16 个 Pi 扩展工具（TypeBox 参数校验 + HTTP 转发）、edini-context 系统提示注入、安装脚本（install.py + setup_pi.bat）、配置持久化（settings.json + env var 覆盖）。DeepSeek V3/R1 两种模型可选。</div>
    <div class="timeline-tags">
      <span>PySide6</span><span>JSON-RPC</span><span>HTTP</span><span>16 tools</span><span>DeepSeek</span><span>安装部署</span>
    </div>
  </div>
</div>

</div>

## 下一步计划

| 优先级 | 任务 | 说明 |
|------|------|------|
| P1 | 工具执行反馈 | 节点创建后在 viewport 高亮或选中 |
| P2 | 单元测试 | 对 node_utils、config、tool_executor 写测试 |
| P2 | Houdini 日志集成 | 工具执行结果输出到 Houdini Console |
| P3 | Python 面板 | 支持嵌入 Houdini Pane Tab |
| P3 | 多模型优化 | Qwen 等更多 provider 快速切换 |

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
- ✅ 代码块一键 Copy（_TimelineView anchorClicked + base64，无需 JS）
- ✅ 会话管理 (pi 接管：Popen cwd 按 HIP 归档 · JSONL 本地读取 · new/switch/set_name RPC · 删除 edini session_store)
- ✅ Viewport 截图 (vision 模型分析画面)
- ✅ API Key / Provider / Model 设置 (下拉选择 + 历史记忆)
- ✅ 4 色主题实时预览 + 字体缩放
- ✅ 执行/中止按钮一体化切换
- ✅ 智能防抖滚动（actionTriggered 用户检测、同步比例定位、无闪烁无抖动）
- ✅ 状态栏 (连接状态 / 模型 / 节点数)
- ✅ 多行输入 (Ctrl+Enter 换行，Enter 发送)
