# 🤖 程序化建模 Agent 详解

> **一句话**：Edini 的程序化建模 agent 不是一个"会写 Houdini 代码的 LLM"，而是一条**受四层守卫约束、按确定阶段推进、最终用硬门证明完成**的建模流水线。本文逐层拆解它的阶段工作、提示词、工具设计与全部规则守卫。
> **最后更新**：2026-07-10 ｜ **代码主线**：`master`（含 component-structure-analyzer cut-1）｜ **配套**：[SKILL.md](../../skills/project-modeling/SKILL.md)、[组件地基验证](project-component-foundation.html)、[会话日志诊断](session-logs-analysis.html)

---

## 0. 先搞清楚：它是什么、不是什么

| | 是 | 不是 |
|---|---|---|
| 建模对象 | **多部件**组装体（桌子、车、键盘、机器、建筑） | 单体生成器 / 一个曲面（那走 `houdini_run_python_sandbox`） |
| 载体 | 一个 **Project HDA**（`edini::project` SOP），自包含、可长期手编 | 在 `/obj` 下散落一堆节点 |
| Agent 角色 | 按**确定阶段**建网、测量、接锚点、验证、过门 | 用 `houdini_run_python` 在 live scene 里试错 |
| 完成判据 | `project_finalize` 返回 `finalized: true` | "看起来对了" / `inspect_health` 的 `overall_ok` |

> ⚠️ **别和 [Procedural Harness](procedural-harness.html) 混淆**。那是**旧的** sandbox + 声明式 Recipe Builder 路径，已备份到 `_disabled_backup/`。本文讲的是**现在的主线**——Project HDA 组件流水线。旧 harness 的"构造轴""健康门"思想被新主线继承，但工具和流程完全不同。

---

## 1. 全景图：一条流水线 + 三层防护

```
用户:"做一个桌子"
   │
   ▼
┌──────────────────────────── Agent 生命周期 ────────────────────────────┐
│                                                                        │
│  ① create  →  ② plan  →  ③ scaffold+声明  →  ④ 建模+测量  →  ⑤ 验证  →  ⑥ finalize │
│  project_     project_    project_build_      project_emit_    verify_     project_   │
│  create       plan        scaffold           component/add_    parametric  finalize   │
│                                              anchors                                       │
│                                                                        │
│   ←────────── 闭环学习（横跨全程）：edini_search_drafts / project_capture_archetype ──→  │
└────────────────────────────────────────────────────────────────────────┘
        ▲                    ▲                      ▲                ▲
        │                    │                      │                │
   ┌────┴────┐         ┌─────┴─────┐         ┌──────┴──────┐    ┌────┴─────┐
   │ 提示词层 │         │ 平台守卫层 │         │  验证门层   │    │ 知识闭环 │
   │ (prompt) │         │ (guards)  │         │  (verify)   │    │ (learn)  │
   └─────────┘         └───────────┘         └─────────────┘    └──────────┘
```

**三层防护（defense in depth）**——同一规则在多层叠加，任何一层失守都有下一层兜底：

1. **提示词层**：系统 prompt + SKILL.md + 工具描述，用统一词汇（`measure`/`anchor`/`scaffold`）告诉 agent 该怎么做。
2. **平台守卫层**：`guards.py` 在工具执行**前** fail-fast 拒绝违规操作（硬编码坐标、改内部节点），`structure.py` 的 lint 在 scaffold **前**拒绝畸形声明。
3. **验证门层**：`project_finalize` 在声明完成**时**自己跑验证、拒绝放行。Gate 4（结构）连 skip 都挡不住。

> **设计哲学**：提示词负责"教会"，平台负责"拦住"。agent 真正违规时，提示词会失效——所以每条提示词规则背后都有一个**平台层拒绝**作为硬执行。两者用**同一套词汇**写错误信息，让 agent 一轮就能学会正道。

---

## 2. 阶段详解：每一步做什么、用什么工具、被什么守卫约束

每个阶段有 **✅ 完成标准（completion criterion）**——不达标不准进下一阶段。这是对抗"过早声明完成"的核心机制。

### 阶段 ① 创建项目 — `project_create`

| | 内容 |
|---|---|
| **做什么** | 建一个 `edini::project` SOP HDA（包在 geo 外壳里），返回 `core_path` |
| **工具** | `project_create(name, goal)` |
| **守卫** | 无（这一步只建空容器）|
| **✅ 完成标准** | 拿到 `core_path` 并记住。若意外建了新 HDA，说明有 stale selection——deselect 重试 |

**工作区感知**：如果当前网络编辑器里已选中一个 Project HDA core，会**复用**它（只返回路径）；只有"没选中任何相关的"时才新建。这是 Project HDA 对话窗口模式的基础（见 §5 的 Workspace Lock）。

### 阶段 ② 捕获意图 — `project_plan`（意图闸）

| | 内容 |
|---|---|
| **做什么** | 在**建任何东西之前**，把"目标 + 完成标准"写进项目声明 |
| **工具** | `project_plan(core_path, goal, success_criteria)` |
| **守卫** | 平台校验：`goal` 非空、`success_criteria` 是非空字符串列表——空了就**拒绝** |
| **✅ 完成标准** | `success_criteria` 存进了声明（后续 `project_finalize` 可交叉对照）|

**为什么必须有这一步**——它是"上游错误不向下游滚雪球"的结构性对策。历史上 agent 把 `inspect_health` 的 `overall_ok` 当成"完成"，但 `overall_ok` 只证明"现在没坏"，**不证明**"参数化 + 达到意图"。`project_plan` 强制 agent 先说清"done 长什么样"，才能开工。

### 阶段 ③ 脚手架 + 声明 — `project_build_scaffold`

这是整条流水线的**确定性骨架**。builder 永远不建几何——只建空的、可幂等的、可检测漂移的结构。几何归 agent 自由发挥。

| | 内容 |
|---|---|
| **做什么** | 一次性声明：**组件**（`components`）+ **设计参数**（`design_params`）+ **结构意图**（`structure`），builder 据此建出脚手架 |
| **工具** | `project_build_scaffold(core_path, components, design_params)` |
| **守卫** | ⭐ 三道 shift-left 校验全在建网**前**（见下） |
| **✅ 完成标准** | 每个组件有 subnet、每个 `ports.in` 有接好的 `in_<from>_<anchor>` 输入 null、无校验错误。重跑安全（幂等）|

#### builder 到底建了什么（四遍扫描）

```
① 每个组件 → _ensure_component_subnet：建一个 subnet（以 id 命名）
② 每个组件 → _ensure_scaffold_nodes：内部 4 节点 + 烘焙链
③ 跨组件   → _ensure_input_scaffold：每个 ports.in → 外部连线 + in_<from>_<anchor> null
                                + filter_<from>_<anchor>（按 @name Blast 留点）
                                + __edini_anchor_clean_*（删所有 prim，保纯点云）
④ core 层  → _ensure_core_output：所有组件的 output_0 → merge 到 OUT null + display flag
            → _ensure_design_params：每个 design_param → core 的真实 spare parm
```

**组件内部烘焙链**（scaffold 自动建，agent 不该改）：
```
[agent 几何…] → out_geometry(null) → tag_component(component_id) → __edini_axis_bake → output_0
                  ↑ agent 连这里          ↑ agent 可编辑             ↑ 内部 __前缀，锁死
                                           只设 component_id         烘焙 edini_world_axis
```

#### 脚手架前置的三道守卫（shift-left）

全部在**任何节点被创建之前**跑完，一次性报全部错：

| 守卫 | 位置 | 触发 | 结果 |
|---|---|---|---|
| **结构声明 lint** | `structure.lint_structure_decl` | 组件带 `structure` 但畸形：bad `kind` / radial·planar 缺 `expected_axis` / repeated 缺 `repeats[]` / 实例化 `count<2` | 返回 `lint_errors[]`，拒绝建网 |
| **端口契约校验** | `ports.validate_component_ports` | `ports.out[0]` 不是 geometry / 锚点 `name` 不符正则 / `ports.in` 缺 `from`·`port`·`anchor` | 聚合所有错一次性返回 |
| **跨组件路由检查** | `ports.validate_route_contract` | `ports.in.anchor` 在上游没声明 / 上游组件不存在 | 软警告（`route_warnings`），不挡建网；运行时 Blast 是硬执行 |

> **结构 lint 是 opt-in**：没声明 `structure` 的组件（历史默认）放行；只有**带了但畸形**才拒。但 Gate 4 仍无条件执行 F1/F2/F4，只有 F3（轴向）需要声明——这是"legacy fixture 不必全改"和"仍要挡结构缺陷"的折中。

#### 声明三件套

**`design_params`**（②b 顶向下参数源）——项目的可调旋钮，自动建成 core 的真实 spare parm：
```python
design_params=[{"name":"length","default":1.2,"min":0.4,"max":3.0}, ...]
# → core 上出现 length/width/height/top_thick/leg_thick 等 spare parm
```
子网里的几何节点用**绝对 `ch()`** 引用它们：`ch('/obj/.../project_core/length')`。

**`structure`**（②c 结构意图）——声明组件的结构种类，驱动 Gate 4 的 F1–F4 检查：
```jsonc
{"id":"front_wheel","structure":{
   "kind":"radial",            // radial | planar | repeated | solid
   "expected_axis":"Z",        // radial/planar 必填
   "repeats":[{"part":"spoke","count":28,"method":"copytopoints"}]  // repeated 必填
}}
```
kind 指南：轮/齿轮 → `radial`；桌面/板 → `planar`；辐条/腿/蜡烛 → `repeated`；单个 box 体 → `solid`。

**`ports`**（跨组件契约）——这是**多组件协作的核心**：
```python
{"id":"legs","ports":{
   "out":[{"index":0,"kind":"geometry"}],
   "in":[{"from":"tabletop","port":1,"anchor":"leg_mount_fr"}, ...]}}  # 消费桌面的锚点
```

### 阶段 ④ 组件内建模 + 测量锚点

这是 agent 最自由的阶段——在脚手架建好的空 subnet 里建几何。但"自由"被两条铁律约束：**测量而非硬编码**、**声明每个跨组件依赖**。

#### ④a 建几何——优先用 archetype，别从零手搓

| 手段 | 何时用 | 为什么 |
|---|---|---|
| **`project_emit_component(archetype=…)`** | 组件匹配某个原型时（面板/阵列/管图/柱） | 原型自管节点、自动接线、用**相对 ch()**（可跨项目迁移），消灭 step-3 的高频错（Python SOP 语法/错参数名/断 ch()） |
| 原生 `houdini_create_node`/`connect_nodes`/`set_param` | **没有原型匹配**时 | 必须抄 `COMPONENT_TEMPLATE.md` 的 Python SOP 骨架——它编码了反复犯的 5 个错 |
| `project_snapshot_component` / `restore` | 冒险改一个组件前 | 快照→迭代→恢复，不用重跑整个项目 |

**内置原型**（archetype）：
- `box_panel` — 参数化盒子（桌面/座/面板）：`size=[x,y,z]`，每个是数字或 design_param 名
- `copy_array` — 把叶子形状盖到消费到的锚点上（腿/辐条/键）
- `tube_graph` — 命名锚点间连管（车架/前叉/车把），PolyWire 加粗，纯 VEX 零 Python SOP 风险
- `extrude_profile` — 参数化管/柱（柱子/把手/圆柱）

#### ④b 测量锚点 — `project_add_anchors` / `project_emit_markers`

**这是整条流水线对抗"参数化失效"的核心**。锚点必须从几何**测量**出来（`bbox_corner`/`bbox_face_center`/`bbox_center`/`grid_on_face`/`by_name`…），这样改参数→bbox 变→锚点重算→下游跟着动。

```python
project_add_anchors(core_path, component_id="tabletop", anchors=[
    {"measure":"bbox_corner","axes":"+X-Y+Z","name":"leg_mount_fr"},  # 桌面前右底角
    ...])
# 改桌面尺寸 → bbox 变 → 锚点重算。LIVE。
```

- **`project_add_anchors`**：测量 → 生成 VEX wrangle，每 cook 从 bbox 派生点，`@name` 打标
- **`project_emit_markers`**：在**真实几何位置**打 `@name` 标记点（不是 bbox 凸包上的近似位置），给下游 `by_name` 锚点精确取用——自行车架的真实钩爪 vs bbox 面中心的区别

**守卫**：`project_anchor_guard`（见 §7）拒绝任何**字面坐标** `addpoint`。计算位置的 `addpoint`（`set(i-base,…)*step`、`@P`、`chf()`）放行——那是正常程序化几何。

#### ④c 下游消费锚点

builder 已经预接好了 `in_<from>_<anchor>`，agent 在它**下游**建模即可：
```python
houdini_create_node("tube", parent="<legs subnet>")
houdini_connect_nodes(tube, ctp, input_index=0)                                    # 模板
houdini_connect_nodes("<legs>/in_tabletop_leg_mount_fr", ctp, input_index=1)       # 目标点
houdini_connect_nodes(ctp, "<legs>/out_geometry")
```

**✅ 阶段 ④ 完成标准**：(a) 每个组件 `out_geometry` 有几何流过；(b) 每个在 ③ 声明的 `ports.out` 锚点都通过 `project_add_anchors` 发射了；(c) `verify_orientation` 通过（无轴向不符）。**任一不满足，模型就没建完——继续。**

### 阶段 ⑤ 验证参数化 — `verify_parametric` / `verify_robust`

> **关键认知**：`inspect_health` 的 `overall_ok` ≠ 完成。它只证明"现在没坏"，不证明"参数化"。这两个工具用**扰动**证明参数真的驱动了几何。

#### `verify_parametric` — LIVE 保证（扰动测试）

```
verify_parametric(node_path="<core>/OUT", core_path="<core>",
                  param="length", new_value=<不同值>, expected_axis="X")
```
**它做的 6 步**（`verify.py:357`）：
1. 读目标节点当前几何（bbox 尺寸 + 点/prim 数 + **点位置哈希**）
2. 把 core 的 design_param 设成 `new_value`
3. force-recook 目标节点
4. 读扰动后几何
5. 断言：几何非空 + 无新 cook 错误 + **（某轴 bbox 变化 ≥5%）或（点位置哈希变了）**
6. **永远还原**原值（`try/finally` 保证——哪怕 cook 出错也得还原，不污染用户场景）

**双探针**（这是修过假阴性的关键）：
- **bbox 探针**：某轴尺寸相对变化 ≥ `min_relative_change`(5%) → 参数驱动了几何
- **点位置哈希**（`_point_position_hash`）：bbox 不变但点移动了（倒角圆滑、贴纸覆盖率这类形状参数）→ 哈希变 → 同样算通过。旧版只有 bbox 探针，把这些形状参数**假阴性**成"死参数"，逼 agent 手改 `__edini_state` 缩小验证集（2026-07-09 立方体会话的根因）

**✅ 完成**：`passed: true`。`passed: false` 说明参数链断了（断 `ch()` / 参数接错节点）——**不能声明完成**。

#### `verify_robust` — 全区间稳定（区间扫描）

```
verify_robust(node_path="<core>/OUT", core_path="<core>", samples="min_default_max")
```
对每个 design_param，在声明的 **min / default / max** 各 recook 一次，断言**每个采样点**都非退化 + 无 cook 错。参数间隔离（扫完一个还原再扫下一个），全程结束 `try/finally` 还原所有参数。

> 两者互补：`verify_parametric` 证明参数**驱动**几何（某点方向变了）；`verify_robust` 证明模型在区间内**挺住**（极端值不坍缩/不报错）。

#### `verify_orientation` — 朝向（ground truth，不靠估计）

读烘焙在 prim 上的 `edini_world_axis`（ground truth），跟声明的 `expected_axis` 比，超 `tolerance_deg`(15°) 则失败。
- **per-check `construction_axis` 覆盖**：临时按假设轴检查，不改烘焙值
- **PCA 回退已移除**：旧版没烘焙轴时用 PCA 估计点云主轴——对径向对称管会取惯性轴（长度轴）而非车轴，90° 误判。现在没烘焙轴直接 fail，指 agent 去 bake 或删掉这个 orientation_assert
- **PCA 交叉校验**（仅警告）：有 ≥4 点时跑 PCA 对照，差异 > 2× 容差则警告"声明轴和实际几何分布不一致"

### 阶段 ⑥ 终结硬门 — `project_finalize`

**这是对抗"过早声明完成"的终极防线。** `verify_parametric`/`verify_robust` 是 agent **可以跳过**的工具（公路车会话就这么干过）；`project_finalize` 是**门**——它自己跑验证，失败就拒绝标记完成。

详见 §8（四道门）。唯一"不验证就过"的口子是 `acknowledge_skip=True` + 非空 `skip_reason`（审计进日志）——但 **Gate 4（结构）连 skip 都挡不住**。

### 横跨全程：闭环学习

```
失败 ──→ project_finalize 自动捕获 FailureRecord ──→ add_failure_drafts ──→ 知识草稿(draft)
                                                                         │
下次遇到类似失败 ←── edini_search_drafts（按类别搜：dead_param/degenerate/cook_error/…）←─┘

成功 ──→ project_capture_archetype（干净组件）──→ archetype 注册表 ──→ 下次 project_emit_component(archetype=…)
```

- **失败被记住**：每次 `project_finalize` 失败自动写成可搜草稿。下次失败前先 `edini_search_drafts`，历史会话可能已解决过（草稿在人工 promote 前不进 `edini_search_knowledge`）
- **成功复利**：组件验证干净且判断可复用→`project_capture_archetype` 存成原型，立即被 `project_emit_component` 复用

---

## 3. 提示词架构：四层叠加，同一套词汇

提示词不是一个大文件，而是**四层**在不同时机注入，用同一套词汇（`measure`/`anchor`/`scaffold`/`finalize`）互相强化。

### 第 1 层：系统 prompt（`edini-context/index.ts`，每轮注入）

`before_agent_start` 事件把下面这些拼进 system prompt：

| 块 | 内容 | 关键点 |
|---|---|---|
| **Role & Identity** | "你是 Edini，Houdini 21 专家助手" | 工作在 live scene，改动实时可见 |
| **Core Principles** | 5 条：先想后做 / 优先专用工具 / 含糊就问 / 展示工作 / 先查错再修 | 优先专用工具 > `houdini_run_python` |
| **Workflow** | 7 步通用模式：理解上下文→搜索→创建配置→display flag→layout→验证→报路径 | |
| **Error Recovery** | 工具返回 `success:false` 时的 5 步排错 | |
| **Build Path Selection** | **关键决策表**：多部件→Project HDA；匹配 recipe→recipe；单体→sandbox | 明确"多部件唯一走 Project HDA" |
| **Geometry verification workflow** | build 后的验证步骤：先 `project_status`→`inspect_health`→`verify_orientation`→`geometry_inventory`→... | `inspect_health` 是 MANDATORY layer-1 |
| **Visual Verification Rules** | 🔴必拍 / 🟡应拍 / 🟢跳过（视觉验证开关 ON 时）；OFF 时改用数值证据 | `visual_verification_enabled` 控制 |
| **Workspace Lock** | Project HDA 模式下：**只许在 core 子树内操作**（见 §5）| |

### 第 2 层：SKILL.md（建模时按需读）

`skills/project-modeling/SKILL.md` 是操作手册。核心是：
- **3 条 Guardrail**：① 声明每个跨组件依赖（`ports.in`）② 总是测量别硬编码 ③ brainstorming 是快速通道不是完整访谈
- **3 个 leading words**：`scaffold` / `anchor` / `measure`——当触发词，不当散文读
- **4 步工作流**（create→scaffold→model→verify），每步带 ✅ 完成标准
- **progressive disclosure**：主文件是操作手册，遇到具体问题读对应参考（`PORT_PROTOCOL.md`/`COMPONENT_TEMPLATE.md`/`MISTAKES.md`/`DISCIPLINE.md`）

### 第 3 层：工具描述 + promptGuidelines（调用时随工具卡注入）

每个工具在 `project.ts` 里有三件套，agent 选工具/填参时直接看到：
- `description`：这个工具干什么
- `promptSnippet`：一句话用法
- `promptGuidelines[]`：填参要点 + 易错点

**例**（`project_finalize` 的 guidelines）：调它必须是报告完成前的最后一步；它自己跑验证（不用你单独调）；Gate 4 的 F1-F4 连 skip 都挡不住；失败要 **fix 后重新 finalize**，不是重新声明 done，也不是用 skip 绕过。

### 第 4 层：铁律（`rules.json`，运行时注入）

`edini-context` 从 `~/.pi/agent/edini-knowledge/rules.json` 读 `enabled` 的规则，注入成"## 铁律"块。规则是**用户沉淀的、跨项目的、反复犯的错**（≤20 条），带分类图标（⚠️避坑/💡技巧/📋工作流/⚙️配置）。这是 Hivemind 式持续学习的"人审过的知识"层。

> **词汇一致性是刻意的**：`guards.py` 的拒绝信息、SKILL.md 的 Guardrail、工具的 promptGuidelines **用同样的词**（`project_add_anchors`/`measure`/`scaffold`）。agent 在任一层撞墙，错误信息都指向同一个正道。

---

## 4. 工具设计：分类目录与设计原则

工具分 7 类。完整 schema 在 `pi-extensions/edini-tools/tools/project.ts`。

| 类别 | 工具 | 设计要点 |
|---|---|---|
| **生命周期** | `project_create` `project_plan` `project_build_scaffold` | 每步有前置依赖；scaffold 幂等且 shift-left 校验 |
| **建模** | `project_emit_component`(archetype) `project_add_anchors` `project_emit_markers` | archetype 优先于手搓；锚点只能测量 |
| **迁移** | `project_repath_to_relative` | 绝对 ch() → 相对，按需（默认留绝对路径） |
| **验证** | `project_status` `analyze_component_structure` `verify_parametric` `verify_robust` `verify_orientation` | 各管一面：状态/结构/驱动/区间/朝向 |
| **硬门** | `project_finalize` | 自己跑验证、拒绝放行（见 §8）|
| **快照** | `project_snapshot_component` `project_restore_component` `project_list_snapshots` | 存在 .hip 的 _snapshots subnet，OUT/inspect 跳过 |
| **学习** | `project_capture_archetype` `project_list_captured_archetypes` `edini_search_drafts` | 成功→原型；失败→草稿 |

### 工具 schema 的统一模式（TS 侧）

```typescript
{
  name, label, description,            // 给 agent 选工具用
  promptSnippet, promptGuidelines[],   // 给 agent 填参用（prompt 第 3 层）
  parameters: Type.Object({...}),      // TypeBox 类型 = JSON Schema
  async execute(_id, params) {          // 统一转发到 Python handler
    return forwardTool("project_xxx", params);
  }
}
```
- **TypeBox** 生成 JSON Schema，同时给 TS 编译期检查
- `forwardTool` 统一走 JSON-RPC 到 Houdini 内的 `tool_executor.py` 的 `TOOL_HANDLERS`
- `_id` 忽略（无状态调用）；参数名在 TS / Python / 文档间严格对齐

### 几个关键设计决策

1. **工具比 `houdini_run_python` 窄但安全**：每个专用工具有约束 + 校验 + 守卫；裸 python 没有。系统 prompt 明确"Only use houdini_run_python when no dedicated tool exists"。
2. **声明式优于命令式**：`project_build_scaffold(components=[…])` 一次声明，builder 确定性建网——agent 不写 `createNode`/wiring/blockpath，消灭整类错误。这是旧 harness 的核心转向（gate 加到一定密度后边际收益为负，builder 直接消灭错误源）。
3. **值约定**：archetype 的 size 是**数字**（字面）或**字符串**（design_param 名→live ch() 引用）。一个约定覆盖"固定值"和"参数化"两种。

---

## 5. Workspace Lock：两种 agent 形态

| 形态 | 触发 | 能做什么 |
|---|---|---|
| **主 Agent 窗口**（解锁） | 默认 | 通用场景操作 |
| **Project HDA 窗口**（锁定） | `EDINI_SCOPE_ID=project_hda` | **只能**在 `EDINI_CORE_PATH` 子树内操作 |

Lock 的硬规则：只许在 `${corePath}` 及其子路径内 create/modify/delete；不许碰 `/obj` 下别的节点、不许删 HDA 本身、不许对子树外跑 sandbox、不许改全局场景设置。用户请求超出范围时**告诉用户去主窗口**，不自己做。

这存在是因为 HDA 对话窗口只服务一个建模任务。Lock 由系统 prompt 注入（§3 第 1 层的 Workspace Lock 块）。

---

## 6. 组件端口协议（inter-component bus）

多组件协作的物理基础。理解它就理解了整条流水线为什么"改 A 就动 B"。

```
组件 tabletop                      组件 legs
┌─────────────────┐                ┌──────────────────┐
│ [桌面几何]       │                │ [腿几何]          │
│      ↓          │                │      ↑            │
│ out_geometry    │                │  out_geometry     │
│      ↓          │                │      ↑            │
│ tag_component   │                │  tag_component    │
│      ↓          │                │      ↑            │
│ out_anchors ────┼──→ output[1] ──┼─→ in_tabletop_leg_mount_fr ─→ tube(模板)
│  (@name,@P,     │   (锚点云)      │   (builder 预接)                   ↑
│   @orient)      │                │                          copytopoints(目标点)
│      ↓          │                │                                ↑
│  output_0 ──────┼─→ output[0]    │  filter_tabletop_leg_mount_fr (按@name留点)
│  (主几何)        │   (主几何)      │                                ↑
└─────────────────┘                │  __edini_anchor_clean_* (删所有prim→纯点云)│
                                   │                                ↑ input(1)
                                   └────────────────────────────────┘
        core.OUT = merge(所有组件的 output_0)
```

- **`out[0]` = 主几何**（必填，`{index:0, kind:'geometry'}`）
- **`out[1..n]` = 锚点云**（`@name`/`@P`/`@orient` 打标的点云）
- **`ports.in` = 消费声明**：`{from, port, anchor}`——从哪个组件的哪个输出端取哪个锚点
- **端口保证**：scaffold 在每个 in-port 插 Blast（按 `@name` 留点）+ prim 净化器（删所有 prim），所以 copytopoints 的第二输入**永远是纯点云**，无论上游接线怎么错

详细接线见 `PORT_PROTOCOL.md`（`in_<from>_<anchor>` 命名 / `output_index` / indirectInputs 机制）。

---

## 7. 规则与守卫全目录

这是"平台层硬执行"的完整清单。每条都是 **fail-fast**——在错误操作生效**前**拒绝，错误信息同时给出**正道**和（多数）**逃生口**。

### 守卫 1：`project_anchor_guard` — 禁止硬编码坐标

| | 内容 |
|---|---|
| **位置** | `project/guards.py: lint_wrangle_snippet`（tool_executor 在设 `snippet` 参数**前**调用）|
| **触发** | 目标是 **attribwrangle** + 在 **project core 子网内** + snippet 含**字面坐标** `addpoint(0, {0.5,0,0})` 或 `addpoint(0, set(0.225,0,0.225))` |
| **不触发** | 计算位置的 `addpoint`（`set(i-base,…)*step`/`@P`/`chf()`）——那是程序化几何；recipe/sandbox/独立 wrangle 不在 project core 内也不触发 |
| **拒绝信息** | `Refused: hardcoded-coordinate addpoint ...` + 两条正道：(a) 是跨组件锚点→`project_add_anchors`；(b) 是几何→从参数/属性算位置 |
| **逃生口** | snippet 含 `// edini-bypass-anchor-guard` 则放行（罕见合法固定点）|

> **判定逻辑**（`_position_is_literal`）：先删数字字面量（含科学计数法，防 `1e3` 的 `e` 被误读）+ 删向量构造名（`set`/`hou`/`vector`），剩下的若**还有标识符**→ 是变量/channel/属性→ 参数化→ 放行；**没有标识符**→ 纯字面坐标→ 拒。

**为什么**：椅子建模日志里 agent 手写 `addpoint(set(0.225,0,0.225), …)`，级联出 VEX 语法错、错 wrangle class、锚点串扰，多花 5 轮才补上。字面坐标不会随参数移动——正是"never hardcode coordinates"禁止的东西。

### 守卫 2：`internal_node_guard` — 禁止改内部节点

| | 内容 |
|---|---|
| **位置** | `project/guards.py: lint_wrangle_snippet`（与守卫 1 同函数，独立分支）|
| **触发** | 目标节点名是 `__` 前缀（如 `__edini_axis_bake`、`__edini_anchor_clean_*`）—— scaffold 拥有的内部节点 |
| **拒绝信息** | `Refused: '<name>' is an internal scaffold node ...` + 指向 `tag_component`（若想设 component_id/属性）|
| **逃生口** | 无（内部节点每次 rebuild 重设，改了也会被覆盖）|

**为什么**：会话日志里 agent 把 `__edini_axis_bake` 整个 snippet 覆盖成只设 component_id，**静默删了朝向轴**。平台因此把轴放进 agent 碰不到的节点 + 每次 rebuild 重设。改轴的唯一正道是**改声明的 `axis` 字段再 rebuild**。

### 守卫 3：结构声明 lint（shift-left）

| | 内容 |
|---|---|
| **位置** | `structure.py: lint_structure_decl`（`build_project_scaffold` 建网前调用）|
| **触发** | 组件带 `structure` 但：`bad_kind` / `missing_axis`（radial·planar 缺轴）/ `repeated_without_repeats` / `bad_repeat_count`（实例化 count<2）/ `structure_not_dict` |
| **结果** | 一次性返回全部 `lint_errors[]`，拒绝建网（`structure_missing` 放行——opt-in）|

### 守卫 4：端口契约校验（shift-left）

| | 内容 |
|---|---|
| **位置** | `ports.py: validate_component_ports`（`build_project_scaffold` 建网前调用）|
| **触发** | `out[0]` 非 geometry / 锚点 name 不符 `^[A-Za-z][A-Za-z0-9_]*$` / `ports.in` 缺 `from`·`port`·`anchor` / 重复或缺失 component id / 非法 `axis` token |
| **结果** | 聚合所有错一次性返回 `validation_errors[]`（带 `schema_hint`）|

### 守卫 5：跨组件路由检查（软警告）

| | 内容 |
|---|---|
| **位置** | `ports.py: validate_route_contract`（scaffold 成功后跑）|
| **触发** | `ports.in.anchor` 在上游没声明 / 上游组件不存在 |
| **结果** | `route_warnings[]`——**软**，不挡建网；运行时 Blast filter 是硬执行 |

### 守卫 6：运行时锚点净化（硬保证）

| | 内容 |
|---|---|
| **位置** | builder 在每个 in-port 自动插的 `filter_<from>_<anchor>`（Blast 按 `@name` 留点）+ `__edini_anchor_clean_*`（删所有 prim）|
| **触发** | cook 时自动生效 |
| **结果** | copytopoints 的第二输入**永远是纯点云**，无论上游误接了真实几何还是别的 |

### 非守卫：耦合建议（advisory，不挡）

`_coupling_advisories`（`verify.py:890`）：≥2 组件但**没有一个**声明 `ports.in` → `coupling_advisory: independent_components`。提示"它们是独立参数岛，各算各的，公式可能漂移——考虑耦合或合并"。**永不阻塞**（合法的独立组件确实存在）。源于 2026-07-09 立方体 cubies+stickers 会话。

---

## 8. `project_finalize` 的四道门

按执行顺序（**Gate 4 先跑**，这样结构致命错连 skip 都触发不了）：

### Gate 4：结构（先跑，skip 免疫）— `analyze_component_structure`

读节点图 + cook 过的几何 + 声明的结构意图，给每组件 fatal/advisory 判定。**fatal 连 `acknowledge_skip` 都挡不住**，唯一出路是审计过的 `structure_override=True` + 非空 `structure_reason`。

| 规则 | 判定 | 典型场景 |
|---|---|---|
| **F1** 裸曲线在 out_geometry | out 处有 curve/nurbs/polyline 原始 prim | 骨架没蒙皮 / OUT 接到了曲线而非 PolyWire |
| **F2** 重复件未实例化 | 声明了 instancing method 但 subnet 没该节点（declared 置信）；或 Python SOP 发 ≥40 prim 无 instancing 节点（inferred 置信） | 手搓复制轮辐 / Python 循环发射副本 |
| **F3** 径向·平面轴向不符 | 声明 radial/planar + expected_axis，但烘焙的 `edini_world_axis` 不符（复用 `verify_orientation`） | 轮子声明 Z 轴却生成 X 对称环（**只在声明了 kind+axis 时跑**）|
| **F4** CTP 目标点无朝向 | 有 copytopoints 但目标点（input 1）无 `orient`/`N`/`up` | 蜡烛/轮子朝错方向（继承单位朝向）|

> **三层分离**（`structure.py`）：纯逻辑 `lint_structure_decl`（声明校验）+ `evaluate_component_signals`（F1/F2/F4 判定，无 hou 可单测）→ hou 耦合 `_extract_component_signals`（走 subnet）→ `analyze_component_structure` 编排（F3 调 `verify_orientation`）。纯逻辑层 20 个单测全绿，无需 hython。

### Gate 1：完整性 — `project_status`

每个声明组件：`geo_flow=ok`（out_geometry 有几何）+ 无缺失锚点 + 无 cook 错。`overall.incomplete` 列出"还剩什么没建"。

### Gate 2：全区间稳定 — `verify_robust`

每个 design_param 在 min/default/max 都非退化 + 无错（见 §2 阶段 ⑤）。

### Gate 3：参数真驱动 — `verify_parametric`

每个 design_param 真的驱动几何（见 §2 阶段 ⑤）。`_finalize_perturbation` 自动选一个和当前值不同的扰动值（优先 max→min→current×1.5）。

### skip 与 override 的边界（"开对的门"原则）

| 想跳过… | 正道 | 审计 |
|---|---|---|
| Gate 1-3（验证真跑不了） | `acknowledge_skip=True` + 非空 `skip_reason` | 写进声明日志 `finalize_skip` |
| Gate 4 结构 fatal（真误报） | `structure_override=True` + 非空 `structure_reason` | 写进声明日志 `structure_override` |
| 无 design_param 的静态模型 | 什么都不用——Gate 2-3 自动 N/A（不是 skip） | 无 |

> **"开对的门"**（源自 pitfalls.md）：拒绝错误动作，但留一个正确的通道。这样 agent 不会被迫"撞墙"——它有合法出路，但每条出路都被审计。

### 闭环：失败 → 知识草稿

Gate 失败 → `_add_failure` 写 `FailureRecord`（带 category + hint）→ `add_failure_drafts` 存成可搜草稿。`_FINALIZE_HINTS` 给每类失败配中文修复提示（dead_param/degenerate/cook_error/orientation/structure…）。下次 agent `edini_search_drafts` 按类别查，历史可能已解决。

---

## 9. 关键设计决策与"为什么"

| 决策 | 理由 |
|---|---|
| **ground truth > 估计**（`edini_world_axis` bake） | PCA 估计点云主轴对径向对称管会取长度轴→90° 误判。烘焙声明轴成 ground truth，确定性、零估计 |
| **shift-left 校验**（scaffold 前一次性报全错） | 错误越早发现越便宜；一次报全部错省 agent 多轮往返 |
| **双探针 verify_parametric**（bbox + 点哈希） | 单 bbox 探针对"bbox 不变但点动"的形状参数假阴性，逼 agent 手改 `__edini_state` 绕过——点哈希兜底 |
| **`try/finally` 还原**（verify_parametric / verify_robust） | 验证工具绝不能污染用户场景；哪怕 cook 出错也得还原 |
| **Gate 4 skip 免疫** | 2026-07-09 的 6 会话里 3/6 靠 skip-hatch 放行了坏模型。结构致命错必须挡住，哪怕 agent 想跳 |
| **structure 是 opt-in**（缺失放行，畸形拒绝） | 每个 legacy fixture 都没声明——强制会全挂。Gate 4 仍无条件跑 F1/F2/F4，只 F3 需要声明 |
| **builder 不建几何** | 确定性/可幂等/可检测漂移的部分归平台，自由/创造性的部分归 agent。职责清晰 |
| **archetype 用相对 ch()** | 原型建的组件可跨项目迁移（copy-paste 子网仍 cook），而手搓的绝对 ch() 绑死在当前路径 |
| **工具 > `houdini_run_python`** | 专用工具有约束+校验+守卫；裸 python 没有。"能力先于规则"——先证能操作地基，再编排 |
| **词汇三层一致** | prompt/SKILL/工具描述/守卫拒绝信息用同一套词，agent 任一层撞墙都指向同一正道 |

---

## 10. 一轮完整建模的最小序列（速查）

```
project_create(name, goal)                          → core_path
project_plan(core_path, goal, success_criteria=[…])  → 意图锁定
project_build_scaffold(core_path, components=[…],     → 脚手架 + design_params
                       design_params=[…])                （含 structure 声明）
# —— 每个组件 ——
project_emit_component(core_path, comp_id, archetype, params)   或  手搓 + project_add_anchors
analyze_component_structure(core_path)                          → 建到一半自检 F1-F4
# —— 收尾 ——
verify_parametric(core/OUT, core, "length", new_value, "X")     → LIVE 证明
project_finalize(core_path)                                     → 四门全过 → finalized:true
# （可选，成功复利）
project_capture_archetype(core_path, comp_id, name)             → 下次复用
```

---

## 11. 代码地图

| 区域 | 文件 |
|---|---|
| 四道门 + verify_* + status + plan | `python3.11libs/edini/verify.py` |
| 结构分析器（lint + evaluator + extractor + orchestrator）| `python3.11libs/edini/structure.py` |
| 平台守卫（anchor + internal-node）| `python3.11libs/edini/project/guards.py` |
| 脚手架 builder + shift-left 校验接入 | `python3.11libs/edini/project/builder.py` |
| 端口协议 + 节点常量 + 校验 | `python3.11libs/edini/project/ports.py` |
| 声明读写 + 日志 + helpers | `python3.11libs/edini/project/state.py` |
| archetype 发射器 | `python3.11libs/edini/project/archetype_emitter.py` |
| 工具 handler 注册 | `python3.11libs/edini/tool_executor.py` |
| 系统 prompt 注入 | `pi-extensions/edini-context/index.ts` |
| 工具 TS schema | `pi-extensions/edini-tools/tools/project.ts` |
| 建模操作手册 | `skills/project-modeling/SKILL.md` |
| spec（设计文档）| `docs/superpowers/specs/2026-07-10-component-structure-analyzer-design.md` |
| plan（实现计划）| `docs/superpowers/plans/2026-07-10-component-structure-analyzer.md` |

---

*本页描述的是 `master` 分支截至 2026-07-10 的程序化建模 agent（含 component-structure-analyzer cut-1）。代码演进后以源文件为准。*
