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

先给 chassis 造锚点：
```python
import hou
chassis = hou.node("/obj/project_bike/project_core/chassis")
wr = chassis.createNode("attribwrangle", "make_anchors")
wr.parm("snippet").set('''
addpoint(0, set(2, 0, 1));
setpointattrib(0, "name", 0, "wheel_mount_fr", "set");
addpoint(0, set(-2, 0, 1));
setpointattrib(0, "name", 1, "wheel_mount_rr", "set");
''')
wr.parm("class").set("detail")  # 必须 detail，addpoint 才执行
chassis.node("out_anchors").setInput(0, wr)
chassis.node("out_anchors").cook(force=True)
```

现在 wheels 里的 `in_chassis_wheel_mount_fr` / `in_chassis_wheel_mount_rr` 应该已能拿到锚点（builder 预先连好了 indirectInputs）。验证：
```python
wheels = hou.node("/obj/project_bike/project_core/wheels")
in_fr = wheels.node("in_chassis_wheel_mount_fr")
in_fr.cook(force=True)
print("前轮锚点数:", len(in_fr.geometry().points()))  # 应为 1
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

## 常见问题

| 现象 | 原因 | 解决 |
|---|---|---|
| `ImportError: build_project_scaffold` | Houdini 加载的还是旧代码 | 确认分支/合并状态 + 重启 Houdini |
| `create_project_hda` 报类型找不到 | `edini::project` HDA 没加载 | 确认 `otls/edini_project.hda` 存在 + `HOUDINI_OTLSCAN_PATH` 指向 `otls/` |
| wrangle 加锚点后 0 个点 | `class` 默认 points 不是 detail | 必须 `wr.parm("class").set("detail")` |
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
