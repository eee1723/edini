---
name: verification
description: Use when components are built and assembled, before committing. Covers the two-layer verification protocol (health + orientation + inventory), debug discipline, and when to stop rebuilding.
license: MIT
---

# Verification

运行验证协议。两层：便宜、权威的检查优先。

## 两层协议

| 层 | 工具 | 检查内容 | 权威性 | 何时运行 |
|---|---|---|---|---|
| **1. 几何健康** | `inspect_health` | orphan_points, open_curves（阻塞）；degenerate, nonmanifold, open boundary（建议） | **阻塞项必须通过** | Phase B 每个组件；Phase C 组装后 |
| **2a. 方向** | `verify_orientation` | 轴方向错误、组件翻转、轴未对齐 | **门禁 — 提交时拒绝** | Phase B 每个组件；Phase C 组装后 |
| **2b. 库存** | `geometry_inventory` | 存在哪些 component_id、prim 数量 + 相对大小 | **“它存在吗？”的权威来源** | Phase C 组装后 |

## 两层健康检查

`inspect_health` 报告 `overall_ok`，仅由阻塞检查决定：

- **阻塞（`overall_ok` 门禁 + 提交）：** `orphan_points`，`open_curves`。这些是明确的缺陷 — 总是修复它们。
- **建议（报告，永不阻塞）：** `degenerate_prims`，`nonmanifold_edges`，`open_boundary_edges`，`coincident_points`。
  **开放边界边在开放曲面（地形、面板）上是预期的** — 不要为了归零而重建。
  **非流形边经常出现在 Sweep 管材连接处** — 建议级别，在自行车车架上是正常的。

## 方向验证

每个 `orientation_assert` 都得到检查：

```jsonc
{"component_id": "rim_front", "kind": "radial",
 "construction_axis": "Y", "expected_axis": "Z", "tolerance_deg": 10}
```

- `radial` — 围绕轴旋转对称（轮子、齿轮）。`expected_axis` = 轴方向。
- `elongated` — 长/细（管、杆）。`expected_axis` = 长轴。
- `planar` — 扁平（面板、板、座垫）。`expected_axis` = 表面法线。`signed: true` 当方向重要时。
- `construction_axis` — 局部空间轴（X/Y/Z/-X/-Y/-Z）。**单路径设计后为必填**
  （A8 检查）—— PCA 估计路径已移除（它对细长圆柱体误判 → hub 90° bug），
  所以每个 assert 都必须声明轴。声明后检查是**确定性的**（基于 builder 烘焙的
  `edini_world_axis`，非估计）。空 `orientation_asserts` 数组 = 显式跳过。

## verification_receipt —— 汇报必须引用它（spec §5.2）

`commit_sandbox` 成功后返回 `verification_receipt`，一个防篡改的 JSON 对象：

```jsonc
{"passed": true,
 "orientation": {"passed": 2, "failed": 0, "total": 2, "failures": []},
 "health": {"overall_ok": true, "hard_errors_count": 0, "soft_warnings": 3,
            "blocking_checks": [...], "advisory_checks": [...]},
 "components_detected": ["frame", "wheel_front", "wheel_rear"],
 "construction_axes_baked": true, "defaulted_axes": {"seat": "Y(fallback)"},
 "timestamp": "2026-06-22T17:30:00"}
```

**汇报规则**：
- **逐字段引用 receipt，不要自己计数几何** —— receipt 是工具返回的 JSON，
  agent 无法改写它的数字，只能选择省略某个失败项（用户仍能在工具结果里看到）。
- **`passed: false` 必须如实报告** —— 即使 `passed=8/total=9`，也要报告那 1 个失败。
  谎报 7/7 为全过正是单路径设计要根治的失败模式（road_bike 会话）。
- **`defaulted_axes` 非空时说明** —— 这些组件用了推断/兜底轴（Y fallback），
  agent 应说明哪些组件的轴是推断的、是否需要显式声明。

## 库存核对

`geometry_inventory` 返回每个 `component_id` 的 prim 数量、点数量和相对大小。
**库存比像素更可信** —— 当 `geometry_inventory` 说一个组件存在（`prim_count > 0`）时，它就存在；不要因为截图看起来不对就重建。

## 调试纪律

| 规则 | 原因 |
|---|---|
| **针对性修复** — 每轮只处理一个特定的 `component_id` 或一个特定的阻塞健康检查项 | 节省上下文，隔离故障 |
| **同一缺陷存活 2 轮 → 切换方案** | 相同的方法不会在第 3 次突然奏效 |
| **3 轮总计后 → 询问用户** | 避免在错误路径上螺旋 |
| **从不在没有命名缺陷的情况下重建整个资产** | 全量重建会丢失诊断状态 |
| **库存说存在 → 相信库存** | 视觉模型对小/薄组件不可靠 |

## 图像存档

`capture_review` 是**仅存档**步骤 — 在提交前保存一次截图以备记录。
**绝不用它来驱动重建循环。** 不要用视觉模型判断它。不要从截图“看到”的缺失组件来重建。
