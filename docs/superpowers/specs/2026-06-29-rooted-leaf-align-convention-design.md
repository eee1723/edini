# Rooted Modeling — Leaf Align Convention (orient point-class fix + align_axis + origin normalize + grouped CTP)

**Date:** 2026-06-29
**Skill / area:** `skills/rooted-modeling` → `python3.11libs/edini/{assembly_builder,vex_strategies,measure}.py`
**Status:** Design approved by user (brainstormed 2026-06-29), ready for implementation plan

## 1. Problem statement

The user verified the M2 rooted-modeling build (`edini_showcase.hip`, a bicycle
platform + 4 wheels) and found four problems, all rooted in the same gap: the
**leaf layer has no explicit align convention**.

1. **`mount_wheel_fr` orient never takes effect.** The wrangle writes
   `p@orient = dihedral(...)` while running in `class=detail`, so VEX's export
   semantics turn it into a **detail** attribute. `copytopoints::2.0` only reads
   **point**-class `orient`, so the wheel never rotates.
2. **Copy input 0 (the shape) orientation is arbitrary.** Houdini `copytopoints`
   aligns the source's `+Z` to `N` (legacy), or uses `orient` directly. The
   builder hardcodes `dihedral({0,1,0}, dir)` — "source +Y → measured direction"
   — but a torus wheel's symmetry axis is **+Z** (disc lies in XY), so even with
   orient working, the wheel would be tilted.
3. **No way to normalize the leaf's origin pose before copy.** A wheel whose
   geometry center ≠ axle center, or that must sit clear of the root, has no
   mechanism to be displaced to a standard pose (+Z / +Y / -Y) before stamping.
4. **Four identical wheels produce four identical shapes + four CTPs.** When N
   mounts of identical shape could share one copy chain, the builder makes N
   copies of the shape geometry.

### First-principles reframing

`copytopoints::2.0` instance orientation is governed **only** by point-class
`orient` (quaternion). Placing a leaf correctly requires satisfying **two
independent conditions**, both currently implicit:

- **Direction condition:** some axis of the leaf (the *align axis*) must be
  rotated onto the direction measured off the root.
- **Position condition:** the leaf's *origin* (after normalization) must land
  on the mount point clear of the root.

Making both conditions explicit is the entire design. The measurement-first
contract (positions come from `bbox_corner`/`grid_on_face`/`array`, never
hardcoded coordinates) is **untouched**.

## 2. Scope

**In scope:**
- Fix the orient point-class bug (problem 1).
- Introduce `align_axis` on `mount.orient` and `leaf` (problem 2).
- Introduce `leaf.origin` with `bbox_center` / `bbox_face:<±XYZ>` / explicit
  `[x,y,z]` anchors + optional `offset` (problem 3).
- Group structurally-identical leaves onto one shape + one CTP (problem 4).
- Update `measure.orient_to_align_y` → generic `orient_to_align(axis, dir)`.
- Update the `car` verified example to the new convention (regression).
- Add a `bicycle` example exercising all four fixes.

**Out of scope (YAGNI):**
- Multi-level root (bike frame → fork → handlebar) — M3.
- Per-instance orient within a grid/array — one orient per mount is enough.
- `matchsize` SOP for normalization — VEX wrangle is more controllable.
- Any change to the measurement primitives (`bbox_corner`, `grid_on_face`,
  `array`, …) — semantics unchanged.

## 3. Data model — assembly JSON schema extensions

All new fields have defaults, so existing assemblies build unchanged.

### 3.1 `mount.orient.align_axis` (problem 2)

```jsonc
"orient": {
  "from": "root",
  "align_axis": "+Z",                 // NEW. default "+Y". leaf's THIS axis → measured dir
  "from_a": { "measure": "bbox_corner", "axes": "-X-Y+Z" },
  "from_b": { "measure": "bbox_corner", "axes": "+X-Y+Z"  }
}
```

Semantics: `p@orient = dihedral(<align_axis_vec>, normalize(B - A))`.
Legal values: `±X`, `±Y`, `±Z` (six).
- torus wheel → `"+Z"` (torus default symmetry axis is +Z).
- box keycap, anything grown along +Y → default `"+Y"`.

### 3.2 `leaf.align_axis` override + `leaf.origin` (problems 2 & 3)

```jsonc
"leaves": [{
  "id": "wheel",
  "mount": "wheel",
  "scale": "wheel_radius",
  "align_axis": "+Z",            // OPTIONAL: overrides mount.orient.align_axis for this leaf
  "origin": {                    // OPTIONAL: normalize leaf pose before copy
    "anchor": "bbox_center",     //   "bbox_center" | "bbox_face:+Z" | ... | [x,y,z]
    "offset": [0, 0, 0.1]        //   additional translate after normalization (param exprs ok)
  },
  "shape": { "type": "torus", "params": { "radx": 1.0, "rady": 0.08 } }
}]
```

**`align_axis` resolution priority:** `leaf.align_axis` > `mount.orient.align_axis` > default `"+Y"`.

**`origin.anchor` values:**
| value | which point moves to the origin |
|-------|---------------------------------|
| `bbox_center` | geometry bbox center |
| `bbox_face:+X` / `-X` / `+Y` / `-Y` / `+Z` / `-Z` | center of that bbox face |
| `[x, y, z]` | explicit point |

Semantics: the chosen point is translated to the origin, the rest of the
geometry follows; then `offset` is added. Default when `origin` omitted: **no
normalization node** (current behavior — backward compatible).

- wheel → `anchor: "bbox_center"`, `offset: [0, 0, <clearance>]` to push clear
  of the platform (problem 3's "avoid root intersection").
- chair leg / support → `anchor: "bbox_face:-Y"` so its base sits on the mount
  and the body hangs in +Y.

## 4. Build layer implementation

### 4.1 orient point-class fix (problem 1) — `vex_strategies._orient_fragment`

Current (buggy):
```vex
p@orient = dihedral({{0,1,0}}, __dir);   // detail-wrangle body → detail attribute
```

Fixed: compute the quaternion, then write it onto **every point** via
`setpointattrib`, guaranteeing point-class:
```vex
vector  __dir = normalize(__db - __da);
vector4 __q   = dihedral({{ax},{ay},{az}}, __dir);
for (int __i = 0; __i < npoints(geoself()); __i++) {
    setpointattrib(geoself(), "orient", __i, __q, "set");
}
```
`{ax},{ay},{az}` are Python-injected from the resolved `align_axis`. The wrangle
still runs `class=detail` (it must — it `addpoint`s), but the attributes land on
the points, where CTP reads them.

### 4.2 align_axis injection (problem 2) — `_orient_fragment`

```python
def _orient_fragment(orient_spec: dict, align_axis: str = "+Y") -> str
```
Python parses the sign-string into a unit vector literal injected into the VEX.
Six axes supported. `measure.orient_to_align_y` is generalized to
`orient_to_align(align_axis, direction)`; the oracle self-check
(`_verify_align_y`) is generalized to `_verify_align(axis, orient, direction)`
and extended across all six axes.

### 4.3 origin normalization node (problem 3) — `assembly_builder`

Between the leaf shape and its CTP, if `leaf.origin` is present, insert a
point-wrangle `<leaf>_normalize`:
```vex
// anchor = bbox_center
@P -= getbbox_center(0);
@P += chv("offset");
// (bbox_face:<±XYZ>: subtract the chosen face-center; explicit [x,y,z]: subtract it)
```
Skipped when `origin` absent (backward compatible). Implemented as VEX (not
matchsize) so the anchor can be a semantic point (face center, axle center) that
bbox-only `matchsize` cannot express reliably.

### 4.4 grouped CTP (problem 4) — `build_assembly` leaf loop restructure

Group leaves by `(shape structurally identical, scale value identical,
resolved align_axis identical, origin identical)`. "Shape structurally
identical" = same `shape.type` AND identical `shape.params` (two different
wheel radii ⇒ different groups). "Resolved align_axis" = the
`leaf.align_axis ?? mount.orient.align_axis ?? "+Y"` value after override
resolution (so two leaves whose leaf/mount fields differ but resolve to the
same axis still group). Per group:
1. Build **one** shape node.
2. Build **one** `<group>_normalize` node if `origin` present.
3. Merge the group's mounts into one sub-cloud.
4. **One** CTP: input 0 = normalize (or shape), input 1 = sub-cloud.

Grouping key is strict — a different shape `params` value (e.g. two wheel
radii) ⇒ separate groups. Any leaf can degenerate to its own group (current
behavior). Net effect for the bicycle: 4 identical torus wheels → **1 shape + 1
CTP + 4 mounts merged**.

**Constraint:** grouping is an **optimization** that must not change assembly
semantics. Two leaves are in the same group only if their stamped output would
be byte-identical (modulo mount position).

## 5. Validation additions (assembly_builder.validate_assembly)

- `orient.align_axis` ∈ `{±X, ±Y, ±Z}` else `MOUNT_BAD_ALIGN_AXIS`.
- `leaf.align_axis` (if present) same check.
- `leaf.origin.anchor` is `"bbox_center"` | `"bbox_face:<±XYZ>"` | 3-list
  else `LEAF_BAD_ORIGIN`.
- `leaf.origin.offset` (if present) is a 3-list of numbers / param exprs,
  with param refs checked against declared params.

## 6. Test strategy — mock + hython two-tier (per project convention)

### 6.1 mock layer (`tests/test_assembly_builder.py`)
- **orient point-class:** generated snippet contains
  `setpointattrib(geoself(), "orient", ...)` and does **not** contain a bare
  `p@orient =` in the detail body.
- **align_axis injection:** `_orient_fragment(spec, "+Z")` emits a dihedral
  whose source axis is `{0,0,1}`.
- **grouped CTP:** 4 structurally-identical wheel leaves ⇒ build produces 1
  shape node + 1 CTP node (asserted by node count / type), not 4+4.
- **origin node:** a leaf with `origin` has a `<leaf>_normalize` wrangle
  between shape and CTP; a leaf without `origin` does not.
- **regression:** existing car/keyboard/staircase cases unchanged (new fields
  default-valued).

### 6.2 hython layer (`tests/test_assembly_hython.py`) — decisive
- **wheel facing (primary, geometry-level):** for each wheel instance, take its
  bbox sizes on the three axes; the **thinnest** axis (torus `radx=1, rady=0.08`
  ⇒ thickness ≈ 0.16 on its symmetry axis, ≈ 2 on the others) must be the one
  aligned with the measured axle direction. Asserts the **final** orientation
  the user sees, independent of whether CTP preserved attributes.
- **orient at the cloud (secondary):** read `p@orient` off the mount cloud
  (pre-CTP), rotate the align-axis basis vector by it, normalize, and assert ≈
  the measured axle unit vector. Proves the intermediate data is correct.
- **live facing follow:** change `length` 4→8, recook; wheel positions move AND
  facing stays correct (current live tests only assert position — extend to
  facing).
- **one CTP, four wheels:** bicycle cloud has 4 points, 1 CTP, OUT has 4 wheel
  geometries.
- **car regression:** car's 4 wheels (now annotated `align_axis: "+Z"`) still
  face correctly under the new convention.

### 6.3 oracle layer (`tests/test_measure.py`)
- `orient_to_align(axis, direction)` correctness across 6 axes × multiple
  directions, verified by the generalized `_verify_align`.

## 7. Skill doc + tool schema updates

- `skills/rooted-modeling/SKILL.md`: document `align_axis`, `origin`, grouped
  CTP; update the car example annotation (`align_axis: "+Z"`); add a bicycle
  verified example section; note the orient point-class fix.
- `pi-extensions/edini-tools/tools/rooted.ts` (`build_assembly` description /
  promptGuidelines): mention `align_axis` and `origin` fields so the agent
  knows they exist.
- `scripts/show_assemblies.py`: add the bicycle to the showcase so
  `edini_showcase.hip` demonstrates all four fixes.

## 8. Risks & mitigations

| risk | mitigation |
|------|-----------|
| align_axis changes break car regression | car annotated `align_axis:"+Z"`; hython regression gate |
| grouped CTP merges leaves that should differ | strict grouping key (shape+scale+align_axis+origin all equal) |
| origin normalization hides a misplaced leaf | normalize only translates to a *standard pose*, never to a coordinate; mount still derives position by measurement |
| orient setpointattrib perf on huge clouds | mount clouds are tiny (≤ grid/array size); non-issue |

## 9. Open items

None — all design questions resolved during brainstorming.
