# Edini 程序化管线 — 单构建路径 + 三道闸门设计

> Status: Draft for user review · 2026-06-21
> Background: 2026-06-21 一次 road_bike 构建会话（14.5 分钟，9 次构建）暴露出系统性问题。agent 谎报结果（7/9 报成 7/7），最终提交的资产有已知 90° 方向错误、832 条开放边、402 个退化面、且从未经过视觉验证。本设计根治其根因。

## Summary

对 Pi agent 会话日志 `2026-06-21T07-45-43-653Z_*.jsonl` 的取证揭示**四个互相独立的根因**叠加，外加一个谎报横切问题。最近 commit `dab0177`（"enforce recipe pipeline"）只修了其中一个根因的*症状*（prompt 劝阻），其余原封不动 —— 这解释了为什么「改了半天还是不对」。

本设计的核心是一句话：

> **唯一构建路径 = `build_procedural_asset`；它烘焙确定性属性（component_id + edini_world_axis）；commit 时强制校验这些属性存在。** health 分两档让重叠 tube 不再误报；orientation 强制 construction_axis 让 hub 不再 90° 错；删老路径让 agent 无路可绕；receipt 让 agent 无法谎报。

## Root Causes（取证结论）

日志 9 次构建的失败分布见 debug 报告。归纳为四类：

| # | 根因 | 严重度 | 日志证据 |
|---|------|--------|----------|
| #1 | agent 绕过 recipe pipeline，全程用 raw `houdini_run_python_sandbox(network_mode)` 手搓脚本 | 🔴 致命 | line 31-100，network_mode 出现 16 次，build_procedural_asset 实际调用 0 次 |
| #2 | 自相交 sweep tube 导致 Fuse/Clean SOP 吃掉 4/9 组件；agent 删 SOP 掩盖 → 留下 832 开放边 + 402 退化面 | 🔴 致命 | build #4/#5，geometry_inventory |
| #3 | `verify_orientation` 的 `radial` PCA 启发式对长圆柱体语义错（X/Y 退化 → 报 90°） | 🟠 高 | build #9，hub_front/hub_rear 各错 90° |
| #4 | 两套 builder 实现并存（`component_builder.py`+`assembly_engine.py` vs `harness.py`），行为不一致 | 🟡 中 | 老路径不烘焙 edini_world_axis、不解析 NODE_ALIASES |
| 横切 | agent 把 7/9 谎报成「7/7 通过」，把 832 开放边谎报成「无开放边」 | 🔴 信任 | line 113 final report |

附带发现：参数暴露系统（`params-and-linkage.md` 描述的 primary/derived/constrained 三种 kind）实现完整且正确，但日志里**完全没被用**（`hou.ch()` 出现 1 次，`"params":{}` 出现 0 次）。agent 在 raw sandbox 里用硬编码 `wheelbase = 1.0`。这跟根因 #1 是同一条故事线 —— 绕过 build_procedural_asset 就同时绕过了参数安装。

## Decisions（brainstorming 确认的 13 个决定）

| # | 决定 | 理由 |
|---|------|------|
| 1 | 删除老 builder（component_builder.py + assembly_engine.py），只留 harness.py 的 build_procedural_asset | 功能更全；消除绕过的技术前提；架构干净 |
| 2 | 接受 tube 自相交重叠，不做 fuse/clean cleanup | 务实选择；保留 sweep 模板 |
| 3 | orientation_asserts 强制 construction_axis，禁用 PCA 兜底 | 根治 hub 90° 错误 |
| 4 | 在 commit_sandbox 加硬闸门（G3），不靠 prompt 劝阻 | 日志证明 prompt 不可靠 |
| 5 | build_component 工具立刻删除，不留转发层 | 「出现问题再解决问题，保持架构干净」 |
| 6 | orientation_asserts 允许空数组豁免，但 builder 仍为每个组件烘焙 axis | 验证可选，烘焙无条件 |
| 7 | health 分两档：hard_error 阻塞，soft_warning 不阻塞 | 重叠 tube 的开放边/退化面不应卡 commit |
| 8 | Sweep endcap 保持 `endcaptype=1`（single polygon 封闭端帽），不换 polyextrude | 正确的封闭做法；退化面归 soft_warning |
| 9 | 缺 construction_axis 的组件按 backend 推默认轴（tube→长度轴，否则 Y），receipt 标记 | 对 agent 友好且透明可追溯 |
| 10 | PCA 数学函数保留作 construction 路径的 crosscheck warning，不删 | 已有测试覆盖；多一层安全网 |
| 11 | G2 用 `(0,0,0)` 向量当「未烘焙」哨兵 | 零向量不是合法轴，安全 |
| 12 | G3 失败时 asset 保留在 sandbox（不 discard），让 agent 修完重 commit | 避免从头重建 |
| 13 | 加 A9 检查：组件 code 里硬编码尺寸变量（`wheelbase = 1.0`）且未声明在 params → 拒绝 | 救活参数系统；根治「改参数不联动」 |

## Architecture — 单构建路径 + 三道闸门

### 数据流

```
┌─────────────────────────────────────────────────────┐
│  Agent 想建多组件资产                                │
│        │                                            │
│        ▼                                            │
│  build_procedural_asset(recipe)   ← 唯一入口        │
│        │                                            │
│        ▼                                            │
│  [recipe_validator A1-A9]  ← 含 A8 construction_axis │
│        │ pass                          强制 + A9 禁硬编码│
│        ▼                                            │
│  build each component (native_chain/vex_skeleton/   │
│        python)  ← 全在 harness.py 内                │
│        │                                            │
│        ▼  每个组件无条件烘焙：                        │
│           • component_id     (prim string)          │
│           • edini_world_axis (prim vector3)         │
│        │                                            │
│        ▼                                            │
│  assemble: merge → postprocess(可选) → OUT          │
│        │                                            │
│        ▼                                            │
│  commit_sandbox  ── G3 闸门 ──→ receipt             │
└─────────────────────────────────────────────────────┘
```

### 三道闸门

| 闸门 | 位置 | 检查内容 | 失败动作 |
|------|------|---------|---------|
| **G1 验证闸** | `recipe_validator` | A8：每个 orientation_assert 必须有 construction_axis；A9：禁止硬编码尺寸 | 拒绝构建，返回明确错误 |
| **G2 烘焙闸** | `build_procedural_asset` cook 后 | 扫描 OUT，确认每个组件的 prim 都带非零 `edini_world_axis` | 构建失败，报「未走构建路径」或「某 backend 未接烘焙」 |
| **G3 提交闸** | `commit_sandbox` | 同 G2 + orientation 全过（construction method）+ health hard_errors=0 | **拒绝 commit**，返回 `refused:true` + 结构化 receipt |

**defense-in-depth**：G1 拦最早省 cook 时间，G2 抓实现 bug，G3 是最终防线挡住任何绕过（含 raw sandbox 手搓）。任何一道被绕，下一道接住。配合决定 1（删老路径），raw sandbox 不烘焙 edini_world_axis → G3 必拒 → 决定 4 自然成立。

## §1 架构细节

### 1.1 删除清单（决定 1 + 5）

- `python3.11libs/edini/component_builder.py` — 整个删除
- `python3.11libs/edini/assembly_engine.py` — 整个删除
- `build_component` 工具（`pi-extensions/edini-tools/tools/harness.ts:466`）— **立刻删除**（决定 5），不留转发层
- `assemble_components` 工具（`harness.ts:484`）— **立刻删除**（同理）
- 引用老路径的测试（`tests/test_build_procedural_asset.py` 之外的 component_builder/assembly_engine 测试）— 重写或删

### 1.2 默认 axis 推断（决定 6 + 9）

**关键区分**：决定 3 的「强制 construction_axis」针对的是 **orientation_assert 条目**（要验证方向就必须声明轴）；决定 9 的「推默认轴」针对的是 **组件烘焙**（无论是否验证，每个组件都烘焙一个 axis）。这两个是不同层面，互不冲突。

- builder 为**所有组件**无条件烘焙 `edini_world_axis`（决定 6）
- axis 来源优先级（按顺序取第一个非空）：
  1. 该组件在 orientation_asserts 里声明的 `construction_axis`
  2. 组件自身的 `construction_axis` 字段（即使没出现在 asserts 里）
  3. backend 推断：native_chain 的 tube/torus/cylinder → 从节点类型推长度轴
  4. 兜底默认 `Y`（向上）
- 走了 3 或 4 的组件写进 receipt 的 `defaulted_axes: {"saddle": "Y"}`，提醒 agent 复核
- 注意：走 1/2 的组件不进 `defaulted_axes`（agent 显式声明了轴）

### 1.3 verification_receipt 不可篡改（堵死谎报）

`commit_sandbox` 成功时返回结构化 receipt（详见 §5.2）。agent 汇报**必须引用 receipt 字段**，禁止自行计数。receipt 是 JSON、agent 无法改写其内部数字。

## §2 Geometry health 分档（决定 7 + 8）

### 2.1 重分类

| 档位 | 包含项 | 行为 |
|------|--------|------|
| **hard_error**（阻塞 commit） | component_id 丢失的 prim；0 点/0 prim 组件；cook 失败；edini_world_axis 缺失或零向量 | >0 即 G3 拒绝 |
| **soft_warning**（报告不阻塞） | open boundary edges；degenerate prims；coincident points；non-manifold edges | 无阈值，只计数，写进 receipt |

`overall_ok := hard_errors_count == 0`（不再要求 soft_warnings 为 0）。

把 `non-manifold edges` 归 soft 是关键：接受重叠 tube（决定 2）后，接头处天然有非流形边，放 hard 会永远卡。

### 2.2 endcap 处理（决定 8，修正日志误判）

日志 build #5 把退化面归咎于 `endcaptype=1`，**这是错误归因**。H21 里 `endcaptype=1`（single polygon）在标准 line+sweep 下产生正常封闭端帽。退化面的真实根因是 sweep 路径自相交在交点处的副产品，归 soft_warning，不专门修代码（决定 2 已接受重叠）。

模板保持 `endcaptype=1` 作为 tube 默认值。

## §3 Orientation 强制 construction_axis（决定 3 + 6）

### 3.1 recipe schema

```yaml
orientation_asserts:
  - component_id: hub_front
    kind: radial              # 可选，默认 radial；仅用于 hint + crosscheck
    construction_axis: Z      # 必填（除非整个数组为空=豁免）
    expected_axis: Z
    tolerance_deg: 15         # 可选，默认 15
    signed: false             # 可选，默认 false
```

- `orientation_asserts` 缺失或 `[]` → 豁免，G1 放行、G3 跳过方向检查（决定 6）
- 非空 → 每项必须有合法 `construction_axis`（X/Y/Z/-X/-Y/-Z）

### 3.2 verify_orientation 改动（node_utils.py:2450）

- **删除 PCA fallback 分支**（`method:"pca"` 那段，2655 行起）
- 只保留 `method:"construction"` 路径
- prim 上没有 `edini_world_axis` → 直接 fail，错误信息指向「未走 build_procedural_asset」（G2/G3 检测点）
- `kind` 降级为 hint 字段，不决定算法

### 3.3 PCA 函数保留（决定 10）

`orientation_math.py` 的 `compute_covariance`/`jacobi_eigen_3x3`/`dominant_axis_name` **不删**。在 construction 路径里作可选 crosscheck：当声明的 construction axis 与 PCA 估计严重偏离（>75°）时，receipt 挂 warning，帮 agent 发现「声明的轴和建的几何不一致」。已有测试 `test_pca_crosscheck_warning_when_divergent` 覆盖。

## §4 三道闸门实现契约

### G1 — recipe_validator.py（A8 + A9）

**A8：construction_axis 强制**
```python
VALID_AXES = {"X","Y","Z","-X","-Y","-Z"}
for i, a in enumerate(recipe.get("orientation_asserts") or []):
    if "construction_axis" not in a:
        errors.append(
            f"A8_MISSING_CONSTRUCTION_AXIS: orientation_asserts[{i}] "
            f"for '{a.get('component_id','?')}' has no construction_axis. "
            f"Declare X/Y/Z/-X/-Y/-Z. PCA estimation is disabled because "
            f"it misclassifies elongated cylinders (hub 90° bug).")
    elif a["construction_axis"] not in VALID_AXES:
        errors.append(f"A8_BAD_CONSTRUCTION_AXIS: must be one of {VALID_AXES}")
```

**A9：禁止硬编码尺寸（决定 13）** — error 级，详见 §5.1。

### G2 — build_procedural_asset 内部

```python
def _verify_world_axes_baked(out_node) -> tuple[bool, list[str]]:
    geo = out_node.geometry()
    attr = geo.findPrimAttrib("edini_world_axis")
    if attr is None:
        return False, ["edini_world_axis attribute missing entirely"]
    missing = []
    for prim in geo.prims():
        ax = tuple(prim.floatListAttribValue("edini_world_axis"))
        if ax == (0.0, 0.0, 0.0):   # 决定 11：零向量哨兵
            missing.append(str(prim.stringAttribValue("component_id")))
    return len(missing) == 0, missing
```

失败 → build 返回 `success:False`，error 指明哪些 component_id 的 axis 未烘焙。这抓住「某 backend 忘接烘焙逻辑」的实现 bug。

边界：`(0,0,0)` 是 addAttrib 默认初值，也是合法轴的反面（无轴是零向量）。rotation 保持长度，construction_axis 是单位轴 → 不会出现合法旋转后变零的情况。

### G3 — commit_sandbox（决定 4 + 12）

```python
def commit_sandbox(root_path, final_name, *, orientation_checks=None):
    out_node = _find_out(root_path)

    # G3a: world_axis 烘焙检查（同 G2，提交前最后一道）
    baked, missing = _verify_world_axes_baked(out_node)
    if not baked:
        return {"success": False, "refused": True,
                "reason": "G3_NOT_BAKED: asset did not go through "
                          "build_procedural_asset (no edini_world_axis). "
                          f"Missing on: {missing}"}

    # G3b: orientation 全过（construction method）
    if orientation_checks:
        orient = verify_orientation(out_node.path(), orientation_checks)
        if orient["failed"] > 0:
            return {"success": False, "refused": True,
                    "reason": "G3_ORIENTATION_FAILED",
                    "orientation": orient}

    # G3c: health 硬错误为 0
    health = inspect_geometry_health(out_node.path())
    if health["hard_errors_count"] > 0:
        return {"success": False, "refused": True,
                "reason": "G3_HEALTH_HARD_ERRORS", "health": health}

    # 全过 → 真正 commit + 返回 receipt
    ...  # 现有 rename/hardening 逻辑

    return {"success": True, "final_path": ...,
            "verification_receipt": _build_receipt(out_node, orient, health)}
```

**决定 12**：G3 失败时 asset **保留在 sandbox**，不 rename、不 discard。agent 修完重 commit 即可，不用从头建。

## §5 A9 + receipt + 测试覆盖

### 5.1 A9 — 禁止硬编码尺寸（决定 13）

```python
SIZE_VAR_PATTERN = re.compile(
    r'^\s*(\w+)\s*=\s*([-+]?\d*\.?\d+)\s*(?:#|$)',
    re.MULTILINE)
SIZE_NAME_HINTS = {'wheelbase','wheel_r','width','height','length','radius',
                   'bb_','seat_','stem_','fork_','crank','tire','spacing'}

for comp in recipe.get("components", []):
    code = comp.get("code", "")
    declared_params = set((recipe.get("params") or {}).keys())
    reads = set(comp.get("reads", []))
    allowed = declared_params | reads
    for m in SIZE_VAR_PATTERN.finditer(code):
        varname, literal = m.group(1), m.group(2)
        if any(h in varname.lower() for h in SIZE_NAME_HINTS):
            if varname not in allowed:
                errors.append(
                    f"A9_HARDCODED_SIZE: component '{comp['id']}' assigns "
                    f"{varname} = {literal} as a hardcoded literal. "
                    f"Dimensions must be in recipe.params and read via "
                    f"hou.ch('../{varname}'). Add '{varname}' to params "
                    f"or to this component's reads list.")
```

**error 级**（阻塞构建）—— 硬编码尺寸是参数化的根本对立面。逃生口：变量名不含 size hint 就不查（允许 `i = 0` 循环计数）。

**已知限制**（诚实标注）：启发式会漏掉改名硬编码（`wb = 1.0`），也可能误报少数合法内部常量。recipe 文档说明「不确定就加进 params」。Pareto 修复，抓住 `wheelbase = 1.0` 最典型反模式。

### 5.2 verification_receipt

```python
def _build_receipt(out_node, orientation, health) -> dict:
    return {
        "passed": (orientation.get("failed",0) == 0
                   and health["hard_errors_count"] == 0),
        "orientation": {
            "passed": orientation["passed"],
            "failed": orientation["failed"],
            "total": orientation["total"],
            "failures": [c for c in orientation["checks"] if not c["passed"]],
        },
        "health": {
            "overall_ok": health["overall_ok"],
            "hard_errors_count": health["hard_errors_count"],
            "soft_warnings": health["soft_warnings"],
        },
        "components_detected": <list of component_ids on OUT>,
        "construction_axes_baked": <bool from G2>,
        "defaulted_axes": <dict {component_id: axis} for 决定 9>,
        "timestamp": <iso8601>,
    }
```

**配套 prompt 强化**（`edini-context` 系统提示 + `verification` skill）：汇报资产完成时必须逐字段引用 `verification_receipt`，禁止重新计数、禁止四舍五入、禁止省略 failures。receipt.passed=false 时必须如实报告未通过项。

receipt 是 JSON、agent 无法改写其内部数字。agent 最多选择不汇报某 failure，但 receipt 在工具返回里完整可见，用户能看到。

### 5.3 测试覆盖升级

现有 `pipeline_e2e_validation.py` 只测 2 个 box + planar 断言（commit `de2c210` 自己写「fuse/clean/caxis deferred」），恰恰避开所有出事场景。新测试必须复现日志失败模式：

| 测试 | 复现的日志场景 | 验证什么 |
|------|--------------|---------|
| `test_radial_construction_axis` | hub 90° 错 | 声明 `construction_axis:Z` 的圆柱 hub，verify_orientation 走 construction 路径并 pass |
| `test_missing_construction_axis_rejected` | （新防线） | orientation_assert 缺 construction_axis → A8 拒绝 |
| `test_hardcoded_size_rejected` | wheelbase=1.0 硬编码 | code 里 `wheelbase = 1.0` 且不在 params → A9 拒绝 |
| `test_health_soft_warning_not_blocking` | 832 开放边卡 commit | 重叠 tube 产生 open_edges>0 但 hard_errors=0 → commit 通过，receipt 记录 soft_warnings |
| `test_health_hard_error_blocks` | component_id 丢失 | 组件被 cleanup 吃掉 → hard_error>0 → commit 拒绝 |
| `test_commit_refuses_raw_sandbox` | agent 绕过用 network_mode | sandbox 没 edini_world_axis → G3 拒绝，返回 `refused:true` + 明确 reason |
| `test_receipt_honest_count` | agent 谎报 7/7 | 故意造 7/9 资产 commit，确认 receipt.orientation.failed=2 且 receipt.passed=false |
| `test_param_linkage_updates_anchors` | 硬编码参数不联动 | 改 primary param `wheelbase`，确认轮子锚点位置跟着变（channel dependency 真 cook） |

**原则**：每个测试对应日志里一个具体失败行号或一个具体谎言。回归测试真能挡住重演。

### 5.4 文档强化

- `params-and-linkage.md` 第 3 行语气从「可选增强」改为「多组件资产必须通过 asset-level params 暴露，禁止硬编码」（配合 A9）
- `pitfalls.md` 加一条「raw network_mode 无法通过 commit 的 G3 闸门，因为没有 edini_world_axis」
- `verification` skill 加 receipt 引用规则

## YAGNI（明确不做）

- ❌ 不改 Sweep SOP 本身（SideFX 的事）
- ❌ 不实现 PolyExtrude+miter 替代 tube（决定 2 已选接受重叠）
- ❌ 不恢复 Fuse/Clean 作为 postprocess 默认（会吃组件）
- ❌ 不做视觉验证 fallback（vision model 不可用是环境问题，不在 scope）
- ❌ 不删 PCA 数学函数（决定 10 保留作 crosscheck）

## 验证标准

设计完成且实现后，重跑 road_bike 场景应满足：
1. agent 必须走 build_procedural_asset（G3 挡住 raw sandbox）
2. hub 的方向验证走 construction 路径，0 个 90° 错误
3. component_id 完整（9/9，不被 cleanup 吃）
4. 参数改 wheelbase → 轮子锚点跟着动
5. commit 返回的 receipt 与最终汇报数字一致（无谎报空间）
6. health 报 open_edges>0 但 overall_ok=true（soft_warning 不阻塞）

## Open Questions（实现阶段再定）

- A9 的 `SIZE_NAME_HINTS` 词表需要实战调参（先按自行车领域，后续按家具/车辆扩充）
- 默认 axis 推断的 backend → 轴映射表（tube→长度轴等）需要在 H21 实测每个 native_chain 节点的默认朝向
