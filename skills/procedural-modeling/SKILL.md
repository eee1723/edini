---
name: procedural-modeling
description: Use when the user mentions procedural modeling, programmatic generation, VEX scripting, Python SOP, algorithmic geometry, parametric design, 程序化建模, 程序化生成, or wants to create geometry/effects through code rather than manual node placement. Also use when the user asks to generate patterns, fractals, L-systems, scatter with rules, or any task where code drives geometry creation.
---

# Procedural Modeling in Houdini

**Code-first approach:** When the user wants procedural results, write and execute code (Python SOP or VEX) rather than manually assembling built-in primitive nodes.

## Code-First Priority

ALWAYS prefer writing geometry through code over assembling built-in primitive nodes:

| Approach | When to Use |
|----------|-------------|
| **Python SOP point/poly generation** | Complex shapes, parametric profiles, anything with loops/arrays/recursion |
| **VEX per-element operations** | Noise displacement, orient randomization, attribute-driven scatter, deformation |
| **Node network (built-in SOPs)** | ONLY for post-processing (PolyBevel, Subdivide, Normal) or when a built-in SOP directly solves a sub-problem with zero code needed (Boolean, Sweep on existing curve) |

Do NOT build shapes by stacking box + transform + merge when you could:
- Generate a profile curve in Python, then Sweep/Skin
- Create points with computed positions, then connect faces programmatically
- Use VEX to deform a base grid into a complex surface

**The goal is parametric controllability and procedural elegance, not node graph complexity.**

## Recipe Template

Before writing ANY code, state the recipe in this exact format:

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

### The @component_id Attribute (MANDATORY)

Every distinct geometric part of the asset MUST carry a `component_id` primitive
attribute. This is how `houdini_verify_orientation` knows which polygons belong
to each component for PCA.

In your Python SOP generator:
```python
geo.addAttrib(hou.attribType.Prim, "component_id", "")  # before any geometry

# When building each component's polygons:
poly = geo.createPolygon()
poly.addVertex(...)
poly.setAttribValue("component_id", "wheel_fl")  # unique per component
```

**Why this matters:** without `component_id`, the orientation gate cannot run
and `houdini_commit_sandbox` will refuse to commit.

## Modular Components — Copy-to-Points Pattern (MANDATORY)

**Single-Python-SOP monoliths are NOT acceptable.** If an asset has more
than ~3 distinct geometric components, or any repeated/swappable part, you
MUST decompose it into a Copy-to-Points / Instance structure.

A generator that builds the entire asset in one Python SOP > 200 lines is
a failure mode — even if the geometry renders correctly. Why:
- `houdini_verify_orientation` needs separate `@component_id` groups to PCA
- Users cannot swap a wheel without rebuilding everything
- Repairing one broken component requires regenerating the whole asset
- No isolated verification of sub-components

```
Main structure (Python SOP) → outputs anchor points
  with @component_id, @orient, @pscale attributes
                         ↓
              Copy-to-Points ← Sub-component geometry (separate Python SOP)
```

### Rules:
1. **Identify swappable parts in the recipe** — wheels, keys, handles, windows, decorative elements
2. **Main body outputs anchor points** — not the sub-component geometry itself
3. **Sub-components are separate geometry streams** — connected via Copy-to-Points or ForEach
4. **Anchor points carry full transform** — `@orient` (quaternion), `@pscale`, `@N`, `@up`, `@component_id`
5. **User can swap sub-component input** without touching the main structure
6. **Each sub-component carries its own `@component_id`** on its polygons

### Example (Vehicle):
```python
# Main body generates wheel anchor points
for i, (x, z) in enumerate(wheel_positions):
    pt = geo.createPoint()
    pt.setPosition((x, wheel_y, z))
    pt.setAttribValue("orient", wheel_orient_quat)
    pt.setAttribValue("pscale", wheel_radius)
    pt.setAttribValue("component_id", "wheel")

# Wheel geometry is a SEPARATE node/subnet
# Connected to Copy-to-Points as second input
# User replaces wheel subnet → all 4 wheels change
```

### Implementation in sandbox:
```python
node = hou.pwd()
container = node.parent()

# 1. Main body (Python SOP)
body_sop = container.createNode("python", "body_generate")
body_sop.parm("python").set(body_code)

# 2. Sub-component (separate Python SOP or subnet)
wheel_sop = container.createNode("python", "wheel_component")
wheel_sop.parm("python").set(wheel_code)

# 3. Copy-to-Points wiring
copy = container.createNode("copytopoints", "copy_wheels")
copy.setInput(0, wheel_sop)   # geometry to copy
copy.setInput(1, body_sop)    # points to copy onto (filtered by group)
```

## Parameter Exposure (in the sandbox — not after commit)

Every procedural asset MUST expose user-controllable parameters. Hardcoded
Python variables are NOT acceptable. Parameters must be installed on the
Python SOP **during the sandbox cook**, so they exist when the user opens
the node — not bolted on as a separate post-commit step.

### Method 1: Spare Parameters on Python SOP (preferred)

```python
node = hou.pwd()
geo = node.geometry()

# Declare the parameters with defaults and ranges
PARM_SPECS = [
    ("radius", hou.FloatParmTemplate("radius", "Radius", 1,
        default_value=((0.35,),), min=0.05, max=2.0,
        naming_scheme=hou.parmNamingScheme.Base1)),
    ("count",  hou.IntParmTemplate("count", "Count", 1,
        default_value=((8,),), min=3, max=64,
        naming_scheme=hou.parmNamingScheme.Base1)),
    ("height", hou.FloatParmTemplate("height", "Height", 1,
        default_value=((2.0,),), min=0.1, max=10.0,
        naming_scheme=hou.parmNamingScheme.Base1)),
]

# Install idempotently — only adds what's missing
ptg = node.parmTemplateGroup()
missing = [tmpl for name, tmpl in PARM_SPECS if ptg.find(name) is None]
for tmpl in missing:
    ptg.append(tmpl)
if missing:
    node.setParmTemplateGroup(ptg)  # triggers a recook; this cook continues with defaults

# Read (now guaranteed to exist)
radius = node.evalParm("radius")
count  = node.evalParm("count")
height = node.evalParm("height")

# ... generate geometry using radius, count, height ...
```

On the first cook, the parameters don't exist yet — `missing` is non-empty,
we install the templates (which triggers a recook), then the current cook
continues using the `default_value`s. On every subsequent cook the
parameters exist and the user's edited values are read directly.

### Method 2: VEX Channel References
```vex
float radius = chf("radius");    // Creates slider in UI
int count = chi("count");
vector offset = chv("offset");
float profile = chramp("profile", @curveu);  // Ramp widget
```

### Minimum parameters per asset type:
- **Vehicle**: wheelbase, body_length, body_height, wheel_radius, ground_clearance, spoke_count
- **Furniture**: seat_height, width, depth, leg_style, material_roughness
- **Architecture**: floors, floor_height, width, depth, window_density, balcony_depth
- **Organic/Plant**: trunk_height, branch_count, branch_angle, leaf_density, seed
- **Mechanical**: key_size, spacing, row_count, bevel_radius, base_thickness

## Detail Standards

A procedural asset is NOT complete when it has correct topology. Detail means STRUCTURAL COMPLEXITY, not surface smoothing.

**Do NOT stack PolyBevel + Subdivide as a substitute for real detail.** These are surface treatments that add no structural information. They are fine as finishing touches, but they do NOT raise the detail level.

### What counts as real detail:
- **Separate geometric parts** — door panels as distinct geometry, not painted on
- **Panel lines / seams as geometry** — inset faces or extruded edges, not just color
- **Secondary components** — bolts, hinges, vents, handles, trim pieces
- **Varied cross-sections** — a car fender's cross-section changes along its length
- **Functional sub-shapes** — brake calipers, mirror housings, key dish concavity
- **Construction logic** — visible how the object would be manufactured/assembled

### What does NOT count as detail:
- PolyBevel on all edges (this is finishing, not detail)
- Subdivide passes (this is smoothing, not detail)
- Normal recalculation (this is shading, not detail)
- Noise displacement (unless creating specific surface texture like bark or leather)

### Detail level rating:
- Level 1: Raw primitives (box, cylinder) — NEVER ACCEPTABLE
- Level 2: Correct silhouette but featureless, no sub-parts — NOT ENOUGH
- Level 3: Distinct sub-components, shaped profiles, panel lines or seams — MINIMUM
- Level 4: Secondary components (bolts, vents), varied cross-sections, construction logic — TARGET

### Finishing (apply AFTER structural detail is sufficient):
1. **Normal SOP** — cusp angle 30-60° for correct shading
2. **PolyBevel** — offset 0.01-0.03 on hard edges ONLY if asset will be rendered with smooth shading
3. **Subdivide** — ONLY on organic forms that need smoothing (not mechanical parts)

### Material Group Organization

No texturing required, but geometry MUST be organized for future material assignment:
- Assign primitive groups by material zone: `body`, `glass`, `rubber`, `metal_trim`, `chrome`, etc.
- Use `@shop_materialpath` attribute or primitive groups — either works
- Each visually distinct surface = separate group
- Example: car → groups: `body_paint`, `glass`, `rubber_tire`, `chrome_trim`, `interior`, `headlight_lens`

This enables one-click material assignment later without re-selecting geometry.

## Probe-First Rule

Before using ANY Houdini node type you haven't used in this session:

```python
# ALWAYS probe parameter names BEFORE setting them
n = container.createNode("nodetype", "_probe")
for p in n.parms():
    print(f"{p.name()} = {p.eval()}")
n.destroy()
```

**Do NOT guess parameter names.** Common traps:
- PolyBevel: `offset` not `bevel`, `divisions` not `iterations`
- Subdivide: `iterations` not `depth`
- Torus: `radx`/`rady` not `radius`
- Line: `dist` not `length`, controlled by `order` mode

## Common Pitfalls

Mistakes that waste 30-50% of procedural generation time. Avoid them.

### pscale semantics in Copy-to-Points
- `@pscale = 1.0` means **original size** of the source geometry (no scaling)
- `@pscale = wheel_radius` does NOT give you a wheel of that radius — it SCALES by that factor
- If your wheel geometry is already modeled at correct radius, set `@pscale = 1.0`
- If you need to scale: `@pscale = desired_size / source_geo_size`

### Attribute name collisions
- If both body and component have `@Cd`, Copy-to-Points may produce unexpected results
- Rule: only set `@Cd` on the FINAL merged output, not on intermediate component streams
- Use `material_zone` (string) for material intent, not `@Cd` color

### Group expression syntax in Copy-to-Points
- `targetgroup` parameter uses Houdini group syntax, NOT Python expressions
- Valid: `wheel_anchors` (group name), `@component_id==wheel` (attribute expression)
- Invalid: Python string operations, f-strings, regex

### Orient quaternion for Copy-to-Points
- `@orient` is a **quaternion** `(x, y, z, w)` — NOT Euler angles
- Identity (no rotation): `(0, 0, 0, 1)`
- 90° around Y: `(0, 0.7071, 0, 0.7071)`
- Use `hou.Quaternion(angle_degrees, axis_vector)` in Python to compute:
  ```python
  import hou
  q = hou.Quaternion()
  q.setToRotation(90, hou.Vector3(0, 1, 0))
  orient = (q[0], q[1], q[2], q[3])  # (x, y, z, w)
  ```

### Node destruction cascades
- If you destroy a node that has downstream connections, those connections break
- Always disconnect outputs before destroying: `node.setInput(idx, None)` on all consumers
- Better: rebuild the network in correct order rather than patching live connections

### Attribute creation order
- `geo.addAttrib()` MUST be called BEFORE creating any geometry that uses it
- Creating points first, then adding attribute = crash or silent failure
- Pattern: all `addAttrib` calls at the top, then geometry creation

## Language Selection

| Task | Use | Why |
|------|-----|-----|
| Per-element math, noise, vector ops | **VEX** (Attribute Wrangle) | Parallel, fast, idiomatic |
| Recursion, external data, complex algorithms | **Python SOP** | Full Python, libraries, recursion |
| Node network generation | **hou Python API** | Only option |
| Procedural textures (Copernicus) | **Python -> node CRUD** | Copernicus is node-based |

## Thinking Strategy: Divide & Conquer

**Build small procedural components first, then combine.** Do not try to generate one monolithic script. Instead:

1. Decompose the goal into independent sub-components (e.g., base shape + scatter rule + orientation + variation)
2. Build and verify each component separately (one wrangle / one Python SOP per component)
3. Combine with merge/Copy-to-Points/switch nodes
4. Verify the combined result visually

## Common Procedural Patterns

Use these proven patterns as building blocks. Don't reinvent from scratch.

### Cross-Section Skinning (vehicles, bottles, pipes with varying profiles)
```python
# Define cross-section curves at different positions along a spine
sections = []
for i, (pos, radius, shape_func) in enumerate(profile_data):
    pts = [shape_func(angle, radius) + pos for angle in angles]
    sections.append(pts)
# Skin between sections by connecting corresponding points with quads
for i in range(len(sections) - 1):
    for j in range(num_pts):
        j_next = (j + 1) % num_pts
        poly = geo.createPolygon()
        poly.addVertex(sections[i][j])
        poly.addVertex(sections[i][j_next])
        poly.addVertex(sections[i+1][j_next])
        poly.addVertex(sections[i+1][j])
```

### Radial Array (wheels, gears, fan blades, clock faces)
```python
import math
for i in range(count):
    angle = 2 * math.pi * i / count
    x = radius * math.cos(angle)
    z = radius * math.sin(angle)
    # Create component at (x, center_y, z) with orient pointing outward
```

### Profile Curve + Sweep (moldings, rims, tire treads)
```python
# Define 2D profile as a list of (x, y) points
profile = [(0, 0), (0.1, 0), (0.1, 0.05), (0.08, 0.08), ...]
# Create as NURBS or polygon curve, then use Sweep SOP along a path
```

### Panel Lines / Seams as Geometry (mechanical surfaces)
```python
# Method 1: Inset faces then extrude inward (creates grooves)
# Method 2: Create thin strip geometry along edges (separate group for material)
# Method 3: In VEX, select edges by angle threshold and create edge geometry
```
Panel lines are separate primitives in group `seam` — not color/attribute tricks.

### Boolean Subtraction for Cutouts (windows, vents, air intakes)
```python
# Create cutter geometry (box, cylinder) at the cut location
# Use Boolean SOP: input0=body, input1=cutter, operation=subtract
# Result: clean cutout with proper topology
```

### Group-Based Assembly (standard structure for any asset)
```python
# Every component gets a primitive group for material assignment
geo.addAttrib(hou.attribType.Prim, "material_zone", "")
# When creating each component's polygons:
for poly in component_polys:
    poly.setAttribValue("material_zone", "chrome_trim")
    geo.findGroup(hou.primType.Polygon, "chrome_trim")  # or createGroup
```

### Anchor Points for Copy-to-Points (standard pattern)
```python
# Output to a separate geometry stream or group
pt = geo.createPoint()
pt.setPosition(anchor_pos)
pt.setAttribValue("orient", quaternion_as_tuple)  # (x, y, z, w)
pt.setAttribValue("pscale", 1.0)  # 1.0 = original size of component
pt.setAttribValue("component_id", "wheel")
# Group the anchors: geo.createPointGroup("wheel_anchors").add(pt)
```

## VEX Guidelines

**VEX generated from scratch fails 64% of the time.** Mitigate with:

1. **Set the run-over class FIRST** — Before writing any VEX logic:
   - **Points**: per-point operations (position, velocity, custom attributes) — most common
   - **Primitives**: per-face operations (face normals, groups, coloring)
   - **Vertices**: per-vertex operations (UV manipulation, vertex normals)
   - **Detail (Numbers)**: once-per-geometry operations (bounding box, totals, global setup)

2. **Short snippets** — One wrangle = one operation. 5 transforms → 5 wrangles in sequence.
3. **Template patterns** — Adapt known building blocks:
   - Noise displacement: `@P += normalize(@N) * noise(@P * chf("freq")) * chf("amp");`
   - Density scatter: `if(rand(@ptnum) > chramp("density", fit01(@P.y, 0, 1))) removepoint(0, @ptnum);`
   - Orient along direction: `p@orient = quaternion(dihedral({0,1,0}, normalize(@vel)));`
   - Panel lines: `if(abs(frac(@P.x * chf("line_freq")) - 0.5) < chf("line_width")) @Cd = {0.2, 0.2, 0.2};`
4. **Validate** — After VEX, always check point counts, attributes, bounds via sandbox diagnostics.
5. **Diagnose repeated failures** — After 2 VEX failures on the same logic, switch to Python SOP.

## Python SOP Guidelines

When using `houdini_run_python_sandbox`, the sandbox creates a Python SOP node (`edini_generate`) for you. Your code runs inside a Python SOP cooking context:

```python
# Inside houdini_run_python_sandbox — this IS a Python SOP context
node = hou.pwd()
geo = node.geometry()
geo.clear()

# Add attributes BEFORE creating geometry
geo.addAttrib(hou.attribType.Point, "height", 0.0)
geo.addAttrib(hou.attribType.Prim, "group_id", 0)

# Build geometry
pt = geo.createPoint()
pt.setPosition((0, 0, 0))
pt.setAttribValue("height", 1.5)

poly = geo.createPolygon()
poly.addVertex(pt)
poly.setAttribValue("group_id", 0)
```

For node network generation inside a sandbox, create child nodes under `hou.pwd().parent()`:

```python
node = hou.pwd()
container = node.parent()  # the sandbox geo container
box = container.createNode("box", "my_box")
box.parm("sizex").set(1)
box.parm("sizey").set(1)
box.parm("sizez").set(1)
```

### String Safety
When embedding string literals in Python code that will pass through JSON → parm.set():
- Avoid backtick characters
- Escape backslashes as `\\\\` (double-escape for JSON + Python)
- Use raw strings (`r"..."`) for paths
- For special characters in data (key labels, etc.), use unicode escapes

## Harness Rules

- Do not use raw `houdini_run_python` for initial procedural asset generation when `houdini_run_python_sandbox` is available.
- Do not delete a failed procedural node before `houdini_collect_diagnostics`.
- Do not explore Qt widgets, main windows, viewport internals, or unsupported HOM APIs to capture images. Use `houdini_capture_review` and report clean failure if capture is unavailable.
- If a generated Python SOP, VEX wrangle, or node-network attempt fails, diagnose that attempt first. Diagnose before switching strategy — switch to Python SOP only if diagnostics confirm the current backend is unsuitable.
- Use `houdini_verify_asset` to run structural checks (point count, bounds, attribute presence) before visual verification.
- Use `houdini_discard_sandbox` to cleanly abort a failed attempt when diagnostics show the approach is fundamentally wrong.
- **NEVER use `commit_on_success=true` on first sandbox execution.** Always capture and verify visually before committing.
- **MANDATORY orientation gate**: Run `houdini_verify_orientation` with checks derived from the recipe's ORIENTATION ASSERTS before `houdini_commit_sandbox`. The gate is also enforced inside `commit_sandbox` — if `@component_id` exists and any check fails, commit is refused. Use `skip_orientation=true` ONLY with a documented reason (e.g. abstract art).
- **No monolithic Python SOPs**: A single `python` node > 200 lines for the whole asset is a failure. Decompose into Copy-to-Points structure with separate sub-component generators.
- **Tag every component**: Every distinct geometric part must carry `@component_id`. Without it, `houdini_verify_orientation` cannot run and `commit_sandbox` will refuse to commit.

## Workflow

1. **Create a recipe** — Include COMPONENTS with `@component_id`, ORIENTATION ASSERTS (mandatory), PARAMETERS list, MODULAR ANCHORS, DETAIL PLAN, and VERIFICATION criteria.
2. **Probe unknown nodes** — If the recipe uses node types you haven't probed this session, probe them first.
3. **Choose backend** — `python_sop` for algorithmic mesh generation, `vex_wrangle` for per-element math, `hybrid` for both.
4. **Generate with sandbox** — Use `houdini_run_python_sandbox` with `commit_on_success=false`. The sandbox code MUST: (a) call `geo.addAttrib(hou.attribType.Prim, "component_id", "")` before any geometry, then `poly.setAttribValue("component_id", "<id>")` on every component's polygons; (b) install spare parameters idempotently on the cooking node; (c) use Copy-to-Points for any repeated/swappable part.
5. **Trust sandbox diagnostics** — The result includes `diagnostics` and `structural_checks`. No need for separate inspect calls.
6. **Add structural detail** — Panel lines, seams, secondary components, varied cross-sections. Then finishing: Normal SOP, optional bevel on render-visible hard edges. Preserve `@component_id` tags.
7. **Run `houdini_verify_orientation`** — Pass the recipe's ORIENTATION ASSERTS as `checks`. This is the authoritative gate. If any check fails, apply the hint quaternion to the SOURCE code (don't try to rotate post-hoc on geometry) and re-run the sandbox BEFORE moving to visual verification.
8. **Capture and verify (visual layer)** — `houdini_capture_review` with 4-view quad, then `describe_image` with the 3D verification prompt. Visual catches missing components, intersections, proportion defects — NOT orientation.
9. **Repair loop** — Fix SPECIFIC defects (orientation: use the hint quaternion in source; visual: address the named defect). Re-verify. Up to 3 cycles, then ask the user.
10. **Commit only when both layers pass** — `houdini_commit_sandbox` re-runs the orientation gate as a final check. If `@component_id` exists and checks fail, commit is refused — you cannot override this except with `skip_orientation=true` and a documented reason.

## Visual Verification Protocol

### Two-Layer Verification

Procedural assets require BOTH layers of verification. Vision models cannot
reliably detect orientation defects (they hallucinate "wheels vertical ✅"
for wheels lying flat). Geometry-based checks are authoritative for orientation.

| Layer | Tool | What it catches | Authority |
|---|---|---|---|
| **Programmatic** | `houdini_verify_orientation` | Wrong axle direction, flipped components, misaligned axes | **AUTHORITATIVE — gate** |
| **Visual** | `houdini_capture_review` + `describe_image` | Missing components, weird proportions, intersection | Advisory |

### Mandatory Pre-Commit Sequence

```
1. houdini_verify_orientation on the sandbox display node
   - Pass all checks from the recipe's ORIENTATION ASSERTS section
   - If any check fails, apply the hint quaternion and re-run sandbox
2. houdini_capture_review (4-view quad) for visual sanity
3. describe_image with the 3D prompt — flag missing/intersecting parts
4. Repair loop: fix specific defect → re-verify → repeat up to 3 times
5. houdini_commit_sandbox — runs orientation gate as final check
```

### The 3D Verification Prompt (for describe_image)

Use this prompt for visual checks. Note: it CANNOT detect orientation —
rely on `houdini_verify_orientation` for that.

```
Verify this procedural 3D asset. Check:
1. PROPORTIONS: Parts at reasonable proportions relative to each other?
2. SYMMETRY: If object should be symmetric, is it?
3. COMPLETENESS: All expected sub-components present (compare to recipe)?
4. INTERSECTION: Parts overlapping incorrectly?
5. SCALE: Sub-parts correct scale relative to whole?
6. DETAIL: Is geometry overly simplistic (just boxes/cylinders)?

DO NOT report on orientation — that is verified programmatically.
Report: missing_components, intersection_issues, proportion_defects, detail_level (1-4).
Format: structured list, not prose.
```

### Orientation Check Examples

```python
# Wheel: axle should be horizontal (along X for a bike facing +Z)
houdini_verify_orientation(
    node_path="/obj/edini_sandbox_.../edini_generate",
    checks=[
        {"component_id": "wheel_fl", "kind": "radial", "expected_axis": "X"},
        {"component_id": "wheel_fr", "kind": "radial", "expected_axis": "X"},
        {"component_id": "wheel_rl", "kind": "radial", "expected_axis": "X"},
        {"component_id": "wheel_rr", "kind": "radial", "expected_axis": "X"},
        # Handlebar long axis transverse (Z direction for a bike facing +Z)
        {"component_id": "handlebar", "kind": "elongated", "expected_axis": "Z"},
        # Saddle normal must point up (signed=true)
        {"component_id": "saddle", "kind": "planar", "expected_axis": "Y", "signed": True},
    ]
)
```

### Repair Loop for Orientation Failures

When `houdini_verify_orientation` returns a failure, each failed check
includes a `hint` field with the exact quaternion to apply:

```python
# Example failed check output:
{
    "component_id": "wheel_fl",
    "kind": "radial",
    "expected_axis": "X",
    "detected_axis": "Y",           # wheel lying flat!
    "angle_error_deg": 89.7,
    "passed": False,
    "hint": "wheel_fl rotational symmetry axis (axle) currently along Y
             (...). Expected X. Apply quaternion (x,y,z,w)=(0,0,-0.7,0.7)
             to the component's geometry, or pre-multiply the generating
             transform: hou.Quaternion(0.7, hou.Vector3(0, 0, -0.7))."
}
```

Fix by applying the hint inside the generator code (don't try to rotate
post-hoc on the geometry — fix the source).

### What counts as defects (visual layer):
- **Critical**: missing major component, geometry not visible
- **Major**: obvious proportion error, intersecting parts, no surface detail (level 1-2)
- **Minor**: slight asymmetry, imperfect edge flow, cosmetic issues

(Note: "wrong orientation" is no longer in this list — it's caught by the
programmatic gate, not the visual layer.)

### Capture (Screenshots)

**Use `houdini_capture_review`** for all visual verification:
```
houdini_capture_review(
  filepath="review.png",  # auto-routed to $HIP/Edini_screenshots/<task>/
  target_path="/obj/asset_name/OUT",
  views=["perspective", "top", "front", "right"],
  shading_mode="smooth"
)
```

- **Always pass `target_path`** — frames and isolates the generated asset.
- Filepath is auto-routed to the session's screenshot folder; AI-supplied
  basenames are preserved with sequence numbering (`review_001.png`, etc.).
- If capture returns an error, do not retry or explore alternative capture methods.

## Common VEX Pitfalls

- **Wrong run-over class** — produces completely different results. Always set explicitly.
- `rand()` returns float; for vectors use `set(rand(s), rand(s+1), rand(s+2))`
- No `float3` — use `vector` with `set()`
- `foreach` syntax: `foreach (elem; array) { ... }`
- Matrix multiply order: `P * M` not `M * P` (column-major)

## Houdini 21 SOP Parameter Reference

Node parameter names differ from older versions. Always use these exact names:

### Line SOP
| Purpose | Parm name | Type |
|---------|-----------|------|
| Origin X/Y/Z | `originx`, `originy`, `originz` | float |
| Direction X/Y/Z | `dirx`, `diry`, `dirz` | float |
| Length | `dist` | float |
| Num points | `points` | int |

### Circle SOP
| Purpose | Parm name | Type |
|---------|-----------|------|
| Primitive type | `type` | int (1=Polygon) |
| Radius X/Y | `radx`, `rady` | float |
| Divisions | `divs` | int |

### PolyBevel SOP
| Purpose | Parm name | Type |
|---------|-----------|------|
| Bevel offset | `offset` | float (NOT `bevel`) |
| Divisions | `divisions` | int (NOT `iterations`) |

### Subdivide SOP
| Purpose | Parm name | Type |
|---------|-----------|------|
| Iterations | `iterations` | int (NOT `depth`) |

### Transform SOP (xform)
| Purpose | Parm name |
|---------|-----------|
| Translate | `tx`, `ty`, `tz` |
| Rotate | `rx`, `ry`, `rz` |
| Scale | `sx`, `sy`, `sz` |

### PolyExtrude SOP
| Purpose | Parm name |
|---------|-----------|
| Distance | `dist` |
| Output front | `outputfront` (1=front faces only) |

### Discovery
If unsure about a node's parm names, create a throwaway probe:
```python
n = container.createNode("nodetype", "_probe")
for p in n.parms():
    print(f"{p.name()} = {p.eval()}")
n.destroy()
```

## Copernicus (Procedural Textures)

1. Create nodes via `houdini_run_python_sandbox` or future image-context harness tools in `/img` context
2. Prefer Copernicus nodes (`copernicus::noise/ramp/math/merge`) over legacy COP2
3. Import SOP data via `sopimport` COP node
4. Bake via `hou.node(...).parm("execute").pressButton()` on ROP
