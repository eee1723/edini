# LLM 建模纪律细化设计（Project HDA）

> **日期**：2026-07-03
> **主线**：Project HDA — 从"一次性生成器"到"长期协作伙伴"
> **前置**：组件建模地基（子系统 1）已 hython 决定性验证通过；agent 工具能力已扩展（connect_nodes output_index + set_param 向量/表达式）。
> **本轮目标**：把 agent 在 Project HDA 内建模的纪律从"散落的原则"收敛为"可执行清单 + 测试 + 工具护栏"三层。
> **范围**：基于代码接口 + 现有 hython 记录，不依赖尚未发生的 GUI agent 实测。

---

## 1. 背景与问题

Project HDA 的组件流水线范式（subnet 组件 + 端口信息点协议 + promote 参数）已在地基层验证通过。`skills/project-modeling/SKILL.md` 已引导 agent 走新流程。

但现有 SKILL 的纪律点存在三个问题：

1. **散落**：纪律分布在 "Modeling discipline"、"Common mistakes"、"Parameter LIVE references" 三处，agent 读时容易跳过细节。
2. **模糊**：部分纪律是原则性陈述（"Measure, don't hardcode"），而非可执行的 ❌/✅ 对比。
3. **缺护栏**：工具层（connect_nodes / promote_params / build_scaffold）在 agent 犯常见错误时静默执行或给出无引导的错误，agent 难以自纠。

真机 hython 记录（TestAgentToolsHython）和 GUI 验证记录暴露了 6 个高频纪律点，需要沉淀。

## 2. 设计目标

**三层落地**，每条纪律尽可能三层都覆盖：

| 层 | 形态 | 作用 |
|---|---|---|
| SKILL.md | Modeling Rules 铁律区块（❌/✅ 对比） | agent 读得到、照着做 |
| 测试 | 纪律测试（断言违反纪律 → 失败/提示） | 回归保护，防将来改工具破坏约定 |
| 工具护栏 | 引导性错误/提示（按场景混用强度） | agent 犯错时引导自纠 |

**硬约束**：
- 现有 676 测试零回归（护栏只加引导，不改成功路径逻辑，不改默认行为）。
- 护栏强度按误伤概率决定：误伤概率极低 → 硬拒绝；可能有意为之 → 软提示。

## 3. 6 个纪律点

### 纪律 1：消费锚点端必须传 `output_index=1`

**来源**：`connect_nodes`（node_utils.py:253-284）默认 `output_index=0`；hython TestAgentToolsHython 验证不传则拿主几何而非锚点。

**问题**：agent 消费上游组件锚点时漏传 output_index → 拿到主几何（空或错）→ 下游 copytopoints 0 点。

**护栏强度**：**硬拒绝**（误伤概率极低）。触发需四条同时满足：
1. from_node 是 subnet（`type().name() == "subnet"`）
2. subnet 有 ≥2 输出端（`len(outputConnectors()) >= 2`——真实 hou API，recipe_library.py:789 已验证用法）
3. `output_index == 0`（默认值，调用者没显式传）
4. to_node 是 copytopoints 且连的是模板输入（`input_index >= 1`）

普通连几何（output_index=0 连到第一输入）完全不受影响。

**错误信息**：
```
You're connecting from a multi-output subnet (chassis, 2 outputs) to the
template input of copytopoints with the DEFAULT output (geometry). If you
meant to consume ANCHOR points, pass output_index=1. (out[0]=geometry,
out[1]=anchors). See project-modeling Rule 1.
```

### 纪律 2：`set_param` 的三种值形态按场景选用

**来源**：`set_param`（node_utils.py:393-454）支持标量/向量/表达式三路径。

**问题**：agent 给 box size 传标量 `1.0`（应传向量 `[1,1,1]` 或单分量 `sizex`）；该用表达式 `ch("../length")` 时传字面值（参数不 live）。

**护栏强度**：**不加工具护栏**（工具层无法无歧义判断"该用哪种"）。纯靠 SKILL ❌/✅ 对比 + 测试断言三路径行为。仅在标量路径设成功但目标 parm 是多分量 tuple 时，result 加 hint。

**三路径契约**：
| 值形态 | 判定 | 行为 |
|---|---|---|
| 标量（number/string/bool） | 非 list/tuple | `parm.set()` + menu 强制 |
| 向量（list/tuple, len>1） | `isinstance(list/tuple) and len>1` | `parmTuple.set()`；含 ch() 分量走 setExpression |
| 表达式（含 `ch(`） | `_looks_like_expr` | `parm.setExpression()` |

### 纪律 3：promote 时机——建模完成+测试后再调用；后加 parm 需重 promote

**来源**：`promote_params`（builder.py:200-237）每次调用扫当前 spareParms；真机记录"promote 后参数面板没出现"。

**问题**：agent 过早 promote（几何还没连到 out_geometry）→ core 参数无效果；或 promote 后又加 subnet parm 不重 promote → core 缺参。

**护栏强度**：**软提示**（agent 可能有意分阶段 promote，硬拒绝会打断合法流程）。

**提示行为**：promote_params 返回结果加 `unmodeled_components` 字段（列出有 spare parm 但 out_geometry 无输入的组件），success 不变仍执行。

```
hint: "tabletop has spare parms but its out_geometry is unconnected.
Promoted parms won't have visible effect until geometry feeds out_geometry.
See project-modeling Rule 3."
```

### 纪律 4：几何必须连到 out_geometry → output_0 → core OUT

**来源**：builder.py `_ensure_core_output`（166-197）；真机高频问题"Built geometry but nothing shows at core OUT"。

**问题**：agent 在 subnet 里建了 box 但忘了 `connect_nodes(box → out_geometry)`。

**护栏强度**：**软提示**。build_scaffold 返回结果加 `components_with_unconnected_output`（列出 out_geometry null 无输入的组件），success 不变。

首次 scaffold 时所有组件都未连接（正常），hint 是信息性的；agent 建模后再调 scaffold（幂等重建）时若仍有未连接，才是真问题。

### 纪律 5：`ch()` 路径方向约定

**来源**：验证指南 project-component-foundation.md:121-127 的表格；builder promote 用 `ch("../<core_parm>")`。

**现状**：SKILL 有一行表格但没强调"站错层就反向"。

**落地**：SKILL 强化（搬进铁律区块 + 加判断口诀"站在哪一层看"）。不加工具护栏（表达式是 agent 写的字符串，工具层无法验证语义）。测试断言两层方向。

**约定**：
| 站在哪一层 | 引用方向 | 例子 |
|---|---|---|
| 组件 subnet 内部节点 → 本组件参数 | `../<parm>` | box 用 `ch("../length")` |
| core 参数 → 子组件（promote 后） | `./<component>/<parm>` | core 的 `chassis_length` 用 `ch("./chassis/length")` |

### 纪律 6：锚点必须用 `project_add_anchors` 程序化生成

**来源**：builder.py:272-369 的 add_anchors；SKILL 已有"Measure, don't hardcode"。

**现状**：SKILL 详细描述了 project_add_anchors，但"禁止手写 addpoint"还不够铁律化。

**落地**：SKILL 强化（升格为带 ❌ 的铁律）。不加工具护栏（无法在工具层检测 agent 手写 addpoint——那是 wrangle snippet 内容）。测试断言手写 addpoint 的锚点不 live（hython，缺失则 skip）。

---

## 4. SKILL.md 强化（第一层）

### 4.1 重组结构

```
# Project Modeling — components that collaborate via anchor ports
[intro 不变]

## ⚠️ Modeling Rules (iron — read before modeling)    ← 新增醒目区块
  6 条铁律，每条:一句话规则 + ❌ 错误 + ✅ 正确 + 工具调用

## The workflow (deterministic steps)    [精简——纪律已提到前面]
## When to use this                       [不变]
## Quick troubleshoot                     [原 Common mistakes，指向 Rules 编号]
## What supports / what's coming          [不变]
```

**删除的重复节**（合并进 Rules）：
- "Parameter LIVE references"（合并进 Rule 5）
- "Modeling discipline (direction)"（合并进 Rules）

### 4.2 铁律区块格式

每条铁律用 ❌/✅ 对比格式（对 LLM 最有效的教学形态）：

```markdown
### Rule 1 — Consuming anchors: pass output_index=1

A component subnet has 2+ outputs: out[0]=geometry, out[1]=anchors.
Default output_index=0 gives geometry. To consume anchors you MUST pass 1.

❌ WRONG (gets geometry, not anchors → 0 points downstream):
   houdini_connect_nodes(from=".../chassis", to=".../ctp", input_index=1)
✅ RIGHT:
   houdini_connect_nodes(from=".../chassis", to=".../ctp",
                         input_index=1, output_index=1)
```

---

## 5. 测试设计（第二层）

### 5.1 新文件：`tests/test_modeling_discipline.py`

6 个测试，分两类：

**A. 护栏行为测试（3 个）**：

| 测试 | 断言 |
|---|---|
| `test_connect_nodes_anchors_requires_output_index` | 多输出 subnet → CTP 模板输入、output_index=0 → `success:False` + error 含 "output_index" |
| `test_promote_warns_on_unmodeled_components` | subnet 有 spare parm 但 out_geometry 无输入 → 返回 `unmodeled_components` 含该组件 |
| `test_build_scaffold_reports_unconnected_outputs` | scaffold 后组件 out_geometry 无几何 → 返回 `components_with_unconnected_output` |

**B. 契约测试（3 个）**：

| 测试 | 断言 |
|---|---|
| `test_set_param_three_value_shapes` | 标量→set / 向量→parmTuple / ch(→setExpression，三路径正确 |
| `test_two_layer_ch_path_direction` | promote 后 subnet parm 表达式 = `ch("../<core_parm>")`（方向正确） |
| `test_hardcoded_anchor_not_live` | 手写 addpoint 锚点改几何不动 vs project_add_anchors live（hython，缺失 skip） |

### 5.2 mock_hou 扩展

MockNode 需加 `outputConnectors()` 方法（返回输出端列表），供护栏 1 判断多输出 subnet。真实 hou 用 `node.outputConnectors()`（recipe_library.py:789 已验证）。

实现：MockNode 已有 `_outputs` 列表（setInput 时 append），但那是"被谁连过"的列表，不等同于"输出端数"。subnet 的输出端数由内部 output 节点数决定。mock 层简化：给 MockNode 加一个可设的 `_output_connectors`（默认 `[None]` 即单输出），测试时设为 `[None, None]` 模拟多输出 subnet。

```python
class MockNode:
    def __init__(self, ...):
        ...
        # Mock of hou.Node.outputConnectors — list of output connectors.
        # Default [None] = single output (普通 SOP). Subnet 测试可设
        # [None, None] 模拟多输出端（geometry + anchors）。
        self._output_connectors = [None]

    def outputConnectors(self) -> list:
        """Mock of hou.Node.outputConnectors — output connector list.
        len() = number of output ports."""
        return list(self._output_connectors)
```

### 5.3 hython 测试优雅 skip

纪律 6（test_hardcoded_anchor_not_live）需真机 cook 验证 live，复用 `tests/test_project_hython.py` 的 `_find_hython()` 自动发现机制，缺失则 skip。

---

## 6. 工具护栏实现（第三层）

### 6.1 护栏 1（硬拒绝）：connect_nodes output_index 检查

**位置**：`python3.11libs/edini/node_utils.py` 的 `connect_nodes` 函数。

**逻辑**（在现有 setInput 调用前插入检查）：

```python
def connect_nodes(from_path, to_path, input_index=0, output_index=0):
    from_node = hou.node(from_path)
    to_node = hou.node(to_path)
    # ... existing None checks ...

    # ── Guardrail 1: multi-output subnet → CTP template input without output_index ──
    if (_looks_like_anchor_consume_mistake(from_node, to_node,
                                           input_index, output_index)):
        return {"success": False,
                "error": _anchor_output_index_error(from_node),
                "hint": "add output_index=1 to consume anchors"}

    to_node.setInput(input_index, from_node, output_index)
    # ... existing success return ...
```

**辅助函数**：

```python
_ANCHOR_CONSUMERS = {"copytopoints", "copytopoints::2.0"}

def _node_output_count(node) -> int:
    """Number of output connectors, defensive (recipe_library.py:789 pattern).
    Returns 1 on any API failure (safe default — single output is the norm)."""
    try:
        conns = getattr(node, "outputConnectors", None)
        if callable(conns):
            return len(conns())
    except Exception:
        pass
    return 1

def _looks_like_anchor_consume_mistake(from_node, to_node,
                                        input_index, output_index):
    """True when from is a multi-output subnet, output_index is default 0,
    and to is an anchor consumer's template input. Nearly always a missed
    output_index on an anchor consume."""
    if output_index != 0:
        return False
    try:
        if from_node.type().name() != "subnet":
            return False
    except Exception:
        return False
    if _node_output_count(from_node) < 2:
        return False
    try:
        to_type = to_node.type().name()
    except Exception:
        return False
    if to_type not in _ANCHOR_CONSUMERS:
        return False
    return input_index >= 1  # template input (index 1+), not geometry (0)
```

**安全性**：所有 API 调用包在 try/except 里，任何异常返回 False（不阻断）。现有 connect_nodes 的 2 参默认调用（output_index=0, input_index=0）永不触发——因为 input_index >= 1 是必要条件。`outputConnectors` 用 getattr 防御（recipe_library.py 已验证此模式），mock_hou 和真实 hou 都支持。

### 6.2 护栏 2（软提示）：promote_params 未建模检测

**位置**：`python3.11libs/edini/project/builder.py` 的 `promote_params` 函数。

**逻辑**：promote 时对每个有 spare parm 的组件，检查其 out_geometry null 有无输入连接。

```python
def _is_geometry_wired(subnet) -> bool:
    """True if the subnet's out_geometry null has at least one input
    (i.e. geometry has been built and fed into the output port)."""
    try:
        out_geo = subnet.node(OUT_GEOMETRY_NODE)
        if out_geo is None:
            return False
        return len(out_geo.inputs()) > 0
    except Exception:
        return True  # 不确定时不误报
```

promote_params 返回结果加字段：
```python
unmodeled = [cid for cid in component_ids_with_parms
             if not _is_geometry_wired(core_node.node(cid))]
result["unmodeled_components"] = unmodeled
if unmodeled:
    result["hint"] = (f"{unmodeled[0]} has spare parms but its out_geometry "
                      f"is unconnected. ... See Rule 3.")
```

success 不变（仍执行 promote），unmodeled 是信息性提示。

### 6.3 护栏 3（软提示）：build_scaffold 未连接输出报告

**位置**：`python3.11libs/edini/project/builder.py` 的 `build_project_scaffold` 函数。

**逻辑**：scaffold 建完后，复用 `_is_geometry_wired` 检查每个组件。

```python
unconnected = [cid for cid in built
               if not _is_geometry_wired(core_node.node(cid))]
result["components_with_unconnected_output"] = unconnected
if unconnected:
    result["hint"] = ("These components' out_geometry has no input yet — "
                      "geometry you build must feed into out_geometry. See Rule 4.")
```

success 不变。

### 6.4 共用 helper

`_is_geometry_wired(subnet)` 被 promote_params 和 build_scaffold 共用，放在 builder.py 模块级。

---

## 7. 不在本轮范围

- **GUI 真机验证 agent 选新流程**：需真实 Houdini GUI + Pi agent，本轮环境无法独立完成。
- **子系统 3（知识图谱描述）**：独立模块，本轮不碰。
- **子系统 4（drift 检测）**：独立模块，本轮不碰。
- **新工具能力**：不加新工具，只在现有工具加护栏。

## 8. 风险与对策

| 风险 | 对策 |
|---|---|
| 护栏 1 误伤合法的"从 subnet 取主几何到 CTP 模板输入" | 四条组合条件极苛刻（subnet + 多输出 + output_index 默认 + CTP 模板输入），误伤概率极低；且失败信息直接给修复方法 |
| mock_hou 加 outputCount 影响现有测试 | 默认值 1 保持旧行为；只有测试显式设 `_output_count=2` 才变 |
| SKILL.md 重组破坏现有引导 | intro + workflow 主体保留；只收敛重复节 + 新增铁律区块 |
| promote/build_scaffold 返回新字段被 agent 误读为错误 | 新字段在 success:True 时出现，hint 是自然语言提示，非 error |

## 9. 验收标准

1. `skills/project-modeling/SKILL.md` 有 Modeling Rules 铁律区块（6 条，❌/✅ 格式），无重复节。
2. `tests/test_modeling_discipline.py` 6 测试全过（5 mock + 1 hython skip-able）。
3. `mock_hou.py` MockNode 有 `outputConnectors()`（返回 list，默认 `[None]` 单输出）。
4. `connect_nodes` 多输出 subnet → CTP 模板输入无 output_index 时硬拒绝 + 引导信息。
5. `promote_params` 返回 `unmodeled_components`（有则加 hint）。
6. `build_project_scaffold` 返回 `components_with_unconnected_output`（有则加 hint）。
7. **现有 676 测试零回归**（5 个 PySide6 缺失失败的除外，那是环境问题）。
