# 🧪 Procedural Harness

> 最后更新：2026-06-15 ｜ 状态：模块化门 + 朝向门 + network_mode + 声明式 Builder + 构造轴（B 站）已落地 ｜ 目标：让程序化建模先进入可诊断、可验证、可回滚的沙盒流程，并从"约束执行"转向"能力放大"。

## 这批解决了什么

Procedural Harness 是 Edini 给 Houdini 程序化建模加上的一层执行护栏。它不再让 AI 一上来就用 `houdini_run_python` 在用户的 live scene 里直接试错，而是要求先创建 `/obj/edini_sandbox_*` 沙盒节点，把生成结果、诊断、结构验证和最终提交拆成清晰步骤。

随着日志诊断深入，护栏演进为三条互补路线：

1. **约束执行（gates）**：模块化硬门 + 朝向门 + 三层验证——挡住"做错的"。
2. **能力放大（builder/abstractions）**：network_mode + 声明式 Recipe Builder——让 agent 不需要会命令式 Houdini API 也能产出模块化资产。这是核心转向：gate 加到一定密度后边际收益为负，builder 直接消灭整类错误。
3. **工具补全**：把验证工具（inventory/health/component-detail）真正暴露给 agent。

| 能力 | 内容 | 观察点 |
|------|------|--------|
| Live sandbox | `houdini_run_python_sandbox` 创建唯一 job id 和沙盒根节点 | 新资产应先出现在 `/obj/edini_sandbox_*` 下 |
| network_mode | `network_mode=true` 让代码跑在 geo 容器，可直接 createNode 子 SOP | 多组件资产不再触发 cook 内 createNode 无限递归 |
| **声明式 Builder** | `houdini_build_procedural_asset(recipe)` 确定性建网，agent 只写纯几何代码 | agent 不再写 createNode/wiring/blockpath；recipe 驱动组件+anchor+Copy-to-Points+OUT |
| 模块化硬门 | `_check_modular_structure` 拒绝单体资产（≥3 cid 全来自单个 Python SOP） | commit 前结构门先跑，拒绝单体 |
| 朝向门 | `houdini_verify_orientation` 按 construction_axis 确定性读取 edini_world_axis（无 PCA）；缺该属性时回退 PCA | failed check 带 hint |
| 构造轴（B 站） | `orientation_asserts.construction_axis` 声明组件局部构造轴，builder 用 anchor @orient 代数推导世界轴并烘焙 edini_world_axis；build 时一致性预检拒绝自洽矛盾 | 朝向从估计变 ground truth，build 时挡住自洽错误 |
| 三层验证 | geometry health → orientation → inventory/data → visual | health 是 MANDATORY layer-1 |
| Diagnostics | `houdini_collect_diagnostics` 收集节点错误、警告、参数、几何统计 | 失败后先看诊断，不立即删节点 |
| Inventory | `houdini_geometry_inventory` 列每个 component_id 的 prim 数 + 相对大小 | 确认组件存在，标 SMALL 需特写 |
| Health | `houdini_inspect_geometry_health` 查 orphan/degenerate/non-manifold | Boolean/Sweep 前必修 |
| Component detail | `houdini_capture_component_detail` 小组件逐个框取特写 | 解决"存在但太小看不见" |
| Lifecycle | `houdini_commit_sandbox` / `houdini_discard_sandbox` | 通过后改名提交，废弃显式删除 |
| Safe capture | `houdini_capture_review` 多视角接触表，自动框到 target bbox | 截图失败干净报告 |
| Skill guidance | `procedural-modeling` 含 Forbidden Patterns + Network Mode + Recipe Builder + H21 参数速查 | 生成程序化资产时不应优先 raw run |

## 标准测试流程

1. 让 Agent 创建一个明确的程序化资产，例如 ladder、parametric stair、scatter pattern 或 L-system tree。
2. 观察它是否先调用 `houdini_run_python_sandbox`，并返回 `job_id`、`execution_mode: live_sandbox`、`root_path`。
3. 如果生成失败，观察是否保留失败沙盒，并调用 `houdini_collect_diagnostics` 读取错误、警告、traceback 或几何状态。
4. 如果生成成功，观察是否调用 `houdini_verify_asset`，至少检查非空几何和非零 bounds。
5. 结构检查通过后，再观察是否调用 `houdini_capture_review` 做视觉确认。
6. 用户确认或结果足够明确后，再调用 `houdini_commit_sandbox` 把沙盒改成最终资产名。
7. 不需要的沙盒应通过 `houdini_discard_sandbox` 清理。

## 手测时重点盯什么

### 应该出现的好信号

- 工具调用顺序是 sandbox → diagnostics/verify → safe capture → commit/discard。
- 失败节点没有被立即删除，能在 Houdini 里看到失败现场。
- tool result 里包含 `root_path`、`job_id`、`diagnostics`、`geometry.point_count`、`geometry.prim_count`、`bounds.size`。
- Agent 在切换 Python SOP / VEX / node network 策略前，会先解释诊断结果。
- `houdini_run_python` 的使用变少，只在专家调试或非程序化资产任务里出现。
- 截图失败时返回明确错误和阶段信息，不尝试 `QtWidgets`、viewport internals 或 main window 探测。

### 需要警惕的坏信号

- 一开始就 raw `houdini_run_python`，并直接改 live scene。
- Python SOP 或 VEX cook 失败后，Agent 先删节点或立刻换方案，没有诊断。
- commit 前没有 point/primitive/bounds 结构验证。
- tool result 里出现 JSON serialization error、circular reference、node object repr 崩溃。
- `commit_on_success` 被误理解成自动提交，但实际没有调用 `houdini_commit_sandbox`。
- final node 重名时没有说明 `replace_existing` 策略。
- 截图失败后开始探索 Qt widget、desktop pane internals 或 unsupported HOM API。

## 互动手测清单

可打开这个单文件 HTML 来做手测记录：

[Procedural Harness 手测清单](../../docs/procedural_harness_test_guide.html)

清单包含 19 个测试项，覆盖基础生成、失败诊断、结构验证、生命周期、skill 行为和安全截图。每项有“通过 / 失败 / 未测”状态、备注框、localStorage 保存和报告导出。

## 代码入口

| 区域 | 文件 |
|------|------|
| Harness 实现（sandbox/gates/builder） | `python3.11libs/edini/harness.py` |
| Tool executor 注册 | `python3.11libs/edini/tool_executor.py` |
| 节点/几何工具 | `python3.11libs/edini/node_utils.py` |
| 朝向数学 | `python3.11libs/edini/orientation_math.py` |
| Pi tool schema（harness） | `pi-extensions/edini-tools/tools/harness.ts` |
| Pi tool schema（query/inventory/health） | `pi-extensions/edini-tools/tools/query.ts` |
| Pi tool index | `pi-extensions/edini-tools/index.ts` |
| Skill 指南 | `skills/procedural-modeling/SKILL.md` |
| Builder 实测文档 | `docs/BUILDER_FIRST_TEST.md`、`docs/BUILDER_SECOND_TEST.md` |
| 单测 | `tests/test_procedural_harness.py`、`tests/test_build_procedural_asset.py`、`tests/test_tool_executor_harness.py`、`tests/test_pi_harness_tools.py`、`tests/test_verify_orientation.py` |

## 三条 build 路径（SKILL.md 的统一矩阵）

| 场景 | 工具 | agent 写什么 |
|---|---|---|
| 多组件资产（车/家具/任何有可替换件） | **`houdini_build_procedural_asset`**（声明式 recipe，PREFERRED） | 每组件纯几何代码 + recipe（绝不 createNode） |
| 非标准拓扑（recipe 表达不了的） | `houdini_run_python_sandbox(network_mode=true)` | 手写建网代码（容器内 createNode 合法） |
| 真正的单体生成器（一个分形/一个曲面） | `houdini_run_python_sandbox`（默认 single-SOP） | 单 SOP cook 代码 |

## 当前限制

- sandbox 仍运行在 live Houdini 进程内，不能提供 OS 级 crash isolation。
- `commit_on_success` 当前只记录请求状态，不自动 commit；正式提交仍应显式调用 `houdini_commit_sandbox`。
- 朝向门对**声明了 construction_axis 的组件**是确定性检查（读 edini_world_axis，零估计）。对未声明该字段的组件回退 PCA——PCA 是点分布估计，对不均匀分布不稳；新资产建议优先用 construction_axis（B 站）。
- builder 的 idfix 用 prim 等分定位实例边界——已验证 Copy-to-Points 连续排列下成立，但极端拓扑（交错排列）理论上可能错位。
- builder 不内嵌 capture/commit（单一职责；commit 是显式后续调用）。

## 验证状态

最近 A/B 站交付后的验证结果：

```text
python -m pytest（harness 子集，忽略 manual_* 与 PySide6 依赖测试）
197 passed（A 站 177 + B 站新增 20）

B 站 mock 验证：
- 纯数学 rotate_vector_by_quaternion：identity/90°/180°/长度保持 6 用例
- build 一致性预检：构造轴/expected_axis 矛盾时拒绝且不泄漏 sandbox
- build 烘焙：direct/stamped 组件 construction_axis 一致时构造 construction_axis_summary
- verify_orientation 构造路径：edini_world_axis 覆盖 PCA（method=construction）
- PCA crosscheck：构造轴与 PCA 估计分歧时只告警不 fail
- 向后兼容：无 construction_axis 的老 recipe 仍走 PCA

真实 Houdini 双阶段实测（docs/BUILDER_FIRST_TEST.md / BUILDER_SECOND_TEST.md）：
- 第一阶段（单组件）：builder 基础设施全过（sandbox/cook/component_id/structure gate）
- 第二阶段（二组件 + Copy-to-Points）：idfix 逐实例 component_id 覆盖正确
  inventory 实扫 OUT：frame:6, wheel_fl:1, wheel_rr:1，40 点 8 prim
```

## 后续规划（ABCDE 五站）

| 站 | 内容 | 状态 | 依赖 |
|---|---|---|---|
| A | 声明式 Recipe Builder | ✅ 完成 | — |
| B | 构造轴替代 PCA（construction_axis + edini_world_axis 烘焙 + build 时一致性预检） | ✅ 完成 | A |
| C | 节点参数 DB（houdini_node_parms 查询工具） | ⬜ | 独立 |
| D | 黄金范例检索（recipe 格式的验证过资产模板） | ⬜ | A |
| E | 数值代理（轮廓圆度/对称性/silhouette IoU） | ⬜ | 独立 |
