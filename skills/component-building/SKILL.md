---
name: component-building
description: Use when build_procedural_asset fails or produces a bad component. Covers backend red lines, VEX code rules, prebuilt templates, reading the build result + error codes (A8/A9/cook/G2), and repair discipline. The build itself is one tool call — this skill is for fixing the recipe when it goes wrong.
license: MIT
---

# Component Building

`build_procedural_asset(recipe)` 是**唯一**的多组件构建入口——它内部串联 validate → cook → 烘焙 → 组装，一步完成。**你不再逐组件构建或手动接线。** 这个 skill 的职责是：当 `build_procedural_asset` 报错或某个组件质量不对时，如何**读错误码、定位是 recipe 哪个字段错了、修 recipe 并重建**。

## ⛔ Backend 红线（写在 recipe 里的 `backend` 字段，违反必出错）

| 几何类型 | 必须用的 backend | 禁止 |
|---|---|---|
| **管 / 杆 / 车把**（沿路径的圆柱体） | **vex_skeleton + sweep::2.0** | Python add_tube() |
| **截面挤出**（柱/梁/块） | **vex_skeleton + polyextrude::2.0** | Python 手写 box |
| **简单几何体**（hub/cylinder/pedal/brake） | **native_chain** | Python createPolygon 循环 |
| **重复件 ≥2**（辐条/砖块/链条） | **native_chain 模板 + CTP**（在 recipe 的 anchors 里声明） | Python for 循环 |
| **复杂有机曲面**（座垫/地形/分形） | python SOP（仅无 SOP 等效项时） | — |

> 重复阈值统一为 **≥2**（与 `edini-brainstorm` 一致）：任何重复 2 次以上的件都走 native_chain 模板 + Copy-to-Points，不要在 Python 里写 for 循环。

## VEX 代码规范（`vex_skeleton` backend 的 `code`/`section_code` 字段）

```vex
// ✅ 正确：Detail 模式，ch() 读参数，只生成骨架
float r = chf("radius");       // 纯字符串，无 %
int n = chi("sides");
vector pts[] = ...;
int pt = addpoint(0, pos);
int prim = addprim(0, "polyline");

// ❌ 错误
float r = chf("%radius%");     // Python 风格的 % — VEX 不支持
addprim(0, "poly");            // 禁止手写 polygon — 封闭性留给 Sweep/PolyExtrude
```

**判断流程：**
1. vexlib 有现成函数？ → 直接用 `make_polyline()` 等
2. vexlib 没有？ → 参照 vexlib 代码风格自己写 Detail 模式 VEX
3. 自定义 VEX 只生成多段线 — 绝不手写 polygon（PolyExtrude 需要 `"poly"` 面，但那由 form_node 的挤出产生，不是你在骨架 wrangle 里手写）

## 预构建模板使用

从 [prebuilt-templates.md](../procedural-modeling/scripts/prebuilt-templates.md) 复制 `native_chain` 模板。
**复制前必须验证 H21 参数名：** 模板中的 `attribcreate` 用 `class1: "primitive"`（不是 `"prim"`）。
`torus` 用 `radscale`（不是 `rad`）。如有疑问，运行 `query_parms("类型名")`。

## 构建结果解读（build_procedural_asset result）

```jsonc
{
  "success": true,                // false = 构建失败，看 error + phase_a_validation
  "phase_a_validation": {...},    // G1 验证闸结果（A1-A9）
  "component_id_check": {"missing": [...], "ok": [...]},
  "orientation_check": {...},     // 方向预览（advisory）
  "construction_axis_summary": {...},  // 每个组件烘焙的世界轴
  "defaulted_axes": {...},        // 用了推断/兜底轴的组件
  "diagnostics": {...}
}
```

**关键检查：**
- `success: false` → 读 `error` 字段定位失败阶段（见下表）。
- `component_id_check.missing` 非空 → 某组件没标记 `@component_id`。修组件 `code`，重建。
- `defaulted_axes` 非空 → 某些组件的轴是推断/兜底的（非显式声明）。**审查**：如果推断轴不对，在组件或 assert 上显式声明 `construction_axis`。

## 常见失败模式（读 `error` 字段定位修复）

| `error` 含 | 阶段 | 原因 | 修复 |
|---|---|---|---|
| `A8_MISSING_CONSTRUCTION_AXIS` | G1 验证 | orientation_assert 没声明 construction_axis | 在该 assert 加 `construction_axis`（X/Y/Z/-X/-Y/-Z）；要跳过方向检查就传空数组 |
| `A8_BAD_CONSTRUCTION_AXIS` | G1 验证 | construction_axis 值非法 | 改成 X/Y/Z/-X/-Y/-Z 之一 |
| `A9_HARDCODED_SIZE` | G1 验证 | 组件 code 里有 `wheelbase = 1.0` 这类硬编码尺寸 | 把该变量加进 `recipe.params`（成为真参数）或组件 `reads`（局部别名） |
| `B1_COOK_FAILED` / cook traceback | 构建 | VEX 语法错误、无效 parm 值、组件 code 异常 | 读 traceback，检查 VEX/code，用 `query_parms` 验证 parm 名 |
| `B1_EMPTY_GEO` | 构建 | wrangle 没生成骨架 | 检查 VEX 逻辑，骨架路径是否有效 |
| `component_id_confirmed: false` | 构建 | attribcreate 参数错误 / 组件 code 没标记 | 验证 `class1: "primitive"` `type1: "string"`；确认 code 里 `setAttribValue("component_id", ...)` |
| `G2_NOT_BAKED` | G2 烘焙闸 | 几何体未烘焙 edini_world_axis | 正常 recipe 不应出现——这表示 builder bug，报告它；**不要**自己补轴 |
| `Parm 'X' not found` | 构建 | H21 参数名不同 | 在 parm_catalog 查正确名称 |
| `Invalid node type name` | 构建 | 节点类型不存在 | `transform`→`xform`, `polybevel`→`polybevel::3.0` |

## 修复纪律

- **每轮修复只针对一个具体的 component_id 或一个具体的 error code**
- **同一缺陷存活 2 轮 → 换方案**（切换 backend，或重新审视该组件的构造方式）
- **3 轮后 → 停止并询问用户** — 不要尝试第 4 次相同修复
- **重建 = 重新调 `build_procedural_asset(recipe)`**（用修过的 recipe）——没有 `force` 参数，每次都是全新构建

## 完成后

- **构建成功（`success: true`，`component_id_check.missing` 为空）** → 返回 `procedural-modeling` 路由，进入**验证**阶段（加载 `verification` skill，或直接调 `verify_orientation`/`inspect_geometry_health`）
- **反复失败（3 轮）** → 停止，向用户报告失败的 error code + 已尝试的方案，询问方向
