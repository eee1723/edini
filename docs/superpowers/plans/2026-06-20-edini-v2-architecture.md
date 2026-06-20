# Edini 程序化架构 v2 实施计划

> **For agentic workers:** Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 Builder 的 vex_skeleton component_id 丢失问题，建立 Builder+Workspace 双层架构，扩展 vexlib 预制工具，优化 skill 指导模型选择正确方案。

**Architecture:** Builder 负责顶层组件分解（管材/锚点/直接merge），Workspace（network_mode sandbox）负责微细重复件（辐条/链条环节）。skill 知道何时回退到工作区。

**Tech Stack:** Python 3.11, Houdini 21, VEX, vexlib

## Global Constraints

- 所有 VEX 函数必须在 Detail 模式下运行
- 所有 vexlib 函数返回 point IDs，不生成封闭几何
- Builder 改动必须在 `harness.py` 的 `build_procedural_asset` 函数内
- 现有 recipe 向后兼容
- 不能引入 Houdini 版本特定的 parm 名称（必须查 `houdini_node_parms`）

---

### Task 1: 修复 vex_skeleton 组件 component_id 丢失
**Files:**
- Modify: `Z:/EEE_Project/Edini/python3.11libs/edini/harness.py:~2419`

**Interfaces:**
- Consumes: vex_skeleton 后端的 form_node 输出节点
- Produces: 带 `component_id` prim 属性的 tagged 输出节点

**问题:** Sweep/PolyExtrude 不传递来源 polylines 的 prim 属性。直接 merge 的 vex_skeleton 组件没有 `component_id` 标签，朝向验证门找不到它。

- [ ] **Step 1: 阅读 harness.py 中 form_node cook 后的代码**
读取 line 2410-2430 确认 exact insertion point。

- [ ] **Step 2: 插入 component_id 标记代码**
在 form_node cook 成功后、无锚点组件加入 comp_nodes 之前，插入：
```python
# Tag vex_skeleton output with component_id (Sweep/PolyExtrude
# strips prim attributes from source polylines)
if backend == "vex_skeleton" and not anchors:
    tag_name = f"{cid}_tag"
    tag_sop = _safe_create_node(root_path, "attribcreate", tag_name)
    tag_sop.setInput(0, comp_output)
    _set_parm_safe(tag_sop, "name1", "component_id")
    _set_parm_safe(tag_sop, "class1", "prim")
    _set_parm_safe(tag_sop, "type1", "string")
    _set_parm_safe(tag_sop, "string1", cid)
    tag_sop.cook(force=True)
    comp_output = tag_sop
```

- [ ] **Step 3: 在 Houdini 中测试**
构建一个简单的 vex_skeleton 组件（如单根管），执行 `houdini_inspect_geometry_health` 确认 `component_id` 存在，执行 `houdini_verify_orientation` 确认朝向验证通过，执行 `houdini_commit_sandbox` 确认不再被拒绝。

---

### Task 2: 在 procedural-modeling SKILL 中声明工作区回退方案
**Files:**
- Modify: `Z:/EEE_Project/Edini/skills/procedural-modeling/SKILL.md`

**Interfaces:**
- 新增章节: "## Step 3c — When Builder Can't Handle Micro-Repetition"
- 修改: Step 5 Workflow 第9步，增加 3 轮修复上限

- [ ] **Step 1: 在 Step 3b 之后插入新章节**
在 Micro-repetition MUST use Copy-to-Points 之后，Step 4 Recipe First 之前，插入工作区回退指南。

- [ ] **Step 2: 修改 Workflow 第9步增加修复上限**
在 repair loop 规则中增加：3轮后放弃，切换方案或问用户。

- [ ] **Step 3: 验证文件完整性**
检查 markdown 结构，确保无语法错误。

---

### Task 3: 创建预制模板索引文档
**Files:**
- Create: `Z:/EEE_Project/Edini/skills/procedural-modeling/scripts/prebuilt-templates.md`

**Interfaces:**
- 被 procedural-modeling SKILL 的 Reference Index 引用
- 每个模板是一个 `native_chain` recipe 片段，模型可直接复制

- [ ] **Step 1: 创建文档**
收录常用原语的 native_chain 定义：spoke_template, hub_template, pedal_template, chain_link_template, bb_shell_template。

- [ ] **Step 2: 在 SKILL.md Reference Index 中添加引用**

---

### Task 4: 新增 vexlib 函数 make_gear_profile
**Files:**
- Modify: `Z:/EEE_Project/Edini/skills/procedural-modeling/scripts/vexlib/sections.vfl`

**Interfaces:**
- Consumes: 参考已有函数 `make_circle_section` 的模式
- Produces: `int[] make_gear_profile(geohandle, teeth, outer_r, inner_r, plane, offset)`
  - 返回闭合 polyline 的 point IDs
  - 在 Detail 模式下运行
  - 生成齿轮状截面：交替 outer_r 和 inner_r 的顶点

- [ ] **Step 1: 阅读 sections.vfl 现有模式**
确认 make_circle_section 的代码风格和惯例。

- [ ] **Step 2: 编写 make_gear_profile 函数**
```vex
int[] make_gear_profile(const int geohandle;
                        const int teeth;
                        const float outer_r;
                        const float inner_r;
                        const string plane;
                        const vector offset)
{
    vector pts[];
    int n = teeth * 2;  // 每个齿两个顶点（尖和谷）
    for (int i = 0; i < n; i++)
    {
        float angle = float(i) / float(n) * 2.0 * M_PI;
        float r = (i % 2 == 0) ? outer_r : inner_r;
        float x = r * cos(angle);
        float y = r * sin(angle);
        vector p;
        if (plane == "XZ") p = set(x, 0, y);
        else if (plane == "YZ") p = set(0, x, y);
        else p = set(x, y, 0);
        append(pts, p + offset);
    }
    return make_closed_polyline(geohandle, pts);
}
```

- [ ] **Step 3: 在 vexlib README 中添加函数文档**

- [ ] **Step 4: 在 Houdini 中测试**
用 `houdini_node_parms("attribwrangle")` 确认 Detail 模式类值。
在 Houdini 中创建一个 attribwrangle，设置 class=Detail，粘贴 make_gear_profile 代码，确认无编译错误。

---

### Task 5: 更新 edini-brainstorm 增加分层决策
**Files:**
- Modify: `Z:/EEE_Project/Edini/skills/edini-brainstorm/SKILL.md`

**Interfaces:**
- 在 Phase 2 中增加 Houdini-specific question #9
- 在 Phase 4 Self-Review 中增加 workspace 检查项

- [ ] **Step 1: 在 Phase 2 问题列表末尾添加新问题**
Question 9: "哪些微细重复件（辐条/链条/铆钉 ≥10）无法在 Builder 中表达，需要单独开 Workspace 构建？"

- [ ] **Step 2: 在 Phase 3 设计方案模板中增加 Workspace Plan 区域**

- [ ] **Step 3: 在 Phase 4 Self-Review 中增加检查**
"Workspace plan: 所有 ≥10 件的微细重复件都有明确的 workspace 计划，不在 Builder 中手写 for 循环。"

- [ ] **Step 4: 增加 3 轮 deliberation 上限规则**
在 Phase 2 前添加: "If you've deliberated on backend/architecture for more than 3 rounds without progress, STOP — pick the simpler approach (Builder for frame, workspace for micro-details) and move to Phase 3."

---

### Task 6: Houdini 集成测试
**Files:**
- Test in: `Z:/EEE_Project/Houdini-test/procedural.hip`

- [ ] **Step 1: 测试 vex_skeleton component_id 修复**
用 houdini_build_procedural_asset 构建单根 vex_skeleton 管的自行车框架，确认 commit 不再因 component_id 缺失而失败。

- [ ] **Step 2: 测试 make_gear_profile**
在 Houdini 中手动创建 attribwrangle(Detail)，include vexlib，调用 make_gear_profile，连接 polyextrude，确认齿轮形截面正确。

- [ ] **Step 3: 测试 workspace 方案**
用 network_mode sandbox 构建辐条散布 + CTP，确认产出正确的辐条几何。

- [ ] **Step 4: 端到端测试**
触发一次完整的 "做一个自行车" 任务，观察模型是否正确选择 Builder+Workspace 模式。
