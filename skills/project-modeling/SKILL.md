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
Always call this FIRST. It creates the edini::project SOP HDA you build inside.
Remember the returned `core_path` — every later step needs it.

### 2. Declare components + design params + build scaffold — `project_build_scaffold`
Pass `core_path`, `components` (the decomposition), and `design_params` (the
adjustable parameters). The **core is the single source of truth for params** —
each design_param becomes a core-level parm with default/min/max; component
subnets reference them via `ch("../<name>")` after promote.

```
project_build_scaffold(core_path="/obj/project_table/project_core",
  design_params=[
    { "name": "length", "default": 2.0, "min": 0.5, "max": 10, "label": "桌长" },
    { "name": "width",  "default": 1.0, "min": 0.3, "max": 5,  "label": "桌宽" },
    { "name": "leg_height", "default": 0.75, "min": 0.2, "max": 3, "components": ["legs"] }
  ],
  components=[
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
- **Core-level design_params** (with default/min/max) under a "Design" folder —
  these are the source of truth; subnets get references after promote
- A core `OUT` (merge of all component geometry) with display flag

The builder does NOT build geometry — that's your job, freely, inside each subnet.

### 3. Promote params (wire subnets to core) — `project_promote_params`
After scaffold, run promote so each component subnet that uses a design_param
gets a reference parm (`ch("../<name>")` pointing at the core). Do this BEFORE
modeling, so your in-subnet nodes can `ch("../<name>")` and have it resolve.
```
project_promote_params(core_path="/obj/project_table/project_core")
# now tabletop.length = ch("../length"), legs.leg_height = ch("../leg_height")
```

### 4. Model inside each component subnet — standard node tools
Use `houdini_create_node`, `houdini_connect_nodes`, `houdini_set_param`. Inside
a subnet, reference the component's (promoted) params with `ch("../<name>")`.

**Build the main geometry** (e.g. tabletop box, driven by core params):
```
houdini_create_node(node_type="box", parent_path="<tabletop subnet>")
houdini_set_param(node_path, "sizex", 'ch("../length")')   # LIVE ref to core param
houdini_set_param(node_path, "sizez", 'ch("../width")')
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

## Parameter LIVE references (core is the source)

The core HDA owns the parameter values (default/min/max, defined via
`design_params` in build_scaffold). Component subnets REFERENCE them. After
`project_promote_params`, each using subnet has a parm with expression
`ch("../<name>")` pointing at the core. So inside a subnet, your nodes use
`ch("../<name>")` to read the core-driven value.

| Where you are | What you reference | Example |
|---|---|---|
| A node INSIDE a component subnet | the subnet's promoted parm (= core's) | a box in `tabletop/` uses `ch("../length")` |
| The core HDA (user adjusts here) | the core's own parm (source) | user sets `length` on the core → all subnets follow |

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
| Box can't read a param | inside a subnet, reference the core's param via the subnet's promoted parm: `ch("../length")`. Run `project_promote_params` first so the subnet parm exists. |
| connect_nodes can't reach the anchor cloud | pass `output_index=1` (default 0 = main geometry) |
| Param has no min/max on the core | define it via `design_params` in build_scaffold (`{name,default,min,max}`), not by adding a bare spare parm. |
| Built geometry but nothing shows at core OUT | your geometry must feed into `out_geometry` → `output_0` → core's OUT merge |

## What this supports (and what's coming)

- ✅ Component subnets with 2 output ports (geometry + anchors), idempotent scaffold
- ✅ Cross-component anchor consumption (builder wires `in_<from>_<anchor>`)
- ✅ Two-layer live params (subnet `../` + core `./` via promote)
- ✅ Tools: create_node / connect_nodes (with output_index) / set_param (vector + expression)
- 🚧 Drift detection (hand-edit awareness) — future
- 🚧 Knowledge-graph description generation — future
