---
name: component-building
description: Use when building individual components with build_component. Covers backend red lines, VEX code rules, prebuilt templates usage, build result interpretation, common cook failures, and repair discipline.
license: MIT
---

# Component Building

逐组件构建。每个组件独立 Cook → 独立验证 → 缓存通过结果。Phase B 管道。

## ⛔ Backend 红线（违反必出错）

| 几何类型 | 必须用的 backend | 禁止 |
|---|---|---|
| **管 / 杆 / 车把**（沿路径的圆柱体） | **vex_skeleton + sweep::2.0** | Python add_tube() |
| **截面挤出**（柱/梁/块） | **vex_skeleton + polyextrude::2.0** | Python 手写 box |
| **简单几何体**（hub/cylinder/pedal/brake） | **native_chain** | Python createPolygon 循环 |
| **重复件 ≥10**（辐条/砖块/链条） | **native_chain 模板 + CTP** | Python for 循环 |
| **复杂有机曲面**（座垫/地形/分形） | python SOP（仅无 SOP 等效项时） | — |

## VEX 代码规范

```vex
// ✅ 正确：Detail 模式，ch() 读参数，只生成骨架
float r = chf("radius");       // 纯字符串，无 %
int n = chi("sides");
vector pts[] = ...;
int pt = addpoint(0, pos);
int prim = addprim(0, "polyline");

// ❌ 错误
float r = chf("%radius%");     // Python 风格的 % — VEX 不支持
addprim(0, "poly");            // 禁止手写 polygon — 封闭性留给 Sweep
```

**判断流程：**
1. vexlib 有现成函数？ → 直接用 `make_polyline()` 等
2. vexlib 没有？ → 参照 vexlib 代码风格自己写 Detail 模式 VEX
3. 自定义 VEX 只生成多段线 — 绝不手写 polygon

## 预构建模板使用

从 [prebuilt-templates.md](scripts/prebuilt-templates.md) 复制 `native_chain` 模板。
**复制前必须验证 H21 参数名：** 模板中的 `attribcreate` 用 `class1: "primitive"`（不是 `"prim"`）。
`torus` 用 `radscale`（不是 `rad`）。如有疑问，运行 `query_parms("类型名")`。

## 构建结果解读（ComponentBuildResult）

```jsonc
{
  "component_id": "frame_top",
  "status": "passed",           // passed | failed
  "cook_time_ms": 120,
  "geometry": {                 // 非空 → 组件存在
    "point_count": 12, "prim_count": 8, "bounds": {...}
  },
  "health": {                   // orphan_points=0, open_curves=0 → 通过
    "orphan_points": 0, "open_curves": 0
  },
  "component_id_confirmed": true,  // ⚠️ 必须为 true — 否则提交失败
  "error": null
}
```

**关键检查：`component_id_confirmed`** — 如果为 false，几何体存在但标记缺失。修复 recipe 并重建，不要用原始 Python 打补丁。

## 常见 Cook 失败模式

| 症状 | 原因 | 修复 |
|---|---|---|
| `B1_COOK_FAILED` | VEX 语法错误、无效 parm 值 | 检查 VEX 代码，用 `query_parms` 验证 parm 名 |
| `B1_EMPTY_GEO` | wrangle 没生成骨架 | 检查 VEX 逻辑，骨架路径是否有效 |
| `component_id_confirmed: false` | attribcreate 参数错误 | 验证 `class1: "primitive"` `type1: "string"` |
| `Parm 'X' not found` | H21 参数名不同 | 在目录中查找正确名称 |
| `Invalid node type name` | 节点类型不存在 | `transform`→`xform`, `polybevel`→`polybevel::3.0` |

## 修复纪律

- **每轮修复只针对一个具体的 component_id**
- **同一缺陷存活 2 轮 → 换方案**（切换 backend 或移到 Workspace）
- **3 轮后 → 停止并询问用户** — 不要尝试第 4 次相同修复
- **重建设置 `force=true`** 以绕过缓存
