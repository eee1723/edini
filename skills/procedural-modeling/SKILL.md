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

COMPONENTS:
  - component_name: description (generation method)
    SWAPPABLE: yes/no
  - component_name: description (generation method)
    SWAPPABLE: yes/no

PARAMETERS (minimum 5):
  - param_name: type [min, max] = default — description
  - param_name: type [min, max] = default — description

MODULAR ANCHORS (for Copy-to-Points):
  - anchor_name: count, purpose (e.g., "wheel_mount: 4, wheel placement positions")

DETAIL PLAN:
  - Post-processing: [bevel, subdivide, noise, normal]
  - Surface detail: [panel lines / seams / rivets / texture variation]

VERIFICATION:
  - min_points: N
  - expected_components: [list]
  - orientation_checks: ["wheels vertical", "roof on top", etc.]
  - detail_level: 3-4 (never accept 1-2)
```

## Modular Components — Copy-to-Points Pattern

For any repeated or user-swappable element, use the Copy-to-Points / Instance pattern:

```
Main structure → generates anchor points (with @orient, @pscale, @component_id attributes)
                         ↓
              Copy-to-Points ← Sub-component geometry (separate input)
```

### Rules:
1. **Identify swappable parts in the recipe** — wheels, keys, handles, windows, decorative elements
2. **Main body outputs anchor points** — not the sub-component geometry itself
3. **Sub-components are separate geometry streams** — connected via Copy-to-Points or ForEach
4. **Anchor points carry full transform** — `@orient` (quaternion), `@pscale`, `@N`, `@up`
5. **User can swap sub-component input** without touching the main structure

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

## Parameter Exposure

Every procedural asset MUST expose user-controllable parameters. Hardcoded Python variables are NOT acceptable.

### Method 1: Spare Parameters on Python SOP (preferred)
```python
node = hou.pwd()
geo = node.geometry()

# Read from spare parameters (user-editable in Houdini UI)
radius = node.evalParm("radius") if node.parm("radius") else 0.35
count = node.evalParm("count") if node.parm("count") else 8
height = node.evalParm("height") if node.parm("height") else 2.0
```

After sandbox success, add spare parameters:
```python
# In a follow-up houdini_run_python call after commit:
node = hou.node("/obj/asset_name/edini_generate")
ptg = node.parmTemplateGroup()
ptg.append(hou.FloatParmTemplate("radius", "Radius", 1, default_value=(0.35,), min=0.05, max=2.0))
ptg.append(hou.IntParmTemplate("count", "Count", 1, default_value=(8,), min=3, max=64))
ptg.append(hou.FloatParmTemplate("height", "Height", 1, default_value=(2.0,), min=0.1, max=10.0))
node.setParmTemplateGroup(ptg)
```

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

## Workflow

1. **Create a recipe** — Use the Recipe Template format above. List all components, parameters, anchors, and verification criteria.
2. **Probe unknown nodes** — If the recipe uses node types you haven't probed this session, probe them first.
3. **Choose backend** — `python_sop` for algorithmic mesh generation, `vex_wrangle` for per-element math, `hybrid` for both.
4. **Generate with sandbox** — Use `houdini_run_python_sandbox` with `commit_on_success=false`.
5. **Trust sandbox diagnostics** — The result includes `diagnostics` and `structural_checks`. No need for separate inspect calls.
6. **Add structural detail** — Panel lines, seams, secondary components, varied cross-sections. Then finishing: Normal SOP, optional bevel on render-visible hard edges.
7. **Expose parameters** — Add spare parms to the Python SOP for all recipe parameters.
8. **Capture and verify** — Use `houdini_capture_review` with 4-view quad, then `describe_image` with the 3D verification prompt.
9. **Repair loop** — If verification finds defects, fix the SPECIFIC issue and re-verify. See Visual Verification Protocol.
10. **Commit only after verification passes** — Use `houdini_commit_sandbox` only when structural AND visual checks pass.

## Visual Verification Protocol

### The 3D Verification Prompt
When calling `describe_image` on a procedural asset capture, ALWAYS pass this custom prompt:

```
Verify this procedural 3D asset. Check:
1. ORIENTATION: All components oriented correctly? (wheels vertical, roof on top, handles horizontal)
2. PROPORTIONS: Parts at reasonable proportions relative to each other?
3. SYMMETRY: If object should be symmetric, is it?
4. COMPLETENESS: All expected sub-components present?
5. INTERSECTION: Parts overlapping incorrectly?
6. SCALE: Sub-parts correct scale relative to whole?
7. DETAIL: Is geometry overly simplistic (just boxes/cylinders)?

Report: defects (critical/major/minor), detail_level (1-4), orientation_issues, missing_components.
Format: structured list, not prose.
```

### Mandatory Repair Loop
```
1. Capture (4-view quad)
2. describe_image with 3D verification prompt
3. IF critical or major defects found:
   a. Fix the SPECIFIC defect (do NOT regenerate from scratch)
   b. Re-capture
   c. Re-describe
   d. Repeat up to 3 times
4. IF 3 repair attempts fail:
   a. Report exact remaining defects to user
   b. Ask user whether to accept, adjust recipe, or try different approach
5. IF no critical/major defects AND detail_level >= 3:
   → Commit
```

### What counts as defects:
- **Critical**: Wrong orientation (wheels lying flat), missing major component, geometry not visible
- **Major**: Obvious proportion error, intersecting parts, no surface detail (level 1-2)
- **Minor**: Slight asymmetry, imperfect edge flow, cosmetic issues

### Capture (Screenshots)

**Use `houdini_capture_review`** for all visual verification:
```
houdini_capture_review(
  filepath="screenshots/asset_review.png",
  target_path="/obj/asset_name/OUT",
  views=["perspective", "top", "front", "right"],
  shading_mode="smooth"
)
```

- **Always pass `target_path`** — frames and isolates the generated asset.
- If capture returns an error, do not retry or explore alternative capture methods.
- `describe_image` with the 3D prompt is authoritative for structural verification.
- Geometry stats (point/prim counts, bounds) are authoritative for topology verification.

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
