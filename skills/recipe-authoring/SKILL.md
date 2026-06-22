---
name: recipe-authoring
description: Use when writing a procedural asset Recipe (JSON), or when validate_recipe returns errors. Covers param three-state system, anchor design, constraint expressions, and the A1-A6 pre-flight checklist.
license: MIT
---

# Recipe Authoring

编写有效的程序化资产 Recipe。管道 Phase A（纯验证）会检查这些规则中的每一项。

## 参数三态体系

```jsonc
"params": {
  // 第一态：主控参数 — 用户直接可调
  "wheel_radius": {
    "kind": "primary",
    "default": 0.34,  "min": 0.28,  "max": 0.40,
    "ui": {"group": "Wheels", "order": 1},
    "label": "Wheel Radius"
  },

  // 第二态：派生参数 — 自动计算，用户不可编辑
  "bb_height": {
    "kind": "derived",
    "from": "wheel_radius - bb_drop",
    "label": "BB Height (auto)"
  },

  // 第三态：约束参数 — 用户有范围，但有硬性约束
  "tire_width": {
    "kind": "constrained",
    "default": 0.025,  "min": 0.020,  "max": 0.035,
    "constraints": [
      {"name": "fork_clearance",
       "check": "tire_width + 0.005 < fork_length * 0.15",
       "on_violation": "block",
       "message": "Tire too wide for fork"}
    ]
  }
}
```

**`from` 和 `check` 表达式语法：**
- 算术: `+ - * / % **`
- 比较: `> < >= <= == !=`
- 逻辑: `and or not`
- 函数: `sin cos tan abs min max sqrt radians degrees`
- 常量: `pi e tau`
- 参数引用: 直接写参数名

**禁止：** 属性访问、文件 IO、导入、Python 代码。

## 锚点设计

```jsonc
// ❌ 旧：构建时烘焙 — 参数变化后失效
{"position_expr": ["wheelbase/2", "wheel_radius", "0"]}

// ✅ 新：活的通道引用 + 命名点挂载
{
  "anchor_id": "front_wheel",
  "target_component": "frame_fork",
  "target_point": "dropout",
  "orient": {"inherit": "target_point"}
}
```

组件在 Recipe 中声明暴露的命名点：
```jsonc
{"id": "frame_fork", "exposes": ["dropout", "crown", "steerer_top"]}
```

## 预检清单（Phase A 检查的全部 9 项 — G1 验证闸）

提交 Recipe 之前逐项确认：

| # | 检查 | 失败症状 |
|---|---|---|
| A1 | 结构完整 — 所有字段存在，类型正确 | `A1_SCHEMA` — Recipe 被拒绝 |
| A2 | 参数名正确 — 每个 SOP parm 名在 H21 目录中存在 | `A2_PARAM_NAME` — Cook 前即报错 |
| A3 | 节点类型正确 — `transform`→`xform`，所有类型存在 | `A3_NODE_TYPE` |
| A4 | VEX 语法有效 — 无 `%`，无 `addprim("poly")`，Detail 模式 | `A4_VEX_PERCENT` / `A4_VEX_POLY` |
| A5 | 构造轴一致 — construction_axis → orient → expected_axis 对齐 | `A5_CONSTRUCTION` |
| A6 | 依赖图健康 — 无循环、无悬空、无孤立 | `A6_DAG_CYCLE` / `A6_DAG_DANGLE` |
| A7 | backend 合理 — 管材用 vex_skeleton，简单几何用 native_chain | `A7_BACKEND_*` |
| A8 | **每个非空 orientation_assert 必须声明 construction_axis**（PCA 已移除） | `A8_MISSING_CONSTRUCTION_AXIS` / `A8_BAD_CONSTRUCTION_AXIS` |
| A9 | **组件 code 无硬编码尺寸**（`wheelbase = 1.0` 禁止；尺寸必须进 params） | `A9_HARDCODED_SIZE` |

> A8：construction_axis ∈ {X,Y,Z,-X,-Y,-Z}。空 `orientation_asserts` 数组 = 显式跳过方向检查。
> A9：逃生口 = 把变量加进 `recipe.params`（成为真参数）或组件 `reads`（局部别名）。循环计数器（`i = 0`）不受影响。

## 常见设计错误

| 错误 | 原因 | 修复 |
|---|---|---|
| 派生参数循环 | A→B→A | 打破循环：将一个设为 primary |
| 悬空引用 | `from: "x + y"` 但 y 未声明 | 声明 y 或移除引用 |
| 锚点烘焙坐标 | 用了 `position_expr` | 改用命名点 + 活通道引用 |
| 忘记声明 `reads` | 组件读 `wheel_radius` 但未在 `reads` 中列出 | 添加 `"reads": ["wheel_radius"]` |

## 完成后

- **Recipe 写好** → 调 `validate_recipe(recipe)` 自查（G1，A1-A9）
  - 全过 → 返回 `procedural-modeling` 路由，调 `build_procedural_asset(recipe)` 构建
  - 有错 → 按错误码（A1-A9）修 Recipe，重验
- **反复验证失败（3 轮）** → 停止，向用户报告失败的 stage + 已尝试的修复
