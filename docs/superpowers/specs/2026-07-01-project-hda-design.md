# Project HDA — 程序化建模项目的"项目化身"容器

**Date:** 2026-07-01
**Area:** 新模块 — `python3.11libs/edini/project/` + 新 HDA 类型 + 新面板
**Status:** Design approved by user (brainstormed 2026-07-01), ready for implementation plan

## 0. TL;DR

Edini 当前的 rooted `build_assembly` 是**一次性生成器**：agent 产声明 → builder
构建 → 完成。本设计把它升级为一个**长期协作伙伴**：每个程序化建模项目 =
一个 Project HDA，它内部承载几何 subnet、知识图谱（持久化为富化声明 JSON）、
PySide 面板、日志。用户可以随意手工编辑几何网络，agent 通过**确定性结构 diff**
检测偏离、请人裁决，并在闲置时提出优化建议。

**一句话总结：** 一个 Project HDA = 一个自包含的、可手工编辑的、agent 持续守护的
程序化建模项目。声明是意图来源，子网络是几何事实来源，两者分离；drift 检测靠
物理结构镜像而非语义推断。

---

## 1. 问题陈述

当前 Edini 的可靠性建立在一条干净的不变量上：**agent 是唯一作者**。它产声明 →
builder 构建。因为只有 LLM 在写，所以永远不存在"两边不一致"。

用户想要的体验要求**有意打破这条不变量**：让用户也能直接在 Houdini 里改几何网络，
让 agent 持续理解、优化、迭代这个项目。这从"一次性生成器"升级到"长期协作伙伴"。

易用性、可迭代性因此提升，但代价是引入了一个根本性难题：**当两边都能改时，
如何保持 agent 维护的知识图谱与真实几何网络同步？**

### 第一性原理

三个用户目标各自需要的工程条件：

| 目标 | 真正需要的工程条件 |
|------|------------------|
| 易用 | 低门槛表达意图 + 低门槛纠偏；agent 吃掉枯燥活 |
| 符合正确的程序化逻辑 | 模型必须始终是活的、测量驱动的，不能 bake 坐标 |
| 适合长期迭代 | 资产始终可编辑、可理解、可改进 |

三个目标里有两个，全部系于"同步"这一件事。所以整个设计的难度塌缩成同一个问题：
**如何在用户自由编辑的前提下，保持知识图谱与真实网络同步。**

**本设计的核心策略：把"语义同步"降级为"结构 diff"。** 通过让 subnet 的物理嵌套
结构镜像组件分解，使得"哪些节点属于哪个组件""组件是否还存在""参数依赖关系"
全部变成确定性查询，无需 LLM 语义推断。这是整个架构能成立的支柱。

---

## 2. 范围

### In scope（本 spec 覆盖）

- Project HDA 的定义、结构、创建方式。
- 富化声明 JSON 的通用骨架（不预设建模专用结构，留扩展位）。
- 嵌入 HDA 的 PySide 面板（Houdini Python Pane，多实例，绑定 HDA 节点）。
- 回合循环状态机（原子动作 → 验证 → 日志 → 更新）。
- drift 检测的概念规则（哪些算 drift，怎么报告，人怎么裁决）。
- 计划与拆解的交互模型（强制计划、多级拆解、用户控序）。
- 与现有 Edini 模块的关系（复用 vs 新建 vs 不动）。

### Out of scope（本 spec 明确不覆盖，留给后续 spec）

- **具体建模能力**（rooted build_assembly、测量链、leaf chains）——这些是"按需
  接入"的能力，不在本设计内。声明 JSON 的 `components`/`plan` 字段刻意保持通用，
  等真正开始建模任务时再约束。
- drift 检测的具体实现算法、reconcile 的具体 merge 策略。
- 优化建议的生成逻辑（四向优化的每一向如何具体产出建议）。
- 跨项目经验库（日志导出后的检索、复用机制）。
- 图谱关系可视化（part-of / depends-on 关系图的渲染）。

### 实现起点（已与用户确认）

从**最小闭环**开始动手：先把"空 Project HDA + PySide 面板 + 对话"跑通——创建
HDA → 出面板 → 能跟 LLM 对话。验证技术路线后再填计划树、drift、优化。本 spec
据此把重心放在最小闭环所需的组件上，其余部分只勾勒方向。

---

## 3. 核心设计决策（11 条，均已与用户确认）

| # | 决定 | 选择 | 后果 |
|---|------|------|------|
| 1 | 真实来源（source of truth） | **混合**：网络管几何事实，图谱管意图/计划 | 用户编辑是一等公民；需双向同步 |
| 2 | 知识图谱范围 | **C：结构 + 语义 + 参数化意图** | 能理解+优化+重建；同步最难 |
| 3 | 同步策略 | **检测偏离 + 人确定** | 不解逆程序化建模难题；drift 报告给人裁决 |
| 4 | "优化"含义 | 四向并行：参数化结构整洁 / 图谱准确 / 性能可维护 / **持续加组件细节** + 日志输出供跨项目复用 | agent 是长期驻留守护者 |
| 5 | 面板形态 | **PySide 全自绘嵌入 HDA** | 对话+统计+图谱可视化同处一个面板 |
| 6 | 半成品一致性 | **始终可 cook** | 每步增量原子、可验证；失败回滚 |
| 7 | 图谱表示 | **富化声明即图谱**（路线 1） | 一个意图来源，无双重同步；直接长在现有声明上 |
| 8 | 计划 | **强制、详细、可 review、用户控序** | agent 先和用户对齐结构再动手 |
| 9 | 组件管理 | **subnet 物理镜像（浅，组件组一层）** | 语义同步降级为结构 diff，确定性 |
| 10 | 参数管理 | **HDA 原生参数接口**（不单独建参数 subnet） | live ch() 引用有真实 parm 落点 |
| 11 | 多项目 | **每个 HDA 独立面板 + 独立 Pi session** | 一个 HDA = 一个隔离的项目世界 |

### 决策依据摘要

- **#9 是分水岭**：组件组 subnet（chassis/ wheels/ lights/）让"wheel_fr 是否还存在"
  从"LLM 推断哪些节点是轮子"变成"subnet 在不在"——确定性。这把 #3（同步）从
  开放研究难题降级为工程化的 diff + 人工裁决。
- **#7 + #9 协同**：富化声明只存意图与语义（不存几何细节），结构信息物理化在
  subnet 里；drift 检测全部确定性：设计参数 = diff HDA 接口 vs JSON；组件 =
  diff subnet 子节点 vs JSON 清单；依赖 = 解析节点 ch() 表达式 vs JSON depends_on。
  **零语义推断。**
- **#10 的理由**：live `ch("../<name>")` 引用需要真实存在的 parm；HDA 顶层参数接口
  是 Houdini 暴露资产参数的标准方式，PySide 里的"参数"不能被 ch() 引用。
- **#6 的理由**：用户始终看到一个"能用"的模型，从不看到崩坏状态；失败 atom 回滚，
  声明 JSON 不变。

---

## 4. Project HDA 的结构

### 4.1 整体架构

```
┌─────────────────── Project HDA（"一个项目"）────────────────────┐
│                                                                  │
│  参数接口（HDA 顶层，原生）                                       │
│    • project meta: name, created_at, version                     │
│    • design params（随推进逐步添加，初始为空）                     │
│    • 「__edini_state」隐藏 string parm ← 声明 JSON 持久化于此      │
│                                                                  │
│  ┌─────── 富化声明 JSON（隐藏 string parm）──────┐               │
│  │  = 知识图谱（路线 1）                           │               │
│  │  • 结构: components（镜像 subnet 浅结构）       │               │
│  │  • 语义: is-a / part-of / named-anchor（新增） │               │
│  │  • 参数化意图: depends_on（ch() 测量链，将来）  │               │
│  │  • 计划/日志: plan + log                        │               │
│  └───────────────┬──────────────────────────────┘               │
│                  │ builder 消费（将来接入建模能力）                 │
│  ┌───────────────▼───────────────┐  ← 几何事实来源               │
│  │   几何 subnet（实际几何）       │  ← 用户可直接编辑            │
│  │     ├─ chassis/  （组件组 subnet）│                            │
│  │     ├─ wheels/   （组件组 subnet）│                            │
│  │     └─ OUT                      │                            │
│  └───────────────┬───────────────┘                              │
│                  │ drift 检测器（每轮/触发）                       │
│  └───────────────▼───────────────┐                              │
│  │   PySide 面板（Python Pane tab）│                             │
│  │   • 对话  • 计划树  • 状态/图谱 │                              │
│  └─────────────────────────────────┘                             │
└──────────────────────────────────────────────────────────────────┘
         ↑                                        ↑
    LLM（声明意图）                          用户（编辑/多模态输入）
```

### 4.2 核心不变量（继承自 Edini 现有设计，必须保持）

1. **声明是意图的来源；子网络是几何事实的来源。两者分离。**
2. **几何始终通过 builder 从声明派生**（将来接入时），所以永远 live、永远测量驱动、
   绝不 bake 坐标。
3. **用户可以改子网络**（这是几何事实），**但不能直接改声明**（那是意图，通过对话改）。

### 4.3 创建时状态

- 在 `/obj` 下实例化 Project HDA（自定义 HDA 类型，定义在 `otls/`）。
- 几何 subnet **初始为空**，只有一个 `OUT`。组件组 subnet（chassis/ wheels/...）
  **不在创建时生成**，而是随计划推进逐个产出。
- 声明 JSON 初始化为"空项目"状态（见 §5）。
- 设计参数接口**初始为空**，随推进逐步添加。
- 挂上 PySide 面板（见 §6）。

> 关键：创建时几何是空的，只有容器和意图层。几何随计划推进逐个 atom 长出来。
> 这符合"不用一次做到完美"。

### 4.4 与现有 Edini 的关系（刻意保持距离）

- Project HDA 是**新模块**，放在 `python3.11libs/edini/project/`。
- 它**不导入** `assembly_builder` / `vex_strategies`——这些是将来"按需接入"的建模
  能力，最小闭环用不到。
- 复用的是**基础设施**：`tool_executor.py`（HTTP 路由）、`rpc_client.py`（与 Pi
  通信）、现有 PySide 面板的样式/叶子组件。
- 现有的独立 Edini 全局浮窗**完全保留不动**，Project HDA 面板是新的、嵌入 HDA 的
  面板，两者共存，职责不同（全局助手 vs 项目化身）。

---

## 5. 富化声明 JSON 骨架（知识图谱）

这是路线 1"富化声明即图谱"的骨架，**刻意保持通用、不预设建模结构**。初始全空，
随推进填入。

```json
{
  "version": 1,
  "project": {
    "name": "car",
    "created_at": "2026-07-01T...",
    "goal": null
  },

  "plan": [],
  "design_params": [],
  "components": [],
  "log": [],
  "drift": []
}
```

### 字段定义

| 字段 | 类型 | 说明 |
|------|------|------|
| `version` | int | schema 版本，便于将来迁移 |
| `project.name` | string | 项目名 |
| `project.created_at` | ISO string | 创建时间 |
| `project.goal` | string \| null | 用户说的意图，阶段 1 后填入（如"一辆可调轴距的车"） |
| `plan` | list of step | 多级拆解计划（决定 #8）。step 形态见下 |
| `design_params` | list of param | 镜像 HDA 参数接口。`{name, default, min?, max?, label, group}` |
| `components` | list of component | 组件清单，镜像 subnet 浅结构。`{id, type, subnet_path, depends_on:[param_names]}` |
| `log` | list of entry | 每个回合的原子动作记录（审计 + 经验沉淀）。`{ts, kind, summary, payload, result_ok}` |
| `drift` | list of drift entry | 检测到的偏离 + 裁决结果（阶段 3 才用） |

**plan step 形态：**
```json
{"id": "wheels", "title": "轮子组", "parent": null, "status": "pending",
 "detail": "4 个轮子，前后各两个，mounted-on 底盘四角"}
```
- `status`: `pending` | `in_progress` | `done` | `skipped`
- `parent`: 父 step id（支持多级嵌套），顶层为 null

**component 形态：**
```json
{"id": "wheels", "type": "wheelset", "subnet_path": "./wheels",
 "depends_on": ["wheel_radius"]}
```
- `type` 是自由字符串（将来可能是 `root`/`mount`/`leaf`，但现在不定义），刻意不约束。
- `depends_on` 来自解析组件 subnet 内节点的 `ch()` 表达式。

### 设计原则（贯穿整个 schema）

1. **声明只存"意图与语义"，不存几何细节。** 几何细节在 subnet 里（那是事实）。声明
   是"我们打算做什么、为什么、各部分什么关系"。
2. **可扩展，不预设。** `components[].type` 自由字符串，`detail` 自由结构。等真正接
   建模能力时再约束，不提前焊死。
3. **plan 是一等公民（决定 #8）。** 它是 agent 和用户对齐结构的契约。推进前必须 review。
4. **log 持续写（决定 #4 末条）。** 是将来导出"项目总结"、做跨项目经验沉淀的原料。
5. **语义关系字段保留但暂空。** §4.1 图示提到的 `is-a` / `part-of` /
   `named-anchor` 这类语义边，在最小闭环 schema 里**故意不出现为字段**——因为
   `part-of`（组件归属）已由 subnet 浅镜像物理化（subnet_path 即归属），而
   `mounted-on` / 具名锚点等跨组件语义边是 rooted 建模能力的一部分，与建模一起
   延后接入（见 §2 out-of-scope）。接入时才在 `components[]` 上加这些字段，不提前
   定义空壳。

### 持久化位置

声明 JSON 持久化为 Project HDA 上的一个**隐藏 string parm** `__edini_state`。

理由：
- 随 `.hip` 自动保存，**自包含**，不依赖外部文件。
- 不会和 `.hip` 脱钩（单独 `.json` 文件的最大风险）。
- 可 diff（string parm 的值变化在 .hip 版本里可追踪）。

替代方案（被否决）：单独的 `.edini.json` 配套 .hip——会和 .hip 脱钩，违背自包含原则。

---

## 6. 嵌入 HDA 的 PySide 面板

### 6.1 面板的"家"：Houdini Python Pane tab

面板注册成一个 **Houdini Python Pane 类型**，使它能够：

- 嵌进 Houdini 的 pane 布局（和 Network Editor、Parameter 并排）。
- 多实例（每个 pane tab 一个）。
- **绑定到具体 HDA 节点**——面板顶部有"项目选择器"（下拉列出场景里所有
  Project HDA），选中哪个，面板就化身那个项目。

面板持有当前绑定的 HDA 节点路径。所有读写（声明 JSON、参数、subnet 子节点、
截图）都针对这个节点。切换项目 = 切换绑定 + 切换 Pi session。

> 现有的全局浮窗 `EdiniMainWindow` **保留不动**（它是"Houdini 通用助手"）。
> Project HDA 面板是新的、嵌入 HDA 的面板，技术栈同源但骨架新写。

### 6.2 面板布局（三栏）

沿用现有 `EdiniMainWindow` 三栏 splitter 范式，但内容针对"项目化身"重设：

```
┌──────────────────────────────────────────────────────────────────┐
│  [项目: project_car ▼]   session: car_2026-07-01        ●已连接   │  顶栏
├────────────────┬──────────────────────────────┬──────────────────┤
│  计划树        │     对话 (timeline)           │  项目状态+图谱   │
│  (Plan Tree)   │                              │                  │
│  ☐ 底盘        │   用户: 做一辆车              │  组件: 3         │
│  ☐ 轮子组      │   AI: 好的,拆解如下…          │  参数: 5         │
│   ☐ wheel_fr   │   [工具卡片: build_atom]      │  组件列表:       │
│  ☐ 灯组        │                              │   • chassis ✓    │
│                │                              │   • wheels  …    │
│  [+推进选中]   │   ┌────────────────────────┐ │  drift: 1 ⚠      │
│  [顺序推进 ▶]  │   │ 输入框            [发送] │ │  [查看 drift]    │
│                │   └────────────────────────┘ │                  │
├────────────────┴──────────────────────────────┴──────────────────┤
│  状态栏: cook OK | 节点 12 | 本轮 +2 | [撤销本轮] [优化建议 3]   │
└──────────────────────────────────────────────────────────────────┘
```

**左栏 — 计划树（Plan Tree）** *(新组件)*
- 可视化 `plan` 字段为树状待办（支持多级）。
- 每个 step 一个 checkbox：`pending` / `in_progress` / `done` / `skipped` 四态。
- 选中一项 → 点"推进选中"，agent 就先做这一项（用户控序）。
- "顺序推进 ▶" = agent 按 plan 顺序自动一步步做，每步暂停 review。
- 这是 agent 和用户对齐结构的**契约视图**——review 在这里发生。

**中栏 — 对话（Timeline）** *(复用现有)*
- 直接复用 `_TimelineView` + `_UserBubble`/`_AiBubble`/`_ToolCardWidget` + mistune
  渲染 + 智能滚动（来自 `agent_panel.py`）。
- 消息走 `RpcClient` → Pi，但 session 是**本项目专属**的（每个 HDA 一个 Pi session）。
- viewport 截图、网络截图、vision 描述气泡全复用现有。

**右栏 — 项目状态 + 图谱** *(改造现有 ContextPanel)*
- 上半：**统计卡片**（组件数、参数数、节点数、cook 状态）——复用 `_make_card` 工厂。
- 中：**组件列表**（镜像 subnet 浅结构，点一项跳转到该 subnet）。
- 下：**drift 提示**——发现偏离时亮起，点开看 diff、裁决。
- （将来）图谱可视化：part-of / depends-on 的关系图，点节点联动其他两栏。

**状态栏 — 每轮操作栏** *(改造现有 ChangeTreeWidget)*
- 本轮 diff 摘要 + 逐回合撤销/重做（复用现有 `snapshot_engine` + undo 栈）。
- "优化建议 N"角标——agent 闲置时产出的优化，点开逐条采纳/忽略。

### 6.3 多模态输入（三选一）

每一步用户可用最顺手的方式推进：
- **说话**：在输入框打字。
- **选节点**：在子网络里点一个已有节点，面板感知选中，配合说话。
- **视窗选择**：在 viewport 里框选一块区域/一个面，配合说话。

因为面板、网络、图谱三者同处一个 HDA（决定 #5 的 A 形态），点面板里的"轮子" →
面板高亮 → 网络跳转 → 图谱聚焦，是三种输入能真正合一的物理基础。

---

## 7. 回合循环状态机

这是 §4.6 "始终可 cook" 的落实机制。每个用户推进动作走这个循环：

```
 用户输入（说话/选节点/视窗选择/点计划项）
        │
        ▼
 [1] 解析意图 + 选定目标 plan step
        │
        ▼
 [2] agent 执行一个原子动作（建节点/改参数/加组件 subnet）
        │          └─ 在组件 subnet 内或 sandbox
        ▼
 [3] 验证:模型仍可 cook?  ── 否 → 回滚,报告失败
        │                             是 ↓
        ▼
 [4] 抓 viewport 截图 → 回传 agent + 面板（即时反馈）
        │
        ▼
 [5] 写声明 JSON:plan step → done,log 追加一条,组件清单更新
        │
        ▼
 [6] 面板刷新:计划勾一项,状态栏 +N,图谱多一节点
        │
        ▼
 [7] drift 检测（若用户期间手工改过）→ 提示（决定 #3）
        │
        ▼
      等待下一个输入
```

每一步都让模型**前进一小步且始终不崩**。失败的 atom 会回滚，声明 JSON 不变，
用户看到的模型永远可 cook。

> **"原子动作"的粒度延后定义。** 一个 atom 是"加一组轮子"（粗）还是"加一个节点"
> （细），与具体建模能力绑定（如 rooted 的 leaf-level vs mount-level）。建模能力
> 属 §2 out-of-scope，故 atom 粒度在接入建模能力时再约束。最小闭环里，"原子动作"
> 退化为通用的节点 CRUD（建/连/改参数/加 subnet），粒度由当时的 agent 行为决定。

---

## 8. 用户的一次完整流程（端到端）

**阶段 0 · 开个项目**
用户创建一个 Project HDA（菜单/命令）。空容器：subnet + PySide 面板。声明 JSON
是空的。面板写着"你想做什么?"。

**阶段 1 · 说意图（宏观拆分）**
用户用自然语言说"做一辆车"或给参考图。agent 不急着建模，先做**宏观拆分**：
产出一份多级计划写进 `plan` 字段，面板可视化为待办树。agent 问"这个拆分对吗?
从哪个开始?"。**此时还没有任何几何。** agent 先和用户对齐结构，再动手。

**阶段 2 · 逐步推进（每一步一个回合）**
用户选下一步要做什么，输入三选一（说话/选节点/视窗选择）。agent 执行**一个原子
动作**，走 §7 的回合循环。每个 atom 让模型前进一小步且始终不崩。用户随时可接手
手工编辑子网络。

**阶段 3 · 用户手工编辑 → agent 检测偏离**
用户改了子网络。下一轮 agent 触发 drift 检测：把声明 JSON 描述的"预期结构"和
子网络"实际结构"做 diff，发现不一致就标记 drift，面板提示"你把 wheel_fr 删了
——(a) 接受事实，从计划去掉?(b) 让我重建?"。用户拍板，agent 更新声明。绝不自动
猜意图。

**阶段 4 · 持续优化（后台，非阻塞）**
agent 闲置或被召唤时，扫描声明 + 子网络，提出优化建议（决定 #4 的四向）。建议
挂在面板，用户点采纳才执行。优化永远是建议性的，不擅自改。

**阶段 5 · 沉淀与输出**
项目进行中 HDA 持续写日志。项目结束时用户可让 HDA 导出总结：从需求到成品的
演化过程、用过哪些结构、踩过哪些坑。这份总结进经验库，供将来其他项目参考。

---

## 9. drift 检测的概念规则

（具体实现算法留后续 spec，这里只定义"哪些算 drift、怎么报告、人怎么裁决"。）

### drift 检测全部确定性（零语义推断）

| 检测项 | 方法 | 触发的 drift |
|--------|------|-------------|
| 设计参数 | diff HDA 参数接口 vs JSON `design_params` | 用户在 HDA 接口加/删/改了参数 |
| 组件存在性 | diff subnet 子节点 vs JSON `components` 清单 | 用户删了组件 subnet / 加了新 subnet |
| 组件内部 | 枚举组件 subnet 子节点 diff | 用户在组件 subnet 内加了/删了节点 |
| 参数依赖 | 解析组件节点 ch() 表达式 vs JSON `depends_on` | 用户改了引用、断了测量链 |

### drift 报告与裁决（决定 #3）

发现 drift 时 agent **不自动反推意图**，而是：
1. 标记为 drift，在面板 drift 区亮起。
2. 用自然语言描述偏离（"你把 wheel_fr 组件删了"）。
3. 给出选项请人裁决：
   - (a) **接受事实**：更新 JSON 的事实视图（从 plan/components 去掉对应项）。
   - (b) **恢复意图**：agent 按声明重建被删的部分。
   - (c) **改意图**：用户说明这次编辑的新意图，agent 更新 JSON 的意图视图。

### 重命名 vs 删除的区分

subnet 名字 = 组件 id 变成承重的。用户重命名一个 subnet 会触发 drift（图谱觉得
"旧组件消失、新组件出现"）。reconcile 时需把重命名和真删除区分开（靠位置/内容
相似度启发式 + 人确认），但走的是"人确认"流程，不崩。

---

## 10. 与现有 Edini 模块的关系

### 复用（import 叶子组件，不动原文件）

| 现有模块 | 复用方式 |
|---------|---------|
| `ui/agent_panel.py`: `_TimelineView`, `_UserBubble`, `_AiBubble`, `_ToolCardWidget`, mistune `_DarkRenderer` | 直接 import，中栏对话 |
| `ui/theme.py`: `build_stylesheet`, `apply_theme`, `accent_color`, `fs` | 直接 import，统一样式 |
| `rpc_client.py`: `RpcClient`, `_RpcWorker` JSONL 协议 | 直接 import，每个 HDA 面板一个实例 + 专属 session |
| `snapshot_engine`（change_tree_widget 用的）+ undo 栈 | 直接 import，状态栏逐回合撤销/重做 |
| `media_manager.capture_viewport()` 三级回退截图 | 直接 import，即时视觉反馈 |
| `screenshots` 文件名方案 | 直接 import |

### 新建

| 新文件 | 职责 |
|--------|------|
| `python3.11libs/edini/project/__init__.py` | Project HDA 包入口 |
| `python3.11libs/edini/project/hda_type.py` | Project HDA 类型定义、创建命令 |
| `python3.11libs/edini/project/state.py` | 声明 JSON 读写（隐藏 parm ↔ dict） |
| `python3.11libs/edini/project/plan_store.py` | plan 字段的 CRUD + review 状态机 |
| `python3.11libs/edini/project/drift.py` | drift 检测（结构 diff）+ 报告（后续 spec 详化） |
| `python3.11libs/edini/project/round.py` | 回合循环（§7 状态机的实现） |
| `python3.11libs/edini/project/panel/project_pane.py` | 嵌入 HDA 的 PySide 面板骨架（三栏） |
| `python3.11libs/edini/project/panel/plan_tree.py` | 左栏计划树组件 |
| `python3.11libs/edini/project/panel/state_panel.py` | 右栏状态/图谱组件 |
| `python3.11libs/edini/project/panel/project_selector.py` | 顶栏项目选择器 |
| `otls/edini_project.hda` | Project HDA 类型（含 `__edini_state` 隐藏 parm） |

### 不动（刻意保持距离）

- `assembly_builder.py` / `vex_strategies.py` / `measure.py` —— 将来按需接入的
  建模能力，最小闭环不碰。
- 现有全局浮窗 `EdiniMainWindow` 及其调用链 —— 完全保留，零回归风险。
- 现有 Pi extensions（edini-tools / edini-context / pi-visionizer）—— 不改，
  Project HDA 复用同一套 tool 转发机制。

---

## 11. 线程不变量（Iron Rule）

继承自现有 Edini：所有 `hou.*` 调用必须在主线程；Pi IPC 跑在 QThread，跨线程靠
Qt queued signal。Project HDA 面板同样遵守。

---

## 12. 风险与对策

| 风险 | 对策 |
|------|------|
| 跨 subnet 的 `ch()` 路径变长，组件重命名/移动打断引用 | 设计参数统一放 HDA 顶层（稳定路径）；组件内局部参数留在自己 subnet（短引用） |
| subnet 名字 = 组件 id 承重，重命名触发假 drift | drift 区分重命名 vs 删除（启发式 + 人确认） |
| 每个面板一个 RpcClient + Pi session，多项目时资源占用 | 监控；必要时共享一个 Pi 进程靠 session 隔离（后续优化） |
| 隐藏 string parm 存大 JSON 有尺寸/性能上限 | 监控；超阈值时考虑外部 cache 文件 + parm 存路径（但默认仍 parm，保自包含） |
| 新建面板骨架与现有浮窗的重复维护 | 只复用叶子组件；骨架差异够大，共享反而牵制（已权衡） |

---

## 13. 最小闭环（实现起点）的定义

已与用户确认：从**最小闭环**开始动手。最小闭环 = "空 Project HDA + PySide 面板
+ 对话"能跑通：

1. 用一条命令创建 Project HDA（空 subnet + 空 `__edini_state` + design params 空）。
2. 面板注册为 Houdini Python Pane，能打开、能选中该 HDA、能显示空三栏。
3. 中栏对话能用：打字 → RpcClient → Pi → 回流 → timeline 渲染。session 是本项目
   专属。
4. 声明 JSON 能读写（隐藏 parm ↔ dict），面板关闭重开后对话/状态不丢。

最小闭环**不**包含：计划树交互、drift 检测、优化建议、任何建模能力。这些在最小
闭环验证技术路线后，按 §8 的阶段逐步填入。

实现计划（writing-plans）将以此最小闭环为第一里程碑。
