---
name: assembly-wiring
description: Reference for designing anchors, Copy-to-Points layout, and variant scatter in a recipe. Assembly itself is automatic inside build_procedural_asset — this skill covers the recipe-level decisions that drive it (anchor placement, position_expr linkage, postprocess chain order, micro-repetition via variant scatter).
license: MIT
---

# Assembly & Wiring (Recipe 设计参考)

**组装是自动的**——`build_procedural_asset(recipe)` 内部完成 Copy-to-Points、idfix、merge、postprocess，你**从不手写接线**。这个 skill 的职责是：教你如何在 **recipe 层面**设计锚点布局、参数联动、后处理链，让自动组装产出正确的结果。

## 锚点设计（recipe 的 `components[].anchors` 字段）

```jsonc
// 参数联动锚点（推荐）— position_expr 引用 params，活的通道
{
  "position_expr": ["wheelbase/2", "wheel_r", "-0.55"],  // 引用 params，改参数自动重算
  "orient": [0, 0, 0, 1],                                 // 四元数 [x,y,z,w]，单位=[0,0,0,1]
  "pscale": 1.0,                                          // 1.0 = 原始大小；建议建模为单位尺寸，pscale 设真实尺寸
  "component_id": "wheel_fl"                              // 每实例唯一 id（verify_orientation 用）
}

// 静态位置（回退）— 固定坐标，不联动
{
  "position": [0.5, 0.34, 0],
  "orient": [0, 0, 0, 1],
  "component_id": "rim_rear"
}
```

**`position_expr` vs `position`：** 优先用 `position_expr`——它引用 `params`，改资产级参数时所有锚点自动重算（真正的参数化）。只在位置确实与参数无关时用静态 `position`。

**`component_id`（每锚点）：** 每个锚点给一个**全局唯一**的实例 id（`wheel_fl`、`wheel_fr`...）。builder 用它覆盖每个 stamp 实例的 prim `component_id`，这样 `verify_orientation` 能逐实例检查方向。模板组件（无锚点，直 merge）的 `component_id` 就是它的 `id`。

## 自动组装网络（builder 生成，你不写）

```
<id>_python     (你的 code)       ─┐
<id>_anchors    (builder: 点)     ─┤-> copy_<id> (copytopoints) -> <id>_idfix (覆盖 component_id) -> merge
                                   │                                                              │
(无锚点组件直 merge) ───────────────────────────────────────────────────────────────────────────────┤
                                                                                                     v
                                                            merge_all -> postprocess... -> OUT
```

- builder 为每个**有锚点**的组件建一个 copytopoints + idfix 子链。
- **无锚点**组件直接 merge。
- 每个组件还自动烘焙 `edini_world_axis`（Stage 3）——这是 G2/G3 闸门检查的轴属性，你不用管，builder 负责。

## CTP 配置（builder 自动处理，但你要懂原理）

- `copytopoints::2.0` 的 `resettargetattribs` 按钮：builder 自动按，把 scatter 点的 `id` 传给实例。**你不要手按**。
- idfix wrangle：把基值 `@component_id` 设为模板 id，再用锚点的 `component_id` 覆盖特定实例。
- 锚点 `orient` 用四元数 `[x,y,z,w]`——单位四元数 `[0,0,0,1]`。

## 后处理链（recipe 的 `postprocess` 字段）

**顺序很重要——不按这个顺序会导致几何体损坏：**

```
merge_all → fuse → clean → normal → OUT
```

```jsonc
"postprocess": [
  {"type": "fuse"},                                          // 合并共点
  {"type": "clean"},                                         // 移除非流形边 + 退化面
  {"type": "normal", "params": {"cuspangle": 60}}            // 顶点法线
]
```

| 步骤 | 用途 | 何时需要 |
|---|---|---|
| `fuse` | 合并共点（共面箱体在 merge 后会有重复顶点） | 多箱体资产（车辆、建筑、家具）默认加 |
| `clean` | 移除熔合后遗留的非流形边和退化面 | fuse 后 |
| `normal` | 为着色设置顶点法线（`cuspangle: 60`） | 总是需要 |

**何时省略 fuse+clean：** 仅限真正的单件资产（一个参数化曲面、一个分形），无相邻共面几何体。

## 微重复（辐条/链条/砖块）— 用 variant scatter 或 native_chain + CTP

**旧文档曾推荐用 `houdini_run_python_sandbox(network_mode=true)` 的 Workspace 模式做微重复——这个建议已作废。** raw network_mode 不烘焙 `edini_world_axis`，**无法通过 G3 commit 闸门**（见 `procedural-modeling` 的强制门控）。

微重复现在有两种**闸门安全**的做法：

1. **单一模板 + 多锚点**（重复件样式相同，如 6 个相同辐条）：在 recipe 的一个组件上声明 N 个 `anchors`，builder 自动 CTP。这是 `build_procedural_asset` 的标准用法。

2. **变体散布**（重复件有多种样式，如 3 种窗户随机分布）：用 `houdini_variant_scatter`（独立的构建工具，它烘焙轴、能过 G3）。详见 `declarative-builder.md` 的 Variant Scatter 章节。

**决策规则：**
- 样式单一、数量已知 → `build_procedural_asset` + 多锚点
- 样式多样、随机分布 → `houdini_variant_scatter`
- **绝不**用 raw network_mode 做多组件/微重复——它会建出一个无法 commit 的资产

## 组装结果解读（build_procedural_asset result）

```jsonc
{
  "success": true,
  "output_node": "/obj/sandbox/OUT",
  "structure_advisory": {"is_monolithic": false, "passed": true},  // builder 的 CTP 网络天然模块化，应总为 passed
  "construction_axis_summary": {...},   // 每组件烘焙的世界轴
  "defaulted_axes": {...},              // 用了推断/兜底轴的组件（审查）
  "component_id_check": {"missing": [], "ok": [...]}
}
```

如果 `structure_advisory.is_monolithic` 为 true，说明 recipe 里只有一个 Python 组件吐了所有几何（没用 CTP）——这违反模块化原则，重新分解组件。

## 完成后

- **构建成功（`success: true`）** → 返回 `procedural-modeling` 路由，进入**验证**阶段
- **某组件质量不对**（几何缺件、方向错）→ 加载 `component-building` skill 修 recipe 重建
- **想调整锚点布局/后处理** → 改 recipe 对应字段，重新 `build_procedural_asset`
