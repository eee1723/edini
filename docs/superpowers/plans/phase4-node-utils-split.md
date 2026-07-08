# Phase 4 — node_utils.py 拆分执行映射(交接文档)

> ✅ **已完成 (2026-07-08)**:825 passed + 2 subtests,零回归。node_utils.py(4627→38 行 shim)
> 拆成 node_ops/manifest/geometry_inspect/verify。AST 脚本 `scripts/_phase4_split_node_utils.py`
> 一次拆完,85 函数全对账。跨模块依赖执行前 grep 验证无环(与下方预测一致,唯一未预测到的是
> node_ops→geometry_inspect 的 `geometry_inventory`,capture_component_detail 用)。shim 用
> `import *` + 动态镜像下划线私有名。测试调整见 `wiki/pages/progress.md` Phase 4 卡。
> PCA 保留(live crosscheck,非死代码)。下方为原始执行映射,留作记录。


> 目标:把 `python3.11libs/edini/node_utils.py`(~4600 行)按职责拆成 4 个模块,
> `node_utils.py` 保留为 **re-export shim**(调用方 `from edini.node_utils import X` 不变,
> 因此可增量拆 + 任意点停下都功能正常)。强测试门:每拆一块跑全量 pytest 零回归。
>
> 本映射基于函数名 + 已知依赖推导;**执行前需验证标注的跨模块依赖边**(见末尾"待验证")。
> 函数行号是拆分前的(Phase 3 后)。

## 目标模块 + 函数分配

### `node_ops.py` — 节点 CRUD + 场景 + 脚本执行 + 截图
```
get_scene_info(26) create_node(42) _create_with_namespace_fallback(79)
_lop_only_type_hint(147) _init_copytopoints_attribs(177) _apply_tool_presets(205)
delete_node(305) connect_nodes(317) _parm_menu_items(351) _coerce_menu_value(376)
_looks_like_expr(406) _set_parm_value(428) _apply_one_param(469) _not_found_msg(536)
_node_type_for_lookup(569) _suggest_parm_names(581) set_param(601) set_params_batch(626)
get_param(663) list_nodes(679) _serialize_parm_value(703) get_node_info(731)
layout_nodes(758) search_nodes(774) get_help(794) get_selection(3391) check_errors(3407)
set_display_flag(3451) run_python(2340) run_vex(2393) _safe_getvalue(2333)
create_hda(2429) get_hda_info(3368) capture_network(2466) _get_view_type(2560)
_trim_white_border(2578) _concat_images_grid(2601) _target_bounds(2665)
_frame_to_bounds(2712) _capture_single_view(2750) capture_review(2778)
capture_component_detail(3122)
```
> 注:`capture_*` 截图族可独立成第 5 模块 `capture.py`(可选,非必须)。

### `manifest.py` — parm 目录(manifest 生成/加载/查询 + H21 版本解析)
```
_node_parms_manifest_path(834) load_node_parms_manifest(840) _attr_or_call(855)
_vector_component_names(869) _extract_parm_spec(888) _json_safe(1015)
_ramp_to_safe_dict(1048) _correct_vector_components(1067) _is_multiparm_block(1136)
_flatten_parm_templates(1160) _node_parm_inventory(1228) _node_type_namespace(1347)
generate_node_parms_manifest(1378) _enrich_manifest_parms(1452)
_annotate_menu_options(1519) _now_iso(1531) _type_specific_hints(1547)
_access_hints(1555) node_parms(1598) _resolve_node_type_in_manifest(1670)
_manifest_version_key(1709) _hou_default_version(1720) _node_parms_live(1753)
manifest_parm_names(1791) manifest_has_parm(1829)
```

### `geometry_inspect.py` — 几何读取/检查(BASE,被 verify 依赖)
```
_vector_to_list(1860) _geometry_bounds(1867) inspect_geometry(1896)
_component_bounds(1930) geometry_inventory(1951) _edge_key(2053)
inspect_geometry_health(2069)
```
> `_vector_to_list` 被 verify 用 → 放这里(leaf),verify 从这里 import。

### `verify.py` — 验证 + 项目状态/闸门
```
verify_orientation(3502) verify_parametric(3766) verify_robust(3956)
_relative_path_to_core(4125) repath_to_relative(4145) _make_replacer(4236)
_declared_anchor_names(4259) project_status(4273) _finalize_perturbation
project_finalize project_plan
```
> PCA 死代码(verify_orientation 的 crosscheck 用,运行时主路径已移除):
> `_compute_covariance` / `_jacobi_eigen_3x3` / `_KIND_EIGEN_RANK` —— **先 grep 确认仅
> crosscheck 引用再删**(若仍被引用则保留并标注"仅 crosscheck")。

## 依赖序(避免循环 import)

```
geometry_inspect  (base: _vector_to_list/_geometry_bounds; 仅依赖 hou)
      ▲
verify            (从 geometry_inspect 导入 _vector_to_list; 依赖 hou/Any/traceback/ports/state)
manifest          (依赖 hou/json/os; 可能用 node_ops 的 _node_type_for_lookup —— 见待验证)
node_ops          (依赖 hou; _serialize_parm_value 可能用 manifest 的 _json_safe —— 见待验证)
      ▼
node_utils.py = shim: from .node_ops import *; from .manifest import *;
                       from .geometry_inspect import *; from .verify import *
```
用 `from .X import *` + 各模块定义 `__all__`(或显式 re-export 列表)控制导出面。
shim 保证 `archetype_emitter.py` / `builder.py` / `tool_executor.py` 现有
`from edini.node_utils import _init_copytopoints_attribs / _apply_one_param /
_relative_path_to_core / verify_parametric / project_status / project_finalize /
project_plan ...` 全部不变。

## 待验证的跨模块依赖边(执行前 grep 确认)

1. **`_node_type_for_lookup`(我分到 node_ops)是否被 manifest 函数引用?**
   若是 → 移到 manifest(或共享 base),否则 manifest→node_ops 成环。
2. **`_json_safe`/`_ramp_to_safe_dict`(我分到 manifest)是否被 node_ops 的 `_serialize_parm_value` 引用?**
   若是 → node_ops 从 manifest 导入(单向,不环),或移到共享 util。
3. **`_apply_one_param`(node_ops)是否被 verify 引用?**
   verify 用 `_set_archetype_parm`?不 —— `_set_archetype_parm` 在 builder,不在 node_utils。但 verify 用 `_vector_to_list`(已处理)。确认 verify 不直接用 node_ops 的函数。
4. **`_init_copytopoints_attribs`(node_ops)被 archetype_emitter 用** —— shim 保证,无需改 emitter。
5. **PCA 代码真的仅 crosscheck 用?** grep `_jacobi_eigen_3x3|_compute_covariance|_KIND_EIGEN_RANK` 全文件,确认引用点。

## 执行步骤(每步跑测试)

1. 建 `geometry_inspect.py`(最 leaf,风险最低)→ 移函数 → shim re-export → `pytest tests/` 全绿。
2. 建 `verify.py` → 移函数(从 geometry_inspect 导入 _vector_to_list,lazy-import 避免环)→ shim → 测试。
3. 建 `manifest.py` → 移函数 → shim → 测试。
4. 建 `node_ops.py` → 移剩余函数 → shim → 测试。
5. 清 PCA 死代码(验证后)→ 测试。
6. `node_utils.py` 最终只剩 re-export shim(+ 模块 docstring 说明已拆分)。

## 测试命令
```
py -3 -m pytest tests/ -q                    # 全量(基线 825,拆分后应不变)
py -3 -m pytest tests/test_node_utils.py -q  # node_utils handler 协议测(快)
```
hython 21.0.440 在本机可用(报头会标 AVAILABLE);63+ 决定性测会真跑。

## 风险与回退
- shim 是安全网:任何一步出错,函数定义在新模块但 node_utils 仍 re-export → 调用方不受影响。
- 若某步测试红 → 该步的函数移动有 dep 漏了 → 把漏的 helper 也移到同模块(或 lazy-import)。
- 拆分是纯机械重构,零行为变更 → 测试应全绿;任何红都是移动错误,不是行为问题。
