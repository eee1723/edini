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

### 1. Open a project
```python
# via tool: project tools, or Python shell
from edini.project.node import create_project_hda
core = create_project_hda(name="project_table", goal="a table")
# → /obj/project_table/project_core  (the SOP HDA you build inside)
```

### 2. Declare the components
Describe what components exist and how they connect. Each component has an `id`
(= its subnet name), a `purpose`, output ports, and optional input ports
(what upstream anchors it consumes).

```python
from edini.project.state import empty_declaration, add_component
decl = empty_declaration("project_table", goal="a table")
add_component(decl, "tabletop", purpose="桌面，输出四条腿的安装锚点",
    ports_out=[
        {"index": 0, "kind": "geometry", "description": "桌面几何"},
        {"index": 1, "kind": "anchors", "points": [
            {"name": "leg_mount_fr", "role": "mount", "description": "前右桌腿点"},
            {"name": "leg_mount_fl", "role": "mount", "description": "前左桌腿点"},
            {"name": "leg_mount_br", "role": "mount", "description": "后右桌腿点"},
            {"name": "leg_mount_bl", "role": "mount", "description": "后左桌腿点"}]}])
add_component(decl, "legs", purpose="四条桌腿，消费桌面锚点定位",
    ports_in=[
        {"from": "tabletop", "port": 1, "anchor": "leg_mount_fr"},
        {"from": "tabletop", "port": 1, "anchor": "leg_mount_fl"},
        {"from": "tabletop", "port": 1, "anchor": "leg_mount_br"},
        {"from": "tabletop", "port": 1, "anchor": "leg_mount_bl"}])
```

### 3. Build the scaffold
```python
# tool: project_build_scaffold (pass the declaration)
from edini.project.builder import build_project_scaffold
build_project_scaffold(core, declaration=decl)
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

### 4. Model inside each component subnet
Use the standard node tools (`houdini_create_node`, `houdini_connect_nodes`,
`houdini_set_param`). Key points specific to this paradigm:

**Emitting anchors** (in the upstream component, e.g. tabletop):
```python
# an attribwrangle that adds points at the table corners, tagged with @name
houdini_create_node(attribwrangle, parent=<tabletop subnet path>)
houdini_set_param(node, "snippet", '<VEX: addpoint + setpointattrib name>')
houdini_set_param(node, "class", "detail")   # MUST be detail for addpoint
houdini_connect_nodes(wrangle, "<tabletop>/out_anchors")  # feed into the anchor port
```

**Consuming anchors** (in the downstream component, e.g. legs):
```python
# the builder already wired in_tabletop_leg_mount_fr to the upstream anchor.
# Just build downstream of it.
shape = houdini_create_node(tube, parent=<legs subnet path>)   # a leg
houdini_set_param(shape, "rad", [0.04, 0.04])     # vector parm
houdini_set_param(shape, "height", 'ch("../leg_height")')  # LIVE expression
ctp = houdini_create_node(copytopoints, parent=<legs subnet path>)
houdini_connect_nodes(shape, ctp, input_index=0)
houdini_connect_nodes("<legs>/in_tabletop_leg_mount_fr", ctp, input_index=1)
houdini_connect_nodes(ctp, "<legs>/out_geometry")   # main geometry out
```

To grab an upstream component's anchor port directly (not via the builder's
in-node), use `output_index`:
```python
houdini_connect_nodes("<tabletop>", "<something>", input_index=0, output_index=1)
# output_index=1 = tabletop's anchor cloud (out[1]); 0 = its main geometry
```

### 5. Promote parameters to the top
After modeling, lift each component's spare parms to the core HDA interface so
the whole model is adjustable from one place:
```python
# tool: project_promote_params (or builder.promote_params)
from edini.project.builder import promote_params
promote_params(core)
# → core gets tabletop_length, legs_leg_height, etc., each driving its subnet live
```

## Parameter LIVE references (two layers, both relative)

| Where you are | Reference direction | Example |
|---|---|---|
| A node INSIDE a component subnet → its own subnet's parm | `../<parm>` | a box in `tabletop/` uses `ch("../length")` |
| The core HDA → a component subnet's parm | `./<component>/<parm>` | core's `tabletop_length` = `ch("./tabletop/length")` (promote builds this) |

`houdini_set_param` accepts expression strings containing `ch(...)` and routes
them to `setExpression` automatically — so LIVE params work through the tool.

## When to use this vs build_assembly

| Situation | Use |
|---|---|
| **Multi-part object, parts are independent components** (table = top + legs; car = body + wheels + lights) | **Project HDA** (this skill) |
| **Long-term editable model** the user may hand-edit | **Project HDA** |
| **Simple single body with leaves hanging off** (one box + 4 wheels measured from it, no real component breakdown) | build_assembly (rooted-modeling) — lighter, one shot |
| Single generator / one SOP | houdini_run_python_sandbox |

**Default to Project HDA** for any object with more than one independent
component. The component breakdown is what makes the model understandable,
editable, and drift-detectable later.

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
