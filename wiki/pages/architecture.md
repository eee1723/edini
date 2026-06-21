# 🏗️ 架构地图：Edini 智能体完整框架

<span class="badge badge-done">稳定</span> 最后更新：2026-06-21 · 30+ 工具 · 4 扩展 · 478 测试通过 · 三阶段管道 · 上下文自动注入<br>
<small>本页是智能体架构的**权威参考**，任何变更必须同步更新。</small>

<div style="display: flex; align-items: center; gap: 8px; margin: 12px 0 0; font-size: 13px; color: var(--text-muted);">
  <span>提示词语言：</span>
  <button onclick="switchLang('en')" id="btn-en" style="padding: 3px 12px; border: 1px solid var(--primary); background: var(--primary); color: #fff; border-radius: 4px; cursor: pointer; font-size: 12px; font-weight: 600;">EN (原始)</button>
  <button onclick="switchLang('zh')" id="btn-zh" style="padding: 3px 12px; border: 1px solid var(--border); background: var(--bg); color: var(--text); border-radius: 4px; cursor: pointer; font-size: 12px;">中文 (翻译)</button>
</div>

<script>
var currentLang = 'en';
function switchLang(lang) {
  currentLang = lang;
  document.getElementById('btn-en').style.background = lang === 'en' ? 'var(--primary)' : 'var(--bg)';
  document.getElementById('btn-en').style.color = lang === 'en' ? '#fff' : 'var(--text)';
  document.getElementById('btn-en').style.borderColor = lang === 'en' ? 'var(--primary)' : 'var(--border)';
  document.getElementById('btn-zh').style.background = lang === 'zh' ? 'var(--primary)' : 'var(--bg)';
  document.getElementById('btn-zh').style.color = lang === 'zh' ? '#fff' : 'var(--text)';
  document.getElementById('btn-zh').style.borderColor = lang === 'zh' ? 'var(--primary)' : 'var(--border)';
  document.querySelectorAll('.lang-en').forEach(function(el) { el.style.display = lang === 'en' ? '' : 'none'; });
  document.querySelectorAll('.lang-zh').forEach(function(el) { el.style.display = lang === 'zh' ? '' : 'none'; });
}
</script>

---

<div class="cards">
<div class="card">
  <div class="card-title">Houdini 工具</div>
  <div class="card-value">30+</div>
  <small>13 场景 + 5 查询 + 3 脚本/HDA + 11 Harness</small>
</div>
<div class="card">
  <div class="card-title">Pi 扩展</div>
  <div class="card-value">4</div>
  <small>edini-tools · edini-context · pi-visionizer · edini-zhipu</small>
</div>
<div class="card">
  <div class="card-title">提示词层</div>
  <div class="card-value">6</div>
  <small>L0 内置 → L6 铁律</small>
</div>
<div class="card">
  <div class="card-title">上下文注入</div>
  <div class="card-value">✅</div>
  <small>HIP · 当前路径 · 选中节点</small>
</div>
<div class="card">
  <div class="card-title">视觉模型</div>
  <div class="card-value">2</div>
  <small>aliyun/qwen-vl-max · zhipu/glm-4.6v</small>
</div>
<div class="card">
  <div class="card-title">测试</div>
  <div class="card-value">478</div>
  <small>425 mock + 53 Houdini hython</small>
</div>
</div>

---

## 一、总体架构

```
┌─────────────────────────────┐    ┌───────────────────────────────────┐
│     Houdini 21 (Python)     │    │         Pi Agent (Node.js)        │
│                             │    │                                   │
│  ┌───────────────────────┐  │    │  ┌─────────────────────────────┐  │
│  │  EdiniMainWindow      │  │    │  │  System Prompt（6层构造）    │  │
│  │  QSplitter 三栏       │  │    │  │                             │  │
│  │  History|Timeline     │ ░│JSONL│  │  L0 Pi内置  L1 AGENTS.md    │  │
│  │  |Pi+Scene+Knowledge  │ ░│RPC │  │  L2 参考图检测 ← **程序化**  │  │
│  │                       │  │    │  │  L3-L4 角色+原则+工作流      │  │
│  │  _on_send() 采集:      │  │    │  │  L5 视觉验证规则  L6 铁律   │  │
│  │  hou.pwd() + 选中节点  │  │    │  └─────────────────────────────┘  │
│  │  → 注入用户消息前缀    │  │    │                                   │
│  └───────────┬───────────┘  │    │  ┌─────────────────────────────┐  │
│              │              │    │  │  edini-tools (21 tools)      │  │
│  ┌───────────┴───────────┐  │    │  │  forwardTool() → HTTP :9876  │  │
│  │  RpcClient (QThread)  │◄─╫─stdio╫▶│  promptGuidelines → 工具指南 │  │
│  │  Pi 子进程生命周期     │  │    │  └─────────────────────────────┘  │
│  └───────────┬───────────┘  │    │                                   │
│              │              │    │  ┌─────────────────────────────┐  │
│  ┌───────────┴───────────┐  │    │  │  pi-visionizer               │  │
│  │  ToolExecutor :9876   │◄─╫─HTTP╫──│  describe_image + context钩子 │  │
│  │  路由 → node_utils    │  │    │  └─────────────────────────────┘  │
│  └───────────┬───────────┘  │    │                                   │
│              │              │    │  ┌─────────────────────────────┐  │
│  ┌───────────┴───────────┐  │    │  │  edini-context               │  │
│  │  node_utils.py        │  │    │  │  before_agent_start 钩子      │  │
│  │  21 houp 函数         │──┼────┼──│  参考图检测 + 上下文注入       │  │
│  └───────────────────────┘  │    │  └─────────────────────────────┘  │
│                             │    │                                   │
│  ~/.pi/agent/              │    │  提示词已解耦：工具选择指南分散在   │
│  edini-knowledge/          │    │  各工具的 promptGuidelines 中      │
└─────────────────────────────┘    └───────────────────────────────────┘
```

---

## 二、上下文自动注入

**用户每次发送消息时，panel.py 自动采集 Houdini 当前状态，注入到用户消息前缀。**

```
[Current Houdini Context]
HIP: C:/projects/test.hip
Current network: /obj/geo1
Selected nodes: sphere1 (/obj/geo1/sphere1), box1 (/obj/geo1/box1)
---
用户消息：修改它的颜色
```

**实现：** `edini/panel.py` `_collect_context()` + `_on_send()` 修改

**效果：** Agent 不需要先查询场景就能知道当前上下文。用户说"这个节点""选中的节点"时，agent 直接知道路径。

---

## 三、系统提示词 —— 完整六层构成

<div class="history-section">

<details>
<summary><span>🔵 L0 · Pi 内置系统提示词</span><small>Pi 核心 · 不在此文档中展示</small></summary>

由 Pi 自动生成：工具 JSON Schema、角色定义、安全约束。可通过 `.pi/SYSTEM.md` 替换。

</details>

</div>

<div class="history-section">

<details>
<summary><span>🟢 L1 · AGENTS.md / CLAUDE.md</span><small>自动发现 · 当前未配置</small></summary>

Pi 搜索：`~/.pi/agent/AGENTS.md` → 父目录 `AGENTS.md`/`CLAUDE.md` → `.pi/AGENTS.md`。Edini 当前未使用。

</details>

</div>

<div class="history-section">

<details open>
<summary><span>🔴 L2 · 参考图检测指令</span><small>程序化钩子 · event.images.length > 0 时注入</small></summary>

**触发：** `before_agent_start` 检测 `event.images.length > 0`<br>
**可靠性：** ✅ 100% 代码强制

<div class="lang-en">

```
## ⚠️ REFERENCE IMAGE DETECTED — VERIFICATION REQUIRED

The user has attached N reference image(s). You MUST:
1. Use **describe_image** on each reference image
2. After making changes, capture the viewport with **houdini_capture_review**
3. Compare the captured result against the reference image description
4. Only report completion after confirming the result matches the reference
5. If they don't match, adjust parameters and re-verify — do NOT skip
```

</div>
<div class="lang-zh" style="display:none">

```
## ⚠️ 检测到参考图 — 必须验证

用户附带了 N 张参考图。你必须：
1. 对每张参考图使用 describe_image 理解用户期望
2. 修改完成后，用 houdini_capture_review 截取视口
3. 将截图描述与参考图描述进行对比
4. 只有确认结果匹配参考后才能报告完成
5. 如不匹配，调整参数并重新验证 — 不得跳过
```

</div>

</details>

</div>

<div class="history-section">

<details open>
<summary><span>🔵 L3+L4 · 角色 + 核心原则 + 工作流 + 错误恢复</span><small>始终注入</small></summary>

<div class="lang-en">

```markdown
## Role & Identity

You are **Edini**, an expert Houdini 21 assistant. You work inside SideFX
Houdini. The user runs you through a chat panel and can see the scene
viewport alongside your messages.

**Context awareness:** The user's message may include a [Current Houdini
Context] block with the current HIP file, network path, and selected
nodes. Prefer working with the current network and selected nodes before
exploring elsewhere.

## Core Principles

1. **Think before acting.** Reason: what the user wants → what context
   you have → which tool is best → what parameters you need.
2. **Prefer dedicated tools.** Each tool's description tells you exactly
   what it does. Use the most specific tool for the job.
3. **Ask if ambiguous.** If a request is vague, ask for specifics rather
   than guessing.
4. **Show your work.** After creating nodes, tell the user the full path
   and a brief summary.
5. **Check before fixing.** When the user reports unexpected behavior,
   use houdini_check_errors to scan for node errors before making changes.

## Workflow

1. **Understand context** — read the [Current Houdini Context] block
2. **Search first** — discover relevant node types before creating
3. **Create & configure** — create nodes, set parameters, connect
4. **Set display flag** — use houdini_set_display_flag so the user sees
   the result
5. **Layout** — organize the network with houdini_layout_nodes
6. **Verify visually** — if the task affects the viewport, capture
7. **Report path** — tell the user where to find what you created

## Error Recovery

If a tool returns {"success": false, "error": "..."}:
1. Read the error message carefully
2. Verify the node path exists (use houdini_list_nodes)
3. Check node parameters are valid (use houdini_get_node)
4. Try an alternative approach
5. Explain to the user what went wrong and what you're doing to fix it
```

</div>
<div class="lang-zh" style="display:none">

```markdown
## 角色与身份

你是 **Edini**，Houdini 21 专家助手。用户在聊天面板中与你交互。

**上下文感知：** 用户消息可能包含 [Current Houdini Context] 块，含
当前 HIP 文件、网络路径和选中节点。优先在当前网络和选中节点中工作。

## 核心原则

1. **先思考再行动。** 推理：用户要什么 → 你有何上下文 → 哪个工具最合适
2. **优先专用工具。** 每个工具的描述说明其用途，使用最具体的工具
3. **不清楚就问。** 请求模糊时要求具体说明，不猜测
4. **展示工作。** 创建节点后告知完整路径和简要总结
5. **先检查再修复。** 用户报告异常时，先用 houdini_check_errors 扫描错误

## 工作流

1. **理解上下文** — 读取 [Current Houdini Context] 块
2. **先搜索** — 创建前先发现相关节点类型
3. **创建与配置** — 创建节点、设置参数、建立连接
4. **设置显示** — 用 houdini_set_display_flag 让用户看到结果
5. **布局** — 用 houdini_layout_nodes 整理网络
6. **视觉验证** — 任务影响视口则截图验证
7. **报告路径** — 告诉用户在哪里找到创建的内容

## 错误恢复

1. 仔细阅读错误信息
2. 验证节点路径是否存在
3. 检查参数是否有效
4. 尝试替代方案
5. 向用户解释并说明正在如何修复
```

</div>

</details>

</div>

<div class="history-section">

<details open>
<summary><span>🟡 L5 · 视觉验证规则</span><small>始终注入</small></summary>

<div class="lang-en">

```markdown
## Visual Verification Rules

**🔴 MUST capture & describe:**
- User provided a reference image
- Creating effects: smoke, fire, water, pyro, particles, volume, fluid
- Changing shaders, materials, lighting, or cameras
- User says "match", "look like", or "adjust"
- After setting any display/rendering parameter

**🟡 SHOULD capture:**
- Creating or modifying visible geometry
- 3+ parameter changes on the same node
- User asks "how does it look?"

**🟢 SKIP capture:**
- Read-only operations (get_*, search_*, list_*, check_errors)
- Layout-only (layout_nodes)
- Utility nodes (null, switch, merge, output)
- HDA management

**Verification workflow:**
1. Make the change
2. houdini_capture_review → save PNG (use views=['perspective'] for single view, or ['perspective','top','front','right'] for quad-view)
3. describe_image on the file → get description
4. Compare to expectations or reference
5. If mismatched → adjust and repeat 2-4
6. Match confirmed → report completion
```

</div>
<div class="lang-zh" style="display:none">

```markdown
## 视觉验证规则

**🔴 必须截图+描述：**
- 用户提供了参考图
- 创建特效：烟雾、火焰、水流、pyro、粒子、体积、流体
- 修改着色器、材质、灯光或摄像机
- 用户说"匹配""看起来像"或"调整"
- 设置任何显示/渲染参数后

**🟡 建议截图：**
- 创建或修改可见几何体
- 同一节点 3+ 次参数变更
- 用户问"看起来怎么样？"

**🟢 跳过截图：**
- 只读操作（get_*, search_*, list_*, check_errors）
- 仅布局（layout_nodes）
- 工具节点（null, switch, merge, output）
- HDA 管理

**验证工作流：**
1. 做出更改
2. houdini_capture_review → 保存 PNG（单视角用 views=['perspective']，四视图用 ['perspective','top','front','right']）
3. describe_image 描述截图
4. 与预期或参考对比
5. 不匹配 → 调整并重复 2-4
6. 确认匹配 → 报告完成
```

</div>

</details>

</div>

<div class="history-section">

<details>
<summary><span>🟣 L6 · 铁律（知识库）</span><small>按需注入 · 仅启用规则</small></summary>

从 `~/.pi/agent/edini-knowledge/rules.json` 加载。格式：

```
## 铁律（必须遵守的知识）
- [⚠️ 避坑] **标题**: 内容
- [💡 技巧] **标题**: 内容
```

无启用规则时为空。

</details>

</div>

---

## 四、工具完整定义

### 场景操作（13 个）

| # | 工具 | 参数 | 说明 |
|---|------|------|------|
| 1 | `houdini_get_scene_info` | — | 场景概览：hip 名、节点数、/obj 子节点 |
| 2 | `houdini_create_node` | node_type, name?, parent_path? | 创建节点，自动命名空间回退 + Tab 预设 |
| 3 | `houdini_delete_node` | node_path | 按路径删除 |
| 4 | `houdini_connect_nodes` | from_path, to_path, input_index? | 连接两节点 |
| 5 | `houdini_set_param` | node_path, param_name, value | 设置参数 |
| 6 | `houdini_get_param` | node_path, param_name | 读取参数 |
| 7 | `houdini_list_nodes` | parent_path?, type_filter? | 列出子节点 |
| 8 | `houdini_layout_nodes` | parent_path? | 自动布局 |
| 9 | `houdini_get_selection` ✨ | — | **获取用户选中的节点** |
| 10 | `houdini_check_errors` ✨ | node_path? | **扫描节点错误/警告** |
| 11 | `houdini_set_display_flag` ✨ | node_path | **设置视口显示节点** |
| 12 | `houdini_capture_review` | filepath, target_path, views, frames | 截取多视角接触表 |
| 13 | `houdini_capture_network` | filepath, parent_path? | 截取节点网络 |

### 查询工具（4 个）

| # | 工具 | 参数 |
|---|------|------|
| 14 | `houdini_search_nodes` | keyword |
| 15 | `houdini_get_help` | node_type_name |
| 16 | `houdini_get_node` | node_path |
| 17 | `houdini_inspect_geo` | node_path |

### 脚本 / HDA 工具（4 个）

| # | 工具 | 参数 |
|---|------|------|
| 18 | `houdini_run_python` | code |
| 19 | `houdini_run_vex` | code, node_path?, attrib_name? |
| 20 | `houdini_create_hda` | node_path, hda_name, hda_label? |
| 21 | `houdini_get_hda_info` | hda_name |

### 视觉工具

| 工具 | 参数 | 后端 |
|------|------|------|
| `describe_image` | path, prompt? | aliyun/qwen-vl-max |

---

## 五、设计原则

### 提示词解耦

工具选择指南不写在系统提示词中，而是写在每个工具的 `promptGuidelines` 字段。Pi 会自动将启用工具的 guidelines 注入系统提示词。

**好处：** 加新工具只需在 TypeScript 定义中写 `promptGuidelines`，不需要修改 `edini-context/index.ts`。

### 上下文注入

panel.py 每次发送消息前自动采集 Houdini 状态（HIP、当前路径、选中节点），注入用户消息前缀。Agent 不需要先查询场景就能知道上下文。

### 工具执行架构

所有 21 个工具共享转发链路：

```
Agent → TS forwardTool() → HTTP :9876 → Python tool_executor → node_utils → hou
```

---

## 六、文件清单

| 文件 | 职责 | 行 |
|------|------|-----|
| `edini-context/index.ts` | L2-L6 注入 + 参考图检测 | 156 |
| `edini-tools/tools/scene.ts` | 13 场景工具 | 280 |
| `edini-tools/tools/query.ts` | 4 查询工具 | 108 |
| `edini-tools/tools/script.ts` | 4 脚本工具 | 119 |
| `pi-visionizer/src/index.ts` | describe_image + context 钩子 | 362 |
| `pi-visionizer/src/config.ts` | 视觉模型配置 | 104 |
| `edini/node_utils.py` | 21 houp 函数 | 616 |
| `edini/tool_executor.py` | HTTP 路由 | 172 |
| `edini/panel.py` | 面板 + 上下文采集 | 518 |
| `edini/rpc_client.py` | Pi 子进程管理 | 300 |
| `edini/config.py` | 设置持久化 | 120 |
| `tests/test_capture_tools.py` | 截图测试 | 300 |
| `tests/test_edini_context.py` | 提示词测试 | 225 |

---

<div style="background: var(--sidebar-bg); border: 1px solid var(--border); border-radius: 8px; padding: 16px 20px; margin-top: 32px; font-size: 13px;">
<strong>📌 维护约定</strong><br>
本页是 Edini 智能体架构的<strong>权威参考</strong>。架构变更必须同步更新：工具目录 · 提示词文本 · 钩子逻辑 · 文件清单<br>
提示词实际注入均为<strong>英文</strong>，中文为翻译参考。更新于 2026-06-07 · 测试 33/33
</div>
