---
name: project-modeling
description: Use when the user wants to build a procedural model — anything made of MULTIPLE PARTS that fit together (a table, a car, a bicycle, a keyboard, a machine, a building). Build it as a Project HDA: declare the components, build the scaffold (empty subnets each with output ports), then model freely inside each component subnet. Components COLLABORATE via anchor point clouds — one component outputs named anchor points (@name), downstream components consume those anchors to position themselves. This is the DEFAULT modeling path for any multi-part object because the result is self-contained in one HDA, long-term editable (user can hand-edit subnets), and each component's parameters stay LIVE (change a length, the model updates). Prefer this over build_assembly for anything with more than one independent component.
---

# Project Modeling — components that collaborate via anchor ports

A procedural model is built as a **Project HDA**: one self-contained asset whose
internal network is a set of **component subnets**. Each component is a subnet
that exposes its geometry and named anchor points through output ports.
Components collaborate: one outputs anchors, the next consumes them to know
where to place itself. The whole model lives in one HDA, is editable by hand,
and every parameter stays live.

This is the **default** way to build any multi-part object. Use `build_assembly`
(rooted-modeling) only for a simple single-body-with-leaves model where you
don't need component breakdown.

## ⛔ Guardrails (read before doing anything)

**brainstorming is allowed** for modeling tasks, but it should be a FAST-PATH:
1-2 quick questions (style? size?) then delegate to this skill's workflow.
Do NOT let brainstorming run its full software-spec interview (5-10 questions +
design doc + plan) — that flow is for code, not 3D models. The brainstorming
skill itself now has a "Houdini Procedural Modeling — Fast-Path Exemption"
section; if you read it, follow that fast-path.

**Do NOT declare components as independent.** When one component physically
depends on another (e.g. legs depend on the tabletop's anchor points), you MUST
declare that dependency in `ports.in` at scaffold time. Without it, the builder
creates no input port and the downstream component cannot consume anchors — you
end up hand-placing things with transform nodes, which defeats the parametric
design. See §"Declaring cross-component dependencies" below.

## The core idea: components + anchor ports

```
Project HDA core (edini::project SOP HDA)
├─ tabletop/   (subnet, id="tabletop")
│   ├─ <your modeling nodes>
│   ├─ out_geometry  → output_0  [out[0] = main geometry]
│   └─ out_anchors   → output_1  [out[1] = anchor point cloud]
│                                   points carry @name e.g. "leg_mount_fr"
├─ legs/       (subnet, id="legs")
│   ├─ in_tabletop_leg_mount_fr  (null, builder-made, = upstream anchor)
│   ├─ <your modeling: place legs at the anchors>
│   └─ out_geometry  → output_0
└─ OUT          (core output: all components merged)
```

- **out[0] is always the component's main geometry** (it merges into the core's OUT).
- **out[1+] are anchor point clouds**: points carrying `@P` (position), `@orient`
  (quaternion), and `@name` (the anchor's identity — e.g. `leg_mount_fr`). These
  are how one component tells another "put things HERE".
- A downstream component consumes an upstream anchor by connecting to the
  upstream subnet's output port 1 (`output_index=1`).

## The workflow (deterministic steps)

The agent drives this via THREE dedicated tools plus the standard node tools.
This is the only modeling path — there is no build_assembly anymore.

### 1. Create the project — `project_create`
```
project_create(name="project_table", goal="a small table")
  → returns { core_path: "/obj/project_table/project_core", ... }
```
Call this FIRST. **Workspace-aware**: if the user has a Project HDA core selected
in the network editor, project_create REUSES it (returns its path, doesn't
create new) — so "select a Project HDA → work in it" is the natural flow. Only
creates new when nothing relevant is selected. Remember the returned `core_path`.

### 2. Declare components + build scaffold — `project_build_scaffold`
Pass `core_path` and `components` (the decomposition). Each component has an
`id` (= subnet name), `purpose`, and `ports`.

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
The builder creates, **deterministically and idempotently**:
- One subnet per component (`tabletop/`, `legs/`) — **id = subnet name**
- Inside each: `out_geometry` + `out_anchors` (nulls) → `output_0`/`output_1`
- For each `ports.in[]`: external wire + internal `in_<from>_<anchor>` null
- A core `OUT` (merge of all component geometry) with display flag
- A "💬 Chat with Edini" button on the core's parameter panel (click → chat popup)

#### Optional: per-component orientation `axis`
A component may declare its construction orientation with `"axis"` (one of
`"X"`, `"Y"`, `"Z"`, `"-X"`, `"-Y"`, `"-Z"`; default `"Y"`). The scaffold bakes
it as `edini_world_axis` and `verify_orientation` reads it as ground truth — so
declare the axis that matches how the geometry is **actually generated**, not
what you wish it were. Common cases:
- `"Y"` (default): anything flat-on-ground or standing up — seat, tabletop,
  legs, wheels-on-ground.
- `"Z"`: a side-facing panel — a **backrest** facing +Z, a side board.
- `"X"`: a transverse part — an axle, a crossbar.

```python
{ "id": "backrest", "axis": "Z", "purpose": "靠背，朝 +Z 的侧立面板", "ports": {...} }
```
Get this wrong and `verify_orientation` will fail with a 90° axis mismatch even
though the geometry looks right (PCA will flag the divergence). To change it
later, update the declaration's `axis` and re-run `project_build_scaffold` — do
NOT edit the internal `__edini_axis_bake` node (it's locked; the declaration is
the source of truth).

The builder does NOT build geometry or parameters — those are your job, bottom-up.

#### ⚠️ Declaring cross-component dependencies (CRITICAL — do not skip)

If component B physically depends on component A (B needs A's anchors to know
where to place itself), you MUST declare it in B's `ports.in`. **A missing
`ports.in` is the #1 cause of broken parametric models** — without it the
builder creates no `in_<from>_<anchor>` input port, so B cannot consume A's
anchors, and you are forced to hand-place B with transform nodes (which breaks
when A's parameters change).

**Wrong** (legs declared independent — they'll float in space, disconnected):
```
{ "id": "legs", "ports": { "out": [{"index":0,"kind":"geometry"}], "in": [] } }
```

**Right** (legs consume tabletop's anchors — builder wires `in_tabletop_<anchor>`):
```
{ "id": "legs", "ports": {
    "out": [{"index":0,"kind":"geometry"}],
    "in": [
      { "from": "tabletop", "port": 1, "anchor": "leg_mount_fr" },
      { "from": "tabletop", "port": 1, "anchor": "leg_mount_fl" },
      { "from": "tabletop", "port": 1, "anchor": "leg_mount_br" },
      { "from": "tabletop", "port": 1, "anchor": "leg_mount_bl" } ] } }
```

Rule: **before calling `project_build_scaffold`, draw the dependency graph on
paper** (tabletop → legs, tabletop → apron). Every arrow becomes a `ports.in`
entry. If a component has NO upstream dependency (rare — only the root), its
`in` can be `[]`.

### 2b. Declare design params (RECOMMENDED — top-down, auto-created)

Pass `design_params` to `project_build_scaffold` and they are **automatically
created as spare parms on the core node**. This is the recommended path — you
don't need `project_promote_params` or manual spare-parm creation.

```
project_build_scaffold(core_path="...", components=[...], design_params=[
    {"name":"length",   "label":"桌面长度",  "default":1.2,  "min":0.4, "max":3.0},
    {"name":"width",    "label":"桌面宽度",  "default":0.6,  "min":0.3, "max":1.5},
    {"name":"height",   "label":"桌高",      "default":0.75, "min":0.3, "max":1.2},
    {"name":"top_thick","label":"面板厚度",  "default":0.04, "min":0.01,"max":0.1},
    {"name":"leg_thick","label":"腿粗",      "default":0.05, "min":0.02,"max":0.2}
])
# → spare parms length/width/height/top_thick/leg_thick auto-created on the core.
# → return includes "design_params_created": 5
```

After scaffold, reference these from geometry nodes INSIDE component subnets
using **ABSOLUTE paths** (relative `ch("../")` is unreliable across subnet nesting):

```
# Inside tabletop/body_box (a box SOP inside the tabletop subnet):
houdini_set_params_batch(node_path=".../tabletop/body_box", params={
    "sizex": "ch('/obj/.../project_core/length')",       # ABSOLUTE path
    "sizey": "ch('/obj/.../project_core/top_thick')",
    "sizez": "ch('/obj/.../project_core/width')",
    "ty":    "ch('/obj/.../project_core/top_thick')*0.5"
})
```

**⚠️ Use ABSOLUTE ch() paths** (e.g. `ch('/obj/geo1/project1/length')`), NOT
relative (`ch('../../length')`). Relative paths across subnet nesting levels
often produce "Bad parameter reference" warnings and zero geometry. The core
path is in the `[Current Houdini Context]` block of every message — use it.

### 3. Model inside each component subnet — standard node tools
Use `houdini_create_node`, `houdini_connect_nodes`, `houdini_set_param`. Model
freely inside each subnet. **Parameters are a byproduct of modeling**: when you
need an adjustable value, add a spare parm ON THE SUBNET (via houdini_set_param
on the subnet node, or addSpareParmTuple), then reference it from your geometry
nodes with `ch("../<parm>")`.

**Build the main geometry** (e.g. tabletop box, with an adjustable length):
```
# 1. Add a spare parm on the SUBNET (parameters are a byproduct of modeling).
houdini_set_param(node_path="<tabletop subnet>", "length", 2.0)  # creates a spare parm
# 2. Build geometry referencing the subnet's parm.
houdini_create_node(node_type="box", parent_path="<tabletop subnet>")
houdini_set_param(node_path, "sizex", 'ch("../length")')   # LIVE ref to subnet parm
houdini_set_param(node_path, "sizey", 0.05)
houdini_connect_nodes(from_path=box_path, to_path="<tabletop>/out_geometry")
```

**Emit anchors PROCEDURALLY** (NOT hardcoded!) — `project_add_anchors`:
```
# Anchors must be DERIVED FROM GEOMETRY (so they move when params change),
# never hardcoded addpoint coordinates. project_add_anchors generates a live
# VEX wrangle that measures the component's bbox on every cook.
project_add_anchors(core_path="<core>", component_id="tabletop", anchors=[
    { "measure": "bbox_corner", "axes": "+X-Y+Z", "name": "leg_mount_fr" },
    { "measure": "bbox_corner", "axes": "-X-Y+Z", "name": "leg_mount_fl" },
    { "measure": "bbox_corner", "axes": "+X-Y-Z", "name": "leg_mount_br" },
    { "measure": "bbox_corner", "axes": "-X-Y-Z", "name": "leg_mount_bl" }
])
# Now resizing the tabletop (change core 'length') → bbox changes → anchors recompute.
```
Available measures: `bbox_corner` (needs `axes` like "+X-Y+Z"), `bbox_face_center`
(needs `face` like "-Y"), `bbox_center`, `grid_on_face` (needs `face`,`rows`,`cols`),
`point_on_edge`, `array`. Each emits point(s) tagged with `@name`.

**Consuming anchors** (in the downstream component, e.g. legs):
```
# the builder already wired in_tabletop_leg_mount_fr to the upstream anchor.
# Just build downstream of it.
houdini_create_node(node_type="tube", parent_path="<legs subnet>")   # a leg
houdini_set_param(node_path, "rad", [0.04, 0.04])     # vector parm
houdini_set_param(node_path, "height", 'ch("../leg_height")')  # LIVE expression
houdini_create_node(node_type="copytopoints", parent_path="<legs subnet>")
houdini_connect_nodes(from_path=tube_path, to_path=ctp_path, input_index=0)
houdini_connect_nodes(from_path="<legs>/in_tabletop_leg_mount_fr", to_path=ctp_path, input_index=1)
houdini_connect_nodes(from_path=ctp_path, to_path="<legs>/out_geometry")   # main geometry out
```

To grab an upstream component's anchor port directly (not via the builder's
in-node), use `output_index`:
```
houdini_connect_nodes(from_path="<tabletop>", to_path="<something>", input_index=0, output_index=1)
# output_index=1 = tabletop's anchor cloud (out[1]); 0 = its main geometry
```

### 4. Promote params to the core (bottom-up) — `project_promote_params`
After modeling (when subnet spare parms exist + tested), lift them to the core
HDA so the whole model is adjustable from one place:
```
project_promote_params(core_path="<core>")
# scans each subnet's spareParms() → creates <component>_<parm> on the core
# (grouped under a <component> folder, with min/max copied) → rewires the subnet
# parm to ch("../<component>_<parm>") so the core drives it.
```
Bottom-up: params originate in subnets (where you model + test them), then get
promoted to the core for unified control. The core becomes the adjustment
entry point; subnets follow via ch() refs.

## Parameter LIVE references (bottom-up, core drives after promote)

Parameters originate on component subnets (spare parms you add while modeling).
After `project_promote_params`, each is lifted to the core as
`<component>_<parm>` (grouped, with min/max), and the subnet parm is rewired to
`ch("../<component>_<parm>")` — so the CORE drives the value.

| Where you are | What you reference | Example |
|---|---|---|
| A geometry node INSIDE a subnet | the subnet's parm | a box in `tabletop/` uses `ch("../length")` |
| The user (after promote) | the core's `<component>_<parm>` | user sets `tabletop_length` → subnet follows → geometry + anchors update |

`houdini_set_param` accepts expression strings containing `ch(...)` and routes
them to `setExpression` automatically — so LIVE params work through the tool.

## When to use this

**This is the ONLY path for multi-part procedural models.** build_assembly no
longer exists as a tool — do not attempt to call it. Any object made of parts
that fit together (a table, car, bicycle, keyboard, machine, building) is built
here as a Project HDA.

| Situation | Use |
|---|---|
| **Any multi-part object** (table=top+legs, car=body+wheels, keyboard=tray+keys) | **Project HDA** (this skill): project_create → project_build_scaffold → model in subnets → project_promote_params |
| **Long-term editable model** the user may hand-edit | **Project HDA** |
| Single generator / one-off SOP (no components) | houdini_run_python_sandbox |

Even a "simple" table is a multi-part object (top + legs): decompose it into
components and build it here. The component breakdown is what makes the model
understandable, editable, and (later) drift-detectable.

## Modeling discipline (direction — refined with real cases)

- **VEX first**: most needs are a wrangle + native SOPs. Don't reach for Python SOPs.
- **No single-SOP Python dumps**: if you use Python, spread it across SOPs, don't pile everything into one.
- **Native nodes where VEX is hard** (sweep, fuse, boolean): use the native node.
- **Measure, don't hardcode**: positions come from upstream anchors or measurements, never typed coordinates. This is what keeps the model parametric.

## Common mistakes

| Mistake | Fix |
|---|---|
| **Anchors don't move when you resize the component** | You hardcoded `addpoint(x,y,z)`. Use `project_add_anchors` so anchors are measured from geometry and recompute live. NEVER hardcode anchor coordinates. |
| Box can't read a param | inside a subnet, add the parm ON THE SUBNET (houdini_set_param on the subnet node), then reference it from geometry with `ch("../length")`. |
| connect_nodes can't reach the anchor cloud | pass `output_index=1` (default 0 = main geometry) |
| Param has no min/max on the core | add the spare parm on the subnet WITH min/max (FloatParmTemplate), then promote copies them up. |
| project_create made a new HDA instead of using the selected one | project_create reuses a selected Project HDA core. To force new, deselect first. |
| Built geometry but nothing shows at core OUT | your geometry must feed into `out_geometry` → `output_0` → core's OUT merge |

## What this supports (and what's coming)

- ✅ Component subnets with 2 output ports (geometry + anchors), idempotent scaffold
- ✅ Cross-component anchor consumption (builder wires `in_<from>_<anchor>`)
- ✅ Two-layer live params (subnet `../` + core `./` via promote)
- ✅ Tools: create_node / connect_nodes (with output_index) / set_param (vector + expression)
- 🚧 Drift detection (hand-edit awareness) — future
- 🚧 Knowledge-graph description generation — future
