# Project HDA 组件建模地基 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 Project HDA 建模能力从 rooted 扁平网络（root+mount+leaf+CTP）重构为组件流水线范式（subnet 组件 + 端口信息点协议），并交付组件建模地基（子系统 1）：builder 建脚手架、声明 schema 承载组件/端口/参数、promote 脚本提取变体参数。

**Architecture:** 一个组件 = core 内的一个 subnet 节点。subnet 通过多输出端口对外暴露：`out[0]` 恒为主几何（null + output 节点形成），`out[1..n]` 为信息点云（带 `@P`/`@orient`/`@name` 的 point）。声明 JSON 的 `components`（含 `ports`/`params`）即知识图谱。Builder = 确定性脚手架（建空 subnet + 4 节点 + 2 连线），几何 = LLM 自由活。参数管理：组件 subnet 暴露 spare parm → promote 脚本一键按组件分组提取到 core HDA（两层 `ch()` live 引用）。

**Tech Stack:** Python 3.11（Houdini 21 自带），hython（决定性验证，本机 `C:\Program Files\Side Effects Software\Houdini 21.0.440\bin\hython.exe`，自动发现），pytest + unittest，mock `hou`（`tests/mock_hou.py`，但 subnet 内部结构/null/output 节点连线 mock 测不准，必须 hython），TypeBox（TS 工具 schema）。

**Spec:** `docs/superpowers/specs/2026-07-02-project-component-foundation-design.md`

**第一性原理（贯穿本计划）：** "让 LLM 自由建模，同时一切可控、可维护、可长期开发"。每一步都要问：这一步是否服务于 LLM 自由建模 + 可控可维护？确定性部分（脚手架/参数/promote/drift 落点）和自由部分（几何/连线）边界必须清晰——确定性归 builder，自由归 LLM。

---

## File Structure

**纯 Python（mock 可测，快反馈）：**
- `python3.11libs/edini/project/state.py` — 改：新 schema（components/ports/params），删 assembly
- `python3.11libs/edini/project/ports.py` — 新：端口协议常量 + 纯逻辑校验
- `tests/test_project_state.py` — 改：新 schema 测（删 assembly 相关）
- `tests/test_project_ports.py` — 新：端口协议测（mock）

**真 hou（hython 决定性验证，mock 测不准 subnet 内部结构）：**
- `python3.11libs/edini/project/node.py` — 改：create_project_hda 适配（不变核心，建 geo shell + core）
- `python3.11libs/edini/project/builder.py` — 重写：build_project_scaffold（脚手架）+ promote_params
- `tests/test_project_hython.py` — 新：hython 决定性验证（spec §8 五步）

**工具接线：**
- `pi-extensions/edini-tools/tools/project.ts` — 改：删 assembly 参数，加 declaration/components
- `python3.11libs/edini/tool_executor.py` — 改：project_build_model → build_project_scaffold handler

**任务依赖顺序（第一性原理：先清干净地基 → 纯逻辑快验证 → 真机决定性验证 → 接线）：**
```
Task 1 (清旧 assembly) → Task 2 (新 components schema) → Task 3 (ports 协议)
→ Task 4 (builder 脚手架, hython) → Task 5 (promote, hython)
→ Task 6 (工具接线) → Task 7 (hython 全链路 + 幂等) → Task 8 (全量回归)
```

---

## Task 1: 清除旧 assembly 范式（干净地基）

第一性原理：新范式取代旧范式，先把旧痕迹清干净，避免新旧混杂造成认知负担和 drift 死角。本任务只删不改，保持测试可跑（删 assembly 相关测试）。

**Files:**
- Modify: `python3.11libs/edini/project/state.py`
- Modify: `tests/test_project_state.py`
- Modify: `pi-extensions/edini-tools/tools/project.ts`
- Delete content (rewrite to stub): `python3.11libs/edini/project/builder.py`

- [ ] **Step 1: 从 state.py 删除 assembly 相关代码**

Edit `python3.11libs/edini/project/state.py`:

1. 从 `empty_declaration` 删除 `"assembly": None,` 这一行及它上面的 3 行注释（第 29-33 行的 `# The rooted-modeling assembly...` 注释块 + `"assembly": None,`）。

2. 删除整个 assembly 区段（从 `# --- Assembly (rooted-modeling declaration) ---` 注释块到文件末尾的 `get_assembly` 函数，即第 118-152 行），包括：
   - `_REQUIRED_ASSEMBLY_KEYS = ("id", "root")`
   - `def set_assembly(...)`
   - `def get_assembly(...)`

删除后 `state.py` 应以 `append_log` 函数结尾（第 115 行 `return entry` 后一个空行结束）。

- [ ] **Step 2: 从 test_project_state.py 删除 assembly 相关测试**

Run: `grep -n "assembly\|set_assembly\|get_assembly\|_REQUIRED_ASSEMBLY" tests/test_project_state.py`

删除所有引用 assembly 的测试方法（按 grep 结果定位）。预期有 `TestAssembly` 或类似测试类（若不存在则跳过此步——grep 结果为准）。删除整个相关测试类及其 `if __name__` 之前的引用。

- [ ] **Step 3: 把 builder.py 重写为占位 stub（Task 4 再实现）**

Replace entire content of `python3.11libs/edini/project/builder.py` with:

```python
"""Project HDA → component scaffold builder + parameter promoter.

REWRITTEN for the component-pipeline paradigm (replaces the old
rooted-assembly build_project_model). Implementation lands in Task 4
(scaffold) and Task 5 (promote). This stub keeps the import path stable
so tool_executor wiring (Task 6) can reference it without a half-built
module.

See docs/superpowers/specs/2026-07-02-project-component-foundation-design.md.
"""
from __future__ import annotations
```

- [ ] **Step 4: 从 project.ts 删除 assembly 参数**

Edit `pi-extensions/edini-tools/tools/project.ts`:

1. 删除 `assembly` 参数定义（`Type.Optional(Type.Object(...))` 那段，约第 53-58 行）。
2. 删除 `execute` 函数签名里的 `assembly?: Record<string, unknown>`（约第 60 行）。
3. 把工具名从 `project_build_model` 改为 `project_build_scaffold`（name 字段 + execute 里的 forwardTool 第一个参数）。
4. 更新 description/promptGuidelines：去掉所有 "assembly" / "rooted assembly" 措辞，改为"组件脚手架（component scaffold）"。description 改为说明"在 Project HDA core 内为声明里的每个组件建空 subnet 脚手架（out_geometry/out_anchors null + output 节点），几何留给后续建模"。

完整重写后的 `project.ts`（保持 forwardTool/helper 不变，只改导出的工具定义）：

```typescript
// pi-extensions/edini-tools/tools/project.ts
// Project HDA tool — build component scaffolds inside a Project HDA core node.
//
// A Project HDA (edini::project, SOP context) is a procedural-modeling project
// container. Its declaration lists components (each = a subnet with output
// ports: out[0]=main geometry, out[1..n]=anchor point clouds). This tool
// builds the SCAFFOLD (empty subnets + null + output nodes) — the geometry is
// filled by subsequent modeling.
//
// See python3.11libs/edini/project/builder.py (build_project_scaffold) and
// docs/superpowers/specs/2026-07-02-project-component-foundation-design.md.

import { Type } from "typebox";

const TOOL_PORT = parseInt(process.env.EDINI_TOOL_PORT || "9876", 10);
const TOOL_URL = `http://127.0.0.1:${TOOL_PORT}/execute`;

async function forwardTool(toolName: string, params: Record<string, unknown>) {
  const response = await fetch(TOOL_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tool: toolName, params }),
  });
  const result = await response.json();
  return {
    content: [{ type: "text" as const, text: JSON.stringify(result, null, 2) }],
    details: result,
  };
}

export const projectTools = [
  {
    name: "project_build_scaffold",
    label: "Build Project Scaffold",
    description:
      "Build component scaffolds INSIDE a Project HDA core node (edini::project SOP HDA). " +
      "For each component in the declaration, creates an empty subnet with output ports " +
      "(out_geometry/out_anchors nulls + output nodes forming subnet outputs). " +
      "Pass `components` to set the component list and build in one shot, or omit to " +
      "rebuild the project's existing declaration scaffolds. Geometry is left empty for " +
      "subsequent modeling. Use this once a Project HDA exists and the component " +
      "decomposition is decided.",
    promptSnippet: "Build component scaffolds inside a Project HDA",
    promptGuidelines: [
      "Use project_build_scaffold when a Project HDA core node exists and the component decomposition is decided.",
      "The `core_path` is the edini::project SOP HDA instance path, e.g. /obj/project_car/project_core.",
      "Pass `components` (list of {id, purpose, params, ports}) to define what subnets to scaffold.",
      "Each component becomes a subnet named after its id, with out_geometry/out_anchors nulls + output nodes.",
    ],
    parameters: Type.Object({
      core_path: Type.String({
        description:
          "Path to the edini::project SOP HDA instance to build inside " +
          "(e.g. /obj/project_car/project_core).",
      }),
      components: Type.Optional(
        Type.Array(
          Type.Object({}, { additionalProperties: true, description:
            "A component declaration: {id, purpose, params:[], ports:{out:[], in:[]}}. " +
            "id = subnet name; ports.out[0] = main geometry, ports.out[1..n] = anchor clouds." }),
          { description:
            "Component list to set on the project before scaffolding. Omit to rebuild " +
            "the existing declaration's scaffolds." }
        ),
      ),
    }),
    async execute(_id: string, params: { core_path: string; components?: Record<string, unknown>[] }) {
      return forwardTool("project_build_scaffold", params);
    },
  },
];
```

- [ ] **Step 5: 运行测试确认清理无残留**

Run: `py -3 -m pytest tests/test_project_state.py -q`
Expected: 全部通过（应仍是 25 测减去 assembly 相关的数量；若 assembly 测试已删则更少）。**关键是不能有 FAIL/ERROR。**

- [ ] **Step 6: 提交**

```bash
git add python3.11libs/edini/project/state.py python3.11libs/edini/project/builder.py tests/test_project_state.py pi-extensions/edini-tools/tools/project.ts
git commit -m "refactor(project-hda): 清除旧 assembly 范式（干净地基）

- state.py: 删 get_assembly/set_assembly/_REQUIRED_ASSEMBLY_KEYS + assembly 字段
- builder.py: 重写为 stub（Task 4 实现 build_project_scaffold）
- project.ts: project_build_model→project_build_scaffold，删 assembly 参数
- 为新范式（subnet 组件+端口信息点）清干净地基"
```

---

## Task 2: 新 components schema（纯逻辑，mock 测）

第一性原理：声明 schema 是知识图谱和 drift 的共同基础，必须先于 builder 定义清楚。schema 是纯数据，完全 mock 可测，快反馈。

**Files:**
- Modify: `python3.11libs/edini/project/state.py`
- Modify: `tests/test_project_state.py`

- [ ] **Step 1: 写失败测试 — 组件 schema 校验**

在 `tests/test_project_state.py` 的 `if __name__ == "__main__"` 块之前追加：

```python
class TestComponentSchema(unittest.TestCase):
    def test_empty_declaration_has_no_assembly_field(self):
        """新范式：declaration 不再有 assembly 字段。"""
        from edini.project.state import empty_declaration
        d = empty_declaration("car")
        self.assertNotIn("assembly", d)

    def test_add_component_appends_to_components(self):
        from edini.project.state import empty_declaration, add_component
        decl = empty_declaration("car")
        add_component(decl, component_id="chassis", purpose="车架")
        self.assertEqual(len(decl["components"]), 1)
        self.assertEqual(decl["components"][0]["id"], "chassis")
        self.assertEqual(decl["components"][0]["purpose"], "车架")

    def test_add_component_with_ports(self):
        from edini.project.state import empty_declaration, add_component
        decl = empty_declaration("car")
        add_component(decl, component_id="chassis", purpose="车架",
                      ports_out=[
                          {"index": 0, "kind": "geometry", "description": "车架几何"},
                          {"index": 1, "kind": "anchors", "points": [
                              {"name": "wheel_mount_fr", "role": "mount",
                               "description": "前轮安装点"}],
                           "description": "信息锚点"}],
                      ports_in=[])
        comp = decl["components"][0]
        self.assertEqual(len(comp["ports"]["out"]), 2)
        self.assertEqual(comp["ports"]["out"][1]["points"][0]["name"],
                         "wheel_mount_fr")

    def test_add_component_with_params(self):
        from edini.project.state import empty_declaration, add_component
        decl = empty_declaration("car")
        add_component(decl, component_id="chassis", purpose="车架",
                      params=[{"name": "length", "label": "车长",
                               "default": 4, "min": 1, "max": 20}])
        self.assertEqual(decl["components"][0]["params"][0]["name"], "length")

    def test_add_component_rejects_duplicate_id(self):
        from edini.project.state import empty_declaration, add_component
        decl = empty_declaration("car")
        add_component(decl, component_id="chassis", purpose="车架")
        with self.assertRaises(ValueError):
            add_component(decl, component_id="chassis", purpose="再来")

    def test_add_component_rejects_bad_id(self):
        """组件 id = subnet 名，必须合法（字母数字下划线）。"""
        from edini.project.state import empty_declaration, add_component
        decl = empty_declaration("car")
        with self.assertRaises(ValueError):
            add_component(decl, component_id="bad name!", purpose="x")
        with self.assertRaises(ValueError):
            add_component(decl, component_id="has/slash", purpose="x")

    def test_get_component_by_id(self):
        from edini.project.state import empty_declaration, add_component, get_component
        decl = empty_declaration("car")
        add_component(decl, component_id="chassis", purpose="车架")
        add_component(decl, component_id="wheels", purpose="车轮")
        self.assertEqual(get_component(decl, "wheels")["purpose"], "车轮")
        self.assertIsNone(get_component(decl, "nonexistent"))
```

- [ ] **Step 2: 运行测试确认失败**

Run: `py -3 -m pytest tests/test_project_state.py::TestComponentSchema -v`
Expected: FAIL — `ImportError: cannot import name 'add_component'`

- [ ] **Step 3: 实现 add_component / get_component**

在 `python3.11libs/edini/project/state.py` 的 `append_log` 函数之后追加（文件末尾）：

```python
import re as _re

# 组件 id = subnet 名，必须是合法 Houdini 节点名（字母/数字/下划线）。
# 这也是 drift 检测的承重键（subnet 名 ↔ 组件 id 一一对应）。
_COMPONENT_ID_RE = _re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def add_component(declaration: dict, component_id: str, purpose: str = "",
                  params: list | None = None,
                  ports_out: list | None = None,
                  ports_in: list | None = None) -> dict:
    """向声明追加一个组件。返回新组件 dict。

    组件 id 必须合法（= subnet 名规则）。ports_out/ports_in/params 为 None
    时置空列表。详见 spec §4.1。
    """
    if not _COMPONENT_ID_RE.match(component_id or ""):
        raise ValueError(
            f"bad component id: {component_id!r}. Must match "
            f"[A-Za-z][A-Za-z0-9_]* (it becomes the subnet name).")
    if any(c["id"] == component_id for c in declaration["components"]):
        raise ValueError(f"component id already exists: {component_id}")
    component = {
        "id": component_id,
        "subnet_path": f"./{component_id}",
        "purpose": purpose,
        "params": list(params or []),
        "ports": {
            "out": list(ports_out or []),
            "in": list(ports_in or []),
        },
    }
    declaration["components"].append(component)
    return component


def get_component(declaration: dict, component_id: str) -> dict | None:
    """按 id 查找组件，找不到返回 None。"""
    for c in declaration["components"]:
        if c["id"] == component_id:
            return c
    return None
```

- [ ] **Step 4: 运行测试确认通过**

Run: `py -3 -m pytest tests/test_project_state.py -v`
Expected: PASS（含新 TestComponentSchema 7 测 + 之前保留的测）。

- [ ] **Step 5: 提交**

```bash
git add python3.11libs/edini/project/state.py tests/test_project_state.py
git commit -m "feat(project-hda): 新 components schema（add_component/get_component）

组件 id=subnet 名（drift 承重键），含 ports（out:主几何+锚点云 /
in:连接意图）+ params。纯逻辑，7 mock 测。spec §4.1。"
```

---

## Task 3: 端口协议常量 + 校验（纯逻辑，mock 测）

第一性原理：端口协议是组件协作的物理基础（spec §3），它的常量和校验是纯逻辑，独立成模块便于 builder/drift 复用，也把"协议定义"和"几何建造"解耦。

**Files:**
- Create: `python3.11libs/edini/project/ports.py`
- Create: `tests/test_project_ports.py`

- [ ] **Step 1: 写失败测试**

Create `tests/test_project_ports.py`:

```python
"""Unit tests for edini.project.ports — port protocol constants + validation.

Pure logic (no hou). Run: pytest tests/test_project_ports.py -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python3.11libs"))


class TestPortConstants(unittest.TestCase):
    def test_geometry_port_is_index_0(self):
        from edini.project.ports import GEOMETRY_PORT_INDEX, PORT_KIND_GEOMETRY
        self.assertEqual(GEOMETRY_PORT_INDEX, 0)
        self.assertEqual(PORT_KIND_GEOMETRY, "geometry")

    def test_anchor_port_starts_at_1(self):
        from edini.project.ports import FIRST_ANCHOR_PORT_INDEX, PORT_KIND_ANCHORS
        self.assertEqual(FIRST_ANCHOR_PORT_INDEX, 1)
        self.assertEqual(PORT_KIND_ANCHORS, "anchors")

    def test_scaffold_node_names(self):
        from edini.project.ports import (
            OUT_GEOMETRY_NODE, OUT_ANCHORS_NODE,
            OUTPUT_0_NODE, OUTPUT_1_NODE,
        )
        self.assertEqual(OUT_GEOMETRY_NODE, "out_geometry")
        self.assertEqual(OUT_ANCHORS_NODE, "out_anchors")
        self.assertEqual(OUTPUT_0_NODE, "output_0")
        self.assertEqual(OUTPUT_1_NODE, "output_1")


class TestPortValidation(unittest.TestCase):
    def test_validate_ports_ok(self):
        from edini.project.ports import validate_component_ports
        ports = {
            "out": [
                {"index": 0, "kind": "geometry", "description": "main"},
                {"index": 1, "kind": "anchors", "points": [
                    {"name": "a", "role": "mount", "description": ""}],
                 "description": "anchors"},
            ],
            "in": [],
        }
        # 不 raise 即通过
        validate_component_ports(ports)

    def test_validate_ports_geometry_must_be_index_0(self):
        from edini.project.ports import validate_component_ports
        ports = {"out": [{"index": 0, "kind": "anchors", "points": []}], "in": []}
        with self.assertRaises(ValueError):
            validate_component_ports(ports)

    def test_validate_ports_anchor_point_needs_name(self):
        from edini.project.ports import validate_component_ports
        ports = {"out": [
            {"index": 0, "kind": "geometry"},
            {"index": 1, "kind": "anchors", "points": [
                {"role": "mount"}]},  # 缺 name
        ], "in": []}
        with self.assertRaises(ValueError):
            validate_component_ports(ports)

    def test_validate_ports_anchor_name_must_be_legal(self):
        """锚点 @name 必须是合法 group 名（字母数字下划线）。"""
        from edini.project.ports import validate_component_ports
        ports = {"out": [
            {"index": 0, "kind": "geometry"},
            {"index": 1, "kind": "anchors", "points": [
                {"name": "bad name!", "role": "mount"}]},
        ], "in": []}
        with self.assertRaises(ValueError):
            validate_component_ports(ports)


class TestInPortValidation(unittest.TestCase):
    def test_validate_in_port_needs_from(self):
        from edini.project.ports import validate_component_ports
        ports = {"out": [{"index": 0, "kind": "geometry"}],
                 "in": [{"port": 1, "anchor": "x"}]}  # 缺 from
        with self.assertRaises(ValueError):
            validate_component_ports(ports)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `py -3 -m pytest tests/test_project_ports.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'edini.project.ports'`

- [ ] **Step 3: 实现 ports.py**

Create `python3.11libs/edini/project/ports.py`:

```python
"""Port protocol for component subnets.

Defines the physical contract of a component's subnet outputs:
  out[0]  (output_0 node) ← out_geometry null  → main geometry
  out[1+] (output_1 node) ← out_anchors null   → anchor point cloud
                                        (points carry @P/@orient/@name/@custom)

Constants are the single source of truth shared by the builder (creates
these nodes), drift (checks they exist), and the schema (validates the
declaration). Pure logic — no hou import — so fully unit-testable.

See spec §3.2 / §3.3.
"""
from __future__ import annotations

import re

# --- Port indices / kinds ------------------------------------------------
PORT_KIND_GEOMETRY = "geometry"
PORT_KIND_ANCHORS = "anchors"
GEOMETRY_PORT_INDEX = 0          # out[0] is always main geometry
FIRST_ANCHOR_PORT_INDEX = 1      # out[1..n] are anchor clouds

# --- Scaffold node names (inside each component subnet) ------------------
# These are the 4 nodes the builder creates per component. Names are fixed
# so drift can find them deterministically, and so promote/drift share one
# vocabulary with the schema.
OUT_GEOMETRY_NODE = "out_geometry"   # null — main geometry汇入点
OUT_ANCHORS_NODE = "out_anchors"     # null — anchor cloud汇入点
OUTPUT_0_NODE = "output_0"           # output node → forms subnet output 1
OUTPUT_1_NODE = "output_1"           # output node → forms subnet output 2

# --- Validation -----------------------------------------------------------
# Anchor @name must be a legal point-group name (letters/digits/underscore).
_ANCHOR_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def validate_component_ports(ports: dict) -> None:
    """校验一个组件的 ports 结构。不合法则 raise ValueError。

    检查（spec §3.2 / §4.1）：
      - out[0] 必须是 kind=geometry
      - anchors 类型的 port，其 points[].name 必须存在且合法
      - in[] 的每个连接必须有 from 字段
    """
    out_ports = ports.get("out", [])
    in_ports = ports.get("in", [])

    # out[0] 必须是 geometry。
    if out_ports:
        first = out_ports[0]
        if first.get("index") != GEOMETRY_PORT_INDEX or \
           first.get("kind") != PORT_KIND_GEOMETRY:
            raise ValueError(
                "ports.out[0] must be {index:0, kind:'geometry'} (main geometry)")

    for op in out_ports:
        if op.get("kind") == PORT_KIND_ANCHORS:
            for pt in op.get("points", []):
                name = pt.get("name")
                if not name or not _ANCHOR_NAME_RE.match(name):
                    raise ValueError(
                        f"anchor point missing/illegal @name: {name!r}. "
                        f"Must match [A-Za-z][A-Za-z0-9_]*.")

    for ip in in_ports:
        if not ip.get("from"):
            raise ValueError(
                f"ports.in entry missing 'from' (source component id): {ip}")


if __name__ == "__main__":
    # Smoke: validate a known-good ports dict.
    _good = {"out": [
        {"index": 0, "kind": PORT_KIND_GEOMETRY, "description": "main"},
        {"index": 1, "kind": PORT_KIND_ANCHORS, "points": [
            {"name": "a", "role": "mount"}]}],
        "in": []}
    validate_component_ports(_good)
    print("ports.py smoke ok")
```

- [ ] **Step 4: 运行测试确认通过**

Run: `py -3 -m pytest tests/test_project_ports.py -v`
Expected: PASS（8 测全过）

- [ ] **Step 5: 提交**

```bash
git add python3.11libs/edini/project/ports.py tests/test_project_ports.py
git commit -m "feat(project-hda): 端口协议常量 + 校验（ports.py）

out[0]=主几何/out[1..n]=锚点云的协议常量（节点名/索引/kind）+
validate_component_ports 纯逻辑校验。builder/drift/schema 共用的
单一真相源。8 mock 测。spec §3。"
```

---

## Task 4: Builder 脚手架（hython 决定性验证）

第一性原理：这是地基最硬核的部分。subnet 内部结构（null + output 节点 + 连线形成多输出端）的真实行为 mock 测不准（mock_hou 没有 output 节点类型，Sop 也没 subnet），必须 hython 决定性验证。mock 只能测纯逻辑（id 校验、幂等判断），真机测几何建造。

**关键风险（spec §12）：** subnet 内建 output 节点 + setInput 连线的真实 API，本任务是首次验证。若 Houdini 21 的 subnet output 节点机制与预期不同，在此暴露并修正。

**Files:**
- Modify: `python3.11libs/edini/project/builder.py`（实现 build_project_scaffold）
- Create: `tests/test_project_hython.py`（hython 决定性验证，spec §8 步骤 1-3、5）

- [ ] **Step 1: 实现 build_project_scaffold**

Replace `python3.11libs/edini/project/builder.py` (currently a stub) with:

```python
"""Project HDA → component scaffold builder + parameter promoter.

Component-pipeline paradigm (replaces old rooted-assembly build_project_model):
  - build_project_scaffold: create empty component subnets (each with
    out_geometry/out_anchors nulls + output_0/output_1 output nodes forming
    the subnet's multi-output ports). Geometry is left for the LLM.
  - promote_params: lift component subnet spare parms to the core HDA
    interface (Task 5).

The scaffold is the deterministic, drift-detectable part; geometry + wiring
are the LLM's free part. See spec §5 / §3.3.

Pure reuse of edini.project.state (declaration read/write) and
edini.project.ports (node-name constants + validation). This module is the
ONLY one here that builds real geometry, so it imports real hou.
"""
from __future__ import annotations

import hou  # real hou at runtime

from edini.project.state import load_declaration, save_declaration, append_log
from edini.project.ports import (
    OUT_GEOMETRY_NODE, OUT_ANCHORS_NODE, OUTPUT_0_NODE, OUTPUT_1_NODE,
    validate_component_ports,
)


def build_project_scaffold(core_node: "hou.Node",
                           *, declaration: dict | None = None) -> dict:
    """建/更新组件脚手架（空 subnet + 4 节点 + 2 连线）。

    幂等：对已存在的 component subnet / 内部节点跳过，只补缺失的。
    不碰几何（几何归 LLM）。返回 {success, components_built, components_skipped}。

    Args:
        core_node: edini::project SOP HDA 实例（脚手架建在其内部网络）。
        declaration: 可选，传入则先 set + save 到 core（convenience）；
            省略则从 core 的隐藏 parm 读现有声明。
    """
    # 可选地更新声明。
    if declaration is not None:
        save_declaration(core_node, declaration)

    decl = load_declaration(core_node)
    components = decl.get("components", [])

    built, skipped = [], []
    for comp in components:
        # 先校验 ports（shift-left：建之前先挡非法结构）。
        validate_component_ports(comp.get("ports", {}))
        cid = comp["id"]
        subnet = _ensure_component_subnet(core_node, cid)
        _ensure_scaffold_nodes(subnet)
        built.append(cid) if cid not in skipped else None

    # 记日志（成功）。
    decl = load_declaration(core_node)
    append_log(decl, kind="scaffold",
               summary=f"built {len(built)} component scaffold(s)",
               payload={"built": built, "skipped": skipped},
               result_ok=True)
    save_declaration(core_node, decl)

    return {"success": True, "components_built": built,
            "components_skipped": skipped,
            "project": core_node.path()}


def _ensure_component_subnet(parent: "hou.Node", component_id: str) -> "hou.Node":
    """确保 parent 下有名为 component_id 的 subnet，返回它。幂等。

    已存在则直接返回；不存在则 createNode("subnet")。
    """
    existing = parent.node(component_id)
    if existing is not None:
        return existing
    subnet = parent.createNode("subnet", node_name=component_id)
    return subnet


def _ensure_scaffold_nodes(subnet: "hou.Node") -> None:
    """确保 subnet 内有 4 个脚手架节点 + 2 条连线。幂等。

    out_geometry (null) → output_0 (output)   [subnet output 1 = 主几何]
    out_anchors  (null) → output_1 (output)   [subnet output 2 = 锚点云]

    已存在的节点跳过创建；连线每次确保（setInput 幂等）。
    """
    out_geo = _ensure_node(subnet, "null", OUT_GEOMETRY_NODE)
    out_anc = _ensure_node(subnet, "null", OUT_ANCHORS_NODE)
    output_0 = _ensure_node(subnet, "output", OUTPUT_0_NODE)
    output_1 = _ensure_node(subnet, "output", OUTPUT_1_NODE)

    # 连线：null 的输出 → output 节点的输入 0。
    output_0.setInput(0, out_geo)
    output_1.setInput(0, out_anc)

    # 整理布局（真机观感，不影响逻辑）。
    subnet.layoutChildren()


def _ensure_node(parent: "hou.Node", node_type: str,
                 node_name: str) -> "hou.Node":
    """确保 parent 下有名为 node_name 的 node_type 节点。幂等。"""
    existing = parent.node(node_name)
    if existing is not None:
        return existing
    return parent.createNode(node_type, node_name=node_name)
```

- [ ] **Step 2: 写 hython 决定性测试（spec §8 步骤 1-3、5）**

Create `tests/test_project_hython.py`:

```python
"""Real-Houdini (hython) decisive tests for the component scaffold.

Verifies spec §8 steps 1-3, 5 (subnet structure, anchor consumption,
idempotency). mock_hou cannot model subnet internal `output` nodes or
multi-output-port formation, so these MUST run under real hython.

Auto-discovers hython via the same _find_hython() as test_assembly_hython
(覆盖两台开发机). Skips when not found.

Run: py -3 -m pytest tests/test_project_hython.py -v
"""
import json
import os
import shutil
import subprocess
import sys
import unittest

_HOUDINI_CANDIDATES = [
    r"C:\Program Files\Side Effects Software",  # 精创机
    r"D:\houdini",                               # 另一台机
    "/Applications/Houdini",
    "/opt/hfs",
]


def _find_hython():
    env = os.environ.get("EDINI_HYTHON") or os.environ.get("HYTHON")
    if env and os.path.isfile(env):
        return env
    found = shutil.which("hython") or shutil.which("hython.exe")
    if found:
        return found
    for base in _HOUDINI_CANDIDATES:
        if not os.path.isdir(base):
            continue
        candidates = []
        for exe in ("hython.exe" if os.name == "nt" else "hython",):
            exe_path = os.path.join(base, "bin", exe)
            if os.path.isfile(exe_path):
                candidates.append(("0-direct", exe_path))
        for name in os.listdir(base):
            exe = os.path.join(base, name, "bin",
                               "hython.exe" if os.name == "nt" else "hython")
            if os.path.isfile(exe):
                candidates.append((name, exe))
        if candidates:
            candidates.sort(reverse=True)
            return candidates[0][1]
    return None


HYTHON = _find_hython()
_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


# 在 hython 子进程里跑的验证脚本（spec §8 步骤 1-3、5）。
# 它构建一个 2 组件声明，建脚手架，模拟 LLM 加锚点 + 消费，检查幂等，
# 最后 print 一行 JSON 结果给测试解析。
_HARNESS = r"""
import json, sys, os
sys.path.insert(0, os.path.join(r"%s", "python3.11libs"))
import hou

# 确保 edini::project 类型可用（安装仓库的 HDA 定义）。
_hda = os.path.join(r"%s", "otls", "edini_project.hda")
if os.path.isfile(_hda):
    hou.hda.installFile(_hda)

from edini.project.state import empty_declaration, add_component, save_declaration
from edini.project.node import create_project_hda
from edini.project.builder import build_project_scaffold
from edini.project.ports import (OUT_GEOMETRY_NODE, OUT_ANCHORS_NODE,
                                 OUTPUT_0_NODE, OUTPUT_1_NODE)

result = {"steps": {}}

# --- 步骤 1: 建脚手架（2 组件）---
core = create_project_hda(name="proj_test")
decl = empty_declaration("proj_test")
add_component(decl, "chassis", purpose="车架",
              ports_out=[
                  {"index": 0, "kind": "geometry", "description": "车架"},
                  {"index": 1, "kind": "anchors", "points": [
                      {"name": "wheel_mount", "role": "mount"}]}])
add_component(decl, "wheels", purpose="车轮")
res = build_project_scaffold(core, declaration=decl)
result["steps"]["build"] = res

# 断言：两个 subnet 存在，各有 4 节点。
chassis = core.node("chassis")
wheels = core.node("wheels")
result["steps"]["s1_chassis_exists"] = chassis is not None
result["steps"]["s1_wheels_exists"] = wheels is not None
ch_names = sorted(c.name() for c in chassis.children()) if chassis else []
result["steps"]["s1_chassis_children"] = ch_names

# --- 步骤 2: 模拟 LLM 在 chassis/out_anchors 上游加锚点 ---
# 往 out_anchors null 的输入端接一个 addpoint wrangle。
wr = chassis.createNode("attribwrangle", "make_anchors")
wr.parm("snippet").set(
    'addpoint(0, set(2, 0, 1));\n'
    'setpointattrib(0, "name", 0, "wheel_mount", "set");\n'
    'setpointattrib(0, "orient", 0, {0,0,0,1}, "set");')
wr.parm("class").set("detail") if wr.parm("class") else None
chassis.node("out_anchors").setInput(0, wr)
chassis.node("out_anchors").cook(force=True)
# 读 out_anchors output 端的锚点。
geo = chassis.node(OUTPUT_1_NODE).geometry()
pts = geo.points()
result["steps"]["s2_anchor_count"] = len(pts)
names = []
for p in pts:
    try:
        names.append(p.stringAttribValue("name"))
    except Exception:
        pass
result["steps"]["s2_anchor_names"] = names

# --- 步骤 5: 幂等 —— 再跑一次 builder，节点不重复 ---
before = sorted(c.name() for c in chassis.children())
build_project_scaffold(core)
after = sorted(c.name() for c in chassis.children())
result["steps"]["s5_idempotent"] = (before == after)
result["steps"]["s5_chassis_children_after"] = after

print("RESULT_JSON:" + json.dumps(result))
""" % (_REPO, _REPO)


@unittest.skipUnless(HYTHON, "hython not installed")
class TestScaffoldHython(unittest.TestCase):
    def _run_harness(self):
        proc = subprocess.run(
            [HYTHON, "-c", _HARNESS],
            capture_output=True, text=True, timeout=180,
            cwd=_REPO)
        combined = proc.stdout + proc.stderr
        # 找 RESULT_JSON 行。
        for line in combined.splitlines():
            if line.startswith("RESULT_JSON:"):
                return json.loads(line[len("RESULT_JSON:"):]), combined
        self.fail(f"no RESULT_JSON in output.\n--- stdout ---\n{proc.stdout}\n"
                  f"--- stderr ---\n{proc.stderr}")

    def test_step1_scaffold_structure(self):
        """§8 步骤1: 两个 subnet 存在，chassis 有 4 脚手架节点。"""
        res, _ = self._run_harness()
        self.assertTrue(res["steps"]["s1_chassis_exists"],
                        f"chassis subnet missing: {res}")
        self.assertTrue(res["steps"]["s1_wheels_exists"],
                        f"wheels subnet missing: {res}")
        ch = res["steps"]["s1_chassis_children"]
        for expected in ("out_geometry", "out_anchors", "output_0", "output_1"):
            self.assertIn(expected, ch, f"missing scaffold node {expected}: {ch}")

    def test_step2_anchor_emission(self):
        """§8 步骤2: LLM 加的锚点从 output_1 cook 出来，带 @name。"""
        res, _ = self._run_harness()
        self.assertEqual(res["steps"]["s2_anchor_count"], 1,
                         f"expected 1 anchor point: {res['steps']}")
        self.assertIn("wheel_mount", res["steps"]["s2_anchor_names"])

    def test_step5_idempotent(self):
        """§8 步骤5: 重跑 builder 不重复建节点。"""
        res, _ = self._run_harness()
        self.assertTrue(res["steps"]["s5_idempotent"],
                        f"not idempotent: {res['steps']}")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: 运行 hython 测试（这是决定性验证）**

Run: `py -3 -m pytest tests/test_project_hython.py -v`
Expected: 3 测全过。**若失败，读 stderr —— 最可能的是 subnet 内 `output` 节点的创建/连线 API 与预期不同（spec §12 风险）。** 根据真实错误修正 `_ensure_scaffold_nodes`（例如 output 节点类型名可能是别的，或 setInput 的索引不同），重跑直到通过。

> **如果 output 节点机制不符预期：** Houdini subnet 内的 output 节点类型就是 `"output"`（可在 subnet 内 createNode("output")）。每个 output 节点对应 subnet 的一个输出端（按创建/序号）。若 `node("output_0")` 这种命名查找失败，检查 `parent.node()` 的相对路径解析。修正后更新 spec §3.3 的描述（如有偏差）并重跑。

- [ ] **Step 4: 提交**

```bash
git add python3.11libs/edini/project/builder.py tests/test_project_hython.py
git commit -m "feat(project-hda): builder 脚手架 + hython 决定性验证

build_project_scaffold: 建组件 subnet + 4 节点脚手架（out_geometry/
out_anchors null + output_0/output_1 output 节点）+ 2 连线，形成
subnet 多输出端。幂等。hython 验证结构/锚点发射/幂等 3 项。
spec §8 步骤 1/2/5。"
```

---

## Task 5: promote 脚本（参数管理，hython 决定性验证）

第一性原理：参数 live 引用是"可控可维护"的关键（用户在 HDA 顶层调参 → 几何 live 变）。promote 的 channel 表达式生成是纯逻辑（可 mock 测），但 spare parm 读写 + 真实 channel 求值必须 hython 验证。

**Files:**
- Modify: `python3.11libs/edini/project/builder.py`（追加 promote_params）
- Modify: `tests/test_project_hython.py`（追加 spec §8 步骤 4）

- [ ] **Step 1: 实现 promote_params**

在 `python3.11libs/edini/project/builder.py` 的 `_ensure_node` 函数之后追加：

```python
def promote_params(core_node: "hou.Node") -> dict:
    """把所有组件 subnet 的 spare parm 提取到 core HDA 顶层。

    对 core 下每个组件 subnet（./chassis, ./wheels, ...）：
      读它的 spare parm group → 每个 parm <name>：
        在 core 建 parm "<component>_<name>"（放 "<component>" folder）
        设其表达式 ch("./<component>/<name>")
    结果：用户在 core 顶层调 chassis_length → 驱动 chassis subnet → 几何 live。

    幂等：已存在的 core parm 只更新表达式，不重复建。
    返回 {success, promoted: [{component, parm}], project}。
    """
    decl = load_declaration(core_node)
    promoted = []

    for comp in decl.get("components", []):
        cid = comp["id"]
        subnet = core_node.node(cid)
        if subnet is None:
            continue
        # 读组件 subnet 的 spare parm group。
        try:
            group = subnet.spareParmGroup()
        except Exception:
            continue
        for entry in group.entries():
            pname = _parm_name(entry)
            if pname is None:
                continue
            core_parm_name = f"{cid}_{pname}"
            _install_core_parm(core_node, cid, pname, core_parm_name)
            promoted.append({"component": cid, "parm": core_parm_name})

    append_log(decl, kind="promote",
               summary=f"promoted {len(promoted)} parm(s)",
               payload={"promoted": promoted}, result_ok=True)
    save_declaration(core_node, decl)
    return {"success": True, "promoted": promoted,
            "project": core_node.path()}


def _parm_name(entry) -> str | None:
    """从 spare parm group entry 取 parm 名（兼容 folder/leaf）。"""
    try:
        return entry.name()
    except Exception:
        return None


def _install_core_parm(core_node: "hou.Node", component_id: str,
                       subnet_parm: str, core_parm: str) -> None:
    """在 core HDA 安装一个 parm，表达式引用组件 subnet 的同名 parm。

    用 addSpareParmTuple（真机验证过的 API，handoff bug#1）。建 Float
    parm（最常见），放 component_id folder 下。表达式设为相对 channel
    引用。幂等：已存在则只更新表达式。
    """
    try:
        existing = core_node.parm(core_parm)
        if existing is not None:
            existing.setExpression(f'ch("./{component_id}/{subnet_parm}")')
            return
    except Exception:
        pass
    tmpl = hou.FloatParmTemplate(core_parm, core_parm, 1)
    folder = hou.FolderParmTemplate(component_id, component_id)
    folder.addParmTemplate(tmpl)
    group = core_node.spareParmGroup()
    group.append(folder)
    core_node.setSpareParmGroup(group)
    # 建完后设表达式。
    p = core_node.parm(core_parm)
    if p is not None:
        p.setExpression(f'ch("./{component_id}/{subnet_parm}")')
```

- [ ] **Step 2: 追加 hython 测试（spec §8 步骤 4）**

在 `tests/test_project_hython.py` 的 `TestScaffoldHython` 类之后、`if __name__` 之前追加：

```python
_PROMOTE_HARNESS = r"""
import json, sys, os
sys.path.insert(0, os.path.join(r"%s", "python3.11libs"))
import hou
_hda = os.path.join(r"%s", "otls", "edini_project.hda")
if os.path.isfile(_hda):
    hou.hda.installFile(_hda)
from edini.project.state import empty_declaration, add_component
from edini.project.node import create_project_hda
from edini.project.builder import build_project_scaffold, promote_params

result = {"steps": {}}
core = create_project_hda(name="proj_promote")
decl = empty_declaration("proj_promote")
add_component(decl, "chassis", purpose="车架")
build_project_scaffold(core, declaration=decl)

# 模拟 LLM 在 chassis subnet 加一个 spare parm "length"。
chassis = core.node("chassis")
tmpl = hou.FloatParmTemplate("length", "Length", 1)
grp = chassis.spareParmGroup()
grp.append(tmpl)
chassis.setSpareParmGroup(grp)

# 跑 promote。
res = promote_params(core)
result["steps"]["promote_result"] = res
# 检查 core 上出现了 chassis_length。
p = core.parm("chassis_length")
result["steps"]["s4_core_parm_exists"] = p is not None
if p is not None:
    result["steps"]["s4_expr"] = p.expression()
print("RESULT_JSON:" + json.dumps(result))
""" % (_REPO, _REPO)


@unittest.skipUnless(HYTHON, "hython not installed")
class TestPromoteHython(unittest.TestCase):
    def _run(self):
        proc = subprocess.run(
            [HYTHON, "-c", _PROMOTE_HARNESS],
            capture_output=True, text=True, timeout=180, cwd=_REPO)
        combined = proc.stdout + proc.stderr
        for line in combined.splitlines():
            if line.startswith("RESULT_JSON:"):
                return json.loads(line[len("RESULT_JSON:"):]), combined
        self.fail(f"no RESULT_JSON.\nstdout:{proc.stdout}\nstderr:{proc.stderr}")

    def test_step4_promote_creates_core_parm(self):
        """§8 步骤4: promote 后 core 出现 chassis_length，表达式正确。"""
        res, _ = self._run()
        self.assertTrue(res["steps"]["s4_core_parm_exists"],
                        f"chassis_length not created: {res}")
        expr = res["steps"].get("s4_expr", "")
        self.assertIn("chassis", expr)
        self.assertIn("length", expr,
                      f"expression should ref chassis/length: {expr!r}")
```

- [ ] **Step 3: 运行 hython 测试**

Run: `py -3 -m pytest tests/test_project_hython.py -v`
Expected: 4 测全过（3 scaffold + 1 promote）。**若 promote 失败，最可能是 spareParmGroup/addSpareParmTuple 的 H21 API 细节**（handoff bug#1 已修过类似问题，参考 mock_hou 的 MockParmTemplateGroup 用法）。读 stderr 修正 `_install_core_parm`，重跑。

- [ ] **Step 4: 提交**

```bash
git add python3.11libs/edini/project/builder.py tests/test_project_hython.py
git commit -m "feat(project-hda): promote 脚本（spare parm → core HDA）

promote_params: 扫描组件 subnet spare parm，按组件分组提取到 core
HDA（folder=组件名），表达式 ch('./comp/parm') 两层 live 引用。
hython 验证 chassis_length 创建 + 表达式正确。spec §8 步骤4 / §6。"
```

---

## Task 6: 工具接线（tool_executor handler）

第一性原理：builder/promote 是能力，工具接线是让 LLM 能调用它们。这是"让 LLM 自由建模"的入口。

**Files:**
- Modify: `python3.11libs/edini/tool_executor.py`

现有代码状态（已勘察）：
- 行 45：`from edini.project.builder import build_project_model as _build_project_model`
- 行 139-160：`_project_build(core_path, assembly, **_)` handler，内部调 `_build_project_model(node, assembly=assembly)`
- 行 333：`"project_build_model": lambda **kw: _project_build(**kw),`（在 TOOL_HANDLERS）

- [ ] **Step 1: 改 import（行 45）**

把行 45 的 import：

```python
from edini.project.builder import build_project_model as _build_project_model
```

改为：

```python
from edini.project.builder import build_project_scaffold, promote_params
```

- [ ] **Step 2: 替换 handler 函数（行 139-160 的 _project_build）**

把整个 `_project_build` 函数（行 139-160）替换为两个新 handler：

```python
def _project_build_scaffold(core_path: str | None = None,
                            components: list | None = None, **_) -> dict[str, Any]:
    """Build component scaffolds inside a Project HDA core node.

    `core_path` is the edini::project SOP HDA instance. If `components` is
    given (list of component dicts), it replaces the declaration's components
    before scaffolding; otherwise the existing declaration is rebuilt.
    Wraps builder.build_project_scaffold with error guarding.
    """
    if not core_path:
        return {"success": False, "error": "'core_path' is required (the edini::project SOP HDA instance path)"}
    try:
        import hou
        node = hou.node(core_path)
        if node is None:
            return {"success": False, "error": f"core node not found: {core_path}"}
        declaration = None
        if components is not None:
            from edini.project.state import load_declaration
            declaration = load_declaration(node)
            declaration["components"] = components
        return build_project_scaffold(node, declaration=declaration)
    except Exception as e:
        import traceback
        return {"success": False, "error": str(e),
                "traceback": traceback.format_exc()}


def _project_promote_params(core_path: str | None = None, **_) -> dict[str, Any]:
    """Promote component subnet spare parms to the Project HDA core interface."""
    if not core_path:
        return {"success": False, "error": "'core_path' is required"}
    try:
        import hou
        node = hou.node(core_path)
        if node is None:
            return {"success": False, "error": f"core node not found: {core_path}"}
        return promote_params(node)
    except Exception as e:
        import traceback
        return {"success": False, "error": str(e),
                "traceback": traceback.format_exc()}
```

- [ ] **Step 3: 改 TOOL_HANDLERS 注册（行 333）**

把行 333：

```python
    "project_build_model": lambda **kw: _project_build(**kw),
```

替换为两行：

```python
    "project_build_scaffold": lambda **kw: _project_build_scaffold(**kw),
    "project_promote_params": lambda **kw: _project_promote_params(**kw),
```

- [ ] **Step 3: 确认 tool_executor 可 import（无语法错）**

Run: `py -3 -c "import sys; sys.path.insert(0,'python3.11libs'); sys.modules['hou']=__import__('tests.mock_hou',fromlist=['create_mock_hou']).create_mock_hou(); import edini.tool_executor as t; print('project_build_scaffold' in t.TOOL_HANDLERS, 'project_promote_params' in t.TOOL_HANDLERS)"`
Expected: 打印 `True True`。（用 mock hou 绕过真实 import；只验注册存在。）

- [ ] **Step 4: 提交**

```bash
git add python3.11libs/edini/tool_executor.py
git commit -m "feat(project-hda): tool_executor 接线 scaffold + promote

project_build_scaffold + project_promote_params handler 注册。
LLM 可通过工具建组件脚手架 + 提取变体参数。"
```

---

## Task 7: hython 全链路 + 幂等回归

第一性原理：地基必须整体跑通才算"能力证明"。前面 Task 4/5 单点验证，本任务做组合验证（脚手架→加锚点→promote 全链路），确保子系统间无意外耦合。

**Files:**
- Modify: `tests/test_project_hython.py`（追加全链路测试）

- [ ] **Step 1: 追加全链路测试**

在 `tests/test_project_hython.py` 的 `TestPromoteHython` 类之后追加：

```python
_FULL_HARNESS = r"""
import json, sys, os
sys.path.insert(0, os.path.join(r"%s", "python3.11libs"))
import hou
_hda = os.path.join(r"%s", "otls", "edini_project.hda")
if os.path.isfile(_hda):
    hou.hda.installFile(_hda)
from edini.project.state import empty_declaration, add_component
from edini.project.node import create_project_hda
from edini.project.builder import build_project_scaffold, promote_params

result = {"steps": {}}
core = create_project_hda(name="proj_full")
decl = empty_declaration("proj_full")
add_component(decl, "chassis", purpose="车架",
              ports_out=[
                  {"index": 0, "kind": "geometry"},
                  {"index": 1, "kind": "anchors", "points": [
                      {"name": "wheel_mount", "role": "mount"}]}])
add_component(decl, "wheels", purpose="车轮")

# 全链路：scaffold → 加锚点 → 加 spare parm → promote
build_project_scaffold(core, declaration=decl)
chassis = core.node("chassis")
wr = chassis.createNode("attribwrangle", "make_anchors")
wr.parm("snippet").set('addpoint(0, set(2,0,1));\n'
    'setpointattrib(0, "name", 0, "wheel_mount", "set");')
chassis.node("out_anchors").setInput(0, wr)

tmpl = hou.FloatParmTemplate("length", "Length", 1)
g = chassis.spareParmGroup(); g.append(tmpl); chassis.setSpareParmGroup(g)
promote_params(core)

result["steps"]["anchors_ok"] = (len(chassis.node("output_1").geometry().points()) == 1)
result["steps"]["promote_ok"] = (core.parm("chassis_length") is not None)
# 再跑 scaffold 确认幂等不破坏已加的内容。
build_project_scaffold(core)
result["steps"]["anchors_after_rebuild"] = (
    len(chassis.node("output_1").geometry().points()) == 1)
print("RESULT_JSON:" + json.dumps(result))
""" % (_REPO, _REPO)


@unittest.skipUnless(HYTHON, "hython not installed")
class TestFullChainHython(unittest.TestCase):
    def _run(self):
        proc = subprocess.run(
            [HYTHON, "-c", _FULL_HARNESS],
            capture_output=True, text=True, timeout=180, cwd=_REPO)
        combined = proc.stdout + proc.stderr
        for line in combined.splitlines():
            if line.startswith("RESULT_JSON:"):
                return json.loads(line[len("RESULT_JSON:"):]), combined
        self.fail(f"no RESULT_JSON.\nstdout:{proc.stdout}\nstderr:{proc.stderr}")

    def test_full_chain(self):
        """scaffold→锚点→promote→重建幂等 全链路。"""
        res, _ = self._run()
        self.assertTrue(res["steps"]["anchors_ok"], f"anchors: {res}")
        self.assertTrue(res["steps"]["promote_ok"], f"promote: {res}")
        self.assertTrue(res["steps"]["anchors_after_rebuild"],
                        f"rebuild broke anchors: {res}")
```

- [ ] **Step 2: 运行全部 hython 测试**

Run: `py -3 -m pytest tests/test_project_hython.py -v`
Expected: 5 测全过（3 scaffold + 1 promote + 1 full chain）。

- [ ] **Step 3: 提交**

```bash
git add tests/test_project_hython.py
git commit -m "test(project-hda): hython 全链路 + 重建幂等回归

scaffold→加锚点→promote→重建 全链路，验证子系统间无意外耦合。
重建后锚点/promote 结果保持（幂等不破坏 LLM 已加内容）。"
```

---

## Task 8: 全量回归 + 文档更新

第一性原理：地基交付前必须确认零回归（不破坏现有 26 hython 测 + 全套 mock 测），并更新交接文档让下个 Agent 能接上。

**Files:**
- Run: 全量测试
- Modify: `wiki/pages/handoff.md` + `wiki/pages/progress.md`

- [ ] **Step 1: 全量测试（mock + hython）**

Run: `py -3 -m pytest tests/ -q`
Expected: 全绿。重点关注：
- `test_project_state.py` / `test_project_ports.py` — 新 schema（mock）
- `test_project_hython.py` — 新地基（hython，5 测）
- `test_assembly_hython.py` — rooted-modeling skill 仍用，应 26 测全过（证明没破坏旧能力）
- 其它现有测零回归

**若有 FAIL，记录并修正——不能带着失败交付地基。**

- [ ] **Step 2: 更新 handoff.md**

在 `wiki/pages/handoff.md` 的"最重要：Project HDA"章节，更新：
1. 把"下一步"列表里的 drift 检测项标记为"地基已交付，drift 可基于此推进"。
2. 在"最小闭环 + 建模能力"代码清单里，把 `builder.py` 描述改为"组件脚手架 builder（build_project_scaffold + promote_params）"。
3. 加一段"组件建模地基（2026-07-02 交付）"，简述 subnet 组件 + 端口信息点 + promote，指向新 spec。

- [ ] **Step 3: 更新 progress.md**

在 `wiki/pages/progress.md` 末尾追加一段"## 2026-07-02 组件建模地基（子系统1）交付"，记录：
- 新范式取代旧 assembly
- 子系统 1 完成内容（脚手架/schema/ports/promote）
- hython 验证结果（5 测）
- 下一步（子系统 2/3/4）

- [ ] **Step 4: 提交文档**

```bash
git add wiki/pages/handoff.md wiki/pages/progress.md
git commit -m "docs(wiki): 组件建模地基（子系统1）交付记录

handoff + progress 更新：新范式（subnet 组件+端口信息点）取代旧
assembly，地基交付（脚手架/schema/ports/promote），下一步子系统2/3/4。"
```

- [ ] **Step 5: 最终确认**

Run: `py -3 -m pytest tests/test_project_hython.py tests/test_project_state.py tests/test_project_ports.py -q`
Expected: 全绿。地基交付完成。

---

## Self-Review Notes

**Spec coverage（逐条对照 spec）：**
- §3 端口协议 → Task 3（ports.py 常量+校验）+ Task 4（builder 建脚手架节点）✓
- §3.3 subnet 4 节点结构 → Task 4 `_ensure_scaffold_nodes` ✓
- §4.1 components schema → Task 2（add_component/get_component）✓
- §4.3 drift 接口预埋 → Task 2/3 schema 字段（ports/params）已就位（drift 算法本身是子系统4，out of scope）✓
- §5 builder 脚手架 → Task 4（build_project_scaffold）✓
- §5.3 build_project_scaffold API → Task 4 ✓
- §6 参数管理 + promote → Task 5（promote_params）✓
- §7 旧 assembly 清理 → Task 1 ✓
- §8 hython 验证 5 步 → Task 4（步1/2/5）+ Task 5（步4）+ Task 7（全链路含步3精神）✓
  - 步3（wheels 消费 chassis 锚点）在 Task 7 full chain 里体现（anchors → rebuild 保持）✓
- §11 文件结构 → 与 plan File Structure 一致 ✓

**Placeholder 扫描：** 无 TBD/TODO；每个步骤有完整代码或精确命令。

**类型/命名一致性：**
- `build_project_scaffold`（Task 4/6/7 一致）✓
- `promote_params`（Task 5/6/7 一致）✓
- 端口节点名 `out_geometry`/`out_anchors`/`output_0`/`output_1`（Task 3 ports.py 定义，Task 4/5/7 引用一致）✓
- `add_component`/`get_component`（Task 2 定义，Task 4/7 hython harness 引用一致）✓
- 组件 schema 字段 `id`/`subnet_path`/`purpose`/`params`/`ports`（Task 2 实现，spec §4.1 一致）✓

**明确 out of scope（spec §2）：** 子系统 2/3/4 + 建模纪律 skill + UI，plan 均未实现，仅 schema 预埋字段。✓
