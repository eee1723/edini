# 程序化 Agent 架构重构计划 (2026-07-08)

> 从第一性原理出发,系统性修复程序化建模 agent 的能力卡点与架构问题。
> 目标:架构清晰、工具完整且分类合理、调用链顺畅、稳定可扩展。
> 本文档是**跨会话的持久追踪物**,每个 Phase 完成后回填状态 + 铁证。

---

## 0. 第一性原理

**程序化模型是一个函数 `params → geometry`。** 要达成用户诉求,它必须满足:

| 诉求 | 数学性质 | 工程体现 |
|---|---|---|
| 参数自由调整 + 稳定正确 | **全函数**(对所有合法参数有定义)+ **连续**(参数微变→几何微变,无拓扑爆炸) | 区间验证,非点采样 |
| 模型模块化拆分 | **子函数复合**,每个子函数**自包含、可重定位** | 组件 = 可迁移单元,引用不绑死 scene 路径 |
| 多轮优化 | 子函数**可独立迭代** | 组件级版本/快照 |
| agent 执行链路清晰 + 发挥最大能力 | agent 行使判断的每一处都满足:**窄、有工具、可验证** | step 3 不能是"工具荒漠" |

**核心张力(现状诊断的母体)**:第 2 步(脚手架)和第 4 步(验证)已是工业级,但**第 3 步(组件内部建模,占 agent 80% 工作量)只有 `create_node/set_param` 裸工具**。所有反复出现的失败(接线错觉、Python SOP 缺口、bbox 伪参数化)根因都是这一个不对称。

**重构的第一性原理锚点**(已验证正确,不动):*不让 LLM 写 VEX/坐标,平台预写预测,agent 只声明意图。* 所有改动都在**强化**这个锚点,而非偏离它。

---

## 1. 目标 → Phase 映射

| 用户诉求 | 主要负责 Phase |
|---|---|
| 架构清晰(单一管线、无死代码) | Phase 0 |
| 完整工具链 + 分类合理 + 调用顺畅 | Phase 0b, 1c, 4 |
| 参数自由调整 + 模型稳定正确 | Phase 1a(引用稳健), Phase 2(区间验证) |
| 模型模块化拆分(组件自包含) | Phase 1a, 4 |
| 多轮优化 | Phase 5 |
| agent 执行链路清晰 | Phase 1b, 1c, 4 |
| 发挥 agent 最大能力 | Phase 3, 4(治 step 3 工具荒漠) |

---

## 2. 重构路线图(依赖序)

```
Phase 0  地基清理 ─────┬─ 0a 退役 build_assembly 后端(单一管线)
                       └─ 0b 工具面盘点 + 分类重组
                            │
Phase 1  稳固现有管线 ─┬─ 1c project_status 聚合工具  [独立, 快赢]
                       ├─ 1b 子网内部重连安全          [独立, 拆雷]
                       └─ 1a 参数引用方案(相对默认)   [解锁 Phase 4]
                            │
Phase 3  关闭 by_name 鸿沟 ── 3a project_emit_markers  [Phase 4 前置]
                            │
Phase 4  组件原型化(核心) ── 4a project_emit_component + 原型库
                            │
Phase 2  区间验证 ─────────── 2a verify_robust          [验证新世界]
                            │
Phase 5  组件级迭代 ───────── 5a 组件版本/快照/分支
```

**排序理由**:地基(0)先清,否则后续每步都要排除死代码干扰;1a 必须在 4 之前(原型生成器要用正确的参数引用方案);3 是 4 的前置(原型默认发射 marker);2 放在能力建完之后验证整体;5 依赖稳定的能力层。

---

## 3. 各 Phase 详案

### Phase 0a — 退役 build_assembly 后端(单一管线)

**治什么**:Problem A(两条管线并存)。TS 面已退役,但后端 handler + `assembly_builder.py` + 反向依赖仍 live,造成维护债 + `vex_strategies` 两头伺候。

**改哪里**:
- `tool_executor.py:50,482-486` — 删 import + 删 `build_assembly` handler + 删 wrapper `build_assembly()`
- `assembly_builder.py` — 归档到 `_disabled_backup/`(保留 git 历史,不 live)
- `vex_strategies.py` — **外科手术**:剥离对 `assembly_builder._expand_shelf_layers` 和 `measure._rule_rot` 的反向依赖

**关键决策点**(执行时定):`vex_strategies` 的 TabularFill 族(cells/pickets/tiles/shelf/blocks)是否保留?
- **方案 A(保留 + 内化)**:把 `_expand_shelf_layers`/`_rule_rot`/`_parse_axes`/`_parse_face` 等共享原语搬进 `vex_strategies.py`(或新建 `edini/measure_primitives.py`),TabularFill 留作 project 的"高级布局"策略(keyboard keys / fence / 书架)。
- **方案 B(裁剪)**:project skill 只教 bbox/by_name,TabularFill 连带裁掉。
- **倾向 A**:cells 是 keyboard 的正解,裁掉是能力倒退。内化依赖后 vex_strategies 成为自足模块。

**验证**:`measure.py` 若仅被 test_measure.py(oracle 测试)用,随 assembly 一起归档;若被 vex_strategies 用,拆出共享部分。全套件 `pytest` 保持绿(退役的 assembly 测试随代码归档)。

**风险**:中。纯删除有耦合,需先读 `assembly_builder.py` + `measure.py` + 两个 assembly 测试确认依赖图。

---

### Phase 0b — 工具面盘点 + 分类重组

**治什么**:Problem C(碎片化 + 别名层)。50+ 工具语义重叠(inspect_health/inspect_geo/geometry_inventory/collect_diagnostics 四个"看状态")。

**做什么**:产出一张工具分类表(建模 / 测量 / 验证 / 探查 / 沙箱 / 配方 / 知识 / 评估),明确每个工具的唯一职责,合并重叠项,清理已无引用的别名。文档化到 wiki/pages/tools.md(若存在)或新建。

**验证**:工具清单与 `tool_executor.TOOL_HANDLERS` + TS 注册逐一对照,无孤儿。

**风险**:低(主要是文档 + 小幅合并)。

---

### Phase 1c — project_status 聚合工具 [快赢]

**治什么**:卡点 6(agent 花 token 收集状态)。诉求:易用 + agent 能力。

**做什么**:新增 `project_status(core_path)`,一次返回每个组件的完成度:
```
{ components: [
    {id, geo_flow: ok|empty|broken, anchors_emitted: "4/4",
     verify: [{param, pass}], errors: 0, orientation: pass|fail}
  ], overall: "2/3 parametric" }
```
聚合现有 `inspect_geometry_health` / `geometry_inventory` / `check_errors` / `verify_orientation` + 读 declaration 的 ports.out anchors 声明。

**改哪里**:`node_utils.py`(实现)+ `tool_executor.py`(注册)+ `project.ts`(TS 工具)。

**验证**:hython 真机搭 3 组件模型(1 完成 / 1 半成品 / 1 空),断言 status 准确区分。mock 测试覆盖空 declaration。

**风险**:低。纯只读聚合。

---

### Phase 1b — 子网内部重连安全 [拆雷]

**治什么**:Problem D(子网内部重连不安全,session-logs 的 10 分钟接线错觉的真根因之一)。

**做什么**:两条路二选一(执行时定):
- **方案 A**:新增组件感知重连工具 `project_rewire_anchor(component_id, from, anchor, new_source)`,内部正确处理 `indirectInputs` + filter/clean/in 三件套。
- **方案 B**:`houdini_connect_nodes` 检测到目标是组件子网内部节点时,明确拒绝并引导到正确工具(对齐 addpoint 守卫哲学)。
- **倾向 A+B**:B 兜底防破坏,A 提供正门。

**验证**:hython 真机断开一条 anchor 线,用 A 重连成功且下游恢复;对照组用裸 connect_nodes 在子网内部重连应被 B 拒绝。补 `internal_chain_ready` 真查接线的测试(填补 session-logs 末尾的 xfailed)。

**风险**:中。setInput 语义在子网内部复杂,需真机验证。

---

### Phase 1a — 参数引用方案(相对为默认)[解锁 Phase 4]

**治什么**:卡点 3(绝对 ch() 绑死 scene 路径,组件不可迁移,改名即崩)。

**决策点**:当前官方路径 `ch('/obj/.../project_core/length')` 绝对。问题:重命名/复制 project 即断链。`repath_to_relative` 是事后补丁。

**候选方案**(执行时用 hython 选定):
- **方案 A(子网提升相对引用)**:scaffold 把每个 design_param 提升进各组件子网为 spare parm = `ch("../<param>")`(到 core 一级,深度由 scaffold 保证)。子网内几何引用 `ch("<param>")` 或 `ch("../<param>")`,永远相对、永远子网内自洽。组件复制到别处只要父级有同名 parm 即可 cook。**这是标准 Houdini HDA 模式,最干净。**
- **方案 B(scaffold 烘焙相对深度)**:scaffold 建子网时把 core→subnet 的相对深度算好,几何用 `ch("../../<param>")`。问题:agent 在子网内新建的节点深度不一,scaffold 无法预知。

**倾向 A**:它把"深度保证"放在 scaffold 能掌控的层级(子网 spare parm),agent 只需在子网内用一级相对引用,彻底消除"跨嵌套相对 ch() 零几何"的历史 bug。这也让被 demote 的 `promote_params` 重新有语义(它本来就是这个机制的雏形)。

**改哪里**:`builder.py`(`_ensure_design_params` 改为提升到子网)、`SKILL.md`(第 2b/3 步改教相对引用)、`repath_to_relative`(降级为导出工具)。

**验证**:hython 铁证——复制一个组件子网到另一个 project,无 repath 即可 cook;改 core param 子网几何跟变。**可先做成 opt-in(scaffold 选项),验证稳定后再翻默认值。**

**风险**:高。触碰核心参数契约 + skill 教学 + 现有测试。必须 hython 铁证 + 分阶段(opt-in→默认)。

---

### Phase 3 — 关闭 by_name 鸿沟 [Phase 4 前置]

**治什么**:卡点 2(by_name 比 bbox 难 → agent 永远退回 bbox 伪参数化,发现 3)。

**做什么**:新增 `project_emit_markers(component_id, markers=[{name, at:"bbox_corner", axes:"+X+Y+Z"} | {name, at:"point", ...}])`,一步声明式发射语义标记点。让 by_name 的上游准备和 bbox 一样容易(一步 + 有专属工具)。

**改哪里**:`builder.py`(新增 `emit_markers`)+ `tool_executor.py` + `project.ts`。

**验证**:hython 真机——emit marker 后,下游 by_name 锚点跟随几何形变(非 bbox 中心);对照仅用 bbox_face_center 偏离真实位置。

**风险**:低-中。新增工具,不破坏现有。

---

### Phase 4 — 组件原型化(核心能力解锁)

**治什么**:卡点 1 + Problem B(step 3 工具荒漠)。这是"发挥 agent 最大能力"的钥匙。

**做什么**:新增 `project_emit_component(core_path, component_id, archetype, ...params)`,平台层生成组件的节点链(含 marker 发射),对齐第 2 步的声明式密度。`COMPONENT_TEMPLATE.md` 从"建议"升级为"参考"(原型已内置骨架)。

**原型库**(覆盖 ~80% 真实组件,按日志频次排序):
| archetype | 适用 | 内部 |
|---|---|---|
| `box_panel` | 桌面/座面/挡板 | 纯 native box + ch() 引用,**无需 Python SOP** |
| `copy_array` | 桌腿/辐条/键盘键 | CTP + by_name 消费锚点 |
| `tube_graph` | 车架/fork/把手 | Python SOP 骨架(内置 5 规则)+ polywire + 自动 marker |
| `extrude_profile` | 扶手/曲线挤出 | sweep/extrude 沿曲线 |

每个原型:**幂等、内置正确 ch() 引用方案(用 1a 的结果)、内置 marker 发射(用 3 的结果)、通过 verify_orientation**。

**改哪里**:`builder.py`(原型生成器族)+ `tool_executor.py` + `project.ts` + `SKILL.md`(第 3 步改教"优先原型,降级才裸建")。

**验证**:hython 真机——用 `tube_graph` 原型搭灯(底座+杆+灯罩),零 Python SOP 错误一次过;对照旧裸建必踩 ≥2 个 return 错误。每个原型配 oracle 测试。

**风险**:中-高。工作量大,但分原型增量交付(先 box_panel + copy_array,再 tube_graph)。

---

### Phase 2 — 区间验证(verify_robust)

**治什么**:卡点 4(点采样验证不证伪"区间不成立")。

**做什么**:新增 `verify_robust(node_path, core_path, params=[...], samples="min_default_max")`,对每个 design_param 在 min/default/max 扰动、recook,断言:(a) 几何非零 (b) 朝预期方向变化 (c) 无新错误 (d) prim 数量变化在合理范围(无拓扑爆炸)。非破坏(restore)。

**改哪里**:`node_utils.py`(实现,复用 verify_parametric 的 perturb→restore)+ `tool_executor.py` + `harness.ts`。

**验证**:hython 真机——对 table length 在 [0.4, 1.2, 3.0] 全 PASS;对人为构造的"极端坍缩"模型 FAIL。

**风险**:低-中。复用现有 perturb 机制,扩展为多点。

---

### Phase 5 — 组件级迭代

**治什么**:卡点 5(无组件级版本/迭代)。诉求:多轮优化。

**做什么**:把 `NodeVersionList`(project/core 级)概念下沉到组件:组件子网可 snapshot/branch/A-B。冻结 tabletop、迭代 legs 3 轮并对比成为一等操作。

**改哪里**:`chat_driver.py` + 新增组件快照机制(子网 copy + 版本元数据)+ UI。

**验证**:hython + UI 手测——snapshot 组件、分支、切回、对比几何。

**风险**:中。涉及 UI + 版本元数据,放最后。

---

## 4. 验证策略(每个 Phase 通用)

1. **代码 + 测试同步**:新行为配 mock 测试 + oracle 测试。
2. **hython 真机铁证**:凡涉及 hou 真实行为(setInput/spare parm/cook)必上 hython,不靠 mock 自证。
3. **零回归**:每 Phase 结束 `pytest` 全绿(当前基线 946 测试 + 1 xfailed)。退役代码的测试随代码归档,不算回归。
4. **wiki 沉淀**:每 Phase 在 `progress.md` 加状态卡 + `pitfalls.md` 记新踩坑。
5. **行号佐证**:凡断言"X 行为"必落到源码行号(团队既定方法论)。

---

## 5. 执行节奏

每个 Phase 独立交付(代码 + 测试 + 铁证 + wiki),可中断可恢复。优先级:
**0a → 1c → 1b → 1a → 3 → 4 → 2 → 5**

(0a 清地基;1c 快赢;1b 拆雷;1a 解锁;3/4 核心能力;2 验证;5 体验)

---

## 状态追踪

| Phase | 状态 | 备注 |
|---|---|---|
| 0a 退役 assembly 后端 | ✅ 完成 (2026-07-08) | 854 passed + 1 xfailed;3 expander 内化,assembly_builder + 2 测试 + rooted.ts + show_assemblies 删除 |
| 0b 工具盘点 | ✅ 完成 (2026-07-08) | exprs 退役;tools.md 重写(删死工具+补全 live 面+决策表) |
| 1c project_status | ✅ 完成 (2026-07-08) | node_utils+tool_executor+project.ts;3 hython 铁证 |
| 1b 重连安全 | ✅ 完成 (2026-07-08) | internal_chain_ready 强化(验接线)+ xfail→pass;connect_nodes 防御延后 |
| 1a 参数引用 | ⏳ | 高风险,opt-in→默认 |
| 3 emit_markers | ✅ 完成 (2026-07-08) | builder.emit_markers + add_anchors 跨调用覆盖 bug 修复;3 hython 铁证 |
| 4 组件原型 | ⏳ | 核心解锁 |
| 2 verify_robust | ✅ 完成 (2026-07-08) | node_utils.verify_robust + harness.ts;3 hython 铁证 |
| 5 组件迭代 | ⏳ | |

---

## 6. 完成记录

### ✅ Phase 0a — 退役 build_assembly 后端(2026-07-08)

**目标**:单一程序化管线,消除 assembly 与 project 两套并存 + `vex_strategies` 两头伺候的维护债。

**改动**:
- **内化**:`_expand_pickets_count` / `_expand_repeat_cells` / `_expand_shelf_layers` 从 `assembly_builder.py` 搬入 `vex_strategies.py`。`PicketStrategy` / `CellsStrategy` / `ShelfStrategy` 各自的 `build()` 现在自行解析 sugar(count / fill=repeat / layers)——**策略自足,无需外部 builder**。
- **删除**(git 保留历史):`assembly_builder.py`、`test_assembly_builder.py`、`test_assembly_hython.py`、`pi-extensions/edini-tools/tools/rooted.ts`、`scripts/show_assemblies.py`。
- **清理**:`tool_executor.py`(import + wrapper 函数 + handler + 归档注释)、`index.ts`(rootedTools import/spread)、`scripts/verify_vex_strategies.py`(改 expander 导入源)、`project/node.py`(3 处把 HDA 描述成 build_assembly 容器的误导注释)、`node_utils.py` + `mock_hou.py`(2 处过期引用)。
- **补测**:`test_vex_strategies.py` +9 测(5 个 expander 纯逻辑 + 4 个 strategy build() sugar 解析)——补回随 `test_assembly_builder` 退役丢失的 expander 覆盖。

**验证**:`854 passed, 1 xfailed, 0 failures`。删除的 ~100 测全是退役 assembly 代码的测(随代码归档,非回归)。`measure.py`(oracle + `_parse_axes/_parse_face/_rule_rot`)留作 vex_strategies 的依赖与测试 oracle。

**未决(转 0b)**:`exprs.py` 现仅被 `test_exprs.py` 用(project 路径用原生 ch() 不用它),评估是否一并退役。真机 hython 对 vex_strategies 的覆盖现为手动(`scripts/verify_vex_strategies.py`),可考虑沉淀为 pytest `test_vex_strategies_hython.py`。

### ✅ Phase 0b — 工具面盘点 + 分类重组(2026-07-08)

**目标**:工具完整且分类合理;清理过期误导内容。

**改动**:
- **退役 `exprs.py`** + `test_exprs.py`:确认 live 代码零引用(assembly/asset 退役后无消费者;project 路径用原生 ch())。-80 测随代码归档。
- **重写 `wiki/pages/tools.md`**:旧版严重过期——列着早已退役的 `build_procedural_asset`/`validate_recipe`/`build_component`/`assemble_components`/`houdini_variant_scatter`,却**完全缺失** Project HDA 工具集、recipe 库、verify_parametric、knowledge/eval。新版按功能分 10 类 + 重叠工具决策表(inspect_health vs inspect_geo vs geometry_inventory vs verify_parametric)+ 已退役清单。
- **保留** 7 个向后兼容别名(`_TOOL_ALIASES`)——agent 不可见,供历史 Pi 配置平滑过渡,移除风险大于收益。

**验证**:`774 passed, 1 xfailed, 0 failures`(854 - 80 test_exprs = 774)。

**未决**:真机 hython 对 vex_strategies 的覆盖现为手动(`verify_vex_strategies.py`),可沉淀为 pytest(低优先,纯测试基建)。`procedural-harness.md` wiki 页仍述旧 harness,后续可清理(非阻塞)。

### ✅ Phase 1c — project_status 聚合工具(2026-07-08)

**目标**:消除 agent 的"N 次逐组件状态收集"税(卡点 6)。一次调用给出全项目完成度。

**实现**:
- `node_utils.py::project_status(core_path)`:遍历声明里的每个组件,报 `geo_flow`(ok/empty/broken/no_scaffold/missing_subnet)+ prim/point count + `anchors{declared,emitted,missing}`(ports.out 声明 vs `anchor_<name>` wrangle)+ 子树 errors/warnings。`overall` 汇总 with_geometry / with_all_anchors / with_errors / complete + `incomplete` 列表。只读、非破坏。
- `tool_executor.py` 注册 handler;`project.ts` 加 TS 工具(含 promptGuidelines 教 agent 何时用)。
- agent 面向:`edini-context` 系统 prompt 的验证流程加入"Project HDA 先调 project_status"。

**验证**:`781 passed + 1 xfailed`。**3 条真机 hython 铁证**(Houdini 21.0.440 实测):建好 tabletop(盒+4 锚)报 `geo_flow:ok / 4-of-4 anchors / 0 errors`、未建 legs+shelf 报 `empty`、overall 正确 tally(`with_geometry:1 / complete:1 / incomplete:[legs,shelf]`,tabletop 不在 incomplete)。纯逻辑 `_declared_anchor_names` 4 测。

### ✅ Phase 1b — 子网内部重连安全(2026-07-08)

**目标**:闭合 session-logs-analysis 标记的 xfail——`internal_chain_ready` 只查节点存在不查接线(断链误报 ready)。

**实现**:`builder.py::_collect_input_wires` 的链检查从"节点存在"升级为"**节点存在 + 真接线**":
- `_has_input(blast, 0)` — blast 接到 indirect(捕获 `setInput(0,None)` 断开)。
- `_input_name_is(clean, 0, blast)` — clean ← blast(按 name)。
- `_input_name_is(in_, 0, clean)` — in_ ← clean(按 name)。
- 新增 `_has_input` / `_input_name_is` helper(原 `_input_is` 用 path/identity 比 SubnetIndirectInput 失败——见踩坑)。

**踩坑**(SubnetIndirectInput 比较):初版 `_input_is` 用 `actual.path()==expected.path()` / identity 比较 blast 的输入(indirect)。**真机失败**:hou.Node 与 SubnetIndirectInput 对象跨查询不是 identity-equal,`.path()` 对 indirect 行为不稳 → 正链误报 not-ready。**正解**:clean/in_ 是普通节点,按 **name** 比稳;blast 的 indirect 输入只查"非 None"(捕获断开即可),不强行比对 indirect 对象。

**验证**:`782 passed, 0 failed, 0 xfailed`(原 1 xfail 转真 pass)。断链(setInput(0,None))→ `internal_chain_ready=False`;正链 → `True`。

**延后(可选)**:`houdini_connect_nodes` 对脚手架内部 filter/clean/in_ 节点的防御性 refuse + 引导。强化后的 ground-truth + project_status 已给 agent 准确的"链是否好/断"信号,agent 不必再手动重连(声明错误应改声明 + 重新 scaffold,幂等)。该防御为锦上添花,非阻塞,留作后续。

### ✅ Phase 3 — project_emit_markers(关闭 by_name 鸿沟)(2026-07-08)

**目标**:让 by_name 锚点的上游 marker 发射变成声明式一次调用(像 bbox 锚点一样容易),治发现 3 的根因——by_name 曾比 bbox 难(需手写 marker 发射 wrangle),所以 agent 永远退回 bbox 伪参数化。

**实现**:`builder.emit_markers(core, component_id, markers)` —— 每个 marker `{name, measure, ...}` 经 `build_mount_vex` 生成 wrangle,读组件主几何源(out_geometry 的输入),发射一个 `@name=<name>` 点,经幂等 `markers_merge` 并入 `out_geometry`。下游 `add_anchors(measure:"by_name", marker:<name>)` 即可取到该真实位置点。`tool_executor` 注册 + `project.ts` TS 工具 + promptGuidelines。

**顺带修复(add_anchors 跨调用覆盖)**:测试暴露的潜伏 bug——第二次单锚 `add_anchors` 调用 `setInput(0, new_only)` 覆盖了第一次的锚连线(因为旧逻辑只在单次调用多锚时才建 merge)。改为收集子网内**所有** `anchor_*` 节点合并(与 emit_markers 同模式),多次调用现在 APPEND 而非覆盖。

**验证**:`785 passed`。**3 条真机 hython 铁证**:by_name 锚点取到 emit 的 marker 落在真实顶 y=H=1.0(对照 bbox_center 在 y=0.5,证明取的是 marker 非 bbox);改 H→2.0 marker 跟到 y=2.0(by_name LIVE 跟随);重 emit 同名 marker 幂等(1 节点,不重复)。

### ✅ Phase 2 — verify_robust 区间验证(2026-07-08)

**目标**:把"稳定正确"从点采样升级为区间证明。`verify_parametric` 只证一个参数在一个扰动点驱动几何;`verify_robust` 证模型在**每个 design_param 的 min/default/max 全区间**保持非退化 + 无错——这才是"参数自由调整并保持稳定正确"的真正判据。

**实现**:`node_utils.verify_robust(node_path, core_path, params=None, samples="min_default_max")` —— 遍历声明的 design_params(或指定子集),对每个在其 min/default/max 采样、recook、断言 `points>0 且无 cook 错误`。参数隔离(扫完一个先还原再扫下一个)+ try/finally 兜底全还原(非破坏)。`tool_executor` 注册 + `harness.ts` verifyRobustTool + promptGuidelines。

**验证**:`788 passed`。**3 条真机 hython 铁证**:稳健模型(box 随 length)全区间 PASS(每采样有点 + 还原 length=1.2);脆弱模型(n=0 时几何消失)被检出 FAIL(fail_overall=False,n=0 采样点 0 点 + passed=False)。与 verify_parametric 互补:后者证"参数驱动几何(单点方向)",前者证"模型跨区间不崩"。
