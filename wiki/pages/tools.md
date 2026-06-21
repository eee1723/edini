# 🔧 工具清单

> Edini 30+ 个 Houdini 工具的完整目录。最后更新：2026-06-21。

## 工具总览

| 分类 | 数量 | 工具 |
|------|------|------|
| 场景/节点 | 11 | Scene Info · Create · Delete · Connect · Set Param · Get Param · List · Layout · Selection · Errors · Display Flag |
| 查询/检查 | 5 | Search · Help · Node Info · Inspect Geo · **query_parms** |
| 脚本/HDA | 3 | Run VEX · Create HDA · Get HDA Info |
| 捕获 | 2 | Capture Viewport Safe · Capture Network |
| Procedural Harness | 12 | Sandbox · Diagnostics · Verify · Commit · Discard · Safe Capture · Build Asset · Variant Scatter · **validate_recipe** · **build_component** · **assemble_components** · **add_parm** |
| 目录 | 1 | **dump_parm_catalog** |

## 场景工具 (scene.ts)

### houdini_get_scene_info
- **说明**：获取当前 Houdini 场景概览
- **返回**：hip 文件名 · /obj 子级 · 总节点数 · 当前路径
- **示例**："What's in my scene right now?"

### houdini_create_node
- **参数**：`node_type` (必填) · `name` (可选) · `parent_path` (默认 /obj)
- **返回**：新节点路径
- **示例**："Create a geometry node called smoke_sim"

### houdini_delete_node
- **参数**：`node_path` (必填)
- **返回**：删除确认
- **示例**："Remove /obj/old_geo"

### houdini_connect_nodes
- **参数**：`from_path` · `to_path` · `input_index` (默认 0)
- **返回**：连接确认
- **示例**："Connect the sphere to the scatter node"

### houdini_set_param
- **参数**：`node_path` · `param_name` · `value`
- **返回**：设置确认
- **示例**："Set the sphere radius to 2.5"

### houdini_get_param
- **参数**：`node_path` · `param_name`
- **返回**：当前参数值和元数据
- **示例**："What's the current grid size?"

### houdini_list_nodes
- **参数**：`parent_path` (默认 /) · `type_filter` (可选)
- **返回**：节点列表 (路径、类型)
- **示例**："List all geo nodes under /obj"


### houdini_get_selection ✨ 新增
- **参数**：无
- **返回**：选中节点列表 (名称/路径/类型)
- **示例**："What is selected right now?"
- 💡 用户说"这个节点"时自动获取选中

### houdini_check_errors ✨ 新增
- **参数**： (可选，省略扫描全场景)
- **返回**：错误列表 + 警告列表
- **示例**："Check for errors in my scene"

### houdini_set_display_flag ✨ 新增
- **参数**： (必填)
- **返回**：设置确认
- **示例**："Show this node in the viewport"

### houdini_layout_nodes
- **参数**：`parent_path` (默认 /obj)
- **返回**：布局确认
- **示例**："Clean up the network layout"

## 查询工具 (query.ts)

### houdini_search_nodes
- **参数**：`keyword` (必填)
- **返回**：匹配的节点类型列表 (分类/名称/描述)
- **示例**："Find all Pyro-related node types"

### houdini_get_help
- **参数**：`node_type_name` (必填)
- **返回**：节点帮助文档 (参数说明/用法)
- **示例**："What does the Pyro Solver do?"

### houdini_get_node
- **参数**：`node_path` (必填)
- **返回**：节点详细信息 (类型/输入/输出/所有参数)
- **示例**："Show me all parameters on /obj/geo1"

### houdini_inspect_geo
- **参数**：`node_path` (必填，必须是 SOP 节点)
- **返回**：点/面/顶点数 · 属性列表 · 包围盒
- **示例**："How many points does this geometry have?"

### query_parms ✨ 新增
- **参数**：`node_type` (必填) · `category` (默认 Sop)
- **返回**：节点的参数目录（名称/类型/默认值/菜单项），由 `parm-catalog.json` 驱动
- **示例**："What parameters does the Normal SOP have?"
- 💡 在任何 parm 设置前先用此工具查参数名——不要猜测 H21 参数名

## 脚本工具 (script.ts)

### houdini_run_vex
- **参数**：`code` (必填) · `node_path` (可选) · `attrib_name` (默认 result)
- **返回**：VEX 执行输出
- **示例**："Write VEX to scatter points on the surface"
- ⚠️ 此工具**非沙盒**——直接在 /obj 创建实时节点。优先用 `houdini_run_python_sandbox` 做程序化资产工作

### houdini_create_hda
- **参数**：`node_path` · `hda_name` · `hda_label` (可选)
- **返回**：HDA 创建确认
- **示例**："Package this network as 'my_smoke_sim' HDA"

### houdini_get_hda_info
- **参数**：`hda_name` (必填)
- **返回**：HDA 定义详情 (参数接口/输入输出)
- **示例**："What parameters does the 'sidefx_smoke' HDA have?"

## 工具转发架构

## Procedural Harness Tools

> 程序化建模默认走这组工具：先验证→逐组件构建→组装→诊断→提交。详细手测重点见 [Procedural Harness](procedural-harness.html)。

### Pipeline Tools (Phase A/B/C)

### dump_parm_catalog
- 从已安装的 Houdini 版本生成参数目录（`parm-catalog.json`）
- 每会话调用一次，在使用 `validate_recipe` 或 `build_procedural_asset` 之前

### validate_recipe
- Phase A：零 Houdini 操作验证程序化资产 recipe
- 六层检查：Schema · Parm 名 · 节点类型 · VEX Lint · 构造轴 · 依赖图
- 在任何 cook 之前捕获参数名拼写错误和无效节点类型

### build_component
- Phase B：在沙盒内构建单个组件。Cook、验证几何健康、确认 @component_id 标记

### assemble_components
- Phase C：将所有通过的组件组装为最终资产（anchors + CTP + merge + postprocess）

### build_procedural_asset
- 声明式 Recipe Builder（PREFERRED）：agent 只写纯几何代码 + recipe JSON，harness 确定性建网
- 内部串联 Phase A 验证→逐组件构建→组装→cook→返回诊断

### houdini_variant_scatter
- Variant Scatter Builder：多 variant 几何体加权分布到散点

### houdini_collect_diagnostics
- 收集节点 cook 错误、参数值、几何摘要和上下文

### houdini_run_python_sandbox
- 在程序化沙盒内执行 Python 代码。两种模式：single-SOP（默认）/ network_mode

### houdini_verify_asset
- 验证生成的资产：点/面数、bounds、节点错误、结构检查

### commit_sandbox
- 验证后将沙盒提交到最终资产位置。运行朝向门+结构门

### discard_sandbox
- 删除不再需要的程序化沙盒

### capture_review
- 多视角、多帧审查接触表。支持 4-view quad、frame-range

### houdini_capture_component_detail
- @component_id 值的特写单元格，各自包围盒取景

### verify_orientation
- 按组件 PCA 或 construction_axis 验证轴向方向（authoritative）

### inspect_health
- 几何健康检查：orphan/degenerate/non-manifold 检测

### geometry_inventory
- 列出每个 @component_id 的 prim 数和相对大小

### add_parm ✨ 新增
- 在任意 Houdini 节点上快速创建 spare float 参数
- 参数：`node_path` · `name` · `default` · `min` · `max` · `label`
- 返回 channel_path 可直接用于 `hou.ch()`
- 示例：`add_parm("/obj/my_asset", "crank_len", default=0.17, min=0.15, max=0.20)`

## 工具别名（向后兼容）

| 旧名 | 新名 |
|------|------|
| `houdini_build_procedural_asset` | `build_procedural_asset` |
| `houdini_commit_sandbox` | `commit_sandbox` |
| `houdini_discard_sandbox` | `discard_sandbox` |
| `houdini_verify_orientation` | `verify_orientation` |
| `houdini_capture_review` | `capture_review` |
| `houdini_node_parms` | `query_parms` |
| `houdini_inspect_geometry_health` | `inspect_health` |
| `houdini_geometry_inventory` | `geometry_inventory` |

## Tool Forwarding Architecture

```
Pi Extension (TypeScript)                  Houdini (Python)
┌─────────────────────────┐    HTTP     ┌─────────────────────────┐
│  forwardTool(name,args) │────POST────▶│  ToolExecutor            │
│                         │  /execute   │  TOOL_HANDLERS[name]     │
│                         │◄───JSON────│  node_utils.fn()         │
└─────────────────────────┘             └─────────────────────────┘
```

所有工具通过统一的 `forwardTool()` 函数转发到 `http://127.0.0.1:9876/execute`。
参数校验由 TypeBox schema 在 Pi 端完成，执行在 Houdini Python 端完成。
