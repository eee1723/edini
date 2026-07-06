---
name: project-modeling
description: Build a procedural model made of MULTIPLE PARTS that fit together (table, car, bicycle, keyboard, machine, building). Declare components, scaffold them as collaborating subnets, model freely inside each. Components connect via measured anchors (never hardcoded). This is the default and only path for multi-part modeling.
---

# Project Modeling — components that collaborate via measured anchors

## Why this skill exists

An LLM dropped into Houdini will, by default, build models four ways that all
break parametricity:

1. **Hardcode coordinates** — type `addpoint(1.2, 0, 0.6)` instead of measuring
   the position from geometry. The model looks right once, then breaks the
   moment any parameter changes.
2. **Skip declared dependencies** — place components with transform nodes
   instead of wiring one component's anchors into the next, so parts float
   disconnected when upstream geometry shifts.
3. **Pile everything into one Python SOP** — write one 200-line script that
   no one can read, debug, or hand-edit.
4. **Declare "done" prematurely** — build two of four legs and stop, because
   nothing told it the model wasn't finished.

This skill forces the deterministic path that defeats all four: **scaffold**
empty component subnets, **measure** anchors from geometry, **wire** components
through anchor ports, and **verify** each step has a completion criterion
before moving on. The platform (`guards.py`) hard-refuses hardcoded anchors, so
the prompt-layer rules below and the platform-layer refusals reinforce each
other through the same vocabulary.

## ⛔ Guardrails (read before doing anything)

**1. Declare every cross-component dependency in `ports.in`.**
If component B physically depends on component A's anchors, B's `ports.in` MUST
list each anchor it consumes. A missing `ports.in` is the #1 cause of broken
parametric models — the builder creates no input port, B cannot consume A's
anchors, and you are forced to hand-place B with transform nodes. This is the
single authoritative statement of this rule; the workflow below refers back to
it rather than restating it.

**2. Always `measure` — never hardcode coordinates.**
Anchors must be measured from geometry (`project_add_anchors`) so they move
when parameters change. Never type `addpoint(x,y,z)`. The platform guard
**refuses** hardcoded `addpoint` inside a Project HDA component — you will see
a `Refused: measure violation ...` error. That refusal is the rule below made
executable.

**3. Brainstorming is a fast-path, not a full interview.**
For modeling tasks, ask 1-2 quick questions (style? size?), present a brief
component decomposition, then delegate to this skill's workflow. Do NOT run
brainstorming's full software-spec flow — that is for code, not 3D models.

## Leading words

These three words appear throughout this skill, the tool descriptions, and the
platform error messages. Learn them as triggers, not prose:

- **`scaffold`** — what the builder does: create empty component subnets with
  output ports and cross-component wiring. Deterministic, idempotent. The
  builder never builds geometry. (Step 2)
- **`anchor`** — a named point one component emits so another knows where to
  place itself (`@name`, `@P`, `@orient`). The inter-component bus. (Step 2–3)
- **`measure`** — how anchors are produced: derived from live geometry on every
  cook, never typed as coordinates. (Step 3, enforced by platform)

## The workflow (deterministic steps)

Driven by three dedicated tools plus standard node tools. Each step ends with a
**✅ completion criterion** — do not proceed until it is met.

### 1. Create the project — `project_create`

```
project_create(name="project_table", goal="a small table")
  → returns { core_path: "/obj/project_table/project_core", ... }
```

Call this FIRST. It is workspace-aware: if a Project HDA core is selected in
the network editor, it is reused (returns its path); only creates new when
nothing relevant is selected. Remember the returned `core_path`.

**✅ Done when:** `core_path` is returned and you have stored it for the next
step. If it created a new HDA unexpectedly, you had a stale selection —
deselect and retry.

### 2. Declare components + `scaffold` — `project_build_scaffold`

Pass `core_path`, `components`, and `design_params`. Each component has an
`id` (= subnet name), `purpose`, and `ports` (declaring what it emits and what
it consumes).

```
project_build_scaffold(core_path="/obj/project_table/project_core", components=[
  { "id": "tabletop", "purpose": "桌面，输出四条腿的安装锚点",
    "ports": { "out": [
        { "index": 0, "kind": "geometry", "description": "桌面几何" },
        { "index": 1, "kind": "anchors", "points": [
            { "name": "leg_mount_fr", "role": "mount" },
            { "name": "leg_mount_fl", "role": "mount" },
            { "name": "leg_mount_br", "role": "mount" },
            { "name": "leg_mount_bl", "role": "mount" } ] } ] } },
  { "id": "legs", "purpose": "四条桌腿，消费桌面锚点定位",
    "ports": { "out": [ { "index": 0, "kind": "geometry" } ],
                "in": [
                  { "from": "tabletop", "port": 1, "anchor": "leg_mount_fr" },
                  { "from": "tabletop", "port": 1, "anchor": "leg_mount_fl" },
                  { "from": "tabletop", "port": 1, "anchor": "leg_mount_br" },
                  { "from": "tabletop", "port": 1, "anchor": "leg_mount_bl" } ] } }
])
```

The builder creates, deterministically and idempotently: one subnet per
component; inside each, `out_geometry` + `out_anchors` (nulls) →
`output_0`/`output_1`; for each `ports.in[]`, an external wire + internal
`in_<from>_<anchor>` null; a core `OUT` (merge of all geometry); a "💬 Chat"
button on the core panel.

**Before calling this**, draw the dependency graph (tabletop → legs,
tabletop → apron). Every arrow is a `ports.in` entry (see Guardrail 1).

A component may declare its orientation `axis` (one of `X`/`Y`/`Z`/`-X`/`-Y`/
`-Z`; default `Y`). `verify_orientation` reads it as ground truth — declare the
axis matching how the geometry is actually generated, not what you wish.

**✅ Done when:** every declared component has a subnet, every `ports.in`
entry has a wired `in_<from>_<anchor>` input null, and the tool returned no
validation errors. Re-run is safe (idempotent).

#### 2b. Declare `design_params` (top-down, auto-created)

Pass `design_params` in the same `project_build_scaffold` call — they are
auto-created as spare parms on the core node. This is required, not optional:
without design params there is nothing to reference from geometry and nothing
to promote later.

```
project_build_scaffold(core_path="...", components=[...], design_params=[
    {"name":"length",   "label":"桌面长度",  "default":1.2,  "min":0.4, "max":3.0},
    {"name":"width",    "label":"桌面宽度",  "default":0.6,  "min":0.3, "max":1.5},
    {"name":"height",   "label":"桌高",      "default":0.75, "min":0.3, "max":1.2},
    {"name":"top_thick","label":"面板厚度",  "default":0.04, "min":0.01,"max":0.1},
    {"name":"leg_thick","label":"腿粗",      "default":0.05, "min":0.02,"max":0.2}
])
# → spare parms length/width/height/top_thick/leg_thick on the core.
```

Reference these from geometry nodes INSIDE subnets using **ABSOLUTE** `ch()`
paths (`ch('/obj/.../project_core/length')`), not relative `ch("../")` —
relative paths across subnet nesting often produce zero geometry.

**✅ Done when:** every design param exists as a spare parm on the core, and
the return includes `design_params_created` matching your count.

### 3. Model inside each subnet + `measure` anchors

Use `houdini_create_node`, `houdini_connect_nodes`, `houdini_set_param`.
Parameters are a byproduct of modeling: when you need an adjustable value, add
a spare parm on the subnet, then reference it from geometry with `ch("../...")`.

**Build the main geometry** (e.g. tabletop box referencing design params):
```
houdini_create_node(node_type="box", parent_path="<tabletop subnet>")
houdini_set_param(node_path, "sizex", "ch('/obj/.../project_core/length')")  # ABSOLUTE
houdini_connect_nodes(from_path=box_path, to_path="<tabletop>/out_geometry")
```

**`measure` anchors procedurally** (NOT hardcoded) — `project_add_anchors`:
```
project_add_anchors(core_path="<core>", component_id="tabletop", anchors=[
    { "measure": "bbox_corner", "axes": "+X-Y+Z", "name": "leg_mount_fr" },
    { "measure": "bbox_corner", "axes": "-X-Y+Z", "name": "leg_mount_fl" },
    { "measure": "bbox_corner", "axes": "+X-Y-Z", "name": "leg_mount_br" },
    { "measure": "bbox_corner", "axes": "-X-Y-Z", "name": "leg_mount_bl" }
])
# Resizing the tabletop → bbox changes → anchors recompute. LIVE.
```
Measures: `bbox_corner` (`axes`), `bbox_face_center` (`face`), `bbox_center`,
`grid_on_face` (`face`,`rows`,`cols`), `point_on_edge`, `array`.

**Consume anchors** in a downstream component — the builder already wired
`in_tabletop_leg_mount_fr`; build downstream of it:
```
houdini_create_node(node_type="tube", parent_path="<legs subnet>")
houdini_connect_nodes(from_path=tube, to_path=ctp, input_index=0)
houdini_connect_nodes(from_path="<legs>/in_tabletop_leg_mount_fr", to_path=ctp, input_index=1)
houdini_connect_nodes(from_path=ctp, to_path="<legs>/out_geometry")
```

**✅ Done when:** (a) every component's `out_geometry` has geometry flowing in;
(b) every anchor declared in step 2's `ports.out[1]` has been emitted via
`project_add_anchors`; (c) `verify_orientation` passes (no axis mismatch). If
any of these is unmet, the model is NOT done — keep going.

### 4. `promote` params to the core — `project_promote_params`

After modeling, lift subnet spare parms to the core so the whole model is
adjustable from one place:
```
project_promote_params(core_path="<core>")
# → each subnet spare parm becomes <component>_<parm> on the core (grouped),
#   subnet rewired to ch("../<component>_<parm>") — core drives.
```

**✅ Done when (the LIVE guarantee):** set one promoted parm on the core to a
new value, re-cook, and confirm the geometry + anchors updated. If changing a
core parm does not move the geometry, the two-layer `ch()` chain is broken —
do not declare done.

## Deeper references (read on demand)

The main file above is the operating manual. When you hit a specific problem,
read the matching reference (relative to this file):

| If you need... | Read |
|---|---|
| Port wiring details, `output_index`, `in_<from>_<anchor>` naming, the anchor bus diagram | `PORT_PROTOCOL.md` |
| A tool error or wrong geometry — symptom → root cause → fix | `MISTAKES.md` |
| Modeling methodology — VEX vs native node vs Python discipline | `DISCIPLINE.md` |

## When to use this

**This is the only path for multi-part procedural models.** Any object made of
parts that fit together (table, car, bicycle, keyboard, machine, building) is
built here as a Project HDA. There is no `build_assembly` tool anymore.

| Situation | Use |
|---|---|
| Any multi-part object (table=top+legs, car=body+wheels) | **Project HDA** (this skill) |
| Long-term editable model the user may hand-edit | **Project HDA** |
| Single generator / one-off SOP (no components) | `houdini_run_python_sandbox` |
