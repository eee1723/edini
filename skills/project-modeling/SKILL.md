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
when parameters change. Never type a literal coordinate like
`addpoint(0, {0.5,0,0})` or `addpoint(0, set(0.225,0,0.225))`. The platform
guard **refuses** literal-coordinate `addpoint` inside a Project HDA component
— you will see a `Refused: hardcoded-coordinate addpoint ...` error. Note:
`addpoint` with a **computed** position (`set(i-base,...)*step`, `@P`,
`chf(...)`) is fine and is the normal way to generate procedural geometry
(grids, stickers, scatter); only typed-in number coordinates are refused.

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

**Split vs. merge — decide deliberately.** Components are for PARTS that
physically attach and must track each other (table + legs, car body + wheels);
declare `ports.in` between them. If two "components" are really one object
(e.g. a cube + its surface stickers), **merge them into one component** rather
than splitting — otherwise each independently re-derives the same formula from
shared params and can drift. A 2+ component project with no `ports.in` surfaces
a non-blocking `coupling_advisory: independent_components` in
`project_status` / `project_finalize` as a prompt to reconsider.

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

#### 2c. Declare structural intent (`structure`) — always declare it

Each component in the `project_build_scaffold` call may carry a `structure`
block. A component with a **MALFORMED** `structure` (bad `kind`, missing
`expected_axis` for radial/planar, `repeated` without `repeats[]`) is refused
at scaffold time — the mistake is caught before any geometry is built. A
component with **NO** `structure` is allowed through, but you lose the F3 axis
check (see below). **Always declare it** — declaring `kind` + `expected_axis`
is the only way F3 fires, and F1/F2/F4 enforce regardless.

```jsonc
{"id": "front_wheel",
 "structure": {
    "kind": "radial",              // radial | planar | repeated | solid
    "expected_axis": "Z",          // required for radial | planar (X|Y|Z|-X|-Y|-Z)
    "repeats": [                   // repeated sub-parts + how they're instanced
      {"part": "spoke", "count": 28, "method": "copytopoints"}
    ]
 }}
```

This declaration drives the structural checks `analyze_component_structure`
runs, and that `project_finalize` enforces as **Gate 4** (F1–F4 fatal verdicts
are NOT bypassable by `acknowledge_skip` — they block finalize even on the skip
path; use `structure_override=True` + a non-empty `structure_reason` only for a
genuinely atypical structure, and the override is audited to the declaration
log):

- **F1 — repeated parts must be instanced via Copy-to-Points** (even 2
  instances). Two wheels, four legs, N spokes: ONE template + Copy-to-Points,
  never hand-duplicated subnets or Python-SOP loops emitting each copy. Declare
  each in `repeats` with `method: "copytopoints"`.
- **F2 — no bare curve/surface primitives at `out_geometry`.** Construction
  curves must go through PolyWire/Sweep (tubes), or be Blasted — don't leave
  skeleton curves wired to the output.
- **F3 — radial/planar parts declare their axis** (`expected_axis`), checked
  against the baked `edini_world_axis` via `verify_orientation`. This check
  ONLY runs when you declared `kind` + `expected_axis` — another reason to
  always declare.
- **F4 — Copy-to-Points target points need `orient` / `N` / `up`**, or copies
  inherit identity orientation (candles/wheels pointing the wrong way).

`kind` guide: wheels/gears/tires → `radial`. tabletops/plates → `planar`.
spokes/legs/candles/rivets → `repeated`. a single box body → `solid`.

Self-check anytime with `analyze_component_structure(core_path)` (omit
`component_id` to scan every component, or pass `...component_id` for one)
before finalizing — it returns `{fatal:[...], advisory:[...], overall}`; fix
the `fatal` set during the build so Gate 4 passes at finalize.

**✅ Done when:** every component you scaffold carries a `structure` block with
a valid `kind` (+ `expected_axis` for radial/planar, + `repeats[]` for
repeated), and `analyze_component_structure` returns no `fatal` findings.

### 3. Model inside each subnet + `measure` anchors

**Prefer `project_emit_component` (archetype) over raw nodes** when the component
matches one of:
- **`box_panel`** — a parametric box (tabletop / seat / panel): `size=[x,y,z]`.
- **`copy_array`** — stamp a leaf onto consumed anchors (legs / spokes / keys).
- **`tube_graph`** — connected tubes between named anchors (frame / fork / bars).

Each archetype builds + wires the chain for you (idempotent, design-param-aware
via **RELATIVE `ch()`** — so archetype-built components are migratable across
projects, zero Python-SOP error surface). Fall back to raw `houdini_create_node` /
`houdini_connect_nodes` / `houdini_set_param` only when NO archetype fits
(then follow `COMPONENT_TEMPLATE.md`'s Python SOP skeleton).

**Before a risky change to a component, snapshot it** via
`project_snapshot_component` — then `project_restore_component` reverts to the
saved version if the new iteration is worse (selective multi-round optimization
without re-running the whole project).

Use `houdini_create_node`, `houdini_connect_nodes`, `houdini_set_param`.
**Reference design params from geometry via ABSOLUTE `ch()` to the core**
(`ch('/obj/.../project_core/length')`) — this is the only official
parameterization path. Do NOT create subnet spare parms and do NOT use
relative `ch("../...")` here; that is the bottom-up path Step 4 `promote`
was designed for, and the two are mutually exclusive (see Step 4's note).
The absolute path is the stable default; `project_repath_to_relative` (Step 4)
can later convert a component to relative paths if you need to migrate it to
another project.

**VEX + native SOPs first; Python SOP only when geometry is genuinely
algorithmic** (a tube graph, a spoked wheel, curved bars). When you DO write a
Python SOP inside a component, **copy the skeleton in
`COMPONENT_TEMPLATE.md`** — it encodes the five Python-SOP errors that recurred
most across real sessions (bare `return`, attribute-before-write, input-vs-output
geometry, `createPoint` signature, `ch` vs `hou.ch`). Do not write a Python SOP
from a blank string; you will re-break one of those five.

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

### 4. Verify parametricity — `verify_parametric` (the LIVE guarantee)

The historical `project_promote_params` lifted subnet spare parms to the core
(a bottom-up path). **It is a no-op under the official design_params path
(Step 2b + absolute `ch()`):** you never create subnet spare parms, so there is
nothing to promote, and it returns `promoted: []`. That empty result is
**correct, not a failure** — the design params already live on the core and
geometry already references them directly. Do NOT call `promote` expecting it
to "fix" parametricity; it has nothing to do in this workflow.

The actual completion gate for parametricity is `verify_parametric` (Layer C2).
It **proves** a design param reaches the geometry by perturbation:

```
verify_parametric(node_path="<core>/OUT", core_path="<core>",
                  param="length", new_value=<a different value>,
                  expected_axis="X")
# → perturbs length, recooks, checks the geometry moved on X (>= 5% relative
#   change), then RESTORES the original value. Non-destructive.
```

**✅ Done when (the LIVE guarantee):** `verify_parametric` returns
`passed: true` for the design params components reference. If it returns
`passed: false`, the param chain is broken (a broken `ch()` reference, the
param wired to the wrong node) — do not declare done. `inspect_health`'s
`overall_ok` is NOT enough — it only proves "not broken now", not "parametric".

#### 4b. (Optional) Make a component migratable — `project_repath_to_relative`

The absolute `ch('/obj/.../project_core/<p>')` references tie a component to its
current project path. If you want to **reuse/migrate** a component subnet into
another project (copy-paste), convert its absolute references to relative ones:

```
project_repath_to_relative(core_path="<core>", component_id="<id>")
# → rewrites every ch('/obj/.../project_core/<p>') inside <id> to a relative
#   reference (ch("../../<p>") — the exact depth is computed from the node's
#   path to the core). The component now references its core by relative
#   position, not absolute path — copy the subnet elsewhere and it still
#   cooks (as long as a <project_core> node sits at the same relative depth,
#   which the project HDA structure guarantees).
```

This is **optional and on-demand**. Leave components on absolute paths unless
you specifically intend to migrate them — absolute paths are the stable default
(relative `ch("../")` across subnet nesting has historically produced
zero-geometry bugs; see `MISTAKES.md`).

## Deeper references (read on demand)

The main file above is the operating manual. When you hit a specific problem,
read the matching reference (relative to this file):

| If you need... | Read |
|---|---|
| Port wiring details, `output_index`, `in_<from>_<anchor>` naming, the anchor bus diagram | `PORT_PROTOCOL.md` |
| To write a Python SOP inside a component — the copy-paste skeleton + the 5 recurring errors | `COMPONENT_TEMPLATE.md` |
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
