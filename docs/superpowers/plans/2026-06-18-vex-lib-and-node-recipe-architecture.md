# 程序化建模架构演进计划：VEX 骨架库 + 节点 Recipe + 布局层

> **状态**：计划（未实施）
> **日期**：2026-06-18
> **依据**：5 个楼梯实验 session + VEX 能力调研 + harness/recipe 源码分析
> **目标**：把方法论默认值从"Python SOP 手写几何"转向"VEX 骨架 + 节点成形 + Copy 布局"，消灭单面问题这一整类失败，让 edini 专注布局与参数关联。

---

## 〇、问题陈述与设计原则

### 当前架构的根本矛盾

实验数据证明了一件事：**让 LLM 用 Python SOP（或 VEX）手写 `createPolygon`/`addprim` 来构造封闭几何体，是一个系统性失败的策略**，因为封闭性取决于"每个面的 winding 都正确"——这是每个新形状都要重新推导的几何数学，LLM 不可靠（实验中 nm=48 的单面问题反复出现）。

当前 skill 的 `declarative-builder.md` 把每个 component 的 `code` 字段硬绑到 **Python SOP cook body**（`harness.py:2238` `_safe_create_node(root_path, "python", py_name)`），并把 `attribwrangle` 归类为后处理节点（`_POSTPROCESS_NODE_TYPES`，`harness.py:551`）。这两点共同把 LLM 推向"Python SOP 手写几何"的默认路径。

### 三条设计原则（贯穿整个计划）

1. **分层职责，而非 VEX 包打一切**：
   - VEX/Python 只生成**骨架**（点序列、polyline、闭合轮廓、点属性）
   - 封闭性由**原生节点**保证（Sweep `endcaptype`、PolyExtrude `output_back`、Cap）
   - LLM 调用**预制函数**而非手写脚手架代码
   - 组件由 **Copy-to-Points 实例化**，可独立替换

2. **不破坏现有 recipe/builder**：向后兼容，新增 `backend` 字段而非替换 `code`。旧 recipe 继续工作。

3. **确定性优先**：每个函数库函数都是测试过的、有明确输入输出的"积木"。LLM 调积木，不现场烧砖。

---

## 一、目标架构（三层）

```
┌──────────────────────────────────────────────────────────┐
│ 第3层 · 布局与关联层（edini 主战场）                          │
│   - Copy-to-Points 实例布局 + @orient/@scale/@component_id │
│   - 参数关联（父参数 ch() 驱动子参数）                         │
│   - 组件装配（整体设计 > 单组件精度）                          │
│   - 这是 builder 的 anchors + copytopoints，已存在，要增强    │
├──────────────────────────────────────────────────────────┤
│ 第2层 · 节点 Recipe 模板层（消灭 Sweep/CTP 探索成本）          │
│   - sweep_tube(path, section) → 封闭管体                    │
│   - extrude_solid(profile, depth) → 封闭挤出体              │
│   - copy_layout(template, anchors) → 实例布局               │
│   - 作为 recipe 的 postprocess/节点链模板，预置参数            │
├──────────────────────────────────────────────────────────┤
│ 第1层 · VEX/Python 骨架函数库（消灭重复脚手架代码）             │
│   - vexlib.vfl：make_polyline/make_helix/make_grid/...     │
│   - 属性写入器：set_orient/set_scale/set_component_id       │
│   - 截面生成器：make_rect_section/make_circle_section       │
│   - 全部 Run Over=Detail，全部参数化(ch() 相对路径)          │
└──────────────────────────────────────────────────────────┘
```

**依赖关系**：第1层喂第2层，第2层喂第3层。三层可独立开发、独立测试。

---

## 二、旧策略清单（需要清理/降级的内容）

> 这些不是删除，而是**从"默认推荐"降为"特定场景备选"**。保留向后兼容。

### 2.1 skill 文档层（SKILL.md + references/）

| 位置 | 当前内容 | 问题 | 处理方式 |
|---|---|---|---|
| `SKILL.md` Step 1 | 把 Python SOP 列为"复杂形状"首选 | 与新方向冲突，误导 LLM | **改写**：默认推"VEX 骨架 + 节点成形"，Python SOP 降为"无法用节点表达时"的兜底 |
| `declarative-builder.md:72` "Component code rules" | 强制 `code` 是 Python SOP cook body | 把 VEX 排除在外 | **扩展**：`code` 改为 backend-aware（见 §3.2） |
| `methodology.md:12` "Orientation VEX recipe" | 给了 tangent/orient 计算 | 是对的，保留 | 保留，但纳入函数库 `set_orient_from_tangent()` |
| `methodology.md:29-45` "VEX Guidelines" | "VEX generated from scratch fails 64%" + "2次失败切Python" | 基于旧认知（LLM 手写 VEX 时代） | **改写**：函数库时代 VEX 失败率应大幅下降；"2次失败切Python"改为"换函数库里的另一个函数" |
| `python-sop-template.py` | 整个文件是 Python SOP 范例 | 与新方向弱相关 | **保留但降权**：移到 references/ 深层，主路由不再引用。补充 vexlib 范例 |
| `recipe-template.md:24-30` | ORIENTATION ASSERTS 全是 wheel(radial) | 导致 radial 误判（Bug 6） | **补示例**：加细长旋转体用 elongated 的示例 |

### 2.2 harness 代码层（python3.11libs/edini/）

| 位置 | 当前行为 | 问题 | 处理方式 |
|---|---|---|---|
| `harness.py:551` `_POSTPROCESS_NODE_TYPES` 含 `attribwrangle` | VEX 生成器不计入模块化 | 打压 VEX 路线 | **拆分**：引入"生成型 wrangle"判定——如果 wrangle 含 `addpoint`/`addprim` 则算 MODULAR，否则算 POSTPROCESS |
| `harness.py:2238` component code 硬绑 `python` SOP | recipe 只支持 Python | VEX 无法走 recipe | **扩展**：component 加 `backend` 字段（见 §3.2） |
| `harness.py:1975` `_direct_component_world_axis_snippet` 是 Python | world_axis 标记只在 Python 注入 | VEX 组件拿不到确定性方向 | **扩展**：提供 VEX 版 world_axis snippet |
| `harness.py:109` `geometry_stats` 对 ObjNode 崩溃 | Bug 7 | 诊断二次失败 | **修**（独立 Bug，不阻塞本计划） |
| `orientation_math.py:23` radial rank=0 误判 | Bug 6 | 细长圆柱误判 | **修**（独立 Bug，不阻塞本计划） |

### 2.3 旧 Bug（不阻塞本计划，但建议同期修）

| Bug | 影响 | 是否阻塞 |
|---|---|---|
| Bug 6 radial PCA 误判 | 方向验证误报 | 否（新路线鼓励 construction_axis，绕开 PCA） |
| Bug 7 geometry_stats ObjNode | 诊断崩 | 否 |
| Bug 8 参数 drift 无标记 | 信任问题 | 否，但建议同期做 |
| Bug 11 FloatParmTemplate | Python 路线特有 | **新路线会自然减少**（VEX 不需要 FloatParmTemplate） |

---

## 三、新策略详细设计

### 3.1 第1层：VEX 骨架函数库

#### 3.1.1 文件组织

```
skills/procedural-modeling/
├── scripts/
│   ├── vexlib/                          ← 新增
│   │   ├── README.md                    # 函数目录（给 LLM 查）
│   │   ├── skeleton.vfl                 # 骨架生成函数（polyline/helix/grid/path）
│   │   ├── sections.vfl                 # 截面生成函数（rect/circle/polygon）
│   │   └── attribs.vfl                  # 属性写入函数（orient/scale/component_id）
│   └── vexlib-usage.md                  ← 新增：每个函数的用法 + 配套节点 recipe
```

#### 3.1.2 函数清单（基于实验重复模式定稿）

**骨架生成（全部 Run Over: Detail）**

| 函数 | 签名 | 产出 | 实验证据 |
|---|---|---|---|
| `make_polyline` | `(geohandle; positions[]) → point_ids[]` | 开放 polyline | 条件B/C 都在手写 |
| `make_closed_polyline` | `(geohandle; positions[]) → point_ids[]` | 闭合 polyline（给 PolyExtrude） | 条件C 踏步轮廓 |
| `make_helix` | `(geohandle; n; r; height; turns) → point_ids[]` | 螺旋路径 | 楼梯路径候选 |
| `make_stair_path` | `(geohandle; n; tread; riser) → point_ids[]` | 阶梯路径点 + @curve_u | 楼梯实验直接场景 |
| `make_grid` | `(geohandle; rows; cols; spacing) → point_ids[]` | 网格阵列点 | 城堡城墙阵列 |

**截面生成（全部 Run Over: Detail，产出闭合 polyline）**

| 函数 | 签名 | 产出 | 用途 |
|---|---|---|---|
| `make_rect_section` | `(geohandle; w; h) → point_ids[]` | 矩形闭合轮廓 | PolyExtrude 拉伸成梁/板 |
| `make_circle_section` | `(geohandle; r; sides) → point_ids[]` | 正多边形闭合轮廓 | Sweep 成管/塔 |
| `make_tapered_section` | `(geohandle; r0; r1; sides) → point_ids[]` | 锥台轮廓 | 变截面（塔顶） |

**属性写入（Run Over: Point 或 Detail）**

| 函数 | 签名 | 说明 |
|---|---|---|
| `set_orient_from_tangent` | `(geohandle; pts[]; up) ` | 切线→orient 四元数（methodology.md:12 的封装） |
| `set_component_id_by_group` | `(geohandle; group; cid)` | 按组批量设 component_id |
| `set_component_id_by_centroid` | `(geohandle; cid; x_min; x_max)` | 按质心范围设 id（楼梯步阶） |
| `set_scale_along_curve` | `(geohandle; pts[]; scales[])` | 沿曲线变缩放 |

#### 3.1.3 关键约束（写入 README.md）

```
vexlib 铁律：
1. 所有骨架/截面生成函数必须 Run Over: Detail（否则 addpoint 会让几何成倍复制）
2. 所有函数用 ch() 相对路径读参数（可移植到 HDA/子网）
3. 函数只产出"骨架"（点/线/属性），绝不产出封闭体——封闭性交给下游节点
4. 每个 make_* 函数返回 point_ids 数组，方便后续 addvertex 串线或 Copy 用
```

#### 3.1.4 配套节点 recipe（vexlib-usage.md 里每个函数都配）

每个函数的文档页结构：
```markdown
## make_circle_section(geohandle; r; sides)

产出：闭合正多边形 polyline（给 Sweep 当截面）

用法（配合 Sweep 造管）：
  1. 第一个 wrangle: make_circle_section(0, chf("r"), chi("sides"))  → 闭合轮廓
  2. 第二个 wrangle: make_polyline(0, <路径点>)  → 路径（或 make_helix）
  3. sweep::2.0: input0=路径, input1=截面, endcaptype=single  → 封闭管体

常见错误：
  - Run Over 不是 Detail → 几何成倍复制
  - Sweep 输入顺序反了 → 截面变成路径
```

---

### 3.2 第2层：recipe backend 扩展（让 VEX + 节点链走 builder）

#### 3.2.1 component schema 扩展（向后兼容）

当前：
```jsonc
{"id": "wheel", "code": "<python cook body>", "anchors": [...]}
```

扩展后（`backend` 字段可选，默认 `python` 保持兼容）：
```jsonc
{
  "id": "tower",
  "backend": "vex_skeleton",          // 新增：见下表
  "code": "make_circle_section(0, chf('r'), chi('sides'))",  // VEX detail snippet
  "form_node": {                       // 新增：下游成形节点
    "type": "sweep::2.0",
    "input0": "path_component_id",     // 引用另一个 component 的输出
    "input1": "self",                  // 自己的 code 输出
    "params": {"endcaptype": "single", "surface": "rowscols"}
  },
  "anchors": [...]
}
```

**backend 类型表**：

| backend | code 执行方式 | 成形节点 | 适用场景 |
|---|---|---|---|
| `python`（默认，向后兼容） | Python SOP cook body | 无（code 自己造面） | 现有 recipe 不变 |
| `vex_skeleton` | VEX detail snippet（`#include vexlib`） | 必须配 `form_node` | 几何由 Sweep/PolyExtrude 成形 |
| `native_chain` | 无 code | 整条节点链在 `nodes` 里 | 纯节点组合（多个 PolyExtrude + Boolean） |

#### 3.2.2 form_node 处理逻辑（harness 改动）

`build_procedural_asset` 在 `_safe_create_node(root_path, "python", ...)` 处分支：

```python
backend = comp.get("backend", "python")
if backend == "python":
    py_sop = _safe_create_node(root_path, "python", py_name)
    _set_parm_safe(py_sop, "python", code)
elif backend == "vex_skeleton":
    wrangle = _safe_create_node(root_path, "attribwrangle", py_name)
    wrangle.parm("class").set(0)  # Detail
    vex_code = "#include <vexlib/skeleton.vfl>\n" + code
    wrangle.parm("snippet").set(vex_code)
    # 接 form_node
    form = comp.get("form_node")
    if form:
        form_sop = _safe_create_node(root_path, form["type"], f"{cid}_form")
        # input1 = 自己 wrangle 输出
        form_sop.setInput(1, wrangle)
        # input0 = 引用的 path component 输出
        if form.get("input0") and form["input0"] != "self":
            path_node = built_components[form["input0"]]
            form_sop.setInput(0, path_node)
        for pname, pval in form.get("params", {}).items():
            _set_parm_safe(form_sop, pname, pval)
        # form_sop 替代 py_sop 作为后续 copytopoints 的输入
        component_output = form_sop
    else:
        component_output = wrangle
```

#### 3.2.3 world_axis 确定性标记的 VEX 版

当前 `_direct_component_world_axis_snippet` 是 Python（`harness.py:1975`）。需要 VEX 等价物：

```vex
// _vex_world_axis_snippet(world_axis)
// 附加到 vex_skeleton code 末尾，每个 prim 写 edini_world_axis
addattrib(0, "prim", "edini_world_axis", {0,0,0});
// 在 detail 模式遍历所有 prim 写值
```

这保证 VEX 组件也能走确定性方向验证（绕开 PCA + Bug 6）。

---

### 3.3 第3层：布局与参数关联（增强现有 anchors）

这一层**大部分已存在**（builder 的 anchors + copytopoints），需要增强的：

#### 3.3.1 anchor 属性扩展

当前 anchor 只有 `position_expr`/`orient`/`pscale`/`component_id`。扩展：

```jsonc
{
  "position_expr": [...],
  "orient": [...],
  "pscale": 1.0,
  "scale3": [1.0, 1.2, 1.0],       // 新增：非均匀缩放（变截面）
  "component_id": "tower_fl",
  "variant": 0,                     // 新增：变体索引（接 variant_scatter）
  "user_attrs": {"roof_type": "conical"}  // 新增：透传自定义属性
}
```

#### 3.3.2 参数关联公式增强

当前 `position_expr` 支持 `"wheelbase/2"` 这种参数引用。扩展支持简单表达式：

```
"position_expr": ["ch('wheelbase')/2", "ch('wheel_r')", "-0.55"]
// 或带函数
"position_expr": ["ch('step_count')*ch('tread_depth')", "0", "0"]
```

---

## 四、实施阶段（分 4 期，每期可独立交付）

### 第 1 期：VEX 函数库 MVP（纯增量，零风险）

**目标**：函数库文件 + skill 文档引用，不改 harness。

| 任务 | 产出 | 风险 |
|---|---|---|
| 写 `vexlib/skeleton.vfl`（5 个函数） | make_polyline/make_closed_polyline/make_helix/make_stair_path/make_grid | 零（纯新增文件） |
| 写 `vexlib/sections.vfl`（3 个函数） | make_rect_section/make_circle_section/make_tapered_section | 零 |
| 写 `vexlib/attribs.vfl`（4 个函数） | set_orient_from_tangent/set_component_id_by_*/set_scale_along_curve | 零 |
| 写 `vexlib/README.md`（函数目录） | 每个 函数签名+用途+配套节点 | 零 |
| 写 `vexlib-usage.md`（recipe 范例） | 每个函数的 Sweep/PolyExtrude/CTP 配套用法 | 零 |
| 写手动测试脚本 | 每个函数单独跑，验封闭性 | 零 |
| SKILL.md 主路由加 vexlib 引用 | Step 1 提到函数库作为首选 | 低（措辞调整） |

**验收**：用一个新 session 跑楼梯任务，prompt 指引用 vexlib，看是否比条件C 的 91 事件更快。

### 第 2 期：recipe backend 扩展（改 harness，中风险）

**目标**：让 VEX + Sweep 走 builder recipe。

| 任务 | 产出 | 风险 |
|---|---|---|
| harness: component 加 `backend` 字段解析 | `build_procedural_asset` 分支 python/vex_skeleton | 中（改核心函数） |
| harness: `form_node` 处理 | Sweep/PolyExtrude 自动接线 | 中 |
| harness: VEX world_axis snippet | 确定性方向标记 | 中 |
| harness: `_POSTPROCESS` 拆分 | 生成型 wrangle 算 MODULAR | 低 |
| recipe schema 文档更新 | declarative-builder.md 补 backend 说明 | 低 |
| 回归测试 | 现有 Python recipe 仍正常工作 | 必须做 |

**验收**：用 recipe backend=vex_skeleton + form_node=sweep 重做楼梯，对比条件C。

**风险缓解**：先加 backend 字段但默认 python，feature flag 控制。灰度。

### 第 3 期：旧策略清理（改 skill 文档，低风险）

**目标**：把 Python SOP 从首选降为兜底。

| 任务 | 产出 |
|---|---|
| SKILL.md Step 1 重写 | 默认推 VEX骨架+节点成形，Python SOP 降为"无法节点化时" |
| methodology.md VEX 章节改写 | 删"64%失败率"旧认知，换函数库时代的表述 |
| python-sop-template.py 降权 | 移到深层 reference，主路由不引用 |
| recipe-template.md 补示例 | 加 vex_skeleton backend 的完整 recipe 范例 |
| 加"封闭性靠节点不靠手写"的铁律 | SKILL.md Iron Rule |

**验收**：新 session 跑城堡任务，看是否默认走 VEX+节点路线。

### 第 4 期：增强与修复（独立改进）

| 任务 | 说明 |
|---|---|
| anchor scale3/variant/user_attrs 扩展 | 第3层布局增强 |
| 修 Bug 6（radial PCA 退化检测） | 独立改进 |
| 修 Bug 7（geometry_stats ObjNode） | 独立改进 |
| 修 Bug 8（参数 drift 标记） | 独立改进 |
| houdini_install_params 工具 | 消灭 FloatParmTemplate 错误 |

---

## 五、向后兼容性保证

### 5.1 recipe 兼容

- 现有 recipe（`backend` 字段缺失）→ 默认 `python`，行为完全不变
- `form_node` 字段缺失 → 行为同当前（code 自己造面）
- 新字段（backend/form_node）只在显式声明时生效

### 5.2 skill 文档兼容

- `python-sop-template.py` 不删除，只是不再被主路由引用
- methodology.md 的 Python SOP 内容保留，移到"特定场景"章节
- 现有 recipe 范例（wheel/vehicle）继续有效

### 5.3 harness 兼容

- `_validate_recipe` 对新字段做**宽松校验**（backend 不在白名单→警告，不报错）
- `build_procedural_asset` 的现有 Python 路径**一个字不改**
- 新增分支用 feature flag（`settings.json` 里 `vex_backend_enabled`）控制，可随时关

---

## 六、风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| VEX `#include` 在 attribwrangle 里不工作 | 中 | 函数库不可用 | 第1期先验证 include 机制；不行则改用"snippet 拼接"（把函数体内联到 code 里） |
| LLM 不会调函数库，还是手写 | 中 | ROI 不达预期 | SKILL.md 强引导 + 函数目录易查；测 2 个新 session 看采用率 |
| recipe backend 改动破坏现有 Python recipe | 低 | 回归失败 | feature flag + 回归测试（第2期必须带） |
| VEX 编译缓存腐败（条件B 的坑） | 中 | 偶发失败 | 函数库代码是预制的、测试过的，比 LLM 现场写稳定得多 |
| form_node 的 input0 跨 component 引用复杂 | 中 | 接线错误 | 第2期先只支持 self 路径（input0=self），跨引用放第4期 |

---

## 七、验收标准（整体）

计划全部实施后，用楼梯任务验收（与实验同规格）：

| 指标 | 实验基线（条件C） | 目标 |
|---|---|---|
| 总事件数 | 91 | < 50 |
| python 执行次数 | 20 | < 8 |
| 封闭性（nm/ob） | 0/0 ✓ | 0/0 ✓（保持） |
| 一次成功 | 否（多次重试） | 是（首次或 1 次重试） |
| component_id 全到位 | 是 | 是（保持） |
| LLM 手写 addpoint 次数 | 67 | < 5（改调函数库） |

**终极验收**：城堡任务（22 组件），看是否默认走 VEX+节点路线，且封闭性优于城堡日志的 787 非流形边。

---

## 八、决策依据摘要（给 review 用）

1. **为什么 VEX 函数库而非 Python**：实验中 VEX 路线（条件B）封闭性 PASS，且 addpoint/addvertex 重复 157/70 次——这是函数库的明确需求信号。VEX 速度快、detail 模式可靠、ch() 自动生参数。

2. **为什么函数库只做骨架不做封闭体**：VEX 没有"封端"算子（调研确认）。让 VEX 造封闭体=把 Python 的 winding 问题平移过来，不解决问题。封闭性必须由 Sweep/PolyExtrude 节点保证。

3. **为什么不完全抛弃 Python SOP**：向后兼容 + 某些场景（文件IO、复杂拓扑判断、HDA 逻辑）Python 仍优。分层职责，各司其职。

4. **为什么第2期是中风险但仍要做**：不扩展 recipe backend，VEX 函数库就只能走 network_mode 手动接线（条件B/C 的磕绊根源）。必须让 VEX+Sweep 能走 builder 的确定性装配。

5. **为什么先做函数库（第1期）再做 harness（第2期）**：第1期纯增量零风险，且能立即降低 LLM 代码量。第2期依赖第1期的函数库存在才有意义。第3期清理依赖前两期验证有效。

---

## 九、待确认问题（实施前需决策）

1. **VEX `#include` 机制**：attribwrangle 能否 `#include <vexlib/skeleton.vfl>`？需在 Houdini 里实测。若不行，备选方案是"函数体内联"（skill 文档里每个函数给完整代码，LLM 复制）。这决定第1期的交付形态。**建议第1期第一步先验证这个。**

2. **函数库放 skill 目录还是 `$HOME/houdini/vex/`**：放 skill 目录便于版本控制 + LLM 读取；放 vex/ 目录便于 `#include` 自动发现。需确认 Houdini 的 VEX include path 配置。**建议放 skill 目录，文档里说明 include path 设置。**

3. **form_node 跨 component 引用是否第2期就做**：Sweep 需要 path + section 两个输入，path 可能来自另一个 component。这增加复杂度。**建议第2期先支持 input0=self 或 input0=显式路径，跨 component 引用放第4期。**

4. **是否同期修 Bug 6/7/8**：它们独立于本计划，但新路线鼓励 construction_axis 会自然绕开 Bug 6。**建议 Bug 7（诊断崩）单独修，Bug 6/8 视进度决定。**

5. **实验验证节奏**：每期做完是否跑验证 session？**建议第1期做完跑楼梯验证，第2期做完跑楼梯+城堡验证。**

---

## 十、第一期立即可执行的任务清单

如果批准第1期，按此顺序执行：

```
[ ] 步骤1: 实测 VEX include 机制（attribwrangle + #include）
    → 决定函数库交付形态（include vs 内联）
[ ] 步骤2: 写 skeleton.vfl 的 make_polyline + make_closed_polyline
    → 这两个是最高频，先验证函数库可行性
[ ] 步骤3: 写手动测试脚本，验证这两个函数产出的 polyline 喂 PolyExtrude 能出封闭体
[ ] 步骤4: 补 make_helix / make_stair_path / make_grid
[ ] 步骤5: 写 sections.vfl（make_rect_section / make_circle_section）
[ ] 步骤6: 写 attribs.vfl（set_orient_from_tangent 等）
[ ] 步骤7: 写 README.md 函数目录 + vexlib-usage.md 配套节点 recipe
[ ] 步骤8: SKILL.md 主路由加 vexlib 引用
[ ] 步骤9: 跑楼梯验证 session（对照条件C 的 91 事件）
```
