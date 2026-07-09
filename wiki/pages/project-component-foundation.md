# 🧱 组件建模地基验证指南

> **用途**：在 Houdini GUI 里验证 Project HDA 组件建模地基（子系统 1）——subnet 组件 + 端口信息点协议 + 输入/输出脚手架 + promote 参数。
> **状态**：hython 决定性测试已全过（6 测），此为 GUI 眼见为实验证。
> **分支**：`feat/project-component-foundation`（已合并 master）。
> **最后更新**：2026-07-02

---

## 准备

1. **重启 Houdini**（让 `feat/project-component-foundation` 分支的新代码生效——旧 session 的 Python 模块已缓存）。
2. 打开 Python Shell（Windows → Python Shell），sanity check 新代码：
   ```python
   from edini.project.builder import build_project_scaffold, promote_params
   from edini.project.state import add_component
   print("新范式代码已加载")
   ```
   若报 `ImportError: cannot import name 'build_project_scaffold'`：确认仓库在 `feat/project-component-foundation` 或已合并的 master（`git branch --show-current`），再重启 Houdini。

---

## 验证 1：建脚手架（输出 + 输入，builder 自动接）

```python
from edini.project.state import empty_declaration, add_component
from edini.project.node import create_project_hda
from edini.project.builder import build_project_scaffold

core = create_project_hda(name="project_bike", goal="一辆自行车")
decl = empty_declaration("project_bike", goal="一辆自行车")
add_component(decl, "chassis", purpose="车架",
    ports_out=[
        {"index": 0, "kind": "geometry", "description": "车架几何"},
        {"index": 1, "kind": "anchors", "points": [
            {"name": "wheel_mount_fr", "role": "mount", "description": "前轮安装点"},
            {"name": "wheel_mount_rr", "role": "mount", "description": "后轮安装点"}]},
    ])
add_component(decl, "wheels", purpose="车轮",
    ports_in=[
        {"from": "chassis", "port": 1, "anchor": "wheel_mount_fr", "description": "前轮定位"},
        {"from": "chassis", "port": 1, "anchor": "wheel_mount_rr", "description": "后轮定位"},
    ])
build_project_scaffold(core, declaration=decl)
```

**你应该看到（网络视图）：**
- `/obj/project_bike`（geo 外壳）→ 进入 → `project_core`（edini::project SOP HDA）→ 进入
- core 内有 `chassis/` 和 `wheels/` 两个 **subnet**
- 进 `chassis`：4 **输出**节点（`out_geometry`/`out_anchors` null + `output_0`/`output_1` output 节点）
- 进 `wheels`：4 输出节点 **+ 2 输入节点** `in_chassis_wheel_mount_fr`、`in_chassis_wheel_mount_rr`（builder 按 `ports.in[]` 自动建！）
- 外部：`wheels` 的输入端已自动连到 `chassis` 的输出端（看 wheels 节点左侧的输入连线）

---

## 验证 2：组件消费（wheels 真的拿到 chassis 锚点）⭐ 核心

这是新范式的核心价值：组件通过端口信息点协作。

> ⚠️ **重要更新（2026-07-06，平台契约强化；2026-07-09 收窄）**：在 Project HDA 组件内手写**字面坐标** `addpoint`（如 `addpoint(0, {0.5,0,0})` / `addpoint(0, set(0.225,0,0.225))`）**会被 `project_anchor_guard` 拒绝**——字面坐标不会随参数移动。锚点请用 `project_add_anchors`（从几何 bbox 测量派生，改参数 live 重算）。注意：**计算位置**的 `addpoint`（如 `set(i-base,j-base,k-base)*step`、`@P`、`chf(...)`）是允许的——那是生成程序化几何（网格/贴纸/scatter）的正常写法，不是硬编码。

先给 chassis 造锚点（**声明式，测量几何而非硬编码**）：
```python
from edini.project.builder import add_anchors
core = hou.node("/obj/project_bike/project_core")
# 给 chassis 一些几何（box）让锚点有东西可测
chassis = core.node("chassis")
box = chassis.createNode("box", "chassis_box")
chassis.node("out_geometry").setInput(0, box)

# 锚点 = bbox 角点测量（改 box size → 锚点自动重算，永不脱节）
add_anchors(core, "chassis", [
    {"measure": "bbox_corner", "axes": "+X-Y+Z", "name": "wheel_mount_fr"},
    {"measure": "bbox_corner", "axes": "-X-Y+Z", "name": "wheel_mount_rr"},
])
```

现在 wheels 里的 `in_chassis_wheel_mount_fr` / `in_chassis_wheel_mount_rr` 应该已能拿到锚点（builder 预先连好了 indirectInputs + `filter_chassis_wheel_mount_fr` Blast 过滤器 + `__edini_anchor_clean_*` prim 净化器）。验证：
```python
wheels = hou.node("/obj/project_bike/project_core/wheels")
in_fr = wheels.node("in_chassis_wheel_mount_fr")
in_fr.cook(force=True)
print("前轮锚点数:", len(in_fr.geometry().points()))      # 应为 1
print("前轮锚点 prims:", in_fr.geometry().primCount())    # 应为 0（纯点云）
```

模拟 LLM 用锚点建模（copytopoints 盖轮子）：
```python
shape = wheels.createNode("sphere", "wheel_shape")
shape.parm("radx").set(0.5)
mount = wheels.createNode("copytopoints", "mount_wheels")
mount.setInput(0, shape)
mount.setInput(1, in_fr)  # 盖到前轮锚点
wheels.node("out_geometry").setInput(0, mount)
wheels.node("out_geometry").cook(force=True)
print("wheels 输出点数:", len(wheels.node("output_0").geometry().points()))
```

**这证明了完整组件协作链：chassis 造锚点 → wheels 消费锚点定位 → 产出几何。**
scaffold 现在在每个 in-port 上插了 `filter_*`（按 `@name` 留点）+ `__edini_anchor_clean_*`（删所有 prims），所以 copytopoints 的第二输入**永远是纯点云**，无论上游接线是否出错。

---

## 验证 3：promote（参数 live 链）

```python
from edini.project.builder import promote_params
chassis = hou.node("/obj/project_bike/project_core/chassis")
chassis.addSpareParmTuple(hou.FloatParmTemplate("length", "车长", 1))

# chassis 内部建 box，引用本组件参数 —— 注意是 ch("../length")！
# box 是 chassis 的子节点，length 在 chassis（父）上 → 父级用 ../
box = chassis.createNode("box", "demo_box")
box.parm("sizex").setExpression('ch("../length")')   # ← ../ 不是 ./
box.parm("sizey").setExpression('ch("../length")')
box.parm("sizez").setExpression('ch("../length")')
chassis.node("out_geometry").setInput(0, box)

core = hou.node("/obj/project_bike/project_core")
promote_params(core)
```

**你应该看到：** 选中 `project_core`，参数面板出现 `chassis` folder，里面有 `chassis_length`。改它 → box 大小 live 变（两层 ch 引用）。

> **路径约定（重要，将来进建模纪律 skill）：**
> | 站在哪一层 | 引用方向 | 例子 |
> |---|---|---|
> | core 参数 → 子组件 | `./<component>/<parm>` | core 的 `chassis_length` 用 `ch("./chassis/length")` |
> | 组件 subnet 内部节点 → 本组件参数 | `../<parm>` | box 用 `ch("../length")` |

两层方向相反但都对，取决于"站在哪一层看"。

---

## 验证 4：幂等

```python
from edini.project.builder import build_project_scaffold
build_project_scaffold(core)  # 再跑一次
```

chassis 里的 `make_anchors`、`demo_box`、spare parm，wheels 里的 `wheel_shape`/`mount_wheels` 都还在；`in_*` 节点和它们的下游连线保持。

---

## 组件朝向轴（2026-07-06 平台契约强化）

每个组件 subnet 内部有一条**烘焙链**（scaffold 自动建、agent 不应改）：

```
[agent geometry…] → out_geometry (null) → tag_component → __edini_axis_bake → output_0
                      (agent 连这里)      (component_id)   (edini_world_axis)
```

- **`tag_component`**（agent 可编辑）：默认 `s@component_id = "<subnet name>";`。agent 可改（加自定义属性），但**只设 component_id**——改它不会影响朝向轴。
- **`__edini_axis_bake`**（内部，`__` 前缀，锁死）：`v@edini_world_axis = {...};`。scaffold 每次重建都重设这个 snippet，`set_param` 对它的编辑会被 `internal_node_guard` 拒绝。**要改朝向轴，改声明里的 `axis` 字段，不是改这个节点。**

### 声明 per-component 朝向轴

`axis` 是组件声明的可选字段（默认 `"Y"`）。scaffold 据此烘焙 `edini_world_axis`，`verify_orientation` 读它作 ground truth：

```python
add_component(decl, "backrest", purpose="靠背，朝 +Z 的侧立面板",
    axis="Z",  # ← 侧立面板声明 Z；默认 Y 适合座面/桌腿/平躺件
    ports_out=[...])
```

常见选择：`"Y"`（默认，平躺/竖立件）、`"Z"`（侧立面：靠背、侧板）、`"X"`（横向件：车轴、横杆）。还有负向 `-X/-Y/-Z`。

> **为什么不能直接编辑 `__edini_axis_bake`？** 历史教训：会话日志里 agent 把整个 snippet 覆盖成只设 component_id，静默删了朝向轴。平台因此把轴放进一个 agent 碰不到的节点 + 每次重建重设。改轴的唯一正道是改声明的 `axis` 字段再 rebuild。

### verify_orientation 的 `construction_axis` 覆盖

`verify_orientation` 的 check 里可传 `construction_axis`（X/Y/Z/-X/-Y/-Z）做**临时覆盖**（不改烘焙值，仅本次检查生效）。用于不想 rebuild 时快速验证假设：
```python
verify_orientation(node_path, checks=[
    {"component_id": "backrest", "kind": "planar", "expected_axis": "Z",
     "construction_axis": "Z"}  # ← 覆盖 baked Y，本次按 Z 检查
])
```
返回的 check 里有 `axis_source: "override" | "baked"` 标明用了哪个来源。

---

## 常见问题

| 现象 | 原因 | 解决 |
|---|---|---|
| `ImportError: build_project_scaffold` | Houdini 加载的还是旧代码 | 确认分支/合并状态 + 重启 Houdini |
| `create_project_hda` 报类型找不到 | `edini::project` HDA 没加载 | 确认 `otls/edini_project.hda` 存在 + `HOUDINI_OTLSCAN_PATH` 指向 `otls/` |
| **`blocked_by: project_anchor_guard`** | 在 Project HDA 组件里写了**字面坐标** `addpoint`（`{0.5,0,0}` / `set(0.2,0,0.2)`） | 若是锚点 → 用 `project_add_anchors`；若是几何 → 从参数/属性算位置（`chf()`/`@P`），别写字面坐标。计算位置的 addpoint 不被拦 |
| **`blocked_by: internal_node_guard`** | 编辑了 `__edini_axis_bake` 等 `__` 前缀内部节点 | 改声明里组件的 `axis` 字段再 rebuild；不要编辑内部节点 |
| **`verify_orientation` 90° 失败但几何对** | baked `edini_world_axis` 默认 Y，但组件是 Z/X 朝向 | 在组件声明加 `"axis": "Z"`（或对应轴）rebuild；或 verify 时传 `construction_axis` 覆盖 |
| **copytopoints 只复制锚点不复制几何** | tube 等 SOP 默认 `type=prim`（单基本体）| 设 `type=poly` 或 `type=mesh`（`query_parms` 的 access_hint 会提示）|
| **in-port 收到退化面** | 上游误把真实几何接进锚点端口 | scaffold 已自动插 `__edini_anchor_clean_*` 删所有 prims；端口保证纯点云 |
| box 拿不到 length 参数 | 用了 `ch("./length")` | 改 `ch("../length")`（box 是子节点，参数在父 chassis 上）|
| promote 后参数面板没出现 | 没选中 core 节点 | 选中 `project_core`，按 `P`，找 `chassis` folder tab |

---

## 真实 API 备忘（hython 验证，2026-07-02）

- **subnet output 节点**：`createNode("output")` 建多个 output 节点形成多输出端，按 `outputidx` 映射。两个 output 节点 = 两个独立输出端口。
- **subnet 输入机制**：
  - 外部连线 `downstream.setInput(input_idx, upstream, output_idx)`（第三参数 = 上游输出端序号）
  - 内部取数 `subnet.indirectInputs()[input_idx]` 返回 `OpSubnetIndirectInput`，内部节点 `setInput(0, indirect_input)` 拿数据
  - `createNode("input")` **不存在**（`Invalid node type name`），必须用 `indirectInputs()`
- **spare parm API**：READ 用 `node.spareParms()`，WRITE 用 `node.addSpareParmTuple(tmpl, in_folder=(folder,), create_missing_folders=True)`。`spareParmGroup()`/`setSpareParmGroup()` 在真机**不存在**。

验证全部通过后，地基在 GUI 站住。任何不符预期，把 Python Shell 输出贴出来排查。

---

## agent 工具建模能力（2026-07-03 扩展）

地基物理机制（subnet/端口/锚点/连线）hython 验证通过后，**agent 还不能用地基建模** —— 因为两个关键工具能力不足。本节记录补齐的能力，这是地基能被"用起来"的决定性一步。

### 工具扩展

| 工具 | 旧能力 | 新能力 | 为什么需要 |
|---|---|---|---|
| `houdini_connect_nodes` | 2 参 `setInput(idx, node)`，只能取源节点第 0 输出端 | 加 `output_index`（3 参 `setInput(idx, node, output_idx)`），能取 subnet 的第 2+ 输出端（锚点云 out[1..n]） | 组件流水线核心：车轮消费车架锚点 = 取 chassis 的 output1 |
| `houdini_set_param` | 只支持标量字面值 | 加**向量**（`parmTuple.set([1,2,3])`，如 box size）+ **表达式**（`setExpression(ch("../length"))`，live 引用） | live 参数化是地基核心价值；promote 后两层 ch 引用要求 agent 能建表达式 |

**向后兼容**：两个工具的默认值保证旧行为不变（output_index 默认 0，标量值仍走原路径）。现有调用零回归（695 mock + 6 hython 全绿）。

### agent 建模全链路（hython 决定性验证，`TestAgentToolsHython`）

全程用工具函数（`node_utils.connect_nodes`/`set_param`/`create_node`）而非直接 `hou.node`，证明 agent 工具面足够建模：

1. `create_node(attribwrangle)` + `set_param(class, "detail")` + `set_param(snippet, VEX)` + `connect_nodes(wr → out_anchors)` —— chassis 造锚点
2. `create_node(box)` + `set_param(size, [1,1,1])` **向量** + `set_param(sizex, 'ch("../wheel_radius")')` **表达式** —— wheels 建几何（live）
3. `connect_nodes(chassis → probe, output_index=1)` **3 参** —— agent 独立取 chassis 锚点端，验证拿到 1 个锚点
4. builder 的 `in_chassis_wheel_mount`（builder 路径也用 output_index）拿到锚点
5. `promote_params` 把 wheels 的 wheel_radius 提到 core 顶层

**断言全过** = agent 工具链能完成"建节点 → 连线（含多输出端消费）→ 配参数（含向量 + live 表达式）→ promote"全链路。地基被 agent "用起来"成立。

### 这解决了什么（第一性原理）

capability-before-rules：先证 agent 能操作地基，再编排多组件流水线（子系统 2）。补这两个工具能力是**小而决定性**的投入 —— 两个函数扩展，解锁整个建模能力。下一步可让真实 Pi agent 在 Project HDA 内做一个最小编模（GUI 端到端真实验证）。
