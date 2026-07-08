# 🚀 开发进度

> 最后更新：2026-07-08（晚）&nbsp;|&nbsp; **🟢 第一性原理开发计划 — Phase 2(2b/2c/2d)完成：P0 archetype 全部数据化**。承接 DP1(spec 格式批准 + param_specs 校验增强)。**2b**：迁移 copy_array + tube_graph 到 spec —— 补 `collect_anchors`/`vex_tube_graph` op + 扩展 `node` op(type/$ref-params/inputs/tweaks/init_ctp_attribs)，移除 `_archetype_copy_array`/`_archetype_tube_graph`/`_build_tube_graph_vex` legacy 代码，`emit_component` 全 spec 驱动(无 legacy 回退)。5 hython 测零回归(vector leaf live 表达式 / 未知 parm loud-fail / tube_graph edges + radius 驱动)。**2c**：新增 `extrude_profile`(柱/管，rad1+height+tube→Polygon tweak)——**仅加 `archetypes/extrude_profile.py` spec 文件，零 emitter 改动**即工作，验证 P0 可扩展性赌注(加原型=加数据)。2 hython 测(参数化 + LIVE)。**2d**：ch() 统一由 emitter 完成(spec 全相对 ch()；box_panel 的 absolute-ch() stale docstring 随函数删除消除)；手搓保持绝对+repath(按设计)；更新 project.ts/builder.py 文档(4 原型全落地)。**Phase 2 完成 —— `builder.py` 不再有硬编码原型分发，加原型=加 spec 文件**。**新基线 822 passed = 76 hython-decisive + 746 mock/logic，零回归**(819 + 1 bad-size + 2 extrude_profile)。剩 Phase 3(意图闸)/4(拆 node_utils)/5(闭环,DP2)。
>
> 上一轮（2026-07-08 晚）&nbsp;|&nbsp; **🟢 第一性原理开发计划 — Phase 2a(DP1)：archetype 数据化 — box_panel 迁移到声明式 spec**。直击几何实现层 35% 瓶颈。**设计**：archetype 从 `builder.py` 命令式函数变成声明式 **Archetype Spec**(数据,非代码)—— `ops` 列表 + 固定 op 词汇表(`node`/`wire_out`/`emit_markers`;2b 补 `collect_anchors`/`vex_tube_graph`/`init_ctp_attribs`),由通用 `archetype_emitter.py` 解释。`$` 前缀引用 agent 运行时参数(`$size.0`→`params["size"][0]`);其余值：数字=字面量 / 字符串(无 `ch(`)=design_param 名→相对 ch() / `ch(` 串=表达式。emitter 复用 `_arch_node`/`_set_archetype_parm`/`emit_markers` → 继承幂等重建 + 相对 ch() 可迁移(Phase 1a)+ P0-2 loud-fail 全部能力。**加原型 = 加 `archetypes/<name>.py` spec 文件,零 emitter 改动**(P0 可扩展性赌注的核心)。**落地**：`archetypes/{__init__,box_panel}.py` + `archetype_emitter.py`(3 op);`builder.emit_component` 改"spec 优先 + legacy 回退"分发;移除 `_archetype_box_panel` 死代码 + 修 stale docstring(含 Phase 1a 遗留的"absolute ch()"误述)。**铁证(行为等价)**：7 box_panel hython 测全过(参数化/LIVE/幂等/marker 转发/相对 ch() 可迁移)+ copy_array/tube_graph legacy 回退 5 测 + snapshot 3 测 = **15 emit_component 测零回归**。**【DP1 暂停】**等你审查 spec 格式(长寿命契约)后推进 2b(迁移 copy_array+tube_graph + 新增 extrude_profile)。
>
> 上一轮（2026-07-08 晚）&nbsp;|&nbsp; **🟢 第一性原理开发计划 — Phase 1(1a+1b+1c)完成：hython 可见化 + 接口清理 + finalize 硬闸**。承接 U 型成熟度诊断（组织层/验证层已工业级，**几何实现层 35% 是瓶颈**）+ 9-Phase 重构（解决了"组织"没解决"能力"）。本轮起按"安全可信度 → P0 能力 → 上游防错 → 闭环"依赖序推进。**Phase 1a（治 P3 虚绿风险）**：`test_project_hython` 63 + `test_skill_workflow_hython` 5 = **68 个决定性 hython 测试**全 `@skipUnless(HYTHON)`，无 Houdini 机器跑 `pytest` 静默 skip → "N passed" 可能虚绿（`.github/workflows` 不存在，是本地 dev-machine 问题）。修法：① 抽 `tests/_hython.py` 共享 `find_hython()`——杀两文件各自复制的 `_find_hython`（pitfalls 记的复制粘贴债），并统一一个已发生的微妙漂移（project 版选最新版本 / skill_workflow 版取第一个找到 → 统一选最新）。② `conftest.py` 加 `pytest_report_header`：报头显式打印 `edini hython: AVAILABLE|NOT FOUND — decisive tests WILL run|SKIP` + 列出会 skip 的模块名（`-q` 模式外不可忽视）。③ 新增 `--edini-require-hython` flag + `EDINI_REQUIRE_HYTHON=1` env：开启后 hython 缺失在 `pytest_configure` 直接 `pytest.exit(rc=1)`（非静默 skip）。④ `tests/test_hython_gate.py` 6 单元测覆盖闸门逻辑（monkeypatch HYTHON + stub config，测真 conftest 函数）。**铁证**：本机 hython 21.0.440 实跑，project_hython 63 passed（202s）+ 其余 = **814 passed，零回归**（808 基线 + 6 闸门测）。**新基线纪律**：测试数从此拆 `hython-passed` / `mock-passed` 两栏报，不再混报单数字（814 = 68 hython-decisive + 746 mock/logic）。顺带（1b 项提前）：`conftest.py` `reload_edini_modules` docstring 的 `assembly_builder`/`exprs` 悬空示例改为 live 模块。**1b（接口清理）**：移 `add_parm` 死接口出 `TOOL_HANDLERS`（无 TS 工具、官方路径禁建 subnet spare parm → 死表面；函数留 harness 内部）+ 修 `tool_executor` exprs 过期注释（exprs 已 Phase 0b 退役非 retained）+ `project.ts` 退役 `project_promote_params` TS 工具（Python handler 留历史兼容）+ 修 archetype 描述过期（误标 copy_array/tube_graph incremental）+ `edini-context` prompt 清 promote_params 工作流引用 + `measure.py` docstring 更新（rooted-modeling core → oracle+primitives；纯 Python 无 hou 运行时负担可忽略，primitives 抽取延至 Phase 4）+ 清 stale pyc。**1c（finalize 硬闸）**：新增 `project_finalize(core_path, acknowledge_skip, skip_reason)`——结构闸，跑 status+verify_robust+verify_parametric(per param)，FAIL 拒绝 finalize 并报 failures[]；acknowledge_skip+skip_reason 是审计逃生口（写 declaration log）；无 design_params 时参数化门 N/A。5 条 hython 铁证：robust 通过 / **dead param 被 parametric 门抓出（verify_robust 单独会漏——证两门都必要）** / incomplete 被状态门抓 / skip+reason 放行记 log / skip 无 reason 被拒。**新基线 819 passed = 73 hython-decisive + 746 mock/logic，零回归**（808 + 6 闸门 + 5 finalize）。
>
> 上一轮（2026-07-08 下午）&nbsp;|&nbsp; **🟢 重构后实测硬化 — archetype 静默失效 ×2 + 并发层（面板卡顿 / 连接断连）**。9-Phase 合并 master 后跑 5 个真实 Pi 会话实测（2 桌 + 2 键盘 + 1 复测）：**手搓节点路径零故障；archetype/grid 路径 + 并发层有硬化缺口**。分支 `refactor/archetype-fixes`（3 commit，**808 测试全绿**）逐条修掉。**P0-1**（`builder.py:759/897`）：多点锚点只命名 `__newpts[0]` → grid 75 点只剩 1 个到下游（键盘 75 键→1）；修为 `foreach` 全部命名。**复测铁证**：75 键直接成功，agent **零手补**（前两轮键盘各手补 1 次命名）。**P0-2**（`_set_archetype_parm`）：未知 parm `if p is None: return` 静默吞，copy_array `leaf.size=[...]` 丢光仍报 `success:true`；重写为委托 `node_utils._apply_one_param`（手搓同款 dispatch：向量/表达式/未知报错），**一套设参真相，原型与手搓同等能力**。**并发 A**：`append_stream_chunk` 每 token 重排整段 QLabel 文本 → 开面板抢主线程卡顿；**节流设施早就在但 `_flush_stream` 是 no-op 死代码** → 重激活既有定时器节流，零新 API、不碰全局状态。**并发 B**：`_write_response` 吞客户端超时断连，消除 `ConnectionAbortedError [WinError 10053]` 级联 traceback。详见下方「2026-07-08 重构后实测硬化」段 + [踩坑记录](pitfalls.md)。**暂缓**（按"最稳定可控"准绳）：P1-P3 archetype 项（leaf.type 解析 / 守卫误拦 / verify_parametric 阈值 / grid 数量参数化 / copy_array 贴面偏移）+ 图侧 manual-update（届时用 scoped context manager 带保证恢复，非裸全局开关）。
>
> 上一轮（2026-07-08 上午）：**🟢 程序化 agent 架构重构 — Phase 0a+0b+1c: 单一管线 + 工具盘点 + project_status 聚合**。承接第一性原理诊断（[诊断深度页](session-logs-analysis.md)）+ [9-Phase 重构计划](../../docs/superpowers/plans/2026-07-08-procedural-agent-refactor.md)，本轮启动系统性重构。**Phase 0a**：彻底退役 `build_assembly` 后端，消除 assembly 与 project 两套程序化管线并存的维护债 + `vex_strategies` 两头伺候。TS 工具面早已退役（`rootedTools=[]`），但后端 handler + `assembly_builder.py` 仍 live。**外科手术**：3 个预展开 helper（`_expand_pickets_count`/`_expand_repeat_cells`/`_expand_shelf_layers`）从 `assembly_builder` 内化进 `vex_strategies`，Picket/Cells/Shelf 三策略各自的 `build()` 自行解析 sugar（count/fill=repeat/layers）——**策略自足，无需外部 builder**（本就是更合理的架构：策略应 own 完整 spec→VEX 变换）。**删除**（git 保留历史）：`assembly_builder.py` + `test_assembly_builder.py` + `test_assembly_hython.py` + `pi-extensions/edini-tools/tools/rooted.ts` + `scripts/show_assemblies.py`。**清理**：`tool_executor`（import+wrapper+handler+归档注释）、`index.ts`（rootedTools import/spread）、`verify_vex_strategies.py` 导入源、`project/node.py` 3 处把 HDA 描述成 build_assembly 容器的误导注释、`node_utils`/`mock_hou` 2 处过期引用。**补测**：`test_vex_strategies.py` +9 测（5 个 expander 纯逻辑 + 4 个 strategy build() sugar 解析）——补回随 `test_assembly_builder` 退役丢失的 expander 覆盖。**854 passed + 1 xfailed，零回归**（删除的 ~100 测全是退役 assembly 代码的测，随代码归档非回归）。`measure.py` 留作 oracle + vex_strategies 依赖。未决（转 0b）：`exprs.py` 现仅 `test_exprs` 用（project 路径用原生 ch()），评估退役 → **Phase 0b 已退役**。**Phase 0b**（工具面盘点）：退役 `exprs.py` + `test_exprs`（确认 live 零引用）+ 重写 `wiki/pages/tools.md`（旧版列着已退役的 `build_procedural_asset`/`validate_recipe`/`build_component` 等死工具、却缺整个 Project HDA 工具集——严重过期误导；新版按功能分 10 类 + 重叠工具决策表 + 已退役清单）。**774 passed + 1 xfailed，零回归**（-80 个 test_exprs 测随 exprs 归档）。未决：真机 hython 对 vex_strategies 的覆盖现为手动，可沉淀为 pytest。**Phase 1c**（project_status 聚合工具，治卡点 6 "N 次逐组件状态收集税"）：新增 `project_status(core_path)` —— 一次调用快照每组件完成度（geo_flow ok|empty|broken / anchors{declared,emitted,missing} / errors）+ `overall.incomplete` 列表。node_utils 实现 + tool_executor 注册 + project.ts TS 工具 + edini-context 系统 prompt 引导。**3 条真机 hython 铁证**（本机 Houdini 21.0.440 实测）：建好 tabletop（盒+4 锚）报 ok/4-of-4/0 错、未建 legs/shelf 报 empty、overall 正确 tally（1 with_geo / 1 complete / incomplete=[legs,shelf]，tabletop 不在其中）。**781 passed + 1 xfailed，零回归**（+4 纯逻辑 +3 hython）。**Phase 1b**（子网内部重连安全，闭合 session-logs 的 xfail）：`builder.py::_collect_input_wires` 的 `internal_chain_ready` 从"只查节点存在"升级为"节点存在 + 真接线"（`_has_input(blast,0)` 捕获断开 + `_input_name_is` 按 name 验 clean←blast←... 链序）。踩坑：SubnetIndirectInput 跨查询非 identity-equal，`.path()` 不稳 → 改按普通节点 name 比 + blast 只查非 None。**782 passed + 0 xfailed**（原 1 xfail 转真 pass）：断链报 not-ready、正链报 ready。connect_nodes 防御性 refuse 延后（ground-truth + project_status 已给准确信号，非阻塞）。**Phase 3**（project_emit_markers，关闭 by_name 鸿沟，治发现 3 根因）：新增 `project_emit_markers(core, component_id, markers)` —— 声明式往组件几何里发射 `@name` 标记点（`build_mount_vex` 生成 wrangle，读主几何源，经幂等 `markers_merge` 并入 `out_geometry`），下游 `by_name` 锚点一次取到真实位置点。让 by_name 和 bbox 一样容易（不再需手写 marker 发射 wrangle）。**顺带修复** add_anchors 跨调用覆盖潜伏 bug（第二次单锚调用覆盖第一次的锚连线 → 改为收集所有 `anchor_*` 节点合并，APPEND 不覆盖）。**3 条真机 hython 铁证**：by_name 取到 marker 落真实顶 y=H=1.0（对照 bbox_center y=0.5）/ H→2.0 marker 跟到 y=2.0 LIVE / 重 emit 幂等。**785 passed，零回归**（+3 hython）。**Phase 2**（verify_robust 区间验证，"稳定正确"从点采样升级为区间证明）：新增 `verify_robust(node_path, core_path, params, samples)` —— 遍历 design_params 在 min/default/max 采样 recook，断言每点 `points>0 且无 cook 错误`。参数隔离 + try/finally 全还原（非破坏）。node_utils 实现 + tool_executor 注册 + harness.ts verifyRobustTool。**3 条真机 hython 铁证**：稳健模型（box 随 length）全区间 PASS + 还原 length=1.2；脆弱模型（n=0 几何消失）被检出 FAIL（n=0 采样 0 点）。与 verify_parametric 互补（单点方向 vs 全区间不崩）。**788 passed，零回归**（+3 hython）。**Phase 4**（组件原型化——核心能力解锁，治 step 3 头号失败：Python SOP 错误 7+ 次 / 错参名 / 断 ch 链）：新增 `project_emit_component(core, component_id, archetype, params)` dispatch + 3 原型（确定性节点名，replace-on-rebuild 幂等；值约定：数字=字面量，字符串=design_param 名→绝对 ch()）：**box_panel**（参数化 box，桌面/座面，可选 markers 转发）/ **copy_array**（CTP 把 leaf 盖到消费锚点，桌腿/辐条/键）/ **tube_graph**（命名锚点间建管子图，**用 VEX 替代 Python SOP** → 零 Python SOP 错误面，车架/fork/把手）。extrude_profile 延后（与 tube_graph 重叠，自定义截面 sweep 较 niche）。**9 条真机 hython 铁证**（box_panel 参数化+LIVE+幂等+marker 转发 / copy_array 4 锚点→4 实例 / tube_graph 3 边无错+radius 驱动）。**795 passed，零回归**（+7 hython）。**Phase 1a**（参数引用方案，稳进——治"组件不可迁移"）：原型生成器 `_set_archetype_parm` 的参数名分支从绝对 `ch('/obj/.../...')` 改为**相对** `ch("../../<p>")`（深度由 `_relative_path_to_core` 按节点实际位置算；原型节点是子网直接子节点→depth-2）。原型建的组件现在可迁移。手建 raw 节点保持绝对（不碰有风险的手建深度计算；agent 优先用原型自动相对，无原型匹配时手建+repath 迁移）。**3 条可迁移性真机 hython 铁证**：原型表达式是相对 `../../length`（非绝对）/ proj_A(length=1.2) box_panel 复制到 proj_B(length=3.0) → 副本读 proj_B 的 **3.0 非 1.2**（绝对引用必断）/ 迁移后改 length→2.5 副本 LIVE 跟变。**798 passed，零回归**（+3 hython）。**Phase 5**（组件级迭代——"有选择的多轮优化"）：3 个平台工具 `project_snapshot_component` / `project_restore_component` / `project_list_snapshots`。快照存 core 内 `_snapshots` 子网（非声明组件→OUT/inspect 跳过，随 .hip 持久化）；`copyNodesTo` 保留内外接线，相对 ch() 恢复后深度自洽。builder 实现 + tool_executor 注册 + project.ts。**3 条真机 hython 铁证**：快照→改→restore 回退（sizez 0.6→2.0→0.6）/ 相对 ref 幸存（sizex 仍读 length=1.2）/ list 记录 top_1。踩坑：copyNodesTo/destroy 使持有 handle 失效（ObjectWasDeleted）→ 平台工具无状态不受影响，harness 重 lookup。**801 passed，零回归**（+3 hython）。**9 Phase 全部完成** — 重构交付。留作增强：UI 版本列表（NodeVersionList 下沉到组件级）。
>
> 上一轮（2026-07-07）：**🟢 会话日志诊断修复的回归硬化（2 个真 bug + 补全缺测边界，含反向验证铁证）**。对上一轮治完的"发现 1-5 修复"（commit `1093eb4`）做行号级回归就绪审计，发现 **2 个违背各自工具安全契约的真 bug + 多处未测的脆弱边界**，本轮全部修硬。**真 bug ①（高，`node_utils.py:verify_parametric`）**——docstring 明写"ALWAYS restore"，但 perturb→recook→snapshot→errors 这段**没有 try/finally**。一旦 perturb 后的 cook 抛异常（恰恰是这个工具要检测的 cook 错误场景），控制跳到外层 except，参数留在 `new_value`，**静默改写用户场景**。修法：perturb/snapshot/errors 包进 try，restore 移到 finally（`parm.set(original_value)`+`cook(force=True)`+`_restored=True`），外层 except 用 `locals().get("_restored")` 报告真实 restore 状态。**反向验证铁证**：临时禁用 finally 后，`err_param_value_after` 变成 2.0（场景被污染），测试正确转红；恢复修复后回到 1.0，测试转绿——证明测试真的在测 restore 行为而非误绿。**真 bug ②（中高，`vex_strategies.py:_VEX_BY_NAME`）**——by_name marker 名拼错（几乎总是这个原因）→ `__found=0` → if 块跳过 → **静默产 0 点，无任何诊断**，agent 无法区分"marker 找不到"还是"上游几何为空"。修法（用户选 VEX `error()` 硬报错）：`if(__found)` 加 else 分支调 `error(sprintf(...marker...))` → cook 失败 → `node.errors()` 含诊断 → 现有 `inspect_health`/`verify_parametric` 链路自然拾取。符合项目 fail-fast 哲学（与 addpoint guard 一致），不需新通道，其他锚点 wrangle 各自独立 cook 不受影响。**小 bug ③（`node_utils.py:repath_to_relative`）**——`count = len(rewritten)` 把 `setExpression` 失败的也计入，agent 看到"N refs migrated"实则有静默失败。改为只数成功的 + 新增 `failed:[...]` 字段。**补全缺测边界**：审计发现 by_name/verify_parametric/repath 的 happy-path-only 覆盖——本轮加 9 测纯逻辑（`test_vex_strategies.py` 的 `_make_replacer` 全覆盖：`hou.ch` 形式 / 双引号 / 近名碰撞 `project_core_backup` / 多层 parm_tail 拒绝 / 非 core 引用）+ 4 测真机 hython（`test_project_hython.py::TestHardeningEdgeCasesHython`：restore-on-cook-error / by_name 零匹配报错 / repath hou.ch 改写 / repath 近名碰撞不动）+ 1 测 expectedFailure（`internal_chain_ready` 只查节点存在不查接线——审计脆弱点，本轮诚实记录待下轮）。**全量回归 946 passed + 1 xfailed + 2 subtests，零回归**（基线 933 → +13）。本机实装 hython（Houdini 21.0.440），真机铁证**实测跑过**（非 skip）。MISTAKES.md +2 行（by_name 零匹配诊断 / verify_parametric restore 保证）。
>
> 上一轮（2026-07-07）：**🟢 发现 4 收尾：promote_params 矛盾的文档对齐 + 新增 repath_to_relative 组件可迁移工具（8 条真机 hython 铁证）**。承接 A/B/C 三层，本轮治掉诊断里**唯一剩余的发现 4**（promote_params 永远返回 0 的 workflow 设计矛盾）。代码级取证后发现这是 **SKILL.md 教了三条互相排斥的参数化路径**（①绝对 ch 直引 core design_params / ②subnet spare parm + 相对 ch / ③promote），agent 选了 ①（最省事），②③就废了——promote 只扫 subnet `spareParms()`，①从不建 subnet parm → 返回 0 是必然，不是 bug。讨论了四个解法（A 文档对齐 / B promote 读声明自动接线 / C 强制单一相对路径 / D 文档+repath 工具），选 **方案 D**（不破坏已落地的 A/B/C，且诚实承认绝对路径是稳定默认，相对路径历史上有"零几何"事故）。落地：① **文档对齐**——SKILL.md Step 3 改为"绝对 ch 是唯一官方路径，禁建 subnet spare parm"；Step 4 重写为"promote 在 design_params 路径下是 no-op，返回 0 正常；LIVE 硬门由 verify_parametric 接管"；新增 Step 4b 介绍可选 repath；MISTAKES.md +3 条（promote 返回 0 正常 / 几何不动用 verify_parametric 查 / 组件迁移用 repath）；TS 代理 project_promote_params 描述改为 legacy/no-op 说明。② **新增 `project_repath_to_relative` 工具**（node_utils.py `repath_to_relative` + `_relative_path_to_core` 路径深度计算 + tool_executor 注册 + TS 代理）——单组件粒度，遍历组件子树所有节点的表达式，正则匹配 `ch('.../project_core/<p>')` 与 `hou.ch(...)`，按节点实际路径深度重写为 `ch("../../<p>")`。实施中发现并修正一个文档错误（初版写 `../../../` 3 级，hython 实测 core 在组件内几何的 2 级之上，应为 `../../`，已改为深度计算而非硬编码）。**8 条真机 hython 铁证**（全 PASS）：repath 把绝对 ch 改写成相对且无残留 / repath 前后 bbox 完全不变（只改记法不改链接）/ repath 后参数仍 live（length 1.5→3 sizex 跟到 3.0）/**把组件复制到另一个 project 仍能 cook 并读到新 core 的 length=2.0**（绝对路径下必断）+ 4 条 `_relative_path_to_core` 纯逻辑路径深度测试。**至此诊断的五个缺陷全部治完**（1→A / 2→B / 3→C1 / 4→本轮 / 5→C2）。**933 测试全绿**。详见 [会话日志第一性原理诊断](session-logs-analysis.md)（发现 4 已标注 ✅ 已解决）。
>
> 上一轮（2026-07-07）：**🟢 双建模会话日志诊断 → A/B/C 三层第一性原理修复全部落地（含 13 条真机 hython 铁证）**。承接上轮的诊断，本轮**按依赖性依次实施 A→B→C 三层**，治掉会话日志暴露的五个真实缺陷。**Layer A（平台层，治"接线错觉"）**——`build_project_scaffold` 返回值新增 `input_wires[]` ground-truth 字段：遍历每个 `ports.in`，读 `subnet.inputConnections()` + `subnet.input(i)` 报告每根线的真实状态（`wired` / `port_matches` / `carries:"geometry"|"anchors"` / `internal_chain_ready`）。消灭桌子日志那 10 分钟"模型不信任已正确接好的脚手架 → 重连子网内部 filter 失败 → sandbox 断链 → 自己删 filter 链退回硬编码"挣扎——模型现在看到 `port_matches:true` 就放心往下建。期间发现并绕过一个 Houdini API 坑：`hou.NodeConnection.outputNode()` 在 subnet 连接上返回的是**下游**节点而非源节点（误导性命名），改用 `subnet.input(i)` 取真实上游。**Layer B（知识层，治"Python SOP 知识缺口系统性复发 7+ 次"）**——纯 prompt，零平台代码。新增 `skills/project-modeling/COMPONENT_TEMPLATE.md`：固化组件生成器骨架（守卫包裹禁 bare `return` / 先 `addAttrib` 再 `setAttribValue` / 读输入用 `inputs()[0].geometry()` 而非 `node.geometry()` / `createPoint()+setPosition(hou.Vector3)` / `hou.ch` 非 `ch`）+ 7 项完成 checklist；SKILL.md 第 3 步链接它；MISTAKES.md 补 6 条症状→根因→fix（5 条 Python SOP + 1 条接线信任）；DISCIPLINE.md 明确"sandbox 无输入 ≠ 组件生成器"。**Layer C1（工作流层，治"锚点测量全 bbox 派生致参数化只是表象"，bike 最致命）**——`vex_strategies.py` 新增第 7 个静态策略 `by_name`：根组件生成器在真实几何位置输出带 `@name` 的语义标记点（如 `head_tube_top` 落在真实头管顶端），下游锚点用 `measure:"by_name"+marker:"head_tube_top"` 取该精确点，而非从 bbox 面中心派生。VEX 不用 `_VEX_CLEAR`（要保留匹配点的真实位置），单遍扫描捕获 P+orient 后清空再重发；`builder.py` 参数安装循环改成类型感知（string marker 用 StringParmTemplate，且剥离 `_` 前缀）。**Layer C2（工作流层，治"bike 跳过参数联动验证违反 premature-done 诫令"）**——新增 `verify_parametric` 工具（python 实现于 node_utils.py + tool_executor 注册 + TS 代理 verifyParametricTool）：扰动一个 design_param → recook → 量化验证几何在预期轴变化 ≥5% → **永远还原原值（非破坏性）**；拒绝 no-op 扰动（防空过假阳性）。这是"模型真的完成了吗？"的硬门——`inspect_health` 的 `overall_ok` 只证明"此刻没坏"，不证明"参数化成立"。**13 条真机 hython 铁证**（全部 PASS）：A=input_wires 报 ground-truth（shelf 声明 port:1 → `port_matches:true, carries:"anchors"`；对照 port:0 → `carries:"geometry"`）；C1=by_name 锚点落在真实顶 y=1.0 而非 bbox 中心 y=0.5，height 1→2 时 live 跟到 y=2.0，且与 bbox_center（y=1.0）明确不同；C2=live 链接 PASS / dead 链 FAIL 带诊断 / 参数还原到原值 / no-op 被拒。修复一个 latent 测试断言（`_STATIC_STRATEGIES` 6→7）。**324 测试全绿**（含 hython）。详见 [会话日志第一性原理诊断](session-logs-analysis.md)（已更新标注 A/B/C 落地状态）。
>
> 上一轮（2026-07-07）：**🟢 双建模会话日志第一性原理诊断（含 output_index 误判修正）→ 沉淀诊断 + A/B/C 路线图**。分析两个真实程序化建模会话日志（**桌子** 3 组件线性链 ~15min / **公路车** 7 组件 DAG ~10min），从第一性原理诊断 Edini 程序化建模 agent 的系统性缺陷。**本轮纯文档，未动任何代码**。核心：① **明确修正了第一版"output_index scaffold bug"误判**——读 `builder.py:292` 证伪（scaffold 用声明的 `ports.in[].port` 接线，shelf 声明 `port:1` 是对的，scaffold 没接错）；真实根因是"模型不信任已正确接好的脚手架 → 重连子网内部 filter 失败 → sandbox setInput 断链 → 自己删 filter 链退回 Object Merge 硬编码"那 10 分钟挣扎。② 归类五个真实缺陷（接线错觉 / Python SOP 知识缺口系统性复发 7+ 次 / 锚点测量全 bbox 派生致参数化只是表象 / promote_params 返回 0 是 workflow 设计矛盾 / bike 跳过参数联动验证违反 premature-done 诫令）。③ 给出 A/B/C 三层改进路线图（A=scaffold 回报接线 ground-truth，杠杆最高；B=Python SOP 组件模板，纯 prompt；C=named-marker 锚点 + verify_parametric 扰动验证门，最治本）—— **本轮一律不实施，待下轮决定**。方法论教训沉淀：凡断言"平台 X 行为错误"，必先 grep 到源码行号佐证，否则归为"模型行为/文档缺口"先排除。新增 [会话日志第一性原理诊断](session-logs-analysis.md) 深度页 + [踩坑记录](pitfalls.md) 两条。详见该深度页。
>
> 上一轮（2026-07-07）：**🟢 椅子建模日志驱动的工具层 + 连接修复（会话日志第一性原理分析 → P0 工具改进 + disconnected 根因定位）**。分析椅子建模会话日志（144 次调用 / ~8 轮浪费），从第一性原理诊断 skill/工具/架构三层问题，落地两个 P0 工具层改进 + 修复 HDA 对话框 disconnected。① **forwardTool 共享 + 错误处理**——9 个工具文件各自复制了一份无 try/catch 的 forwardTool，网络抖动抛成裸 `fetch failed`（日志里 3 次 connect_nodes 死于此）。抽出唯一共享 `_shared.ts`：try/catch + 瞬时错误重试 2 次 + 30s 超时 + 结构化错误体 `{success, error, hint, transient, retryable}`。② **create_node 返回参数清单**——日志里模型给 line SOP 写 `length`，失败后才发现真名 `dist`（5 轮浪费）。`create_node` 现返回 `parms` 字段（真实 name/type/components/menu tokens），agent 创建即知参数名，`_node_parm_inventory` 双路径（type.parmTemplateGroup 优先，回退 node.parms）。③ **disconnected 根因修复**——Pi 子进程用 `CREATE_NO_WINDOW` 但缺 `CREATE_NEW_PROCESS_GROUP`，共享 Houdini 控制台会话 → 被控制事件以 `0xC000013A` (STATUS_CONTROL_C_EXIT) 击杀（启动 ~2s 后死，无 stderr）。加进程组隔离 + 进程退出检测（Pi 退出时 emit 带 exit code 的真实错误，不再卡假 connected）。新建 `diagnose_rpc.py` 诊断工具（精确识别 0xC000013A）。**906 测试全绿**。
>
> 上一轮（2026-07-07）：**🟢 程序化建模 skill 从第一性原理重构 + 测试基建修复**。对照 mattpocock 的 `writing-great-skills` 框架，对 `project-modeling/SKILL.md` 做了系统性优化。核心：确立 3 个 leading words（`measure`/`anchor`/`scaffold`）贯穿 **prompt 层（skill）+ platform 层（guards.py 报错 + 工具 description + 系统 prompt）** 双层强化；新增对抗性 intro（"agent 默认会怎样搞砸"）；4 步工作流每步加 ✅ completion criterion（治 premature completion）；progressive disclosure 拆分为 4 文件（主文件 316→230 行 + MISTAKES/DISCIPLINE/PORT_PROTOCOL 子文件）。新增 `test_skill_workflow_hython.py`（5 测）用真机 hython 端到端验证每个 criterion 可检查——**最关键的是证明了 "measure 锚点是 LIVE 的"：改 length 参数→bbox 变→锚点 X 坐标真的跟着移动**。同步修复测试基建两个潜伏 bug（`startswith("edini")` 全局清空污染 chat 类身份 / Python 3.14 subprocess WinError 6 句柄竞争）。**901 测试全绿**。
>
> 上一轮（2026-07-06）：**🟢 会话日志驱动的平台契约强化（三轮 fix-observe-refix）**。分析三份真实 agent 建模会话日志（"做一个椅子"），逐轮从第一性原理定位问题并修复。核心：把建模契约从 SKILL.md 散文变成 **fail-fast 平台结构**（拒绝错误行为 + 开放正确通道）。三轮 11 个修复：addpoint 守卫 / 锚点路由净化（Blast + prim-strip）/ tag_component 拆分（agent-可编辑 + 内部锁死的 __edini_axis_bake）/ per-component `axis` 声明 / verify_orientation 的 construction_axis 真正生效 / 参数名建议 / sandbox 契约自文档 / canonical 工具名 / tube type 提示。净效果：会话1（120 调用/4 失败/2 沙箱）→ 会话3（**55 调用/1 失败/0 沙箱/0 锚点泄漏**）。848 测试 + 18 hython 铁证。详见 [组件地基指南](project-component-foundation.md) + 第四十一阶段卡片。
>
> 上一轮（2026-07-05）：**🟢 统一对话窗口架构完成 + 工具链全量修复**。主 Agent 窗口与 HDA 建模窗口重构为共享组件库 + 配置差异化架构。HDA 窗口从简陋 QDialog 升级为完整三面板（橙色 #f59e0b 差异化 + 版本列表 + 参数快照 + workspace lock）。agent_panel 1951→958 行。121 测试 + 2 个架构守卫。同步修复 15+ 个工具链 bug（Ramp 序列化 / set_params_batch 向量 / ports 逐字段报错 / `__edini_state` 复用检查 / brainstorm 双重注册 / design_params 断层）。详见 [统一对话窗口](unified-chat.md)。
>
> 上一轮（2026-07-03）：**🟢 Project HDA 组件流水线成熟 — 锚点程序化 + 参数自底向上 + HDA 按钮弹窗**。Project HDA 已从"最小闭环"演进为**组件流水线建模范式**（subnet 组件 + 端口信息点协议 + 程序化锚点 + 自底向上参数管理）。三大 UX 改进：① **工作区感知**（project_create 复用选中 HDA）；② **参数自底向上**（subnet 建→promote 按分组提到 core 带 min/max，core 驱动 subnet）；③ **HDA 参数面板 💬 Chat 按钮 → 精简对话弹窗**（取代原生 Python Pane 主入口，工作区统一在 HDA）。锚点不再硬编码（复用 vex_strategies 测量，改参数 live 重算）。**真机铁证**：promote 分组+min/max+live；HDA button+PythonModule 注入；锚点 length 2→4 ±1→±2。详见 [交接](handoff.md) + [组件地基指南](project-component-foundation.md)。
>
> 上一轮（rooted-modeling）：M2.6+M2.7 — 真机测试驱动的三大修复（leaf 参数全 live + 视觉自检 + shape 链细节），607 测试 + 26 真机 hython 铁证全绿。Project HDA 是在其上的**容器化 + 协作化升级**，不是取代——rooted 的 build_assembly/测量链是 Project HDA 将来"按需接入"的建模能力。

## ⚠️ 重大架构转向（2026-06-29）：rooted-modeling 取代声明式资产管道

**为什么转向**：声明式资产管道（asset_model + 骨架点 DAG + asset_builder）的 build 层是「**测一次、烤成字面值**」——build 时测对 root 几何算出坐标，但写进 xform 的 `t`/`r`/`scale` 后就死了。用户改 root 参数（如车的 `length`），4 个轮子的 xform 还写着旧坐标，纹丝不动。这违背程序化建模的核心承诺——**live 参数化**。

**新方向（rooted-modeling）**：用户一句话定义了本质——「**先做根件（车架/底座/房子外壳），再用根件的真实几何去算出所有其他组件的位置**，不能硬编码」。落地为 4 角色：Root（根基，先建）→ Mount（位置+朝向，**测量** cooked 几何得到）→ Shape（叶子资产，形态独立）→ Leaf（摆到 Mount 上）。

**关键技术决策**（用户拍板）：用 **VEX + Copy to Points** 实现 live，但**不让 LLM 写 VEX**——每种测量原语对应一段**预制 VEX 策略**（Python 解析符号串→注入数字），agent 只选策略+参数。这绕开了项目历史上 VEX 翻车的根因（LLM 手写 VEX 出错率高）。

**里程碑进展**：

| 里程碑 | 内容 | 状态 |
|--------|------|------|
| **M0** | measure.py 测量层（bbox 角点/面中心/边点/方向/朝向）+ assembly_builder（xform 版）+ 小车 4 轮 + SKILL | ✅ 交付（459→489 测试） |
| **M1** | grid_on_face（键盘网格）+ array（阶梯阵列）fan-out | ✅ 交付（489→499 测试） |
| **M2** | **live 关联**：vex_strategies.py 预制 VEX + 重写 build 层为 attribwrangle+CTP + root 参数暴露为 spare parm | ✅ 交付（502 测试，**含真机 hython live recook 铁证**） |
| **M2.5** | **leaf align convention**：orient point-class 修复 + `align_axis` 可配 + `leaf.origin` 规范化 + 分组 CTP | ✅ 交付（151 测试，**含 9 真机 hython wheel-facing 铁证**） |
| **M3** | **cells 测量原语 + 三层类架构 + square/fill**：显式布局表（1u 网格，6.25u 空格/staggered/gap/per-point v@scale）+ VexStrategy 三层类重构 + square 正方约束 + pad/repeat/stretch 三填满模式 + Pi agent 端到端链路修复 | ✅ 交付（599 测试，**含 5 真机 hython 铁证：square 键 X==Z / pad 留白 / repeat 增量 / live 重排 / one-CTP-many-sizes**） |

**真机铁证**（Houdini 21.0.440，本机 `C:\Program Files\Side Effects Software\Houdini 21.0.440\bin\hython.exe`）：
```
车：length 4→8，recook（不重建）→ 前轮 (+2,-0.25,+1) → (+4,-0.25,+1) [MOVED live]
键盘：tray_width 16→24，recook → 65 键正方形布局自动重排填满 [MOVED live, square]
阶梯：3 踏步对角攀升 (run=0.5, rise=0.3)
cells: 8 策略 vs 预言机全过（stretch/square/pad 三模式 ratio=6.250 守恒）
square 键 bbox X==Z（正方），pad 居中留白不溢出，repeat 自动增量键数 >6
```

**新 skill 文件**：`python3.11libs/edini/{measure,vex_strategies,assembly_builder}.py` + `skills/rooted-modeling/SKILL.md` + `pi-extensions/edini-tools/tools/rooted.ts` + `tests/test_{measure,assembly_builder,assembly_hython}.py` + `scripts/{verify_vex_strategies,show_assemblies}.py`。

**✅ 已发现并修复的 leaf 层问题**（用户 2026-06-29 实测发现 → M2.5 全部修复）：
- 用户在 Houdini GUI 打开 `edini_showcase.hip` 后发现 4 个 leaf 层问题（orient 不生效 / 朝向硬编码 / 无原点规范化 / 重复几何）。**M2.5（本次交付）已全部修复**：systematic-debugging 走完整流程，hython facing 测试作决定性验证，并纠正了 spec 的事实错误（torus 轴是 +Y 非 +Z）。详见下方 M2.5 时间线卡片。`edini_showcase.hip` 已重新生成（含 car + bicycle + keyboard + stairs 四例）。

---


## ⚠️ 架构转向说明（2026-06-23 → 06-26 三次演进）

**重要**：旧的程序化建模管道（提示词驱动 + validate_recipe/build_procedural_asset/G1-G3 闸门）
曾**关闭并备份**到 `_disabled_backup/procedural-modeling/`。根因：LLM 对 Houdini 不熟，
靠提示词规则无论写多细还是会出错——这是概率模型的本质缺陷。

但经过多轮会话日志分析（水管/自行车/水管-v2/v3），发现**根因不是"思路错"，而是"规则跑在能力前面"**——
skill 强制 agent 走 `build_procedural_asset`，但底层工具（组件构建器/骨架点/表达式引擎）没跟上，
agent 够不着，只能退回 sandbox，再被门禁拒。**门禁编码了正确的领域知识，但 agent 没有满足门禁的手段，
于是变成死循环。**

**2026-06-26 第三次演进（当前方向）= 声明式资产管道（自底向上重启）**：
不再先写 skill 规则，而是从地基往上逐层做，每层独立可跑。复用 `_disabled_backup` 里已有的
高质量前身（`exprs.py` 表达式引擎、`recipe_validator.py` 的 DAG 循环检测、`component_registry.py`），
但补上**之前缺失的核心创新——全局骨架点 DAG**（旧设计是组件自带 anchors，新设计是所有组件
挂载到一张共享骨架点表上，组件之间不互相看见，只看见骨架点）。

核心流程（6 阶段）：**拆分组件 → 骨架点 DAG → 盒子占位 → 参数库 → native 节点链实现 → 组装提交**。
详细设计见下方"下一步计划"。里程碑1（骨架点 + 表达式引擎）**已交付，待真实 Houdini 实测**。

**2026-06-25 二次定位（仍有效）**：recipe 定位为「参考样本」（python_script + manifest 降噪），
recipe 降低 LLM 的语法出错率，但不限死其能力。这条定位在资产管道里继续生效——
recipe 教惯用法，资产管道教结构。

下方旧的「程序化建模」阶段卡片保留作为历史记录。

## 总览看板

<div class="phase-grid">

<div class="phase-card">
  <div class="phase-card-header">
    <span class="phase-card-title">🦴 声明式资产管道 — 里程碑1（骨架点 DAG + 表达式引擎）</span>
    <span class="status-tag status-done">交付 · 真机实测通过 ✅</span>
  </div>
  <div class="progress-bar-bg"><div class="progress-bar-fill progress-done" style="width:30%"></div></div>
  <div class="phase-card-detail">程序化建模<strong>自底向上重启</strong>的第一层地基。核心创新 = <strong>全局骨架点 DAG</strong>：所有组件挂载到一张参数驱动的骨架点表上，组件之间不互相看见，只看见骨架点。这解决旧设计"组件自带 anchors 各自摆位、改参数全乱"的致命缺陷。<strong>三模块（纯 Python，无 hou 依赖）</strong>：① <code>exprs.py</code>（从 _disabled_backup 搬回 + 扩展）：安全 AST 表达式引擎，<code>evaluate</code>/<code>evaluate_tuple</code>/<code>extract_refs</code>，新增 <code>Name[int]</code> 下标支持（点引用语法 <code>rear_axle[0]</code>）。② <code>skeleton_resolver.py</code>：骨架点 DAG 拓扑求值（Kahn 排序 + 环检测 + 点引用解析）。③ <code>asset_model.py</code>：资产 JSON 三段结构（params/skeleton/components）+ validate（参数库 kinds + 骨架循环/悬空/语法）+ resolve（derived 参数先按依赖序求值，再求骨架点）。<strong>一个工具</strong>：<code>validate_asset</code>（纯数据验证，shift-left，无 Houdini 代价；resolve=true 预览所有骨架点坐标）。已注册 tool_executor + TS schema。<strong>样例</strong>：<code>bicycle.asset.json</code>（10 参数 + 5 骨架点，验证+求值全通过，bb_center 数学已修正为物理正确的水平投影）。<strong>实测完成（2026-06-26）</strong>：补全 5 个测试文件 162 测试全绿 + hython 真机端到端 5 项（Houdini 21.0.440 子进程 import hou + validate_asset 返回 5 点骨架）。实测暴露并修复 2 bug：exprs 的 round(ndigits) 被 float 化 + asset_model 在 params 非对象时崩溃。<strong>M1 实测通过，可启动 M2 组件构建</strong>。</div>
</div>

<div class="phase-card">
  <div class="phase-card-header">
    <span class="phase-card-title">🧱 声明式资产管道 — 里程碑2（组件构建 · 完整能力）</span>
    <span class="status-tag status-done">交付 · 真机生成自行车 ✅</span>
  </div>
  <div class="progress-bar-bg"><div class="progress-bar-fill progress-done" style="width:70%"></div></div>
  <div class="phase-card-detail">让 <code>components[]</code> 真正生成几何并挂到 M1 骨架点上。<strong>核心契约</strong>：组件引用骨架点<strong>名</strong>（不是私有坐标表达式）——消灭旧设计"组件自带 anchor 各自摆位、改参数全乱"的缺陷。<strong>分层重构</strong>：asset_model.py（纯数据校验）+ 新建 asset_builder.py（几何构造层，依赖 hou）。<strong>两个 backend</strong>：① <code>native_chain</code>（native SOP 节点链，从 git 移植助手 + 8 个 H21 workaround）；② <code>python</code>（Python SOP 画曲线/截面，<strong>值注入</strong>参数——agent 代码用参数名当变量，builder AST 安全替换成数值，永不碰 hou.ch）。故意不做 vex_skeleton（VEX 是旧管道失败根因）。<strong>三种 placement</strong>：① <code>attach.position</code>（单实例）；② <code>instances[]</code>（1 定义 + N 实例 transform 复制，替代旧 CTP stamping）；③ <strong><code>from</code>/<code>to</code> 两点连接</strong>（管材/桁架核心原语——builder 自动算中点/长度/朝向，agent 永不算角度，用 axis-angle→四元数→欧拉无万向锁）。<strong>orient 旋转</strong>（attach/instance 的 Euler 度）。<strong>真机实测</strong>（Houdini 21.0.440）：table（168 点，多实例桌腿+python 圆环）、chair（112 点，orient 倾斜靠背）、<strong>bicycle（224 点：4 from-to 车架管材 + 2 python 轮子，零 cook 错误，上管长度自动=两点距离）</strong>。<strong>实战测试价值</strong>：椅子→自行车递进暴露并修复 3 真实缺陷（无朝向→orient / orient 静默忽略→校验 / 无两点连接→from-to），这是 M3 抓不到的。<strong>skill</strong>：asset-authoring/SKILL.md 沉淀实战约定。<strong>测试</strong>：纯 Python + mock hou + hython 真机三层共 240+ 测试全绿，全量回归 581 passed 零回归。</div>
</div>

<div class="phase-card">
  <div class="phase-card-header">
    <span class="phase-card-title">🔧 声明式资产管道 — 里程碑4（组装提交 · 标记+绕过策略）</span>
    <span class="status-tag status-done">交付 · 真机待测</span>
  </div>
  <div class="progress-bar-bg"><div class="progress-bar-fill progress-done" style="width:90%"></div></div>
  <div class="phase-card-detail">让 <code>build_asset</code> 的 sandbox 结果能 <code>commit_sandbox</code> 固化成正式节点——资产从"预览"到"产出"的最后一环。<strong>核心冲突识别</strong>：现有 G3 门禁（commit_sandbox）是为旧提示词管道设计的，会<strong>误判声明式资产</strong>——G3a bake 门禁要求每个 component_id prim 烘焙 <code>edini_world_axis</code>，但 builder 故意不烘焙（方向靠骨架点 DAG 确定）；G3b PCA 方向门禁要 agent 供应 orientation_checks 跑 PCA，而 PCA 正是被否决的不可靠估计（hub-90° bug）。<strong>策略：标记 + 绕过</strong>（与用户共同敲定，符合 M3 暂缓决策）。① <code>build_asset</code> 成功路径给 sandbox root 打 <code>edini_asset_source</code> userData 印记（JSON 存 asset_id + component_ids）；② <code>commit_sandbox</code> 识别印记后<strong>绕过 G3a bake + G3b PCA</strong>，<strong>保留 G3c 健康门禁</strong>（orphan_points/open_curves 硬错误仍拒绝）和<strong>结构门禁</strong>（声明式资产天然多组件不单体，实际不触发）；③ verification receipt 标 <code>method:"declarative"</code>（默认 "gated"），让 agent 汇报时知道方向已由 builder 确定。<strong>关键安全保证</strong>：绕过是 opt-in 的——只有带印记的 build_asset 产物绕过，旧 network_mode 手写网络（无印记）继续走完整门禁栈，不削弱旧管道防御。<strong>测试</strong>：新增 test_commit_declarative.py（7 用例：声明式提交成功/receipt method/不需 orientation_checks/旧管道仍被 G3a 拒绝回归）+ test_asset_hython.py TestCommitAssetHython（5 真机用例 build→commit→receipt，本机无 hython 优雅 skip）。全量回归 <strong>592 passed, 27 skipped, 0 failed</strong>。</div>
</div>

<div class="phase-card">
  <div class="phase-card-header">
    <span class="phase-card-title">📚 Recipe Library（参考样本架构 · python_script）</span>
    <span class="status-tag status-done">核心完成 + 真实验证 + HDA 按钮</span>
  </div>
  <div class="progress-bar-bg"><div class="progress-bar-fill progress-done" style="width:98%"></div></div>
  <div class="phase-card-detail">recipe = <strong>参考样本</strong>（不是死模板）。<strong>5 工具</strong>（recipe_list/read/capture/capture_tree/rebuild）。捕获时自动生成 <code>python_script</code> 字段（可读 Python 还原代码，Notes 里「重要参数」标为 <code># author-marked</code>）。LLM 读 python_script 学习节点语法和约定，<strong>自己重建网络</strong>——能力不被 recipe 限死。recipe_rebuild 降级为可选的快速忠实复制路径（共存）。<strong>manifest 降噪修复</strong>：sweep::2.0 版本名优先 + 字符串标量↔单元素列表归一化 + vector/ramp/folder 参数名匹配 → 全库 changed_params 528→72（-86%），tube sweep 101→6（仅真实修改）。<strong>HDA 一键捕获按钮</strong>：rebuild_hda_with_button.py 用 setTags API 装到 edini_recipe_manager HDA，点按钮即捕获全部叶子子网。<strong>四个链路环节对齐</strong>：注册管理→检索（marked_parms 可搜）→python_script 生成→message注入（system prompt/工具描述/SKILL.md 统一新方向）。94 测试全绿。6 个 SOP 几何原语 recipe + 1 散布 recipe。</div>
</div>

<div class="phase-card">
  <div class="phase-card-header">
    <span class="phase-card-title">🎛️ Dashboard HDA（捕获按钮已上线 · Qt 树面板待做）</span>
    <span class="status-tag status-active">捕获按钮完成</span>
  </div>
  <div class="progress-bar-bg"><div class="progress-bar-fill" style="width:30%"></div></div>
  <div class="phase-card-detail">edini_recipe_manager 主 HDA：内部递归 subnet 树（结构即分类）+ 不锁定内容。<strong>✅ Capture All Recipes 按钮已装</strong>（hou.HDADefinition setTags API + recipe_capture_tree callback，reload 后真实 Houdini 验证通过）。⬜ Qt QTreeView 仪表盘（检查/重建/编辑按钮）待做。⬜ Skill 开关（Settings → Pi Capabilities 复选框，已完成，可 A/B 测试 recipe-library）。设计定稿见 recipe-manager-hda-design.md。</div>
</div>

<div class="phase-card">
  <div class="phase-card-header">
    <span class="phase-card-title">🔧 三阶段管道架构</span>
    <span class="status-tag status-done">完成</span>
  </div>
  <div class="progress-bar-bg"><div class="progress-bar-fill progress-done" style="width:100%"></div></div>
  <div class="phase-card-detail">Phase A → B → C（验证→构建→组装）。单构建路径（build_procedural_asset 唯一入口，旧 builder 已删）。三道闸门：G1 验证（A1-A9）/ G2 bake（edini_world_axis 烘焙）/ G3 commit（bake+orientation+health 硬闸 + verification_receipt）。参数三态。8 别名。H21 hython 53/53 + mock 468/468。parm_catalog 自动生成。</div>
</div>

<div class="phase-card">
  <div class="phase-card-header">
    <span class="phase-card-title">🖥️ PySide6 面板 UI</span>
    <span class="status-tag status-done">完成</span>
  </div>
  <div class="progress-bar-bg"><div class="progress-bar-fill progress-done" style="width:100%"></div></div>
  <div class="phase-card-detail">三栏布局 · Thinking 面板（可折叠、QTextEdit 纯文本流、实时展开/收拢）· Tool Call 面板（fixedHeight 折叠 24px↔200px、暗色协调、自动滚底）· 时间线 QScrollArea + Widget（_UserBubble / _AiBubble / _Separator / _ErrorBanner）· 智能滚动（rangeChanged valueChanged + _pinned_to_bottom 标志位）· Markdown 完整渲染（mistune 3.2.1 + _DarkRenderer, GFM: 标题/列表/表格/代码块/链接/图片/删除线/任务列表/引用块, 流式/最终 pixel 一致, 零依赖纯 Python）· 文本选择（TextSelectableByMouse）· 知识提取确认区（铁律/知识卡片 + ✓✕ + 全部接受/放弃 + 类型切换）· 气泡 Expanding 填满窗口 · 完成后自动折叠面板 · 4 层统一字号 · 历史气泡合并 · 知识提取过滤</div>
</div>

<div class="phase-card">
  <div class="phase-card-header">
    <span class="phase-card-title">🔌 JSON-RPC 通信</span>
    <span class="status-tag status-done">完成</span>
  </div>
  <div class="progress-bar-bg"><div class="progress-bar-fill progress-done" style="width:100%"></div></div>
  <div class="phase-card-detail">subprocess + stdin/stdout · QThread 非阻塞 · 事件分发 (text_delta/thinking_delta/tool_call/tool_result) · 会话 RPC (new/switch/set_name/get_state) · extension_info 信号 · cwd 支持 · ensure_ascii=True · CREATE_NO_WINDOW</div>
</div>

<div class="phase-card">
  <div class="phase-card-header">
    <span class="phase-card-title">⚙️ 工具执行器</span>
    <span class="status-tag status-done">完成</span>
  </div>
  <div class="progress-bar-bg"><div class="progress-bar-fill progress-done" style="width:100%"></div></div>
  <div class="phase-card-detail">HTTP Server (127.0.0.1:9876) · 22 tool handlers · /health 端点 · JSON 序列化 · 异常处理</div>
</div>

<div class="phase-card">
  <div class="phase-card-header">
    <span class="phase-card-title">🎯 Houdini 操作 (node_utils)</span>
    <span class="status-tag status-done">完成</span>
  </div>
  <div class="progress-bar-bg"><div class="progress-bar-fill progress-done" style="width:100%"></div></div>
  <div class="phase-card-detail">场景查询 · 节点 CRUD · 参数读写 · 节点搜索 · 几何检查 · Python/VEX 执行 · HDA 创建 · 布局</div>
</div>

<div class="phase-card">
  <div class="phase-card-header">
    <span class="phase-card-title">🧩 Pi 扩展</span>
    <span class="status-tag status-done">完成</span>
  </div>
  <div class="progress-bar-bg"><div class="progress-bar-fill progress-done" style="width:100%"></div></div>
  <div class="phase-card-detail">22 tools (TypeBox schema) · edini-context 注入铁律（rules.json）+ Houdini 上下文 · forwardTool HTTP 转发 · edini_search_knowledge 知识检索</div>
</div>

<div class="phase-card">
  <div class="phase-card-header">
    <span class="phase-card-title">📦 安装部署</span>
    <span class="status-tag status-done">完成</span>
  </div>
  <div class="progress-bar-bg"><div class="progress-bar-fill progress-done" style="width:100%"></div></div>
  <div class="phase-card-detail">install.py (Houdini 包注册) · setup_pi.bat · settings.json · Pi 路径自动检测 · env var 覆盖 · 隐藏 Windows 控制台</div>
</div>

<div class="phase-card">
  <div class="phase-card-header">
    <span class="phase-card-title">🎨 UI 字体</span>
    <span class="status-tag status-done">完成</span>
  </div>
  <div class="progress-bar-bg"><div class="progress-bar-fill progress-done" style="width:100%"></div></div>
  <div class="phase-card-detail">4层统一字号（header 13pt/body 12pt/detail 11pt/caption 10pt）· 全局 fs() 缩放 · 消除硬编码 pt · 面板高度/宽度适配 · 6 文件精确修改</div>
</div>

<div class="phase-card">
  <div class="phase-card-header">
    <span class="phase-card-title">🧪 测试</span>
    <span class="status-tag status-done">完成</span>
  </div>
  <div class="progress-bar-bg"><div class="progress-bar-fill progress-done" style="width:100%"></div></div>
  <div class="phase-card-detail">✅ Mock Hou 模块 · ✅ 521 测试（mock 468 + Houdini hython 53）· ✅ 三阶段管道完整覆盖 · ✅ 三道闸门测试矩阵（test_pipeline_gates.py 17 用例）· ⬜ Edini GUI 全链路测试</div>
</div>

<div class="phase-card">
  <div class="phase-card-header">
    <span class="phase-card-title">🛠️ Skill 系统</span>
    <span class="status-tag status-done">完成</span>
  </div>
  <div class="progress-bar-bg"><div class="progress-bar-fill progress-done" style="width:100%"></div></div>
  <div class="phase-card-detail">✅ 1 路由器 + 5 专用技能（recipe-authoring/component-building/assembly-wiring/verification/parametric-testing）· ✅ edini-brainstorm · ✅ grill-me · ✅ 技能自动发现</div>
</div>

</div>

<div class="timeline">

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-07-07</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第四十二阶段：椅子建模日志驱动的工具层改进 + HDA 对话框 disconnected 根因修复</span>
      <span class="status-tag status-done">完成 · 906 测试 · 会话日志第一性原理分析</span>
    </div>
    <div class="timeline-summary"><strong>分析一份真实椅子建模会话日志（"做一个椅子"，144 次工具调用 / 13 分钟），从第一性原理诊断 skill/工具/架构三层为什么"做不出高细节模型"，落地两个 P0 工具层改进。排查过程中又顺藤定位并修复了 HDA 对话框 disconnected 的真实根因。</strong><br><br><strong>会话日志第一性原理分析</strong>：最终质量 = (意图表达精度) × (原子操作粒度) × (反馈闭环速度)，edini 三项全偏低。核心发现：skill 把"脚手架"(scaffold/anchor/measure) 当成产品，却<strong>没回答"一个组件内部怎么雕细节"</strong>；没有零件库/recipe 层，每次从零拼装(box 椅子)；completion criteria 只检查"有无"不检查"质量"(open_boundary_edges 168 照样过)。工具层两个具体浪费源：9 个 forwardTool 复制粘贴无 try/catch(3 次 fetch failed)；create_node 不返回参数名(agent 猜 line 的 length，实际是 dist，5 轮浪费)。<br><br><strong>P0-1: forwardTool 共享 + 错误处理</strong>——9 个工具文件(eval/harness/knowledge/project/query/recipe/rooted/scene/script)各自复制了一份完全相同的 forwardTool，<strong>无 try/catch</strong>。网络抖动直接抛成裸字符串 <code>fetch failed</code>，agent 无法判断该重试还是改参数。抽出唯一共享 <code>_shared.ts</code>：try/catch + 瞬时错误(ECONNRESET/ECONNREFUSED/5xx)重试 2 次(退避 150ms) + 30s 超时(AbortController) + <strong>结构化错误体</strong> <code>{success:false, error, hint, transient, retryable}</code>(agent 看到"瞬时错误,重试即可"的明确指引) + tool 感知 hint(超时→"executor 可能 cook 中"；连接失败→"重发一次")。TypeScript 类型检查 _shared.ts 零错误。<br><br><strong>P0-2: create_node 返回参数清单</strong>——<code>houdini_create_node</code> 原先只返回 path/name/type，agent 被迫凭记忆猜参数名(会跨 Houdini 版本失效)。现返回 <code>parms</code> 字段，含该节点真实参数清单(name/type/components/menu tokens)。新增 <code>_node_parm_inventory(node)</code> 辅助函数，<strong>双路径</strong>：优先 <code>node.type().parmTemplateGroup()</code>(真实 hou 完整，含 type/menu/components)，回退 <code>node.parms()</code>(已物化参数，覆盖 mock/特殊节点)。精简成 <code>{name, type, components?, menu?}</code>，60 项截断保护，完全 best-effort 不阻塞 create。更新工具描述告知 agent 用 parms.list。5 个新测试(box→sizex/sizey/sizez / normal menu tokens / 降级 / 不阻塞)。<br><br><strong>disconnected 根因(意外收获)</strong>——用户报 HDA 对话框 Pi Status 显示 disconnected。诊断脚本 <code>diagnose_rpc.py</code>(新建)抓到 Pi 启动 2.2s 后退出，<strong>exit code 3221225786 = 0xC000013A = STATUS_CONTROL_C_EXIT</strong>。<strong>根因</strong>：rpc_client.py 启动 Pi 用 <code>CREATE_NO_WINDOW</code> 但缺 <code>CREATE_NEW_PROCESS_GROUP</code>，Pi 共享 Houdini 控制台会话 → Houdini 内部控制台控制事件级联到 Pi 将其击杀(无 stderr，不是 Pi 报错是被外部信号杀)。症状完美解释：Pi 能启动加载扩展(emit connected)→ 2s 后被控制事件杀 → UI 掉 disconnected。<strong>修复</strong>：加 <code>CREATE_NEW_PROCESS_GROUP</code> 让 Pi 进独立进程组(免受父侧控制事件波及，stop() 用 TerminateProcess 仍有效)。诊断脚本验证：修复前 2.2s 退出，修复后 8s 全存活。另加<strong>进程退出检测</strong>(Pi 非主动退出时 emit disconnected + exit code 错误，不再卡假 connected)。<br><br><strong>测试</strong>：906 passed(原 901 + 新增 5 create_node parms 测试)，零回归。两个 commit：<code>feat(tools)</code>(P0 两项) + <code>fix(rpc)</code>(disconnected 修复)。<strong>下一步</strong>：P1 项(finish/质量三角 + recipe 接入)才是把"box 椅子"升级到"高细节椅子"的关键。</div>
    <div class="timeline-tags">
      <span>会话日志分析</span><span>第一性原理</span><span>forwardTool共享</span><span>结构化错误</span><span>create_node参数清单</span><span>消除猜参数名</span><span>disconnected根因</span><span>0xC000013A</span><span>STATUS_CONTROL_C_EXIT</span><span>CREATE_NEW_PROCESS_GROUP</span><span>进程组隔离</span><span>进程退出检测</span><span>diagnose_rpc.py</span><span>906测试</span>
    </div>
  </div>
</div>

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-07-06</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第四十一阶段：会话日志驱动的平台契约强化（三轮 fix-observe-refix）— 把 SKILL 散文变成 fail-fast 结构</span>
      <span class="status-tag status-done">完成 · 848 测试 + 18 hython 铁证 · 三轮迭代</span>
    </div>
    <div class="timeline-summary"><strong>分析三份真实 agent 建模会话日志（同一任务"做一个椅子"），逐轮从第一性原理定位问题并修复。</strong>核心洞察：平台把建模契约写在了 SKILL.md 散文里，agent 不读/读了不照做 → 错误一路静默，靠肉眼巡检兜底。修法不是让 agent 更聪明，而是<strong>让平台把契约真正强制起来</strong>（shift from prose to fail-fast structure）。复用既有 <code>[VISUAL-VERIFY-GATE]</code> 三层模式（filter tool → swap guideline → refuse in handler）。<br><br><strong>会话1（120 调用/4 失败）→ Round 1 六修复</strong>：① <code>project_anchor_guard</code>——拒绝 Project HDA 组件内手写 <code>addpoint()</code>，指向 <code>project_add_anchors</code>（带 <code>// edini-bypass-anchor-guard</code> 逃生口）；② 锚点路由自动 <code>filter_&lt;from&gt;_&lt;anchor&gt;</code> Blast（按 <code>@name</code> 留点）+ 静态 <code>route_warnings</code>；③ scaffold 自动烘焙 <code>component_id</code> + <code>edini_world_axis</code>；④ 参数名 "Did you mean" 建议（<code>difflib</code> + manifest）；⑤ sandbox 契约自文档化错误（NameError/NoneType 附注入变量清单）；⑥ canonical 工具名清理 + Lop 类别提示（cylinder→tube）。<br><br><strong>会话2（128 调用）→ Round 2 三修复（Round 1 的边界）</strong>：① <strong>Fix A（过度矫正）</strong>——agent 覆盖 <code>tag_component</code> snippet 静默删了 axis。拆成两节点：<code>tag_component</code>（agent 可编辑，只 component_id）+ <code>__edini_axis_bake</code>（内部 <code>__</code> 前缀，锁死，每次 rebuild 重设）；guard 拒绝编辑 <code>__</code> 节点。② <strong>Fix B</strong>——Blast 漏 degenerate prims（72 个零顶点面）。加 <code>__edini_anchor_clean_*</code> detail wrangle 删所有 prims，端口保证纯点云。③ sandbox 引导：别在 sandbox 原型组件。<br><br><strong>会话3（55 调用/最干净）→ Round 3 三修复（Round 2 的过度矫正）</strong>：会话3 几乎完美（0 沙箱/0 锚点泄漏/读 SKILL/用声明式锚点），但 <strong>backrest 朝向失败</strong>暴露 Round 2 Fix A 把"设 per-component 轴"的正门也封死了。<strong>第一性原理</strong>：安全闸应"拒绝错误行为 + 开放正确通道"，Round 2 只做了前半。① <strong>D1</strong>——组件声明加可选 <code>axis</code> 字段（默认 Y），scaffold 据此烘焙正确向量（<code>resolve_axis_vector</code>）。agent 声明 <code>"axis":"Z"</code> + rebuild，axis 自动正确，永不碰内部节点。② <strong>D2</strong>——<code>verify_orientation</code> 的 <code>construction_axis</code> 参数之前被忽略（L87 陷阱），现在真的生效（per-check 覆盖 baked 值，<code>axis_source: override|baked</code>）。③ <strong>D3</strong>——tube <code>type=prim</code> access_hint（copytopoints 只复制锚点的坑）。<br><br><strong>三轮净效果</strong>：会话1（120 调用/4 失败/2 沙箱/0 声明式锚点）→ 会话3（<strong>55 调用/1 失败/0 沙箱/1 声明式锚点/0 锚点泄漏</strong>）。会话3 唯一剩余失败（backrest 轴 Y-vs-Z）已被 D1+D2 修复。<strong>测试</strong>：848 mock + 18 hython（新增 6 椅子回归 + 2 轴回归，含 <code>test_fixa_axis_survives_tag_component_override</code> / <code>test_fixb_anchor_port_is_prim_free</code> / <code>test_d1_backrest_axis_z_baked_and_passes</code>）。<strong>核心设计原则</strong>：对 LLM agent，<strong>不可绕过的结构 &gt; 拒绝 &gt; 默认值</strong>（默认值会被全量覆盖语义无声擦除）。详见 [组件地基指南](project-component-foundation.md)。</div>
    <div class="timeline-tags">
      <span>会话日志驱动</span><span>第一性原理</span><span>fail-fast</span><span>addpoint-guard</span><span>声明式锚点</span><span>锚点路由净化</span><span>__edini_axis_bake</span><span>内部节点锁</span><span>per-component轴</span><span>construction_axis生效</span><span>拒绝+开放通道</span><span>三轮迭代</span><span>848测试</span><span>18hython</span>
    </div>
  </div>
</div>

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-07-01 → 07-02</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第四十阶段：Project HDA — 程序化建模的"项目化身"容器（brainstorming 11 决策 + spec + 12 任务计划 + subagent-driven 最小闭环实现）</span>
      <span class="status-tag status-done">最小闭环实现完成 · 112 tests · 待真机验证</span>
    </div>
    <div class="timeline-summary"><strong>新子系统，不是 rooted 里程碑的延续，而是其上的容器化 + 协作化升级。</strong>rooted 的 build_assembly 是<strong>一次性生成器</strong>（agent 产声明 → builder 构建 → 完成，agent 是唯一作者）。用户想要的体验要求<strong>有意打破这条不变量</strong>：让用户也能直接在 Houdini 里改几何网络，让 agent 持续理解、优化、迭代项目。这是从"一次性生成器"到"长期协作伙伴"的范式升级。<strong>第一性原理</strong>：易用/正确程序化逻辑/长期迭代三个目标里，有两个全部系于"同步"一件事——如何在用户自由编辑前提下保持 agent 维护的知识图谱与真实网络同步。<strong>核心策略（架构支柱）</strong>：把"语义同步"降级为"结构 diff"——让 subnet 的物理嵌套结构镜像组件分解，使"哪些节点属于哪个组件""组件是否还存在""参数依赖"全部变成确定性查询，无需 LLM 语义推断。<br><br><strong>brainstorming 11 个核心决策</strong>（全部用户拍板）：① 真实来源=<strong>混合</strong>（网络管几何事实，图谱管意图）；② 图谱范围=<strong>C 档</strong>（结构+语义+参数化意图）；③ 同步策略=<strong>检测偏离+人确定</strong>（不解逆程序化建模难题）；④ "优化"=<strong>四向并行</strong>（参数化整洁/图谱准确/性能可维护/持续加组件细节 + HDA 输出日志供跨项目复用）；⑤ 面板=<strong>PySide 全自绘嵌入 HDA</strong>；⑥ 半成品=<strong>始终可 cook</strong>（每步原子、失败回滚）；⑦ 图谱表示=<strong>富化声明即图谱</strong>（路线1，一个意图来源无双重同步，直接长在现有声明上）；⑧ 计划=<strong>强制、详细、可 review、用户控序</strong>；⑨ 组件管理=<strong>subnet 浅镜像</strong>（组件组一层，把语义同步降级为结构 diff——分水岭决策）；⑩ 参数管理=<strong>HDA 原生参数接口</strong>（live ch() 引用有真实 parm 落点）；⑪ 多项目=<strong>每个 HDA 独立面板+独立 Pi session</strong>。<br><br><strong>实现（subagent-driven，分支 feat/project-hda）</strong>：纯 Python 核心 <code>state.py</code>（声明 schema：version/project{name,created_at,goal}/plan/design_params/components/log/drift；load/save JSON↔隐藏 parm；plan-step 助手；log 助手）+ <code>node.py</code>（隐藏 string parm 模板 + create_project_hda）→ <code>otls/edini_project.hda</code>（edini::project 类型，hython 验证 found:True）→ 嵌入面板（<strong>本仓库第一个真正的 Houdini Python Pane</strong>，.pypanel XML 注册，三栏：计划树/对话/状态，复用 edini.ui.theme + _TimelineView/_AiBubble）→ 对话接线（<strong>复用单例 RpcClient</strong> via open_chat_window()._rpc_client，绝不每 HDA 起 Pi 进程撞端口 9876；每项目 send_set_session_name 开独立 session）。<strong>两轮 review 各发现并修真实问题</strong>：① load 的 parm-is-None 分支被偷懒 fake 漏掉→补专属测试；② save 无 None 守卫→加清晰报错；③ 计划里两处 H21 API 写错（createDigitalAsset 引用失效需按 path 重取；hou.nodeType 两参字符串签名错误，正确是 nodeTypeCategories()['Object'].nodeType(...)）→ 实现时按真实 API 改正。<strong>测试</strong>：19 新 state 单测（纯 Python，mock hou）+ 93 既有 node_utils 全绿 = 112 tests，零回归。<strong>状态</strong>：最小闭环（空 Project HDA + 嵌入面板 + 对话）11/12 任务完成，Task 12（agent 侧 project_hda_create 工具）按用户要求暂不做。<strong>✅ 真机验证通过（2026-07-02，Houdini 21.0.440 GUI）</strong>：建 Project HDA → 开 Edini Project pane → 三栏布局 + 项目选择器 → 中英对话（独立 Pi 进程，每项目隔离 session）。<strong>真机抓修 8 个 mock 测不出的 bug</strong>：① setHidden/spareParmGroup→真实 API hide()/addSpareParmTuple；② pane 找不到→HOUDINI_PYTHON_PANEL_PATH + python_panels/ 目录（包 JSON 的 houdini.python_panels 键无效）；③ PySide2+继承类崩溃→PySide6 + onCreateInterface() 函数；④ 每次发送弹主窗口→独立 RpcClient + ToolExecutor 进程单例；⑤ 流式卡顿→轻量 _StreamBubble（纯文本流式，finalize 才跑 markdown）；⑥ 中文输入失焦→Houdini Python Panel 容器在 Qt 输入法管道前拦截键盘事件（SideFX 确认 bug），改 popout 输入对话框；⑦ 首条消息无回复→bootstrap 时未 set_model；⑧ visionizer stale-ctx 阻塞→去掉多余 send_new_session。<strong>已知限制</strong>：嵌入面板内联输入框不支持中文 IME（Houdini 容器层限制），中文走 💬 popout 对话框。<strong>刻意保持距离</strong>：Project HDA 是新模块 python3.11libs/edini/project/，<strong>不导入</strong> assembly_builder/vex_strategies——这些是将来"按需接入"的建模能力，声明 schema 刻意通用不预设建模结构。<strong>下一步候选</strong>：① drift 检测实现（结构 diff 规则 + 人裁决流程）；② 计划树 UI 交互（checkbox + 推进选中/顺序推进）；③ 接入 rooted 建模能力让 agent 能真正建模；④ Task 12。详见 [spec](../../docs/superpowers/specs/2026-07-01-project-hda-design.md) §13 最小闭环定义 + [实现计划](../../docs/superpowers/plans/2026-07-01-project-hda-minimal-loop.md)。</div>
    <div class="timeline-tags">
      <span>新子系统</span><span>项目化身</span><span>长期协作伙伴</span><span>混合真实来源</span><span>C档图谱</span><span>检测偏离人确定</span><span>subnet浅镜像</span><span>结构diff非语义推断</span><span>富化声明即图谱</span><span>隐藏parm持久化</span><span>第一个Python-Pane</span><span>复用单例RpcClient</span><span>per-project-session</span><span>始终可cook</span><span>subagent-driven</span><span>feat/project-hda分支</span><span>112tests</span><span>11/12任务</span><span>H21-API修正</span><span>待真机验证</span>
    </div>
  </div>
</div>

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-07-01</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第三十九阶段：真机 agent 测试驱动的三大修复 — M2.6 leaf 参数全 live + 视觉自检 + M2.7 shape 链细节</span>
      <span class="status-tag status-done">完成 · 真机 hython 5 项新铁证</span>
    </div>
    <div class="timeline-summary">用户首次用真实 Pi agent（glm-5.2）端到端测试「程序化简易小汽车」，agent 完整走通 build → inspect → capture → commit 链路，但 GUI 实测暴露三个真实问题。<strong>全链路健康检查</strong>（提示词注入 → 工具注册 → Python handler → 构建层 → 策略 dispatch → SKILL.md）确认链路本身正常，但发现一个<strong>阻塞隐患</strong>：文档 hython 路径写反（声称 C:\Program Files\... 实际在 D:\houdini\bin\，M3.5 Task 0 把方向修反了），已修正。<strong>问题 ①（M2.6 leaf 参数不 live）</strong>——用户发现只有 length/width/thickness（root box 的 size）三个参数有效，wheel_radius/cabin_length/head_size 等 7 个 leaf 参数全无效，但 live_params 却报告全部 10 个 live。<strong>根因</strong>：_build_shape 有两条路径——is_root=True 把参数名转 ch("../name") 通道引用（LIVE），is_root=False（leaf）用 evaluate() 烤成死数字。leaf scale 和 origin offset 同样烤死。<strong>关键洞察</strong>：leaf shape 节点跟 root shape 在 container 下<strong>同层</strong>，所以 ch() 路径完全相同（ch("../name")）。修复：leaf shape/scale/offset 统一走 _param_ref_expr（原 _root_param_ref_expr 重命名，本就通用）。<strong>真机铁证</strong>：wheel_radius 0.4→1.2 轮子直径长大 >2x（scale live）；wheel_tube_r 0.08→0.4 厚度变厚 >3x（shape param live）；全程 recook 不重建。<strong>问题 ②（视觉自检失效）</strong>——两个测试会话的 describe_image 都报 "Vision model aliyun/qwen-vl-max not found in model registry"。<strong>根因</strong>：pi-visionizer 硬编码默认 provider 名 aliyun，但 models.json 注册的是 ali。修复：默认改 ali + index.ts 加 registry 兜底搜索（find 失败时按 modelId 扫 getAvailable()），not-found 错误现在还列出可用模型。<strong>问题 ③（M2.7 模型太简易）</strong>——用户反馈「做的太简易了」。根因：每个 leaf = 一个裸 SOP（box/torus/sphere），无倒角/挤出/细分。<strong>调查 + 设计</strong>（subagent 双轮探索 + plan mode）：最高杠杆改进是给 leaf 引入 shape 节点链。用户确认<strong>轻量选面方案</strong>（group 参数写 Houdini 原生 group spec，不做具名锚点）+ 覆盖 polyextrude/polybevel/subdivide/grid 四个修饰符。<strong>Schema</strong>（向后兼容）：shape 可为 {type, params}（单 SOP，不变）或 {chain: [{type, params}, ...]}（线性 SOP 链，tail 接 CTP）。<strong>核心技术点</strong>：_resolve_chain_param 智能分类——参数引用（如 rim_h，所有 extract_refs 名字都是已知 param）转 ch()；Houdini 原生字符串（如 polyextrude group "0"）原样透传。<strong>真机发现的约束</strong>：polyextrude::2.0 的 group 参数用 prim 号（"0"）或 named group，<strong>不接受 VEX @P.y>0.5 语法</strong>（那是 wrangle 的）——已 SKILL.md 标注。<strong>真机铁证</strong>：box 6 面 → polyextrude 10 面（凸缘）；box 8 点 → polybevel 20+ 点（圆边）；改 polyextrude dist 参数 live recook 挤出高度。<strong>测试</strong>：607 mock（+11 新：8 TestLeafShapeChain + 3 TestLeafParamsLive）+ 26 hython（+5 新：2 leaf-live + 3 chain）全绿，零回归。</div>
    <div class="timeline-tags">
      <span>真机agent测试</span><span>M2.6-leaf-live</span><span>ch()通道引用</span><span>同层路径洞察</span><span>visionizer-ali修复</span><span>registry兜底</span><span>M2.7-shape链</span><span>polyextrude</span><span>polybevel</span><span>subdivide</span><span>grid新shape</span><span>_resolve_chain_param</span><span>group-prim号非VEX</span><span>向后兼容</span><span>607mock</span><span>26hython</span>
    </div>
  </div>
</div>

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-07-01</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第三十八阶段：rooted-modeling M3.5 — TabularFill 四布局扩展（pickets/tiles/shelf/blocks）+ 方案 C 分层泛化 + per-cell orient milestone</span>
      <span class="status-tag status-done">完成 · 真机 hython 7 项铁证</span>
    </div>
    <div class="timeline-summary">用户要求「扩展 cells/skill 能力，要足够通用稳定泛化，从第一性原理优化框架」。<strong>brainstorming → spec → plan → subagent-driven 执行 → 最终 code review</strong> 全流程。<strong>第一性原理诊断</strong>：4 个目标布局（栅栏/瓷砖/书架/街区）的差异全是「槽位 schema 列」的差异，共享「N 维槽位空间 + 填充声明」这一个抽象；当前 cells 把槽位维度写死 2D 且无 per-cell 朝向。<strong>架构决策（方案 C 分层泛化）</strong>：一布局一子类（清晰可测），但每个布局驱动真实泛化下沉到 TabularFillStrategy 基类；泛化由真实布局驱动而非预测（避开方案 B 过度抽象的陷阱）。<strong>开发顺序 = 泛化路线图</strong>（从简单到复杂打磨抽象）：①栅栏(1D) → ②瓷砖(per-cell orient) → ③书架(3D layers) → ④街区(合成考试)。<strong>五大交付</strong>：① <strong>pickets（1D 栅栏）</strong>——驱动 axes[] 解析基础设施 + count→cells 语法糖；1D 通过「退化第二轴」技巧复用 2D 循环（gz=0/d=1，所有点共享 Z），真机铁证 8 栏杆均匀分布在 [-1.75,+1.75]。② <strong>tiles（2D 瓷砖 + per-cell orient）</strong>——<strong>解决 SKILL.md 点名的 deferred milestone「per-instance orient」</strong>：每个 cell 携带 rot（度），绕 face 法线生成四元数 quaternion(radians(rot), nvec)，setpointattrib 写 POINT-class p@orient（避开 M2.5 的 detail-class 被忽略 bug）；命名 orient 规则 herringbone/checker/running（agent 只选名字不算角度，延续「不让 LLM 写表达式」铁律）；hython 铁证 rot=90 的 p@orient = (0, sin45, 0, cos45) 用点积验证（q ≡ -q）。③ <strong>shelf（3D 书架）</strong>——layers 预处理（_expand_shelf_layers 拍平 layers→3D cells），layer 概念是 subclass-only（ShelfStrategy._parse_table 设 _shelf_layers，base/cells/pickets/tiles 都不设）；_build_vex 加 gated shelf fragment（_shelf_layers 非空才发），覆写每个点的 face 轴 P（层中心）+ face 轴 scale（层高）；<strong>hython 手算验证 VEX 数学严格等于预言机</strong>（Y=[3.889, 3.889, 6.889]，unit_axis=5/18，layer-0 center≈3.889，layer-1 center≈6.889）。④ <strong>blocks（城市街区，合成考试）</strong>——<strong>近零新 VEX，纯组合 ①②③</strong>：BlockStrategy = tiles 的 rot 机制（_rot_vals→p@orient）+ 新的 height fragment（_block_h_vals→face 轴 scale 覆写），两个 fragment 独立（orient 写 p@orient，height 写 scale 分量）无冲突；hython 铁证 3 街区高度成比例（tower/podium ratio=4.0=40/10，unit 守恒）。⑤ <strong>三层 gate 防御 byte-identical</strong>——_rot_vals / _shelf_layers / _block_h_vals 三个 gated fragment，getattr 默认 None，cells/pickets 永不触发；test_cells_2d_byte_identical_after_axes_refactor 全程钉死 2D VEX 变量名。<strong>最终 code review（opus）发现 1 阻塞</strong>：shelf oracle 每层独立算 in-plane unit 而 VEX 用单一 unit，不等宽层上静默分歧（违反项目 #1 契约 oracle==VEX）。<strong>按用户决策处理</strong>：C1 加 shift-left 校验（强制 layers 等宽）+ 文档；I1 真 bug 修（basis.face 在 cells/tiles/blocks 统一接受，加 _resolve_face_str helper）；I2/I3/I4 de-spec（删死代码 _resolve_axes + 移除未实现的 basis.edge/picket h 主张，诚实反映「1D=退化2D」真实实现）。<strong>真机铁证</strong>（hython 21.0.440）：栅栏 8 栏杆 1D 行 live / 瓷砖 rot=90 四元数 / 书架 3 书 2 层 Y 精确匹配 / 街区 3 高度成比例 + rot+height 合成。<strong>测试</strong>：595 mock + 21 hython 全绿，零回归，verify 脚本 14/14 ALL MATCH ORACLE。<strong>新展示</strong>：`edini_showcase.hip` 含 car + bicycle + 65 键键盘 + stairs + fence + shelf 六例（均可 live recook）。</div>
    <div class="timeline-tags">
      <span>方案C分层泛化</span><span>按需下沉</span><span>YAGNI</span><span>pickets-1D</span><span>退化轴技巧</span><span>tiles-per-cell-orient</span><span>四元数</span><span>命名orient规则</span><span>orient-milestone解决</span><span>shelf-3D-layers</span><span>layer预处理</span><span>subclass-only</span><span>blocks-合成考试</span><span>近零新VEX</span><span>三层gate防御</span><span>byte-identical</span><span>code-review-C1</span><span>shift-left校验</span><span>de-spec</span><span>595测试</span>
    </div>
  </div>
</div>

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-06-30</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第三十七阶段：rooted-modeling M3 — cells 测量原语 + 三层类架构 + square/fill 模式 + Pi agent 端到端链路</span>
      <span class="status-tag status-done">完成 · 真机 hython 5 项铁证</span>
    </div>
    <div class="timeline-summary">用户实测 M2.5 键盘后发现「按键是均匀点阵不是真键盘」→ 引发本轮系统性重构。<strong>第一性原理拆解</strong>：真键盘的布局是「每个位置带自己的尺寸」——位置和尺寸是<strong>绑定</strong>的，而 grid_on_face 只能「N 个相同东西均匀铺满」。这是工具能力上限，不是 agent 执行问题。<strong>五大交付</strong>：① <strong>cells 测量原语</strong>（measure_cells + build_cells_vex）—— 显式 1u 单位网格布局表 <code>{gx,gz,w,d}</code>，每个 cell 声明位置+大小，系统生成 <code>{position, v@scale}</code> 对，CTP 2.0 原生支持逐实例非均匀缩放（读 v@scale），<strong>1 个 CTP 盖印 N 个不同尺寸的键</strong>（1u 键 + 6.25u 空格键从一个 1u leaf 出）。支持 staggered 行错位 + gap 间隔 + 缺口。② <strong>unit 实时从 root 派生</strong>（修复 keys 溢出 root 的 bug）—— <code>unit = (root_span - 2*margin) / 布局总u宽</code>，缩 root → unit 实时重算 → keys 自动重排精确填满 root，永不溢出。③ <strong>三层类架构重构</strong>（VexStrategy 契约 → StaticTemplateStrategy 6 静态 kind / TabularFillStrategy 表+循环+unit 派生 → CellsStrategy gx/gz/w/d schema），消掉 build_mount_vex 的 if-elif 链，<strong>泛化性载体</strong>（书架/街区/瓷砖可继承 TabularFillStrategy）。数据/代码解耦：表编码成 VEX 数组字面量 + 单循环，VEX ~30 行不管多少 cell。④ <strong>square 形状约束 + pad/repeat/stretch 三填满模式</strong>（square 强制 unit=min 保正方；pad 居中留白；repeat build 时预处理展开 cells 表自动增量；stretch 默认拉伸）。⑤ <strong>Pi agent 端到端链路修复</strong>（build_assembly 返回契约补 sandbox_root_path/live_params + system prompt 引导用 build_assembly + pi_data_bridge ESM 重写修复 provider 列表消失）。<strong>调试关键发现</strong>：VEX 数组字面量+循环在 H21 可用（验证过）；detail wrangle 的 <code>__n</code> 变量与 clear 循环冲突（改用 <code>__ci/__ncell</code>）；CTP transform 开关默认开读 v@scale 无需配置。<strong>真机铁证</strong>（hython 21.0.440，8 策略 vs 预言机全过含 stretch/square/pad 三模式 ratio=6.250 守恒；square 键 bbox X==Z 正方；pad 居中留白不溢出；repeat 键数 >6 自动增量；65 键 showcase square=true 缩 tray_width 自动重排）。<strong>测试</strong>：599 passed（含 11 新测试），全量零回归。<strong>新展示</strong>：`edini_showcase.hip` 含 car + bicycle + 65 键正方形键盘 + stairs。</div>
    <div class="timeline-tags">
      <span>cells原语</span><span>显式布局表</span><span>1u网格</span><span>per-point-v@scale</span><span>1-CTP多尺寸</span><span>unit实时派生</span><span>三层类架构</span><span>VexStrategy</span><span>TabularFillStrategy</span><span>square约束</span><span>pad/repeat/stretch</span><span>数据代码解耦</span><span>Pi-agent端到端</span><span>pi_data_bridge-ESM</span><span>599测试</span>
    </div>
  </div>
</div>

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-06-29</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第三十六阶段：rooted-modeling M2.5 — leaf align convention（orient point-class 修复 + align_axis + origin normalize + 分组 CTP）</span>
      <span class="status-tag status-done">完成 · 真机 hython facing 铁证</span>
    </div>
    <div class="timeline-summary">用户实测 M2 的 `edini_showcase.hip` 后发现 4 个 leaf 层问题，本次全部修复。<strong>第一性原理拆解</strong>：4 问题共享同一根因——leaf 层缺显式「对齐约定」（align convention）。<strong>brainstorming → spec → plan → subagent-driven 执行（8 task）</strong>，每 task 两阶段 review（spec 合规 + 代码质量）。<strong>四修复</strong>：① <strong>orient point-class</strong>（`vex_strategies._orient_fragment`）—— detail wrangle 里 `p@orient=` 变成 detail 属性 CTP 不读，改 `setpointattrib` 写到每个 point；② <strong>align_axis 约定</strong>（`measure.orient_to_align(direction, align_axis="+Y")` 泛化）—— leaf 的对齐轴可配（±X/±Y/±Z 六轴），dihedral→四元数→矩阵→Euler 直构（已验证 0/66 失败）；③ <strong>leaf.origin 规范化</strong>（`_build_origin_normalize`）—— copy 前插入 wrangle，把 anchor 点（bbox_center / bbox_face:±XYZ / [x,y,z]）移到原点 + offset；④ <strong>分组 CTP</strong>（`_leaf_group_key` + `_group_leaves`）—— 同 shape+scale+origin 的 leaf 共享 1 shape + 1 CTP，4 轮子从 4+4 降到 1+1。<strong>调试关键发现（systematic-debugging）</strong>：hython facing 测试暴露 mock 抓不到的两个根因——(a) <strong>VEX 语义陷阱</strong>：detail wrangle 里 `npoints()` 不反映同次 cook 内 `addpoint` 创建的点，导致 orient 循环 `for i&lt;npoints()` 永不执行（orient 留单位四元数），改用 `__newpts[]` 数组解决；(b) <strong>事实错误</strong>：torus 对称轴是 <strong>+Y</strong>（圆盘在 XZ 平面）不是 spec 假设的 +Z，align_axis 改回 +Y 后轮子才立起来（bbox `[0.063, 0.805, 0.805]` thin=X 车轴方向）。<strong>真机铁证</strong>（hython 21.0.440）：bicycle 4 轮每个 bbox thin 轴 = X（车轴方向）、mount cloud orient 四元数旋转 +Y 得 X 方向、1 CTP 4 轮、car 回归仍朝向正确、live recook（length 4→8 轮子滑动）。<strong>测试</strong>：151 passed（142 mock + 9 hython），final code review APPROVED。<strong>新展示</strong>：`edini_showcase.hip` 含 car + bicycle + keyboard + stairs 四例。7 个 feature commit + 1 review 修复 commit。</div>
    <div class="timeline-tags">
      <span>leaf-align-convention</span><span>orient-point-class</span><span>setpointattrib</span><span>__newpts数组</span><span>align_axis</span><span>dihedral→矩阵→Euler</span><span>origin规范化</span><span>分组CTP</span><span>systematic-debugging</span><span>torus轴+Y纠正</span><span>hython-facing铁证</span><span>151测试</span>
    </div>
  </div>
</div>

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-06-26</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第三十五阶段：声明式资产管道里程碑1 — 骨架点 DAG + 表达式引擎 + validate_asset（自底向上重启）</span>
      <span class="status-tag status-active">地基交付 · 待真机实测</span>
    </div>
    <div class="timeline-summary">① **根因复盘**：分析 4 轮会话日志（水管/自行车/水管-v2/v3），确认旧程序化建模失败的本质 = "规则跑在能力前面"。skill 强制走 build_procedural_asset，但底层工具不存在，agent 够不着→退回 sandbox→被门禁拒→死循环。门禁本身编码了正确的领域知识，问题在 agent 没有满足门禁的手段。② **与用户共同设计新流程**（6 阶段）：拆分组件 → 骨架点 DAG → 盒子占位 → 参数库（边做边加，禁硬编码）→ native 节点链实现（拼不出才用 Python SOP）→ 组装提交。核心创新 = <strong>组件不互相连接，都连接到一张参数驱动的骨架点表（DAG）</strong>——这解了"连接问题"，且和"参数库禁硬编码""盒子占位"天然咬合。③ **地基三模块（纯 Python 无 hou）**：exprs.py（从 _disabled_backup 搬回的安全表达式引擎，新增 Name[int] 下标放行点引用语法）、skeleton_resolver.py（Kahn 拓扑排序 + 环检测 + 点引用求值）、asset_model.py（资产 JSON 三段 + validate + resolve，含 derived 参数 DAG 求值）。④ **接入 validate_asset 工具**（tool_executor 注册 + TS schema），纯数据 shift-left 验证，resolve=true 预览坐标。⑤ **样例 bicycle.asset.json**：10 参数（含 2 个 derived）+ 5 骨架点，验证 + 求值 + 参数联动（wheel_radius 改动，bb_center 正确跟随）全通过。⑥ **教训**：先写 skill 规则再补能力会崩；必须 capability before rules。**下一步明确：先在真实 Houdini 实测里程碑1（agent 调 validate_asset），跑通再进里程碑2**。两个提交已推 GitHub（025ca86 参数系统修复 + eb2cfe1 资产管道里程碑1）。</div>
    <div class="timeline-tags">
      <span>骨架点DAG</span><span>表达式引擎</span><span>自底向上</span><span>validate_asset</span><span>shift-left</span><span>纯Python</span><span>capability-before-rules</span><span>待真机实测</span>
    </div>
  </div>
</div>

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-06-25</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第三十四阶段：Recipe 二次定位 — 参考样本架构（python_script）+ manifest 降噪 + HDA 捕获按钮</span>
      <span class="status-tag status-done">完成</span>
    </div>
    <div class="timeline-summary">① **定位转向**：recipe 从「LLM 用 recipe_rebuild 机械还原的死模板」重定义为「给 LLM 的参考样本」。根因洞察——机械 rebuild 把 LLM 能力限死在 recipe 形状内，违背「降低出错率而非限定能力」的初衷。参考 EEEAi_Houdini 的 node_tree_extractor 模式（current_value vs default_value 标记 is_modified）。② **python_script 生成器**（_generate_python_script）：捕获时从 nodes[] 生成可读 Python 还原代码（createNode+setInput+parm.set），Notes 里「重要参数」标为 <code># author-marked</code>（核心信号），噪音参数（tx=0/空字符串/folder 折叠态）过滤。LLM 读它学习节点语法和约定，自己重建网络。③ **manifest 降噪（根因修复）**：诊断发现 sweep1 记了 101 个假 changed（用户只改 2 个）。根因三连——_manifest_defaults 优先匹配老 sweep（20参数）而非 sweep::2.0（81参数）；_values_equal 不处理字符串标量↔单元素列表（'roll'≠['roll']）；vector/ramp/folder 参数名不匹配。修复：版本名优先 + 字符串归一化 + vector（upvectorx/uvscale1）+ multiparm（value0/value#）+ folder-state（section/folder01）匹配。全库 changed_params 528→72（-86%），tube sweep 101→6。④ **四链路环节对齐 review**：发现 capture/generation 已转新方向，但 search/injection 还在说旧的「机械 rebuild」——edini 收到矛盾指令。修复 system prompt（Build Path Selection）、recipe_list/recipe_read/recipe_rebuild 三工具描述、SKILL.md 全文统一；marked_parms 进 index+haystack 可搜（recipe_list(query='endcaptype') 命中）。⑤ **HDA 一键捕获按钮**：rebuild_hda_with_button.py 用正确的 setTags({'script_callback':...}) API（初版误用不存在的 setScript）装到 edini_recipe_manager HDA，callback 调 recipe_capture_tree。reload edini 模块后真实 Houdini 验证：捕获产生 python_script + marked + 干净 changed_params。⑥ **Skill 开关**：Settings → Pi Capabilities 每个 skill 加复选框，disabled_skills 过滤，可 A/B 测试 recipe-library。⑦ **新增 3 通用原语 recipe**（linear_array_copy/boolean_op/bevel_edges）+ 清理重复（Base_Sweep/dopnet.noise_forece）。⑧ 94 测试全绿（+13 manifest/python_script/skill-toggle 测试）。</div>
    <div class="timeline-tags">
      <span>参考样本</span><span>python_script</span><span>author-marked</span><span>manifest降噪</span><span>版本名优先</span><span>vector匹配</span><span>HDA按钮</span><span>setTags API</span><span>四链路对齐</span><span>marked可搜</span><span>Skill开关</span><span>94测试</span>
    </div>
  </div>
</div>

### 第三十一阶段：三阶段管道架构 + H21 完整验证

- **三阶段管道**：Phase A (recipe_validator: A1-A6 六层检查) → Phase B (component_builder: 3 backend) → Phase C (assembly_engine: CTP+anchor 活通道)。全 pipeline 通过 `build_procedural_asset` 内部串联，向后兼容。
- **参数目录自动生成**（`parm_catalog.py`）：扫描已安装 Houdini 的所有 SOP 类型（1651 个），缓存到 `parm-catalog.json`。Phase A 用目录做 parm 名/节点类型的地面真相——零 cook 验证。包含别名解析（transform→xform, fuse→fuse::2.0）。
- **工具面重组**：移除 `houdini_run_python`，新增 4 工具（`validate_recipe`/`build_component`/`assemble_components`/`dump_parm_catalog`）。8 个工具重命名（`houdini_verify_orientation`→`verify_orientation` 等）+ `_TOOL_ALIASES` 向后兼容。
- **Skill 体系重组**：`procedural-modeling` 改为轻量路由器（~80 行），按管道阶段分发到 5 个专用技能。
- **H21 hython 完整验证**：53/53 全过（Phase 0: 11 + Phase A: 20 + Phase B+C: 13 + Commit: 5 + Cleanup: 2）。三个 backend（native_chain/python/vex_skeleton）全部通过。network_mode sandbox 通过。
- **7 个 H21 兼容 bug 修复**：`.name`→`.name()` 类型序列化、`menuItems()` 返回字符串非对象、`_set_parm_safe` 添加 `parmTuple` 多分量参数支持、`params:{}` 空对象处理、`addAttrib` 重复创建防护、`A4_VEX_NO_DETAIL` 严重级别 WARNING、`attribwrangle.class=2`→`"detail"`。
- 478 测试通过（425 mock + 53 Houdini hython）。

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-06-21</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第三十一阶段：三阶段管道架构实现 + H21 hython 全验证</span>
      <span class="status-tag status-done">完成</span>
    </div>
    <div class="timeline-summary">① 三阶段管道全部落地：`parm_catalog.py`→`recipe_validator.py`(A1-A6)→`component_builder.py`(3 backend)→`component_cache.py`→`assembly_engine.py`。`build_procedural_asset` 内部串联全管道。② H21 hython 53/53 通过：Phase 0(11) + A(20) + B+C(13) + Commit(5)。native_chain/python/vex_skeleton 三 backend 全过。③ 7 个 H21 兼容 bug 修复：`.name`→`.name()` / `menuItems()` 字符串 / `parmTuple` 多分量 / `params:{}` 空处理 / `findPrimAttrib` 防护 / `A4_VEX_NO_DETAIL_WARNING` / `class="detail"`。④ 478 测试通过（425 mock + 53 hython）。</div>
  </div>
</div>

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-06-21</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第三十二阶段：vex_skeleton 双 wrangle Sweep + 派生参数系统 + add_parm 工具</span>
      <span class="status-tag status-done">完成</span>
    </div>
    <div class="timeline-summary">① 根因分析：车架 8/8 组件全用 Python 手写管材（add_tube()），违反"管材用 vex_skeleton"铁律。根因 = vex_skeleton 的 `_build_vex_skeleton_component` 有两个阻塞缺陷：(a) wrangle spare parm expr 用 `../../` 而非 `../`（同一作用域 bug 再次出现，session 日志 3 轮修复佐证），(b) form_node params 只支持静态值，不支持 ch() 通道表达式。② 修复 A：form_node params 检测字符串含 `ch(` 则调 `setExpression()` 而非 `set()` → 管长可参数化。③ 修复 B：wrangle spare parm expr 从 `ch("../../param")` 改为 `ch("../param")`。④ 修复 C：PolyExtrude 需要 polygon face 而非 polyline → VEX 用 `addprim(0,"poly")` 创建封闭面。⑤ 修复 D：PolyExtrude/Sweep 剥离 component_id 属性 → 在 form_node 后加 `attribwrangle` 重新打标。⑥ **架构突破**：扩展 `_build_vex_skeleton_component` 支持双 wrangle Sweep 模式（`section_code` 字段）。路径 wrangle + 截面 wrangle → Sweep 自动垂直对齐 → 完美封闭管材（endcaptype=1）。⑦ **派生参数系统**：实现 `_evaluate_derived_params`，params 支持 `kind: "derived"` + `from` 表达式。拓扑排序求值，16 个派生坐标一次计算、全部组件共享。⑧ **add_parm 工具**：`add_parm(node_path, name, default, min, max, label)` 一键创建 spare float 参数，返回 channel_path。⑨ **最终效果**：车架从 0% vex → **75% vex**（6 vex_skeleton + 1 native_chain + 1 python），Python 占比从 94%→12%。成功构建完整公路自行车车架（8 组件 273 点 185 面），保存可操作 .hip 文件。⑩ **文档更新**：declarative-builder.md（vex_skeleton 双模式、派生参数）、params-and-linkage.md（三态体系、add_parm）、pitfalls.md（hou.ch ../ 路径、poly vs polyline、outputback 命名）、wiki tools/progress/procedural-harness 同步更新。</div>
    <div class="timeline-tags">
      <span>三阶段管道</span><span>A1-A6验证</span><span>parm_catalog</span><span>工具重组</span><span>H21 hython</span><span>parmTuple</span><span>478测试</span>
    </div>
  </div>
</div>

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-06-22</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第三十三阶段：单构建路径 + 三道闸门（根治 road_bike 失败会话）</span>
      <span class="status-tag status-done">完成</span>
    </div>
    <div class="timeline-summary">① **根因**：road_bike 会话失败日志分析暴露 4 类失控——agent 谎报 7/9 为 7/7、832 开放边、402 退化面、hub 90° 错。根因是**双构建路径**（build_procedural_asset 与旧 component_builder/assembly_engine 并行）让 raw network_mode 手写网络能伪装成已验证资产提交。② **阶段 1 删旧 builder**：删 component_builder.py / assembly_engine.py / component_cache.py + build_component/assemble_components 工具（-776 行）。build_procedural_asset 成为唯一构建入口。③ **阶段 2 G1 验证闸 A8+A9**：A8 每个 orientation_assert 必须声明 construction_axis（PCA 已禁用，轴不能靠估计）；A9（BLOCKING）禁止组件代码里硬编码尺寸字面量（wheelbase=1.0），逃生口=加进 params/reads。④ **阶段 3 全组件烘焙轴 + G2 bake 闸**：决策 6——为每个组件烘焙 edini_world_axis（优先级：assert 声明 > 组件字段 > backend 推断 > Y 兜底），走推断/兜底的记入 defaulted_axes。G2 检查输出几何每个 prim 都带非零轴。⑤ **阶段 4 G3 commit 硬闸 + receipt**：commit_sandbox 三层防御——G3a 烘焙（堵 raw sandbox）/ G3b 方向 / G3c 健康（BLOCKING 检查）。失败保留 sandbox（决策 12）。成功返 verification_receipt（防篡改 JSON，agent 汇报必须逐字段引用，禁止自行计数）。⑥ **阶段 5 删 PCA fallback**：verify_orientation 的 PCA 估计分支移除（决策 3，根治 hub 90° bug——PCA 对细长圆柱体取惯性轴而非径向轴）。construction 路径的 PCA crosscheck 保留（warning-only）。⑦ **阶段 6 测试矩阵**：新增 test_pipeline_gates.py 17 用例，每条复现日志一个失败模式（A8/A9/G2/G3/receipt/sandbox 保留）。⑧ **阶段 7 文档/prompt**：params-and-linkage.md（尺寸必须进 params）、pitfalls.md（raw network_mode 无法过 G3）、verification/SKILL.md（receipt 引用规则）、edini-context（commit 返 receipt，汇报引用它）、procedural-modeling/SKILL.md（单构建路径流程图）。⑨ **取证发现**：spec 设想的约 40% 代码里已实现（construction_axis 烘焙、健康硬/软分档、PCA crosscheck），避免重复劳动。⑩ 521 测试通过（468 mock + 53 hython）。</div>
    <div class="timeline-tags">
      <span>单构建路径</span><span>A8必填construction_axis</span><span>A9硬编码尺寸</span><span>G2烘焙闸</span><span>G3提交硬闸</span><span>verification_receipt</span><span>删PCAfallback</span><span>hub90°根治</span><span>521测试</span>
    </div>
  </div>
</div>

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-06-16</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第三十阶段：Harness 两 Bug 修复 — 参数挂载 + degenerate 误报（真实 Houdini 验证）</span>
      <span class="status-tag status-done">完成</span>
    </div>
    <div class="timeline-summary">① 根因诊断：日志分析暴露两个 Harness bug，共同特征是"工具误报逼 agent 花 3 轮思考自证清白"。Bug A：`_install_spare_params` 用全新空 group 调 `setSpareParmGroup`，H21 非 HDA 节点上受限，失败被 `except Exception: pass` 吞掉 → `installed` 恒为 False，参数永不落地（自行车交付文案被迫写"参数暂时固化在代码里"）。Bug B：`inspect_geometry_health` 把 `0.5·|cross|²`（= `2·area²`，**不是**面积）与 `1e-7` 比，等效面积阈值 ~7e-5；且只取前 3 顶点 → 合法 fan-cap 三角（面积 2e-4 → `2·area²`=8e-8）被误报；n-gon cap 改 fan-cap 后误报数 238→1228。② Fix A（harness.py `_install_spare_params`）：改 read-merge 文件夹参数模式（Houdini 官方推荐、H21 兼容）—— `ptg = root.parmTemplateGroup()` 读现有（保留 Transform 等默认文件夹）→ `FolderParmTemplate("edini_params")` 装参数 → `setParmTemplateGroup(ptg)` merge-safe 写回。主路径 `setParmTemplateGroup` → 失败回退 `setSpareParmGroup` → 仍失败才降级 `installed=False`+warning。保持 geo 容器不变（视口零回归——所有几何读取都针对子级 OUT SOP）。修正过时注释 `../../`→`../`（组件 SOP 只在 root 下一层），同步 SKILL.md 通道路径文档。③ Fix B（node_utils.py `inspect_geometry_health`）：改 `prim.intrinsicValue("measuredarea")`（真实多边形面积，含 n-gon）优先，异常时回退修正后的 shoelace（遍历全部顶点对中心做扇形面积求和，修掉"只看前 3 顶点"+"单位错误"两缺陷）。阈值 `1e-7` 现在真的是面积阈值。④ Fix C（mock_hou.py）：新增 `MockFloatParmTemplate`/`MockFolderParmTemplate`/`MockParmTemplateGroup` 类 + `MockNode.parmTemplateGroup()`/`setParmTemplateGroup()`/`setSpareParmGroup()`/`evalParm()` 方法 + 注册 subnet 类型，使成功安装路径可测。⑤ Fix D（测试翻转）：`installed` 断言 False→True，并拆出降级路径测试（`_NoTemplate` 模拟 API 缺失，验证 `installed=False` 但默认值仍返回，用 try/finally 在共享 mock 上打补丁避免状态污染）。⑥ 新增 fan-cap 不误报回归测试（面积 2e-4 合法三角形断言不被标记）。⑦ 真实 Houdini 21.0.440 端到端验证：`manual_verify_fixes.py` 脚本（pre-flight 组件代码 isolation cook 抓真实 traceback）13/13 全过——5 个参数全部 `installed=true` 且 `eval()` 等于默认值、`edini_params` 文件夹在 root 接口、degenerate count==1（仅共线三角，合法小三角实测 measuredarea=2e-4 不误报）。⑧ 修复后重跑自行车 build 实证：`params_summary` 5/5 `installed=true`（之前全 false）、`degenerate_prims: 0`（之前 1228）、agent build 轮次 3→2、discard 2→1、输出 token -41%。遗留：Normal SOP `cangle` 参数名在 H21 变更（独立 bug，见计划）。382 测试通过。</div>
    <div class="timeline-tags">
      <span>参数挂载</span><span>read-merge文件夹</span><span>setParmTemplateGroup</span><span>degenerate误报</span><span>measuredarea</span><span>H21兼容</span><span>真实Houdini验证</span><span>2·area²单位错误</span><span>fan-cap回归</span><span>382测试</span>
    </div>
  </div>
</div>

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-06-15</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第二十九阶段：构造轴替代 PCA（B 站）— 朝向从估计变 ground truth</span>
      <span class="status-tag status-done">完成</span>
    </div>
    <div class="timeline-summary">① 问题诊断：A 站朝向门用 PCA 估计组件轴向有两个根本缺陷——点分布不均时估计漂移（不稳），且 agent 既生成几何又写 expected_axis（自洽校验，错误是相关的：误解"X 轴水平"会同时生成躺平轮子 + 写 expected_axis:Y，PCA 愉快确认）。② B 站核心：把启发式变成 ground truth——agent 在 recipe 的 orientation_asserts 声明 construction_axis（局部空间构造轴，如轮子绕 Y 生成），builder 用 anchor @orient 四元数代数推导世界轴（rotate_vector_by_quaternion，零估计零采样），烘焙成 prim 属性 edini_world_axis，verify_orientation 直接读它跳过 PCA（method=construction）。③ build 时一致性预检：construction_axis + anchor @orient + expected_axis 三者矛盾时（如 orient 把局部 Y 旋到世界 Z 但 expected_axis 写 X）build 在 cook 前拒绝整个 recipe 且不泄漏 sandbox——这是关键价值，挡住自洽错误。④ PCA 降级为可选 crosscheck（告警非硬门）：构造路径下若点数充足仍跑一次 PCA，偏差 > 2×容差时加 pca_crosscheck.warning 捕获"声明与代码不符"。⑤ 向后兼容：无 construction_axis 的老 recipe 继续走 PCA（method=pca），gate/commit 流程零改动。⑥ 寄生在 A 的 orientation_asserts schema 上：新增可选字段 construction_axis，不改 components/anchor schema。⑦ 197 测试通过（A 站 177 + B 站新增 20：纯数学 rotate 6 + verify 构造路径 4 + builder 预检/烘焙/向后兼容 10）。⑧ 全部用现有 mock_hou 可测，无需真实 Houdini。</div>
    <div class="timeline-tags">
      <span>构造轴</span><span>construction_axis</span><span>edini_world_axis</span><span>四元数代数</span><span>确定性推导</span><span>build时预检</span><span>自洽错误</span><span>PCA crosscheck</span><span>向后兼容</span><span>B站</span><span>197测试</span>
    </div>
  </div>
</div>

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-06-15</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第二十八阶段：声明式 Recipe Builder（A 站）— 程序化建模架构升级</span>
      <span class="status-tag status-done">完成</span>
    </div>
    <div class="timeline-summary">① 架构诊断：审视日志发现 agent 的核心瓶颈是 Houdini API 命令式编程能力不足（createNode-in-cook 无限递归、foreach blockpath 误连、H21 参数名盲区），gate 只能挡"做错的"挡不住"不会做的"。提出 5 站构想（A 声明式 builder / B 构造轴 / C 节点参数 DB / D 黄金范例 / E 数值代理），按杠杆排序分站交付。② A 站 `build_procedural_asset(recipe)`：agent 只写每组件的纯几何代码 + 一份声明式 recipe，harness 确定性建网。复用现有 sandbox 生命周期 + structure/orientation gate，gate 代码零改动。③ recipe schema：components[{id, code, anchors}] + postprocess + orientation_asserts。stamping 组件自动建 anchor 生成器 + copytopoints + idfix（逐实例覆盖 component_id 供 PCA）。④ 真实 Houdini 双阶段验证：单组件（基础设施全过）→ 二组件 + Copy-to-Points（idfix 逐实例 component_id 覆盖正确，40 点 8 prim，inventory 实扫 frame/wheel_fl/wheel_rr）。⑤ 顺手补 3 个验证工具的 TS schema（geometry_inventory/inspect_geometry_health/capture_component_detail 之前漏暴露）。⑥ 修复 test_error_surfacing 的 mock 孤儿化测试隔离 bug。⑦ 316 测试通过。commit 拆为代码（7bd740b）+ 文档（bce9d73）两个，分支 feat/network-mode-and-builder。</div>
    <div class="timeline-tags">
      <span>声明式Builder</span><span>recipe</span><span>确定性建网</span><span>Copy-to-Points</span><span>idfix</span><span>component_id</span><span>真实Houdini验证</span><span>A站</span><span>测试隔离修复</span><span>316测试</span>
    </div>
  </div>
</div>

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-06-15</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第二十七阶段：network_mode sandbox + Forbidden Patterns + H21 参数速查表</span>
      <span class="status-tag status-done">完成</span>
    </div>
    <div class="timeline-summary">① network_mode：`run_python_sandbox(network_mode=True)` 让代码跑在 sandbox geo 容器（非 Python SOP cook 内），可直接 createNode 子 SOP 建多节点网络，消除 cook 内 createNode 的"Infinite recursion in evaluation"。② Forbidden Patterns 章节：createNode-in-cook、raw houdini_run_python 绕过 sandbox、ForEach blockpath 误连、H21 参数名猜测——4 个反复出现的失败模式。③ Network Mode 章节 + recipe skeleton。④ Houdini 21 SOP 参数速查表：Attrib Promote(inname/inclass/outclass)、Blast(grouptype menu)、ForEach(blockpath 在 block_end 上)、Sweep 2.0、Copy-to-Points 2.0、Merge、Normal、Boolean——避免 agent 每次 get_node_info 探测浪费轮次。⑤ _bounds_nonzero 防 None 崩溃。⑥ 316 测试通过。</div>
    <div class="timeline-tags">
      <span>network_mode</span><span>Forbidden Patterns</span><span>H21参数速查</span><span>infinite recursion</span><span>_resolve_output_node</span><span>ForEach blockpath</span>
    </div>
  </div>
</div>

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-06-12</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第二十六阶段：模块化结构硬门 + 朝向门 + 三层验证协议</span>
      <span class="status-tag status-done">完成</span>
    </div>
    <div class="timeline-summary">① 模块化结构硬门（`_check_modular_structure`）：commit_sandbox 拒绝单体资产（≥3 component_id 全来自单个 Python SOP + 无 copytopoints/sweep/foreach）。agent 被迫分解成 body_generate + 子组件生成器 + Copy-to-Points。② `_select_gate_target` 修正：不再被空的 dispatcher Python SOP 误导（之前它会 shadow 真正的 OUT 导致 gate 误报 component_id not found）。③ 朝向门（`verify_orientation`）：PCA 按组件检测 radial/elongated/planar 轴方向，failed check 带 hint 四元数。commit 时硬关卡。④ 三层验证协议：geometry health（orphan/degenerate/non-manifold）→ orientation → inventory/data → visual。health 是 MANDATORY layer-1。⑤ 取景修复：4 视图 capture 自动框到 target bounding box，不再裁切。⑥ vision 不再评朝向（移除 orientation 维度，加 projection immunity）。⑦ SKILL.md enforce health-first workflow。</div>
    <div class="timeline-tags">
      <span>模块化硬门</span><span>朝向门</span><span>PCA</span><span>三层验证</span><span>component_id</span><span>health-first</span><span>取景修复</span><span>_select_gate_target</span>
    </div>
  </div>
</div>

### Procedural Harness Phase B

- Added live sandbox workflow for procedural generation.
- Added diagnostics before retry/delete, structural asset verification, sandbox commit/discard, and safe viewport capture.
- Updated procedural-modeling skill so agents use harness tools before raw Houdini Python.
- Preserved Phase C path through `job_id`, `execution_mode`, diagnostics bundles, and artifact-shaped result fields.

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-06-11</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第二十五阶段：程序化建模 Skill + LogParser 参数提取修复</span>
      <span class="status-tag status-done">完成</span>
    </div>
    <div class="timeline-summary">① 调研 AI+Houdini 程序化建模可行性：HoudiniVexBench 基准测试显示 VEX 从零生成执行成功率仅 36%（Claude Opus 4.5 最高分 0.512），确认 Python SOP 优先策略 ② 创建 procedural-modeling Skill（644 词）：语言选择策略表（VEX/Python SOP/hou API/Copernicus）、VEX run-over class（point/prim/vertex/detail）首选设置、分而治之思考策略、模板模式适配、失败两次自动切换 Python、常见 VEX 陷阱 4 条、Copernicus 程序化贴图 4 步流程 ③ 修复 LogParser 重大 bug：ToolCallRecord.params 永远为 {}（写死 params={}），改为两阶段匹配——从 assistant 消息提取 toolCall.arguments（含完整 VEX/Python 代码），用 toolCallId 与 toolResult 匹配回填。修复后 98% tool call 有参数（之前 0%），评估系统现在可以分析 VEX 代码模式/长度/失败原因 ④ 全部 157 测试通过</div>
    <div class="timeline-tags">
      <span>procedural-modeling</span><span>Skill系统</span><span>VEX run-over class</span><span>分而治之</span><span>LogParser修复</span><span>参数提取</span><span>98%参数覆盖率</span><span>HoudiniVexBench</span>
    </div>
  </div>
</div>

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-06-10</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第二十四阶段：识图管道完整修复 — 配置注入 + 会话路径 + 临时文件过滤</span>
      <span class="status-tag status-done">完成</span>
    </div>
    <div class="timeline-summary">① 修复视觉模型配置丢失：get_pi_env() 未注入 VISIONIZER_PROVIDER/VISIONIZER_MODEL_ID 环境变量，导致 pi-visionizer 的 resolveConfig() 返回 undefined，图片原样发给纯文本模型→识图失败 ② 新增：从 Edini settings.json 读取 vision_provider/vision_model_id，注入到 pi 子进程环境变量中 ③ 修复会话路径缺失：_on_agent_started() 中新增 send_get_state() 调用，使 _current_session_path 在普通对话流程中也能被填充（之前仅在手动 new_session/switch_session 后设置），修复图片缓存和视觉描述无法写入磁盘的问题 ④ 修复 describe_image 临时文件报错：浏览器拖放图片时产生的 Temp 临时文件路径残留到 LLM 上下文，LLM 调用 describe_image 失败→增强 ENOENT 处理：检测 Temp 目录路径，返回引导性提示；增强 stripNoVisionNote：过滤 describe_image 关键词 + 正则过滤 Temp 临时图片路径 ⑤ 生产环境日志清理：删除 20+ 条 [Edini:img] 调试输出（image_cache.py + main_window.py + pi_sessions.py），sed 批量删除 + 语法修复 ⑥ 修复两份代码副本同步问题（edini/ vs python3.11libs/edini/）⑦ 端到端验证：历史对话可看到图片缩略图和视觉描述气泡</div>
    <div class="timeline-tags">
      <span>视觉配置注入</span><span>环境变量</span><span>会话路径自动获取</span><span>临时文件过滤</span><span>日志清理</span><span>describe_image修复</span><span>双副本同步</span>
    </div>
  </div>
</div>

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-06-10</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第二十三阶段：图片缓存竞态修复 + 查看原图交互优化</span>
      <span class="status-tag status-done">完成</span>
    </div>
    <div class="timeline-summary">① 修复图片缓存写入竞态条件：_on_agent_done 先于 _on_pi_session_switched 到达时，session_path 为空导致缓存跳过写入 → pending 数据在 _on_agent_done 中被清零，session_switched 后已无数据可写 ② 修复方案：_on_agent_done/_on_abort_request/_on_error 中仅在 session_path 已确认时才清零 pending 数据，否则保留给 _on_pi_session_switched 写入 ③ _on_pi_session_switched 写入缓存后显式清零 pending ④ 新增 _flush_pending_image_cache() 统一缓存写入方法（从 admin_window 内联逻辑抽取）⑤ VisionDescriptionBubble 头部新增 "📸 原图" 按钮（始终可见，有图片时显示）⑥ 头部标签点击即可查看原图 ⑦ 修复 set_original_images() 错误更新 _toggle_btn 而非 view_btn 的 bug ⑧ 全面调试日志覆盖（[Edini:img] 前缀，image_cache + main_window + pi_sessions 完整链路）</div>
    <div class="timeline-tags">
      <span>竞态修复</span><span>图片缓存</span><span>session_switched</span><span>agent_done</span><span>查看原图</span><span>调试日志</span><span>flush方法</span>
    </div>
  </div>
</div>

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-06-10</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第二十二阶段：MD 渲染 mistune 重构</span>
      <span class="status-tag status-done">完成</span>
    </div>
    <div class="timeline-summary">① 手写 ~250 行正则 Markdown→HTML 渲染器存在 4 个 bug（代码块双重转义、数学误判斜体、流式不分段、bold 跨行失败）② 调研 mistune / markdown-it-py / QMarkdownWidget 后选型 mistune 3.2.1（零依赖、纯 Python、性能最快）③ 自定义 _DarkRenderer 继承 HTMLRenderer，覆盖所有 tag 方法注入暗色主题 inline style ④ _format_lite = _format_full = mistune.html(text)，流式/最终渲染 pixel 级一致 ⑤ 新增语法支持：h4-h6、引用块 `>`、图片 `![alt](url)`、删除线 `~~`、任务列表 `- [ ]` ⑥ pip install --target python3.11libs/ 部署 ⑦ 57 项测试全部通过</div>
    <div class="timeline-tags">
      <span>mistune</span><span>Markdown渲染</span><span>pyc缓存</span><span>暗色主题</span><span>GFM</span>
    </div>
  </div>
</div>

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-06-09</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第二十一阶段：知识反思面板 + 去重</span>
      <span class="status-tag status-done">完成</span>
    </div>
    <div class="timeline-summary">① ReflectWorker（QThread 后台线程）：对话结束后独立 HTTP 调 LLM API 反思，不占用主时间线 ② KnowledgeZone 替代旧 Knowledge 卡片：可折叠规则/条目浏览 + 反思过程实时展示 + 条目卡片确认/拒绝 ③ Jaccard 标题去重：新条目自动检测与已有知识的相似度，≥0.5 标记为 merge ④ 合并：merge_entry 将新旧条目内容合并为一个更通用的版本 ⑤ 设置面板新增"反思模型"选择（Provider + Model），默认对话模型 ⑥ AgentPanel 移除旧的知识提取 UI（~160 行） ⑦ MainWindow 旧提取流程替换为 ReflectWorker 触发 ⑧ Houdini 实测修复 4 bug：RpcClient 信号缺失、撤销方法误删、PROJECT_ROOT 路径、pi-ai 桥接函数丢失</div>
    <div class="timeline-tags">
      <span>ReflectWorker</span><span>KnowledgeZone</span><span>Jaccard去重</span><span>HTTP直调</span><span>反思模型配置</span><span>稳定性修复</span>
    </div>
  </div>
</div>

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-06-09</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第二十阶段：测试基建 + 知识检索闭环 + 评估联动</span>
      <span class="status-tag status-done">完成</span>
    </div>
    <div class="timeline-summary">① Mock Hou 模块（MockNode/MockParm/MockNodeType/MockCategory）支持全部 22 个 handler 脱机测试 ② node_utils 单元测试 48 用例覆盖全部 handler ③ config.py 测试 24 用例覆盖读写 JSON、路径查找、legacy 迁移 ④ knowledge_store 测试 33 用例覆盖 CRUD/search/parse extraction ⑤ edini_search_knowledge Pi 工具注册，Agent 可查询知识库 ⑥ 评估低分会话自动提取知识条目 ⑦ 全部测试 105+ 通过</div>
    <div class="timeline-tags">
      <span>单元测试</span><span>Mock Hou</span><span>知识检索</span><span>评估联动</span>
    </div>
  </div>
</div>

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-06-09</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第十九阶段：供应商与模型配置重构 — pi CLI 风格 + pi-ai 自动同步</span>
      <span class="status-tag status-done">完成</span>
    </div>
    <div class="timeline-summary">① 设置面板重构为 3 Tab：Providers & Models / Appearance / Knowledge ② Login/Logout pi CLI 风格交互：可搜索供应商列表（35 内置供应商 + 自定义供应商）→ API Key 输入 ③ pi_data_bridge.js Node.js 桥接：读取已安装 pi-ai 包数据，pi 更新后自动同步 ④ Chat Model Provider→Model 级联下拉 + Vision Model 独立选择（仅 image-capable 模型） ⑤ 自定义供应商支持 API Key ⑥ 修复：models.json 无效 provider 导致 pi 拒绝加载所有自定义供应商（根本原因）→ 视觉识别从此正常工作</div>
    <div class="timeline-tags">
      <span>pi-ai同步</span><span>Login/Logout</span><span>Vision Model</span><span>35供应商</span><span>视觉识别修复</span>
    </div>
  </div>
</div>

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-06-08</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第十八阶段：评估修复 + 工具补齐 + 智谱Provider + 设置增强</span>
      <span class="status-tag status-done">完成</span>
    </div>
    <div class="timeline-summary">① 三层评估架构：数据模型（StructuredSession/ToolCallRecord/EvalResult）→ SQLite EvalStore（4 表 CRUD + 聚合）→ EvaluatorPipeline（5维度：reliability/efficiency/cost 确定性 + tool_accuracy/task_completion LLM-as-Judge）② LogParser 适配 Pi RPC JSONL 格式（message.toolName 提取工具名，content 解析 success/error）③ EvalDashboard UI（_ScoreCard 概览卡片、_TrendChart 趋势折线图、QTableWidget 会话列表、双击导航）④ edini_get_eval_stats Pi Extension 工具（自省：平均分/趋势/最弱维度/常见错误）⑤ MainWindow 集成（状态栏 📊 Eval 按钮 + 弹窗）⑥ 后台自动触发评估（finish_streaming/show_aborted → 线程评估 → 保存）⑦ LLM-as-Judge 真实 API 调用（DeepSeek deepseek-chat，2 轮/会话，～4.4s 平均）· 实测 8 个 Houdini 对话，评分合理有区分度 · 发现 V4 Pro reasoning_tokens 问题 · Wiki 记录设计理念 + 实测结果 + 经验教训</div>
    <div class="timeline-tags">
      <span>5维度评估</span><span>SQLite</span><span>LLM-as-Judge</span><span>LogParser</span><span>EvalDashboard</span><span>edini_get_eval_stats</span><span>后台评估</span><span>DeepSeek</span><span>V4 Pro推理问题</span><span>设计理念</span>
    </div>
  </div>
</div>

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-06-08</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第十八阶段：评估修复 + 工具补齐 + 智谱Provider + 设置面板增强</span>
      <span class="status-tag status-done">完成</span>
    </div>
    <div class="timeline-summary">① Eval修复：force_no_judge LLM Judge失败自动回退 / traceback完整日志 / PRAGMA d[0]→d[1]修复 / ⚡ Re-evaluate按钮 / 纯确定性评估先跑通16个历史会话 ② 缺失工具补齐：houdini_get_selection (hou.selectedNodes) / houdini_check_errors (allSubChildren errors+warnings) / houdini_set_display_flag (setDisplayFlag) — scene.ts已注册但Python handler缺失 ③ Ramp参数安全：_safe_parm_value() 检测hou.Ramp返回结构化keys / allowEditingOfContents解锁HDA子节点 / HDADefinition属性安全read ④ 智谱Coding Plan接入：新建edini-zhipu扩展(5模型: glm-5.1/5/4.7/4.6v/4.5v) / Coding专属端点 / ZHIPU_USE_CODING=1切换 ⑤ API Key修复：get_pi_env()改用_set_provider_api_key按provider分发 / send_set_model在connect+save时调用 ⑥ 设置面板增强：新增Vision标签(视觉Provider/Model/Key) / Test Model按钮(通过tool_executor:9876/test_model中转，ssl._create_unverified_context) / QTimer.singleShot替代QMetaObject.invokeMethod / 按钮状态瞬时反馈+异常捕获 ⑦ 知识库清理：合并3条重复Ramp规则→1条/更新已修复工具规则/20→18</div>
    <div class="timeline-tags">
      <span>Eval修复</span><span>3个缺失工具</span><span>Ramp安全</span><span>智谱Provider</span><span>CodingPlan</span><span>Vision设置</span><span>Test按钮</span><span>APIKey修复</span><span>知识库清理</span>
    </div>
  </div>
</div>

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-06-08</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第十七阶段补丁：端到端调试与 Python 3.11 兼容修复</span>
      <span class="status-tag status-done">完成</span>
    </div>
    <div class="timeline-summary">① 修复 f-string 反斜杠兼容问题（eval_tab.py — 改用 _EM_DASH 常量；evaluator.py — 改用变量 _json_example）② 修复 ScoreCard 按钮裁切（125px+dialog 960px+QScrollArea）③ 修复 session 路径时序竞争（agent_end 先于 session_switched — 延迟触发评估）④ 修复 _debug_log 函数缩进错误吞掉后续 AgentPanel 方法（_toggle_thinking_panel 找不到）⑤ 添加诊断日志系统（_debug_log 写入 %%TEMP%%/edini_eval_debug.log）⑥ 空数据状态显示提示文字</div>
    <div class="timeline-tags">
      <span>f-string兼容</span><span>Python3.11</span><span>时序竞争</span><span>缩进bug</span><span>诊断日志</span><span>UI适配</span>
    </div>
  </div>
</div>

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-06-06</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第十六阶段：多模态 UI 按钮优化 + 剪贴板全渠道修复</span>
      <span class="status-tag status-done">完成</span>
    </div>
    <div class="timeline-summary">① 📋 Paste 按钮移除：用户通过 Ctrl+V 或右键粘贴，不占面板空间 ② 按钮布局重排：📷 截图 + 📁 上传改为文本标签按钮（minHeight 34px, padding 4px 10px），不再被裁切，hover/pressed 动效 ③ 仅对话右对齐 · 执行按钮 minWidth 90px · 6px/8px 间距 ④ 移除旧截图槽位+移除按钮，截图统一走附件栏 ⑤ 剪贴板粘贴修复：QImage.save() 在 Houdini PySide6 中不接受 BytesIO/QBuffer → 改用 tempfile 中转 ⑥ 剪贴板多模式探测：image()→mimeData().imageData()→URLs→raw image/png image/jpeg，覆盖浏览器/截图工具/文件管理器等所有来源 ⑦ Houdini 20 视窗截图修复：saveImage() 和 grabFrameBuffer() 在 20.x 中已移除 → flipbook 方法 frameRange([1.0, 1.0]) 修复 ⑧ 右键上下文菜单：monkey-patch contextMenuEvent（Houdini 阻止 eventFilter 收到 ContextMenu 事件），图片剪贴板时显示 "📋 粘贴图片到附件栏" + "粘贴文本"（QTimer.singleShot defer focus+paste），无图片时走原生菜单 ⑨ PySide6 枚举兼容：Qt.Clipboard/Selection/FindBuffer 不存在 → 整数 mode 值 0/1/2</div>
    <div class="timeline-tags">
      <span>按钮布局</span><span>剪贴板修复</span><span>右键菜单</span><span>Houdini20适配</span><span>QImage.save</span><span>PySide6兼容</span><span>contextMenuEvent</span><span>tempfile</span>
    </div>
  </div>
</div>

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-06-06</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第十五阶段：图片时间线显示 — 缩略图卡片 + 历史持久化 + 视觉描述缓存</span>
      <span class="status-tag status-done">完成</span>
    </div>
    <div class="timeline-summary">① ImageCacheManager：图片缓存与 Pi 会话同目录（edini_images/<session_id>/manifest.json + 原始图片文件），支持 save/load/prune ② 时间线缩略图卡片：_UserBubble 中 96×68 缩略图 _ClickableCard（IgnoreAspectRatio 填满、QFrame mouseReleaseEvent 可靠点击），点击在 OS 查看器中打开 ③ 原始文件名保留：MediaItem.filename → _on_send → _on_agent_submit → 缓存 + 气泡，全链路传递 ④ 视觉描述持久化：_on_vision_description 收到通知时保存 descriptions.json，历史加载时重新渲染 VisionDescriptionBubble ⑤ Defer 缓存写入：_current_session_path 异步就绪时才写缓存，解决 Pi session 路径延迟问题 ⑥ _cleanup_recognizing 不再清除 _pending_images，避免缓存 flush 被跳过 ⑦ QPixmap 缩略图启用：make_thumbnail + _load_thumb_pixmap try/except 安全保护 ⑧ 附件栏缩略图恢复真实显示（不再 🖼️ 占位）⑨ 会话删除时自动清理孤立的图片缓存</div>
    <div class="timeline-tags">
      <span>缩略图卡片</span><span>图片缓存</span><span>历史持久化</span><span>视觉描述缓存</span><span>Defer写入</span><span>原始文件名</span><span>QPixmap</span><span>edini_images</span>
    </div>
  </div>
</div>

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-06-06</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第十四阶段：多模态调试修复 — 视觉管道打通 + UI 体验优化</span>
      <span class="status-tag status-done">完成</span>
    </div>
    <div class="timeline-summary">① 修复 pi-visionizer fetch 死锁：Windows 上 Pi 的 undici 全局代理导致 fetch() 永久挂起 → 改用 Node.js 原生 https.request() ② 修复通知 API：sendUiRequest 不存在 → 改用 ctx.ui.notify() ③ 修复 Aliyun API Key：auth.json 缺少 aliyun 条目 → 添加 sk-ded80b7... ④ 识别中状态提示：_RecognizingPlaceholder 虚线框 "🔍 正在识别图片…"，通知到达后自动替换 ⑤ 视觉描述气泡默认折叠：显示 "👁️ 图片识别完成 · qwen-vl-max · 3.2s ▶ 展开" ⑥ 查看原图：气泡内 📸 按钮用 OS 默认查看器打开原图 ⑦ 缩略图安全降级：QBuffer 导致 Houdini segfault → 改用 emoji 🖼️ 占位 ⑧ rpc_client 添加 stderr 读取线程 + vision_description 日志</div>
    <div class="timeline-tags">
      <span>https.request</span><span>undici死锁</span><span>ctx.ui.notify</span><span>识别中状态</span><span>默认折叠</span><span>查看原图</span><span>segfault修复</span>
    </div>
  </div>
</div>

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-06-05</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第十三阶段：多模态扩展 — 全渠道图片输入 + Qwen-VL</span>
      <span class="status-tag status-done">完成</span>
    </div>
    <div class="timeline-summary">① 全渠道图片输入：截图（三级降级修复 saveImage→grabFrameBuffer→flipbook）、拖拽（仅拦截图片 MIME）、粘贴（Ctrl+V 剪贴板图片）、文件选择（📁 按钮 + 多选过滤）② ImageAttachmentWidget 附件预览栏（缩略图 120×68 + 来源图标 + ✕ 删除，最多 5 张）③ VisionDescriptionBubble 视觉描述气泡（可折叠、查看原图、错误变体）④ pi-visionizer 默认视觉模型改为 aliyun/qwen-vl-max ⑤ pi-visionizer 写入 vision-description custom entry + extension_ui_request 实时通知 Edini ⑥ MediaManager 统一管理所有图片输入渠道 ⑦ rpc_client 新增 vision_description 信号</div>
    <div class="timeline-tags">
      <span>pi-visionizer</span><span>Qwen-VL</span><span>视觉代理</span><span>截图按钮</span><span>多模态</span>
    </div>
  </div>
</div>

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-06-05</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第十二阶段：时间线 Markdown 渲染 + 变更树修复</span>
      <span class="status-tag status-done">完成</span>
    </div>
    <div class="timeline-summary">① Markdown 双格式化器：_format_full（标题/列表/表格/代码块/p 段落）用于最终+历史，_format_lite（仅行内 bold/italic/code）用于流式 ② _render_body 统一 body 渲染（table/list/paragraph），header+body 组合支持（### 下跟表格/列表）③ 历史气泡合并：_merge_consecutive_assistants 合并 JSONL 中连续的 assistant entry 为单个气泡 ④ 知识提取过滤：_filter_knowledge_extraction 隐藏提取对话 ⑤ 文本选择：AiBubble/UserBubble 加 TextSelectableByMouse，UserBubble→RichText ⑥ 移除代码 Copy 按钮 ⑦ 间距收紧（line-height 1.55→1.45, padding 10/16→8/14）⑧ 标题裁切修复（COLLAPSED_H 20→24）⑨ 变更树空时不展开 ⑩ 快照 diff 过滤自变参数（time/frame/seed/cache）⑪ 切换/新建对话清除变更树+undo</div>
    <div class="timeline-tags">
      <span>双格式化器</span><span>完整Markdown</span><span>气泡合并</span><span>知识过滤</span><span>文本选择</span><span>变更树修复</span>
    </div>
  </div>
</div>

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-06-05</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第十一阶段：UI 字体协调优化</span>
      <span class="status-tag status-done">完成</span>
    </div>
    <div class="timeline-summary">统一整个 Edini UI 的字号层级为 4 层体系：① header (fs13) — 面板标题、section 标签 ② body (fs12) — 聊天气泡、标签、按钮、菜单、列表 ③ detail (fs11) — Thinking 内容、工具卡片、树节点、知识详情 ④ caption (fs10) — 状态栏、进度条、折叠头、徽章小字、tooltip。消除全部 fs(9) 和硬编码 pt 值（history_panel 原使用 raw "12pt"/"11pt"）。代码块和行内代码字号改用 fs() 缩放。放宽固定尺寸（知识徽章 36→40px，分类标签 32→40px，卡片行标签 50→56px，面板 COLLAPSED_H 22→24 / EXPANDED_H 260→280）。6 个文件精确修改，零裁切回归。</div>
    <div class="timeline-tags">
      <span>字号体系</span><span>4层统一</span><span>fs()缩放</span><span>消除硬编码pt</span><span>视觉协调</span>
    </div>
  </div>
</div>

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-06-05</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第十阶段：变更树 + Undo/Redo + 节点创建预设修复</span>
      <span class="status-tag status-done">完成</span>
    </div>
    <div class="timeline-summary">① SnapshotEngine（snapshot / diff / restore 三阶段节点级回滚）② ChangeTreeWidget 重写（QTreeWidget，按轮次分组，创建/修改/删除三级树，节点路径可点击跳转 viewport）③ Undo/Redo 栈（每轮对话一个事务，撤销=整轮回滚重建，重做=重放，手动修改场景自动清空栈）④ 对话中自动折叠、对话结束自动展开 ⑤ 节点创建 namespace 自动解析（裸名失败 → namespaceOrder → 全限定名）⑥ Shelf tool 预设自动应用（创建后查找匹配 tool 脚本，执行 pressButton/set 后处理操作）⑦ diff 过滤 Houdini 自动生成的子节点 ⑧ 参数紧凑显示（≤2参数全显示，3+ 收起为摘要，点击展开）</div>
    <div class="timeline-tags">
      <span>SnapshotEngine</span><span>变更树</span><span>Undo/Redo</span><span>视图跳转</span><span>namespace解析</span><span>tool预设</span><span>紧凑显示</span>
    </div>
  </div>
</div>

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-06-05</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第九阶段：时间线稳定性重构 — QScrollArea Widget 架构</span>
      <span class="status-tag status-done">完成</span>
    </div>
    <div class="timeline-summary">彻底重构时间线渲染引擎：① 从 QTextBrowser + setHtml 全量重绘 重构为 QScrollArea + 独立 Widget（_UserBubble / _AiBubble / _Separator / _ErrorBanner）② 智能滚动从 actionTriggered + 比例定位 改为 rangeChanged + valueChanged + _pinned_to_bottom 标志位（彻底消除抖动）③ 修复流式内容丢失 bug：_flush_thinking_buf 清空 _current_text 导致气泡只显示新 chunk，新增 _streaming_full_text 永不清空的累加器 ④ Thinking 面板实时更新：add_thinking_step 直接调用 _update_live_thinking，不再等待文字 chunk ⑤ 气泡大小固定：去掉 setMaximumWidth + stretch，改用 layout margin + Expanding sizePolicy 填满窗口 ⑥ 完成后自动折叠：_collapse_tool_panel + _collapse_thinking_panel 在 finish_streaming 和 show_aborted 中调用。修复：双 deleteLater、QLabel 选择器兼容、_raw_text 追踪。</div>
    <div class="timeline-tags">
      <span>QScrollArea</span><span>Widget架构</span><span>智能滚动</span><span>流式持久化</span><span>气泡自适应</span><span>自动折叠</span>
    </div>
  </div>
</div>

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-06-05</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第八阶段：知识沉淀系统重构 — 两层架构</span>
      <span class="status-tag status-done">完成</span>
    </div>
    <div class="timeline-summary">完全重构知识系统为两层架构：① 铁律层（rules.json，≤20条，每次会话自动注入 system prompt）② 知识库层（entries.json，无上限，细节化知识）③ 提取流程改为 AI 反思 → JSON 解析 → 聊天面板内确认区展示 → 用户逐条 ✓✕ 或全部接受/放弃 ④ 铁律/知识类型徽章可点击切换 ⑤ 提取 prompt 严格限制：只有会重复犯的错才提取，排除 LLM 已知的通用知识 ⑥ Settings Dialog 改为 General + Knowledge 双标签 ⑦ Context Panel 新增 Pi Status 工具信息 + 对话计时器 + Knowledge 卡片 ⑧ JSON 解析加固：代码块提取、单引号修复、尾逗号修复 ⑨ 提取响应不再渲染进时间线（get_raw_stream_text + cancel_current_stream）⑩ 移除调试 stderr 输出。修复：3 位 hex 颜色解析、knowledge_dialog 空指针、时间线消失 bug。</div>
    <div class="timeline-tags">
      <span>两层架构</span><span>用户确认面板</span><span>铁律上限20</span><span>类型切换</span><span>提取prompt优化</span><span>Settings双标签</span><span>JSON加固</span><span>12文件</span>
    </div>
  </div>
</div>

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-06-04</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第七阶段：知识沉淀系统初版 + Thinking 独立面板 + Windows 部署</span>
      <span class="status-tag status-done">已重构</span>
    </div>
    <div class="timeline-summary">初版知识沉淀系统（单文件 JSON、自动存储、无用户确认），已在第八阶段重构为两层架构。Thinking 面板从 _ThinkingPanelWidget 独立类重构为 AgentPanel 内联实现。部署完善：install.py + MainMenuCommon.xml + CREATE_NO_WINDOW + 进程终止加固。</div>
    <div class="timeline-tags">
      <span>已重构</span><span>初版v1</span><span>Thinking面板</span><span>部署配置</span>
    </div>
  </div>
</div>

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-06-04</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第六阶段：Session 浏览模式 + 三个 Bug 修复</span>
      <span class="status-tag status-done">完成</span>
    </div>
    <div class="timeline-summary">实现会话浏览模式并修复三个关键 Bug：① HistoryPanel 新增 set_browsing_mode() / highlight_session() / back_to_current_requested 信号 ② MainWindow 新增 _active_session_path / _browsing_session_path 状态字段 ③ 修复 Windows 盘符冒号 ④ 修复 Pi v3 session 格式兼容 ⑤ 修复 HOME vs USERPROFILE 路径问题。</div>
    <div class="timeline-tags">
      <span>浏览模式</span><span>回到当前</span><span>Windows路径修复</span><span>Pi v3兼容</span><span>HOME路径修复</span>
    </div>
  </div>
</div>

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-06-04</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第五阶段：Session 架构重构 — pi 接管会话管理</span>
      <span class="status-tag status-done">完成</span>
    </div>
    <div class="timeline-summary">彻底重构 Session 管理：① 删除 edini session_store.py，pi 成为唯一真理源 ② Popen(cwd=HIP) 启动（去掉 --no-session）③ 新建 pi_sessions.py 读 pi JSONL ④ RpcClient 新增 new/switch/set_name/get_state ⑤ ContextPanel reset_stats() ⑥ 修复窗口单例、ensure_ascii、_bootstrap 时序问题。</div>
    <div class="timeline-tags">
      <span>pi 接管 Session</span><span>删除 session_store</span><span>pi_sessions</span><span>Popen cwd</span><span>RPC 新命令</span>
    </div>
  </div>
</div>

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-06-04</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第四阶段：UI 稳定化 — Thinking 独立面板 · 纯文本流 · 滚动防抖</span>
      <span class="status-tag status-done">完成</span>
    </div>
    <div class="timeline-summary">重构 Thinking 展示：独立可折叠面板（QTextEdit 只读，自然段落分段，实时流 ▊ 光标，自动滚底）· Tool Call 面板 fixedHeight 折叠 · 智能滚动 actionTriggered + 同步比例定位 · TimelineView anchorClicked + base64 Copy · Thinking 实时分段。</div>
    <div class="timeline-tags">
      <span>Thinking 独立面板</span><span>纯文本流</span><span>防抖滚动</span><span>Copy 修复</span>
    </div>
  </div>
</div>

<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-06-04 · 06-03</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第一~三阶段：基础架构 → UI 重构 → UI 精细化</span>
      <span class="status-tag status-done">完成</span>
    </div>
    <div class="timeline-summary">第一阶段：PySide6 + JSON-RPC + HTTP 工具执行器 + 16 tools + DeepSeek。第二阶段：Houdini 原生菜单 + QSplitter 三栏 + 暗色主题。第三阶段：Pi CLI 风格双层折叠 + Session 系统 + Viewport 截图 + 智能滚动。</div>
    <div class="timeline-tags">
      <span>PySide6</span><span>JSON-RPC</span><span>16 tools</span><span>三栏布局</span><span>Session管理</span>
    </div>
  </div>
</div>

</div>

## 下一步计划

### ⚠️ 接手者必读：当前主线 = 声明式资产管道（自底向上重启）

程序化建模经历了三次演进，接手者必须理解这个**上下文转折**：

1. **第一次（已废弃）**：提示词驱动 + ABCDE 五站 + G1-G3 闸门。失败根因 = 规则跑在能力前面。
   代码备份在 `_disabled_backup/procedural-modeling/`（含 `exprs.py`/`recipe_validator.py`/
   `component_registry.py` 等高质量前身，里程碑1 已部分复活复用）。
2. **第二次（仍有效）**：Recipe Library 转向「参考样本」定位。recipe 降低 LLM 语法出错率，
   不限死能力。**这条定位在资产管道里继续生效**——recipe 教惯用法，资产管道教结构。
3. **第三次（当前方向）**：声明式资产管道，自底向上逐层做，**capability before rules**（先有工具
   再写 skill 规则，绝不重蹈"规则要求不存在的能力"的覆辙）。

**新流程 6 阶段**：拆分组件 → 骨架点 DAG → 盒子占位 → 参数库 → native 节点链实现 → 组装提交。
核心设计决策（与用户共同敲定）：
- **组件之间不互相连接**，都连接到一张参数驱动的骨架点表（DAG）。轮子不知道车架存在，
  它们都知道 `rear_axle` 这个点。这是连接问题的解。
- **参数库禁硬编码**：任何数字必须能在参数库或骨架点找到来源。primary（用户调）+ derived（表达式算）。
- **盒子占位优先**：先用盒子摆比例朝向，在盒子上做廉价验证（连接点对齐、比例合理性），
  再做真实几何。**不做 AABB 相交检测**（自行车轮子天然嵌在车架里，AABB 必误报）。
- **native 节点链优先**：叶子组件能用 circle→sweep/torus/polyextrude 拼就拼，拼不出才用 Python SOP。
- **方向不靠烘焙**：组装阶段的方向验证直接读骨架点 DAG 的朝向，不再要求 agent 手 bake
  `edini_world_axis`（这消灭了自行车日志里的死循环）。

### 资产管道里程碑路线图

| 里程碑 | 内容 | 状态 | 关键文件 |
|--------|------|------|----------|
| **M1 骨架点 + 表达式引擎** | exprs.py + skeleton_resolver.py + asset_model.py + validate_asset 工具。纯数据层，shift-left 验证。 | ✅ **交付 + 真机实测通过**（162 单元/集成测试 + hython 端到端 5 项，修 2 bug + 样例数学修正） | exprs.py / skeleton_resolver.py / asset_model.py / tool_executor.py(validate_asset) / pi-extensions/edini-tools/tools/asset.ts / data/bicycle.asset.json / tests/test_{exprs,skeleton_resolver,asset_model,tool_executor_asset,asset_hython}.py |
| **M2 组件构建** | `components[]` 真正生成几何，挂到骨架点。native 节点链 + python backend（Python SOP 画曲线）+ 多实例 + orient 旋转 + from-to 两点连接（管材/桁架）。组件声明 attach 到哪个骨架点、读哪个参数。 | ✅ **完整能力交付 + 自行车真机验证**（自行车 6 组件 224 点：4 from-to 管材 + 2 python 轮子）。3 种 placement（attach/instances/from-to）+ 2 backend + orient。实战测试（椅子→自行车）暴露并修复 3 真实缺陷 | asset_builder.py（_build_native_chain/_build_python_component/_inject_param_values/_from_to_geometry/_move_to_point）/ asset_model.py(_validate_components) / tool_executor.py(build_asset) / pi-extensions asset.ts / skills/asset-authoring/SKILL.md / data/{table,chair,bicycle}.asset.json / tests/test_asset_{builder,model,hython,tool_executor_asset}.py |
| **M3 盒子占位 + 早期验证** | 拆分阶段先输出盒子几何，做连接点对齐 + 比例合理性验证。 | ⏸️ **暂缓**（经分析：历史失败无一是骨架点摆位错；M1 resolve_skeleton 已能预览坐标发现几何错；约束断言=领域规则会扼杀创造力。自行车实战证明 resolve 预览足够） | — |
| **M4 组装提交 + skill** | 组件合并到 OUT，方向验证读骨架点朝向（不烘焙 axis）。**最后才写 skill 规则**（capability before rules）。 | ✅ **交付 · 真机待测**（标记+绕过策略：build_asset 打 edini_asset_source userData 印记 → commit_sandbox 识别后绕过旧 G3a bake/G3b PCA 门禁，保留 G3c 健康+结构门禁，receipt 标 method=declarative） | asset_builder.py(setUserData 印记) / harness.py(commit_sandbox 识别分支 + receipt method) / tests/test_commit_declarative.py / tests/test_asset_hython.py(TestCommitAssetHython) |

### ✅ 里程碑1 实测已完成（2026-06-26）

**capability-before-rules 纪律的第一道检验通过**。M1 的三个纯 Python 模块此前**零单元测试**，本次补全后：

- **5 个新测试文件，162 个测试全绿**（exprs 80 + skeleton_resolver 21 + asset_model 41 + tool_executor_asset 15 + asset_hython 5）。
- **hython 真机端到端 5 项全绿**（Houdini 21.0.440 子进程里 `import hou` 成功 + `validate_asset(resolve=true)` 返回 5 点骨架 + bb_center 物理正确）。无 hython 的环境自动 skip。
- **实测暴露并修复 2 个真实 bug**：
  1. `exprs.py`：`round(x, 2)` 报错——`_eval_node` 把整数字面量 `2` 强制 `float()` 化，Python 内置 `round` 的 `ndigits` 拒绝 float。修复：字面量保留原生类型（int 保 int），仅 `evaluate` 顶层和算术结果转 float。
  2. `asset_model.py`：`_validate_skeleton_graph` 在 params 是非 dict 时崩溃（`set(params.keys())`）。根因：validate_asset 的 graph 跳过条件只检查 skeleton 结构错误，漏了 PARAMS_NOT_OBJECT。修复：把 params 结构错误码也加入跳过条件。
- **样例数学修正**：`bicycle.asset.json` 的 `bb_center.expr[0]` 从物理不准的 `'rear_x + chainstay_len'` 改为正确的水平投影 `'rear_x - sqrt(chainstay_len**2 - bb_drop**2)'`（BB 在后轴前方）。
- **全量回归 475 passed**（比改动前 +162），零回归。

### ✅ 里程碑2 完整交付（2026-06-27）

**capability-before-rules 纪律的核心检验通过**。M2 让 `components[]` 真正生成几何，经过 4 个递进的实施轮次（native_chain → python → 多实例 → from-to），每一轮都用真机实测验证：

- **2 个 backend**：`native_chain`（声明式 SOP 节点链，从 git history 移植助手 + 8 个 H21 workaround）+ `python`（Python SOP 画曲线，**值注入**参数——agent 用参数名，builder AST 安全替换数值，永不碰 hou.ch）。**故意不做 vex_skeleton**（VEX 是旧管道失败根因）。
- **3 种 placement**：`attach.position`（单实例）/ `instances[]`（1 定义 + N 实例 transform 复制，替代旧 CTP stamping）/ **`from`/`to` 两点连接**（管材/桁架核心原语）。
- **orient 旋转**（attach/instance 的 Euler 度）。
- **实战测试暴露并修复 3 个真实缺陷**（M3 抓不到，递进式发现）：
  1. 组件无朝向（椅子靠背暴露）→ 加 orient 旋转。
  2. orient 被静默忽略 → 加 COMPONENT_BAD_ORIENT 校验。
  3. **无两点连接原语**（自行车车架暴露——agent 要算斜管角度极易错）→ 加 from-to（builder 自动算中点/长度/朝向，用 axis-angle→四元数→欧拉无万向锁）。
- **真机实测**（Houdini 21.0.440）：table（168 点）/ chair（112 点，倾斜靠背）/ **bicycle（224 点：4 from-to 管材 + 2 python 轮子，零 cook 错误，上管长度自动=两点距离 0.5612）**。
- **skill 沉淀**：`skills/asset-authoring/SKILL.md`，基于实战验证的约定（不是空想规则）。
- **全量回归 581 passed**（比 M1 后 +106），零回归。

**核心教训**：实战测试（写真实复杂资产）比设计验证（M3 盒子占位）更能暴露缺陷——椅子暴露 orient 缺失，自行车暴露 from-to 缺失，都是"用的时候才发现缺"的能力。

### 🔴 当前最高优先级：M4 组装提交 + 真实 agent 端到端

M2 已完整交付并通过真机验证（自行车 224 点）。**M3 经分析暂缓**（历史失败无一是骨架点摆位错；resolve_skeleton 预览已能发现几何错；约束断言会扼杀创造力——详见 M2 实战测试的递进发现）。

下一步两条并行线：
1. **✅ M4 组装提交已交付（标记+绕过策略）**：`build_asset` 打 `edini_asset_source` 印记 → `commit_sandbox` 识别后绕过旧 G3a bake/G3b PCA 门禁，保留 G3c 健康+结构门禁，receipt 标 `method:"declarative"`。**待真机 hython 实测**（本机仅装 Houdini Server 无 hython，TestCommitAssetHython 已注册但优雅 skip；需在带完整 Houdini 的机器跑 `pytest tests/test_asset_hython.py::TestCommitAssetHython`）。
2. **真实 Pi agent 端到端**：让真正的 Pi agent 用 `asset-authoring` skill + `build_asset` + `commit_sandbox` 写一个它没见过的资产（不是手写测试资产），验证它能否理解 params/skeleton/components 模型 + 完整走通 build→commit。这是 capability-before-rules 的最终检验——发现 agent 实际使用的真实缺陷。M4 让这条线现在可达（之前 build_asset 出来的 sandbox 无法 commit，端到端断了）。

### 关键设计文档 & 前身代码

- **完整设计**：`docs/edini/specs/2026-06-20-pipeline-architecture-design.md`（三阶段管道，
  资产管道是其演进；§6.3 锚点活通道引用 = 骨架点的前身概念）
- **被禁用的前身（可复用）**：`_disabled_backup/procedural-modeling/python/edini/`
  - `exprs.py` ✅ 已搬回（M1）
  - `recipe_validator.py` — A1-A9 验证 + A6 DAG 循环检测（Kahn），M2 可参考
  - `component_registry.py` — 组件注册 + `{"component":"wheel"}` 引用展开，M2 直接复用设计
  - `components/{tube,wheel,spoke,hub,chain_link,bolt}.json` — 6 个组件样板，M2 的起点
- **资产样例**：`python3.11libs/edini/data/bicycle.asset.json`（M1 测试基础）
- **禁用说明**：`python3.11libs/edini/tool_executor.py` 顶部 NOTE 注释（说明哪些复活了哪些不复活）

### Recipe Library + Dashboard HDA（次主线，可与资产管道并行）

Recipe Library 已完成「参考样本」定位转向，Dashboard HDA 的捕获按钮已上线，Qt 树面板待做：

| 阶段 | 任务 | 说明 | 状态 |
|------|------|------|------|
| **核心** | Recipe Library 5 工具 + python_script | recipe_list/read/capture/capture_tree/rebuild + python_script 参考样本生成 | ✅ 完成（94 测试） |
| **降噪** | manifest 匹配修复 | 版本名优先 + 字符串归一化 + vector/ramp/folder 匹配，changed_params -86% | ✅ 完成 |
| **2026-06-26 增强** | manifest 精度大修 + recipe 孤儿清理 + 中英检索 | 向量真实分量名（temp 节点读取）+ multiparm 记录 + 版本别名 + capture_tree 全局清孤儿 + recipe_list 分词+中英同义词 | ✅ 完成（提交 025ca86） |
| **捕获** | HDA 一键按钮 | Capture All Recipes 按钮（setTags API），reload 后真实验证通过 | ✅ 完成 |
| **开关** | Skill on/off | Settings → Pi Capabilities 复选框，可 A/B 测试 recipe-library | ✅ 完成 |
| **对齐** | 四链路 message 注入 | system prompt/工具描述/SKILL.md/index 统一「参考样本」方向 | ✅ 完成 |
| **1** | scan_tree + create_recipe_manager | 递归读 HDA 内部 subnet 树 + 一键建主 HDA | ⬜ 待做（需真实 Houdini） |
| **2** | Qt 树面板骨架 | recipe_tree_window.py（QTreeView 显示 HDA 内部结构） | ⬜ 待做 |
| **3** | edini 消费 recipe 实测 | 观察真任务里 edini 是否走 list→read python_script→自建 | ⬜ 待真实验证 |

**关键阻塞**：阶段 1-2 依赖真实 Houdini 的 HDA/Qt 行为验证。设计文档
`docs/edini/recipe-manager-hda-design.md`，操作手册 `docs/edini/recipe-capture-workflow.md`。

### 其它规划

| 优先级 | 任务 | 说明 |
|------|------|------|
| **P0** | **Normal SOP 参数适配（C 站前置）** | 第三十阶段遗留：自行车 build 报 `postprocess[0] 'normal' parm 'cangle': Parm 'cangle' not found`。Normal SOP 在 H21 的法线/cusp 参数名变更，导致法线 postprocess 静默用默认值（影响着色但不挡门禁）。需查 H21 Normal SOP 正确参数名，更新 harness postprocess 参数映射 + SKILL.md 速查表。与 C 站（节点参数 DB）同源，可作为 C 站的最小验证用例。 |
| **P1** | **Skill 使用效果追踪** | 基于 LogParser 参数数据，追踪 procedural-modeling Skill 对 VEX/Python 成功率的影响 |
| **P1** | **Copernicus 程序化贴图 Skill** | 在 procedural-modeling Skill 基础上扩展 COPs 专用指导 |
| **P2** | **多 Agent 组件级并行生成** | B 站之后：主 agent 定 recipe + 契约 → N 个子 agent 各产一个组件代码 → 确定性 builder 组装 → 主 agent 验证。先证明单 agent + builder 跑稳再上。 |
| **P2** | **跨 Agent 共享（Hivemind）** | 把 knowledge/skills 推到共享存储（Git repo / S3） |
| P2 | Judge模型优化 | 接入 Anthropic Claude 做 Judge、V4 Pro reasoning_tokens 兼容 |
| P3 | 效率基线优化 | 基于任务类型百分位计算效率评分 |
| P3 | Python 面板 | 支持嵌入 Houdini Pane Tab |

## 已实现功能清单

- ✅ 自然语言创建节点 ("Create a smoke simulation")
- ✅ 参数控制 ("Set the grid size to 0.1")
- ✅ VEX 脚本执行 ("Write a VEX expression to scatter points")
- ✅ Python 脚本执行 ("Run a Python script to...")
- ✅ 场景检查 ("What's connected to this node?")
- ✅ HDA 创建 ("Package this network as a digital asset")
- ✅ 节点搜索 ("Find the Pyro solver node type")
- ✅ 节点帮助文档查询
- ✅ 几何体检查 (点/面/属性/包围盒)
- ✅ 流式响应 (打字机效果)
- ✅ 流式思考展示（独立 Thinking 面板、纯文本自然分段、实时流 ▊ 光标、自动滚底）
- ✅ 工具调用实时面板（fixedHeight 折叠 20px↔200px、执行状态 ✅/❌、结果预览、自动滚底）
- ✅ JavaScript-Free 文本选择（QLabel TextSelectableByMouse）
- ✅ 会话管理 (pi 接管：Popen cwd 按 HIP 归档 · JSONL 本地读取 · new/switch/set_name RPC)
- ✅ Viewport 截图（Houdini 20 flipbook 单帧 + frameRange([1.0,1.0]) 修复）
- ✅ 全渠道图片输入（截图 / 拖拽 / Ctrl+V / 右键粘贴 / 文件选择，原始文件名保留）
- ✅ 图片附件预览栏（真实缩略图 120×68，最多 5 张）
- ✅ 视觉描述气泡（可折叠，显示 Qwen-VL 分析结果，📸 查看原图 (N) 多图支持）
- ✅ 识别中状态提示（🔍 正在识别图片… 虚线框，通知到达自动替换）
- ✅ 视觉管道修复（fetch→https.request 绕过 undici 死锁，ctx.ui.notify 通知修复）
- ✅ 时间线缩略图卡片（96×68 缩略图 + 文件名 + 来源图标，点击在 OS 查看器中打开原图）
- ✅ 图片缓存持久化（edini_images/ 目录，按 session 隔离，切换历史对话可回看图片）
- ✅ 视觉描述缓存（descriptions.json，历史对话中自动渲染 VisionDescriptionBubble）
- ✅ Defer 缓存写入（session 路径异步就绪后自动刷入，解决端到端时序问题）
- ✅ API Key / Provider / Model 设置 (pi CLI 风格 Login/Logout + 35 供应商自动同步 + Vision Model 独立配置)
- ✅ 4 色主题实时预览 + 字体缩放
- ✅ 执行/中止按钮一体化切换
- ✅ 智能滚动（rangeChanged + valueChanged + _pinned_to_bottom 标志位，零抖动）
- ✅ 状态栏 (连接状态 / 模型 / 节点数)
- ✅ 多行输入 (Ctrl+Enter 换行，Enter 发送)
- ✅ 会话浏览模式（历史回看 + 回到当前）
- ✅ 对话轮次计时器（Pi Status 卡片实时显示 Round 时间）
- ✅ Pi Status 工具信息（Tools: 22 loaded, port 9876）
- ✅ 知识沉淀两层架构：铁律 (≤20, 上下文注入) + 知识库 (细节, 可检索)
- ✅ AI 反思 → 用户确认面板（✓✕ + 全部接受/放弃 + 类型切换）
- ✅ Settings Knowledge 标签页（开关 + 统计 + 管理按钮）
- ✅ 变更树 QTreeWidget 面板（按轮次分组：创建/修改/删除三级树，可折叠，对话结束自动展开）
- ✅ 4 层统一字号体系（header 13pt / body 12pt / detail 11pt / caption 10pt）
- ✅ 全局 fs() 缩放（历史面板、代码块等之前硬编码 pt 的元素全部改用 fs()）
- ✅ 消除 fs(9) 极小字号（全部提升至 fs(10)）
- ✅ 面板固定高度 + 徽章固定宽度与字号适配
- ✅ Markdown 双格式化器（_format_full 完整解析 + _format_lite 流式安全）
- ✅ 标题 #/##/### + 有序/无序列表 + 表格 + 代码块 + 分隔线 + 段落 p 分隔
- ✅ header+body 组合（### 标题下跟随表格/列表）
- ✅ 历史气泡合并（连续 assistant entry 合并为单个大气泡）
- ✅ 知识提取过滤（隐藏提取对话轮次）
- ✅ 文本选择（TextSelectableByMouse，所有气泡）
- ✅ pi-visionizer 视觉代理扩展（图片透明路由到 Qwen-VL Max，纯文本模型"看懂"截图）
- ✅ pi-visionizer 默认视觉模型改为 aliyun/qwen-vl-max
- ✅ pi-visionizer 写入 vision-description custom entry + 实时通知 Edini
- ✅ VisionDescriptionBubble 时间线内渲染（可折叠、查看原图、错误变体）
- ✅ 剪贴板多模式探测（QImage → mimeData.imageData → URLs → raw png/jpeg）
- ✅ 右键上下文菜单（图片剪贴板→粘贴图片到附件栏 + 粘贴文本，无图片→原生菜单）
- ✅ 📷 截图 + 📁 上传按钮布局优化（文本标签、hover/pressed 动效、不再被裁切）
- ✅ 视窗截图 Houdini 20 API 适配（saveImage/grabFrameBuffer 移除→flipbook 修复）
- ✅ QImage.save() PySide6 兼容（BytesIO/QBuffer 失败→tempfile 中转）
- ✅ PySide6 枚举兼容修复（Qt.Clipboard 等不存在→整数 mode 值 0/1/2）
- ✅ SnapshotEngine 场景快照 Diff（snapshot / diff / 三阶段节点级 restore）
- ✅ Undo/Redo 栈（每轮一个事务，撤销=整轮回滚重建，手动修改自动清空栈）
- ✅ 节点视图跳转（点击变更树路径 → hou.node.setCurrent + frame viewport）
- ✅ 节点创建 namespace 自动解析（裸名如 copytopoints → namespaceOrder → copytopoints::2.0）
- ✅ Shelf tool 预设自动应用（创建后匹配 tool 脚本，执行 pressButton/set）
- ✅ 变更树参数紧凑显示（≤2 参数全显，3+ 折叠摘要）
- ✅ diff 自动过滤 Houdini 内部生成的子节点
- ✅ procedural-modeling Skill（程序化建模指导：语言选择策略、VEX run-over class、分而治之、模板模式、失败切换、Copernicus 流程）
- ✅ Skill 目录自动发现（--no-skills + --skill 逐目录加载，支持 SKILL.md 子目录和根级 .md）
- ✅ LogParser toolCall 参数提取（两阶段匹配：assistant toolCall.arguments → toolResult 回填，98% 参数覆盖率）
- ✅ Procedural Harness：live sandbox（`houdini_run_python_sandbox`）→ diagnostics → structural verify → safe capture → commit/discard 全流程护栏
- ✅ 模块化结构硬门（`_check_modular_structure`）：commit_sandbox 拒绝单体资产，强制 Copy-to-Points/Sweep/foreach 分解
- ✅ 朝向门（`houdini_verify_orientation`）：PCA 按组件检测轮轴/长轴/法线方向，failed check 带 hint 四元数，commit 时硬关卡
- ✅ 三层验证协议：geometry health → orientation → inventory/data → visual（health 是 MANDATORY layer-1）
- ✅ geometry_inventory / inspect_geometry_health / capture_component_detail 三个验证工具（组件清单 / 几何健康 / 小组件特写）
- ✅ network_mode sandbox（`run_python_sandbox(network_mode=True)`）：代码跑在 geo 容器，可直接 createNode 子 SOP 建多节点网络
- ✅ 声明式 Recipe Builder（`houdini_build_procedural_asset`）：agent 提交 recipe，harness 确定性建网，agent 永不写 createNode/wiring/blockpath
- ✅ 构造轴（B 站，`orientation_asserts.construction_axis`）：声明组件局部构造轴 → builder 用 anchor @orient 四元数代数推导世界轴 → 烘焙 `edini_world_axis` prim 属性 → verify 直接读跳过 PCA（method=construction）。build 时一致性预检拒绝 construction_axis/expected_axis/anchor 矛盾（挡自洽错误）。无该字段老 recipe 仍走 PCA。PCA crosscheck 仅告警。
- ✅ Forbidden Patterns + Network Mode + H21 参数速查表（SKILL.md：Attrib Promote / Blast / ForEach / Sweep / Copy-to-Points 等关键参数）
- ✅ **spare 参数挂载修复**（`_install_spare_params`）：read-merge 文件夹参数模式（`parmTemplateGroup()` 读现有 + `FolderParmTemplate` 装 + `setParmTemplateGroup` 写回），H21 兼容、merge-safe；setSpareParmGroup 受限时自动回退；真实 Houdini 验证 5/5 参数 `installed=true` 并落到 `/obj/bicycle` 参数面板
- ✅ **degenerate 误报修复**（`inspect_geometry_health`）：改用 `prim.intrinsicValue("measuredarea")` 真实多边形面积（含 n-gon），异常回退修正 shoelace（全顶点扇形求和）；消除 `0.5·|cross|²`(=2·area²) 单位错误 + "只看前 3 顶点"采样偏差；fan-cap/n-gon cap 不再误报
- ✅ **mock_hou 参数模板模拟**：`MockFloatParmTemplate`/`MockFolderParmTemplate`/`MockParmTemplateGroup` + `MockNode.parmTemplateGroup()`/`setParmTemplateGroup()`/`evalParm()` + subnet 注册，成功安装路径可测
- ✅ **真实 Houdini 验证脚本**（`tests/manual_verify_fixes.py`）：pre-flight 组件代码 isolation cook 抓真实 traceback + 双修复端到端断言（参数挂载 + degenerate 不误报），13/13 全过

---

## 2026-07-02 组件建模地基（子系统 1）交付

**范式重构**：Project HDA 建模能力从 rooted 扁平网络（root+mount+leaf+CTP）重构为**组件流水线范式**。这是 4 子系统全栈设计的**地基**（子系统 1）。

### 核心架构（用户拍板，第一性原理）

- **subnet = 组件间信息总线**：一个组件 = core 内一个 subnet，多输出端口对外暴露。`out[0]`=主几何，`out[1..n]`=**信息点云**（带 `@P`/`@orient`/`@name` 的 point）。组件流水线协作：车架输出 wheel_mount 锚点 → 车轮消费定位 → 车轮再输出锚点供辐条。LLM 自由决定组件粒度。
- **新范式取代旧范式**：mount/leaf 扁平网络被组件流水线取代，旧 `assembly` 字段整套移除。
- **声明 = 知识图谱**：`components`（含 `ports`/`params`）即组件关系图，drift = diff 意图 vs 实际网络（子系统 4）。
- **Builder = 脚手架（确定性），几何 = LLM 自由活**：builder 只建空 subnet+4节点+连线，几何和跨 subnet 连线归 LLM。
- **promote 脚本**：组件 subnet spare parm 一键按组件分组提取到 core HDA，两层 ch() live 引用。

### 交付内容（8 任务，分支 feat/project-component-foundation）

| 模块 | 内容 |
|---|---|
| `state.py` | 新 components schema（add_component/get_component，组件 id=subnet 名校验）+ 删 assembly |
| `ports.py` | 端口协议常量（4 节点名）+ validate_component_ports 校验 |
| `builder.py` | build_project_scaffold（脚手架）+ promote_params（参数提取），重写取代旧 build_project_model |
| `tool_executor.py` | project_build_scaffold + project_promote_params handler |
| `project.ts` | project_build_scaffold 工具（components 参数，删 assembly） |
| 测试 | state 26 + ports 8（mock）+ project_hython 5（hython 决定性）|

### 真实 API 发现（hython 决定性验证的价值，mock 测不出）

1. **subnet output 节点机制**：subnet 内建 `output` 节点（`createNode("output")`），两个 output 节点按 `outputidx` 形成两个独立 subnet 输出端。decisive proof：两个端口放不同 marker 几何，下游消费者各取所需，确认端口独立且有序。**spec §12 最高风险点验证通过，plan 的猜测完全正确。**
2. **spare parm 真实 API（纠正旧记录）**：READ 用 `node.spareParms()`（`list[hou.Parm]`），WRITE 用 `node.addSpareParmTuple(tmpl, in_folder=(folder,), create_missing_folders=True)`。**`spareParmGroup()`/`setSpareParmGroup()` 在真机不存在**（mock_hou 支持但真机没有，mock 误导了之前的实现——上方"spare 参数挂载修复"记录里 `setParmTemplateGroup`/`setSpareParmGroup` 的描述对真机不准确，以此 hython 验证为准）。

### hython 决定性验证（5 测全过）

- 脚手架结构：2 组件 subnet，各有 4 节点（out_geometry/out_anchors/output_0/output_1）
- 锚点发射：LLM 加的锚点从 output_1 cook 出，带 @name
- 幂等：重跑 builder 不重复建节点
- promote：chassis_length 创建，表达式含 chassis/length
- 全链路：scaffold→锚点→promote→重建，重建不破坏 LLM 已加内容

### 全量回归

672 passed（含新 39 测：state 26 + ports 8 + project_hython 5）。5 failed 均为 PySide6 import（test_error_surfacing.py，预存环境问题，与本次改动无关）。rooted-modeling 的 26 hython 测全过（旧能力零回归）。

### 下一步（后续 spec，地基已稳）

- **子系统 2**：多组件流水线 agent 端到端（LLM network_mode sandbox 在 subnet 内建模 + 跨 subnet 连线）
- **子系统 3**：知识图谱描述生成（components/ports → 给 LLM 的"组件联系"自然语言）
- **子系统 4**：drift 检测算法（声明意图 vs 实际网络确定性 diff，schema 已预埋接口）
- **LLM 建模纪律 skill**：VEX 优先/禁纯 Python 单 SOP/native node 兜底（capability 验证后沉淀）

**设计文档**：`docs/superpowers/specs/2026-07-02-project-component-foundation-design.md` + `docs/superpowers/plans/2026-07-02-project-component-foundation.md`。

---

## 2026-07-07 程序化建模 skill 第一性原理重构

**动机**：对照 [mattpocock/skills - writing-great-skills](https://github.com/mattpocock/skills/blob/main/skills/productivity/writing-great-skills/SKILL.md) 框架审视我们的 `project-modeling/SKILL.md`。该框架的核心论点是 **"一个 skill 存在的根本理由是 wrangle determinism —— 对抗 LLM 在特定领域会犯的几类错误"**。我们的 skill 已经内化了这个对抗（Guardrails、guards.py 平台层），但从未在结构上把它表达清楚。

### 7 个维度的诊断 → 优化

| mattpocock 维度 | 旧 skill 问题 | 优化措施 |
|---|---|---|
| **第一性原理 / 开头** | 开头是描述性的（"A procedural model is built as a Project HDA…"），不是目的性的 | 新增"Why this skill exists"——列出 agent 默认会犯的 4 类错误（硬编码坐标/漏依赖/单SOP堆积/premature completion），让 guardrails 变成"对失败倾向的条件反射" |
| **Leading Words** | 同一概念用多个 synonym（hardcode/hand-rolling/hand-rolled/DERIVED FROM GEOMETRY），破坏锚定 | 确立 3 个 leading words：`measure`/`anchor`/`scaffold`，贯穿 **skill + guards.py 报错 + 工具 description + 系统 prompt**（全链路双层强化——这是 mattpocock 纯 prompt 理论之外的、我们项目独有的机会） |
| **Information Hierarchy** | 316 行全在一个文件（sprawl），agent 每次要在其中找当下需要的那段 | progressive disclosure 拆分为 4 文件：主文件（intro+guardrails+workflow+leading words）+ MISTAKES.md / DISCIPLINE.md / PORT_PROTOCOL.md（按需读取） |
| **Completion Criterion** | 4 个 workflow step **一个都没有** done 标准 → premature completion 风险 | 每步加 ✅ Done when（checkable + demanding）。Step 3 最严格：要求每个组件 out 有几何 + 每个声明的 anchor 已发射 + verify_orientation 通过 |
| **Description 精简** | 180 词，含 how-to 泄漏 + duplication（"DEFAULT path" 与正文"ONLY path"重复）| 精简到 ~50 词，只留 triggers + leading words |
| **Duplication** | ports.in 规则在 4 处重复（Guardrails / ASCII 图 / workflow ⚠️ 框 / mistakes 表）| 收拢到 Guardrails 单一权威位置，其他用 leading word 指回 |
| **No-Op 检查** | 未做 | DISCIPLINE.md 标注每条规则对抗的真实失败倾向 |

### 改动范围（全链路）

| 层 | 文件 | 改动 |
|---|---|---|
| Skill 主文件 | `skills/project-modeling/SKILL.md` | 重构（316→230 行）|
| Skill 子文件（新增）| `MISTAKES.md` / `DISCIPLINE.md` / `PORT_PROTOCOL.md` | 从主文件拆出 |
| 中文版 | `SKILL.zh.html` | 重生成同步新结构 |
| 平台层 guard | `python3.11libs/edini/project/guards.py` | 报错用统一 `measure` leading word（保留 `_BYPASS_MARKER`/`_FORBIDDEN_TOKEN`/`"Refused:"` 不变）|
| 工具描述 | `pi-extensions/edini-tools/tools/project.ts` | 4 个工具 description + promptGuidelines 统一 leading words |
| 系统 prompt | `pi-extensions/edini-context/index.ts` | 路由文案补 leading words |
| brainstorming | `skills/superpowers/brainstorming/SKILL.md` | fast-path 契约同步阶段名 |
| **验证测试（新增）**| `tests/test_skill_workflow_hython.py` | 5 测，真机 hython 端到端验证每个 completion criterion |

### hython 端到端验证（5/5 通过）

新增的 `test_skill_workflow_hython.py` 用真机 hython 完整执行新 skill 的 4 步工作流，逐个检查 completion criterion：

| Criterion | 实测 |
|---|---|
| Step 1: core_path 返回且有效 | ✅ |
| Step 2: 每个组件有 subnet + 每个 ports.in 有 in_<from>_<anchor> + design_params 成为 core spare parm | ✅ |
| Step 3a: out_geometry 有几何流入 | ✅ |
| Step 3b: 每个声明的 anchor 已通过 measure 发射（@name 齐全）| ✅ |
| **Step 3c: anchors 是 LIVE 的**——改 length 1.2→2.4，leg_fr 锚点 X 坐标真的跟着移动 | ✅ **核心铁证** |
| Step 4: promote 创建 tabletop_thick core parm + subnet 用 ch("../tabletop_thick") 引用 + 改 core 值后 subnet eval 立即同步 | ✅ |

**最有价值的是 Step 3c**：它把 "measure, don't hardcode" 这条 skill 规则变成了**可量化验证的物理事实**。如果有人手写 `addpoint`，这个测试会失败。

### 同步修复的测试基建两个潜伏 bug

这次 skill 优化过程中，因为装上 PySide6 让之前一直收集失败的 chat 测试终于能跑，暴露出两个一直潜伏的 bug（详见 [踩坑记录](pitfalls.md)）：

1. **测试污染**：6 个测试文件用 `for _m: if _m.startswith("edini"): del sys.modules[_m]` 全局清空，破坏了 UI/chat 模块的类身份稳定性（重新执行产生新类对象，`isinstance`/`findChildren` 失败）。修复：`conftest.py` 加 `reload_edini_modules(*names)` helper，只清指定模块。
2. **hython flaky**：Python 3.14 + Windows subprocess 的 WinError 6 句柄竞争（18 个 hython 测试随机失败）。修复：8 处 `subprocess.run` 加 `stdin=subprocess.DEVNULL`。

### 全量回归

**901 passed**（原 896 + 新 5 skill 工作流测试），连跑稳定。

### 验证边界（诚实说明）

**已验证**：新 skill 的每条规则、每个 completion criterion 都不是空话——它们在真机 hython 下可执行、可检查。旧 skill 没有任何 criterion，谈不上可验证。

**待验证**（需 Pi 实测）：agent 读了新 skill 后，是否真的更少犯错、更少轮次完成建模。这个只能靠启动一个 Pi session 让它建模型来对比——不是 ZCode 能做的 A/B 测试。

### 设计参考

- [mattpocock/skills - writing-great-skills/SKILL.md](https://github.com/mattpocock/skills/blob/main/skills/productivity/writing-great-skills/SKILL.md) + [GLOSSARY.md](https://github.com/mattpocock/skills/blob/main/skills/productivity/writing-great-skills/GLOSSARY.md)
- 核心论点：*"A skill exists to wrangle determinism out of a stochastic system."*

## 2026-07-08（下午）重构后实测硬化（archetype-fixes + 并发）

9-Phase 重构合并 master 后，跑 5 个真实 Pi 会话（2 桌 + 2 键盘 + 1 复测）端到端实测。
**判定：手搓节点路径零故障；archetype/grid 路径 + 并发层有硬化缺口** —— 4/4 模型最终
都成功，但 archetype 路径每次都要 agent 手动补丁，把"省事"做成了"更脆"。分支
`refactor/archetype-fixes`（3 commit，**808 测试全绿**）逐条修掉。

### 实测发现 → 修复（同一根因：tool 执行同步跑 hou 图变更，与 UI 抢主线程；客户端有超时无流控）

| 问题 | 根因（行号） | 修法 |
|---|---|---|
| **P0-1** 多点锚点只命名第一个点 | `builder.py:759/897` `setpointattrib(__newpts[0])` —— grid_on_face/pickets/cells/shelf 发 N 点只命名 [0]，端口 `@name` 过滤后下游只剩 1/N（键盘 75 键→1） | `foreach (int __pt; __newpts) setpointattrib(...)` 全部命名。单点策略 N=1 不受影响 |
| **P0-2** copy_array leaf 参数静默丢失 | `_set_archetype_parm:975` 遇未知 parm `if p is None: return` 静默吞；box 无 "size" parm（只有 sizex/y/z），`leaf.size=[...]` 丢光，且不处理 list 值；emit_component 仍报 `success:true` | 重写为委托 `_apply_one_param`（手搓 set_param/set_params_batch 同款 dispatch）：向量→parmTuple / 表达式→setExpression / 未知报错。失败 raise → 清晰 `{success:False}` |
| **并发 A** 开面板卡顿 | `agent_panel.append_stream_chunk` 每 token 调 `update_streaming(full_text)` → `QLabel.setText(整段增长文本)` → Qt 每 token 重排整段；与 agent 图变更抢主线程。**节流设施早就在但 `_flush_stream` 是 no-op 死代码** | 重激活既有 `_stream_flush_timer`：append 只 buffer + 起单次定时器；`_flush_stream` 真正渲染（~12/秒）。`finish_streaming` 补 flush 防尾部丢失。删死常量 `STREAM_FLUSH_CHARS` |
| **并发 B** `ConnectionAbortedError` 级联 | 客户端 30s 超时关 socket，server 写响应撞关闭连接 → 双重失败 traceback（`do_POST` except 捕获第一次失败 → 又写错误响应 → 又失败 → 未捕获） | `_write_response` 统一发送，吞 `BrokenPipe/ConnectionAborted/ConnectionReset`。客户端已重试，无可送达 |

### 实测铁证（hython H21 + UI 单元测）

- **P0-1 复测**（真实 Pi 会话 `08-50`）：grid_on_face 75 点全部到达 keys → 直接 450 面（75 键），agent **零手补命名**（前两轮键盘各手补 1 次）。
- **+4 hython 测**：`TestCopyArrayVectorLeafHython`（leaf `size=[leg_thick,leg_h,leg_thick]` → sizex/sizez eval 0.08、sizey 0.7、且是 live 表达式；未知 parm 大声失败）；`TestGridMultiPointNamingHython`（grid 12 点全命名 + 全达下游 consumer）。
- **+3 UI 测**：`test_agent_panel_stream_throttle`（chunks 不 eager render / `_flush_stream` 渲染 / `finish_streaming` 不丢尾部）。
- 此前测试矩阵的盲区：只测单点锚点策略（bbox_corner），多点策略（grid/pickets/cells/shelf）零覆盖 → P0-1 漏网。

### 暂缓（按"最稳定可控 + 架构干净"准绳）

- **P1-P3 archetype 项**：leaf.type=box_panel 解析 / 锚点守卫误拦测量 addpoint / verify_parametric 阵列尺寸阈值（key_size 改大整体 bbox 稀释 <5% 假失败）/ grid rows/cols 构建时不可传 ch()（注：post-build 用 ch() 设 spare parm 可让键数量 live，复测已证 cols 15→10 键 75→50）/ copy_array 贴面偏移（leaf 中心盖印，每次要手加 xform）。
- **图侧 manual-update**：改 Houdini 全局更新模式（恢复失败 → 整 session 视口不更新），不够稳定可控，且收益未经实测。届时用 **scoped context manager 带保证恢复**，非裸全局开关。
