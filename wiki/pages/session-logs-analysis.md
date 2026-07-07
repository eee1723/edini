# 🔬 会话日志第一性原理诊断

> **用途**：从两个真实程序化建模会话日志出发，用第一性原理诊断 Edini 程序化建模 agent 的系统性缺陷，并给出 A/B/C 三层后续改进路线图（本轮**未实施**，供下轮决策）。
> **方法**：日志时间戳取证 + 平台源码行号佐证（凡断言"平台行为错误"必落到代码行号）。
> **状态**：诊断已完成；本文档为纯沉淀，未动任何代码。
> **最后更新**：2026-07-07

---

## 0. 来源与方法

### 0.1 两份日志对照

| | 日志 1（桌子） | 日志 2（公路车） |
|---|---|---|
| 路径 | `~/.pi/agent/sessions/.../2026-07-07T07-11-48-753Z_*.jsonl` | `~/.pi/agent/sessions/.../2026-07-07T07-28-02-014Z_*.jsonl` |
| 时间窗 | 07:11–07:26（~15 min） | 07:28–07:38（~10 min） |
| 对象 | 双层桌子 | 公路自行车 |
| 部件拓扑 | 3 组件线性链：`tabletop → legs → shelf` | 7 组件 DAG：`frame → {fork→{handlebar,front_wheel}, rear_wheel, seat, crankset}` |
| 结局 | **成功且真的验证了参数联动**（length 1.2→1.5，X 尺寸 1.25→1.55） | 声明成功，但**未做任何参数扰动验证** |

### 0.2 第一性原理：程序化建模的四个不变量

任何"参数化多部件模型"若要成立，必须同时满足：

1. **坐标可参数化** —— 几何位置/尺寸来自对 live 几何的测量或对参数的引用，不是字面值。
2. **依赖显式声明** —— 部件 A 物理依赖部件 B，则该依赖必须以可被平台验证的形式声明（ports.in），不能靠 transform 硬摆。
3. **单元可读可改** —— 每个组件是独立 subnet，内部不堆 200 行单 SOP，他人可读懂、可手改。
4. **完成有判据** —— "done" 不是模型自觉，而是可检查的完成条件（每步都有 ✅）。

下文每个发现都标注**违背了哪条不变量**。

---

## ⚠️ 关键修正：第一版"output_index scaffold bug"诊断是错的

> 这一节必须先读。改进方向取决于它。

### 第一版断言（错误）

初版分析称："**scaffold 默认 `output_index=0` 接错**，shelf 的 4 个输入被连到 legs 的几何体输出而非锚点云"。

### 读源码后证伪

读 `python3.11libs/edini/project/builder.py` 的 `_ensure_input_scaffold`：

```python
# builder.py:282-292
from_id   = in_entry.get("from")
from_port = in_entry.get("port")     # ← 来自声明的 ports.in[].port
anchor    = in_entry.get("anchor")
...
upstream = core_node.node(from_id)
...
# 外部：下游第 i 输入 ← 上游第 from_port 输出。
subnet.setInput(i, upstream, from_port)   # ← 用的是声明的 port，不是默认 0
```

且日志里 shelf 的 scaffold 声明 `"port": 1` 是**正确的**（4 个 in 条目全 `{"from":"legs","port":1,"anchor":"shelf_mount_*"}`），scaffold 也确实按 `from_port=1` 接了。

**结论：scaffold 的 port 路由是正确的。没有 output_index bug。**

### 真实根因链（全部有日志时间戳佐证）

| 时间 | 事件 | 性质 |
|---|---|---|
| 07:15:58 | 模型自己把 `shelf/merge_shelf_pts` 接到 `__edini_anchor_clean_legs_*` 上 | 模型行为，非 scaffold |
| 07:21:35 | 模型不信任脚手架，对**子网内部的 filter 节点**用 `houdini_connect_nodes(output_index=1)` 重连，未生效 | Houdini 子网内部引用外部 upstream 的 setInput 语义复杂 |
| 07:21:57 | 退到 sandbox `setInput` 修，**disconnect 成功 / reconnect 失败**，把 filter 链扯断 | sandbox 不可用于组件级重连 |
| 07:24:01 | 模型**自己 delete 了整条 filter 链**（8 个 `houdini_delete_node`），改用 Object Merge 硬引用 `/obj/geo1/project1/legs/output_1` | 模型放弃 port 抽象，退回硬编码 |

### 修正后的定性

> 这是「**模型与一种它不理解但平台已正确实现好的机制作斗争 10 分钟，最终自己破坏契约退回硬编码**」—— 不是 scaffold bug。

**这条修正决定了 Layer A 的形状**：问题不在"修 scaffold 的 output_index"（它没坏），而在"**让 scaffold 把接线 ground-truth 报给模型**"，使模型不必靠怀疑和重连去探明。详见下文路线图 A。

> 📌 **方法论教训**：第一性原理分析若不落到代码行号，会把"模型行为"误判成"平台 bug"，导致改进方向整层错位。已沉淀为 [pitfalls.md](pitfalls.html) 的一条规矩。

---

## 发现 1：接线错觉 —— 违背"依赖显式声明"

见上节"关键修正"。模型浪费 ~10 分钟与正确的 scaffold 作斗争，根因是 **scaffold 不回报接线状态**，模型只能靠"接了看看有没有数据"反向探明。`route_warnings`（builder.py:138）只检查静态命名一致性，不回报运行时的 `setInput` ground-truth。

**严重度**：高（直接导致一次契约破坏 + 硬编码退路）。

---

## 发现 2：Python SOP 知识缺口系统性复发 —— 违背"单元可读可改"

两份日志里，**同类 Python SOP 错误反复出现 7+ 次**：

| 错误类型 | 出现次数 | 跨日志 | 性质 |
|---|---|---|---|
| `return` outside function（bare return 在 Python SOP cook body） | 6+（fork/handlebar/seat/crankset/2×wheel/shelf_builder） | 两日志都有 | 执行上下文心智模型不清 |
| `addAttrib` 必须先于 `setAttribValue` | 2（前后轮 `width` 属性） | 日志 2 | API 生命周期不清 |
| `createPoint()` 不吃位置参数 | 1（日志 1 shelf sandbox） | 日志 1 | API 签名记错 |
| `ch()` ≠ `hou.ch()`（Hscript vs Python 混淆） | 1 | 日志 1 | 表达式语言混淆 |
| `node.geometry()` 是输出非输入 | 1 | 日志 1 | 数据流方向不清 |

**这不是"模型笨"。** 一个熟练建模师这些是肌肉记忆。问题在于：**当前 skill 把"怎么在 Python SOP 里写组件生成器"完全留给模型即兴发挥** —— 每个组件都从一段空白 Python 字符串开始写，于是同一个坑在不同组件里反复踩（fork 修了 return，wheel 又踩一次；wheel 修了 return，handlebar 再踩）。

**严重度**：高（结构性重复犯错，浪费时间且降低模型可信度）。

---

## 发现 3：锚点测量全是 bbox 派生 —— 参数化只是表象（bike 最致命）—— 违背"坐标可参数化"

bike 的 frame 四个锚点**全部**用 `bbox_face_center` 测量：

```
head_tube       ← bbox +X 面中心
rear_dropout    ← bbox -X 面中心
seat_tube       ← bbox +Y 面中心
bottom_bracket  ← bbox -Y 面中心
```

但 frame 是**单一合并网格**（`gen_frame_curves` → `polywire` 后所有管子合并），它的 bbox 面中心 ≠ 真实的头管顶端 / dropout / 五通位置。模型自己在 07:38:35 承认：

> "后轮锚点 rear_dropout 使用 bbox face center 测量，由于车架是整体单网格，测量点略高于实际 dropout 位置。"

读 `python3.11libs/edini/vex_strategies.py:120-146` 确认：**当前所有 measure 策略（`bbox_corner`/`bbox_face_center`/`bbox_center`/`point_on_edge`/`grid_on_face`/`array`）都是 bbox 派生，没有 `by_name` / named-marker 策略**。

**后果**：调 `frame_scale` 时，轮子跟着 bbox 中心走，**不跟真实 dropout 走**。参数化只在"整体轮廓"层面成立，部件间的精确装配关系是脆的。这直接违背 skill 第一条原理："measure anchors from geometry, not hardcode."

**正确做法**：frame 生成器内部就**显式创建带 `@name` 的语义标记点**（如 `@name=head_tube_top` 落在真实头管顶端坐标），下游 anchor 用 `by_name` 测量。bbox 测量只该用于"整体姿态"类锚点，绝不该用于"精确装配"类锚点。

**严重度**：极高（直接削弱产品核心承诺"live 参数化"，且模型无法自查）。

---

## 发现 4：promote_params 返回 0 是 workflow 设计矛盾 —— 违背"完成有判据" ✅ 已解决（2026-07-07，方案 D）

> **已解决**：代码级取证确认这不是 promote 的 bug，而是 SKILL.md 教了三条互相排斥的参数化路径（①绝对 ch 直引 core design_params / ②subnet spare parm + 相对 ch / ③promote），agent 选了 ①（最省事），②③就废了。选**方案 D** 落地：文档对齐（路径①为唯一官方路径，promote 在该路径下返回 0 是**正确行为**，LIVE 硬门由 `verify_parametric` 接管）+ 新增可选工具 `project_repath_to_relative`（单组件绝对 ch→相对 ch，深度计算，让组件可迁移）。8 条 hython 铁证含"复制组件到另一 project 仍 cook"。详见 [progress.md](progress.html) 的"最后更新"卡片。

两份日志 `project_promote_params` 都返回 **0**。模型两次都自我安慰"参数已在 core 层，无需提升"。

读 `python3.11libs/edini/project/builder.py:467-536`（`promote_params` / `_promote_one_parm`）：promote 只提升 **subnet 的 `spareParms()`**。

但 `SKILL.md` 第 2b 步教模型用**绝对 `ch()` 直引 core design_params**：

```
houdini_set_param(node_path, "sizex", "ch('/obj/.../project_core/length')")  # ABSOLUTE
```

模型从不建 subnet spare parm → `subnet.spareParms()` 为空 → promote 永远返回 0。

**这是 skill 内部的自相矛盾**：第 2b 步（绝对 ch 直引）与第 4 步（promote subnet spare parm）是两条互斥的参数化路径，skill 同时教了，promote 这步成了永远空操作的死重量。长期会让模型学会"这步可以无视"。

**副作用**：绝对路径 `ch('/obj/geo1/projectN/...')` 让组件**不可迁移** —— 复制 project2 成 project3，所有 `ch()` 失效，整模型崩。

**严重度**：中（功能上当前能跑，但 workflow 有死重量 + 组件不可迁移）。

---

## 发现 5：bike 跳过参数联动验证 —— 违反 skill 自己的 premature-done 诫令

skill 四诫第 4 条："Declare done prematurely."

- **桌子**：改 `length` 1.2→1.5，**量化验证** X 尺寸 1.25→1.55 ✅
- **自行车**：**零参数联动验证**，仅凭 `inspect_health` 的 `overall_ok` 就在 07:38:44 声明完成。

确认现有验证工具：`verify_orientation`、`inspect_geometry_health`、`geometry_inventory`、`houdini_check_errors`（见 `tool_executor.py:328-379`）。**没有任何扰动测试工具**。

`overall_ok` 只证明"此刻没坏"（无孤儿点、无退化面），**不证明"参数化成立"**（改参后几何朝正确方向变化）。结合发现 3，bike 很可能在 `frame_scale` 改了之后轮子位置是错的——但没人查。这是典型的 premature done，且**正是 skill 自己最警惕的失败模式**。

**严重度**：高（"完成"判据不可靠 = 产品核心质量门失效）。

---

## 公平起见：做对的地方

不全是坏消息。两份日志也证明流程方向正确：

- **组件分解**两例都合理（桌子线性链；bike DAG 依赖图清晰，frame 作为根部件正确）。
- **brainstorming fast-path**（1–2 问即开工）执行得很好，没陷入 10 问访谈 —— 这正是 skill 设计意图。
- **design_params 集中在 core** 是合理的中心化（builder.py `_ensure_design_params` 落成真实 spare parm）。
- **bike 用 PolyWire + `width` 属性做变粗管道**是真技巧（虽然 `addAttrib` 顺序错了）。
- **桌子最终真的达到了参数化并量化验证了** —— 证明流程能跑通，问题在可靠性而非方向。
- **scaffold 本身是正确的**（发现 1 修正后）—— `_ensure_input_scaffold` 的 port 路由、`@name` Blast 过滤、prim-strip 净化都是健壮设计。

---

## 后续路线图（✅ A/B/C 已全部实施 — 2026-07-07 · ✅ 回归硬化 — 2026-07-07）

每层都标了**改哪个文件 / 为什么 / 配什么 hython 铁证**。三层均已落地，详见
[progress.md](progress.html) 的"最后更新"卡片。

> **🔧 回归硬化（2026-07-07，合并 master）**：对 A/B/C/发现4 的修复（commit `1093eb4`）
> 做了行号级回归就绪审计，发现并修硬 **2 个违背自身安全契约的真 bug**：
> ① `verify_parametric` 的 perturb→recook→snapshot 段无 `try/finally`，perturb 后 cook
> 抛异常会**静默把参数留在 `new_value` 污染用户场景**（违背 docstring 的 "ALWAYS restore"）——
> 已加 `try/finally` 保障还原（反向验证：禁用 finally 后参数留 2.0 场景被污染，测试正确转红）；
> ② `by_name` 的 marker 名拼错曾**静默产 0 点无诊断**（`__found=0` 无 else 分支）——
> 已加 VEX `error()` 硬报错，让 `inspect_health`/`verify_parametric` 自然拾取。
> 另修正 `repath_to_relative` 的 `count` 把失败 `setExpression` 也计入的误报。
> 补全审计点名的缺测边界：`_make_replacer` 全覆盖（`hou.ch` 形式 / 近名碰撞 / 多层 parm_tail）
> + 4 测真机 hython（restore-on-error / 零匹配报错 / repath hou.ch / 近名碰撞不动）。
> 1 测 `expectedFailure` 诚实记录 Layer A 的 `internal_chain_ready` 只查节点存在不查接线的
> 脆弱点（待下轮）。**946 测试全绿 + 1 xfailed**，零回归。

### 🅰 Layer A —— 平台层：scaffold 回报真实接线状态 ✅ 已实施

> **杠杆最高，改动最小。优先做。**

| 项 | 内容 |
|---|---|
| **改哪里** | `python3.11libs/edini/project/builder.py:140-144`（`build_project_scaffold` 返回值） |
| **改什么** | 返回值增加 `input_wires` 字段：遍历每个 `ports.in` 条目，读 `subnet.inputConnections()` 确认 (a) 外部连线存在且 `output_index == from_port`；(b) 内部 `filter_<from>_<anchor>` / `__edini_anchor_clean_*` / `in_<from>_<anchor>` 三件套就绪。报 ground-truth，不报推断。 |
| **治什么** | 发现 1 —— 模型不再需要"怀疑 scaffold 接错 → 重连 → 破坏 → 退回硬编码"那 10 分钟。看到 `input_wires[].ready == true` 就放心往下建。 |
| **hython 铁证** | (1) 声明正确 `port:1` 后，scaffold 返回的 `input_wires` 全 `ready:true, carries:"anchors"`；(2) 对照组声明 `port:0`，返回 `ready:true, carries:"geometry"`（明示拿的是几何而非锚点，防止模型误用）。 |
| **风险** | 低。只读 `inputConnections()`，不改 setInput。 |

### 🅱 Layer B —— 知识层：Python SOP 组件模板 + DISCIPLINE ✅ 已实施

> **纯 prompt 层，零平台代码。**

| 项 | 内容 |
|---|---|
| **改哪里** | `skills/project-modeling/` 新增 `COMPONENT_TEMPLATE.md`；SKILL.md 第 3 步链接它；MISTAKES.md 补 5 条 Python SOP 错误。 |
| **改什么** | 固化组件生成器骨架：(1) 守卫用 `if inputs and inputs[0].geometry().points():` 包裹整个 body（**禁 bare `return`**）；(2) `addAttrib` 必须在任何 `setAttribValue` 之前；(3) 读输入统一用 `node.inputs()[0].geometry()`，不要混用 `node.geometry()`（那是输出）；(4) 建点用 `pt = geo.createPoint(); pt.setPosition(hou.Vector3(...))`；(5) 明确"**sandbox 无输入 ≠ 组件生成器**"——sandbox 用于无依赖的试错，组件生成器必须在 subnet 内且消费 anchor 输入。 |
| **治什么** | 发现 2 —— 消灭 `return`/addAttrib/createPoint 那 7+ 次重复错误。 |
| **hython 铁证** | 用模板在真机搭一个 3 组件小模型（如灯=底座+杆+灯罩），零 Python SOP 错误一次过；对照旧写法必踩至少 2 个 return 错误。 |
| **风险** | 极低。纯文档。 |

### 🅲 Layer C —— 工作流层：live-guarantee 扰动验证门 + named-marker 锚点 ✅ 已实施

> **最治本，也最重。建议 A、B 落地后再做。**

#### C1：named-marker 锚点（治发现 3）

| 项 | 内容 |
|---|---|
| **改哪里** | `python3.11libs/edini/vex_strategies.py` 新增 `named_marker` 策略；`project_add_anchors` 支持 `measure:"by_name"`。 |
| **改什么** | 根组件生成器（如 frame）在生成几何时**同时输出带 `@name` 的语义标记点**（落在真实几何坐标，如真实头管顶端）。下游 anchor 用 `by_name` 从该点云里按名取点，而不是从 bbox 派生。 |
| **治什么** | 发现 3 —— bike 那种 `bbox_face_center` 伪参数化。锚点真正跟随几何变形。 |
| **hython 铁证** | named_marker 锚点改 `frame_scale` 后 live 跟随真实 dropout（非 bbox 中心）；对照 bbox_face_center 锚点偏离真实位置。 |

#### C2：`verify_parametric` 扰动验证门（治发现 5）

| 项 | 内容 |
|---|---|
| **改哪里** | 新增工具（参考现有 `verify_orientation` 的注册模式 `tool_executor.py:370` + `pi-extensions/edini-tools/tools/harness.ts:133`）。 |
| **改什么** | 工具行为：改一个 design_param → recook → 量化验证 (a) 几何非零、(b) 朝预期方向变化、(c) 无新错误。作为 Step 4 "完成"的**硬门**（guards 层或 skill 完成判据）。 |
| **治什么** | 发现 5 —— bike 跳过参数联动验证就 premature-done。`overall_ok` 不再够用。 |
| **hython 铁证** | `verify_parametric` 对 table `length` 1.2→1.5 报 PASS（X 尺寸正方向变化）；对断链（手动破坏 ch()）报 FAIL。 |
| **风险** | 中。新增工具 + 需设计"预期方向"的声明接口。 |

---

## 推荐执行顺序

1. **先 A**（杠杆最高、改动最小、风险最低）—— 立刻消除"接线错觉"那一类 10 分钟浪费。
2. **再 B**（纯文档、零风险）—— 消灭 Python SOP 重复错误，提升每次建模的基础可靠度。
3. **最后 C**（最治本）—— C1 解决参数化的"真实性"，C2 守住"完成"的质量门。C 依赖 A/B 落地后的稳定基础。

---

## 一句话总结

> 桌子证明了**流程方向是对的**（能到 parametric 并验证）；自行车暴露了**流程的可靠性还远不够**（模型与正确的 scaffold 作斗争、Python SOP 靠即兴、参数化靠 bbox 假装、完成判据靠自觉）。真正的下一阶段重心不该是"做更复杂的模型"，而是**把发现 1–5 这五个底层契约修硬** —— 否则模型越复杂，脆性越大。

**本轮交付**：仅本文档 + [progress.md](progress.html) 卡片 + [pitfalls.md](pitfalls.html) 两条踩坑。A/B/C 待下轮决定。
