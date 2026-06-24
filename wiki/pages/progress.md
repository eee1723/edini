# 🚀 开发进度

> 最后更新：2026-06-24 &nbsp;|&nbsp; **架构转向：关闭程序化建模 → Recipe Library（recipe_rebuild 真实验证通过）+ 旧死代码清理完成** 🚧 &nbsp;|&nbsp; 进展：35 测试全绿，harness.py 4644→1810 行

## ⚠️ 架构转向说明（2026-06-23）

**重要**：旧的程序化建模管道（提示词驱动 + validate_recipe/build_procedural_asset/G1-G3 闸门）
已**完全关闭并备份**到 `_disabled_backup/procedural-modeling/`。根因：LLM 对 Houdini 不熟，
靠提示词规则无论写多细还是会出错——这是概率模型的本质缺陷。

**新方向 = Recipe Library**：把人类 TD 搭好的 subnet（含正确参数+连线+Notes）沉淀成可被 LLM
读取、理解、按需重建的配方库。LLM 从「凭空发明节点」降级为「选择并调参」，用人类确定性覆盖
LLM 不确定性。设计文档见 `docs/edini/recipe-manager-hda-design.md`。

下方旧的「程序化建模」阶段卡片保留作为历史记录，但**已不再是当前架构**。

## 总览看板

<div class="phase-grid">

<div class="phase-card">
  <div class="phase-card-header">
    <span class="phase-card-title">📚 Recipe Library（新架构 · schema v2）</span>
    <span class="status-tag status-done">核心完成 + 真实验证</span>
  </div>
  <div class="progress-bar-bg"><div class="progress-bar-fill progress-done" style="width:95%"></div></div>
  <div class="phase-card-detail">替代旧程序化建模管道。<strong>5 工具</strong>（recipe_list/read/capture/<strong>capture_tree</strong>/rebuild）：捕获 subnet 内部网络→配方 JSON（区分 changed/marked 参数，inputs 用相对名跨场景可重建）→索引→拓扑排序重建+内置验证。<strong>schema v2 新增</strong>：recipe_capture_tree 递归扫整棵分类树自动抓叶子（recipe_id 用树路径防撞名）、kind（network|vex）、vex_snippets（wrangle 代码+runover 可搜）、tree_path 分类面包屑、自动忽略 output/stashed 节点、空 Notes 自动生成。<strong>真实 Houdini 闭环已验证</strong>：用户手搭 6 叶子分类树一次性抓取成功，发现并修复 popnet 网络容器穿透 bug。配方库已有 4 个真实配方。30 测试 + 2 subtests 全绿。</div>
</div>

<div class="phase-card">
  <div class="phase-card-header">
    <span class="phase-card-title">🎛️ Dashboard HDA（进行中）</span>
    <span class="status-tag status-active">设计定稿</span>
  </div>
  <div class="progress-bar-bg"><div class="progress-bar-fill" style="width:15%"></div></div>
  <div class="phase-card-detail">edini_recipe_manager 主 HDA：内部递归 subnet 树（结构即分类）+ 自写 Qt QTreeView 仪表盘（检查/重建/编辑按钮）+ PythonModule 调 recipe_library。不锁定内容，内部透明可读。可扩展新方向（fx/materials）。设计定稿，待真实 Houdini 验证 scan_tree/create_recipe_manager。</div>
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

### Recipe Library + Dashboard HDA（当前主线）

旧的程序化建模 ABCDE 五站计划已随管道关闭而**废弃**（代码备份在 `_disabled_backup/`）。
新主线是 Recipe Library 配套的 Dashboard HDA，6 阶段推进：

| 阶段 | 任务 | 说明 | 状态 |
|------|------|------|------|
| **核心** | Recipe Library 4 工具 | recipe_list/read/capture/rebuild，配方 JSON schema，拓扑排序重建，内置验证 | ✅ 完成（285 测试） |
| **1** | scan_tree + create_recipe_manager | 递归读 HDA 内部 subnet 树（区分容器/叶子）+ 一键建主 HDA（不锁定） | ⬜ 待做（需真实 Houdini） |
| **2** | recipe_list 递归支持 | LLM 能查 HDA 内部树（不只读 index.json） | ⬜ 待做 |
| **3** | Qt 树面板骨架 | recipe_tree_window.py（QTreeView 显示 HDA 内部结构） | ⬜ 待做 |
| **4** | 按钮接线 | 检查/重建/编辑按钮调 recipe_library | ⬜ 待做 |
| **5** | 右键菜单 + 拖拽 | 新建/移动 subnet，改分类 | ⬜ 待做 |
| **6** | LLM 工具接线 | recipe_manager_create/tree_scan/tree_open 工具 | ⬜ 待做 |

**关键阻塞**：阶段 1-6 依赖真实 Houdini 的 HDA/Qt 行为验证（save_as_locked、subnet category 判定、Qt 浮动面板），mock 无法覆盖。设计文档 `docs/edini/recipe-manager-hda-design.md`，测试指南 `docs/edini/recipe-library-testing.md`。

### 旧程序化建模（已废弃，备份可恢复）

ABCDE 五站（A 声明式 Builder / B 构造轴 / C 参数 DB / D 黄金范例 / E 数值代理）随管道关闭废弃。
A/B/C 已完成的代码备份在 `_disabled_backup/procedural-modeling/`，恢复方式见
`python3.11libs/edini/tool_executor.py` 顶部 NOTE 注释。

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
