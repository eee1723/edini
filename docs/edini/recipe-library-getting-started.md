# Recipe Library — 搭建你的第一个配方

> 这份指南带你在真实 Houdini 21 里走通 recipe-library 的完整闭环：
> **搭 subnet → 写 Notes → 捕获 → 重建 → 验证**。
>
> 工具链已实现并通过测试（285 个测试全绿），但真实 Houdini 的 hou API
> 细节（promote 参数、input connectors）需要实际跑一遍确认。

## 前置：启动 Edini

1. 打开 Houdini
2. 菜单 **Edini → Open Chat Panel**（或 `Alt+Shift+E`）
3. 等聊天面板出现「Edini tools loaded」通知——表示工具服务器（端口 9876）已就绪

## 样板 1：tube_along_curve（沿曲线生成管材）

这是最经典的「单一职责」配方，验证捕获 + 重建。

### 步骤 1：手动搭建 subnet

在 `/obj` 里：

1. 创建一个 `subnet` 节点，重命名为 `tube_along_curve`
2. 双击进入 subnet
3. 内部搭：
   - `curve` 节点（画一条曲线作为路径）→ 重命名 `guide_curve`
   - `circle` 节点（截面圆）→ 重命名 `profile`，调 `rad` 到合适半径（如 0.05）
   - `sweep::2.0` 节点 → 重命名 `sweep1`
     - 把 `guide_curve` 连到 sweep 的第 0 输入（curve 输入）
     - 把 `profile` 连到 sweep 的第 1 输入（截面输入）
     - 设 `endcaptype = 1`（封闭端帽，关键约定）
4. 把 subnet 的第 0 输入暴露出来（可选：让外部曲线驱动）
5. promote 关键参数到 subnet 顶层：
   - 右键 sweep1 的 `rad`（或 profile 的半径）→ **Promote Parameter**
   - 重命名提升的 parm 为 `radius`

### 步骤 2：写 Notes（强制）

选中 subnet `tube_along_curve`，按 `C` 打开 Notes 面板，写：

```
功能：沿曲线生成封闭圆柱管材
用途：车架管、栏杆、把手——任何「一条曲线+半径=一根管」的场景
输入：guide_curve（第0输入，曲线节点）
重要参数：radius, endcaptype
不要用于：变径管（用 tube_tapered）、截面挤出（用 extrude_profile）
```

> ⚠️ **Notes 不能空、不能是占位词**（todo/notes/placeholder），否则捕获会被拒绝。
> `重要参数` 列出的参数即使等于默认值也会被记录——用来锁定关键约定（如 endcaptype=1）。

### 步骤 3：捕获

在 Edini 聊天面板输入：

> 捕获 /obj/tube_along_curve 这个 subnet 到配方库

工具调用 `recipe_capture(subnet_path="/obj/tube_along_curve")`。

**预期返回**：
```json
{
  "success": true,
  "recipe_id": "tube_along_curve",
  "node_count": 3,
  "exposed_parm_count": 1,
  "warnings": []
}
```

检查产物：`recipes/tube_along_curve/recipe.json` 已生成，`recipes/index.json` 已更新。

### 步骤 4：查询验证

> 查询配方库里有哪些管材相关的配方

`recipe_list(query="tube")` 应该返回 tube_along_curve。

### 步骤 5：重建（核心验证）

> 用 tube_along_curve 配方在 /obj 下重建一个，半径改成 0.1

`recipe_rebuild(recipe_id="tube_along_curve", parent_path="/obj", overrides={"radius": 0.1})`。

**预期**：
- 在 `/obj` 下生成一个新 subnet（如 `tube_along_curve_1`）
- 内部节点结构、连线、参数与原配方一致
- `radius` 被覆盖为 0.1
- 返回的 `verify.ok` 为 `true`，`mismatches` 为空

### 步骤 6：人工核对

在 Houdini 视口里对比原始 subnet 和重建的 subnet——几何应一致（除了半径差异）。

---

## 如果捕获/重建出问题

### 捕获报「Notes 为空」
→ 你在错误的节点上写了 Notes，或 Notes 写在了内部节点而非 subnet 本身。选中 subnet 后再写。

### 重建后 verify.mismatches 不为空
→ 读 mismatches。常见原因：
- `某节点.某parm: parm missing`——重建的节点类型没有该 parm（manifest 缺失或类型版本差异）
- `某节点.某parm: expected X, got Y`——参数没设上（可能 parm 是 multiparm 或需要 pressButton）

### exposed_parms 为空
→ promote 的参数没被识别。recipe_library 通过检测 subnet 顶层 parm 的 expression（`ch("../inner/parm")`）来识别 promote。确认你用的是 **Promote Parameter**（Houdini 原生 promote），它会自动生成 channel reference 表达式。

---

## 推荐的第二、三个样板

跑通 tube 后，建议搭这两个验证不同模式：

| 配方 | 验证什么 | 内部节点 |
|---|---|---|
| `copy_to_points` | 多输入 + 散布 | template(geo) + target(points) + copytopoints::2.0 |
| `extrude_profile` | 截面挤出 + 封闭 | curve(截面) + polyextrude::2.0 (output_back=1) |

每个都按同样流程：搭 → 写 Notes → 捕获 → 重建验证。

## 常见问题

**Q: 我改了 subnet 后要重新捕获吗？**
A: 是。配方是捕获时的快照。改了 subnet 就重新 `recipe_capture` 覆盖（同 recipe_id 会覆盖 recipe.json）。

**Q: 配方能跨场景用吗？**
A: 能。配方存在 `recipes/` 目录（项目级），任何场景都能 `recipe_rebuild`。内部 inputs 用相对名，所以场景无关。

**Q: LLM 能自己搭 subnet 并捕获吗？**
A: 能。LLM 用 `houdini_create_node` 搭好后，调 `recipe_capture` 即可。但人工搭建的质量更高——配方库的价值来自 TD 的确定性。
