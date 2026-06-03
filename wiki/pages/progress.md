# 🚀 开发进度

> 最后更新：2026-06-03 &nbsp;|&nbsp; 第一阶段：基础架构搭建完成

## 总览看板

<div class="phase-grid">

<div class="phase-card">
  <div class="phase-card-header">
    <span class="phase-card-title">🖥️ PySide6 面板 UI</span>
    <span class="status-tag status-done">完成</span>
  </div>
  <div class="progress-bar-bg"><div class="progress-bar-fill progress-done" style="width:100%"></div></div>
  <div class="phase-card-detail">聊天视图 · 输入栏 · 设置对话框 · 状态栏 · 流式文本渲染 · 工具卡片 · 模型切换 UI</div>
</div>

<div class="phase-card">
  <div class="phase-card-header">
    <span class="phase-card-title">🔌 JSON-RPC 通信</span>
    <span class="status-tag status-done">完成</span>
  </div>
  <div class="progress-bar-bg"><div class="progress-bar-fill progress-done" style="width:100%"></div></div>
  <div class="phase-card-detail">subprocess + stdin/stdout · QThread 非阻塞 · 事件分发 (text_delta/tool_call/agent_start) · 重连 · 模型热切换</div>
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
    <span class="status-tag status-pending">计划中</span>
  </div>
  <div class="progress-bar-bg"><div class="progress-bar-fill progress-pending" style="width:0%"></div></div>
  <div class="phase-card-detail">⬜ Anthropic Claude · ⬜ Qwen · ⬜ 图片输入 (viewport 截图)</div>
</div>

</div>

## 近期关键节点

<div class="timeline">

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-06-03</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第二阶段：UI 重构 — Houdini 原生菜单 + 三栏高级面板</span>
      <span class="status-tag status-done">全部完成</span>
    </div>
    <div class="timeline-summary">参照 EEEAi_Houdini 架构完成全面 UI 重构：① 目录迁移到 python3.11libs/ 标准 Houdini 包路径 ② MainMenuCommon.xml 注册 Edini 主菜单栏入口 ③ Houdini packages JSON 注册（install.py 改写）④ QMainWindow + QSplitter 三栏布局（History | Chat Timeline | Pi+Scene Context）⑤ 暗色主题系统（4 色霓虹预设 + 字体缩放 + 全局样式表）⑥ AgentPanel 时间线（流式文本渲染、Tool Card、Markdown 支持、Enter 发送/Ctrl+Enter 换行）⑦ ChatRuntime Pi 事件适配层（text_delta/tool_call/stats 事件映射）⑧ HistoryPanel 会话列表（新建/切换/右键删除）⑨ ContextPanel 双面板（Pi 状态：连接灯/模型/token/成本/上下文进度条/流式速率 + 场景信息：HIP/选中节点/节点统计/QTimer 3s 刷新）⑩ session_store JSON 本地持久化 ⑪ SettingsDialog 双标签（Provider 配置 + 主题/字体选择）⑫ Alt+Shift+E 全局热键 ⑬ 窗口单例管理（windows.py）。全部 19 个文件语法验证通过。</div>
    <div class="timeline-tags">
      <span>MainMenuCommon.xml</span><span>QSplitter三栏</span><span>暗色主题</span><span>Pi事件映射</span><span>时间线</span><span>会话管理</span><span>热键</span><span>19文件</span>
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
| P0 | 实机验证 | 在 Houdini 21 中完整测试：安装→配置→对话→工具调用 |
| P1 | 多模型支持 | 增加 Anthropic Claude / Qwen，模型列表 UI |
| P1 | Viewport 截图 | 实现图片输入通道，Agent 可"看到" viewport |
| P1 | 工具执行反馈 | 节点创建后在 viewport 高亮或选中 |
| P2 | 单元测试 | 对 node_utils、config、tool_executor 写测试 |
| P2 | 对话历史 | 加载/保存对话会话 |
| P2 | Houdini 日志集成 | 工具执行结果输出到 Houdini Console |
| P3 | Python 面板 | 支持嵌入 Houdini Pane Tab |
| P3 | 节点推荐 | 基于上下文推荐下一步操作 |

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
- ✅ 工具调用可视化卡片
- ✅ API Key / 模型设置 (⚙ 设置对话框)
- ✅ Dark mode 自动跟随系统
- ✅ 多行输入 (Ctrl+Enter 发送)
