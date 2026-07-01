# Tabular Fill Layouts — Extending `TabularFillStrategy` (pickets / tiles / shelf / blocks)

**Date:** 2026-06-30
**Skill / area:** `skills/rooted-modeling` → `python3.11libs/edini/{vex_strategies,measure,assembly_builder}.py`
**Status:** Design approved by user (brainstormed 2026-06-30), ready for implementation plan
**Parent milestone:** rooted-modeling M3 (`cells` 测量原语 + 三层类架构). This extends the
`TabularFillStrategy` generalization vehicle M3 introduced.

## 0. TL;DR

M3 shipped `TabularFillStrategy` as an explicitly-generalization-bound class hierarchy
(`VexStrategy` → `TabularFillStrategy` → `CellsStrategy`), with the gx/gz/w/d keyboard
schema as the first concrete subclass. Its docstring and SKILL.md both say *"bookshelves,
city blocks, tile mosaics, fence pickets ... subclass `TabularFillStrategy` and override
the cell schema."* This design cashes that check: four new layout strategies, built in an
order where each one **drives a real generalization down into the base class**, so the
abstraction is shaped by need rather than by prediction.

| # | layout | `measure` | drives what into the base class |
|---|--------|-----------|----------------------------------|
| ① | fence pickets | `pickets` | **variable dimensionality** (`axes[]` 1/2/3) + named coord/size columns + `count`→table sugar |
| ② | tile mosaic | `tiles` | **per-cell orient** (the long-deferred milestone) + named orient rules + quaternion oracle |
| ③ | bookshelf | `shelf` | **layer pre-expansion** (subclass-side builder translation, base class untouched) + 3D cells |
| ④ | city blocks | `blocks` | **synthesis exam** — composes ①②③, near-zero new code |

The agent never writes or sees VEX. Each new layout = we add one `TabularFillStrategy`
subclass + a `measure.py` oracle + `validate_assembly` schema + SKILL.md docs. The
existing `cells` (keyboard) must stay green at every step (599-test regression gate).

## 1. Problem statement & first principles

### 1.1 What `TabularFillStrategy` already does right

`vex_strategies.py:236-388`. The defining property of `cells` is **measurement-driven
coupling**: the physical size of 1u is NOT a free parameter, it is DERIVED live from the
root's span:

```
unit_a0 = (root_span_a0 - 2*margin) / max(gx + w)
```

So the layout FILLS the root and rescales when the root resizes. The class achieves this
by separating three concerns:

| layer | responsibility | current form |
|-------|----------------|--------------|
| **data (table)** | declare "which slots hold what, how big" | `{gx,gz,w,d}` cells → VEX array literals |
| **code (loop)** | one ~30-line VEX loop, cell-count-independent | single `__ci` loop |
| **mechanism (derivation)** | unit derivation + per-point `v@scale` + square/pad/repeat | shared by all subclasses |

These three are **truly general** — any "fill a region with (position, size) instances"
layout inherits them. What is NOT general is the cell schema and the 2D in-plane-axis
assumption baked into the VEX. That is what this design generalizes.

### 1.2 First-principles diagnosis of the limits

Reading the four target layouts (pickets/tiles/shelf/blocks) against the current code,
they share ONE abstraction that the current `cells` does not expose: **a layout is a set
of slots in an N-dimensional slot space (1/2/3), where each slot optionally declares its
coordinate, size, and orientation.** The differences across the four are entirely
*differences in which columns a slot has*:

| layout | slot space | slot declares |
|--------|-----------|---------------|
| keyboard (cells) | 2D `{gx,gz}` | position + size `{w,d}` |
| fence pickets | 1D `{gx}` | position + size + height |
| tile mosaic | 2D `{gx,gz}` | position + size + **rotation** |
| bookshelf | 3D `{gx,gz,gy}` | position + size per layer |
| city blocks | 2D `{gx,gz}` | position + footprint + height + rotation |

So the three concrete limits to remove are:

1. **Schema fields are hard-coded in `CellsStrategy._parse_table`.** Adding a "rotation"
   or "layer" column requires editing parse logic AND the VEX loop's hardcoded
   `scl[__a0]` writes.
2. **Slot-space dimensionality is fixed at 2D** (`a0/a1`, two in-plane axes). Pickets
   (1D) and shelf (3D) cannot be expressed.
3. **Per-cell orient is absent.** Orient is per-mount today (one quaternion shared by all
   points, `vex_strategies.py:446-493`). Tiles need per-cell rotation; SKILL.md §"later
   milestones" lists this explicitly.

### 1.3 Architecture choice: layered generalization (the agreed path)

Three routes were considered (see brainstorm log):

- **A. one class per layout** — clear but lots of boilerplate; shared new mechanisms
  (per-cell orient) get re-implemented per class.
- **B. one UnifiedStrategy, config-driven** — most "elegant" but premature
  generalization: a universal schema becomes "fills anything, specializes nothing," and
  the VEX generator degenerates into a giant condition tree (complexity shoved from data
  back into code — the opposite of data/code decoupling).
- **C (CHOSEN) layered generalization** — keep one-class-per-layout (A's clarity), but as
  each layout is built, proactively **push whatever it shares down into
  `TabularFillStrategy`**. Generalization is driven by real layouts, not predicted. Each
  push makes the next layout cheaper. The development order ①②③④ is itself the
  generalization roadmap.

## 2. Scope

**In scope:**
- Four new `TabularFillStrategy` subclasses: `PicketStrategy`, `TileStrategy`,
  `ShelfStrategy`, `BlockStrategy`, plus their `measure.py` oracles and
  `validate_assembly` schema branches.
- Three base-class generalizations: `axes[]` variable dimensionality, per-cell `rot`
  orient, named coord/size columns.
- Per-cell orient milestone (SKILL.md "later milestones") resolved.
- `count`→table pre-expansion sugar (for pickets and any uniform layout).
- `layers` pre-expansion (shelf's subclass-side builder translation).
- hython real-machine proof for all four layouts (oracle ↔ VEX point-by-point).
- SKILL.md additions documenting the four layouts + the named orient rules.

**Out of scope (YAGNI):**
- Full nested split grammar (multi-level recursive subdivision). Shelf's single-axis
  layering is the only nesting needed; blocks proves full recursion is unnecessary.
- Per-cell orient as a free expression (`"rot": "expr:row*30"`). Only named rules
  (herringbone/checker/running) + explicit per-cell `rot` degrees — the "agent never
  writes expressions" rule is preserved.
- Per-cell `scale` independent of the table (size still comes from the cell's size columns).
- Live mount internals (grid rows/cols still bake at build — that is a separate milestone).
- Auto-generated shelf boards (separation: shelf places books; the root builds boards).
  An optional `shelf_board` sugar is documented but out of the critical path.

**Regression gate (HARD):** the existing `cells` keyboard layout and all 599 M3 tests
must remain green at every step. Generalizing the base class must not change 2D behavior.

## 3. Design — §3.1 Variable dimensionality (driven by ① pickets)

### 3.1.1 The diagnosis

`TabularFillStrategy._build_vex` hardcodes two in-plane axes:

```vex
int __a0 = -1, __a1 = -1, __seen = 0;
for (int __i = 0; __i < 3; __i++) { if (__i != __fa) { ... } }   // always 2 axes
__p[__a0] = __g0 + __cx[__ci] * __u0;                             // position: 2 axes
__scl[__a0] = ...; __scl[__a1] = ...;                             // scale: 2 axes
```

Pickets are 1D (a row along one edge); shelf is 3D (layers × within-layer 2D). Neither
fits "exactly two in-plane axes."

### 3.1.2 The abstraction: `axes[]` — an ordered list of layout axes

Replace the implicit two-axis assumption with an explicit `axes[]` list (length 1/2/3):

| layout | `axes` | meaning |
|--------|--------|---------|
| pickets | `["X"]` | one row along X |
| cells/tiles/blocks | `["X","Z"]` | 2D grid on the face (current behavior) |
| shelf | `["X","Z","Y"]` | within-layer 2D (X,Z) + layer axis Y |

The face's own axis (the normal) is NOT in `axes` — it is derived from `basis.face`
exactly as today. `axes` are the *layout* axes along which slots step.

### 3.1.3 Schema evolution: named columns derived from `axes`

The most important first-principles change. The current fixed `{gx,gz,w,d}` becomes
**named coordinate + named size columns, one pair per axis**, the pair name derived from
the axis letter:

- `g<AXIS>` = the slot coordinate on that axis (1u units)
- `<axis-lower>` = the slot's size on that axis (1u units)

| `axes` | coordinate columns | size columns | example cell |
|--------|--------------------|--------------|--------------|
| `["X"]` | `gx` | `w` | `{"gx":0,"w":1}` |
| `["X","Z"]` | `gx,gz` | `w,d` | `{"gx":0,"gz":0,"w":1,"d":1}` (= current cells, full back-compat) |
| `["X","Z","Y"]` | `gx,gz,gy` | `w,d,h` | `{"gx":0,"gz":0,"gy":0,"w":1,"d":1,"h":1}` |

**Full backward compatibility:** when `axes=["X","Z"]`, the schema is byte-identical to
the current `cells`. The 599-test regression gate is the proof.

### 3.1.4 `basis` — where the layout sits (generalizes `face`)

Pickets stand *along an edge of a face*, not on the whole face. Shelf stacks *along an
axis of a face*. So `face` alone is insufficient. Introduce `basis`:

```jsonc
"position": {
  "measure": "pickets",
  "basis": {"face": "+Y", "edge": "+Z"},   // on the +Y face, along its +Z edge
  "axes": ["X"], "count": 8
}
```

- `basis.face` — the face the layout lies on (current `face` semantics, retained).
- `basis.edge` (optional) — restricts a 1D layout to one edge of that face. A 2D/3D layout
  omits `edge` and fills the face.

`face` (bare) remains accepted as sugar for `basis: {"face": <face>}` (no edge) to keep
existing `cells` specs unchanged.

### 3.1.5 `count`→table sugar (uniform layouts)

Pickets are usually *evenly spaced N posts*, not an explicit table. Support two forms:

```jsonc
// form A: uniform (pickets/railing common) — count drives, auto-splits
"position": {"measure":"pickets", "basis":{...}, "count": 8}
// → builder expands to 8 equal-width cells, same loop

// form B: explicit table (uneven pickets / keyboards)
"position": {"measure":"pickets", "basis":{...},
  "cells": [{"gx":0,"w":1}, {"gx":1.5,"w":0.5}]}
```

Form A is syntactic sugar: the builder layer expands `count` into N equal cells, then
runs the same single loop. Only one VEX path exists; data drives it.

### 3.1.6 unit derivation generalized

Current unit is two scalars (`__u0/__u1`); new form is **one unit per axis**:

```vex
// generalized (pseudo-VEX):
float __u[]; resize(__u, __naxes);
for (int __ai = 0; __ai < __naxes; __ai++) {
    int __ax = __axes[__ai];
    __u[__ai] = (__mx[__ax] - __mn[__ax] - 2*__m) / __total_u[__ai];
}
```

`square`/`pad`/`repeat` semantics generalize naturally: `square` = unify all axes' units
to `min` (currently two-axis min; mathematically identical for the 2D case — regression
gate proves equivalence).

### 3.1.7 Pickets schema — the `h` column (out-of-plane size)

A 1D picket row lives on the face (its `gx`/`w` are along `axes=["X"]`), but a post also
has a **height** — which is along the face's *normal* (out of the layout plane), NOT a
layout axis. The optional `h` column is this out-of-plane size (1u units, derived like the
others). So a picket cell can be `{"gx":0,"w":1,"h":12}` (1u wide, 12u tall). The post's
out-of-plane unit is derived from the root's extent along the face normal, exactly the same
unit-derivation rule as the layout axes.

### 3.1.8 §3.1 proof artifact

Pickets (1D) builds a fence: 8 posts evenly along the +Z edge of a +Y platform, each post
carrying a live-derived `h` (the post height scales with the platform's normal extent).
After this, `TabularFillStrategy` supports arbitrary dimensionality; `cells` (2D) is
verified still green.

## 4. Design — §4 per-cell orient (driven by ② tiles)

### 4.1 Three orient sources (first principles)

Per-cell orient has three semantic sources — they must not be conflated:

| source | used by | meaning | status |
|--------|---------|---------|--------|
| **A. measured direction** | wheels (per-mount) | two points → dihedral | existing |
| **B. axis-locked angle** | tiles (per-cell) | each tile rotates 0/90/180/270° about the face normal | NEW |
| **C. path tangent** | pickets (per-cell) | each post perpendicular to its edge | implied by §3.1.4 |

B and C are the same abstraction filled differently: "for each cell, give an orientation."
Unified into one per-cell orient mechanism.

### 4.2 Two declaration levels

| level | where | precedence | use |
|-------|-------|-----------|-----|
| **mount-level rule** (global) | `position.orient` | low | herringbone/checker (position-based formula) |
| **cell-level `rot`** (per-cell) | the cell's `rot` field | high | explicit per-tile angle |

cell `rot` wins → else fall back to mount rule → else identity orient (current behavior).

### 4.3 Orient is a quaternion, not Euler

[SideFX docs](https://www.sidefx.com/docs/houdini/copy/instanceattrs) and the
[TOADSTORM guide](https://www.toadstorm.com/blog/?p=493): CTP 2.0's canonical instance
orientation is point-class `p@orient` (quaternion). Euler has gimbal lock and drifts on
composition; quaternion is shortest-arc and composes by multiplication. The existing
mount orient is already quaternion (`dihedral`). Per-cell orient continues this:

```vex
// tile: each tile's rot (degrees) about the face normal → quaternion
vector __axis = {0,0,0}; __axis[__fa] = __fs;
vector4 __qrot = quaternion(radians(__rot[__ci]), __axis);
setpointattrib(geoself(), "orient", __pt, __qrot, "set");
```

When a cell has both a global measured-direction orient (like a wheel) AND a per-cell rot,
the two quaternions **multiply** (VEX `qmultiply`) to compose. This is a second advantage
of quaternions over Euler — composition is unambiguous multiplication.

### 4.4 Named orient rules (herringbone / checker / running)

The essence of tiling is not single-tile rotation but the **pattern**. Provide named
rules (mount-level) — the agent picks a name, we compute angles:

| rule | rotation formula | visual |
|------|------------------|--------|
| `"herringbone"` | `45° if (row+col)%2==0 else 135°` | herringbone |
| `"checker"` | `0° if (row+col)%2==0 else 90°` | checker diagonal |
| `"running"` | `(col*30°) % 90°` | staggered running bond |
| no rule + cell `rot` | use cell's explicit `rot` | custom |

**Why named rules, not free expressions:** the agent cannot write VEX; making it compute
"each tile's angle" is making it write an expression, returning to the root failure mode.
Baking the pattern math into the framework with names preserves the "agent only declares"
contract.

### 4.5 Oracle upgrade: `(pos, scale, orient)` triples

`measure.py` currently returns `(position, scale)` pairs. Upgraded to triples:

```python
# measure.measure_tiles(...) returns [(pos, scale, orient_quat), ...]
# orient_quat = quaternion rotating `rot` degrees about the face normal
# (axis-angle→quat, mirroring VEX quaternion())
```

The hython oracle comparison compares orient as a quaternion (4 components) by **dot
product**, not componentwise: two equivalent quaternions may have opposite sign
(`q ≡ -q`); `|q1·q2| ≈ 1` means equivalent. This is a key verification detail.

### 4.6 §4 proof artifact

Tiles build a mosaic: a 6×6 face with the herringbone rule; selected tiles carry explicit
`rot: 90`. hython verifies each instance's `p@orient` matches the oracle quaternion (dot
product ≥ 1-1e-6). After this, per-instance orient (the deferred milestone) is resolved;
block rotation and shelf spine orientation inherit it free.

## 5. Design — §5 layer pre-expansion (driven by ③ shelf)

### 5.1 Shelf's precise structure

```
┌─────────────────────────┐
│ books books   books books│  ← layer 1 (height 8u, 4 books of varying width)
├─────────────────────────┤  ← divider (part of root)
│ books books   books books│  ← layer 0 (height 10u, uneven spacing)
└─────────────────────────┘   ← base (part of root)
```

Three challenges:
1. Layers are 1D subdivision along the height axis.
2. Each layer fills independently (2D within the layer).
3. Layer heights vary (not equal-split).

### 5.2 Three candidates — two rejected

**Candidate A — layer as the 3rd layout axis (`axes=["X","Z","Y"]`):**
```jsonc
{"gx":0,"gz":0,"gy":0,"w":1,"d":1,"h":10}   // every book repeats layer's h
```
**REJECTED.** Layer height is a *layer* attribute, not each book's. Repeating `h:10` on
10 books is redundant, and the layer boundary (which book belongs to which layer) is
implicit in `gy` — unclear.

**Candidate B — full nested split grammar:**
```jsonc
"splits": [{"axis":"Y","layers":[...]}, {"per_layer":{"measure":"cells",...}}]
```
**REJECTED (this milestone).** The most general form, but introduces nested measurement
(measurement results feeding the next measurement), breaks the clean "one mount, one
measure," and turns the VEX from a single loop into nested loops. YAGNI — only shelf and
blocks need it, and blocks (§6) proves it is unnecessary.

**Candidate C (CHOSEN) — explicit layers, within-layer reuses cells:**
```jsonc
"position": {
  "measure": "shelf",
  "basis": {"face":"+Y"},
  "axis": "Y",
  "layers": [
    {"height": 10, "cells": [{"gx":0,"w":2}, {"gx":2,"w":1}, {"gx":3,"w":4}]},
    {"height": 8,  "cells": [{"gx":0,"w":1}, {"gx":1,"w":5}]}
  ]
}
```
Layer attributes belong to the layer (`height`); book attributes belong to the book (cell).
Within-layer cells reuse all of §3.1's machinery (unit derivation, fill, square), scoped
to that layer's space.

### 5.3 The mechanism: layer → flatten (builder layer)

Layers are flattened in the **builder layer (Python)** into the 3D cells of §3.1, then run
the same single VEX loop. **VEX never knows "layer" exists:**

```python
# builder-layer pseudo: layers → flat cells
def _expand_shelf_layers(layers, layer_axis):
    out = []
    cur = 0.0
    for layer in layers:
        h = layer["height"]
        for cell in layer["cells"]:
            cell["g" + layer_axis] = cur        # inject absolute layer coord
            cell[layer_axis.lower()] = h         # inject layer height
            out.append(cell)
        cur += h
    return out                                   # → standard TabularFill loop
```

So `shelf` writes almost no new VEX — it is a schema translation layer (layer table →
flat 3D cells). The core loop is inherited from `TabularFillStrategy`. This is exactly
"push down by need": the layer concept does **not** pollute the base class; it lives as a
subclass's pre-processing step.

**Layer height unit derivation:** each layer cell's `h` is absolute u; the layers' total
`Σ height[i]` defines the Y-axis `total_u`; the Y unit is derived from the root's height.
Resize the shelf → Y unit shrinks → every layer and book rescales together. **Still live.**

### 5.4 Boards: layer geometry vs book geometry

A shelf has two geometries: boards (continuous) and books (discrete instances). Two
options:

- **Option 1 (CHOSEN): books only, boards left to root.** The shelf root itself is a
  multi-box merge with dividers (the user builds dividers in the root); the `shelf`
  strategy only places books. Separation of concerns: boards are continuous geometry
  (not copy instances) and forcing them into CTP is a stretch; building boards in the root
  is natural in Houdini; `shelf` stays focused on "fill within layers."
- **Option 2: strategy also generates boards.** Each layer top auto-adds a full-width
  cell. REJECTED as default — but an optional sugar `shelf_board: true` on a layer is
  documented for users who want one-click generation. Out of the critical path.

### 5.5 §5 proof artifact

Shelf builds a 3-shelf bookcase: layer heights [10, 8, 6], each layer filled with books
of varying width. hython verifies each book's position = (root-space center from the
flattened 3D coords × derived unit). After this, 3D cells are battle-tested; blocks (§6)
reuses the "position-is-position, height-is-height" separation.

## 6. Design — §6 city blocks (synthesis exam)

### 6.1 Blocks = shelf's height column + tile's rotation, in 2D

```
top view (2D footprint):       elevation (height):
┌──────┬─────┬───────┐         ■■■  tower (h=40u)
│ park │tower│ podium │         ■■■┐
│(empty│ ■■■ │ ■■    │         ■■■│podium (h=10u)
├──────┴─────┤ ■■    │         ─────
│   main st  │ ■■    │
└────────────┴───────┘
```

Decomposition:
1. 2D footprint subdivision (inherits shelf's "within-layer cells" = 2D cells, §3.1).
2. One height per cell (inherits shelf's "height belongs to the cell/layer" = `h` column, §5).
3. Empty cells (park = no building = no cell, §3.1's empty-slot mechanism).
4. Optional rotation (inherits tile's `rot`, §4).

### 6.2 Block schema: it is 2D cells with an `h` column

```jsonc
"position": {
  "measure": "blocks",
  "basis": {"face":"+Y"},
  "cells": [
    // park at {gx:0..2, gz:0..2} is OMITTED — empty slot, see §6.3
    {"gx":2,"gz":0,"w":2,"d":3,"h":40},             // tower: footprint 2x3, h=40u
    {"gx":4,"gz":0,"w":2,"d":3,"h":10,"rot":0},     // podium: short, facing south
    {"gx":0,"gz":2,"w":6,"d":2,"h":6}               // main street block: long strip, short
  ],
  "square": true, "fill": "pad"
}
```

The only difference from shelf: blocks is 2D (ground), shelf is 3D (layers × within). Both
use the `h` column for height. This is the reuse of §5's separation.

### 6.3 Empty cells (parks / streets) by omission

A park is not a special building — it is **no cell.** This reuses §3.1's empty-slot
mechanism (a slot with no declared cell is just empty; keyboard gaps already do this,
SKILL.md line 100). Simply don't declare the park's cell; that area stays empty. `fill:
"pad"` leaves gaps between blocks (streets).

**Why not `h:0`:** it would stamp a zero-height degenerate instance. Omission is cleaner
and matches keyboard-gap semantics.

### 6.4 §6 proof artifact

Blocks build a 4-block cityscape on a ground plane with a park (empty), tower, podium, and
street strip. hython verifies footprint positions + heights + (optionally) rotation.
**Near-zero new code** — this composes §3.1/§4/§5. If it composes cleanly, the
generalization is correct; if not, an abstraction gap surfaced (the exam's value).

## 7. Schema summary (the whole extension at a glance)

### 7.1 mount-level fields (on `position`)

| field | required? | meaning | source § |
|-------|-----------|---------|----------|
| `measure` | yes | one of `pickets`/`cells`/`tiles`/`shelf`/`blocks` (+ existing kinds) | all |
| `basis` | yes (new) | `{face, edge?}` — the face the layout lies on; `edge` restricts 1D layouts to one edge | §3.1.4 |
| `face` | sugar | bare `"+Y"` = `basis:{face:"+Y"}` (kept for `cells` back-compat) | §3.1.4 |
| `axes` | yes (new) | `["X"]`/`["X","Z"]`/`["X","Z","Y"]` — the layout axes | §3.1.2 |
| `count` | optional | uniform-layout sugar (expands to N equal cells) | §3.1.5 |
| `layers` | shelf-only | `[{height, cells}]` — pre-expanded by the builder | §5.3 |
| `orient` | optional | mount-level named rule (`herringbone`/`checker`/`running`) | §4.2 |
| `margin`/`gap`/`square`/`fill` | optional | inherited from existing `cells` | M3 |
| `from` | sugar | defaults `"root"` (single-root M0 scope) | M0 |

### 7.2 cell-level columns (per layout)

| layout | `measure` | `axes` | coord cols | size cols | special cols | source § |
|--------|-----------|--------|-----------|-----------|--------------|----------|
| fence pickets | `pickets` | `[X]` | `gx` | `w` | `h` (opt out-of-plane height, §3.1.7) | §3.1 |
| keyboard (existing) | `cells` | `[X,Z]` | `gx,gz` | `w,d` | — | M3 |
| tile mosaic | `tiles` | `[X,Z]` | `gx,gz` | `w,d` | `rot` (opt orient) | §4 |
| bookshelf | `shelf` | `[X,Z,Y]` | `gx,gz,gy` | `w,d,h` | `layers` (mount-level, §7.1) | §5 |
| city blocks | `blocks` | `[X,Z]` | `gx,gz` | `w,d` | `h` + `rot` | §6 |

**Column naming rule** (established §3.1.3): `g<AXIS>` is the slot coordinate, `<axis-lower>`
is the size (X→`gx`/`w`, Y→`gy`/`h`, Z→`gz`/`d`). Orient uses `rot` (degrees). For shelf,
the `gy`/`h` columns are *injected* by the layer pre-expansion (§5.3) — the agent writes
cells without them, inside a `layers[].cells` list.

**`measure` registry additions** (in `build_mount_vex` / `_STATIC_STRATEGIES`):
`pickets`, `tiles`, `blocks` → dispatch to their `TabularFillStrategy` subclass (like
`cells` does today); `shelf` dispatches to its subclass which pre-expands layers then
delegates to the flattened 3D path.

## 8. Base-class capability stack after all four layouts

`TabularFillStrategy` accumulates these shared mechanisms (inherited by all subclasses):

| mechanism | source | used by |
|-----------|--------|---------|
| `axes[]` variable dimensionality (1/2/3) | pickets ① | all |
| named coord/size columns (per `axes`) | pickets ① | all |
| `count`→table pre-expansion sugar | pickets ① | pickets |
| unit N-axis derivation + square/pad/repeat | generalized from existing | all |
| per-cell `rot` (quaternion about face normal) | tiles ② | tiles, blocks |
| named orient rules (herringbone/checker/running) | tiles ② | tiles |
| oracle `(pos,scale,orient)` triples | tiles ② | all |
| layer pre-expansion (subclass-side builder translation) | shelf ③ | shelf |

A subclass writes only: `_parse_table` (its own schema) + optional builder-layer
pre-processing (shelf's layer flatten, pickets' count expand). The core VEX loop, unit
derivation, orient, and fill are all inherited. This is route C's promise kept —
**generality sedimented by real layouts, not predicted abstraction.**

## 9. Files touched

| file | changes |
|------|---------|
| `python3.11libs/edini/vex_strategies.py` | generalize `TabularFillStrategy` (`axes[]`, per-cell `rot`, named orient rules); add `PicketStrategy`/`TileStrategy`/`ShelfStrategy`/`BlockStrategy`; register in `build_mount_vex` |
| `python3.11libs/edini/measure.py` | add `measure_pickets`/`measure_tiles`/`measure_shelf`/`measure_blocks` oracles; upgrade return to `(pos,scale,orient)` triples |
| `python3.11libs/edini/assembly_builder.py` | extend `validate_assembly` schema for the 4 new measures + `basis` + `axes`; add `_expand_pickets_count` / `_expand_shelf_layers` builder-layer pre-expansion; register measures |
| `skills/rooted-modeling/SKILL.md` | document the 4 layouts, `axes`/`basis`, `count` sugar, per-cell `rot`, named orient rules, layer syntax |
| `tests/test_assembly_builder.py` | mock schema-validation + network-structure tests per layout |
| `tests/test_measure.py` | oracle unit tests for the 4 new measures (incl. quaternion dot-product comparison) |
| `tests/test_assembly_hython.py` | real-machine proof: pickets 1D, tiles herringbone + per-cell rot, shelf 3 layers, blocks 4 cells |
| `scripts/verify_vex_strategies.py` | add the 4 new strategies to the oracle↔VEX comparison |
| `scripts/show_assemblies.py` | add a shelf and a fence to the showcase `.hip` |

## 10. Test strategy (three-layer, per layout)

For each layout:
1. **mock schema-validation** — `validate_assembly` rejects bad schema (missing columns,
   negative sizes, unknown measure, malformed `basis`/`axes`/`layers`).
2. **mock network-structure** — each measure produces the correct wrangle + CTP node tree.
3. **hython real-machine proof** — VEX ↔ oracle point-by-point. The local hython is
   confirmed at `D:\houdini\bin\hython.exe`.

**Regression gate (HARD):** the existing `cells` keyboard layout and all 599 M3 tests
remain green at every step. Generalizing the base class must not change 2D behavior — the
2D path with `axes=["X","Z"]` is byte-identical to the current `cells`.

## 11. Development order (the silkiness roadmap)

```
① pickets (1D)  →  shapes axes[] + count sugar  →  cells 2D still green
② tiles  (rot)  →  shapes per-cell orient        →  cells still green
③ shelf  (layer)→  shapes layer pre-expand + 3D  →  ①② still green
④ blocks (synth)→  near-zero new code, composes  →  ①②③ still green
```

Each step: real layout drives → exposes an abstraction gap → push down to base class →
regression-verify. This is incremental generalization that never breaks existing
capability — exactly the user's "from simple to complex, polish the abstraction" mandate.

## 12. What is explicitly deferred

- Full nested split grammar (multi-level recursive subdivision).
- Per-cell orient as free expressions (`"rot": "expr:..."`).
- Live mount internals (grid rows/cols still bake).
- Auto-generated shelf boards (only the `shelf_board` sugar is documented, out of critical path).
- Multi-level root (placed leaf becomes a root for the next level).

The measurement-first contract (positions come from geometry, never hardcoded) and the
"agent never writes VEX" rule are both **untouched**.
