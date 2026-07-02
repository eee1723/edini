# Project HDA — 组件建模地基设计(spec)

> **状态**：设计已与用户确认（2026-07-02 brainstorming），待 writing-plans 转实现计划。
> **范围**：子系统 1（组件建模地基）。子系统 2/3/4（多组件流水线 agent 端到端 / 知识图谱描述生成 / drift 检测）只勾勒方向，单独 spec。
> **取代**：本设计**取代**当前 Project HDA 里基于 rooted `build_assembly` 的扁平建模范式（旧 `assembly` 字段整套移除，见 §7）。
> **前身**：`docs/superpowers/specs/2026-07-01-project-hda-design.md`（§9 定义了 drift 概念规则，本 spec 的子系统 4 将细化）。

---

## 0. TL;DR

把 Project HDA 的建模能力从"rooted 扁平网络（root + mount + leaf + CTP）"重构为**组件流水线范式**：

- 一个组件 = core 内的一个 **subnet 节点**（id = subnet 名，承重键）。
- subnet 通过**多输出端口**对外暴露：`out[0]` 恒为组件主几何，`out[1..n]` 为**信息点云**（带 `@P`/`@orient`/`@name`/自定义属性的 point），供下游组件定位/定向/参考。
- 组件间协作是流水线：车架输出 `wheel_mount` 锚点 → 车轮消费它定位 → 车轮再输出锚点供辐条……LLM 自由决定组件粒度和信息点。
- **声明（components + ports + params）即知识图谱**。drift = diff 这份意图 vs 实际网络。
- **Builder = 脚手架**（确定性）：只建空 subnet + null + 端口连接。**几何 = LLM 自由活**（network_mode sandbox）。
- 参数管理：每个组件 subnet 暴露 spare parm → **promote 脚本**一键按组件分组提取到 core HDA 顶层，两层 `ch()` 引用全程 live。

这是 4 子系统全栈设计的**地基**（子系统 1）。地基真机验证站稳后，再做流水线 agent 端到端（2）、知识图谱（3）、drift 检测（4）。

---

## 1. 问题陈述

### 第一性原理

Project HDA 的核心价值是"用户和 agent 都能改几何的长期协作"。为此，agent 维护的知识图谱（声明）必须与真实网络保持同步。spec 2026-07-01 §9 的核心策略是：**让 subnet 的物理嵌套结构镜像组件分解，把"语义同步"降级为"结构 diff"**——使"哪些节点属于哪个组件""组件是否还存在""参数依赖"全部变成确定性查询。

但当前实现（`build_project_model`）把 rooted 扁平网络直接铺在 core 内部（13 个无分组 SOP），**没有组件级物理结构**。这让 drift 检测失去确定性落点。

### 用户确立的新范式（2026-07-02 brainstorming）

用户在 brainstorming 中明确了 subnet 的根本作用，并要求**新范式取代旧范式**：

> "subnet 上有输入输出端口，可以用这些端口来做其他组件的挂载点。subnet 的第一输入端必须是组件本身的输出端，后续所有端口都可以作为信息端口输出给其他组件做定位用……比如做自行车，先做车架组件，输出两个点作为车轮的定位定向点，再去 subnet 中做车轮组件建模……知识图谱就是快速告诉大模型每个组件之间的联系。"

关键转变：subnet 不是"drift 的容器"，而是**组件间信息总线**。端口 = 组件协作的物理基础。

### 本次 brainstorming 确立的 6 个核心决策

| # | 决策点 | 选择 | 理由 |
|---|---|---|---|
| 1 | subnet 根本作用 | **组件间信息总线**（端口=信息锚点） | 用户第一性原理 |
| 2 | 与旧 rooted 范式关系 | **新范式取代** mount/leaf | 用户拍板，保持架构干净 |
| 3 | 本次 brainstorming 范围 | **全栈 4 子系统**，但地基先单独 spec | 用户选 Approach A（地基先做） |
| 4 | 信息点物理本质 | **混合**：out[0]=主几何，out[1..n]=带属性点云 | 决定端口协议 |
| 5 | 挂载消费方式 | **声明意图 + 自由连接** | 声明软约束，LLM 自由接线，drift 查一致性 |
| 6 | 知识图谱本质 | **声明的一部分**（components+ports 即图谱） | 零双重同步（spec 决策 #7 延伸） |

---

## 2. 范围

### In scope（本 spec 覆盖，子系统 1）

- 组件 subnet 物理结构 + 端口信息点协议（§3）
- 声明 schema 改造（`components` + `ports` + `params`，§4）
- Builder 重写：脚手架 builder + promote 脚本（§5、§6）
- 参数 live 引用链（两层 channel）
- 旧 `assembly` 范式清理（§7）
- hython 决定性验证（§8）

### Out of scope（后续 spec 覆盖）

- **子系统 2：多组件流水线 agent 端到端** —— LLM 真实驱动建模（network_mode sandbox 在 subnet 内 createNode）、跨 subnet 连线的 agent 编排。地基只保证脚手架"可被 LLM 工具操作"，不实现 agent 流程。
- **子系统 3：知识图谱描述生成** —— 把声明里的 components/ports 渲染成给 LLM 的"组件联系"自然语言描述（"车架输出 wheel_mount 给车轮"），供 LLM 分析合理性、补细节。
- **子系统 4：drift 检测算法** —— §9 定义确定性 diff 算法 + 人裁决流程（三选项：接受事实 / 恢复意图 / 改意图）。本 spec 只保证 schema 能支撑它（§4.3 预埋接口）。
- **LLM 建模纪律 skill** —— 见 §10（后续沉淀，本次只记录方向）。
- 计划树 / 状态面板 / drift 裁决 UI。

---

## 3. 组件 subnet 物理结构 + 端口协议

### 3.1 一个组件长什么样

一个组件 = core（`edini::project` SOP HDA 实例）内部网络里的一个 **subnet 节点**。subnet 名 = 组件 id（承重键，drift 识别用）。subnet 内部是一个 SOP 网络，汇到命名 output 节点，通过**多输出端**对外暴露几何和信息点：

```
core (edini::project SOP HDA, 内部网络)
├─ chassis/                 ← 组件 subnet (id="chassis")
│   ├─ <LLM 自由建模节点>    ← 车架几何（LLM 在 network_mode sandbox 建）
│   ├─ out_geometry          ← out[0] 主几何，连 subnet output connector 1
│   └─ out_anchors           ← out[1] 信息点云，连 subnet output connector 2
│                             （每个点带 @P/@orient/@name/@(自定义)）
├─ wheels/                  ← 组件 subnet (id="wheels")
│   ├─ <LLM 建模：从 chassis 取锚点定位车轮>
│   └─ out_geometry          ← out[0] 车轮几何
└─ OUT                      ← core 输出（所有组件主几何 merge）
```

### 3.2 端口协议（关键约定）

| 端口 | 内容 | 用途 |
|---|---|---|
| **out[0]** | 组件**主几何**（subnet output connector 1） | 汇入 core 的 OUT（最终显示）；也可供下游组件作输入几何 |
| **out[1..n]** | **信息点云**（subnet output connector 2+） | 带属性的 point group，供下游组件**定位/定向/参考** |

**信息点云的属性约定**（每个 point）：

| 属性 | 类型 | 含义 |
|---|---|---|
| `@P` | vector | 位置（定位） |
| `@orient` | quaternion | 朝向（定向） |
| `@name` | string | 信息点名（`wheel_mount_fr` / `handlebar` / `seat`）—— **图谱与 drift 的识别键** |
| `@<任意>` | 任意 | 自定义属性（半径、长度等参数，LLM 按需） |

### 3.3 subnet 内部强制结构（builder 建，确定性）

builder 对每个 component 建如下脚手架（subnet 内部）：

```
<component>/  (subnet)
├─ out_geometry   (null 节点, 连 subnet output 1)   ← builder 建，空，等 LLM 填
├─ out_anchors    (null 节点, 连 subnet output 2)   ← builder 建，空，等 LLM 填锚点云
└─ (空，LLM 在 out_geometry / out_anchors 上游自由建模)
```

- builder **不建**任何 VEX/box/torus（旧 build_assembly 的活，现在归 LLM）。
- builder 保证 `out_geometry` 和 `out_anchors` 两个 null 存在且连到对应 subnet output connector，使端口协议物理成立。
- LLM 往 `out_geometry` 上游接节点建模（产主几何），往 `out_anchors` 上游接 addpoint/wrangle 产锚点云。

### 3.4 设计依据

- **subnet 多输出端**是 Houdini 原生能力（subnet 可加多个 output connector），不造新机制。
- **信息点 = 带属性的 point**，是 Houdini 最自然的"带元数据的位置"载体，CTP/wrangle 都能消费，drift 能确定性枚举（"这个 @name 的点在不在"）。
- **out[0] 恒为主几何**，让"几何事实"和"信息锚点"物理分离，drift 能分别检测（主几何丢失 vs 锚点丢失是不同 drift）。
- **@name 作识别键**，让"wheel_mount_fr 锚点"跨组件可寻址，是"声明意图"（下游该消费哪个点）的物理基础。

---

## 4. 声明 schema 改造

### 4.1 `components[]` 新形态

```jsonc
"components": [
  {
    "id": "chassis",                       // 组件 id = subnet 名（承重键）
    "subnet_path": "./chassis",            // core 内相对路径（事实定位）
    "purpose": "车架主体 + 信息锚点输出",    // LLM 写的语义说明（图谱给 LLM 看）
    "params": [                            // 这个组件暴露的可调参数（§6）
      {"name": "length", "label": "车长", "default": 4, "min": 1, "max": 20},
      {"name": "width",  "label": "车宽", "default": 2}
    ],
    "ports": {                             // 端口协议（§3.2）
      "out": [
        {"index": 0, "kind": "geometry", "description": "车架几何主体"},
        {"index": 1, "kind": "anchors", "points": [
          {"name": "wheel_mount_fr", "role": "mount",      "description": "前轮安装点"},
          {"name": "wheel_mount_rr", "role": "mount",      "description": "后轮安装点"},
          {"name": "handlebar",      "role": "reference",  "description": "车把位置参考"}
        ]}
      ],
      "in": []                             // chassis 是根组件，无 in
    }
  },
  {
    "id": "wheels",
    "subnet_path": "./wheels",
    "purpose": "车轮，消费车架的 wheel_mount 锚点定位",
    "params": [
      {"name": "radius", "label": "轮半径", "default": 0.5}
    ],
    "ports": {
      "out": [
        {"index": 0, "kind": "geometry", "description": "前后轮几何"}
      ],
      "in": [                              // 连接意图：我消费 chassis 的锚点（软约束）
        {"from": "chassis", "port": 1, "anchor": "wheel_mount_fr", "description": "前轮定位依据"},
        {"from": "chassis", "port": 1, "anchor": "wheel_mount_rr", "description": "后轮定位依据"}
      ]
    }
  }
]
```

### 4.2 设计要点

1. **`ports.out` = 我提供什么，`ports.in` = 我消费什么**。合起来即组件关系图（知识图谱）。drift 时：`out` 对照实际 subnet 输出端 + 锚点 `@name`；`in` 对照实际节点连线。
2. **`ports.in` 是软约束（意图），不是接线指令**。声明写"wheels 意图从 chassis 的 `wheel_mount_fr` 定位"，但 LLM 在 wheels subnet 内部自由决定怎么接（可能 wrangle 取点，可能 CTP）。drift 只在"声明说连 chassis 但实际没连"时提示——契合"声明意图 + 自由连接"。
3. **`purpose` / `description` 是给 LLM 的语义**。这是知识图谱"告诉大模型组件联系"的载体——LLM 读声明就能理解"车架输出轮子安装点、车轮消费它们"，进而分析合理性、补细节（子系统 3 展开）。
4. **`ports.in[].anchor` 用 `@name` 软指定**（不硬绑端口序号）。下游意图取"这个名的点"，实际接哪个端口由 LLM 定。
5. **`points[].role` 取自由字符串**（`mount`/`reference`/`axis`/...），不预设枚举，等真机见多了再约束——沿用 spec 2026-07-01 §5"可扩展不预设"原则。

### 4.3 drift 接口预埋（本 spec 不实现，只确认 schema 能支撑）

| drift 检测项（子系统 4） | 对照 schema 的什么 | 对照实际的什么 |
|---|---|---|
| 组件存在性 | `components[].id` | core 内 subnet 子节点名 |
| 端口/锚点存在性 | `ports.out[].points[].name` | subnet 输出端 + 锚点云的 `@name` |
| 连接一致性 | `ports.in[]` | 实际节点跨 subnet 连线 |
| 主几何丢失 | `ports.out[0]` | subnet output 1 是否有几何 |
| 参数登记一致性 | `components[].params[].name` | subnet 实际 spare parm 名 |

---

## 5. Builder 重写：职责边界

### 5.1 核心切分

把职责一刀切开：**Builder = 脚手架（确定性），几何 = LLM 自由活**。

| 职责 | 谁做 | 确定性？ |
|---|---|---|
| 创建组件 subnet（按 `components[].id`） | **builder** | ✅ |
| 配置 subnet 端口 + null output 节点（按 `ports.out`） | **builder** | ✅ |
| 声明 ↔ 结构同步（隐藏 parm 读写） | **builder** | ✅ |
| **subnet 内部几何建模** | **LLM**（network_mode sandbox） | ❌ 自由 |
| **跨 subnet 连线（消费上游锚点）** | **LLM** | ❌ 自由 |

builder 只建"脚手架"：空 subnet + 多 output 端口 + null 占位。LLM 在 subnet 里自由建模，几何和连线都是 LLM 的自由活。

### 5.2 为什么这样切

1. **确定性部分 = 可 drift 检测部分**。builder 建的脚手架（subnet/null/端口）是 drift 能确定性查的；LLM 自由建的部分（几何细节）不在 drift 范围（那是事实，声明不管）。drift 边界天然清晰。
2. **最大化 LLM 能力**（用户目标）。几何和连接完全由 LLM 决定，不被声明焊死。声明只管"有哪些组件、各自提供/消费什么端口"这个骨架。
3. **builder 极简、极稳**。只建空容器 + null + 连端口，不碰 VEX/几何，几乎没有真机 bug 风险（对比旧 build_assembly 的 VEX 策略复杂度）。
4. **network_mode sandbox 已存在**（harness.py），LLM 在 subnet 内建模的机制现成，不造新东西。

### 5.3 builder API（取代旧 `build_project_model`）

```python
def build_project_scaffold(core_node, *, declaration=None) -> dict:
    """建/更新组件脚手架（空 subnet + null + 端口）。

    幂等：对已存在的 subnet/null 不重复创建，只补缺失的。
    不碰几何（几何归 LLM）。返回 {success, components_built, ...}。
    """
```

- 取代旧 `build_project_model`（吃 assembly 建几何）。
- 吃完整 `declaration`（或从 core 隐藏 parm 读），按 `components[]` 建脚手架。
- 幂等：重跑不重复（对已存在 subnet/null 跳过）。

---

## 6. 参数管理：subnet 暴露 + promote 脚本

### 6.1 参数流转链（两层 channel 引用，全程 live）

```
HDA core 顶层 parm:  chassis_length = 8
                        │  ch("./chassis/length")      ← promote 脚本建的引用
                        ▼
chassis/ subnet parm:  length = ch("chassis_length")   ← 实际由 HDA 顶层驱动
                        │  VEX 里 ch("./length") 或 ch("length")
                        ▼
                    几何 live 更新
```

每层引用都是相对路径，引用深度天然正确（SOP 上下文决策的延伸）。

### 6.2 两个动作

| 动作 | 谁触发 | 做什么 | 确定性？ |
|---|---|---|---|
| 组件 subnet 暴露参数 | LLM 建模时 | LLM 在自己 subnet 上加 spare parm（命名 `<param>`），声明 `components[].params` 记录 | ⚠️ LLM 半自由 |
| **promote 到 HDA** | 用户/agent 一键脚本 | 扫描所有组件 subnet 的 spare parm → 按组件名分组 → 在 core HDA 建 parm（folder=组件名）+ channel 引用 | ✅ 确定性 |

promote 是**独立触发的一键脚本**（不是每次 build 自动跑），用户想生成变体接口时手动/agent 触发。

### 6.3 promote 脚本确定性逻辑

```
对 core 下每个 component subnet (./chassis, ./wheels, ...):
    读它的 spare parm group
    对每个 spare parm <name>:
        在 core HDA 建 parm: "<component>_<name>"  (放 "<component>" folder 下)
        设其值为表达式:  ch("./<component>/<name>")
结果: 用户在 core 顶层调 chassis_length → 驱动 chassis subnet → 几何 live
```

纯确定性、可单测（spare parm group 读写 mock 已有，见 `tests/mock_hou.py`）。不需要 LLM，不碰几何。

### 6.4 schema 配套

`components[].params`（见 §4.1）记录每个组件暴露的参数，供 promote + drift 用。顶层 `design_params` 降为 **promote 后的产物**（HDA 顶层接口镜像），由 promote 自动生成，不再是手填。

---

## 7. 旧范式清理（保持架构干净）

本设计**取代**旧 rooted `assembly` 范式。旧范式痕迹从 Project HDA 移除（不影响 rooted-modeling skill，后者仍用 `assembly_builder.py`/`vex_strategies.py`/`measure.py`）：

| 文件 | 动作 |
|---|---|
| `python3.11libs/edini/project/state.py` | 删 `get_assembly`/`set_assembly`/`_REQUIRED_ASSEMBLY_KEYS`；`empty_declaration` 移除 `assembly` 字段 |
| `python3.11libs/edini/project/builder.py` | **重写**：不再 `import build_assembly`；改为 `build_project_scaffold`（§5.3）+ promote 脚本（§6） |
| `pi-extensions/edini-tools/tools/project.ts` | 删 `assembly` 参数；改为接收 `declaration`（完整声明）或 `components` |
| `assembly_builder.py`/`vex_strategies.py`/`measure.py` | **保留不动**（rooted-modeling skill 仍用） |
| `tests/test_project_state.py` | 改：删 assembly 相关断言；加新 schema（components/ports/params）测 |

**无兼容负担**：当前 `project_build_model` 的 agent 端到端尚未真机验证（handoff 下一步①），重写不破坏已验证能力。地基干净，直接重写成新范式。

---

## 8. 验证策略（hython 决定性）

地基必须有**决定性真机证据**，不能只 mock。最小验证场景（hython 跑通即地基稳）：

```
场景：2 组件流水线（chassis → wheels），证明端口协议 + builder + promote 全链路

1. builder 收到声明（2 components + ports + params）
   → core 内建 2 个 subnet（chassis/, wheels/），各带 out_geometry/out_anchors null + 连端口
   → 断言：./chassis、./wheels 存在；各有 2 个 null 连到 subnet output connector 1/2

2. 模拟 LLM 往 chassis/out_anchors 上游插 addpoint（产 wheel_mount 锚点）
   → 断言：chassis subnet output 2 cook 出带 @name="wheel_mount" 的点

3. 模拟 LLM 往 wheels/out_geometry 上游插建模 + 从 chassis 取锚点
   → 断言：wheels 几何落在锚点位置（消费链通）

4. 在 chassis subnet 加 spare parm "length"
   → 跑 promote 脚本 → core HDA 出现 chassis_length（folder:chassis）parm
   → 断言：改 chassis_length → chassis subnet length 跟变 → 几何 live（若有 VEX 引用）

5. 幂等：再跑一次 builder，subnet/null 不重复创建
```

**这套跑通 = 地基能力证明**（capability-before-rules 的"capability"）。后续 skill（建模纪律）建立在它之上。

验证脚本：`tests/test_project_hython.py`（复用 `tests/test_assembly_hython.py` 的 hython 发现机制 `_find_hython()`，两台开发机自动覆盖，见 handoff）。

---

## 9. 后续子系统方向（勾勒，单独 spec）

### 9.1 子系统 2：多组件流水线 agent 端到端

LLM 真实驱动建模：在组件 subnet 内用 `houdini_run_python_sandbox`（network_mode）createNode + native SOP 组合建模；跨 subnet 连线（消费上游锚点）由 agent 编排。地基只保证脚手架"可被 LLM 工具操作"。

### 9.2 子系统 3：知识图谱描述生成

把声明 components/ports 渲染成给 LLM 的"组件联系"自然语言描述（"车架输出 wheel_mount 给车轮，车轮输出辐条参考点"），供 LLM 分析合理性、补细节、加联系。挂在 agent 的 system prompt 或专用工具。

### 9.3 子系统 4：drift 检测

§4.3 的 5 个检测项的确定性 diff 算法。发现不一致时按 spec 2026-07-01 §9.2 的三选项请人裁决：(a) 接受事实（更新声明的事实视图）/ (b) 恢复意图（agent 重建）/ (c) 改意图（用户说明新意图）。重命名 vs 删除的区分靠位置/内容相似度启发式 + 人确认（§9.3）。

---

## 10. LLM 建模纪律（后续 skill，本次只记录方向）

等真机积累案例后，沉淀成 `project-modeling` skill（类似现有 `asset-authoring`）。方向（用户 2026-07-02 确立）：

| 纪律 | 含义 |
|---|---|
| 禁纯 Python 建模 | 不能一个 Python SOP 画全部几何，要符合正常建模逻辑 |
| Python 不塞单 SOP | 即便用 Python，也分散到多个 SOP，不堆一个里 |
| VEX 优先 | 绝大部分需求用 VEX（wrangle + native SOP 组合） |
| native node 兜底 | VEX 难但 native 节点容易的（sweep/fuse/boolean），用 native |

本 spec 不实现这些规则（capability-before-rules：先证明地基能力，规则建立在已验证能力之上）。

---

## 11. 文件结构（子系统 1 产出）

```
python3.11libs/edini/project/
  state.py          # 改：新 schema（components/ports/params），删 assembly
  node.py           # 改：create_project_hda 适配（仍建 geo shell + core）
  builder.py        # 重写：build_project_scaffold（脚手架）+ promote 脚本
  ports.py          # 新：端口协议常量/校验（out[0]=主几何, out[1..n]=锚点云）
pi-extensions/edini-tools/tools/project.ts   # 改：新工具参数（declaration/components）
tests/
  test_project_state.py     # 改：新 schema 测
  test_project_ports.py     # 新：端口协议测（mock）
  test_project_hython.py    # 新：hython 决定性验证（§8 五步）
```

---

## 12. 风险与对策

| 风险 | 对策 |
|---|---|
| subnet 多输出端配置在 Houdini 21 的真实 API 细节未验证 | §8 步骤 1 的 hython 验证先行暴露；参考 Houdini 自带 subnet 多 output 用法 |
| promote 脚本读 spare parm group 在 H21 的 API（addSpareParmTuple/setParmTemplateGroup）已有真机验证（handoff bug#1） | 复用已验证模式 |
| LLM 在 subnet 内建模的 network_mode sandbox 行为未在 subnet 上下文验证 | 子系统 2 范围；地基的 §8 步骤 2-3 用 addpoint 模拟，先证端口通 |
| 重写破坏现有 mock 测试 | §7 清理清单已列；重写后重跑 test_project_state.py |

---

## 13. 自审记录

- **placeholder 扫描**：无 TBD/TODO；§9/§10 明确标注"后续 spec/skill"。
- **内部一致性**：§3 端口协议 ↔ §4 schema ports ↔ §5 builder ↔ §8 验证步骤，全程对齐；`assembly` 清理（§7）与 schema（§4 无 assembly）、builder（§5.3 取代 build_project_model）一致。
- **范围**：聚焦子系统 1（地基），2/3/4 明确 out-of-scope 并勾勒方向。
- **歧义**：`ports.in[].anchor` 用 @name 软指定（非端口序号）已显式说明；promote 独立触发（非每次 build）已显式说明。
