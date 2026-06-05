# 🚀 开发进度

> 最后更新：2026-06-05 &nbsp;|&nbsp; 第十阶段：变更树 QTreeWidget 面板 + SnapshotEngine Diff · Undo/Redo 栈 · Shelf Tool 预设 · 节点创建 namespace 解析

## 总览看板

<div class="phase-grid">

<div class="phase-card">
  <div class="phase-card-header">
    <span class="phase-card-title">🖥️ PySide6 面板 UI</span>
    <span class="status-tag status-done">完成</span>
  </div>
  <div class="progress-bar-bg"><div class="progress-bar-fill progress-done" style="width:100%"></div></div>
  <div class="phase-card-detail">三栏布局 · Thinking 面板（可折叠、QTextEdit 纯文本流、实时展开/收拢）· Tool Call 面板（fixedHeight 折叠 20px↔200px、暗色协调、自动滚底）· 时间线 QScrollArea + Widget（_UserBubble / _AiBubble / _Separator / _ErrorBanner）· 智能滚动（rangeChanged valueChanged + _pinned_to_bottom 标志位）· 代码 Copy（QLabel linkActivated + base64）· Markdown 渲染 · 知识提取确认区（铁律/知识卡片 + ✓✕ + 全部接受/放弃 + 类型切换）· 气泡 Expanding 填满窗口 · 完成后自动折叠面板</div>
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
  <div class="phase-card-detail">16 tools (TypeBox schema) · edini-context 注入铁律（rules.json）+ Houdini 上下文 · forwardTool HTTP 转发</div>
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
  <div class="phase-card-detail">✅ 两层架构（铁律 rules.json ≤20条 + 知识库 entries.json）· ✅ 对话结束 AI 反思 → 用户确认（面板内 ✓✕）· ✅ 铁律自动注入 system prompt · ✅ 管理弹窗（双标签增删改搜索）· ✅ Settings Knowledge 标签页 · ✅ 类型可切换（铁律↔知识）· ✅ 只提取会重复犯的错</div>
</div>

</div>

## 近期关键节点

<div class="timeline">

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
| P1 | ~~工具执行反馈~~ | ✅ 变更树 + Undo/Redo + 节点跳转 viewport |
| P2 | 知识库检索工具 | 为 Agent 添加 search_knowledge 工具调用 |
| P2 | 单元测试 | 对 node_utils、config、tool_executor 写测试 |
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
- ✅ 会话管理 (pi 接管：Popen cwd 按 HIP 归档 · JSONL 本地读取 · new/switch/set_name RPC)
- ✅ Viewport 截图 (vision 模型分析画面)
- ✅ API Key / Provider / Model 设置 (下拉选择 + 历史记忆)
- ✅ 4 色主题实时预览 + 字体缩放
- ✅ 执行/中止按钮一体化切换
- ✅ 智能滚动（rangeChanged + valueChanged + _pinned_to_bottom 标志位，零抖动）
- ✅ 状态栏 (连接状态 / 模型 / 节点数)
- ✅ 多行输入 (Ctrl+Enter 换行，Enter 发送)
- ✅ 会话浏览模式（历史回看 + 回到当前）
- ✅ 对话轮次计时器（Pi Status 卡片实时显示 Round 时间）
- ✅ Pi Status 工具信息（Tools: 16 loaded, port 9876）
- ✅ 知识沉淀两层架构：铁律 (≤20, 上下文注入) + 知识库 (细节, 可检索)
- ✅ AI 反思 → 用户确认面板（✓✕ + 全部接受/放弃 + 类型切换）
- ✅ Settings Knowledge 标签页（开关 + 统计 + 管理按钮）
- ✅ 变更树 QTreeWidget 面板（按轮次分组：创建/修改/删除三级树，可折叠，对话结束自动展开）
- ✅ SnapshotEngine 场景快照 Diff（snapshot / diff / 三阶段节点级 restore）
- ✅ Undo/Redo 栈（每轮一个事务，撤销=整轮回滚重建，手动修改自动清空栈）
- ✅ 节点视图跳转（点击变更树路径 → hou.node.setCurrent + frame viewport）
- ✅ 节点创建 namespace 自动解析（裸名如 copytopoints → namespaceOrder → copytopoints::2.0）
- ✅ Shelf tool 预设自动应用（创建后匹配 tool 脚本，执行 pressButton/set）
- ✅ 变更树参数紧凑显示（≤2 参数全显，3+ 折叠摘要）
- ✅ diff 自动过滤 Houdini 内部生成的子节点
