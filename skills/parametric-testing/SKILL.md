---
name: parametric-testing
description: Use when the asset is assembled and verified, before commit. Covers test scenario design, derived param validation, intersection detection, constraint verification, and interpreting test reports.
license: MIT
---

# Parametric Testing

参数边界测试。提交前最后一道门禁 — 验证资产在参数空间的极端值上不会损坏。

## 测试场景设计

覆盖参数空间的 4 类点：

| 类型 | 示例 | 目的 |
|---|---|---|
| **默认值** | `{}`（所有参数默认） | 基线 |
| **单参数边界** | `{"wheel_radius": 0.30}`，`{"wheel_radius": 0.38}` | 每个主控参数独立极端值 |
| **组合极端** | `{"wheel_radius": 0.30, "frame_scale": 0.85}` | 多个参数同时推向极端 |
| **冲突组合** | `{"tire_width": 0.035, "frame_scale": 0.85}` | 宽胎 + 小车架 = 可能穿插 |

工具调用：
```
test_params({
  "sandbox_root": "...",
  "scenarios": [
    {"label": "default",           "params": {}},
    {"label": "min_wheel",         "params": {"wheel_radius": 0.30}},
    {"label": "max_wheel",         "params": {"wheel_radius": 0.38}},
    {"label": "extreme_combo",     "params": {"wheel_radius": 0.30, "frame_scale": 0.85}},
  ],
  "checks": ["health", "orientation", "intersection", "constraint"]
})
```

## 每项检查的内容

### 健康
每个场景重新 Cook 后，运行 `inspect_health`。**任何阻塞项 = 测试失败。**

### 方向
重新运行 `verify_orientation`。**任何失败的组件 = 测试失败。**

### 穿插检测
对每对 `component_id` (A, B)：
```
overlap = AABB(A) ∩ AABB(B)
if overlap / min(vol(A), vol(B)) > 0.05：
  → 告警: "component A and B overlap N%"
```
**告警级别** — 不阻塞提交。但两个以上告警说明参数范围需要缩小。
限制：这是轻量 AABB 检测，不是完整碰撞检测。小部件之间的窄间隙穿透可能检测不到。

### 约束验证
评估每个 `constrained` 参数的 `check` 表达式：
```jsonc
{"name": "fork_clearance",
 "check": "tire_width + 0.005 < fork_length * 0.15",
 "on_violation": "block",
 "message": "Tire too wide for fork"}
```
- `on_violation: "block"` → **阻塞提交**
- `on_violation: "warn"` → 告警，不阻塞

## 派生参数验证

每个测试场景下，验证所有派生参数的 `from` 表达式计算无误：
- 设置主控参数 → Cook → 读取派生参数值 → 对比表达式预期值
- 偏差 > 1e-6 → 失败

## 测试报告解读

```jsonc
{
  "scenarios_tested": 7,
  "scenarios_passed": 6,        // 所有检查通过
  "scenarios_warning": 1,       // 有告警但无阻塞
  "checks": {
    "health":    {"passed": 7, "failed": 0},
    "orientation": {"passed": 7, "failed": 0},
    "intersection": {
      "warning_count": 2,       // 穿插告警
      "details": [
        {"pair": ["tire_front", "frame_down"], "overlap_pct": 12.3}
      ]
    },
    "constraint": {"passed": 7, "failed": 0}
  }
}
```

## 阻塞 vs 告警

| 结果 | 含义 | 操作 |
|---|---|---|
| 健康失败 | 几何体在极端值下退化 | **阻塞提交** — 缩小参数范围或加固几何体 |
| 方向失败 | 轴翻转 | **阻塞提交** — 检查构造轴 |
| 穿插（高重叠）| 组件碰撞 | **告警** — 检查约束表达式 |
| 约束 `block` 失败 | 硬性约束被违反 | **阻塞提交** — 缩小范围或放宽约束 |
| 约束 `warn` 失败 | 软性约束被违反 | **告警** — 向用户说明 |

## 完成后

- **所有场景全过（无 block）** → 返回 `procedural-modeling` 路由，调 `commit_sandbox`（G3 闸 + verification_receipt）。汇报逐字段引用 receipt
- **有 block 失败** → 缩小参数范围（min/max）或加固几何体；回到 `recipe-authoring` 改 params 重建
- **只有 warn** → 向用户说明告警项，仍可 commit（warn 不阻塞）
