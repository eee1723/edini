# Edini 三阶段管道架构 — 设计文档

**状态：** 待审核
**日期：** 2026-06-20
**范围：** Skills + Tools + Harness 全栈重设计

---

## 1. 动机 — 当前架构的五个根本缺陷

所有已知问题（12 项风险 + 参数依赖性断裂）根源于五个架构错误：

| # | 缺陷 | 症状 |
|---|---|---|
| D1 | **验证与执行交织** | parm名错误在 Cook 阶段才暴露（构建 1/2/3/4 全部在 Cook 时失败），4.9M token 上下文膨胀 |
| D2 | **食谱是原子单位** | 20 个组件生死与共，一个 parm 拼写错误 → 全部重来 |
| D3 | **锚点位置在构建时烘焙** | `position_expr` 在构建时计算为固定坐标，此后参数变化不联动 → 轮子穿进车架 |
| D4 | **参数之间无依赖关系** | 系统不知道 `bb_height` 由 `wheel_radius - bb_drop` 派生，改一个参数后其他组件停在原位 |
| D5 | **工具面暴露危险路径** | `houdini_run_python` 仍然可用，Agent 在压力下使用 4 次非沙箱操作 |

---

## 2. 核心原则

| 原则 | 含义 |
|---|---|
| **验证前移** | 语法/语义错误在 Phase A 全部捕获，不进 Houdini |
| **组件作为工作单元** | 逐个构建、独立验证、独立缓存 |
| **参数活在 Houdini 里** | 锚点是活的通道引用，不是死坐标 |
| **依赖显式声明** | 派生参数、约束条件全部写在 Recipe 里 |
| **工具面收窄** | 只暴露正确的路径，危险工具物理删除 |

---

## 3. 管道总览

```
RECIPE ──→ Phase A: 纯验证 ──→ Phase B: 逐组件构建 ──→ Phase C: 组装→测试→提交
             零 Houdini 操作      每个组件独立沙箱          已验证组件的确定性组装

              ┌─────────────────────────────────────────────┐
              │          Param Dependency Graph             │
              │  (primary / derived / constrained 交织验证) │
              │         ┌──────────────────────┐            │
              │         │  Auto Catalog (JSON) │            │
              │         │  Houdini启动时自动生成│            │
              │         └──────────────────────┘            │
              └─────────────────────────────────────────────┘
```

三个阶段的产物是**独立可检查的**：
- Phase A 产出 → `validation_report.json`（通过了就保证 Cook 不会因 parm/类型/VEX 语法失败）
- Phase B 产出 → `component_cache/{id}/`（每个组件几何体 + 验证报告）
- Phase C 产出 → 提交到场景的最终资产 + 参数边界测试报告

---

## 4. Phase A — 纯验证（零 Houdini 代价）

### 4.1 设计目标

Phase A 不创建节点、不 Cook、不调用 Houdini HOM。所有验证都是纯数据操作。

### 4.2 验证项目（按执行顺序）

#### A1. Schema 校验
验证 Recipe JSON 的结构完整性：
- 顶层字段存在且类型正确
- `components[]` 中每个组件有合法的 `id`、`backend`、`code`/`nodes`
- `params{}` 中每个参数有合法的 `kind`、`default`、`min`/`max`

#### A2. 参数目录交叉验证
对每个组件的每条 SOP 参数设置，交叉验证参数名在自动生成的 H21 目录中存在：

```
输入：
  component["rim"].nodes[0]: {"type": "torus", "params": {"radscale": 0.08, "type": "poly"}}

验证：
  catalog["Sop"]["torus"]["parms"] 中 "radscale" ✓
  catalog["Sop"]["torus"]["parms"] 中 "type" ✓, 菜单值 "poly" ✓

错误输出：
  {
    "stage": "A2_PARAM_NAME",
    "component": "rim",
    "node_index": 0,
    "node_type": "torus",
    "bad_parm": "rad",
    "suggestion": "torus H21 has 'radscale' (float), not 'rad'. Did you mean radscale?",
    "valid_parms": ["radscale", "rows", "cols", "type", "orient", "surftype", ...]
  }
```

**参数目录来源：** 系统启动时调用 `houdini_dump_parm_catalog()` 扫描 Houdini 安装目录下的所有 SOP 类型，生成 `parm-catalog.json`。Phase A 用这个文件作为 ground truth。

#### A3. 节点类型验证
验证所有 `form_node.type` 和 `native_chain.nodes[].type` 在 Houdini 中存在：

```
❌ "type": "transform" → 不存在 → 建议: "xform"
❌ "type": "polybevel"  → 存在但不精确 → 建议: "polybevel::3.0"
```

目录中包含别名映射：
```json
{
  "aliases": {
    "transform": "xform",
    "polybevel": "polybevel::3.0"
  }
}
```

#### A4. VEX 基础 Lint
在 Chef 之外做正则级别的语法扫描：

| 规则 | 检测模式 | 严重性 |
|---|---|---|
| Python 风格 `%` 格式化 | `chf("%`)` `chf("%s")` | **阻塞** |
| 手写 Polygon | `addprim(0, "poly")` 或 `addprim(geohandle, "poly")` | **阻塞** |
| 非 Detail 模式标记 | 代码中无 `// Run Over: Detail` 注释且包含 `addpoint` | **告警** |
| 非法 include 路径 | `#include` 后的路径不在 vexlib 白名单中 | **告警** |
| `ch()` 引用未声明参数 | 正则提取所有 `chf("name")`，交叉验证 name 在 `params` 或 `reads` 中 | **阻塞** |

> 注意：A4 是正则级别的**启发式检查**，不能替代 VEX 编译器。它的目标是捕获 90% 的常见错误，不是 100%。

#### A5. 构造轴一致性（已有，保留）
验证 `construction_axis` → `anchor.orient` → `expected_axis` 三者一致。已有实现，从 harness.py:`_check_construction_axis_consistency` 迁移到验证阶段。

#### A6. 参数依赖图验证（新增）

验证四件事：

```
✅ DAG 无循环    — 派生参数 from 表达式形成有向无环图
✅ 无悬空引用    — from 表达式中引用的所有参数名都已声明
✅ 无孤立主控    — 每个 primary 参数至少被一个组件 reads 或一个派生参数 from 引用
⚠️ 约束可达性   — constrained 参数的 check 表达式在默认值下全部通过
⚠️ 范围连续性   — min/max 范围内的离散采样点全部通过约束（如果不通过则告警）
```

**DAG 实现：**
```
_param_dag = {
  "bb_height":      {"depends_on": ["wheel_radius", "bb_drop"]},
  "fork_length":    {"depends_on": ["wheel_radius"]},
  "chainstay_eff":  {"depends_on": ["wheel_radius", "bb_drop", "seat_angle"]},
  "wheel_radius":   {"depends_on": []},    // primary
  "bb_drop":        {"depends_on": []},    // constrained
  "seat_angle":     {"depends_on": []},    // primary
}
```

用 Kahn 的拓扑排序算法检测循环。

#### A7. 验证报告

```jsonc
{
  "passed": true,                          // 全部 A1-A6 通过
  "stages": {
    "A1_schema":         {"passed": true},
    "A2_param_names":    {"passed": true, "warnings": []},
    "A3_node_types":     {"passed": true},
    "A4_vex_lint":       {"passed": true, "warnings": ["frame_top: VEX codes uses addpoint without Detail marker comment"]},
    "A5_construction":   {"passed": true},
    "A6_dependency":     {"passed": true, "param_count": 17, "primary": 8, "derived": 5, "constrained": 4}
  },
  "dependency_graph": { /* DAG 数据，供 Phase C 使用 */ },
  "component_manifest": [ /* 所有组件的清单，供 Phase B 使用 */ ]
}
```

---

## 5. Phase B — 逐组件构建

### 5.1 设计目标

每个组件在**独立沙箱**中构建，Cook 后立即验证。通过的组件缓存，失败的组件只影响自己。

### 5.2 工具接口

```
build_component({
  "recipe_path": "...",                // 完整 Recipe（读取 param 定义）
  "component_id": "frame_top",        // 本次只构建这一个
  "sandbox_root": "...",              // 所有组件共享同一个 sandbox root
  "param_overrides": {}               // 可选：测试时覆盖参数值
}) → ComponentBuildResult
```

### 5.3 构建流程（每个组件）

```
1. 在 sandbox root 下创建此组件的子网络
2. 根据 backend 类型创建节点链：
   - native_chain: 创建 SOP 链 + attribcreate
   - vex_skeleton: 创建 attribwrangle(注入 VEX) + form_node(sweep/polyextrude) + attribcreate
   - python:       创建 python SOP(注入代码)
3. Cook 组件
4. 验证：
   a. 组件 Cook 成功（无异常）
   b. 几何体非空（point_count > 0）
   c. @component_id prim 属性存在且值正确
   d. 健康检查（orphan_points=0, open_curves=0）
5. 缓存组件几何体 + 验证结果到 component_cache/{component_id}/
6. 返回 ComponentBuildResult
```

### 5.4 构建结果

```jsonc
{
  "component_id": "frame_top",
  "status": "passed",                    // passed | failed
  "cook_time_ms": 120,
  "geometry": {
    "point_count": 12,
    "prim_count": 8,
    "vertex_count": 56,
    "bounds": {"min": [...], "max": [...], "size": [...]}
  },
  "health": {
    "orphan_points": 0,
    "open_curves": 0,
    "nonmanifold_edges": 0,
    "open_boundary_edges": 0,
    "degenerate_prims": 0
  },
  "component_id_confirmed": true,
  "cache_path": "component_cache/frame_top/",
  "error": null                           // 失败时填充
}
```

### 5.5 增量重构建

Agent 修改了组件 3 的代码：
```
build_component(component_id="frame_down")  → 只 Cook frame_down，其他 19 个组件不动
```

Phase B 维护 `component_cache/.manifest.json` 追踪每个组件的状态：
```jsonc
{
  "frame_top":       {"status": "passed", "hash": "a1b2c3"},
  "frame_down":      {"status": "failed", "error": "A2: parm 'rad' not found"},
  "frame_seat":      {"status": "pending"},      // 还没构建
  "rim":             {"status": "passed", "hash": "d4e5f6"},
}
```

`assemble_components`（Phase C）只接受 `status: "passed"` 的组件。

### 5.6 错误反馈精度

每个组件的错误独立报告：

```
❌ frame_down: A2_PARAM_NAME — torus 没有 parm "rad"，建议 "radscale"
❌ chainring_outer: A5_CONSTRUCTION — construction_axis Y 与 expected_axis Z 偏离 90°
❌ frame_seat: COOK_FAILED — VEX 语法错误 line 4: 无效的 chf("...") 调用
```

而不是当前的：
```
❌ 5 个组件全部 Cook 失败 + 2 个节点类型无效 — 整个构建中止
```

---

## 6. Phase C — 组装 → 测试 → 提交

### 6.1 设计目标

取所有 `status: "passed"` 的组件，按 Recipe 中的组装规则连接，在参数边界上测试，提交。

### 6.2 组装（`assemble_components`）

```
assemble_components({
  "recipe_path": "...",
  "sandbox_root": "...",
}) → AssemblyResult
```

组装逻辑：

```
1. 从 component_cache 加载所有 passed 组件的几何体
2. 对于每个有锚点的组件：
   - 创建 scatter 点（锚点位置是活的通道引用，不是固定坐标）
   - 设置 @orient / @pscale
   - 创建 CTP 节点连接组件几何体 → scatter 点
3. 无锚点的组件 → 直接连到 Merge
4. 应用后处理链（fuse → clean → normal）
5. 创建 OUT null 节点
```

### 6.3 锚点实时计算（核心改动）

旧设计：
```jsonc
// 构建时烘焙。wheel_radius 改了 → 这个坐标还是旧值
{"position_expr": ["wheelbase/2", "wheel_radius", "0"]}
```

新设计：
```jsonc
// 活的 Houdini 通道引用。wheel_radius 改了 → 锚点自动跟着动
{
  "anchor_id": "front_wheel",
  "target_component": "frame_fork",      // 锚点挂载到哪个组件
  "target_point": "dropout",             // 该组件的哪个命名点
  "orient": {"inherit": "target_point"}  // 方向继承挂载点的方向
}
```

实现方式：
- 每个组件的输出几何体上，关键连接点标记为命名的 point group（`dropout_front`, `dropout_rear`, `bb_center`, `head_top`, `seat_cluster` 等）
- 组件在 Recipe 中声明它暴露哪些命名点：
  ```jsonc
  {
    "id": "frame_fork",
    "exposes": ["dropout", "crown", "steerer_top"],  // 本组件暴露的连接点
    "code": "..."
  }
  ```
- 锚点声明引用目标组件的命名点 → Houdini 自动追踪通道依赖 → 参数变化时整个网络重新 Cook

### 6.4 参数边界测试（`houdini_test_params`）

```
houdini_test_params({
  "sandbox_root": "...",
  "scenarios": [
    {"label": "default",            "params": {}},
    {"label": "min_wheel",          "params": {"wheel_radius": 0.30}},
    {"label": "max_wheel",          "params": {"wheel_radius": 0.38}},
    {"label": "min_frame",          "params": {"frame_scale": 0.85}},
    {"label": "max_frame",          "params": {"frame_scale": 1.15}},
    {"label": "extreme_combo_A",    "params": {"wheel_radius": 0.30, "frame_scale": 0.85}},
    {"label": "extreme_combo_B",    "params": {"wheel_radius": 0.38, "frame_scale": 1.15}},
    {"label": "max_tire_min_frame", "params": {"tire_width": 0.032, "frame_scale": 0.85}},
  ],
  "checks": ["health", "orientation", "intersection", "constraint"]
}) → ParamTestReport
```

每个场景：
1. 设置参数值
2. 递归 Cook 整个网络（包括派生参数自动更新）
3. 对 OUT 运行健康检查
4. 对 OUT 运行方向验证
5. **穿插检测**：计算每个 `component_id` 的 AABB，标记异常重叠对（如 `tire_front` 与 `frame_down` 的重叠比例 > 阈值）
6. **约束验证**：评估所有 `constrained` 参数的 `check` 表达式

**穿插检测算法（轻量）：**
```
对每对 component_id (A, B)：
  overlap_volume = AABB(A) ∩ AABB(B)
  if overlap_volume / min(volume(A), volume(B)) > 0.05：
    warn("component A and B overlap {percent}%")
```
这不能替代完整的碰撞检测，但能捕获最明显的穿插问题。

### 6.5 提交（`commit_sandbox`）

```
commit_sandbox({
  "sandbox_root": "...",
  "final_name": "road_bicycle",
  "param_test_report": test_report,      // 必须提供
}) → CommitResult
```

提交前门禁：
1. ✅ 所有组件 `status: "passed"`
2. ✅ 组装成功
3. ✅ 参数测试报告存在且关键检查通过：
   - `health.all_scenarios_passed` = true
   - `orientation.all_scenarios_passed` = true
   - `intersection.blocking_count` = 0（告警级别的不阻塞提交）
   - `constraint.all_scenarios_satisfied` = true
4. ❌ 任何一项未通过 → 提交拒绝，返回具体的失败场景和原因

---

## 7. 工具面重设计

### 7.1 工具映射

| 当前工具 | 新工具 | 说明 |
|---|---|---|
| `houdini_build_procedural_asset` | → | 拆分为 3 个工具 |
| — | **`validate_recipe`** | **新增** → Phase A 全部验证 |
| — | **`build_component`** | **新增** → Phase B 逐组件构建 |
| — | **`assemble_components`** | **新增** → Phase C 组装 |
| `houdini_verify_orientation` | `verify_orientation` | 改名，Phase B 和 C 复用 |
| `houdini_inspect_geometry_health` | `inspect_health` | 改为 `inspect_health`，Phase B 和 C 复用 |
| `houdini_geometry_inventory` | `geometry_inventory` | Phase B 和 C 复用 |
| `houdini_commit_sandbox` | `commit_sandbox` | 增加参数测试报告参数 |
| `houdini_discard_sandbox` | `discard_sandbox` | 保留 |
| `houdini_capture_review` | `capture_review` | 保留作为存档 |
| `houdini_node_parms(type)` | `query_parms(type)` | 改名，补充自动生成目录 |
| — | **`dump_parm_catalog`** | **新增** → 启动时扫描 Houdini 安装 |
| — | **`test_params`** | **新增** → Phase C 参数边界测试 |
| `houdini_run_python` | **🗑️ 移除** | 物理删除 |
| `houdini_run_python_sandbox` | `build_component(network_mode=true)` | 统一入口 |
| `houdini_build_procedural_asset` | 拆分为 3 个工具 | 原子操作拆分为可组合阶段 |

### 7.2 工具可见性控制

工具分为三个可见性级别：

| 级别 | 工具 | 何时可用 |
|---|---|---|
| **ALWAYS** | `validate_recipe`, `query_parms`, `dump_parm_catalog` | 随时 |
| **SCOPE:sandbox** | `build_component`, `assemble_components`, `inspect_health`, `verify_orientation`, `geometry_inventory`, `capture_review` | 有活跃沙箱时 |
| **SCOPE:commit** | `commit_sandbox`, `discard_sandbox`, `test_params` | 全部验证通过后 |

`houdini_run_python` 从工具注册表中完全移除 → Agent 不可发现、不可调用。

---

## 8. 参数体系

### 8.1 三态参数

```jsonc
"params": {

  // ▬ 第一态：主控参数 ▬
  // 用户可见，直接可调。是参数空间的"自由度"。
  "wheel_radius": {
    "kind": "primary",
    "default": 0.34,   "min": 0.28,   "max": 0.40,
    "ui": {"group": "Wheels", "order": 1},
    "label": "Wheel Radius"
  },
  "frame_scale": {
    "kind": "primary",
    "default": 1.0,    "min": 0.80,   "max": 1.20,
    "ui": {"group": "Frame Geometry", "order": 1},
    "label": "Frame Scale"
  },
  "head_angle": {
    "kind": "primary",
    "default": 73.0,   "min": 70.0,   "max": 76.0,
    "ui": {"group": "Frame Geometry", "order": 3},
    "label": "Head Tube Angle"
  },
  "spoke_count": {
    "kind": "primary",
    "default": 32,     "min": 16,     "max": 48,
    "ui": {"group": "Wheels", "order": 4},
    "label": "Spokes per Wheel"
  },

  // ▬ 第二态：派生参数 ▬
  // 自动计算，用户不可编辑。确保全局一致性。
  "bb_height": {
    "kind": "derived",
    "from": "wheel_radius - bb_drop",
    "label": "BB Height (auto)"
  },
  "fork_length": {
    "kind": "derived",
    "from": "wheel_radius + 0.12 + frame_scale * 0.02",
    "label": "Fork Length (auto)"
  },
  "seat_height": {
    "kind": "derived",
    "from": "bb_height + frame_scale * 0.55 * sin(radians(seat_angle))",
    "label": "Seat Height (auto)"
  },
  "wheelbase_effective": {
    "kind": "derived",
    "from": "wheel_radius * 2 + chainstay_len + bb_drop * 0.3",
    "label": "Effective Wheelbase (auto)"
  },

  // ▬ 第三态：约束参数 ▬
  // 用户可能有范围，但有硬性约束确保结构不出错。
  "bb_drop": {
    "kind": "constrained",
    "default": 0.07,   "min": 0.06,   "max": 0.08,
    "constraints": [
      {"name": "pedal_clearance",
       "check": "(wheel_radius - bb_drop - crank_length - 0.02) > 0.05",
       "on_violation": "warn",
       "message": "Pedal may hit ground at this BB drop"},
      {"name": "tire_seat_tube_clearance",
       "check": "(chainstay_len * sin(radians(seat_angle)) + bb_drop) > (wheel_radius + tire_width + 0.01)",
       "on_violation": "block",
       "message": "Rear tire intersects seat tube"}
    ]
  },
  "tire_width": {
    "kind": "constrained",
    "default": 0.025,  "min": 0.020,  "max": 0.035,
    "constraints": [
      {"name": "fork_clearance",
       "check": "tire_width + 0.005 < fork_length * 0.15",
       "on_violation": "block",
       "message": "Tire too wide for fork"},
      {"name": "chainstay_clearance",
       "check": "tire_width + 0.005 < chainstay_len * 0.12",
       "on_violation": "block",
       "message": "Tire too wide for chainstays"}
    ]
  }
}
```

### 8.2 `from` 表达式语法

派生参数的 `from` 和约束参数的 `check` 使用同一个安全的表达式引擎。基于现有 `exprs.py`，需要新增：
- 多参数引用（原引擎支持单表达式求值，需支持参数名→值的绑定表）
- `radians(deg)` 函数（`from` 中角度计算常用）
- 表达式的依赖提取（`extract_refs("wheel_radius - bb_drop")` → `["wheel_radius", "bb_drop"]`，用于依赖图构建）

```
支持：
  - 算术: + - * / % **
  - 比较: > < >= <= == !=
  - 逻辑: and or not
  - 函数: sin cos tan abs min max sqrt radians degrees
  - 常量: pi e tau
  - 参数引用: 直接写参数名（wheel_radius, bb_drop, ...）

不支持：
  - 属性访问、文件 IO、导入、任何 Python 代码
```

### 8.3 参数 UI 组织

`ui.group` 和 `ui.order` 控制 Houdini 参数面板的布局：

```
┌─ Wheels ─────────────────┐
│ Wheel Radius    [0.34]   │  ← primary
│ Tire Width      [0.025]  │  ← constrained (有约束)
│ Spoke Count     [32]     │  ← primary
│ BB Height (auto)[0.27]   │  ← derived (灰色只读)
├─ Frame Geometry ─────────┤
│ Frame Scale     [1.0]    │
│ Head Angle      [73.0]   │
│ Seat Angle      [73.5]   │
│ BB Drop         [0.07]   │  ← constrained
│ Chainstay Len   [0.405]  │
│ ─────────────────────    │
│ Fork Length(auto)[0.48]  │  ← derived
│ Seat Height(auto)[0.72]  │  ← derived
│ Wheelbase(auto) [1.01]   │  ← derived
└──────────────────────────┘
```

---

## 9. Skill 架构重组

### 9.1 当前问题

`procedural-modeling` 技能（237 行）试图同时做：
- 后端选择决策树
- 构建路径路由
- 微重复 CTP 规则
- Builder 限制 + Workspace 回退
- 验证协议
- 预检清单
- Harness 规则

全部内容在 237 行内。结果是：什么都说了但什么都没说清楚。Agent 在 4.9M token 的会话中多次违反规则。

### 9.2 新架构：路由 + 专用技能

```
edini-brainstorm          ← 设计阶段（不变，增加组件数量限制检查）

    ↓ 用户批准设计后

procedural-modeling       ← 轻量路由（~80 行）
    │                        "这是什么类型的任务？用哪个工具？"
    │                        不包含规则——只做路由
    │
    ├─→ recipe-authoring   ← 如何写有效的 Recipe
    │     参数三态、锚点设计、约束编写
    │
    ├─→ component-building ← 如何构建单个组件
    │     backend 选择、VEX 规范、native_chain 模板
    │
    ├─→ assembly-wiring    ← 如何组装组件
    │     锚点挂载、CTP、合并、后处理
    │
    ├─→ verification       ← 验证协议
    │     两阶段（Phase B 组件 / Phase C 组装）、调试纪律
    │
    └─→ parametric-testing ← 参数化测试
          派生参数、约束、边界扫描、穿插检测
```

### 9.3 各技能内容

#### `procedural-modeling`（路由，~80 行）

```
用途：判断当前任务处于管道的哪个阶段，加载对应的专用技能。

- 有 Recipe 但没通过验证？ → 加载 recipe-authoring，修复 A1-A6 检查项
- 验证通过但组件未构建？ → 加载 component-building，逐个构建
- 组件全部通过但未组装？ → 加载 assembly-wiring
- 组装完成但未测试？ → 加载 parametric-testing
- 全部通过？ → commit
```

#### `recipe-authoring`（~150 行）

```
内容：
- 参数三态规范（primary / derived / constrained）
- 锚点设计规范（命名点、通道引用）
- 约束表达式语法
- 常见设计错误（循环依赖、悬空引用、锚点烘焙）
- 预检清单（A1-A6 全部检查项）
```

#### `component-building`（~200 行）

```
内容：
- Backend 红线（从当前 SKILL.md 迁移）
- prebuilt-templates 使用指南
- VEX 代码规范（Detail 模式、ch() 语法、禁止手写 polygon）
- 构建结果解读（ComponentBuildResult）
- 常见 Cook 失败模式（从 pitfalls.md 迁移）
- 3 轮修复限制
```

#### `assembly-wiring`（~100 行）

```
内容：
- 锚点挂载规则（命名点、方向继承）
- CTP 配置（resettargetattribs、变体）
- 后处理链（fuse → clean → normal 顺序）
- CTP 限制与 Workspace 回退
- 组装结果解读（AssemblyResult）
```

#### `verification`（~120 行）

```
内容：
- 两阶段验证（组件 / 组装）的区别
- 健康检查分级（BLOCKING vs ADVISORY）
- 方向验证（construction_axis vs PCA）
- 库存核对（component_id 存在性）
- 调试纪律（针对性修复、3 轮限制）
- 图像存档（仅存档，不驱动重建）
```

#### `parametric-testing`（~100 行）

```
内容：
- 测试场景设计（边界、组合、极端值）
- 派生参数验证（所有 from 表达式计算正确）
- 穿插检测（AABB 重叠）
- 约束验证（check 表达式评估）
- 测试报告解读
- 阻塞 vs 告警的判断标准
```

### 9.4 技能加载策略

`edini-brainstorm` 在任何 Houdini 几何任务开始时自动加载。

`procedural-modeling` 在用户批准设计后加载（通过 brainstorming Phase 6 触发）。

其他五个技能按需加载：
- Agent 调用 `validate_recipe` 失败 → 自动加载 `recipe-authoring`
- Agent 调用 `build_component` 前 → 自动加载 `component-building`
- 以此类推

---

## 10. 错误分类体系

每种错误都有标准化的格式：

```jsonc
{
  "stage": "A2_PARAM_NAME",          // 错误所属阶段
  "severity": "BLOCKING",            // BLOCKING | WARNING
  "location": {
    "component": "chainring_outer",  // 哪个组件
    "node_index": 0,                 // 该组件的第几个节点
    "node_type": "torus",            // 节点类型
    "parm_name": "rad"               // 具体哪个参数
  },
  "message": "torus H21 does not have parm 'rad'. Valid parms: radscale, rows, cols, ...",
  "fix": "Replace 'rad' with 'radscale' and set a single float value (not a vector)",
  "see": "docs/parm-catalog/Sop/torus.md"
}
```

### 完整错误码表

| 错误码 | 阶段 | 严重性 | 触发条件 |
|---|---|---|---|
| `A1_SCHEMA` | A1 | BLOCKING | Recipe JSON 结构不合法 |
| `A2_PARAM_NAME` | A2 | BLOCKING | SOP 参数名在 H21 目录中不存在 |
| `A2_PARAM_VALUE` | A2 | BLOCKING | 菜单参数值不在允许列表中（如 `class1: "prim"`） |
| `A3_NODE_TYPE` | A3 | BLOCKING | 节点类型名在 Houdini 中不存在 |
| `A4_VEX_PERCENT` | A4 | BLOCKING | VEX 代码中使用了 `%` Python 风格格式化 |
| `A4_VEX_POLY` | A4 | BLOCKING | VEX 代码中手写了 `addprim("poly")` |
| `A4_VEX_UNDEF_PARAM` | A4 | BLOCKING | VEX `ch()` 引用了未声明的参数 |
| `A4_VEX_NO_DETAIL` | A4 | WARNING | VEX 代码中有 `addpoint` 但未标记 Detail 模式 |
| `A5_CONSTRUCTION` | A5 | BLOCKING | 构造轴与预期轴不一致 |
| `A6_DAG_CYCLE` | A6 | BLOCKING | 派生参数存在循环依赖 |
| `A6_DAG_DANGLE` | A6 | BLOCKING | 派生参数 from 表达式引用了未声明的参数 |
| `A6_DAG_ORPHAN` | A6 | WARNING | primary 参数未被任何组件或派生参数使用 |
| `B1_COOK_FAILED` | B | BLOCKING | 组件 Cook 时 Houdini 抛出异常 |
| `B1_EMPTY_GEO` | B | BLOCKING | 组件 Cook 成功但几何体为空 |
| `B2_NO_COMPONENT_ID` | B | BLOCKING | 组件几何体上缺少 `@component_id` 属性 |
| `B3_HEALTH_BLOCKING` | B | BLOCKING | 组件健康检查有 BLOCKING 项未通过 |
| `C1_ASSEMBLY_FAILED` | C | BLOCKING | 组装过程失败 |
| `C2_TEST_HEALTH` | C | BLOCKING | 参数测试中健康检查未通过 |
| `C2_TEST_ORIENT` | C | BLOCKING | 参数测试中方向验证未通过 |
| `C2_TEST_INTERSECT` | C | WARNING | 参数测试中检测到组件穿插 |
| `C2_TEST_CONSTRAINT` | C | BLOCKING | 参数测试中约束检查未通过 |

---

## 11. 数据流图

```
                    ┌──────────┐
                    │  用户     │ "做一个程序化公路自行车"
                    └────┬─────┘
                         │
                    ┌────▼─────┐
                    │ brainstorm│  edini-brainstorm 技能
                    │  设计阶段  │
                    └────┬─────┘
                         │ 设计审批
                    ┌────▼─────┐
                    │  Recipe  │  Agent 编写 JSON 食谱
                    │  (.json) │
                    └────┬─────┘
                         │
              ┌──────────▼──────────┐
              │   Phase A: validate │  纯验证，零 Houdini
              │                     │
              │  A1 Schema          │
              │  A2 Parm Names   ◄──┼──── 自动生成 Parm 目录 (JSON)
              │  A3 Node Types   ◄──┤
              │  A4 VEX Lint        │
              │  A5 Construction    │
              │  A6 Dependency   ◄──┼──→ 参数 DAG
              └──────────┬──────────┘
                         │ validation_report.json (通过)
              ┌──────────▼──────────┐
              │   Phase B: build    │  逐组件构建
              │                     │
              │  for each component:│
              │    build → cook →   │
              │    health → orient  │
              │    → 缓存           │
              │                     │
              │  component_cache/   │
              │    .manifest.json   │
              └──────────┬──────────┘
                         │ 全部组件 passed
              ┌──────────▼──────────┐
              │   Phase C: assemble │  组装 + 测试 + 提交
              │                     │
              │  assemble_components│
              │     ↓               │
              │  test_params        │
              │     ↓               │
              │  commit_sandbox     │
              └──────────┬──────────┘
                         │
                    ┌────▼─────┐
                    │ /obj/... │  提交到 Houdini 场景
                    └──────────┘
```

---

## 12. 迁移路径

当前系统的向后兼容是一个约束。下面是一个分阶段迁移计划：

### Step 1: 新增，不删除（Week 1-2）

- 实现 `validate_recipe` 工具 → 现有 `build_procedural_asset` 仍可用
- 实现 `build_component` 工具 → 可以替换 `build_procedural_asset`
- 实现 `dump_parm_catalog` + 生成 `parm-catalog.json`
- Skill 重组（新文件，旧文件保留）

### Step 2: 默认切换（Week 3-4）

- `build_procedural_asset` 内部默认走新管道
- 旧的单次调用改为三个阶段：
  ```
  build_procedural_asset(recipe) 内部变为：
    → validate_recipe(recipe)
    → for each component: build_component(...)
    → assemble_components(...)
  ```
- 参数边界测试在提交前自动运行

### Step 3: 清理（Week 5）

- 移除 `houdini_run_python` 工具
- 移除旧的 SKILL.md 中冗余内容（新技能已经覆盖）
- 更新 `parm-reference.md` 为自动生成

---

## 13. 成功指标

| 指标 | 当前 | 目标 |
|---|---|---|
| 首次构建成功率 | 20%（5 次构建，1 次成功） | > 80% |
| 失败后诊断轮次 | 3-4 轮原始 Python 修复 | 1 轮（Phase A 直接报错位置） |
| 参数变化后的结构一致性 | 手动修复穿插 | 自动联动，约束阻止非法参数 |
| 单次构建 token 消耗 | 4.9M（20 个组件） | < 1.5M（20 个组件，缓存命中） |
| 危险工具暴露 | `houdini_run_python` 可用 | 物理移除 |
| 参数名验证 | Cook 时报错 | Phase A 即报错，零 Houdini 代价 |

---

## 14. 未解决问题（后续迭代）

1. **VEX 编译器级验证** — Phase A4 是启发式的。真正的 VEX 语法验证需要调用 Houdini 的 VEX 编译器（`vcc` 命令行工具），这在 Phase A 中需要一次性的轻量 Houdini 进程。
2. **分布式组件缓存** — `component_cache/` 目前是本地文件。对于团队协作，是否需要共享缓存？
3. **可视化参数 DAG** — 为用户提供一个可视化的参数依赖图，帮助理解参数之间的关系。
4. **学习引擎** — 记录每次构建失败的模式，自动改进 A2/A3 的修复建议。
5. **旧食谱自动迁移工具** — 将现有的旧格式 Recipe JSON 自动转换为新格式。

---

**文档版本：** v1.0
**作者：** Edini 系统架构
**审核状态：** 待审核
