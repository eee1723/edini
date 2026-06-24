# Recipe 搭建指南 — 程序化自行车所需的几何原语

> **状态**：搭建指南（不是 recipe.json，recipe 必须由 `recipe_capture` 脚本从真实 subnet 提取）
> **目的**：告诉你在 Houdini 里该搭哪些 subnet、每个的 Notes 该写什么，
> 搭好后用 `recipe_capture` 脚本提取成稳定可检索的 recipe.json。
>
> **为什么是这份文档而不是手写 recipe.json**：
> recipe.json 是机器产物，必须由脚本从真实节点网络确定性提取。
> 手写会引入参数名错误、spare parm 缺失、节点类型版本差异等不稳定因素。
> LLM 的职责是读 Notes 理解意图 + 改参数，不是编造节点网络。

---

## 〇、心法：recipe 锁什么、放什么

| 锁进 recipe（确定性、可复用） | 留给 LLM 自由发挥（布局层） |
|---|---|
| **几何操作**（扫管、挤出、旋转、阵列） | **组件装配**（哪根管接哪根管） |
| **封闭性约定**（`endcaptype=1`、`outputback=1`、`cap=1`） | **参数关联**（轴距驱动轮位） |
| **朝向约定**（截面画在 XZ 平面、construction_axis） | **比例/尺寸**（车架几何） |
| **单位约定**（米制、unit-scale + pscale） | **风格选择**（公路车/山地车） |
| **打标约定**（component_id） | **细节密度**（辐条数、速别） |

**铁律：不做成品零件 recipe。** 没有 `bicycle_frame`，只有 `tube_along_curve`。
牙盘 = `extrude_solid`（圆盘）+ `radial_copy`（齿牙），让 LLM 自己组合。
这样 recipe 编码"怎么把一类形状做对"，绝不编码"做成什么样子"。

---

## 一、搭建 → 提取的标准流程

每个 recipe 都按这个流程：

1. **在 HDA 内部对应分类容器下建 subnet**（如 `Procedural_Modeling/tubes/tube_along_curve`）
2. **双击进入，搭内部节点网络**（按本文档每个 recipe 的"内部结构"）
3. **选中 subnet，按 C 写 Notes**（按本文档每个 recipe 的"Notes 模板"）
4. **在 Type Properties 里 Apply + Accept**（持久化 HDA 内容）
5. **捕获**：对 LLM 说「捕获 /obj/edini_recipe_manager1 这个树」，
   或在面板里点捕获按钮 → `recipe_capture_tree` 脚本提取所有 leaf 为 recipe.json

**Notes 是强制契约**——空 Notes 或占位词会被 `recipe_capture` 拒绝。
Notes 同时是 LLM 分析意图的唯一入口，所以要写清「功能/用途/重要参数/不要用于」。

---

## 二、需要的 recipe 清单（按几何意图分组）

以自行车为试金石，但每个都泛化到所有机械/载具建模。

### A 组 · 封闭扫管（车架/把手/前叉——自行车几何的大头）

#### A1. `tube_along_curve` — 沿曲线扫掠封闭管材（最通用）

**内部结构**：
```
curve(路径) ──┐
              ├─→ sweep::2.0 (endcaptype=1, surfacetype=2) ─→ 输出
circle(截面) ─┘
```
- `curve`：画路径（直管用两点直线，弯把/前叉用多段曲线）
- `circle`：截面，`type=1`(NURBS) 或 Polygon，半径调到管壁厚
- `sweep::2.0`：**关键约定**——`surfacetype=2`(tube)、`endcaptype=1`(封双端)
-截面必须画在 **XZ 平面**（Sweep 会自动转正）

**Notes 模板**：
```
功能：沿任意输入曲线生成封闭圆柱管材（sweep::2.0 + 圆截面）
用途：弯把、前叉弯曲段、链条撑、座撑、车架直管——任何「一条曲线 + 半径 = 一根管」
输入：第0输入=路径曲线
重要参数：surfacetype, endcaptype, rad
不要用于：变径管（需改 sweep scaleramp）
```

#### A2. `tube_between_points` — 两点直管（A1 的便捷特例）

如果觉得每次画两点曲线太麻烦，可以单独搭这个：内部用 Detail wrangle 从 6 个参数(p0x..p1z)生成两点 polyline 当路径，再接 sweep。**但通常直接用 A1 画直线即可**，这个是可选优化。

---

### B 组 · 截面挤出实体（牙盘/曲柄/踏板/把立）

#### B1. `extrude_solid` — 闭合 2D 截面挤出成封闭实体

**内部结构**：
```
curve(闭合 2D 轮廓) ──→ polyextrude::2.0 (outputfront=1, outputback=1, dist=厚度) ─→ 输出
```
- `curve`：画闭合 2D 形状（牙盘=圆、曲柄=异形、踏板=矩形）
- `polyextrude::2.0`：**关键约定**——`outputfront=1`+`outputback=1`(正反两面都封)，`dist`=厚度

**Notes 模板**：
```
功能：闭合 2D 截面轮廓沿法向挤出成封闭实体（polyextrude，正反两面都封）
用途：牙盘、曲柄、踏板、把立、链轮片——任何「平面闭合形状 + 厚度 = 板状实体」
输入：第0输入=闭合 2D 轮廓
重要参数：dist, outputfront, outputback
不要用于：管材（用 tube_along_curve）、旋转体（用 revolve_profile）
```

---

### C 组 · 旋转体（外胎/把套/花鼓锥——当前完全缺）

#### C1. `revolve_profile` — 母线绕轴旋转成回转实体

**内部结构**：
```
curve(2D 母线) ──→ revolve (surftype=4, cap=1, dir=旋转轴, divs=32) ─→ 输出
```
- `curve`：画 2D 侧轮廓（外胎=小矩形、把套=梯形、花鼓锥=三角）
- `revolve`：**关键约定**——`surftype=4`(Bezier mesh) 或按需、`cap=true`(封端)、`dir`定轴

**Notes 模板**：
```
功能：2D 母线轮廓绕轴旋转一周生成回转实体（revolve，封端）
用途：外胎、把套、花鼓锥面、脚踏体外壳——任何「2D 侧轮廓绕轴转 = 回转体」
输入：第0输入=母线曲线（位于过轴平面内）
重要参数：surftype, cap, dir, divs
不要用于：非回转对称件（用 extrude_solid）
```

---

### D 组 · 实例阵列（辐条/链条——重复件）

#### D1. `radial_copy` — 绕轴均匀阵列（辐条 24/28/32 根）

**内部结构**：
```
attribwrangle(Detail, 布点) ──→ copytopoints::2.0 (第1输入)
                                    ↑
模板几何 ────────────────────────(第0输入)
```
- `attribwrangle`：Detail 模式，生成 N 个绕轴均布的点 + `@orient` 朝向
  （可参考 `skills/recipe-library/vexlib/attribs.vfl` 的 `set_instance_attrs`）
- `copytopoints::2.0`：第0输入=模板，第1输入=布点

**Notes 模板**：
```
功能：单位模板复制到绕指定轴均匀分布的 N 个点（Detail wrangle 布点 + copytopoints）
用途：辐条、齿牙、转子叶片、螺栓圆周阵列——任何「模板 + 绕轴 N 等分 = 环形阵列」
输入：第0输入=模板几何（单位尺寸）
重要参数：radial_count, radial_radius, radial_axis
不要用于：沿曲线分布（用 linear_array_copy）、随机散布（用 scatter+copytopoints）
```

#### D2. `linear_array_copy` — 沿曲线阵列（链条 100+ 节）

**内部结构**：和 D1 类似，但布点沿输入曲线等距分布（resample 后取点，或用 carve 等 u 值）。实例朝向自动对齐曲线切线。

**Notes 模板**：
```
功能：单位模板沿输入曲线均匀阵列 N 份（copytopoints，朝向对齐路径）
用途：链条、飞轮片排列、栏杆、铆钉沿缝——任何「模板 + 沿曲线等距 = 线性阵列」
输入：第0输入=模板；第1输入=路径曲线
重要参数：array_count
不要用于：绕轴环形（用 radial_copy）、单段弯曲管（用 tube_along_curve）
```

---

### E 组 · 布局操作（左右对称）

#### E1. `mirror_bilateral` — 半边镜像焊接

**内部结构**：
```
输入 ──→ mirror (dir=[1,0,0], keepOriginal=1, consolidatepts=1) ─→ normal ─→ 输出
```
- `mirror`：**关键约定**——`keepOriginal=true`(保留半边)、`consolidatepts=true`(焊缝)、`dir=[1,0,0]`(YZ对称面)
- 不焊缝会在对称面产生幽灵非流形边，腐蚀下游 Boolean/Sweep
- 后接 `normal` 重算法线

**Notes 模板**：
```
功能：左右镜像半边几何并焊接对称面（mirror，保留原始+consolidatepts 焊缝）
用途：自行车/摩托车/载具整车——任何「左右对称物体只建半边」
输入：第0输入=半边几何（建在 X>=0 侧）
重要参数：dir, keepOriginal, consolidatepts
不要用于：非对称物体、四向对称（需多次镜像）
```

---

## 三、不要搭的 recipe（保住 LLM 发挥空间）

- ❌ `bicycle_frame` / `chainring` / `crank` / `handlebar` ——成品零件会锁定设计
- ❌ `bicycle` 整装配方 ——装配是 LLM 在布局层的核心职责
- ❌ 倒角/细分等表面处理做成独立 recipe ——那是 finishing，不是 detail

---

## 四、搭好后怎么验证

1. **捕获**：`recipe_capture_tree(/obj/edini_recipe_manager1)` → 看 captured_count
2. **检索**：`recipe_list(query="tube")` → 确认能搜到
3. **重建**：`recipe_rebuild("tube_along_curve", "/obj", overrides={...})`
   → 看 `verify.ok` 是否为 true、`mismatches` 是否为空
4. **视觉核对**：重建的 subnet 和原始的几何一致（除参数差异）

如果 verify 报 mismatches，常见原因（按 `recipe-library-getting-started.md` 排查）：
- `parm missing`：节点类型版本差异（sweep::2.0 vs sweep）
- `expected X got Y`：multiparm 或需要 pressButton 的参数
- `exposed_parms 为空`：没用 Promote Parameter（需用原生 promote 生成 ch 表达式）

---

## 五、和现有 recipe 的关系

| 现有 recipe | 问题 | 建议 |
|---|---|---|
| `sopnet.Procedural_Modeling.Base_Sweep` | spiral 耦合，只能造螺旋管，造不了车架直管 | **重构为** `tube_along_curve`（用通用 curve 替代 spiral） |
| `sopnet.Procedural_Modeling.Base_Copy` | scatter 随机散布 | 保留，覆盖"随机散布"场景（铆钉/草地） |
| `dopnet.noise_forece` | Notes 为空（用了 auto-notes） | **手写 Notes** 后重新捕获 |

`Base_Sweep` 的重构是最高 ROI——它已经 90% 就位，只需把 spiral 换成通用 curve 输入，
就能从"只能造螺旋管"升级为"能造任何管材"。
