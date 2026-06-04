# 🚀 开发进度

> 最后更新：2026-06-04 &nbsp;|&nbsp; 第四阶段：UI 稳定化 — Thinking 独立面板 · 纯文本流 · 滚动防抖 · Copy 修复

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

</div>

## 近期关键节点

<div class="timeline">

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
- ✅ 会话管理 (新建/切换/回看、自动命名、上下文重建)
- ✅ Viewport 截图 (vision 模型分析画面)
- ✅ API Key / Provider / Model 设置 (下拉选择 + 历史记忆)
- ✅ 4 色主题实时预览 + 字体缩放
- ✅ 执行/中止按钮一体化切换
- ✅ 智能防抖滚动（actionTriggered 用户检测、同步比例定位、无闪烁无抖动）
- ✅ 状态栏 (连接状态 / 模型 / 节点数)
- ✅ 多行输入 (Ctrl+Enter 换行，Enter 发送)
