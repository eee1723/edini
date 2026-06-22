# Edini Builder — 六项问题完整修复设计

- **日期**: 2026-06-22
- **背景**: 程序化公路车 Phase 1 构建会话日志分析 + 用户视觉反馈，暴露 builder 的 6 类问题
- **范围**: `python3.11libs/edini/harness.py` 的 declarative recipe builder
- **状态**: 待实施

## 1. 问题来源与根因定位

问题来自两个信息源的对齐：(a) Pi agent 会话日志 `2026-06-22T12-47-38...jsonl` 中 3 次完整重建暴露的 cook 失败、fuse 失败、参数读取失败；(b) 用户在 Houdini 视窗中的 6 条视觉/交互反馈。代码根因全部在 `harness.py` 的 builder 段定位完成。

| # | 问题 | 代码根因位置 | 分类 |
|---|---|---|---|
| 1 | 车轮方向不对 | sweep 截面坐标系无约定 | 架构 |
| 2 | sweep `surfaceshape=1 roundtube` 使第二端口 cross-section 失效 | `_build_vex_skeleton_component` line 2748-2765 不处理 surfaceshape | 架构 + 文档 |
| 3 | sweep 对 cross-section 朝向有要求（Z→N, Y→up）未文档化 | 同上 + declarative-builder.md | 架构 + 文档 |
| 4 | 频繁删除整个网络重建浪费资源 | builder 无增量重建能力 | 架构 |
| 5 | 参数 UI 文件夹分裂（第一个多，后面每个只 1 个参数） | `_evaluate_derived_params` line 2073 每个_derived 单独调用 `_install_params_via_template_group`，每次新建 folder | 架构 bug（最影响体验）|
| 6a | python 后端 `hou.ch()` 读不到参数 | `_build_python_component` line 2569-2584 完全不装 spare parms | bug |
| 6b | 不该用 python 的地方还在用 | 缺少使用门槛约束 | 架构 |
| B2 | fuse postprocess 创建失败（"Invalid node name"）| postprocess 段 line 3233 `pp_name = f"post_{i}_{pp_type}"`，`fuse::2.0` → 非法节点名 `post_0_fuse::2.0` | bug |

## 2. 关键决策（已与用户确认）

- **决策 1（sweep）= A 最小修复**: 强制 `surfaceshape=0` + 文档约定截面坐标系，不自动注入 N/up
- **决策 2（重建）= B 新增 rebuild_component**: 支持只重建单个组件子网，不持久化 recipe（接收新 component spec dict）
- **决策 3（python 后端）= B 保留 + 收紧**: 修参数安装 bug，validation 加 `justification` 警告门槛，文档降级为"最后手段"

## 3. 架构总览

所有修复集中在 3 个文件，无新模块：

- `python3.11libs/edini/harness.py` —— builder 逻辑（5 处改动 + 1 个新函数）
- `skills/procedural-modeling/references/declarative-builder.md` —— 约定文档
- `skills/procedural-modeling/scripts/{recipe-template,prebuilt-templates}.md` —— 模板纠正
- 测试: `tests/test_build_procedural_asset.py`（TDD, mock）+ `tests/multi_component_e2e.py`（真 H21）

**六项问题 → 修复映射:**

| 问题 | 修复 | 位置 |
|---|---|---|
| 1/2/3 车轮+sweep | sweep 强制 surfaceshape=0 + 截面坐标系约定 | harness `_build_vex_skeleton_component` + 文档 |
| 5 参数文件夹分裂 | 参数批量收集，单次安装 | harness `_install_spare_params` + `_evaluate_derived_params` 重构 |
| 6a python 不装参数 | python 后端补装 spare parms | harness `_build_python_component` |
| 6b python 滥用 | validation 加 justification 警告 + 文档降级 | harness `_validate_recipe` + 文档 |
| 4 频繁重建 | 新增 `rebuild_component` 工具 | harness 新函数 |
| B2 fuse 失败 | postprocess 节点名清洗 `::` + mock 加固 | harness postprocess 段 + mock_hou.py |

## 4. 详细设计

### 4.1 sweep 修复（问题 1/2/3）

**代码改动**（`_build_vex_skeleton_component`，dual-wrangle 分支 line 2748-2765）:

- 当 `section_code` 存在时（即使用第二端口 cross-section），builder **强制 `surfaceshape=0`**，覆盖 recipe 设的任何值
- 若 recipe 显式设了非 0 的 `surfaceshape` 且同时有 `section_code` → 矛盾，emit warning 并强制改回 0（第二端口 cross-section 与 roundtube 互斥）

**文档约定**（declarative-builder.md "Dual-wrangle mode" 段）:

- cross-section 必须画在 **XZ 平面**
- **Z 轴 = 对齐曲线法线 N 方向**，**Y 轴 = 对齐 up 方向**
- path wrangle 产出折线即可，朝向由 sweep 按 N/up 计算

**模板纠正**（recipe-template.md / prebuilt-templates.md）:

- 删除示例里的 `surfaceshape:1` / `surfaceshape: 1`
- 保留 `surfacetype:2, endcaptype:1`，不设 surfaceshape（让 builder 默认处理）

**测试**: mock 断言"section_code 存在时，sweep 节点 surfaceshape parm == 0"；recipe 显式设非 0 + section_code 时有 warning。

### 4.2 参数文件夹合并（问题 5，最影响体验）

**根因重述**: `_evaluate_derived_params` 在 for 循环里每个 derived 调用一次 `_install_params_via_template_group`，每次新建一个 folder → N 个 derived = N 个单参数文件夹。

**重构**（`_install_spare_params` + `_evaluate_derived_params`）:

1. `_evaluate_derived_params` 改为只返回 `{name: value}`（纯计算，不安装）
2. `_install_spare_params` 增加参数：接收已算好的 derived values，收集 primary + derived 的 templates 合成一个 list
3. **单次**调用 `_install_params_via_template_group(root, hou, all_templates)` → 只生成一个 `edini_params` 文件夹

**调用顺序**（build_procedural_asset 内，一次性收集所有 templates 后单次安装，避免多次 setParmTemplateGroup 互相覆盖）:
```
1. primary_values = _resolve_primary_values(primary_params_spec)  → 纯计算，不安装
2. derived_values = _evaluate_derived_params(derived_params_spec, primary_values) → 纯计算，不安装
3. _install_spare_params(root, primary_params_spec, derived_values) → 收集 primary+derived templates，单次安装
```

**接口变化**:
- `_evaluate_derived_params` 签名改为接收 params_spec + primary_values，返回 `{name: {value, label}}`，**完全不安装**（去掉 line 2069-2089 的安装逻辑）
- `_install_spare_params` 签名增加 `derived_values: dict[str, dict]` 参数，把 derived 也加进 templates list，单次安装全部

**测试**: mock build 一个含 5 primary + 4 derived 的 recipe，断言 root 的 parmTemplateGroup 里名为 `edini_params` 的 folder **恰好 1 个**且含 9 个 parm。

### 4.3 python 后端修复（问题 6）

**6a 参数安装**（`_build_python_component`，line 2569-2584）:

- 函数签名加 `param_values: dict` 参数
- 复用 `_make_wrangle` 里的 reads→spare parm 安装逻辑（line 2732-2744），给 python SOP 装 spare parms 并设 `ch("../name")` 表达式
- 调用点（line 3125）传入 `param_values`

**6b 收紧门槛**（`_validate_recipe`）:

- backend == "python" 且无 `justification` 字段 → 加入 `warnings`（不阻断，保持向后兼容）
- backend == "python" 且有 `justification`（非空字符串）→ 通过
- warnings 通过 build result 的 `validation_warnings` 字段返回，agent 可见

**文档**（declarative-builder.md）:

- python 后端标记为"最后手段"，需 `justification` 说明为何不能用 SOP
- 判断准则: NURBS / 细分曲面等 SOP 难表达的才算；简单几何一律走 native_chain / vex_skeleton

**测试**:
- mock 断言 python SOP 装了 reads 对应的 spare parms
- validation 对无 justification 的 python 后端返回 warning；有 justification 不警告

### 4.4 rebuild_component 工具（问题 4）

**新函数** `rebuild_component(sandbox_root_path, component_id, component_spec) -> dict`:

逻辑:
1. 在 sandbox 内找出所有名字以 `{cid}_` 开头的节点（如 `wheel_rim_path` / `wheel_rim_section` / `wheel_rim_sweep` / `wheel_rim_tag` / `copy_wheel_rim` 等）
2. 记录它们在 merge 节点的输入索引（找到 merge 节点中哪个 input 连到 `{cid}_tag` 或 `{cid}_idfix`）
3. 销毁这些节点
4. 用 `component_spec`（完整的组件定义 dict）调用对应的 `_build_*_component`，只重建这一个
5. 把新输出节点接回 merge 的原索引
6. cook OUT，返回诊断（成功/失败 + geometry stats）

**不持久化 recipe 的取舍**:

- `rebuild_component` 直接接收新的 component spec dict，不依赖 sandbox 存 recipe
- 理由: 最简单、无副作用；用户/agent 手里本来就有 recipe
- 不选"sandbox 存 recipe": 增加状态管理复杂度，收益小

**边界处理**:
- 目标 cid 在 sandbox 中不存在 → 报错（不能 rebuild 不存在的组件）
- component_spec 的 id 与 component_id 不一致 → 报错
- 销毁节点时，若该组件是 stamped（有 anchors），需同时销毁 anchors SOP + copytopoints + idfix，全部按 `{cid}_` 前缀匹配
- rebuild 后若 cook 失败，sandbox 保持已销毁状态（不回滚），返回错误供 agent 决策

**测试**:
- mock build 两组件 → rebuild 其中一个 → 断言只有目标 cid 的节点被重建（对象身份变化），另一个 cid 的节点对象身份不变
- rebuild 不存在的 cid → 报错
- component_spec.id 与 component_id 不一致 → 报错

### 4.5 fuse 节点名 bug（问题 B2）

**根因**: line 3233 `pp_name = f"post_{i}_{pp_type}"`，当 `pp_type="fuse::2.0"` → 节点名 `post_0_fuse::2.0`，真 Houdini 拒绝含 `::` / `.` 的节点名 → "Invalid node name" → fuse 被跳过 → 652 非流形边残留。

**修复**（postprocess 段 line 3229-3239 + variant scatter line 3865+）:

- 节点名清洗: `pp_name = f"post_{i}_" + re.sub(r"[^A-Za-z0-9_]", "_", pp_type)` → `post_0_fuse_2_0`
- 抽出 helper `_sanitize_node_name(type_str)` 复用于两处 postprocess + 任何动态命名

**mock 加固**（mock_hou.py）:

- `setName` / `createNode` 加节点名合法性校验: 拒绝含 `::` 或其他非法字符的名字，抛 `hou.InvalidNodeName` 异常
- 目的: 这类 bug 未来能在 mock 测出来，而不是只等真 H21 暴露

**测试**:
- mock 断言 postprocess 节点名不含 `::`
- mock `setName("fuse::2.0")` 抛 InvalidNodeName

## 5. 测试策略

TDD，每个修复先写失败测试:

- **mock 单元测试**（test_build_procedural_asset.py）: 4.1/4.2/4.3/4.4/4.5 各 1-3 个测试
- **mock 校验加固**（mock_hou.py）: 节点名校验
- **真 H21 e2e**（multi_component_e2e.py）: 用一个含 sweep 双 wrangle + 多个 derived 参数 + python 组件的 recipe 跑完整 build，确认参数 UI 单文件夹、sweep 成型、python 读参数成功、fuse postprocess 不再失败

## 6. 不在本轮范围（YAGNI）

- sweep 自动注入 N/up（决策 1 选 A，不做）
- recipe diff 持久化重建（决策 2 选 B 的轻量版，不存 recipe）
- 废弃 python 后端（决策 3 选 B，保留）
- H21 参数名更新（B3）和 VEX `{}` 语法文档（B4）作为附带项顺带更新模板，不单独列计划

## 7. 实施顺序建议

按依赖与风险从低到高:

1. **B2 fuse 节点名**（最小、独立、立刻见效）+ mock 加固
2. **4.2 参数文件夹合并**（体验最痛点，纯重构）
3. **4.3 python 后端参数安装 + 门槛**（独立 bug）
4. **4.1 sweep surfaceshape**（需要文档配合）
5. **4.4 rebuild_component**（新功能，最大，放最后）
6. 真 H21 e2e 验证全部
