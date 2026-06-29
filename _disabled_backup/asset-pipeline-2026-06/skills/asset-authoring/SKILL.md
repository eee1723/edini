---
name: asset-authoring
description: Use when the user wants a procedural/parametric model (a chair, a table, a bike frame, anything with dimensions the user may want to change). Author a declarative asset JSON instead of hand-building a node network — describe the params, the skeleton points (where things sit), and the components (what each part is). Then validate_asset + build_asset turn it into Houdini geometry. This is more reliable than authoring nodes because every dimension stays parametric and the asset validates before a single node is created.
---

# Asset Authoring — declarative parametric models

An **asset** describes a parametric object in three layers — **params** (the
knobs the user can change), **skeleton** (the points where parts sit), and
**components** (the parts themselves). You write the JSON; `validate_asset`
checks it for free (no Houdini cost), then `build_asset` turns it into real
geometry.

This works for any object whose shape is defined by a few dimensions: a table,
a chair, a wheel, a pipe run, a bike frame. If the user says "make a ___" and
might later want it bigger/smaller/different proportions, author an asset.

## The three layers (write them top-down)

### 1. params — the dimensions a user can change

Declare every number that defines the shape. Two kinds:

```json
"params": {
  "top_size":     {"kind": "primary", "default": 1.0},
  "table_height": {"kind": "primary", "default": 0.75},
  "leg_radius":   {"kind": "primary", "default": 0.04},
  "leg_inset":    {"kind": "derived", "from": "top_size/2 - leg_radius"}
}
```

- **primary**: a free knob with a `default`. The user changes these.
- **derived**: computed from others via `"from"` (an expression over the param
  library — `+ - * / **`, `sqrt`, `sin`, `cos`, `radians`, ...). A derived
  param auto-tracks: change `top_size` and `leg_inset` recomputes.

Name params by what they ARE physically (`wheel_radius`, not `r1`). Never
hardcode a dimension into geometry — make it a param.

### 2. skeleton — where the parts sit (the heart of the design)

A map of named **points** in 3D space, each `[x, y, z]` an expression over
params (and over other points, via `point_name[0/1/2]`):

```json
"skeleton": {
  "top_center": {"expr": ["0", "table_height", "0"]},
  "leg_fl":     {"expr": ["-leg_inset", "table_height/2", "-leg_inset"]},
  "rear_axle":  {"expr": ["0", "wheel_radius", "0"]},
  "front_axle": {"expr": ["rear_axle[0] + wheelbase", "rear_axle[1]", "0"]}
}
```

**This is the core idea: components do NOT carry their own coordinates.** Every
part attaches to a skeleton point BY NAME. So two parts can never disagree about
where a shared feature sits — the skeleton DAG computes it once. Change a param
and every dependent point moves correctly.

Points can reference each other: `front_axle` reads `rear_axle[1]` (its y). The
resolver evaluates them in dependency order and rejects cycles.

### 3. components — what each part is

Each component attaches to a skeleton point and reads params. Two backends:

```json
"components": [
  {
    "id": "tabletop", "backend": "native_chain",
    "attach": {"position": "top_center"},
    "nodes": [
      {"type": "box", "params": {"size": ["top_size", "top_thickness", "top_size"]}}
    ]
  }
]
```

- **native_chain**: a list of native SOP nodes (`box`, `tube`, `torus`, ...) in
  a linear chain. Param values can be **numbers** (used directly) or **strings**
  (expressions over the param library — `"top_size/2"`, `"sqrt(a**2+b**2)"`).
  This keeps every dimension parametric.
- **python**: a Python SOP cook body for curves/sections native SOPs can't make
  (a rim circle, a custom profile). Write the geometry with the deterministic
  `geo.createPoint()` / `createPolygon()` API — use param NAMES as plain
  variables (`r = rim_r`), the builder substitutes their values. **Never use the
  `curve` node** (it needs viewport drawing); generate points in Python instead.

#### Multi-instance (one definition, many copies)

If a part repeats (4 table legs, 2 bike wheels), define it ONCE and instance it
onto N skeleton points:

```json
"instances": [
  {"id": "leg_fl", "position": "leg_fl"},
  {"id": "leg_fr", "position": "leg_fr"}
]
```

Each instance gets its own `component_id` (for the gates) and lands on its own
point. The geometry is built once and transform-copied — efficient and DRY.

#### Rotation (orient)

Most parts sit axis-aligned (a box is built along XYZ, so its `size` Y makes it
tall). For a part that must tilt — a leaning chair back, an angled strut — add
`"orient": [rx, ry, rz]` (Euler **degrees**) to `attach` or each `instance`:

```json
"attach": {"position": "back_center", "orient": [10, 0, 0]}
```

#### from-to struts (a part spanning two points)

Many parts are *connections* between two points — a bike-frame tube (seat tube
spans BB to seat top), a chair rung, a table stretcher. For these, name two
skeleton points with `from`/`to` instead of `attach`. The builder auto-computes
the midpoint (position), the length (|to−from|, overriding any height you
wrote), and the rotation that aligns a Y-axis tube onto the (to−from) direction.
**You never compute a length or an angle** — that's the whole point:

```json
{
  "id": "top_tube", "backend": "native_chain",
  "from": "seat_top", "to": "head_top",
  "nodes": [{"type": "tube", "params": {"rad": ["tube_r", "tube_r"]}}]
}
```

Use `from`/`to` for any strut whose defining feature is "it goes from here to
there". Use `attach` for a part that *sits at* a point (a box, a wheel).
`from`/`to` is mutually exclusive with `attach`/`instances`.

## Workflow

1. **Sketch the points first.** Before writing components, decide which skeleton
   points the object needs and what params drive them. The skeleton is the
   backbone — get it right and components become trivial.
2. **Write the asset** (params → skeleton → components, top-down).
3. **validate_asset(resolve=true)** — catches param typos, dangling references,
   cycles, bad backends, and prints the resolved point coordinates. Fix every
   error BEFORE building. This costs nothing (no Houdini nodes made).
4. **build_asset** — turns it into geometry. Returns the OUT path + where each
   part landed.
5. **inspect_health / geometry_inventory** on the OUT — verify the result.
6. **commit_sandbox** when the user wants it kept. A declarative asset commits
   cleanly: the builder stamps the sandbox, so `commit_sandbox` bypasses the
   legacy bake (`edini_world_axis`) and PCA-orientation gates — orientation is
   already deterministic from the skeleton DAG (from-to midpoint/angle, orient
   Euler). You do NOT bake axes or supply `orientation_checks`; just call
   `commit_sandbox(sandbox_root, <final_name>)`. The receipt is marked
   `method: "declarative"`.

## Common mistakes this skill prevents

| Mistake | Right way |
|---------|-----------|
| Hardcoding a dimension in geometry (`"size": [1.0,...]`) | Make it a param, reference by name (`"size": ["top_size",...]`) |
| Two parts disagreeing on a shared position | Both attach to the same skeleton point by name |
| Writing 4 identical leg components | One component + `instances[]` |
| `curve` node for a profile | python backend with `createPoint` |
| Expecting a part to auto-tilt | Add `orient: [rx,ry,rz]` explicitly |
| Building before validating | `validate_asset` first — it's free |

## Reference samples

- `python3.11libs/edini/data/table.asset.json` — multi-instance legs + python rim
- `python3.11libs/edini/data/chair.asset.json` — tilted backrest via orient
- `python3.11libs/edini/data/bicycle.asset.json` — skeleton-only (params + points)
