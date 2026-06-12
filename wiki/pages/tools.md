# 🔧 工具清单

> Edini 27 个 Houdini 工具的完整目录。最后更新：2026-06-12。

## 工具总览

| 分类 | 数量 | 工具 |
|------|------|------|
| 场景/节点 | 11 | Scene Info · Create · Delete · Connect · Set Param · Get Param · List · Layout · Selection · Errors · Display Flag |
| 查询/检查 | 4 | Search · Help · Node Info · Inspect Geo |
| 脚本/HDA | 4 | Run Python · Run VEX · Create HDA · Get HDA Info |
| 捕获 | 2 | Capture Viewport Safe · Capture Network |
| Procedural Harness | 6 | Sandbox · Diagnostics · Verify · Commit · Discard · Safe Capture |

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

## 脚本工具 (script.ts)

### houdini_run_python
- **参数**：`code` (必填)
- **返回**：Python 执行输出
- **示例**："Run a Python script to randomize point colors"
- ⚠️ 优先使用专用工具，仅在必要时用此工具

### houdini_run_vex
- **参数**：`code` (必填) · `node_path` (可选) · `attrib_name` (默认 result)
- **返回**：VEX 执行输出
- **示例**："Write VEX to scatter points on the surface"
- 💡 自动创建临时 Attribute Wrangle 节点执行

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

> 程序化建模默认走这组工具：先沙盒生成，再诊断/验证，最后提交或丢弃。详细手测重点见 [Procedural Harness](procedural-harness.html)。

### houdini_collect_diagnostics
- Collect node errors, warnings, parameters, and optional geometry stats before retrying or deleting failed procedural work.

### houdini_run_python_sandbox
- Run Houdini Python inside a live procedural sandbox so failed generation keeps diagnostics and avoids overwriting live scene nodes.

### houdini_verify_asset
- Verify generated assets with geometry counts, bounds, node errors, and expected structural checks.

### houdini_commit_sandbox
- Rename a verified sandbox root into the final asset location after checks pass.

### houdini_discard_sandbox
- Delete a procedural sandbox after it is no longer needed.

### houdini_capture_review
- Capture multi-view, multi-frame review contact sheets for procedural assets.
- Supports single views (`views=["perspective"]`), 4-view quads, and frame-range time-lapses.
- Always pass `target_path` — it automatically isolates the target and frames each view.
- If capture fails, report the clean failure and diagnostics instead of probing Qt widgets or unsupported viewport internals.

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
