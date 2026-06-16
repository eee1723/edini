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

## Modular Components — Copy-to-Points Pattern (MANDATORY + HARD GATE)

**Single-Python-SOP monoliths are NOT acceptable.** If an asset has more
than ~3 distinct geometric components, or any repeated/swappable part, you
MUST decompose it into a Copy-to-Points / Instance structure.

**This is now a HARD GATE, not just prose.** `houdini_commit_sandbox` runs
`_check_modular_structure` and REFUSES to commit an asset that has:
- ≥3 distinct `component_id` values, ALL originating from a single Python SOP,
  with NO modular assembly nodes (copytopoints/sweep/foreach/boolean).

The gate returns the exact reason + a decomposition suggestion. To bypass it
you must pass `skip_structure_check=true` with a documented reason (e.g. a
genuinely simple single-piece asset like one fractal or one parametric surface).
Do NOT use the bypass for multi-component assets.

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

### Anti-pattern → Correct pattern (bicycle example)

**❌ MONOLITHIC (gate will reject this):**
```
edini_generate (python, 400 lines)
  ↓ builds frame + wheels + handlebar + saddle + crankset ALL inline
  ↓ tags each with component_id but everything comes from THIS one node
OUT (null)
```
The `structure_advisory` in the sandbox result will flag this. The commit
gate will refuse it.

**✅ MODULAR (gate accepts this):**
```
body_generate (python) → frame tubes + anchor points (@component_id, @orient, @pscale)
wheel_component (python) → single wheel geometry
saddle_component (python) → saddle geometry
handlebar_component (python) → handlebar geometry
copytopoints ×3 ← instance each component onto its anchors
merge → normal → OUT
```
Each sub-component is a separate geometry stream the user can swap. Frame
tubes should use Sweep 2.0 with profile curves, not hand-built faces.

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

> **The snippet above MUST run in `network_mode=true`.** See [Forbidden
> Patterns](#forbidden-patterns) and [Network Mode](#network-mode-for-modular-assets).
> A Python SOP's cook body cannot `createNode` on siblings — Houdini raises
> "Infinite recursion in evaluation".

## Forbidden Patterns

Patterns that reliably break the sandbox or waste 10+ iterations. Memorize them.

### 1. `createNode` inside a Python SOP cook body → Infinite recursion
A Python SOP's `cook()` evaluates its `python` parm. If that code calls
`hou.node(...).createNode(...)` (creating network nodes), Houdini re-enters
cook evaluation to validate the new network → infinite recursion:
```
Error: Infinite recursion in evaluation
```
**Rule:** the cook body may ONLY emit geometry via `node.geometry().createPoint()`
/ `createPolygon()` / `addAttrib()` on its OWN geometry. To BUILD a network,
use **`network_mode=true`** (the code runs in the container, not inside a cook).

| You want to… | Wrong | Right |
|---|---|---|
| Emit one piece of geometry | single-SOP cook (`geo.createPoint`) | single-SOP cook ✅ |
| Build body_generate + copytopoints + OUT | `createNode` inside cook ❌ | `network_mode=true` ✅ |
| Add a Sweep on a curve | create sweep in cook ❌ | `network_mode=true` ✅ |

### 2. Using raw `houdini_run_python` for asset generation
Raw `houdini_run_python` builds nodes directly on the LIVE scene
(`/obj/bicycle_builder`), bypassing the sandbox entirely — so the modular
structure gate, orientation gate, and health check never run on the asset, and
a failed cook leaves half-built nodes in the scene. The "not sandboxed" warning
is not cosmetic.
**Rule:** Always go through `houdini_run_python_sandbox`. If single-SOP mode
rejects your `createNode`, switch to `network_mode=true`, not to raw python.

### 3. ForEach with a mis-wired block_begin blockpath
`foreach_begin(method=piece)` needs `blockpath` pointing at the matching
`block_end`. If it's blank or wrong: `Invalid sop specified`. The block_end
owns the `class` / `method` / `iterations` parms, NOT the block_begin.
**Rule:** prefer **Sweep 2.0 + Copy-to-Points** over hand-wired ForEach for
tube/frame generation — it's one node with no blockpath bookkeeping. See the
parameter cheat-sheet below.

### 4. Guessing Houdini 21 parameter names
H21 renamed several parms (e.g. `attribpromote` uses `inname`/`inclass`/`outclass`,
not `original`). Guessing burns a get_node_info round per parm. **Either use the
cheat-sheet below, or probe once** — never guess.

## Network Mode (for modular assets)

`houdini_run_python_sandbox` has a **`network_mode`** flag. Use it for ANY
multi-component asset (anything that needs `createNode` on more than one SOP).

- **`network_mode=false` (default):** code is the cook body of ONE
  `edini_generate` Python SOP. Geometry via `hou.pwd().geometry()`. Cannot
  `createNode`. Use for single-piece generators.
- **`network_mode=true`:** code runs in the sandbox geo **container**. It can
  `createNode` child SOPs, wire them, and build a full modular network. The
  harness then finds your `OUT` node (or the largest `@component_id`-bearing
  node), cooks it, and runs diagnostics + the structure gate on the result —
  exactly as the commit gate would. This is how modular assets reach the
  sandbox → gate pipeline instead of leaking onto the live scene.

### Network-mode recipe skeleton
```python
# Runs in network_mode=true. `sandbox_root` is the injected geo container.
container = sandbox_root            # or hou.node(sandbox_root_path)

# 1. Body: emits anchor points with @component_id/@orient/@pscale
body = container.createNode("python", "body_generate")
body.parm("python").set(BODY_CODE)   # BODY_CODE builds frame + anchor points

# 2. One sub-component generator (a single wheel, modeled at unit radius)
wheel = container.createNode("python", "wheel_component")
wheel.parm("python").set(WHEEL_CODE)

# 3. Sweep the tube profile along a curve (no ForEach bookkeeping)
#    profile = container.createNode("circle", "tube_profile")
#    spine   = container.createNode("curve", ...)   # or driven by body
#    sweep   = container.createNode("sweep::2.0", "frame_sweep")
#    sweep.setInput(0, spine); sweep.setInput(1, profile)

# 4. Copy-to-Points: instance wheel onto the body's anchor points
copy = container.createNode("copytopoints::2.0", "copy_wheels")
copy.setInput(0, wheel)   # geometry to stamp
copy.setInput(1, body)    # points to stamp onto

# 5. Merge everything + OUT (the harness auto-finds this node)
merge = container.createNode("merge", "merge_all")
merge.setInput(0, copy)
# merge.setInput(1, sweep) ...
out = container.createNode("null", "OUT")
out.setInput(0, merge)
out.setDisplayFlag(True)
```
Each generator's code (BODY_CODE, WHEEL_CODE) is a *single-SOP-style* script:
`node = hou.pwd(); geo = node.geometry(); geo.clear(); ...` — it runs when that
child Python SOP cooks, which is fine because it only emits its OWN geometry.
The `createNode` calls live in the **network-mode body**, not in a cook.

## Declarative Recipe Builder (PREFERRED for multi-component assets)

`houdini_build_procedural_asset` is the **preferred path** for any
multi-component asset (vehicles, furniture, anything with swappable/repeated
parts). You submit a JSON **recipe** and the harness **deterministically**
assembles the modular network — you never write `createNode`/`setInput`/
`blockpath`/wiring. This eliminates the whole class of imperative-Houdini-API
errors that dominate failed procedural runs.

**When to use which build path:**

| Situation | Tool |
|---|---|
| Multi-component asset (body + wheels/handles/legs via Copy-to-Points) | **`houdini_build_procedural_asset`** (this section) — PREFERRED |
| Non-standard topology you can't express as a recipe | `houdini_run_python_sandbox(network_mode=true)` (hand-write the network) |
| Genuinely single-piece generator (one fractal, one surface) | `houdini_run_python_sandbox` (default single-SOP mode) |

### The recipe schema

```jsonc
{
  "asset_name": "bicycle",
  "units": "meters",
  "params": {                                    // A2-station: asset-level shared params (optional)
    "wheelbase": {"default": 1.0, "min": 0.5, "max": 2.0, "label": "Wheelbase"},
    "wheel_r":   {"default": 0.35, "label": "Wheel Radius"}
  },
  "components": [
    {
      "id": "frame",                              // -> component_id prim attr value
      "code": "<single-SOP python: emit geometry, tag component_id='frame'>",
      "reads": ["wheelbase", "wheel_r"],          // A2: params this component reads (via hou.ch)
      "anchors": []                               // empty -> goes straight into merge
    },
    {
      "id": "wheel",                              // template id (unit-radius wheel)
      "code": "<emit a unit-radius wheel; tag prims component_id='wheel'>",
      "anchors": [                                // A2: position_expr strings reference params -> linked
        {"position_expr": ["wheelbase/2", "wheel_r", "-0.55"], "orient": [0,0,0,1], "pscale": 1.0, "component_id": "wheel_fl"},
        {"position_expr": ["wheelbase/2", "wheel_r",  "0.55"], "orient": [0,0,0,1], "pscale": 1.0, "component_id": "wheel_fr"},
        {"position_expr": ["-wheelbase/2", "wheel_r", "-0.55"], "orient": [0,0,0,1], "pscale": 1.0, "component_id": "wheel_rl"},
        {"position_expr": ["-wheelbase/2", "wheel_r",  "0.55"], "orient": [0,0,0,1], "pscale": 1.0, "component_id": "wheel_rr"}
      ]                                            // (static "position": [x,y,z] numbers are also valid)
    }
  ],
  "postprocess": [                                // optional SOP Chain after merge
    {"type": "normal", "params": {"cuspangle": 60}} // parm NAMES are version-specific —
                                                   // verify with houdini_node_parms("normal")
  ],
  "orientation_asserts": [                        // flows to commit_sandbox's orientation gate
    {"component_id": "wheel_fl", "kind": "radial", "expected_axis": "X",
     "construction_axis": "Y"},                    // B-station: local axis the wheel is generated around
    {"component_id": "frame", "kind": "elongated", "expected_axis": "Z",
     "construction_axis": "Z"}
  ],
  "expected": {"min_points": 100}                 // optional, for verify_asset
}
```

### Component code rules (CRITICAL)
Each component's `code` is a **single Python SOP cook body**. It MUST:
1. Read its own geometry: `node = hou.pwd(); geo = node.geometry()`.
2. Declare the attribute **before** geometry:
   `geo.addAttrib(hou.attribType.Prim, "component_id", "")`.
3. Tag every prim: `poly.setAttribValue("component_id", "<id>")`.
4. **NEVER call `createNode`** — the builder owns the network. Only emit
   geometry on the cooking node. Violating this triggers infinite recursion.

The builder **post-checks** `component_id` presence on the cooked OUT and
reports any missing ids in `component_id_check.missing`.

### Anchor semantics
- `position`: world-space `[x, y, z]` where the stamp lands.
- `orient`: quaternion `[x, y, z, w]` (NOT Euler). Identity = `[0,0,0,1]`.
- `pscale`: `1.0` = source geometry at original size. Model stamped components
  at **unit scale** and set `pscale` to real size (cleanest), or model at real
  scale and use `1.0`.
- `component_id` (per anchor): the **per-instance** id (e.g. `wheel_fl`). The
  builder overwrites each stamped instance's prim `component_id` with this, so
  `houdini_verify_orientation` can PCA each instance separately.

### What the builder assembles (deterministic — you don't write this)
```
<id>_python     (your code)        ─┐
<id>_anchors    (builder: points)  ─┤-> copy_<id> (copytopoints) -> <id>_idfix (overwrite component_id) -> merge
                                     │                                                              │
(no-anchor components go straight to merge) ───────────────────────────────────────────────────────────────┤
                                                                                                           v
                                                              merge_all -> postprocess... -> OUT (null, display)
```

### Build result (read these before committing)
The `houdini_build_procedural_asset` result includes:
- `components_built`, `anchors_built` — what actually got built.
- `component_id_check` — `{missing: [...], ok: [...]}`. **Fix any `missing`
  before committing** (orientation checks will fail for missing ids).
- `structure_advisory` — should be `passed: true` (the builder's Copy-to-Points
  network is inherently modular, so the monolithic gate never trips).
- `orientation_check` — a PREVIEW of `verify_orientation` (advisory; the hard
  gate runs at commit). Apply any failed-check `hint` quaternion **in the
  component code** (fix the source, don't rotate post-hoc).
- `diagnostics` / `structural_checks` — point/prim counts, bounds.

### Commit (separate step)
```python
houdini_commit_sandbox(
    sandbox_root_path="<root_path from build result>",
    final_name="bicycle",
    orientation_checks=<recipe.orientation_asserts>,
)
```
The existing structure gate + orientation gate run on the built OUT
automatically — no gate changes were needed for the builder.

### Construction axis (B-station — PREFERRED over leaving orientation to PCA)

`orientation_asserts` gain an optional `construction_axis` field. Set it
whenever you can — it makes orientation a **deterministic** check instead of a
PCA estimate:

- `construction_axis`: the **local-space** axis the component is generated
  around. A wheel built as a ring in the XZ plane has `construction_axis:"Y"`
  (its axle / symmetry axis). A frame tube drawn along Z has
  `construction_axis:"Z"`.
- The builder derives the world axis by rotating `construction_axis` through
  the anchor's `@orient` quaternion — pure algebra, no point sampling, no PCA.
  It bakes that world axis onto each instance as the `edini_world_axis` prim
  attribute. `verify_orientation` reads it directly (`method:"construction"`).
- Without `construction_axis`, the check falls back to PCA on point positions
  (`method:"pca"`). PCA is an *estimate* and is noisy on uneven point
  distributions — prefer the deterministic path.

**The builder also catches self-consistent errors at build time.** If your
`construction_axis` + anchor `@orient` + `expected_axis` contradict each other
(e.g. you declare `construction_axis:"Y"` but the anchor orient rotates Y to
world Z while `expected_axis` says X), the build **refuses** before any cook,
telling you exactly which field to fix. This is the key value: a wrong mental
model can no longer produce a self-consistent-but-incorrect asset that PCA
would happily confirm.

Read the build result's `construction_axis_summary` to confirm which components
got deterministic axes (`method:"construction"`) and their derived world axes.

For a component with **no anchors** (direct-merge), the world frame is
identity, so `construction_axis` and `expected_axis` are usually the same
value.

## Asset-level parameters & linkage (A2-station)

By default each component's `code` is independent — a hardcoded
`wheelbase = 1.0` in the frame does nothing to the wheel anchors. To make a
**real parametric asset** (change one value, every dependent part updates),
use asset-level `params` + expression-driven anchors.

### Declaring shared params
Top-level `params` installs spare parms on the sandbox root. After commit
they live on the final asset, so the user tunes them in the Houdini
parameter panel and sees the whole asset update:
```jsonc
"params": {
  "wheelbase": {"default": 1.0, "min": 0.5, "max": 2.0},
  "wheel_r":   {"default": 0.35}
}
```

### Reading params in component code
A component is a child of the sandbox root, so reference a param via a
relative channel reference. List the params you read in `reads` so a typo is
caught at build (not silently returned as 0):
```python
node = hou.pwd(); geo = node.geometry()
wheelbase = hou.ch('../wheelbase')   # one level up = sandbox root
wheel_r   = hou.ch('../wheel_r')
...
```
```jsonc
{"id": "frame", "code": "...", "reads": ["wheelbase", "wheel_r"]}
```
Changing the parm re-cooks the component automatically (channel dependency).

### Linking anchor positions to params
Anchors accept `position_expr` / `orient_expr` / `pscale_expr` — expression
strings (or plain numbers) evaluated against the asset params **at build
time**. This is how the wheel follows the frame's wheelbase:
```jsonc
{"position_expr": ["wheelbase/2", "wheel_r", "0"], "component_id": "wheel_fl"}
```
- Expression grammar: parameter names, arithmetic (`+ - * / % **`), unary
  `-`, and a whitelist of `math` functions (`sin cos sqrt abs min max ...`)
  plus constants `pi`/`e`/`tau`. Anything else (imports, attributes, calls to
  non-whitelisted functions) is **rejected** — the engine is a security
  sandbox, not a Python `eval`.
- A bad expression (unknown param, syntax error, div-by-zero) fails the
  build with a precise error naming the anchor and the reason.
- `position` (static numbers) and `position_expr` are mutually exclusive;
  static is the backward-compatible default.

### Design note
Anchor positions are resolved at BUILD time (deterministic) and baked as
coordinates — they are assembly-time, not cook-time. Component *shapes*
driven by params (e.g. wheel radius) ARE cook-time dynamic via `hou.ch`.
This split is intentional: the layout is fixed by the recipe; the parts
themselves stay live.

## Parameter Exposure (in the sandbox — not after commit)

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

`houdini_run_python_sandbox` has two modes. Pick by whether your code needs
`createNode` on child SOPs:

- **Single-SOP mode (default):** the sandbox creates one `edini_generate`
  Python SOP; your code IS its cook body. Use `hou.pwd()` / `node.geometry()`.
  NEVER `createNode` here (infinite recursion — see Forbidden Patterns).
- **Network mode (`network_mode=true`):** your code runs in the sandbox geo
  container. Use it to BUILD a multi-node modular network. Each child Python
  SOP's own cook body is still single-SOP-style (only emits its own geo).

```python
# Inside single-SOP mode (or inside a child python SOP's cook in network mode)
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

For node network generation, ALWAYS use `network_mode=true` and create child
nodes under the injected `sandbox_root` container (see [Network Mode](#network-mode-for-modular-assets)):

```python
# network_mode=true — runs in the sandbox geo container
container = sandbox_root            # injected; == hou.node(sandbox_root_path)
box = container.createNode("box", "my_box")
box.parm("sizex").set(1)
box.parm("sizey").set(1)
box.parm("sizez").set(1)
out = container.createNode("null", "OUT")
out.setInput(0, box)
out.setDisplayFlag(True)   # OUT is auto-found, cooked, and diagnosed
```

### String Safety
When embedding string literals in Python code that will pass through JSON → parm.set():
- Avoid backtick characters
- Escape backslashes as `\\\\` (double-escape for JSON + Python)
- Use raw strings (`r"..."`) for paths
- For special characters in data (key labels, etc.), use unicode escapes

## Harness Rules

- Do not use raw `houdini_run_python` for initial procedural asset generation when `houdini_run_python_sandbox` is available.
- **Multi-component assets: prefer `houdini_build_procedural_asset` (declarative recipe).** It assembles the modular network deterministically — you only write per-component geometry code, never createNode/wiring. Fall back to `network_mode=true` only for topologies the recipe can't express.
- **Use `network_mode=true` for any multi-component asset** built via `houdini_run_python_sandbox`. Single-SOP mode (default) cannot `createNode` on child SOPs (infinite recursion). If your code needs more than one SOP, it MUST run in network mode — do NOT fall back to raw `houdini_run_python` to dodge the sandbox.
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
3. **Choose backend + mode** — `python_sop` for algorithmic mesh generation, `vex_wrangle` for per-element math, `hybrid` for both. Then choose the BUILD path: if the asset has ≥2 components or any repeated/swappable part, **use `houdini_build_procedural_asset` (declarative recipe)** — it assembles the modular network deterministically and you only write per-component geometry code. Fall back to `houdini_run_python_sandbox(network_mode=true)` only for non-standard topologies you can't express as a recipe. Single-SOP mode only for genuinely single-piece generators.
4. **Generate with sandbox/builder** — Use `houdini_build_procedural_asset` (preferred for multi-component) or `houdini_run_python_sandbox` with `commit_on_success=false`. The component code MUST: (a) call `geo.addAttrib(hou.attribType.Prim, "component_id", "")` before any geometry, then `poly.setAttribValue("component_id", "<id>")` on every component's polygons; (b) install spare parameters idempotently on the cooking node (or, in network mode / builder, on each generator SOP); (c) use Copy-to-Points (via builder anchors or manual network_mode) for any repeated/swappable part; (d) in builder mode, the network terminates in a builder-created OUT automatically; in network mode, terminate with a null named `OUT` (or pass `output_node_name`).
5. **Check `structure_advisory` IMMEDIATELY** — The sandbox result now includes a `structure_advisory` field. If it reports `is_monolithic: true`, you MUST `houdini_discard_sandbox` and rebuild with a modular decomposition (separate component generators + Copy-to-Points/Sweep). Do NOT proceed to verification on a monolithic asset — the commit gate will refuse it anyway, so fixing it now saves a wasted verify cycle.
6. **Trust sandbox diagnostics** — The result includes `diagnostics` and `structural_checks`. No need for separate inspect calls.
7. **Add structural detail** — Panel lines, seams, secondary components, varied cross-sections. Then finishing: Normal SOP, optional bevel on render-visible hard edges. Preserve `@component_id` tags.
8. **Run THREE-LAYER verification** (see below) — geometry health → orientation → data → visual. Do NOT skip layers; each catches defects the others can't. **Layer 1 (health check) is MANDATORY** — skipping it lets non-manifold edges / degenerate faces / orphan points flow into Boolean/Sweep and silently corrupt the result.
9. **Repair loop with TARGETED fixes** — Each repair round must address a SPECIFIC component_id or a SPECIFIC health-check finding. Never rebuild the whole asset without a named defect (see Debug Discipline below).
10. **Commit only when all layers pass** — `houdini_commit_sandbox` runs TWO hard gates: the modular-structure gate (refuses monolithic assets) then the orientation gate (refuses wrong axes) on the REAL output node. If either fails, commit is refused — fix in source and re-run. Don't bypass with `skip_orientation=true` or `skip_structure_check=true` unless you have a documented reason.

## Three-Layer Verification Protocol

**Why three layers, not two:** A recurring failure mode was relying on
screenshots alone. Vision models cannot reliably see small/thin components
(chains, spokes, bolts) at viewport resolution, so they report them as
"missing" even when they exist — and the agent wastes iterations rebuilding
with no real change. Geometry health checks and per-component inventory data
catch what screenshots cannot.

| Layer | Tool | What it catches | Authority | Cost |
|---|---|---|---|---|
| **1. Geometry health** | `houdini_inspect_geometry_health` | Orphan points, open/stray curves, degenerate faces, non-manifold edges, holes, coincident points | AUTHORITATIVE — must pass | cheap (no render) |
| **2a. Orientation** | `houdini_verify_orientation` | Wrong axle direction, flipped components, misaligned axes | AUTHORITATIVE — gate | cheap |
| **2b. Inventory data** | `houdini_geometry_inventory` / the `geometry_inventory` field returned by `capture_review` | Which component_ids exist, their prim counts + relative sizes | AUTHORITATIVE for "is it present?" | cheap |
| **3. Visual** | `houdini_capture_review` + `describe_image` (+ `houdini_capture_component_detail` for small parts) | Proportions, symmetry, intersection, construction logic | Advisory | expensive (render + vision) |

**Run layers in order.** Cheap authoritative layers first; only escalate to
vision when the cheap layers can't resolve a question.

### Mandatory Pre-Commit Sequence

```
0. CHECK structure_advisory (returned by run_python_sandbox) — if is_monolithic,
   discard and rebuild modular. Do this BEFORE any verification.

1. houdini_inspect_geometry_health on the OUT node — MANDATORY, not optional.
   - Fix orphan points (Fuse), stray open curves (Blast), degenerate faces
     (Clean), non-manifold edges before anything else. These silently break
     Boolean/Sweep/subdivision downstream.
   - NOTE: open_boundary_edges is EXPECTED for open surfaces (terrain, a
     single panel). Only treat it as a defect for assets that should be closed.

2. houdini_verify_orientation on the OUT node
   - Pass all checks from the recipe's ORIENTATION ASSERTS section
   - If any check fails, apply the hint quaternion to the SOURCE code and
     re-run the sandbox. Do NOT rotate post-hoc on geometry.

3. houdini_geometry_inventory on the OUT node (or read geometry_inventory
   from the capture_review result)
   - Confirm every expected component_id is present with prim_count > 0.
   - Note any component with size_fraction < 0.08 — it is present but SMALL.
     These will need a component close-up (step 5b) before vision can judge them.

4. houdini_capture_review (4-view: perspective/top/front/right) → describe_image
   - The capture now frames each view to the target's bounding box (no more
     clipped ortho views). It also returns a `geometry_inventory` text block.
   - Pass the PROCEDURAL_VERIFY_PROMPT to describe_image, AND include the
     inventory text in your message so the vision model cross-validates.
   - The vision model CANNOT assess orientation — ignore any orientation
     claims it makes. Only act on PROPORTIONS, SYMMETRY, INTERSECTION
     (perspective-confirmed only), STRUCTURAL_DETAIL.

5. IF vision flags a component as missing/unclear, OR the inventory marks it SMALL:
   5a. Check the inventory: if the component_id has prim_count > 0, it EXISTS
       — vision just couldn't see it. Do NOT rebuild it.
   5b. Run houdini_capture_component_detail on that component_id to get a
       close-up, then re-judge. This resolves the "exists but too small"
       ambiguity definitively. Use this tool, NOT a single-view capture_review.

6. Repair loop: fix the SPECIFIC defect → re-verify the SPECIFIC layer →
   repeat. Up to 3 rounds, then ask the user (see Debug Discipline).

7. houdini_commit_sandbox — runs the modular-structure gate then the
   orientation gate as final checks.
```

### Debug Discipline (anti-flail rules)

The single biggest waste in procedural generation is the **blind rebuild
loop**: vision reports a vague defect, the agent regenerates the whole asset
hoping it improves, the geometry is essentially unchanged, repeat 4×. These
rules prevent it:

1. **Name the defect before fixing.** State exactly which component_id or
   which health-check field you are fixing. "The chain is missing" is NOT a
   valid defect statement until you've confirmed via `geometry_inventory`
   that chain has prim_count == 0. If it has prim_count > 0, the defect is
   "chain is too small to see" → fix is a close-up capture, not a rebuild.
2. **One defect per round.** Fix one named thing, re-verify that one thing.
   Don't bundle 5 changes into one rebuild — you won't know which worked.
3. **Diff the inventory.** Before and after a repair, compare
   `geometry_inventory` output. If the component's prim_count/bounds didn't
   change, your edit didn't take effect — don't re-capture and hope.
4. **Escalate, don't loop.** If the same defect survives 2 targeted fixes,
   the approach is wrong — switch backend (VEX↔Python SOP), ask the user,
   or capture a component detail. Do NOT do a 3rd identical rebuild.
5. **Rebuild = last resort.** `houdini_discard_sandbox` + full regenerate is
   only justified when the health check shows fundamental topology breakage
   (non-manifold, many orphan points) OR orientation is structurally wrong
   across multiple components.

### The Verification Prompt (for describe_image)

Use the canonical `PROCEDURAL_VERIFY_PROMPT` (single source of truth in
`pi-visionizer/src/config.ts`). It instructs the vision model to:
- cross-reference a `GEOMETRY_INVENTORY` block you provide alongside the image,
- NOT report small components as "missing" if they appear in the inventory,
- emit a structured `VERDICT: accept | fix:<list> | closer_capture:<list> | uncertain`.

When you call `describe_image`, paste the `geometry_inventory` text (returned
by `capture_review`) into the same message so the vision model can
cross-validate. Note: vision CANNOT detect orientation — rely on
`houdini_verify_orientation` for that.

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
  Each view (including orthographic top/front/right) is framed to the
  target's bounding box via `setViewToBoundingBox`, so the COMPLETE model is
  always visible — no more clipped ortho views.
- The result includes a `geometry_inventory` text block listing every
  `component_id` with its prim count and relative size. **Paste this into
  your describe_image message** so the vision model can cross-validate
  presence/absence rather than guessing from pixels.
- Filepath is auto-routed to the session's screenshot folder; AI-supplied
  basenames are preserved with sequence numbering (`review_001.png`, etc.).
- If capture returns an error, do not retry or explore alternative capture methods.

**Use `houdini_capture_component_detail`** when a component is present (per
inventory) but too small to judge in the whole-asset capture:
```
houdini_capture_component_detail(
  filepath="chain_detail.png",
  node_path="/obj/asset_name/OUT",
  component_ids=["chain_top", "chainring", "pedal"],
  views=["perspective"]   # keep cells large; add "top" for a 2-view sheet
)
```
Each component is framed to its OWN bounding box and captured as a separate
cell — this is how you resolve the "exists but too small to see" ambiguity.

### New Verification Tools (cheat-sheet)

| Tool | When to use |
|---|---|
| `houdini_inspect_geometry_health` | After sandbox build, before orientation. Catches orphan points, stray open curves, degenerate faces, non-manifold edges, holes, coincident points. Returns `overall_ok` + per-check `fix` recommendations. |
| `houdini_geometry_inventory` | Confirm every expected `component_id` exists with prim_count > 0. Flag small components (size_fraction < 0.08) that need a close-up. |
| `houdini_capture_component_detail` | Close-up capture of specific component_ids when they're too small to see in the whole-asset 4-view. |

## Methodology — Houdini Procedural Modeling (researched)

Distilled from production practice (Horikawa, Entagma, Knipping, SideFX,
CGWiki). Encode these as defaults, not aspirations.

### Units & scale contract
- **1 Houdini unit = 1 meter.** Many SOP/sim defaults assume this. Always emit
  geometry at real-world meter scale. A bicycle wheel is ~0.35m radius, not 35.

### VEX constraints
- **VEX has NO recursion.** AI-generated recursive VEX functions always fail.
  Use iteration (`for`/`foreach` inside one wrangle), a SOP Solver for feedback
  loops, or ForEach subnetworks.
- **Always `normalize()` after `cross()`.** Cross-product magnitude = product
  of input lengths × sin(angle), which is not unit-length in general.

### Copy-to-Points attribute contract
- The target points must carry `@orient` (quaternion, preferred) OR `@N`+`@up`
  (fallback), plus `@pscale` (uniform) or `@scale` (vector), plus `@piece`/
  `@name` for variant selection.
- `@pscale = 1.0` = original source size (no scaling). To scale a component,
  set `@pscale = desired_size / source_geo_size`.
- **Copy Stamp was REMOVED in H19.5.** Never reference it. Use ForEach +
  Metadata node for per-piece variation (read iteration values from the
  Metadata node's detail attributes, not stale upstream values).

### Boolean hygiene
- **Clean before Boolean.** Non-manifold edges and degenerate faces on either
  input produce garbage output. Run `houdini_inspect_geometry_health` and fix
  before any Boolean/Sweep that cuts the body.
- **Subdivide AFTER Boolean produces artifacts.** If you need clean topology,
  VDB-remesh instead, or order PolyExtrude/Bevel before the boolean.

### Orientation VEX recipe (canonical)
```
tangent = normalize(next_P - P);           // along the spine/axis
side    = normalize(cross(tangent, up));   // perpendicular, in-plane
@N      = cross(side, tangent);            // true surface normal
p@orient = quaternion(maketransform(side, @N, tangent));
```

### Standard decomposition by asset type
| Asset | Decomposition |
|---|---|
| Vehicle | Profile curves + Sweep for frame tubes → mirror → Copy-to-Points wheels/handles → Boolean panel cutouts |
| Furniture | Spine + cross-section profiles → Sweep/Skin → Copy-to-Points legs/rungs |
| Architecture | Footprint curve → extrude → Copy-to-Points window/door kits via `@piece` → Boolean openings |
| Organic | L-system or SOP-solver growth → VDB smooth/remesh → attribute scatter for detail |

### Further reading (when stuck on a pattern)
- Junichiro Horikawa — *VEX for Algorithmic Design* (loop/conditional/trig patterns)
- Entagma — *SOP Solver in 5 min* (feedback loops)
- Steven Knipping — *Applied Houdini* (Boolean hard-surface)
- CGWiki (tokeru.com/cgwiki) — *Joy of Vex*, *Copy Stamp ramble* (attribute flow gotchas)
- SideFX — Procedural Modeling Learning Path

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

### Attrib Promote SOP (high-misguess node)
Older tutorials say `original`/`newname`. H21 uses these:
| Purpose | Parm name | Type / menu |
|---------|-----------|------|
| Source attrib name | `inname` | string (NOT `original`) |
| Output attrib name | `outname` | string |
| Source class | `inclass` | menu: `point`/`prim`/`vertex`/`detail` |
| Output class | `outclass` | menu: `point`/`prim`/`vertex`/`detail` |
| Promotion mode | `method` | menu: `min`/`max`/`sum`/`average`/`mode` |

### Blast SOP
| Purpose | Parm name | Type / menu |
|---------|-----------|------|
| Group to act on | `group` | string |
| Group type | `grouptype` | menu: `guess`/`prims`/`points`/`edges`/`breakpoints` (NOT a bool/int — use the menu word, e.g. `prims`) |
| Delete non-selected | `negate` | bool (1 = keep group, delete rest) |
| Delete entities | `dodelete`/`delpts` etc. | use defaults unless changing behaviour |

### ForEach (Begin/End) — prefer Sweep+Copy-to-Points when possible
The block_end owns the structural parms; the block_begin only reads them via
`blockpath`:
| Purpose | Parm name | Which node | Type / menu |
|---------|-----------|------------|------|
| Method | `method` | **block_end** (the begin reads it) | menu: `count`/`foreachpiece`/`forloopwithmetadata` |
| Iterations | `iterations` | block_end | int |
| Piece attribute | `pieceattrib` | block_end | string (e.g. `component_id`) |
| Block path | `blockpath` | **block_begin** | must point at the block_end node (auto-wired when created together; if "Invalid sop specified", it's unwired) |
| Class | `class` | block_end | menu (NOT block_begin) |

Gotcha: if you create block_begin and block_end separately, `blockpath` is empty
→ "Invalid sop specified". Either let Houdini create the pair (create the
`foreach` HDA, which wires them), or set `begin.parm("blockpath").set(end.path())`.
**For tube/frame generation, prefer Sweep 2.0 — no blockpath bookkeeping.**

### Sweep SOP (2.0 — preferred for tubes/frames)
| Purpose | Parm name | Type / menu |
|---------|-----------|------|
| Curve to sweep along (spine) | input 0 | — |
| Cross-section (profile) | input 1 | — |
| Surface shape | `surface` | menu: `raildim`/`ribbon`/`tube` (use `tube` for round tubes) |
| Scale along curve | `scale` | float |
| Roll | `roll` | float (degrees) |
| Output polygon | `outputpoly` | bool |

### Copy-to-Points (2.0)
| Purpose | Parm name | Type / menu |
|---------|-----------|------|
| Source group | `sourcegrp` | string |
| Target group (points) | `targetgrp` | string or attr expr `@component_id==wheel` |
| Pack geometry | `pack` | bool (1 = packed primitives) |
| Use @orient/@pscale/@N+@up | (automatic) | these point attrs drive transform, no parm needed |

### Merge SOP
No parms. Just `merge.setInput(0, a); merge.setInput(1, b); ...` (up to ~50 inputs).

### Normal SOP
> Parm names below may be version-specific — **verify with `houdini_node_parms("normal")`** before writing a recipe.
| Purpose | Parm name | Type / menu |
|---------|-----------|------|
| Cusp angle | `cuspangle` | float (degrees, 0-180) |
| Add normals to | `type` | menu: `typepoint`/`typevertex`/`typeprim`/`typedetail` |

### Boolean SOP (2.0)
| Purpose | Parm name | Type / menu |
|---------|-----------|------|
| Operation (subtract/union/intersect) | `subtract`/`union`/`intersect` | bool flags (set the one you want to 1) |

### Discovery (recommended: query the manifest)
Parm names drift across Houdini versions (e.g. Normal SOP's cusp-angle parm).
**Before writing `postprocess` params, call `houdini_node_parms("normal")`**
— it returns the authoritative parm list (names/types/menu tokens/defaults)
from a catalogue generated against the real Houdini install, and the harness
validates your `postprocess` parm names against it at build time (an unknown
name is a hard error before any node is created). This replaces guessing from
the tables above, which can go stale.

Fallback (sandbox probe) if the tool is unavailable:
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
