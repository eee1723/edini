# 💬 统一对话窗口架构

<span class="badge badge-done">完成</span> 最后更新：2026-07-05 · 主 Agent 窗口 + HDA 窗口共享组件库 · 121 测试通过

---

## 概述

两个对话窗口（主 Edini Agent + Project HDA 建模窗口）从"独立项目"重构为"共享骨架 + 配置差异化"。核心设计原则：**交互逻辑通用化，UI 外观差异化**。

<div class="cards">
<div class="card">
  <div class="card-title">共享组件</div>
  <div class="card-value">13</div>
  <small>components/ 纯叶子组件库</small>
</div>
<div class="card">
  <div class="card-title">装配层</div>
  <div class="card-value">5</div>
  <small>chat/ ChatRuntime+Shell+Driver+Scope</small>
</div>
<div class="card">
  <div class="card-title">测试</div>
  <div class="card-value">121</div>
  <small>含 2 个架构守卫测试</small>
</div>
<div class="card">
  <div class="card-title">agent_panel 瘦身</div>
  <div class="card-value">1951→958</div>
  <small>减少 51%</small>
</div>
</div>

## 三层架构

```
┌─────────────────────────────────────────────────────────┐
│  components/ (13个纯叶子组件)  ← 无 RPC/Chat 依赖          │
│  TimelineView / AiBubble / ThinkingPanel / ToolPanel /   │
│  InputBar / NodeVersionList / ParamSnapshotPanel / ...   │
└──────────────▲──────────────────────────────────────────┘
               │ Qt signals
┌──────────────┴──────────────────────────────────────────┐
│  chat/ (5个装配层模块)                                    │
│  ChatRuntime → BaseChatDriver → ChatWindowShell          │
│  ScopeConfig (唯一差异入口)                               │
└──────────────▲──────────────────────────────────────────┘
               │ 各自实例化,注入 scope
   ┌───────────┴───────────────┐
   │                           │
┌──┴──────────┐  ┌─────────────┴────────┐
│ 主 Agent 窗口 │  │ HDA 建模窗口          │
│ 青色(跟随全局)│  │ 橙色 #f59e0b(固定)   │
│ 左=全局会话  │  │ 左=节点版本列表       │
│ 共享 RPC    │  │ 每节点独占 RPC        │
└─────────────┘  └──────────────────────┘
```

### 关键不变量（架构守卫测试强制）

- `components/` 永远不 import `rpc_client` / `chat` / `main_window`
- `ChatRuntime` 永远不 import `components`
- 组件内无 `if scope_id ==` 分支（差异只通过 ScopeConfig 字段表达）

## HDA 窗口差异化

| 维度 | 主 Agent 窗口 | HDA 建模窗口 |
|------|:------------:|:------------:|
| 强调色 | 跟随全局主题(青) | 固定橙 #f59e0b |
| 左侧 | 全部历史会话 | 该节点版本列表(core_path::vN) |
| 附件栏 | ✓ 截图/上传 | ✗ 聚焦建模 |
| 参数快照 | ✗ | ✓ HDA 参数 + diff |
| Eval 按钮 | ✓ | ✗ |
| Workspace Lock | ✗ | ✓ 锁定在 core_path 子树内 |

### Workspace Lock（3 层 prompt 注入）

HDA 窗口的 agent 被约束在绑定的 HDA 子树内操作：

1. **环境变量**：`EDINI_SCOPE_ID=project_hda` + `EDINI_CORE_PATH=/obj/...`
2. **System prompt**：edini-context hook 注入 "WORKSPACE LOCK" 指令
3. **消息前缀**：每条消息带 `[Current Houdini Context] LOCKED to core_path`

## 版本管理

HDA 窗口左侧的版本列表（NodeVersionList）：
- 会话名 `core_path::vN`（Pi 侧无感知，只看到 session 名字符串）
- 版本清单从 Pi sessions 目录扫描（`~/.pi/agent/sessions/<cwd-hash>/*.jsonl`）
- 新建/切换/删除版本 = 切换 Pi session
- session 文件的 `sessionName` 字段含 `::vN` 后缀，scanner 用它过滤

## 关键修复历程

### 第一轮：基础架构 + HDA 升级
- 组件库抽取（10 模块）
- ChatWindowShell + BaseChatDriver + ScopeConfig
- HDA 窗口从简陋 QDialog → 完整三面板（橙色差异化）
- AiBubble 合并 StreamBubble O(1) 流式优化

### 第二轮：功能 bug 修复
- busy 状态不复位 → 连 `busy_changed` 信号
- abort 按钮无效 → 连 `abort_requested` → `rpc.send_abort()`
- Pi Status 显示 disconnected → 转发 status 到 ContextPanel
- 版本不持久化 → session 名带 `::vN` 后缀
- model 名/token 不显示 → 连 `model_changed` + stats 轮询
- thinking 一词一词分段 → driver 层 buffer + flush

### 第三轮：工具链 + brainstorm 修复
- get_node/get_param Ramp 序列化崩溃 → `_json_safe` 加 Ramp 处理
- set_params_batch 丢向量/表达式 → 复用 set_param 三分派
- `_looks_like_expr` 误判 VEX ch() → 排除多行/含分号
- project_create 复用不检查 `__edini_state` → 自动补装
- ports 逐字段报错 → 一次列出所有错误 + schema_hint
- brainstorm 双重注册 → 移除全局 superpowers 包，只用项目副本
- brainstorm 不适配建模 → 加快速通道豁免（1-2 问题→委托 project-modeling）

### 第四轮：design_params 断层修复
- `project_build_scaffold` 自动创建 design_params 的 spare parms
- SKILL.md 指导用绝对路径 `ch('/obj/.../core/parm')`
- vision 模型配置修正（ali/qwen-vl-max → zai-coding-cn/glm-5v-turbo）

## 相关文件

| 文件 | 职责 |
|------|------|
| `python3.11libs/edini/ui/components/` | 13 个纯叶子组件 |
| `python3.11libs/edini/ui/chat/` | 装配层(ChatRuntime/Shell/Driver/Scope) |
| `python3.11libs/edini/ui/status/` | 数据驱动 status 子系统 |
| `python3.11libs/edini/project/panel/chat_dialog.py` | HDA 对话窗口 |
| `python3.11libs/edini/project/panel/chat_driver.py` | HDA driver + scope |
| `pi-extensions/edini-context/index.ts` | system prompt + workspace lock |
| `skills/superpowers/` | 14 个 superpowers skill（项目副本） |

## 设计文档

- [统一对话窗口架构设计](../docs/edini/specs/2026-07-05-unified-chat-window-architecture-design.md)
- [实现计划](../docs/edini/specs/2026-07-05-unified-chat-window-architecture-plan.md)
