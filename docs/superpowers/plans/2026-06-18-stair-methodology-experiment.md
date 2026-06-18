# 程序化建模方法论对比实验方案

> **目的**：用同一个任务（程序化楼梯）量化对比 4 种建模方法论在 LLM 驱动下的表现，
> 用数据决定 procedural-modeling skill 的路线选择。
>
> **核心问题**：当前 skill 默认走 Python SOP，导致频繁出现单面/非流形几何。用户的
> 生产实践倾向"曲线+Sweep+Copy-to-Points"。本实验回答：哪种方法论最适合 LLM 驱动？
> skill 当前是在帮忙还是在添乱？

---

## §1 实验设计原则

### 1.1 控制变量

每个条件**只改一个变量：方法论指引**。其余全部固定：

| 固定项 | 值 | 理由 |
|---|---|---|
| 任务规格 | 12 级踏步, 踏宽0.3m, 踏高0.18m, 梯段宽1.2m | 统一可比 |
| 必需参数 | `step_count`, `tread_depth`, `riser_height`, `width` | 统一参数化要求 |
| 封闭性硬指标 | nonmanifold_edges=0 且 open_boundary_edges=0 | 用户明确需求 |
| harness 工具 | 全部可用（sandbox/health/inventory/verify/capture） | 方法论中立的基础设施 |
| 重试上限 | 每条件最多 2 次重试 | 测真实成功率，非无限调试 |
| session 隔离 | 每条件独立新 session | 避免上下文污染 |

### 1.2 "关闭 skill"的精确定义

**条件 0（无 skill 基线）不加载** `skills/procedural-modeling/SKILL.md` 及其
`references/`、`scripts/`。但**保留 harness 工具**（它们是方法论中立的执行/验证能力）。

> 区分：skill = 方法论指引（要关的部分）；harness = 执行基础设施（必须保留）。
> 否则测的是"无工具的裸 LLM"，不是"无方法论的 LLM"。

### 1.3 为什么要条件 0

条件 0 回答两个诊断问题，是其他条件无法替代的：

1. **LLM 天然倾向什么方法论？** （受训练数据影响，预测：倾向 Python SOP）
2. **当前 skill 是帮是害？** 对比条件 0 与条件 A 的失败模式：
   - 失败方式相同 → skill **没帮上忙**（规则没生效）
   - 条件 0 反而更好 → skill **在添乱**（Step 1 误导）
   - 条件 0 更差 → skill **有帮助**（只是还不够）

---

## §2 实验矩阵

共 **6 次** 运行。条件 C 跑 2 次取平均（重点验证路线，排除运气）。

| 条件 | 方法论 | skill 状态 | 方法论约束 prompt | 次数 |
|---|---|---|---|---|
| **0** | LLM 自选（无引导） | **关闭** | 无 | 1 |
| **A** | 纯 Python SOP | 开（当前 skill） | 强制 createPolygon 手写 | 1 |
| **B** | 纯 VEX | 开（当前 skill） | 强制 VEX wrangle | 1 |
| **C** | 曲线+Sweep+CTP | 开（当前 skill） | 强制曲线+Sweep | **2** |
| **D** | PolyExtrude+CTP | 开（当前 skill） | 闭合曲线+PolyExtrude | 1 |

### 方法论约束的公平性说明

条件 A/B/C/D 都加载当前 skill，但 prompt 末尾追加**强制方法论约束**，覆盖 skill 的
Step 1 默认。这样测的是"该方法论被正确引导后的上限"，而非"LLM 自发选了什么"。

---

## §3 Prompt 模板（逐字复制，只替换方法论约束段）

### 3.1 基础 prompt（所有条件共用）

```
做一个程序化楼梯，规格如下：
- 12 级踏步
- 踏步深度（tread_depth）0.3m
- 踏步高度（riser_height）0.18m
- 梯段宽度（width）1.2m
- 楼梯整体走向沿 +X 方向，从原点出发逐级升高（+Y）

必须满足：
1. 暴露 4 个用户可调参数：step_count, tread_depth, riser_height, width
2. 几何必须是封闭实体（不能有单面/开口）
3. 每个踏步是一个独立的封闭几何体（component_id="step_0"..."step_11"）
4. 扶手可选，但若做也必须是封闭体

完成后用验证工具检查封闭性。
```

### 3.2 条件 0：无 skill 基线

```
[基础 prompt，不加任何方法论约束]

重要：本次任务不要读取任何 skill 文件（不要 read procedural-modeling/SKILL.md
及其 references/scripts）。直接用 harness 工具（houdini_run_python_sandbox,
houdini_inspect_geometry_health, houdini_geometry_inventory,
houdini_verify_orientation, houdini_capture_review）完成任务。
用你自己判断最合适的方法。
```

> **skill 禁用方式说明**：skill 加载由 agent harness 层按 SKILL.md 的 description
> 自动匹配触发，不受 `settings.json` 控制。可靠的禁用方式是在 prompt 里**显式指示
> 不要读 skill 文件**（如上）。即便 harness 自动把 SKILL.md 内容注入了上下文，
> 明确的"不要遵循其中的方法论指引，用你自己判断"指令也能让 LLM 忽略其引导。
>
> 验证禁用是否生效：检查 session 日志里是否有 `read procedural-modeling/...` 的
> tool call。若有，说明禁用未生效，该次运行作废重跑。
>
> 备选方案（更彻底）：临时把 `skills/procedural-modeling/SKILL.md` 的 description
> 改成不匹配建模任务的文字（如 "DO NOT MATCH"），跑完条件 0 后改回。但这会污染
> 其他条件，不推荐，除非 prompt 指示法验证无效。

### 3.3 条件 A：纯 Python SOP

```
[基础 prompt]

方法论约束（必须严格遵守）：
- 所有几何必须用 Python SOP 的 geo.createPoint() + geo.createPolygon() 手写
- 禁止使用 Sweep / PolyExtrude / PolyTube 等会自动生成面的原生 SOP
- 禁止使用 VEX wrangle 生成主要几何
- 可以用 Copy-to-Points 布置重复的踏步（但踏步本身必须是 Python 手写的封闭体）
- 参照 procedural-modeling skill 的工作流
```

### 3.4 条件 B：纯 VEX

```
[基础 prompt]

方法论约束（必须严格遵守）：
- 几何生成必须用 VEX wrangle（attribwrangle）完成
- 可以用原生 SOP 做 pre/post 处理（如 copytopoints 布置踏步）
- 禁止用 Python SOP 的 createPolygon 手写面
- 禁止用 Sweep / PolyExtrude 生成主体
- 踏步几何由 VEX 在 point/prim 级别生成
- 参照 procedural-modeling skill 的 methodology.md VEX 章节
```

### 3.5 条件 C：曲线+Sweep+Copy-to-Points（重点）

```
[基础 prompt]

方法论约束（必须严格遵守）：
- 用曲线（curve）描述踏步的截面或路径
- 用 Sweep SOP 沿路径扫掠截面生成踏步主体（封闭管状/带状体）
- 用 Copy-to-Points 将踏步实例布置到阶梯路径点上
- Python SOP/VEX 仅用于生成控制点坐标（曲线的 vertices），不直接 createPolygon
- 禁止用 Python SOP 手写踏步的面
- 参照 procedural-modeling skill，但方法论以本约束为准
```

### 3.6 条件 D：PolyExtrude+Copy-to-Points（轻量替代）

```
[基础 prompt]

方法论约束（必须严格遵守）：
- 每个踏步 = 一个闭合曲线（如矩形）+ PolyExtrude SOP 拉伸成封闭体
- 用 Copy-to-Points 将单个踏步模板布置到阶梯路径点上
- 曲线用 Python SOP 生成控制点（只生点位，不生面）
- 禁止用 Python SOP 手写踏步的面
- 参照 procedural-modeling skill，但方法论以本约束为准
```

---

## §4 量化指标（6 项，权重已定）

每个条件跑完后，填写一行。**封闭性是一票否决**。

| # | 指标 | 怎么测 | 权重 | 一票否决？ |
|---|---|---|---|---|
| 1 | **一次成功率** | 第 1 次构建是否产出几何（success=true） | 高 | 否 |
| 2 | **封闭性** | health check 的 `nonmanifold_edges` + `open_boundary_edges` | **最高** | **是（都须=0）** |
| 3 | **重试次数** | 达到可用几何用的构建次数（1=一次成功） | 高 | 否 |
| 4 | **代码量** | Python 行数 / VEX 行数 / 原生节点数 | 中 | 否 |
| 5 | **参数化程度** | 用户可调参数个数（必需 4 个，超出加分） | 中 | 否 |
| 6 | **用户可改性** | 主观：把结果给人类，5 分钟内能否改踏步数 | 中 | 否 |

### 4.1 封闭性判定细则（一票否决）

```
PASS 条件（同时满足）：
  inspect_geometry_health.summary.nonmanifold_edges == 0
  inspect_geometry_health.summary.open_boundary_edges == 0
  inspect_geometry_health.summary.degenerate_prims == 0
  inspect_geometry_health.summary.orphan_points == 0

FAIL：任一非零 → 该条件标记"封闭性不合格"，不论其他指标多好
```

> 注意：open_boundary_edges=0 是严格封闭实体的要求。楼梯踏步作为独立封闭体，每个都
> 应是闭合的（6 面体或 Sweep 封端）。这比城堡的 advisory 标准更严，因为用户明确
> 要求"尽量都要是封闭模型"。

### 4.2 代码量统计口径

- **Python SOP 方案**：所有 `hou.pwd()...geo.createXxx` 的 Python cook body 行数总和
- **VEX 方案**：所有 wrangle 的 VEX 代码行数总和
- **曲线+Sweep 方案**：曲线生成 Python 的行数 + Sweep/CTP 节点数（节点数单列）
- **统一换算**：1 个原生 SOP 节点 ≈ 3 行等价代码（便于横向比）

---

## §5 验收流程（每个条件统一执行）

严格按此顺序，**不跳步**。每步的原始返回都要存档（用于事后分析）。

```
Step 1. 构建
  - 条件 0/D: houdini_run_python_sandbox
  - 条件 A/B: houdini_run_python_sandbox 或 houdini_build_procedural_asset
  - 条件 C: houdini_build_procedural_asset (推荐) 或 network_mode
  - 记录: 构建次数、是否 success、traceback（若有）

Step 2. 几何健康（封闭性核心指标）
  houdini_inspect_geometry_health(node_path=OUT)
  - 记录 overall_ok, summary 的 6 项计数
  - 若 nonmanifold/open_boundary 非0 → 标记封闭性 FAIL

Step 3. 方向验证
  houdini_verify_orientation(node_path=OUT, checks=[
    {"component_id":"step_0", "kind":"box", "expected_axis":"X"},
    ...对几个代表踏步
  ])
  - 记录 passed/failed

Step 4. 组件清单
  houdini_geometry_inventory(node_path=OUT)
  - 记录 step_0..step_11 是否都在，prim_count 是否 > 0

Step 5. 归档截图
  houdini_capture_review(target_path=OUT, views=["perspective","top","front","right"])
  - 存档用，不用于判定

Step 6. 参数清点
  houdini_run_python: 遍历 sandbox root 的 parms，列出 name + value
  - 核对 step_count/tread_depth/riser_height/width 是否存在且可调
```

---

## §6 验收辅助脚本

把这段存为 `tests/stair_experiment_judge.py`，每个条件跑完后调用一次，自动采集 6 项指标
并输出一行 CSV。

```python
"""
楼梯实验验收脚本。在某个条件跑完后，传入其 OUT 节点路径，自动采集指标。

用法（在 Houdini Python shell 或通过 houdini_run_python）:
    import stair_experiment_judge as j
    result = j.judge("/obj/edini_sandbox_xxx/OUT", condition="C", run=1)
    print(j.to_csv_row(result))

或在命令行（通过 harness）:
    houdini_run_python(code="...import judge; judge.judge(...)...")
"""
import json

# 验收时由调用方注入这些函数（真实环境从 edini.node_utils import）
def _health(node_path): ...   # → inspect_geometry_health
def _inventory(node_path): ...# → geometry_inventory
def _list_parms(node_path): ...# → 遍历 parms

REQUIRED_PARMS = {"step_count", "tread_depth", "riser_height", "width"}

def judge(node_path, condition, run, build_attempts=1):
    """采集一个条件的全部指标。返回 dict。"""
    result = {
        "condition": condition,
        "run": run,
        "node_path": node_path,
        "build_attempts": build_attempts,
    }

    # ── 指标 2: 封闭性（一票否决）──
    health = _health(node_path)
    summary = health.get("summary", {})
    nm = summary.get("nonmanifold_edges", -1)
    ob = summary.get("open_boundary_edges", -1)
    dp = summary.get("degenerate_prims", -1)
    op = summary.get("orphan_points", -1)
    sealed = (nm == 0 and ob == 0 and dp == 0 and op == 0)
    result["nonmanifold_edges"] = nm
    result["open_boundary_edges"] = ob
    result["sealed"] = sealed  # 一票否决项

    # ── 指标 1 & 3: 成功率 & 重试次数 ──
    geo = health.get("point_count", 0)
    result["first_try_success"] = (build_attempts == 1 and geo > 0)
    result["has_geometry"] = geo > 0

    # ── 指标 5: 参数化程度 ──
    parms = _list_parms(node_path)
    parm_names = {p["name"] for p in parms}
    result["required_parms_present"] = REQUIRED_PARMS.issubset(parm_names)
    result["total_user_parms"] = len(parm_names)

    # ── 指标 4: 代码量（需调用方额外提供，无法从节点推断）──
    result["code_lines"] = None  # 手动填
    result["native_node_count"] = None  # 手动填

    # ── 组件完整性 ──
    inv = _inventory(node_path)
    comps = {c["component_id"] for c in inv.get("components", [])}
    expected_steps = {f"step_{i}" for i in range(12)}
    result["steps_present"] = len(expected_steps & comps)
    result["total_prims"] = sum(c.get("prim_count", 0) for c in inv.get("components", []))

    # ── 综合判定 ──
    result["overall_pass"] = (
        sealed and
        result["required_parms_present"] and
        result["steps_present"] == 12
    )
    return result

CSV_HEADER = "condition,run,sealed,first_try_success,build_attempts," \
             "nonmanifold_edges,open_boundary_edges," \
             "required_parms_present,total_user_parms," \
             "steps_present,total_prims,code_lines,native_node_count,overall_pass"

def to_csv_row(r):
    return ",".join(str(r.get(k, "")) for k in [
        "condition","run","sealed","first_try_success","build_attempts",
        "nonmanifold_edges","open_boundary_edges",
        "required_parms_present","total_user_parms",
        "steps_present","total_prims","code_lines","native_node_count","overall_pass"
    ])
```

---

## §7 结果记录模板

实验跑完后，填这张表。**条件 C 取 2 次的平均/最佳**。

| 条件 | sealed | first_try | build_attempts | nonmanifold | open_boundary | parms(4/?) | steps | prims | code | nodes | overall |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 无skill | | | | | | | | | | | |
| A Python | | | | | | | | | | | |
| B VEX | | | | | | | | | | | |
| C-1 Sweep | | | | | | | | | | | |
| C-2 Sweep | | | | | | | | | | | |
| D PolyExt | | | | | | | | | | | |

### 列说明
- `sealed`: true/false（一票否决）
- `first_try`: 第1次构建是否成功出几何
- `build_attempts`: 达到可用几何的总构建次数
- `parms`: 形如 `4/7`（必需4个全有/总共7个用户参数）
- `steps`: 12 个踏步组件有多少个存在（prim_count>0）
- `code`: 等价代码行数（Python行 / VEX行 / 节点数×3）
- `nodes`: 原生 SOP 节点数
- `overall`: sealed AND parms全 AND steps=12

---

## §8 决策规则（实验跑完后怎么定）

按优先级判断：

1. **若条件 C（Sweep）2 次都 overall_pass=true 且 sealed=true**：
   → **结论：曲线+Sweep+CTP 是最优路线**。
   → 行动：改写 SKILL.md Step 1，把曲线+Sweep 列为首选，Python SOP 降为"仅复杂拓扑"。

2. **若条件 C 封闭性好但一次成功率低**：
   → 结论：路线对，但 LLM 对 Sweep 的掌握不稳。
   → 行动：skill 需要更强的 Sweep 引导（更多范例、parm 速查）。

3. **若条件 0（无 skill）比条件 A（有 skill）更好**：
   → 结论：当前 skill 的 Step 1 在**主动误导**（把 LLM 推向 Python SOP）。
   → 行动：Step 1 必须重写，反转默认值。

4. **若条件 0 自发就选了 Python SOP 且失败**：
   → 结论：LLM 训练数据偏 Python SOP，skill 必须**主动对抗**这个惯性。
   → 行动：曲线+Sweep 的引导要写在 Step 1 最显眼处，并用"禁止默认用 Python SOP 造面"的强约束。

5. **若所有条件都封闭性 FAIL**：
   → 结论：LLM 当前能力下，封闭实体需要 harness 级保障（如强制 PolyExtrude/Sweep 封端）。
   → 行动：考虑在 build_procedural_asset 里加"封闭性自动后处理"（Cap SOP）。

---

## §9 执行清单（照着跑）

实验前准备：
- [ ] 确认 harness 工具全部可用（houdini_run_python_sandbox / inspect_geometry_health / geometry_inventory / verify_orientation / capture_review）
- [ ] 确认能创建独立 session（6 个，互不污染）
- [ ] 确认条件 0 的 skill 禁用方式（session 配置或显式指示）
- [ ] 把验收脚本放到 tests/stair_experiment_judge.py

逐条件执行（每条件一个新 session）：
- [ ] 条件 0：无 skill，prompt §3.2，跑完填表
- [ ] 条件 A：有 skill，prompt §3.3，跑完填表
- [ ] 条件 B：有 skill，prompt §3.4，跑完填表
- [ ] 条件 C-1：有 skill，prompt §3.5，跑完填表
- [ ] 条件 C-2：有 skill，prompt §3.5（新 session），跑完填表
- [ ] 条件 D：有 skill，prompt §3.6，跑完填表

事后分析：
- [ ] 填完 §7 结果表
- [ ] 对照 §8 决策规则得出结论
- [ ] 若结论涉及 skill 改写，记录到 docs/superpowers/plans/ 新 plan

---

## 附录：预测（待数据验证）

基于 LLM 能力分析的预判，供实验后对照：

| | 0 无skill | A Python | B VEX | C Sweep | D PolyExt |
|---|---|---|---|---|---|
| 一次成功率 | 中 | 中 | 中低 | **高** | **高** |
| 封闭性 | 差（预测自发选Python） | **差** | 中 | **优** | **优** |
| 用户可改 | 中 | 差 | 中 | **优** | 优 |

**预测结论**：C 或 D 胜出，且封闭性差距会很明显。条件 0 预测会自发选 Python SOP
（受训练数据影响），从而复现城堡的单面问题——这本身是个关键发现，说明 skill 必须
主动对抗 LLM 的 Python SOP 惯性。
