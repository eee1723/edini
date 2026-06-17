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

ORIENTATION ASSERTS (consumed by houdini_verify_orientation — MANDATORY):
  - wheel_fl:        kind=radial,     expected_axis=X  (axle horizontal across bike)
  - wheel_fr:        kind=radial,     expected_axis=X
  - wheel_rl:        kind=radial,     expected_axis=X
  - wheel_rr:        kind=radial,     expected_axis=X
  - handlebar:       kind=elongated,  expected_axis=Z  (long axis across front)
  - frame_downtube:  kind=elongated,  expected_axis=Z  (or whatever the design calls for)
  - saddle:          kind=planar,     expected_axis=Y, signed=true  (must point UP)

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
