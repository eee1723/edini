# 🧰 工具分类总览

> Edini agent 工具面的权威分类参考。按**功能职责**分组(非文件结构),
> 标注每个工具的唯一职责 + 何时用哪个(重叠工具的决策表)。
> 工具注册的真相源:`tool_executor.py::TOOL_HANDLERS`(Python handler)
> + `pi-extensions/edini-tools/tools/*.ts`(agent 可见的工具定义)。
> 最后更新:2026-07-08(Phase 0b)

---

## 决策原则

1. **先选路径,再选工具**。多部件模型 → Project HDA 管线(下表 §1);
   单件生成器 → sandbox(§7);匹配现成模式 → recipe(§8)。
2. **验证用数值,不用眼睛**(视觉验证默认关闭)。§5 的工具是质量门。
3. **重叠工具看"要什么数据"**,不看名字相似度(§5 决策表)。

---

## §1 项目建模(Project HDA 管线)— 核心路径

多部件程序化模型的**唯一官方路径**。组件 = 子网,经测量锚点协作。

| 工具 | 职责 | 何时用 |
|---|---|---|
| `project_create` | 建 Project HDA,返回 core_path | 任何多部件建模的第一步 |
| `project_build_scaffold` | 声明组件+设计参数 → 建空子网+端口+连线+core spare parm | 跑完 create,组件分解定了 |
| `project_add_anchors` | 从组件几何**测量**锚点(LIVE VEX,非硬编码) | 组件几何建好后,为下游发锚点 |
| `project_repath_to_relative` | 单组件绝对 ch()→相对(可迁移) | 想把组件复制到别的 project 时(可选) |
| `project_promote_params` | 提升子网 spare parm 到 core | design_params 路径下返回 `[]` 是**正确的**(no-op),非失败 |
| `project_status` | 一次性快照:每组件 geo_flow / anchors{declared,emitted,missing} / errors + `overall.incomplete` | 替代 N 次逐组件 inspect;看"还差什么" |

## §2 节点操作(Scene)— 通用 Houdini 节点操纵

| 工具 | 职责 |
|---|---|
| `houdini_create_node` | 建节点(返回含 `parms` 参数清单,免再查) |
| `houdini_connect_nodes` | 连线(from→to,input/output index) |
| `houdini_set_param` / `houdini_set_params_batch` | 设参(**带 addpoint 守卫**:组件内 wrangle 拒硬编码 addpoint) |
| `houdini_get_param` | 读参 |
| `houdini_delete_node` / `houdini_list_nodes` / `houdini_get_node` | 节点 CRUD |
| `houdini_get_scene_info` / `houdini_get_selection` | 场景/选区概览 |
| `houdini_layout_nodes` / `houdini_set_display_flag` | 布局/display flag(观感,不影响逻辑) |
| `houdini_search_nodes` / `houdini_get_help` | 按关键词找节点 / 查节点帮助 |

## §3 参数查询(Parameters)

| 工具 | 职责 |
|---|---|
| `query_parms` | 读节点类型的参数 manifest(**创建前**查询,注意可能与实际版本漂移) |
| `add_parm` | 给节点加 spare parm |
| `dump_parm_catalog` | 导出全节点参数目录(离线参考) |

> `create_node` 返回的 `parms` 字段是**创建后实证**(反映实际版本),
> 比 `query_parms`(manifest)更准。两者互补。

## §4 几何探查(Geometry Inspection)— 低层探针

| 工具 | 要什么数据 |
|---|---|
| `houdini_inspect_geo` | 点/面数、bbox、属性(通用几何探针) |
| `houdini_collect_diagnostics` | 几何+参数+错误打包(一次性聚合诊断) |

## §5 验证(Verification)— 质量门

**这是"模型对不对"的判据层。** 重叠工具决策表:

| 你想知道... | 用 | 别用 |
|---|---|---|
| 节点有没有 cook 错(VEX 语法/编译错) | `houdini_check_errors` | — |
| 几何健不健康(退化面/孤儿点/重合点/非流形) | `inspect_health` | inspect_geo |
| 每个组件(@component_id)各多少面/点 | `geometry_inventory` | inspect_health |
| 几何基础数值(点面数/bbox/属性) | `houdini_inspect_geo` | inspect_health |
| 朝向轴对不对(组件 construction axis) | `verify_orientation` | — |
| **参数化成立吗**(改参→几何朝预期方向变) | `verify_parametric` | inspect_health(只证"此刻没坏") |

> **`inspect_health` 的 `overall_ok` ≠ 参数化成立。** 它只证明"此刻没坏"。
> 证明"改参后几何正确响应"必须用 `verify_parametric`(扰动→recook→量化→还原)。

| 工具 | 职责 |
|---|---|
| `houdini_check_errors` | 节点 errors/warnings(VEX/cook 失败) |
| `inspect_health` | 几何健康(退化/孤儿/重合/非流形)→ `overall_ok` |
| `geometry_inventory` | 按 @component_id 的面/点清单(项目感知) |
| `verify_orientation` | 朝向轴校验 |
| `verify_parametric` | **参数化硬门**:扰动 design_param→recook→量化验证→还原原值 |

## §6 捕获(Capture)— 多为视觉验证门控

| 工具 | 状态 |
|---|---|
| `capture_review` | 视觉验证;**默认关闭**(`visual_verification_enabled`) |
| `houdini_capture_network` | 网络截图 |
| `houdini_capture_component_detail` | 组件细节截图 |

## §7 沙箱生命周期(Sandbox)

无依赖的单件试错用 sandbox;组件生成器必须在 subnet 内(sandbox 无输入)。

| 工具 | 职责 |
|---|---|
| `houdini_run_python_sandbox` | 隔离 geo 跑 Python(试错算法;`network_mode` 建网络) |
| `houdini_verify_asset` | 校验资产符合预期 |
| `commit_sandbox` | 沙箱转正(命名落地) |
| `discard_sandbox` | 丢弃沙箱 |

## §8 配方库(Recipes)

参考样本,非死模板。读 `python_script` 学语法,自建网络。

| 工具 | 职责 |
|---|---|
| `recipe_list` / `recipe_read` | 列/读配方 |
| `recipe_capture` / `recipe_capture_tree` | 从子网/树捕获新配方 |
| `recipe_rebuild` | 确定性复刻配方(可选) |
| `recipe_tree_scan` / `recipe_manager_create` / `recipe_set_notes` | 树扫描/管理器/注记 |

## §9 脚本/VEX/HDA(Scripting)

| 工具 | 职责 |
|---|---|
| `houdini_run_vex` | 跑 VEX 片段(探属性) |
| `houdini_create_hda` / `houdini_get_hda_info` | HDA 创建/查询 |

## §10 知识/评估(Knowledge & Eval)

| 工具 | 职责 |
|---|---|
| `edini_search_knowledge` | 搜沉淀的知识条目 |
| `edini_get_eval_stats` | 近期会话评估统计 |

---

## 工具转发架构

```
Pi Extension (TypeScript)                  Houdini (Python)
┌─────────────────────────┐    HTTP     ┌─────────────────────────┐
│  forwardTool(name,args) │────POST────▶│  ToolExecutor            │
│  (_shared.ts: 重试/超时) │  /execute   │  TOOL_HANDLERS[name]     │
│                         │◄───JSON────│  node_utils.fn()         │
└─────────────────────────┘             └─────────────────────────┘
```

所有工具通过统一 `forwardTool()`(`_shared.ts`,带瞬时错误重试 + 30s 超时 +
结构化错误体)转发到 Houdini 内的 `ToolExecutor`。参数校验由 TypeBox schema
在 Pi 端完成,执行在 Houdini Python 端完成。

---

## 别名(向后兼容,agent 不直接可见)

`TOOL_HANDLERS` 内置旧名→规范名映射(`_TOOL_ALIASES`),供历史 Pi 配置/脚本
平滑过渡。agent 通过 TS 注册看到的始终是规范名:

| 旧名 | 规范名 |
|---|---|
| `houdini_commit_sandbox` | `commit_sandbox` |
| `houdini_discard_sandbox` | `discard_sandbox` |
| `houdini_verify_orientation` | `verify_orientation` |
| `houdini_capture_review` | `capture_review` |
| `houdini_node_parms` | `query_parms` |
| `houdini_inspect_geometry_health` | `inspect_health` |
| `houdini_geometry_inventory` | `geometry_inventory` |

---

## 已退役(不在工具面)

| 工具/模块 | 退役时间 | 原因 |
|---|---|---|
| `build_assembly` / `assembly_builder.py` | 2026-07-08 (Phase 0a) | 被 Project HDA 组件管线取代;VEX 策略已内化进 `vex_strategies` |
| `exprs.py`(表达式引擎) | 2026-07-08 (Phase 0b) | project 路径用原生 ch(),assembly/asset 管线退役后无消费者 |
| `build_procedural_asset` / `validate_recipe` / `build_component` / `assemble_components` / `houdini_variant_scatter` | 2026-06 | 归档于 `_disabled_backup/procedural-modeling/`,被组件管线取代 |
| 声明式资产管道(asset_model/builder/skeleton_resolver) | 2026-06 | 无法表达"测量真实 root 几何定位叶子",见 `_disabled_backup/asset-pipeline-2026-06/` |
