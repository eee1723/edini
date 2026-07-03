# 🤖 Agent 交接文档

> **用途**：让新 Agent 或开发者在 Edini 仓库里快速上手。

**最后更新**：2026-07-03（**引导 agent 走组件流水线** — 写 project-modeling skill + system prompt 决策表改新流程首选。修复 agent 默认走旧 build_assembly 的引导偏向。地基 + 工具 + 引导三件齐备，待 GUI 真机验证 agent 主动选新流程）。
**当前阶段**：**Project HDA**（新主线）—— 把程序化建模从"一次性生成器"升级为"长期协作伙伴"。一个程序化建模项目 = 一个 Project HDA（**SOP 上下文**：geo 外壳 + 内部 SOP HDA core 承载几何 + 知识图谱富化声明 JSON 存隐藏 parm + 嵌入 PySide 面板 + 日志）。
**组件建模地基状态（2026-07-02 交付，子系统 1）**：✅ **hython 决定性验证通过**。新范式：一个组件 = core 内一个 **subnet**，通过**多输出端口**对外暴露——`out[0]`=主几何（null `out_geometry` → `output_0` output 节点形成 subnet 输出端 1），`out[1..n]`=**信息点云**（带 `@P`/`@orient`/`@name` 的 point，null `out_anchors` → `output_1`）。组件间流水线协作（车架输出 wheel_mount 锚点 → 车轮消费定位）。真机铁证：subnet output 节点机制验证通过（两个 output 节点映射到两个独立输出端，下游各取所需）；锚点 @name 发射正确；重建幂等不破坏 LLM 已加内容；promote 生成 chassis_length 两层 ch() live 引用。
**旧 assembly 范式已移除**：`assembly` 字段、`get_assembly`/`set_assembly`、`build_project_model`、`project_build_model` 工具全部清除。rooted-modeling skill（assembly_builder/vex_strategies/measure）**保留**给 skill 用，只是 Project HDA 不再调。
**关键架构决策（本次确立）**：① **subnet = 组件间信息总线**（端口=信息锚点，非 drift 容器）—— 第一输入端是组件输出，后续端口输出给其他组件做定位定向；② **新范式取代旧范式** —— mount/leaf 扁平网络被组件流水线取代；③ **声明 = 知识图谱** —— `components`（含 `ports`/`params`）即组件关系图，drift = diff 这份意图 vs 实际网络；④ **Builder = 脚手架（确定性），几何 = LLM 自由活** —— builder 只建空 subnet+4节点+连线，几何和跨 subnet 连线归 LLM；⑤ **promote 脚本** —— 组件 subnet spare parm 一键按组件分组提取到 core HDA，两层 ch() live 引用。
**真实 API 发现（2026-07-02 hython 验证，重要）**：① subnet 内建 `output` 节点类型就是 `"output"`（`createNode("output")`），两个 output 节点按 `outputidx` 形成两个独立 subnet 输出端；② **spare parm API**：READ 用 `node.spareParms()`（返回 `list[hou.Parm]`），WRITE 用 `node.addSpareParmTuple(tmpl, in_folder=(folder,), create_missing_folders=True)`——`spareParmGroup()`/`setSpareParmGroup()` 在真机**不存在**（旧 handoff bug#1 描述不准确，以此为准）。
**引导状态（2026-07-03）**：✅ **agent 引导已就绪**。写 `skills/project-modeling/SKILL.md`（组件流水线范式 + 工作流 + 端口协议 + 桌子示例 + 何时用 vs build_assembly）；system prompt 决策表改为"多组件模型首选 Project HDA 组件流水线，build_assembly 降为简单 root+leaf 兼容路径"。工具能力已扩展（connect_nodes 加 output_index 取锚点端；set_param 加向量 + ch() 表达式 live 引用）。三件齐备（地基 + 工具 + 引导），hython 决定性验证 agent 工具链能建模（TestAgentToolsHython）。
**下一步**：⓪ **GUI 真机验证 agent 选新流程**（重启 Houdini，让 agent "做一个桌子"，确认它调 project_build_scaffold 而非 build_assembly —— 这是引导生效的唯一铁证）；① 子系统 3：知识图谱描述生成；② 子系统 4：drift 检测；③ LLM 建模纪律细化。
**工作分支**：master（引导改动直接在 master）。feat/project-component-foundation 已合并（组件地基）。

---

## 🔴 最重要：Project HDA（2026-07-02，新主线，必读）

### 这是什么

rooted-modeling 的 `build_assembly` 是**一次性生成器**：agent 产声明 → builder 构建 → 完成，agent 是唯一作者。Project HDA **有意打破这条不变量**：让用户也能直接在 Houdini 里改几何网络，让 agent 持续理解、优化、迭代项目。这是从"一次性生成器"到"长期协作伙伴"的范式升级。

### 核心架构支柱：把"语义同步"降级为"结构 diff"

难点是：当用户和 agent 都能改时，如何保持 agent 维护的知识图谱与真实网络同步？**核心策略**：让 subnet 的物理嵌套结构镜像组件分解（浅镜像，组件组一层：chassis/ wheels/ lights/），使"哪些节点属于哪个组件""组件是否还存在""参数依赖"全部变成**确定性查询**，无需 LLM 语义推断。这是整个架构能成立的支柱。

### 11 个核心决策（用户拍板）

1. 真实来源=**混合**（网络管几何事实，图谱管意图）
2. 图谱范围=**C 档**（结构+语义+参数化意图）
3. 同步策略=**检测偏离+人确定**（不解逆程序化建模难题）
4. "优化"=四向并行（参数化整洁/图谱准确/性能可维护/持续加组件 + 日志输出供跨项目复用）
5. 面板=**PySide 全自绘嵌入 HDA**
6. 半成品=**始终可 cook**（每步原子、失败回滚）
7. 图谱表示=**富化声明即图谱**（一个意图来源，无双重同步）
8. 计划=**强制、详细、可 review、用户控序**
9. 组件管理=**subnet 浅镜像**（分水岭决策）
10. 参数管理=**HDA 原生参数接口**
11. 多项目=**每个 HDA 独立面板 + 独立 Pi session**

### 最小闭环 + 建模能力（✅ 均已真机验证，2026-07-02）

```
python3.11libs/edini/project/
  state.py        # 声明 schema（components/ports/params）+ JSON↔隐藏 parm + plan/log 助手 + add_component/get_component（纯 Python，26 单测）
  ports.py        # 端口协议常量（out_geometry/out_anchors/output_0/output_1 节点名）+ validate_component_ports（纯逻辑，8 单测）
  node.py         # 隐藏 string parm 模板 + create_project_hda（SOP 上下文：geo 外壳 + 内部 core）+ find_project_cores
  builder.py      # build_project_scaffold（建组件 subnet+4节点脚手架）+ promote_params（spare parm→core HDA 两层 ch() live）
  panel/
    project_widget.py    # 三栏面板 + 项目选择器 + 对话接线 + 轻量流式渲染 + IME popout
    project_pane.py      # onCreateInterface() 入口函数（Houdini Python Panel 真实写法）
python_panels/edini_project.pypanel  # .pypanel XML（走 HOUDINI_PYTHON_PANEL_PATH 发现）
otls/edini_project.hda   # edini::project 类型（SOP 上下文 + 定义层解锁，hython + GUI 验证）
scripts/make_project_hda.py  # 一次性 HDA 生成脚本（SOP 上下文 + lockContents=False + unlockNewInstances=True）
pi-extensions/edini-tools/tools/project.ts  # project_build_scaffold TS schema（agent 调用入口）
tests/test_project_state.py   # 26 单测（components schema，无 assembly）
tests/test_project_ports.py   # 8 单测（端口协议）
tests/test_project_hython.py  # 5 hython 决定性测试（脚手架结构/锚点发射/幂等/promote/全链路）
```

**关键设计点（真机验证后定稿）**：
- **HDA 用 SOP 上下文**（`edini::project` 注册在 Sop category）。结构：`/obj/<project>`（geo 外壳，显示节点）→ 内部 `/obj/<project>/project_core`（SOP HDA，建模核心）。rooted 扁平网络直接建在 core 内部，用户可手改，spare parm `ch("../<name>")` 引用深度天然正确。
- **HDA 定义层解锁**：`lockContents=False` + `unlockNewInstances=True`（make_project_hda.py save 前）。实例天生可编辑，无需运行时 `allowEditingOfContents` hack（builder 的 `_ensure_editable` 仅作防御性兜底）。
- **建模链路自包含**：`build_project_model` 把 `core_node.path()` 作为 `build_assembly` 的 `root_path`，几何全部建在 core 内部，**零 /obj temp 污染**（真机监控确认：build 后 /obj 只有项目本身的 geo 外壳）。
- **声明新增 `assembly` 字段**：rooted 格式 `{id,params,root,mounts,leaves}` verbatim 存储，`build_assembly` 零 adapter 直接消费。`set_assembly`/`get_assembly` helper（基本结构守卫，深层验证靠 `validate_assembly` shift-left）。
- **每面板独立 RpcClient + 独立 Pi 进程**（spec 决策 #11）。不寄生主窗口——Pi 找 9876 工具执行器靠 `EDINI_TOOL_PORT` 环境变量，不依赖对象引用，多个 Pi 天然共享一个无状态 HTTP server。
- **ToolExecutor 是进程级单例**（`get_tool_executor()`），与 EdiniMainWindow 生命周期解耦。主窗口 closeEvent 不再 stop 它。
- **对话 bootstrap 时序**：连接 `status_changed`，首次 connected 时 `set_session_name` + `set_model`（Pi 冷启动无模型配置，必须设否则首条消息无回复）。**不要** `send_new_session`（进程已自带全新 session，且会触发 visionizer stale-ctx 报错阻塞 LLM）。
- 声明 JSON 存在隐藏 string parm `__edini_state`（随 .hip 自包含）。

**建模能力真机铁证（hython，car assembly）**：
- build 成功，OUT **1152 点**（底盘 box + 4 轮子），core 内 13 个 SOP（扁平结构：root_shape + 4 mount wrangle + wheel shape/pscale/cloud/ctp + OUT）
- **LIVE**：`length` 4→8 → mount_wheel_fr 第一个点 x 从 +2 移到 **+4**（轴距 live 跟随 root bbox，零烤值）
- **重建幂等**：再次 build 子节点数一致（13），无重复
- build 后 `/obj` 只有 `project_car`，**零 temp 节点**；用户可在 core 内手改（加 null 节点 OK）

**真机验证抓修的 8 个 bug**（全是 mock 测不出的真实环境问题）：
1. `setHidden`/`spareParmGroup` → 真实 API 是 `hide()`/`addSpareParmTuple`
2. pane 找不到 → 包 JSON 用无效的 `houdini.python_panels` 键，改 `HOUDINI_PYTHON_PANEL_PATH` 环境变量 + `python_panels/` 目录
3. PySide2 + 继承 `hou.pypanel.PythonPanelInterface` 崩溃 → Houdini 21 用 PySide6；`.pypanel` 真实写法是模块级函数 `onCreateInterface()` 返回 widget
4. 每次发送弹主窗口 → 独立 RpcClient + ToolExecutor 进程单例（不再寄生 `open_chat_window`）
5. 流式卡顿（输入框冻结）→ `_AiBubble.update_streaming` 每 chunk 跑全文 mistune + QLabel 富文本重排；改轻量 `_StreamBubble`（纯文本流式，finalize 才跑一次 markdown）
6. 中文输入失焦 → Houdini Python Panel 容器在 Qt 输入法管道前拦截键盘事件（SideFX 确认的 bug），嵌入 widget IME 不可用；改 popout 输入对话框（父窗口 `hou.qt.mainWindow()`，真实顶层窗口 IME 正常）
7. 首条消息无回复 → bootstrap 时未 `set_model`（Pi 冷启动无 provider/model）
8. visionizer stale-ctx 阻塞 LLM → 去掉多余的 `send_new_session`（每面板已是独立 Pi 进程，session 天然隔离）

**已知限制**：嵌入面板的内联输入框不支持中文 IME（Houdini 容器层限制，非配置问题），中文需点 💬 按钮走 popout 对话框。英文/粘贴不受影响。

---

## 🔴 次重要：rooted-modeling skill（2026-06-29，基础，必读）

---

## 🔴 最重要：rooted-modeling skill（2026-06-29，必读）

### 这是当前主线

程序化建模的**第四次演进**，取代了被搁置的声明式资产管道。**核心思想**（用户原话）：「**先做根件（车架/底座/房子外壳），再用根件的真实几何去算出所有其他组件的位置，不能硬编码**」。

**为什么取代声明式管道**：旧管道的 build 层是「测一次、烤成字面值」——build 时测对 root 几何算出坐标写进 xform，但写完就死了，用户改 root 参数叶子不动。这违背 live 参数化的核心承诺。

**M2 的突破（live 关联）**：每个 mount 变成一个 `attribwrangle`，VEX 每次 cook **实时读 root 的 bbox**（`getbbox_min/max`），叶子用 `copytopoints` 盖印。改参数 → bbox 变 → wrangle 重 cook → 点移位 → CTP 重盖印，**全程零烤值**。

### 4 角色

| 角色 | 是什么 | 怎么得到 |
|------|--------|----------|
| **Root** | 根基组件（车平台/键盘盘/房子外壳） | 先建，native SOP，size 读参数表达式 |
| **Mount** | 位置+朝向，叶子坐的地方 | **测量** root 的 cooked 几何（bbox 角点/面中心/网格/阵列）。永不硬编码坐标 |
| **Shape** | 自包含叶子资产（轮子/键帽/门） | 形态独立于 root |
| **Leaf** | 摆到 Mount 上的 Shape | 形态独立，**摆放派生** |

### 关键技术决策（用户拍板）

1. **VEX + Copy to Points** 实现 live（不是 Python SOP）。
2. **不让 LLM 写 VEX**：每种测量原语 = 一段**预制 VEX 策略**（`vex_strategies.py`），Python 解析符号串（`"+X-Y+Z"`→`{cx:1,cy:0,cz:1}`）注入数字。agent 只选策略+参数。
3. **measure.py 保留作预言机**：Python 算期望点，VEX 算实际点，逐点对比验证 VEX 正确性。
4. orient 用 **`@orient` 四元数**（`dihedral({0,1,0}, dir)`），不是 @N+@up。

### 里程碑

| MS | 内容 | 状态 |
|----|------|------|
| M0 | measure.py 测量层 + 小车 4 轮（xform 版） + SKILL | ✅ 交付 |
| M1 | grid_on_face（键盘网格）+ array（阶梯阵列）fan-out | ✅ 交付 |
| M2 | **live 关联**：vex_strategies + 重写 build 为 attribwrangle+CTP + root 参数暴露 spare parm | ✅ 交付（真机 hython live recook 铁证） |
| M2.5 | **leaf align convention**：orient point-class 修复 + align_axis + origin 规范化 + 分组 CTP | ✅ 交付（9 真机 facing 铁证） |
| M2.6 | **leaf 参数全 live**：leaf shape/scale/offset 统一走 ch("../name")（之前只有 root live） | ✅ 交付（真机 wheel_radius/tube_r live 铁证） |
| M2.7 | **shape 链细节**：leaf 可声明 SOP 链（polyextrude/polybevel/subdivide/grid） | ✅ 交付（真机 extrude/bevel 铁证） |
| M3 | **cells 测量原语** + 三层类架构 + square/fill 模式 + Pi agent 端到端链路 | ✅ 交付（599 测试） |
| M3.5 | **TabularFill 四布局**（pickets/tiles/shelf/blocks）+ per-cell orient | ✅ 交付（595 测试 + 7 hython 铁证） |

### 真机铁证（Houdini 21.0.440）

```
车：length 4→8，recook（不重建）→ 前轮 (+2,-0.25,+1) → (+4,-0.25,+1) [MOVED live]
键盘：tray_width 4→8，recook → 15 键帽网格整体重缩放 [MOVED live]
阶梯：3 踏步对角攀升 (run=0.5, rise=0.3)
```

### 关键文件

```
python3.11libs/edini/
  measure.py           # 测量层 + Python 预言机（bbox 角点/面中心/边点/grid/array/方向/朝向）
  vex_strategies.py    # 预制 VEX 策略库（每测量原语一段 detail-wrangle 模板 + 符号串解析器）
  assembly_builder.py  # build_assembly（live 网络：root + mount wrangles + CTP + OUT）+ validate + root 参数 spare parm 暴露
  exprs.py             # 安全表达式引擎（复用，未被搁置）
pi-extensions/edini-tools/tools/rooted.ts  # build_assembly TS schema（live 描述 + promptGuidelines）
skills/rooted-modeling/SKILL.md            # skill 文档（4 角色 + live 章节 + shape 参数表）
tests/
  test_measure.py            # 53 测试（测量层 + Python 预言机）
  test_assembly_builder.py   # 25 mock 测试（校验 + VEX 选择器解析 + 网络结构）
  test_assembly_hython.py    # 5 真机测试（含 2 个 live recook 铁证：车+键盘）
scripts/
  verify_vex_strategies.py  # 7 个 VEX 策略 vs Python 预言机逐点对比（hython）
  show_assemblies.py         # 构建 car/keyboard/stairs → edini_showcase.hip + live demo
edini_showcase.hip           # 三个 live 模型，可 GUI 打开改参数看效果
```

### 开发机环境（两台，跨机协作）

项目在两台机器间切换开发，hython 路径不同。**hython 测试会自动发现**（`tests/test_assembly_hython.py:_find_hython()` 的 `_HOUDINI_CANDIDATES` 已覆盖两台机器；或设 `EDINI_HYTHON` / `HYTHON` 环境变量覆盖），缺失则 skip。两台机器无需改任何代码。

| 机器 | hython 路径 | 发现方式 |
|------|------------|---------|
| **精创机**（Houdini 完整安装） | `C:\Program Files\Side Effects Software\Houdini 21.0.440\bin\hython.exe` | `_HOUDINI_CANDIDATES` 的 `C:\Program Files\Side Effects Software` 自动列出 `Houdini 21.0.440` 子目录 |
| **另一台** | `D:\houdini\bin\hython.exe` | `_HOUDINI_CANDIDATES[0]`（已列首位） |

> ⚠️ 精创机上 `D:\houdini` 不存在——下方命令里的 `D:\houdini\bin\hython.exe` 是另一台机器的路径，精创机请替换为上面的完整安装路径，或直接 `python -m pytest tests/`（hython 自动发现）。

### 怎么跑

```bash
# 真机验证 VEX 策略
"D:\houdini\bin\hython.exe" scripts/verify_vex_strategies.py
# 精创机：
"C:\Program Files\Side Effects Software\Houdini 21.0.440\bin\hython.exe" scripts/verify_vex_strategies.py

# 构建 + live demo + 存 .hip
"D:\houdini\bin\hython.exe" scripts/show_assemblies.py

# 全量测试（mock + hython，本机全跑；hython 路径自动发现）
python -m pytest tests/ -q
```

### ✅ rooted-modeling leaf 层问题（用户 2026-06-29 实测发现 → M2.5 已全部修复）

用户在 Houdini GUI 打开 `edini_showcase.hip` 实测后报告 4 个 leaf 层问题，**M2.5 全部修复并真机验证**：

1. **orient 不生效**（`mount_wheel_fr` 的 `f@orient=xxx` 没起作用）→ 根因：detail wrangle 里 `p@orient=` 写成 detail 属性 CTP 不读。修复：`setpointattrib` 写到每个 point。**systematic-debugging 进一步发现**：detail wrangle 的 `npoints()` 不反映同次 cook 内 addpoint 创建的点，导致循环永不执行 → 改用 `__newpts[]` 数组（每个 addpoint append 进去）。
2. **copy 第一输入端朝向**（第一输入端应强制朝 z 轴，z 轴朝向第二输入端 N 方向）→ 根因：leaf 对齐轴硬编码 +Y。修复：新增 `orient.align_axis` 字段（±X/±Y/±Z 六轴可配）。**关键事实纠正**：torus 对称轴是 +Y（圆盘在 XZ 平面）不是 +Z，spec 原假设错了，hython 实测纠正。
3. **leaf 原点规范化**（用 matchsize 或 vex 把模型位移到标准轴避免和 root 穿插）→ 修复：新增 `leaf.origin`（anchor: bbox_center / bbox_face:±XYZ / [x,y,z] + offset），copy 前插入 point wrangle 规范化。
4. **单个 copy 出 N 实例**（4 同形状轮子 + 4 mount merge 后用 1 个 copy）→ 修复：`_leaf_group_key` + `_group_leaves`，同 shape+scale+origin 的 leaf 共享 1 shape + 1 CTP。

**真机铁证**（hython 21.0.440，9 个 facing 测试全过）：bicycle 4 轮每个 bbox `[0.063, 0.805, 0.805]` thin 轴 = X（车轴方向）；mount cloud orient 四元数旋转 +Y 得 X；1 CTP 4 轮；car 回归仍正确；live recook 工作。

**设计/计划文档**：`docs/superpowers/specs/2026-06-29-rooted-leaf-align-convention-design.md` + `docs/superpowers/plans/2026-06-29-rooted-leaf-align-convention.md`。

**仍存在的设计限制（非 bug）**：只有 root-shape 参数是 live；mount 内部参数（grid rows/cols/margin、array count/step/origin）build 时烤进 VEX，改这些要重建。

---

## 🔴 最重要：声明式资产管道 M2（2026-06-27，必读）

### 这是当前主线

第三次程序化建模演进，已交付完整的 M2 能力。**核心思想**：agent 写声明式资产 JSON（params + skeleton + components），validate_asset 免费校验，build_asset 生成 Houdini 几何。**capability before rules** 纪律——先证明能力，规则（skill）建立在已验证能力之上。

### M2 完整能力清单

| 能力 | 用途 | 示例资产 |
|------|------|---------|
| `native_chain` backend | 声明式 SOP 节点链（box/tube/torus），参数值支持表达式 | table/chair/bike 车架管 |
| `python` backend | Python SOP 画曲线/截面，**值注入**参数（agent 用参数名，builder AST 替换数值）| table 桌面圆环、bike 轮子 |
| 多实例 `instances[]` | 1 定义 + N 实例挂 N 骨架点（transform 复制，非 CTP）| 4 桌腿、2 轮子 |
| `orient` 旋转 | attach.orient / instance.orient（Euler 度）| 椅子倾斜靠背、轮子朝向 |
| **`from`/`to` 两点连接** | 管材/桁架——builder 自动算长度/中点/朝向，**agent 永不算角度** | 自行车车架 4 管材 |

### 关键文件

```
python3.11libs/edini/
  asset_model.py      # 纯数据层：schema + validate（含 component 校验：orient/from-to/instances）
  asset_builder.py    # 几何构造层：build_asset 主入口 + _build_native_chain/_build_python_component/
                      #   _from_to_geometry/_move_to_point/_inject_param_values（值注入 AST）
                      #   + M4 setUserData 印记（edini_asset_source）
  harness.py          # commit_sandbox（M4：识别印记绕过 G3a/G3b，保留 G3c/结构 + receipt method）
  tool_executor.py    # validate_asset + build_asset + commit_sandbox handler（TOOL_HANDLERS 注册）
  exprs.py            # M1 表达式引擎（safe AST，支持比较/布尔用于约束）
  skeleton_resolver.py # M1 骨架点 DAG（topo + 环检测）
pi-extensions/edini-tools/tools/asset.ts  # validateAsset + buildAsset TS schema（含 promptGuidelines + M4 commit 说明）
skills/asset-authoring/SKILL.md           # agent 写资产的约定文档（实战验证沉淀 + M4 commit 流程）
python3.11libs/edini/data/
  table.asset.json    # 多实例桌腿 + python 圆环（3 定义/6 实例）
  chair.asset.json    # 倾斜靠背（orient 实战）
  bicycle.asset.json  # 完整自行车（from-to 管材 + python 轮子）
tests/
  test_asset_builder.py       # mock hou：native_chain/python/instances/orient/from-to + M4 印记
  test_commit_declarative.py  # M4：声明式提交 vs 旧管道门禁（mock hou）
  test_asset_model.py         # 纯数据：validate 全错误码 + 3 资产端到端
  test_asset_hython.py        # 真机：table/chair/bicycle 端到端 + M4 TestCommitAssetHython（build→commit）
  test_tool_executor_asset.py # handler 接入
```

### 真机验证（Houdini 21.0.440）

桌子 168 点、椅子 112 点、**自行车 224 点（4 管材 + 2 轮子，零 cook 错误）**。上管长度自动 = 两点几何距离（精确）。

### 实战测试的价值（capability-before-rules 兑现）

自行车实战暴露并修复了 3 个真实缺陷（M3 抓不到）：
1. 组件无朝向 → 加 orient 旋转
2. orient 被静默忽略 → 加 COMPONENT_BAD_ORIENT 校验
3. **无两点连接原语** → 加 from-to（管架结构核心，agent 永不算角度）

### 下一步（M4 已交付，2026-06-29）

1. **✅ M4 组装提交已交付**：`build_asset` 打 `edini_asset_source` userData 印记 → `commit_sandbox` 识别后绕过旧 G3a bake（edini_world_axis）+ G3b PCA 方向门禁，保留 G3c 健康 + 结构门禁，receipt 标 `method:"declarative"`。**核心冲突**：旧门禁为提示词管道设计，会误判声明式资产（builder 故意不烘焙 axis、不走 PCA）。**策略**（与用户敲定）：标记 + 绕过是 opt-in 的，旧 network_mode 手写网络（无印记）继续走完整门禁栈，不削弱旧防御。全量回归 592 passed 零回归。
2. **M4 真机 hython 实测（待办）**：本机 hython 在 `D:\houdini\bin\hython.exe`（Houdini 21.0.440，完整可用）。可跑 `D:\houdini\bin\hython.exe -m pytest tests/test_asset_hython.py::TestCommitAssetHython` 验证 build→commit→receipt 端到端。
3. **真实 Pi agent 端到端**：让 Pi agent 用 asset-authoring skill + build_asset + commit_sandbox 写一个它没见过的资产，验证它能否理解模型 + 完整走通 build→commit。**M4 让这条线现在可达**（之前 build_asset 出来的 sandbox 无法 commit，端到端断了）。最后的 capability 检验。
4. **M3 暂缓**：经分析无必要（历史失败无一是骨架点摆位错；resolve_skeleton 预览已能发现几何错；约束断言会扼杀创造力）。

**M4 关键文件**：`asset_builder.py`（setUserData 印记）/ `harness.py`（commit_sandbox 识别分支 + receipt method）/ `tests/test_commit_declarative.py`（声明式 vs 旧管道 vs 健康）/ `tests/test_asset_hython.py`（TestCommitAssetHython 真机）。

---

## 🔴 历史架构转向：2026-06-23（保留作参考）

### 发生了什么

旧的程序化建模管道（提示词驱动 + validate_recipe/build_procedural_asset/G1-G3 闸门）
**已完全关闭并备份**。根因：LLM 对 Houdini 不熟，靠提示词规则无论写多细还是会出错。

### 两件大事

**1. 关闭程序化建模（已备份，可恢复）**
- 7 个 skill + 5 个 Python 模块 + 23 个测试 → `_disabled_backup/procedural-modeling/`
- tool_executor.py 移除 4 个工具注册（build_procedural_asset/validate_recipe/rebuild_component/houdini_variant_scatter）
- harness.ts 移除 3 个 TS 工具定义
- 恢复方式：见 `python3.11libs/edini/tool_executor.py` 顶部 NOTE 注释

**2. 新建 Recipe Library（核心完成 + schema v2 + 真实验证）**
- `python3.11libs/edini/recipe_library.py`（~900 行）：**5 个工具**
  - `recipe_capture(subnet_path, ...)` — 捕获 subnet 内部网络→配方 JSON（支持 kind/tree_path/vex_snippets）
  - `recipe_capture_tree(root_path)` — **递归扫整棵分类树，自动抓所有叶子 subnet**（一次抓完用户手搭的分类树）
  - `recipe_list(query, category, kind)` — 查询索引（按关键词/分类/kind 检索，支持 tree_path 组件命中）
  - `recipe_read(recipe_id)` — 读完整配方（含 vex_snippets 代码）
  - `recipe_rebuild(recipe_id, parent_path, overrides)` — 拓扑排序重建+内置验证+还原 VEX snippet
- **配方 JSON schema v2**：nodes（相对名 inputs）/ changed_params / marked_params / exposed_parms / **kind**（network|vex）/ **tree_path**（分类面包屑）/ **vex_snippets**（wrangle 代码+runover）
- subnet Notes 强制非空作元数据（功能/重要参数/不要用于）；tree_capture 时空 Notes 自动生成
- `pi-extensions/edini-tools/tools/recipe.ts`：5 工具 TS 定义
- `skills/recipe-library/SKILL.md`：自动注册的轻量 skill（含 tree capture + 两 kind 说明）
- `tests/test_recipe_library.py`：30 测试 + 2 subtests，全绿

### 当前状态

- **35 recipe 测试全绿**（30 schema v2 + 5 新增回归：dopnet 分类层下钻、multiparm 名字归一化、scalar/list 默认值比较、ramp dict 往返、harness 死代码移除后无回归）。完整套件 **300 passed**。
- **47 个工具注册**（recipe 5 个 + 共享工具保留）
- **2 个 skill**（grill-me + recipe-library）
- **recipe_rebuild 真实 Houdini 端到端验证通过**：Base_Sweep（spiral+circle→sweep）重建成功，`verify.ok=True, mismatches=[]`。修复 4 个真实 bug：①dopnet 分类层不下钻（noise_forece 抓不到）②rebuild 用 subnet 容器致 SOP 节点创建失败（改用 geo）③multiparm 实例名 vs manifest 模板名不匹配（heightprofile2pos vs #pos）④Ramp 序列化为字符串 + scalar/list 默认值不等。
- **架构清理完成（2026-06-24）**：
  - `harness.py` 4644→**1810 行**（删 2834 行死代码：build_procedural_asset/rebuild_component/build_variant_scatter/validate_recipe_tool 整条 builder 链 + _validate_recipe/_build_*_component/_safe_create_node 等），7 个共享工具 import 不变、功能不变
  - `edini-context/index.ts` system prompt 从「强制 build_procedural_asset」改为「recipe-library 优先 + 通用几何验证」
  - `node_utils.py`/`mock_hou.py` 移除过时的 procedural-modeling-bugs.md/build_procedural_asset 引用
  - 2 个纯 vexlib 手动脚本移到 `_disabled_backup/procedural-modeling/tests/`
  - commit `ce7431b`（4 bug 修复）+ 后续清理 commit
- **配方库配方是 Houdini 本地产物**（随 .hip 存，不随 git）—— 新环境需在 Houdini 里重抓。

### 下一步该做什么

1. **给高价值配方补 Notes**（最优先，需真实 Houdini）
   - 给 Base_Sweep / noise_forece 等选中 subnet → 按 `C` 写 `功能：...` + `重要参数：...` → `recipe_capture` 重抓
   - Notes 是搜索质量的根本——auto-generated 占位文本搜索效果差

2. **验证 recipe_rebuild**（补完 Notes 后）
   - 聊天面板发「用 tube 配方重建一个」测真实重建
   - 重点验：exposed_parms override 生效、vex_snippet 还原、verify.mismatches 为空

3. **实现 Dashboard HDA**（验证后）
   - 设计文档：`docs/edini/recipe-manager-hda-design.md`
   - 阶段 1：scan_tree + create_recipe_manager（递归读 HDA 内部 subnet 树）
   - 阶段 3：Qt 树面板（recipe_tree_window.py，QTreeView）
   - 关键技术点：createDigitalAsset(save_as_locked=False) + PythonModule 调 recipe_library

## 关键文件速查（新增 Recipe Library 部分）

| 文件 | 作用 |
|------|------|
| `python3.11libs/edini/recipe_library.py` | **Recipe Library 核心**：4 工具 + 配方 schema + 拓扑排序重建 |
| `pi-extensions/edini-tools/tools/recipe.ts` | 4 recipe 工具的 TS 定义（LLM 接口） |
| `skills/recipe-library/SKILL.md` | recipe-library skill（自动注册） |
| `tests/test_recipe_library.py` | 20 测试（捕获/重建/索引/notes 校验） |
| `docs/edini/recipe-manager-hda-design.md` | Dashboard HDA 设计文档（定稿） |
| `docs/edini/recipe-library-testing.md` | 真实 Houdini 测试指南 |
| `docs/edini/recipe-library-getting-started.md` | 搭建第一个配方指南 |
| `_disabled_backup/procedural-modeling/` | 旧程序化建模完整备份（7 skill + 5 模块 + 23 测试） |

---

## 历史记录（2026-06-09 之前，保留作参考）

> 以下是架构转向前的交接记录，程序化建模部分已废弃（备份在 _disabled_backup/）。

## 第二十一阶段修复记录（Houdini 实测后修复 4 个 bug）

1. `RpcClient` 缺 `thinking_delta`/`tool_result`/`extension_info` 等 6 个信号 — Phase 20 sync 覆盖了完整版
2. `_on_change_undo`/`_redo`/`_node_requested` 3 个方法误删 — 字节替换时范围过大
3. `PROJECT_ROOT` 差一级，Pi 找不到扩展 — `config.py` 在 `python3.11libs/edini/` 时 parent.parent 是 `python3.11libs/` 而非 `edini/`
4. `config.py` 缺 `get_pi_ai_providers` 等 6 个桥接函数 — Phase 19 代码在 sync 中丢失

**经验教训**：`edini/` 和 `python3.11libs/edini/` 是两个独立的安装路径，同步时不能简单覆盖，需要双向对比确保功能完整。最好用 `diff` 对比后再合并。

## Procedural Harness Handoff (2026-06-12)

- Worktree: `E:/edini/.worktrees/procedural-harness`
- Branch: `codex/procedural-harness`
- Current HEAD: `0930850 fix(harness): sanitize output diagnostics path`
- Base plan: `docs/superpowers/plans/2026-06-11-edini-procedural-harness.md`
- Design spec: `docs/superpowers/specs/2026-06-11-edini-procedural-harness-design.md`
- Status: Phase B procedural harness is implemented, documented, and final-review approved after two JSON-safety fixes.
- Scope landed: live procedural sandbox, diagnostics before retry/delete, structural verification, commit/discard lifecycle, safe flipbook viewport capture, Pi harness tools, procedural-modeling skill guidance, and ladder regression coverage.
- Phase C path preserved: harness results include `job_id`, `execution_mode`, diagnostics bundles, JSON-safe result payloads, and artifact-shaped fields so an external worker can replace live sandbox execution later.
- Final focused verification: `python -m pytest tests/test_node_utils.py tests/test_procedural_harness.py tests/test_tool_executor_harness.py tests/test_capture_tools.py tests/test_pi_harness_tools.py -q` -> `111 passed, 743 warnings`.
- Compile/read checks passed: Python `py_compile` for harness/node_utils/tool_executor source/runtime copies, Pi TS file readability check, and source/runtime copy comparisons.
- Full-suite blocker: `python -m pytest tests -q` still has one unrelated failure, `tests/test_config.py::TestGetPiEnv::test_vision_env_not_set_when_configured`, where `VISIONIZER_PROVIDER` is `openai` but the test expects `None`.
- Diff check: the procedural harness branch does not modify `edini/config.py`, `python3.11libs/edini/config.py`, or `tests/test_config.py`; do not mix that config behavior decision into the harness commits unless explicitly choosing to resolve the blocker.
- Next continuation step: decide/fix the config test behavior, rerun full verification, then use the finishing branch workflow to choose merge, PR, keep-as-is, or discard.

## 一句话总结

Edini 是 Houdini 21 的 AI 助手：Python/PySide6 面板 → JSON-RPC 进程通信 → Pi Agent AI 后端 → 22 个 Houdini 工具。知识沉淀采用两层架构（铁律 + 知识库），对话结束后 ReflectWorker 后台反思 → KnowledgeZone 面板确认 → 自动去重合并。

## 当前能做什么

- ✅ **UI 层**：完整的 PySide6 聊天面板（流式文本、Thinking 面板、Tool Call 面板、知识确认区、Settings 双标签）· 4 层统一字号体系 (fs13/fs12/fs11/fs10) · 全局 fs() 缩放 · 零文字裁切
- ✅ **通信层**：JSON-RPC stdin/stdout 协议 (QThread 管理 Pi 子进程) · 会话 RPC
- ✅ **工具层**：22 个 Houdini 操作全部实现 (node_utils.py + HTTP 工具执行器)
- ✅ **扩展层**：Pi 扩展 (22 tools TypeBox 注册 + 铁律上下文注入 + edini_search_knowledge 知识检索)
- ✅ **知识层**：铁律 (≤20, rules.json) + 知识库 (entries.json) · AI 反思 · 用户确认
- ✅ **部署**：install.py · setup_pi.bat · settings.json 配置持久化
- ✅ **变更树**：SnapshotEngine 快照 Diff · QTreeWidget 面板（按轮次，可点击跳转 viewport）· Undo/Redo 栈（每轮一个事务，整轮撤销/恢复）· 对话中自动折叠/对话结束自动展开 · shelf tool 预设自动应用
- ✅ **测试**：Mock Hou 模块 + 156 单元测试（node_utils 48 + config 21 + knowledge_store 33 + dedup 12 + reflect_worker 9）
- ✅ **模型**：DeepSeek V3 (默认) · DeepSeek R1 (推理模式) · Anthropic Claude · 35 内置供应商自动同步

## 关键文件速查

| 文件 | 作用 | 关键点 |
|------|------|------|
| `python3.11libs/edini/config.py` | 配置中心 | `_find_pi()` 三级查找 · settings.json · env var · knowledge_enabled |
| `python3.11libs/edini/ui/main_window.py` | 主窗口 | 三栏布局 · 信号绑定 · 知识提取流程（反思→解析→确认→存储）· 轮次计时器 |
| `python3.11libs/edini/ui/agent_panel.py` | 对话面板 | QScrollArea Widget 时间线（_UserBubble / _AiBubble / _Separator / _ErrorBanner）+ Thinking 面板 + Tool Call 面板 + 知识确认区 · QLabel 流式更新 · linkActivated Copy · _pinned_to_bottom 智能滚动 · TypeToggleBadge |
| `python3.11libs/edini/rpc_client.py` | Pi 通信 | `RpcClient` → QThread → `_RpcWorker` · JSON-RPC · 会话 RPC · extension_info 信号 · CREATE_NO_WINDOW |
| `python3.11libs/edini/tool_executor.py` | 工具执行 | `HTTPServer` on daemon thread · 22 `TOOL_HANDLERS` · `/execute` + `/health` |
| `python3.11libs/edini/node_utils.py` | Houdini 操作 | 纯 houp API · create_node 含 namespace 解析 + shelf tool 预设 · 22 个 handler 函数 |
| `python3.11libs/edini/ui/snapshot_engine.py` | 场景快照 | snapshot(root) → 全节点状态 dict · diff(before, after) → 结构化变更 · restore(before, after) → 三阶段节点级回滚 · _filter_descendants 过滤内部子节点 |
| `python3.11libs/edini/ui/change_tree_widget.py` | 变更树面板 | QTreeWidget 按轮次分组 · 创建/修改/删除三级树 · 节点路径可点击跳转 viewport · 参数折叠（≤2全显/3+摘要）· 撤销/重做按钮 · 对话中自动折叠 · undo_round_requested / redo_requested / node_path_requested 信号 |
| `python3.11libs/edini/__init__.py` | 入口 | `create_panel()` / `createPanel()` |
| `python3.11libs/edini/ui/knowledge_store.py` | 知识存储 | 两层 CRUD（rules.json + entries.json）· `parse_extraction_response`（代码块提取/单引号/尾逗号修复）· `find_similar`/`merge_entry` 去重合并 · MAX_RULES=20 |
| `python3.11libs/edini/ui/knowledge_dialog.py` | 知识管理 | 双标签弹窗（铁律/知识库）· 搜索/分类筛选 · 增删改 · 启用禁用 |
| `python3.11libs/edini/ui/knowledge_zone.py` | Knowledge Zone | 右侧面板可折叠浏览 + 反思结果展示 · 条目确认/拒绝 · 合并标注 |
| `python3.11libs/edini/ui/reflect_worker.py` | 反思引擎 | QThread 后台 HTTP 调 LLM · 读 session JSONL · 去重分类 · 5 列供应商 URL |
| `python3.11libs/edini/ui/dedup.py` | 去重模块 | Jaccard 相似度（中英文字符分词）· `classify_items`（new/merge 分类） |
| `python3.11libs/edini/ui/context_panel.py` | 右侧面板 | Pi Status (含 Tools + Round 计时) · Scene · KnowledgeZone |
| `python3.11libs/edini/ui/history_panel.py` | 会话列表 | 浏览模式 · 选中高亮 · 右键删除 · 回到当前 |
| `python3.11libs/edini/ui/settings_dialog.py` | 设置 | General + Knowledge 双标签 · Provider/Model/API Key/外观 · 知识开关/统计/管理 |
| `python3.11libs/edini/ui/pi_sessions.py` | 会话读取 | 直接读 pi JSONL 文件获取会话列表和消息 |
| `pi-extensions/edini-tools/` | Pi 工具 | `index.ts` 注册 22 tools · `forwardTool()` HTTP 转发 · `edini_search_knowledge` 知识检索 |
| `pi-extensions/edini-context/index.ts` | 系统提示 | `before_agent_start` hook 注入 Houdini 上下文 + 读取 rules.json 注入铁律 |
| `scripts/install.py` | 安装 | Houdini 包注册 · MainMenuCommon.xml hconfig |
| `MainMenuCommon.xml` | 菜单 | Edini > Open Chat Panel / Settings |

## 知识沉淀系统架构

```
对话结束
  ↓ knowledge_enabled?
AI 反思（提取 prompt：只记录会重复犯的错）
  ↓
JSON 解析（代码块提取 → 单引号修复 → 尾逗号修复 → json.loads）
  ↓ 有内容
时间线底部弹出知识确认区
  · 每条显示：铁律/知识徽章（可点击切换）| 分类 | 标题 | 内容 | ✓ ✕
  · 全部接受 / 全部放弃 按钮
  ↓ 用户确认
铁律 → rules.json (≤20条，超限淘汰最旧)
知识 → entries.json (无上限)

存储路径：~/.pi/agent/edini-knowledge/
├── rules.json    ← 铁律层（每次会话注入 system prompt）
└── entries.json  ← 知识库层（细节知识，可检索）
```

## 启动命令

```bash
# 1. 安装 Pi
npm install -g @earendil-works/pi-coding-agent

# 2. 安装 Edini 到 Houdini
python scripts/install.py

# 3. 在 Houdini Python Shell
from edini import createPanel
panel = createPanel()
panel.show()

# 4. 点击 ⚙ 设置 API Key
```

## Pi 启动参数

```
pi --mode rpc \
   -e pi-extensions/edini-tools/index.ts \
   -e pi-extensions/edini-context/index.ts
```

- `--mode rpc`: JSON-RPC stdin/stdout 协议
- `-e`: 加载扩展文件
- Pi 以 `cwd=HIP目录` 启动，session JSONL 按项目归档

## 环境变量

| 变量 | 作用 |
|------|------|
| `DEEPSEEK_API_KEY` | DeepSeek API Key（Edini 自动传递） |
| `EDINI_API_KEY` | 覆盖 settings.json 中的 api_key |
| `EDINI_MODEL_PROVIDER` | 覆盖 provider 设置 |
| `EDINI_MODEL_ID` | 覆盖 model_id 设置 |
| `EDINI_TOOL_PORT` | 工具执行器端口（默认 9876） |
| `EDINI_PI_PATH` | 指定 Pi 可执行文件路径 |

## 当前限制

1. **无嵌入式 Panel** — 当前为独立浮动窗口，未注册为 Houdini Pane Tab

## 常见开发任务

### 添加新工具
1. 在 `node_utils.py` 添加 handler 函数（返回 `{success, ...}` 或 `{success:false, error:"msg"}`）
2. 在 `tool_executor.py` 的 `TOOL_HANDLERS` 注册
3. 在 `pi-extensions/edini-tools/tools/` 添加 TypeBox schema + `forwardTool()` 调用
4. 在 `index.ts` 的 `allTools` 数组注册

### 添加新的 AI Provider
1. 在 `~/.pi/agent/models.json` 添加 provider 配置
2. 更新 `settings_dialog.py` 中 PROVIDERS 列表

### 调试通信问题
1. 检查 Pi 进程是否正常启动
2. 检查工具执行器：`curl http://127.0.0.1:9876/health`
3. 查看 Pi 子进程 stderr（pipe 到父进程）
