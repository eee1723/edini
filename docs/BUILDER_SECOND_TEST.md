# Builder 第二阶段实测：二组件 + Copy-to-Points stamping

> **前置**：第一阶段（单组件 builder_smoke）已全过。本阶段验证 mock 覆盖
> 不到的 Copy-to-Points 真实 stamping + idfix 覆盖。

## 目的（要证伪什么）
验证两件 mock 验证不了的事：
1. Copy-to-Points 把单个 wheel 模板真的 stamp 到了 anchor 位置（数量对、位置对）。
2. idfix 把每个实例的 prim `component_id` 改写成了各自的 anchor id
   （wheel_fl / wheel_rr），不是停留在模板的 "wheel"。
   —— 这一步是 verify_orientation 能按实例 PCA 的前提。

## 发给 agent 的 prompt（直接复制）

---

用 `houdini_build_procedural_asset` 工具提交下面这份 recipe，建一个二组件
资产（一个 frame 直接进 merge，一个 wheel 通过 Copy-to-Points stamp 2 份）。
**不要 commit**——先 build，把结果完整报给我。

recipe 内容：
- asset_name: "builder_stamp"
- components（2 个）：
  1. id: "frame"
     - code: 单 SOP python，生成一个 box（8 点 6 面），每个 prim tag
       `component_id="frame"`。先 addAttrib 再建几何。
     - anchors: []  （空，直接进 merge）
  2. id: "wheel"
     - code: 单 SOP python，生成一个**单位半径圆环/圆**（torus 或 circle
       都行，8-16 个点即可），每个 prim tag `component_id="wheel"`（注意：
       这里是模板 id "wheel"，不是 wheel_fl/wheel_rr——builder 的 idfix 会
       把每个实例改成各自的 anchor id）。先 addAttrib 再建几何。
     - anchors: 2 个：
       - {position: [1.5, 0.5, 0.0], orient: [0,0,0,1], pscale: 1.0, component_id: "wheel_fl"}
       - {position: [-1.5, 0.5, 0.0], orient: [0,0,0,1], pscale: 1.0, component_id: "wheel_rr"}
- 不加 orientation_asserts（本阶段只验证 stamping + idfix，不验证朝向）
- 不加 postprocess

调用 build 工具后，把结果里的这些字段**逐条**报给我：
1. `success`（应为 true）
2. `components_built`（应为 ["frame", "wheel"]）
3. `anchors_built`（应为 {"wheel": 2}）
4. `output_node`（应以 /OUT 结尾）
5. `component_id_check`——这是本次最关键的字段：
   - `missing` 应为 []（如果含 wheel_fl/wheel_rr 说明 idfix 没生效！）
   - `ok` 应包含 ["frame", "wheel_fl", "wheel_rr"]
6. `structural_checks.point_count`（frame 8 点 + 2 个 wheel 实例的点，
   应明显多于单组件）
7. `structure_advisory.passed`（应为 true）+ `modular_node_count`（应 ≥ 1，
   因为有 copytopoints 节点）

另外，build 完成后，请**额外**调用 `houdini_geometry_inventory` 工具，传
node_path = 你的 output_node 路径，把返回的 `components` 列表（每个组件的
component_id + prim_count）报给我。我要确认 OUT 上真的能看到 3 个独立
component_id：frame、wheel_fl、wheel_rr，且每个 prim_count > 0。

如果 `component_id_check.missing` 非空，或者 inventory 里看不到独立的
wheel_fl/wheel_rr，**不要重试**——把完整结果贴给我，idfix 逻辑可能需要调。

---

## 人类验收清单（agent 报完后核对）

| 检查项 | 期望 | 挂了说明 |
|---|---|---|
| `success` | true | builder 基础设施（第一阶段已验证，不应挂） |
| `anchors_built` | {"wheel": 2} | anchor 生成器没建对 |
| `component_id_check.missing` | [] | **idfix 没生效**——核心问题，需修 |
| `component_id_check.ok` 含 wheel_fl + wheel_rr | 是 | 同上 |
| `structure_advisory.modular_node_count` ≥ 1 | 是 | copytopoints 节点没被识别为 modular |
| inventory 显示 3 个独立 component_id（frame/wheel_fl/wheel_rr） | 是 | stamping 或 idfix 出问题 |
| 每个 component_id 的 prim_count > 0 | 是 | 空几何 |

## 最可能的故障点（如果挂了）
- **idfix 没生效**（最可能）：我的 `_component_id_overwrite_snippet` 用
  `total // n_anchors` 等分 prim 来定位每个实例的边界。如果真实
  Copy-to-Points 的 prim 排列不是连续等分的（比如交错、或带额外 prims），
  idfix 的索引会错位 → 部分 prim 拿到错的 id。这是 mock 验证不到的。
  修法：改用 Copy-to-Points 自带的 `copynum` 点属性（每个目标点带
  copynum），或让 idfix 读 anchor 的 @ptnum 映射，而不是按 prim 等分。

## 全过之后（第三阶段）
stamping + idfix 确认后，第三阶段加 orientation_asserts，验证完整的
build → verify_orientation → commit_sandbox 端到端（含朝向门硬关卡）。
