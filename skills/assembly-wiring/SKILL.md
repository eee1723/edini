---
name: assembly-wiring
description: Use when all components passed build and need to be assembled. Covers anchor mounting, CTP configuration, postprocess chains, CTP limitations, and Workspace fallback.
license: MIT
---

# Assembly & Wiring

将所有 `status: "passed"` 的组件组装成最终资产。Phase C 组装步骤。

## 锚点挂载规则

```jsonc
// 命名点锚点（推荐）— 活的通道引用
{
  "anchor_id": "front_wheel",
  "target_component": "frame_fork",   // 挂载到哪个组件
  "target_point": "dropout",          // 该组件的哪个命名点
  "orient": {"inherit": "target_point"}
}

// 静态位置（回退）
{
  "anchor_id": "rear_wheel",
  "position": [0.5, 0.34, 0],
  "orient": [0, 0, 0, 1],
  "component_id": "rim_rear"
}
```

**命名点：** 每个组件在 Recipe 中通过 `exposes` 声明其暴露的命名点。
组装引擎从目标组件的命名点读取位置 → Houdini 自动追踪通道依赖 → 参数变化时整个网络重新 Cook。

## CTP 配置

```
[组件几何体] ──→ copytopoints::2.0 ──→ idfix wrangle ──→ merge
                      ↑
[scatter 锚点] ───────┘
```

- CTP 节点必须 **按 `resettargetattribs` 按钮**
- idfix wrangle 将基值 `@component_id` 设置为模板 id；锚点覆盖特定实例的 id
- 锚点 `orient` 使用四元数 `[x, y, z, w]` — 单位四元数 = `[0,0,0,1]`

## 后处理链

**顺序很重要 — 不按这个顺序会导致几何体损坏：**

```
merge_all → fuse → clean → normal → OUT
```

| 步骤 | 用途 | 何时需要 |
|---|---|---|
| `fuse` | 合并共点（共面箱体在 merge 后会有重复顶点） | 多箱体资产（车辆、建筑、家具）必须使用 |
| `clean` | 移除熔合后遗留的非流形边和退化面 | 熔合后 |
| `normal` | 为着色设置顶点法线（`cuspangle: 60`） | 总是需要 |

**何时省略 fuse+clean：** 仅限真正的单件资产（一个参数化曲面、一个分形），无相邻共面几何体。

## CTP 限制与 Workspace 回退

Builder 为每个组件创建一个 SOP。它**不能**在单个组件内部创建带有嵌套 scatter+CTP 的子网络。

**Workspace 模式**用于单组件内部的微重复（辐条、链条）：

1. **构建主体结构** — `build_component` 处理框架和锚定组件
2. **构建微细节** — `build_component(network_mode=true)` 处理每个子组件：
   - `wheel_spokes`: 一个辐条模板 + scatter wrangle + copytopoints
   - `chain_links`: 一个链节模板 + 路径 scatter wrangle + copytopoints
3. **合并** — 手动将 workspace 输出连接到 merge 节点

**决策规则：** 如果一个组件有 ≥10 份相同小件的副本且 Recipe builder 无法表达 → **Workspace**。不要在 Builder 与 Workspace 之间来回超过 3 轮。Bicycle 辐条就是一个典型的 Workspace 场景。

## 组装结果解读

```jsonc
{
  "success": true,
  "output_node": "/obj/sandbox/OUT",
  "structure_advisory": {
    "is_monolithic": false,  // 必须为 false
  },
  "errors": []
}
```
