---
name: edini-brainstorm
description: Use at the START of any Houdini procedural asset or geometry task, BEFORE touching nodes or writing code. Explores user intent, decomposes into components, selects backends (vex_skeleton / native_chain / Python / CTP), and produces a design spec. Replaces the generic brainstorming skill for Houdini geometry work.
license: MIT
---

# Edini Brainstorming — Houdini Design Router

Use this skill at the START of any Houdini geometry task that involves creating, modifying, or assembling components. Do NOT jump into implementation.

## Phase 1 — Context First

Before asking any questions, understand the scene:

1. Check `[Current Houdini Context]` if present — current HIP, network, selected nodes
2. If unclear, call `houdini_get_scene_info` to understand the scene state
3. If there's existing geometry, call `houdini_get_selection` to see what the user has selected

## Phase 2 — Clarifying Questions (one at a time)

Ask questions **one at a time**, each with 3-4 concrete options (A/B/C/D). Wait for the user's answer before asking the next.

**Auto-advance rule:** If the user says "继续" (continue) twice, they want you to stop asking and move to Phase 3. Do NOT ask a third clarifying question after two "继续" responses — proceed to the design proposal immediately.

### Required questions (ask only these 3-4, then auto-advance):

1. **Style & purpose** — What style/type? (e.g. road bike vs mountain bike vs city bike)
2. **Parameterization level** — How many parameters? (基础/中度/高度)
3. **Detail level** — How detailed? (精简/标准/完整) "精简/标准" are self-contained in the Builder; "完整" triggers the Workspace question below.
4. **Material/shape preferences** — Tube shape, spoke style, etc. (domain-specific; skip if obvious from style)

### After answers to Q1-3, auto-advance to Phase 3 (design proposal).

### Stop asking when:
- You have answers to items 1-3 minimum
- OR the user says "继续" twice
- The component decomposition is clear enough to fill the RECIPE template

## Phase 3 — Propose Design

After gathering answers, propose the design as a structured summary:

```
## [Asset Name] — 设计方案

**需求回顾：** [1-line summary of key decisions]

### 组件分解

| # | Component | component_id | Backend | Anchor? |
|---|---|---|---|---|
| 1 | ... | ... | vex_skeleton / native_chain / python / CTP | yes/no |

### 参数体系

| Parameter | Range | Default | Drives |
|---|---|---|---|
| ... | ... | ... | ... |

### 后端选择理由
- [component_X]: vex_skeleton — tube/path geometry, Sweep guarantees closed normals
- [component_Y]: python — complex organic surface, no SOP equivalent
- [component_Z]: CTP template — repeated ≥2 times

### 组装架构
[ASCII diagram showing Merge → CTP → postprocess flow]

### Workspace Plan（微细重复件独立构建计划）
| Workspace | 内容 | 方法 |
|---|---|---|
| _wheel_spokes_ | 单根辐条模板 + scatter → CTP | network_mode sandbox |
| _chain_links_ | 单节链条模板 + 路径scatter → CTP | network_mode sandbox |

\`\`\`

## Phase 4 — Self-Review

Before showing the design to the user, check:

1. **Backend audit** — Every tube/path/pipe component MUST use vex_skeleton. Every simple geometric shape (hub, cylinder, box, pedal, brake body) MUST use native_chain (see prebuilt-templates.md). If any tube uses python or any simple shape uses python, FIX IT NOW.
2. **CTP audit** — Every component repeated ≥2 times MUST use CTP anchors. If any repeated part uses inline generation, FIX IT.
3. **Python gate** — Count the components using python backend. If there are more than 2, reconsider: can any be converted to native_chain or vex_skeleton? python is ONLY for organic surfaces with no SOP equivalent.
4. **Orientation asserts** — Every component_id has an ORIENTATION ASSERT (kind + expected_axis + construction_axis).
4. **Parameter completeness** — Minimum 5 user-exposed parameters. At least 1 cross-component linkage.
5. **No monoliths** — The structure MUST use Merge + CTP, not a single Python SOP emitting everything.
6. **Workspace plan** — All ≥10-copy micro-repetition components (spokes, chain links, rivets) have a concrete workspace plan. They are NOT inlined as Python for-loops in a Builder component.
7. **Recipe size guard** — If total components >12, propose an **incremental build plan**: split into 2-3 phases (Phase 1: core frame + anchors, 5-8 components; Phase 2: remaining, 8-12 components). This catches parm-name and axis errors early instead of after 20 components fail together. Mark each component with its build phase in the component table.

## Phase 5 — Write Design Spec

Write the spec to `docs/edini/specs/YYYY-MM-DD-<topic>-design.md` (project-relative). Include:
- Full RECIPE (components, params, anchors, orientation asserts)
- Assembly architecture diagram
- Backend selection justification
- Verification plan (health → orientation → inventory → commit)

## Phase 6 — Transition to Implementation

After the user approves the design:
1. Load the **procedural-modeling** skill
2. Follow its workflow: recipe → parm lookup → build → verify → commit
3. Do NOT re-ask clarifying questions already answered
