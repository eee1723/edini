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

### 2. Declare components + build scaffold — `project_build_scaffold`
Pass `core_path` (from step 1) and `components` (the decomposition). Each
component has an `id` (= its future subnet name), a `purpose`, output ports,
and optional input ports (what upstream anchors it consumes).

```
project_build_scaffold(core_path="/obj/project_table/project_core", components=[
  { "id": "tabletop", "purpose": "桌面，输出四条腿的安装锚点",
    "ports": { "out": [
        { "index": 0, "kind": "geometry", "description": "桌面几何" },
        { "index": 1, "kind": "anchors", "points": [
            { "name": "leg_mount_fr", "role": "mount", "description": "前右桌腿点" },
            { "name": "leg_mount_fl", "role": "mount", "description": "前左桌腿点" },
            { "name": "leg_mount_br", "role": "mount", "description": "后右桌腿点" },
            { "name": "leg_mount_bl", "role": "mount", "description": "后左桌腿点" } ] } ] } },
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
  (output nodes forming the subnet's 2 output ports)
- For each `ports.in[]` entry: an external wire (`legs` input ← `tabletop`
  output 1) + an internal named null `in_<from>_<anchor>`
  (e.g. `in_tabletop_leg_mount_fr`) so you can grab the upstream anchor without
  knowing Houdini's indirectInputs mechanism.

The builder does NOT build geometry — that's your job, freely, inside each subnet.

### 3. Model inside each component subnet — standard node tools
Use `houdini_create_node`, `houdini_connect_nodes`, `houdini_set_param` inside
each component's subnet path (e.g. `/obj/project_table/project_core/tabletop`).
Key points specific to this paradigm:

**Emitting anchors** (in the upstream component, e.g. tabletop):
```
# an attribwrangle that adds points at the table corners, tagged with @name
houdini_create_node(node_type="attribwrangle", parent_path="<tabletop subnet>")
houdini_set_param(node_path, "snippet", '<VEX: addpoint(0, set(x,y,z)); setpointattrib(0,"name",0,"leg_mount_fr","set");>')
houdini_set_param(node_path, "class", "detail")   # MUST be detail for addpoint
houdini_connect_nodes(from_path=wrangle_path, to_path="<tabletop>/out_anchors")
```

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

### 4. Promote parameters to the top — `project_promote_params`
After modeling, lift each component's spare parms to the core HDA interface so
the whole model is adjustable from one place:
```
project_promote_params(core_path="/obj/project_table/project_core")
# → core gets tabletop_length, legs_leg_height, etc., each driving its subnet live
```

## Parameter LIVE references (two layers, both relative)

| Where you are | Reference direction | Example |
|---|---|---|
| A node INSIDE a component subnet → its own subnet's parm | `../<parm>` | a box in `tabletop/` uses `ch("../length")` |
| The core HDA → a component subnet's parm | `./<component>/<parm>` | core's `tabletop_length` = `ch("./tabletop/length")` (promote builds this) |

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
| `addpoint` in wrangle produces 0 points | `class` parm must be `detail`, not `points` |
| Box can't read `length` | inside a subnet, reference the subnet's parm with `ch("../length")` (parent), not `ch("./length")` |
| connect_nodes can't reach the anchor cloud | pass `output_index=1` (default 0 = main geometry) |
| promote didn't lift a parm | the parm must be a spare parm ON the component subnet first, then run promote |
| Built geometry but nothing shows at core OUT | your geometry must feed into `out_geometry` → `output_0` → core's OUT merge |

## What this supports (and what's coming)

- ✅ Component subnets with 2 output ports (geometry + anchors), idempotent scaffold
- ✅ Cross-component anchor consumption (builder wires `in_<from>_<anchor>`)
- ✅ Two-layer live params (subnet `../` + core `./` via promote)
- ✅ Tools: create_node / connect_nodes (with output_index) / set_param (vector + expression)
- 🚧 Drift detection (hand-edit awareness) — future
- 🚧 Knowledge-graph description generation — future
