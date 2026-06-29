---
name: rooted-modeling
description: Use when the user wants a procedural/parametric model (a vehicle, a keyboard, a building — anything built from a main body plus parts attached to it). Build it with build_assembly, where a leaf's position is DERIVED by MEASURING the root's real geometry — never hardcoded coordinates. First make the root component, then compute where every other part sits by measuring that root (a wheel at a measured corner, a key on the measured tray face, a door at a measured point along a wall). Changing a parameter re-measures and every leaf moves correctly. This is more reliable than authoring nodes or hardcoding coordinates because the placement is a function of geometry, not of numbers you have to keep in sync.
---

# Rooted Modeling — measure the root, derive everything else

A procedural model has one **root** component that everything hangs off.
Build the root first, then place every other part by **measuring the root's
real, cooked geometry** — not by writing coordinates. The build is **LIVE**:
each mount is an `attribwrangle` whose VEX reads the root's bbox on every
cook, and leaves are stamped by `copytopoints`. Change a parameter and the
root re-cooks → the bbox re-reads → the points move → the copies re-stamp.
No coordinates are ever baked; the model is parametric end-to-end.

## The four roles

| Role | What it is | How it's obtained |
|------|-----------|-------------------|
| **Root** | The foundational component (a car's platform, a keyboard's tray, a building's mass) | Built first, as a native SOP (box/tube/torus/sphere) whose size reads from params |
| **Mount** | A `{position, orient}` where a part will sit | **Measured off the root's cooked geometry** — a bbox corner, a face center, a point along an edge. NEVER a hardcoded coordinate. |
| **Shape** | A self-contained part (a wheel, a keycap, a door) | Its *form* is independent of the root; only its *placement* is derived |
| **Leaf** | A shape placed onto a mount (optionally scaled) | The final placed part |

Data flows one way: `params → Root(cook) → measure → Mounts → place Leaves`.

## Shape size params (verified against Houdini 21.0.440)

Each shape type has specific size parm names — get these right or the build
fails in real Houdini (the mock can't catch wrong parm names). All values may
be numbers or param-expression strings.

| shape | size parms | notes |
|-------|-----------|-------|
| `box` | `size` (3-vec: `[x,y,z]`) | the parmTuple decomposes to sizex/sizey/sizez |
| `tube` | `rad` (2-vec `[r1,r2]`), `height` | the rad parmTuple → rad1/rad2. Set implicitly to Polygon type |
| `torus` | `radx`, `rady` (**independent parms**, NOT a tuple), `rows`, `cols` | a wheel's rim radius = radx, tube thickness = rady |
| `sphere` | `radx`, `rady`, `radz` (independent) | |

**No `cylinder`** — it is not a SOP in H21; use `tube`. **No `rad1`/`rad2` on
torus/sphere** — those names belong only to tube.

## The one rule you must not break

**Never write a coordinate.** Every position is a *measurement* of geometry
that has already been built. If you find yourself typing `[2, 0, 1]`, stop —
that's a hardcoded coordinate. Instead measure the corner that sits at that
spot. This is what makes the model parametric: the measurement tracks the
geometry, so a param change can never desync the parts.

## The measurements (how a mount reads the root)

A mount's `position.measure` picks a feature of the root's bounding box. Two
families: **single-point** measures (return one position) and **multi-point**
measures (return many — used to fan one leaf out to N instances):

| measure | returns | example |
|---------|---------|---------|
| `bbox_corner` | one corner, by sign | `axes: "+X-Y+Z"` → corner at (xmax, ymin, zmax). A wheel at a corner. |
| `bbox_face_center` | center of a face | `face: "+Y"` → top face center. A spacebar at the tray's center. |
| `bbox_center` | box midpoint | the whole root's center |
| `point_on_edge` | a point at `t∈[0,1]` along an edge | `axes_a`/`axes_b` + `t: 0.3` → 30% along. A door at 30% of a wall. |
| `grid_on_face` | **an rows×cols lattice** across a face | `face: "+Y", rows: 5, cols: 3, margin: 0.05` → 15 points, one per key on the tray top. A keyboard key grid. |
| `array` | **a 1D/2D/3D lattice** stepping from an origin | `count: [5,1,1], step: [[0.5,0.3,0],...]` → 5 points climbing diagonally. Stair treads. |

A mount's `orient` (optional) is **also derived**: give two measured points
and the builder computes the direction the leaf's built +Y axis should align
to, then returns the Euler angles. A wheel's axle = the direction between two
opposite corners along the platform's long edge. You never write a trig
function.

### Fan-out: one leaf definition → many placed instances

When a mount is a **multi-point** measure (`grid_on_face` or `array`), a single
leaf definition is fanned out to one placed instance per measured position.
This is the keyboard's trick: you write the keycap shape **once**, declare a
`grid_on_face` mount, and the `copytopoints` stamps `rows*cols` keycaps across
the tray's top — each at its measured grid point. Change the tray size and
every key re-measures and moves.

## The build is LIVE (M2): VEX wrangle + Copy-to-Points

The build layer produces a network that updates **live** when a param changes —
no rebuild needed. The structure per leaf:

```
root (box, size = ch("../length") ...)   ← parametric via container spare parms
   ↓
mount_<id>  (attribwrangle, detail)       ← reads root bbox LIVE via getbbox_min/max,
   ↓                                          emits @P + p@orient + @pscale points
   └── (merged with other mounts into mounts_cloud)
                                     ↓ input 1
leaf_shape (torus/box, ...)  ────→  copytopoints::2.0  ──→ OUT
                                   (input 0 = shape)
```

**Why this works live:** the root's `size` references the container's spare
parms via `ch("../length")`, so changing a param changes the box → its bbox →
the wrangle re-cooks (it reads `getbbox_min(0)` on every cook) → the points
move → `copytopoints` re-stamps. Every param becomes an editable spare parm on
the container, so a user can tweak them in the Houdini UI and watch the model
update. The `@orient` on each point is a quaternion from
`dihedral({0,1,0}, dir)` — the leaf's built +Y faces the measured direction.

**M2 scope (be honest):** only **root-shape** params (length/width/etc. that
feed the root box's size) are live. A mount's *internal* params (grid rows/
cols/margin, array count/step/origin) are resolved at build time — they're
baked into the wrangle's VEX/ch() spares. To change those you rebuild. Live
mount internals are a later milestone.

**Proven live in hython** (real Houdini 21): building a car and changing
`length` 4→8 (recook, no rebuild) moves the front wheels from x=±2 to x=±4
automatically; widening a keyboard's `tray_width` 4→8 re-scales the whole
key grid. See `tests/test_assembly_hython.py::TestLiveBuildHython`.

## How to author an assembly (top-down)

Write four sections in this order:

### 1. params — the dimensions a user can change
```json
"params": {
  "length": 4.0, "width": 2.0, "thickness": 0.5,
  "wheel_radius": 0.4
}
```
A bare number is a fixed default. Every dimension the shape needs lives here.

### 2. root — the foundational component
```json
"root": {
  "shape": {"type": "box", "params": {"size": ["length", "thickness", "width"]}}
}
```
A native SOP. Param values may be numbers or **strings** (expressions over
the param library, e.g. `"length/2"`). This keeps every dimension parametric.

### 3. mounts — measure the root to find where parts sit
```json
"mounts": [
  {"id": "wheel_fr", "position": {
     "measure": "bbox_corner", "from": "root", "axes": "+X-Y+Z"},
   "orient": {"from": "root",
     "from_a": {"measure": "bbox_corner", "axes": "-X-Y+Z"},
     "from_b": {"measure": "bbox_corner", "axes": "+X-Y+Z"}}}
]
```
Each mount measures the cooked root. `from: "root"` always (M0).

### 4. leaves — self-contained shapes placed onto mounts
```json
"leaves": [
  {"id": "wheel_fr", "mount": "wheel_fr", "scale": "wheel_radius",
   "shape": {"type": "torus", "params": {"rad1": 1.0, "rad2": 0.08}}}
]
```
The shape's form is independent of the root. `scale` (optional) is a param
expression so size stays parametric too.

## The verified example: a car (platform + 4 wheels)

This exact assembly is proven by the test suite (`tests/test_assembly_builder.py`,
`tests/test_assembly_hython.py`). Use it as your template.

- **Root**: a box platform, size `[length, thickness, width]`.
- **4 mounts**: each wheel at one bottom corner (`+X-Y+Z`, `+X-Y-Z`, `-X-Y+Z`,
  `-X-Y-Z`), axle oriented along the long edge (direction between `-X-Y+Z` and
  `+X-Y+Z`).
- **4 leaves**: a torus wheel on each mount, scaled by `wheel_radius`.

**The proof**: build it with `length=4`, the front-right wheel measures to
position `(2, -0.25, 1)` (the `+X-Y+Z` corner). Rebuild with `length=8` and
the SAME mount spec measures the wheel to `(4, -0.25, 1)` — it moved with the
geometry. No coordinate was changed by hand.

## The verified example: a keyboard (tray + key grid)

Also test-proven (`tests/test_assembly_builder.py::TestKeyboardGrid`). This is
the case that forced the **fan-out** design: many keys on a face.

- **Root**: a box tray, size `[tray_width, tray_thick, tray_depth]`.
- **1 mount**: `grid_on_face` on `+Y`, `rows: 5, cols: 3, margin: 0.05` → 15
  measured points across the tray's top.
- **1 leaf**: a keycap box — defined **once** — placed at each of the 15
  measured grid points.

```json
"mounts": [
  {"id": "keys", "position": {
     "measure": "grid_on_face", "from": "root", "face": "+Y",
     "rows": 5, "cols": 3, "margin": 0.05}}
],
"leaves": [
  {"id": "key", "mount": "keys",
   "shape": {"type": "box", "params": {"size": ["key_size","key_height","key_size"]}}}
]
```

**The proof**: widen the tray from 4 to 8 and every key's X position doubles —
the whole grid rescales off the measured face, no key coordinate was touched.
The build result reports `mounts.keys.count == 15`.

The keycap's *form* is a plain box that knows nothing of the tray — exactly
the decoupling the skill is built around: only the *placement* derives from
the root.

## The verified example: a staircase (diagonal array)

Test-proven (`tests/test_assembly_builder.py::TestStaircaseArray`). Shows an
`array` whose steps climb diagonally — a single step vector advances in X
**and** rises in Y.

```json
"mounts": [
  {"id": "treads", "position": {
     "measure": "array", "from": "root",
     "origin": {"measure": "bbox_face_center", "face": "+Y"},
     "count": [5, 1, 1],
     "step": [["run", "rise", 0], [0, 0, 0], [0, 0, 0]]}}
],
"leaves": [
  {"id": "tread", "mount": "treads", "shape": {"type": "box", "params": {...}}}
]
```

The array's `origin` is itself a measurement (the base's top center), and each
step is the full vector `["run", "rise", 0]` — so treads march up a diagonal
without you writing any climb arithmetic.

## Workflow

1. **Identify the root.** What is the one component everything else hangs off?
   (A vehicle's platform, a keyboard's tray, a building's shell.) Build it first.
2. **Author params** — every dimension the root and leaves need.
3. **Author the root shape** — a native SOP reading those params.
4. **Author mounts** by measuring the root. Think in features: "wheels at the
   four bottom corners", "keys across the top face", "door at 30% of the front
   wall". Express each as a measurement, never a coordinate.
5. **Author leaves** — self-contained shapes, each on a mount, optionally
   scaled by a param.
6. **build_assembly** — validate runs first (shift-left, free); on success it
   builds a LIVE network (root + mount wrangles + copytopoints + OUT) and
   returns the OUT path + sandbox root + the mount/leaf ids.
7. **VERIFY** the result. Open the sandbox in Houdini, find the container's
   param spare parms (under "Edini Params"), and **change a root-shape param**
   — the model must update live without rebuilding. If it doesn't move, the
   mount is mis-specified. (Under hython, `tests/test_assembly_hython.py`
   asserts this live behavior automatically.)
8. **commit_sandbox(sandbox_root, name)** to make it permanent.

## Common mistakes this skill prevents

| Mistake | Right way |
|---------|-----------|
| Hardcoding a leaf position `position: [2,0,1]` | Measure it: `bbox_corner` axes `+X-Y+Z` |
| Two parts disagreeing on a shared spot | Both measure the same root feature |
| A part that doesn't move when params change | Its mount must be a measurement, not a literal |
| Hardcoding an orient angle `orient: [0,90,0]` | Derive it: give two measured points, let the builder compute the direction |
| A leaf shape that depends on the root | Keep leaf forms self-contained; only placement derives from the root |
| Building before thinking about the root | The root is the anchor — pick it first |

## What this skill supports (and what's coming)

**Done (M0–M2):** native-SOP roots and leaves (box/tube/torus/sphere);
single-point mounts (bbox corner / face center / center / edge point);
**multi-point mounts** (`grid_on_face`, `array`) that fan one leaf out to many
placed instances; direction-based orient mounts (quaternion via `dihedral`);
expression-based scale/size; single root level; and a **LIVE build layer**
(M2) where root-shape params are editable spares and the model updates live
(VEX wrangle + Copy-to-Points, no baked coordinates).

**Later milestones:** live mount internals (grid rows/cols, array step are
currently baked at build); named anchors the root exposes explicitly (so a
root can mark "hub_point" instead of you inferring the corner); per-instance
orient within a grid/array (all keys currently share one orient); and
**multi-level derivation** where a placed leaf becomes the root for the next
level (bike frame → fork → handlebar). The measurement-first contract won't
change — only the menu of measurements grows.

## Reference

- `python3.11libs/edini/measure.py` — the measurement layer + Python ORACLE
  (bbox corners, face centers/normals, edge points, **grid_on_face**, **array**,
  direction, orient-to-align-Y). Used as the correctness oracle for the VEX
  strategies, verified point-by-point in hython.
- `python3.11libs/edini/vex_strategies.py` — the LIVE measurement strategies.
  Each is a pre-built, pre-tested VEX template (one per measure kind); the
  agent never writes VEX, only picks a strategy + params.
- `python3.11libs/edini/assembly_builder.py` — `validate_assembly` +
  `build_assembly` (the LIVE build: root + mount wrangles + copytopoints +
  OUT; root params as editable spares; no baked coordinates).
- `tests/test_measure.py` / `tests/test_assembly_builder.py` — mock-level
  tests (validation, VEX strategy selector resolution, network structure).
- `tests/test_assembly_hython.py` — the decisive real-Houdini tests: the
  car/keyboard/stairs build, AND the **live-recook proof** (change a param,
  recook, instances move without rebuild).
- `scripts/verify_vex_strategies.py` — runs each VEX strategy in real hython
  against the Python oracle, point-by-point. Run after touching vex_strategies.
- `scripts/show_assemblies.py` — builds all three examples to a `.hip` and
  demonstrates live param changes. Open `edini_showcase.hip` in Houdini.
