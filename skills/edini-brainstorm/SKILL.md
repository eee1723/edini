---
name: edini-brainstorm
description: Use at the START of any Houdini procedural asset or geometry task, BEFORE touching nodes or writing code. Explores user intent, decomposes into components, selects backends (vex_skeleton / native_chain / Python / CTP), and produces a design spec. Replaces the generic brainstorming skill for Houdini geometry work.
license: MIT
---

# Edini Brainstorming — Houdini Design Router

Use this skill at the START of any Houdini geometry task that involves creating, modifying, or assembling components. Do NOT jump into implementation.

## Phase 1 — Context First

Before asking any questions, understand the scene:

1. Check `[Current Houdini Context]` if present — current HIP, network, selected nodes
2. If unclear, call `houdini_get_scene_info` to understand the scene state
3. If there's existing geometry, call `houdini_get_selection` to see what the user has selected

## Phase 2 — Clarifying Questions (one at a time)

Ask questions **one at a time**, each with 3-4 concrete options (A/B/C/D). Wait for the user's answer before asking the next.

**Auto-advance rule:** If the user says "继续" (continue) twice, they want you to stop asking and move to Phase 3. Do NOT ask a third clarifying question after two "继续" responses — proceed to the design proposal immediately.

### Required questions (ask only these 3-4, then auto-advance):

1. **Style & purpose** — What style/type? (e.g. road bike vs mountain bike vs city bike)
2. **Parameterization level** — How many parameters? (基础/中度/高度)
3. **Detail level** — How detailed? (精简/标准/完整) "精简/标准" are self-contained in the Builder; "完整" triggers the Workspace question below.
4. **Material/shape preferences** — Tube shape, spoke style, etc. (domain-specific; skip if obvious from style)

### After answers to Q1-3, auto-advance to Phase 3 (design proposal).

### Stop asking when:
- You have answers to items 1-3 minimum
- OR the user says "继续" twice
- The component decomposition is clear enough to fill the RECIPE template

## Phase 3 — Propose Design

After gathering answers, propose the design as a structured summary:

```
## [Asset Name] — 设计方案

**需求回顾：** [1-line summary of key decisions]

### 组件分解

| # | Component | component_id | Backend | Anchor? |
|---|---|---|---|---|
| 1 | ... | ... | vex_skeleton / native_chain / python / CTP | yes/no |

### 参数体系

| Parameter | Range | Default | Drives |
|---|---|---|---|
| ... | ... | ... | ... |

### 后端选择理由
- [component_X]: vex_skeleton — tube/path geometry, Sweep guarantees closed normals
- [component_Y]: python — complex organic surface, no SOP equivalent
- [component_Z]: CTP template — repeated ≥2 times

### 组装架构
[ASCII diagram showing Merge → CTP → postprocess flow]

### Workspace Plan（微细重复件独立构建计划）
| Workspace | 内容 | 方法 |
|---|---|---|
| _wheel_spokes_ | 单根辐条模板 + scatter → CTP | network_mode sandbox |
| _chain_links_ | 单节链条模板 + 路径scatter → CTP | network_mode sandbox |

\`\`\`

## Phase 4 — MANDATORY Backend Audit (HARD GATE)

Before showing the design to the user, fill out this audit checklist.
**Each item must answer YES or NO. If ANY check returns NO, fix the design
BEFORE presenting it to the user. Do NOT skip this step.**

### ⛔ Backend 红线表（来自 component-building，此处重复以确保在设计中可见）

| 几何类型 | 必须用的 backend | 绝对禁止 |
|---|---|---|
| **管 / 杆 / 车把**（沿路径的圆柱） | **vex_skeleton + sweep::2.0** | Python add_tube() / createPolygon 循环 |
| **截面挤出**（柱/梁/块） | **vex_skeleton + polyextrude::2.0** | Python 手写 box |
| **简单几何体**（hub/cylinder/pedal/brake） | **native_chain** | Python createPolygon 循环 |
| **重复件 ≥2**（辐条/砖块/链条/轮子） | **native_chain 模板 + CTP** | Python for 循环 |
| **复杂有机曲面**（座垫/地形/分形） | python SOP | —（仅此类别可用 Python）|

### 审计清单

逐组件对照红线表检查：

```
BACKEND AUDIT:
  [component_id_1]: 几何类型=<管材/简单几何/重复件/有机曲面>, 当前后端=__, 红线要求=__, 符合? YES/NO
  [component_id_2]: 几何类型=__, 当前后端=__, 红线要求=__, 符合? YES/NO
  ...

PYTHON GATE:
  Python 后端组件数: __ / 总数 __ = __%
  其中管材几何: __ 个 (必须为 0!)
  其中简单几何: __ 个 (必须为 0!)
  真正必需的有机曲面: __ 个 (唯一允许使用 Python 的类别)

CTP AUDIT:
  重复 ≥2 次的组件: [list], 全部有 CTP 锚点? YES/NO

ORIENTATION ASSERT AUDIT:
  所有 component_id 都有 orientation_assert? YES/NO
  缺失: [list if any]

PARAMETER CHECK:
  用户可调参数 ≥5? YES/NO  跨组件联动 ≥1? YES/NO

RECIPE SIZE:
  总组件数 >12? YES→分阶段 / NO→单阶段
```

### ⛔ HARD STOP 条件（违反任一条 = 禁止输出设计方案）

1. **任何管材/路径组件使用 python → 拒绝。** 必须改为 vex_skeleton
2. **任何简单几何体（hub/cylinder/box）使用 python → 拒绝。** 必须改为 native_chain
3. **Python 占比 >20% → 拒绝。** 复查：是否有可转换为 vex_skeleton 或 native_chain 的组件？
4. **重复件没有 CTP 锚点 → 拒绝。** 必须添加 anchors

## Phase 5 — Write Design Spec (结构化 Recipe 骨架)

将设计输出为 **recipe 骨架格式**（可直接交给 `recipe-authoring` 技能完善）：

```jsonc
{
  "asset_name": "<name>",
  "units": "meters",
  "components": [
    {"id": "frame", "backend": "vex_skeleton", "geometry_type": "tube_frame",
     "exposes": ["bb_shell", "head_tube_top", "seat_cluster", "rear_dropout"],
     "description": "完整车架管材（上下立头后上下叉）"},
    {"id": "hub_front", "backend": "native_chain", "geometry_type": "cylinder",
     "description": "前花鼓（圆柱+法兰）"},
    // ...
  ],
  "params": [
    {"name": "wheel_radius", "kind": "primary", "default": 0.34, "min": 0.28, "max": 0.40, "group": "Wheels"},
    // ...
  ],
  "orientation_asserts": [
    {"component_id": "rim_front", "kind": "radial", "expected_axis": "Z", "construction_axis": "Z"},
    // ...
  ],
  "postprocess": ["fuse", "clean", "normal"],
  "phases": [
    {"phase": 1, "components": ["frame", "fork", "rim_front", ...], "description": "核心结构"},
    {"phase": 2, "components": ["spokes", "chain", ...], "description": "重复件+细节"}
  ]
}
```

同时保存到 `docs/edini/specs/YYYY-MM-DD-<topic>-design.md`。

## Phase 6 — Transition to Implementation

After the user approves the design:
1. **MANDATORY:** Load the **procedural-modeling** skill — it will route you to recipe-authoring
2. **MANDATORY:** Use `build_procedural_asset(recipe)` as the build entry — NEVER use `houdini_run_python_sandbox(network_mode=true)` for multi-component assets
3. Follow the pipeline: recipe → validate_recipe (G1, A1-A9) → build_procedural_asset (构建+组装+G2 烘焙) → verify (G3 闸) → commit (返回 verification_receipt) → test_params
4. Do NOT re-ask clarifying questions already answered
