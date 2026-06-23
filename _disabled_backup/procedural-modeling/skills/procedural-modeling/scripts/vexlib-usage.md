# VEXlib Usage — Node Recipes

## ⚙️ 加载机制（重要）

**vexlib 函数会自动可用 —— 你不需要手写 `#include`。** 当你的 wrangle snippet 调用任意 vexlib 函数（`make_polyline`、`make_circle_section`、`make_gear_profile`、`set_instance_attrs` … 共 15 个），`build_procedural_asset` 会在 cook 前自动把对应的 `.vfl` 源码内联到 snippet 头部。这是可靠的内置机制（不依赖环境变量），所有 15 个函数都覆盖。

- ✅ **直接写函数调用**：`int p[] = make_circle_section(0, chf("r"), 16, "XZ", {0,0,0});`
- ❌ **不要手写 `#include`**：多余且若路径未配置会失败。下面示例里的 `#include` 行仅为历史参考，实际不需要。
- 若你在 `attribwrangle` 的 `snippet` 里既调用 vexlib 函数又有自定义逻辑，只需把 vexlib 调用和你的逻辑写在一起即可。

## 设计理念

vexlib 是**基础工具箱**，不是**唯一选择**。它的作用是：
1. 提供最常用的几何骨架函数（make_polyline、make_circle_section 等）
2. 作为 VEX 语法的**参考范式**——当你需要 vexlib 没有的功能时，参照已有函数的风格自己写

**判断流程：**
1. vexlib 有现成函数？→ 直接用
2. vexlib 没有，但可以用已有的组合实现？→ 组合现有函数
3. 需要全新的 VEX 逻辑？→ 参照 vexlib 的代码风格自己写（Detail 模式、ch() 读参数、返回 point_ids、不生成封闭几何）

**自己写 VEX 的范式（照着写）：**
```vex
// ✅ 正确：Detail 模式，ch() 读参数，返回 point_ids，只生成骨架
int[] make_my_shape(const int geohandle; ...)
{
    vector pts[];
    for (int i = 0; i < count; i++) {
        float t = float(i) / float(count - 1);
        vector pos = ...;  // 你的几何计算
        int pt = addpoint(geohandle, pos);
        setpointattrib(geohandle, "pscale", pt, chf("radius"));
        append(pts, pt);
    }
    int prim = addprim(geohandle, "polyline");
    for (int i = 0; i < len(pts); i++)
        addvertex(geohandle, prim, pts[i]);
    return pts;
}
```

**❌ 不要做的事：**
- 在 VEX 里 addprim("poly") 生成多边形（封闭性留给 Sweep/PolyExtrude）
- 硬编码数字（用 chf/chi 读参数）
- 在 Point 模式下跑（必须 Detail）

## 模式优先级

| 优先级 | 模式 | VEXlib 函数 | 下游节点 |
|---|---|---|---|
| 🥇 | **CTP + 原生模板** | scatter wrangle（@P/@orient） | CTP |
| 🥈 | **截面 + PolyExtrude** | make_rect_section / make_circle_section | PolyExtrude |
| 🥉 | **路径 + 截面 + Sweep** | make_polyline + make_*_section | Sweep |

---

## 🥇 CTP + 原生模板（默认首选）

最简单的模式——LLM 只写 scatter wrangle（10 行以内 VEX），模板用原生 SOP。

### 楼梯 / 重复离散部件

**网络：**
```
box（sizex=tread, sizey=thick, sizez=width, ty=thick/2）
          ↓
wrangle（Detail 模式，每步一个点 @P/@orient）
          ↓
CTP（点 resettargetattribs 按钮）
          ↓
Normal → OUT
```

**scatter wrangle 模板（Detail 模式）：**
```vex
int n = 12;           // 从 ch("steps") 读
float tread = 0.3;
float riser = 0.18;
vector dir = set(1,0,0);
vector pos = set(tread*0.5, 0, 0);
for (int i = 0; i < n; i++) {
    int pt = addpoint(0, pos);
    vector4 ori = set(0.0, 0.0, 0.0, 1.0);
    setpointattrib(0, "orient", pt, ori);
    setpointattrib(0, "pscale", pt, 1.0);
    pos += dir * tread + set(0, riser, 0);
}
```

**关键规则：**
- 模板尺寸和散布位置通过参数关联（`thick = riser` 消除间隙）
- CTP 节点创建后 `点 resettargetattribs` 按钮
- 散布 wrangle 必须 Run Over: Detail
- 用 `set()` 不用 `{}`——避免 vector4/matrix2 歧义

### 砖墙 / 瓷砖

散射模板同上，scatter 用 `make_grid`（vexlib）：
```vex
#include <vexlib/skeleton.vfl>
int pts[] = make_grid(0, 10, 20, 0.25, 0.1, 1, {0,0,0}, "XZ");
for (int i = 0; i < len(pts); i++) {
    vector4 ori = set(0.0, 0.0, 0.0, 1.0);
    setpointattrib(0, "orient", pts[i], ori);
    setpointattrib(0, "pscale", pts[i], 1.0);
}
```

---

## 🥈 截面 + PolyExtrude（单件挤出）

闭合轮廓由 vexlib 生成，封闭性由 `output_back=1` 保证。

**网络：**
```
wrangle（Detail，make_rect_section / make_circle_section）
          ↓
PolyExtrude（output_back=1, dist=长度）
          ↓
OUT
```

**wrangle 模板（Detail 模式）：**
```vex
#include <vexlib/skeleton.vfl>
#include <vexlib/sections.vfl>
int prof[] = make_rect_section(0, chf("width"), chf("height"), "XY");
```

---

## 🥉 路径 + 截面 + Sweep（连续管/螺旋）

**仅在 CTP 无法表达时使用。** Sweep 对属性敏感——这是高级模式。

### 管道

**网络：**
```
wrangle_path（Detail，make_polyline）──┐
                                       ├→ Sweep（surfacetype=2, endcaptype=1）→ OUT
wrangle_sect（Detail，make_circle_section）┘
```

**Network (built via `build_procedural_asset` — the only multi-component build path; raw `network_mode` cannot pass the G3 commit gate because it does not bake `edini_world_axis`):**

```
wrangle_path (attribwrangle, Detail):
  int pids[] = make_stair_path(0, chi("steps"), chf("tread"), chf("riser"),
                               {0,0,0}, {1,0,0});
  ↓ (open polyline)
wrangle_section (attribwrangle, Detail):
  int prof[] = make_rect_section(0, chf("width"), chf("riser"), "XZ");
  ↓  (closed rectangular polyline in XZ plane)
sweep (sweep::2.0):
  input0 = wrangle_path   (spine)
  input1 = wrangle_section (cross-section)
  params: surfacetype=1 (ribbon)
  ↓ (surface ribbon following stair path)
OUT
```

> The Sweep ribbon follows the stair path with the rectangular section. Each
> tread/riser segment gets a face from the sweep.

---

## make_rect_section → PolyExtrude (beam/pillar/beam from profile)

**Network (single component):**

```
wrangle (attribwrangle, Detail):
  int prof[] = make_rect_section(0, chf("width"), chf("height"), "XY");
  ↓ (closed rectangular contour)
polyextrude (polyextrude::2.0):
  input0 = wrangle
  params: dist=ch("length"), output_back=1
  ↓ (closed extruded solid)
OUT
```

> `output_back=1` ensures the back face is output, making it a closed solid.
> The profile is a closed polyline, so PolyExtrude produces a proper 6-face
> extruded prism.

---

## make_circle_section → PolyExtrude (round pillar/pipe)

**Network:**

```
wrangle (attribwrangle, Detail):
  int prof[] = make_circle_section(0, chf("radius"), chi("sides"), "XZ", {0,0,0});
  ↓
polyextrude (polyextrude::2.0):
  input0 = wrangle
  params: dist=ch("height"), output_back=1, divisions=chi("height_divs")
  ↓
OUT
```

---

## make_polyline + make_circle_section → Sweep (curved pipe/tube)

**Network:**

```
wrangle_path (attribwrangle, Detail):
  vector pts[] = ...  // curved path defined parametrically
  int pids[] = make_polyline(0, pts);
  ↓ (open polyline)
wrangle_section (attribwrangle, Detail):
  int prof[] = make_circle_section(0, chf("pipe_r"), 16, "XY", {0,0,0});
  ↓ (circle contour)
sweep (sweep::2.0):
  input0 = wrangle_path   (spine)
  input1 = wrangle_section (cross-section)
  params: surfacetype=2 (tube), endcaptype=1  ← endcaptype=1 caps both ends
  ↓ (closed pipe with capped ends)
OUT
```

> `endcaptype=1` caps BOTH ends of the sweep, making a fully closed pipe.

---

## make_grid → Copy-to-Points (brick wall, tile floor, rivet array)

**Network (via `build_procedural_asset`):**

```
component code (single-SOP, one brick template):
  node = hou.pwd(); geo = node.geometry()
  geo.addAttrib(hou.attribType.Prim, "component_id", "")
  add_box(geo, (0,0,0), (bw,bh,bd), "brick", "brick_mat")
  ↓ (one brick, component_id="brick", unit scale)
anchors: position_expr driven, or scatter through a separate wrangle:
  va (attribwrangle, Detail):
    int pts[] = make_grid(0, chi("rows"), chi("cols"),
                          chf("brick_w"), chf("brick_h"),
                          1, {0,0,0}, "XZ");
    for (int i = 0; i < len(pts); i++)
    {
      setpointattrib(0, "component_id", pts[i], "anchor_brick");
    }
  ↓ (scatter points)
copytopoints::2.0:
  input0 = brick component output
  input1 = scatter points output
  ↓ (brick wall — one template, parametric rows×cols)
merge → postprocess(fuse, clean, normal) → OUT
```

---

## make_helix → Sweep (spiral staircase rail, spring)

**Network:**

```
wrangle_path (attribwrangle, Detail):
  int path[] = make_helix(0, 200, chf("radius"), chf("height"), chf("turns"));
  ↓
wrangle_section (attribwrangle, Detail):
  int prof[] = make_circle_section(0, chf("pipe_r"), 12, "XY", {0,0,0});
  ↓
sweep (sweep::2.0):
  input0 = wrangle_path, input1 = wrangle_section
  params: surfacetype=2, endcaptype=1
  ↓
OUT
```

## make_arc_path → Sweep (arched window frame, curved beam)

**Network:**

```
wrangle_path (attribwrangle, Detail):
  int path[] = make_arc_path(0, 50, chf("radius"), 0, 180, "XY", {0,chf("rise"),0});
  ↓
wrangle_section (attribwrangle, Detail):
  int prof[] = make_rect_section(0, chf("frame_w"), chf("frame_d"), "XZ");
  ↓
sweep (sweep::2.0):
  input0 = wrangle_path, input1 = wrangle_section
  params: surfacetype=1, endcaptype=0
  ↓
OUT
```

---

## Common Composition Patterns

### Pattern A: Sweep path + Sweep section (tube/pipe/beam/rail)
```
wrangle (path) ─┐
                ├→ sweep::2.0 (endcaptype=1 for closed tube)
wrangle (section)┘
```

### Pattern B: Closed section → PolyExtrude (pillar/block/beam)
```
wrangle (closed profile) → polyextrude::2.0 (output_back=1) → OUT
```

### Pattern C: Scatter grid → Copy-to-Points (wall/floor/rivets)
```
component template ─┐
                    ├→ copytopoints::2.0 → OUT
wrangle (grid) ─────┘
```

---

## Gotchas

- **Sweep input order matters:** input 0 = spine (path), input 1 = cross-section.
  Getting them swapped produces a flat ribbon instead of a tube.
- **endcaptype:** 0 = open tube, 1 = capped (closed pipe). Use 1 when you need
  a closed solid.
- **output_back on PolyExtrude:** 0 = front face only (open), 1 = both faces
  (closed solid). Always use 1 for closed geometry.
- **Run Over must be Detail:** if the wrangle runs Over: Points, each point
  calls addpoint N times → geometry multiplied by N².
- **Parms via ch():** all sizing reads `chf("name")` or `chi("name")`. This
  auto-creates UI sliders on the wrangle — no need to install spare parms
  with FloatParmTemplate.
