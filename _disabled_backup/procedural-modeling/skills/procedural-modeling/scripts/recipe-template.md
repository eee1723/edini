# RECIPE Template

State this recipe BEFORE writing any code. One recipe per asset.

```
RECIPE: [Asset Name]
TYPE: mechanical | organic | architectural | natural
BACKEND: python_sop | vex_wrangle | hybrid (python_sop + vex post-process)

COMPONENTS (each gets a @component_id — required for orientation verification):
  - component_id="wheel_fl": front-left wheel (radial, swappable)
  - component_id="handlebar": handlebar tube (elongated, swappable)
  - component_id="saddle": saddle plate (planar)
  - ...

PARAMETERS (minimum 5):
  - param_name: type [min, max] = default — description
  - param_name: type [min, max] = default — description

MODULAR ANCHORS (for Copy-to-Points):
  - anchor_name: count, purpose (e.g., "wheel_mount: 4, wheel placement positions")

ORIENTATION ASSERTS (consumed by verify_orientation — MANDATORY):
  - wheel_fl:        kind=radial,     expected_axis=X, construction_axis=Y  (axle horizontal across bike)
  - wheel_fr:        kind=radial,     expected_axis=X, construction_axis=Y
  - wheel_rl:        kind=radial,     expected_axis=X, construction_axis=Y
  - wheel_rr:        kind=radial,     expected_axis=X, construction_axis=Y
  - handlebar:       kind=elongated,  expected_axis=Z, construction_axis=Z  (long axis across front)
  - frame_downtube:  kind=elongated,  expected_axis=Z, construction_axis=Z
  - saddle:          kind=planar,     expected_axis=Y, signed=true, construction_axis=Y  (must point UP)

DETAIL PLAN:
  - Post-processing: [bevel, subdivide, noise, normal]
  - Surface detail: [panel lines / seams / rivets / texture variation]

VERIFICATION:
  - min_points: N
  - expected_components: [list]
  - detail_level: 3-4 (never accept 1-2)
  - orientation: ALL orientation_asserts must pass before commit
```

## Orientation assert kinds
- `radial`: component has rotational symmetry around an axis (wheel, gear). `expected_axis` = the axle direction.
- `elongated`: component is long/thin (tube, bar, handlebar). `expected_axis` = the long dimension.
- `planar`: component is flat (panel, plate, saddle). `expected_axis` = the surface normal. Use `signed=true` when direction matters (e.g. saddle must point up +Y).

**`construction_axis` is MANDATORY on every assert (A8).** It's the **local-space** axis the component is generated around (the axle for a radial wheel, the long dimension for an elongated tube, the normal for a planar surface). The builder bakes `edini_world_axis` from it; without it the check fails (`method:"no_axis"` — there is no PCA fallback). Pass an **empty** `orientation_asserts` array to skip orientation verification entirely.

---

## VARIANT SCATTER RECIPE (for `houdini_variant_scatter`)

Use this template when a repeated part has **multiple styles** (windows/doors/trees) that should be distributed with seeded randomness across a source piece library. Full schema: [references/declarative-builder.md](../references/declarative-builder.md#variant-scatter-变体散布).

```
RECIPE: [Asset Name]
TYPE: architectural | organic | mechanical
BACKEND: variant_scatter (houdini_variant_scatter)

VARIANTS (each gets a source geometry + integer variant index, auto-assigned):
  - variant 0: id="win_a" — window style A (e.g. 2-pane)
  - variant 1: id="win_b" — window style B (e.g. 4-pane with mullions)
  - variant 2: id="win_c" — window style C (e.g. arched)

SCATTER:
  - source: <python code emitting points with @P, optional @orient/@pscale>
  - seed: 42                      (integer — reproducible; drives attribfrompieces)
  - weights: {win_a: 0.6, win_b: 0.3, win_c: 0.1}   (echoed; see note below)

POSTPROCESS: [fuse, clean, normal(cusp 60°)]

PER-INSTANCE IDS: auto-assigned as {variant_id}_{id} (e.g. win_a_0, win_b_3)
  - `variant` is drawn onto each scatter point by attribfrompieces
  - `id` is the scatter point number, transferred via resettargetattribs

ORIENTATION ASSERTS (declare on variant source geometry via construction_axis):
  - win_a: construction_axis=Z, expected_axis=Z  (window faces +Z in source space)
  - win_b: construction_axis=Z, expected_axis=Z
  - win_c: construction_axis=Z, expected_axis=Z

VERIFICATION:
  - n_variants: 3
  - structure_advisory.passed: true (attribfrompieces + copytopoints = modular)
  - detail_level: 3-4 (variation across instances = real detail, not repetition)

NOTE: weights are echoed in the result but attribfrompieces currently assigns
variants uniformly across the source piece library. seed still controls
reproducibility. For true weighted distribution, set AFP's weightattrib/
weightmethod manually after build.
```

### When to choose variant scatter over single-template Copy-to-Points
- **Single template** (`build_procedural_asset` + one anchored component): all N instances identical. Use when the repeated part has ONE canonical form (e.g. 4 identical bike wheels).
- **Variant scatter** (`houdini_variant_scatter`): N instances each pick from M styles. Use when the repeated part has multiple interchangeable forms (windows, trees, debris) — this is what breaks the "procedural repetition" feel and lifts detail to Level 3+.
