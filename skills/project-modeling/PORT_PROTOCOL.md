# Port Protocol — the anchor bus between components

> Read this when wiring components together, using `output_index`, or
> debugging why a downstream component cannot see upstream anchors.

## The structure

Each component is a subnet with two output ports:

```
Component subnet (id="tabletop")
├─ <your modeling nodes>          ← you build geometry here
├─ out_geometry  (null)  → output_0   [out[0] = MAIN GEOMETRY]
├─ out_anchors   (null)  → output_1   [out[1] = ANCHOR POINT CLOUD]
│                                         points carry @name, @P, @orient
└─ tag_component / __edini_axis_bake     [platform nodes — do not edit]
```

- **`out[0]` is always the component's main geometry.** It merges into the
  core's `OUT` node. This is what the user sees.
- **`out[1]` is the anchor point cloud.** Each point carries:
  - `@P` — the anchor's position (measured from geometry)
  - `@orient` — a quaternion giving the anchor's orientation
  - `@name` — the anchor's identity (e.g. `leg_mount_fr`)

Anchors are how one component tells another "put things HERE, oriented THIS
way". They are the **inter-component information bus** — components never
communicate through coordinates, only through named anchors.

## What `scaffold` creates (the platform's deterministic part)

When you call `project_build_scaffold` with a component declaration, the
builder creates — idempotently, every time:

1. **One subnet per component** (`tabletop/`, `legs/`). The component `id`
   becomes the subnet name.
2. **Inside each subnet:** `out_geometry` + `out_anchors` (two nulls) →
   `output_0` / `output_1` (two output nodes). These four nodes form the two
   subnet output ports.
3. **For each `ports.in[]` entry:** an external wire from the upstream
   component's output port to this subnet, PLUS an internal
   `in_<from>_<anchor>` null that makes the upstream anchor available inside
   this subnet.
4. **A core `OUT`** node: merges every component's `out[0]` (main geometry)
   into the core's single output. Has the display flag.
5. **A "💬 Chat" button** on the core's parameter panel.

The builder **never** builds geometry, parameters (beyond design_params), or
cross-subnet anchor wiring beyond the declared `ports.in`. Those are yours.

## Consuming an upstream anchor

Two ways to reach an upstream component's anchors:

**Way 1 — via the builder-wired input null (recommended):**
The builder created `in_<from>_<anchor>` inside the downstream subnet. Connect
your geometry downstream of it:
```
houdini_connect_nodes(
    from_path="<legs>/in_tabletop_leg_mount_fr",  # builder-made input null
    to_path="<legs>/copy_to_points",
    input_index=1)  # input 1 of copy-to-points = target points
```

**Way 2 — directly from the upstream subnet's output port:**
Use `output_index` to pick which output of the upstream subnet you want:
```
houdini_connect_nodes(
    from_path="<tabletop>",      # the upstream SUBNET (not an inner node)
    to_path="<something>",
    input_index=0,
    output_index=1)              # 1 = anchor cloud (out[1]); 0 = main geometry
```

**`output_index` cheat sheet:**
| `output_index` | What you get |
|---|---|
| `0` (default) | the upstream component's **main geometry** |
| `1` | the upstream component's **anchor point cloud** |

## The `ports.in` declaration (Guardrail 1 in detail)

When component B needs component A's anchors, B's declaration must list them:
```json
{ "id": "legs",
  "ports": {
    "out": [{"index": 0, "kind": "geometry"}],
    "in": [
      {"from": "tabletop", "port": 1, "anchor": "leg_mount_fr"},
      {"from": "tabletop", "port": 1, "anchor": "leg_mount_fl"}
    ]
  }
}
```
- `from` — the upstream component's `id`.
- `port` — which output port of the upstream (`1` = anchors).
- `anchor` — the `@name` of the specific anchor point to wire.

Each `ports.in` entry becomes one `in_<from>_<anchor>` input null inside the
downstream subnet. A missing entry = no input null = the anchor is invisible
inside B = B is forced to hand-place (which breaks parametricity).

**Validation:** `ports.in[].anchor` names must be unique within a component
(they form node names) and must match `[A-Za-z][A-Za-z0-9_]*`.
