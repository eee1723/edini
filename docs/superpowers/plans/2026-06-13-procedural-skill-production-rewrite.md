# Procedural Modeling Skill Production Rewrite

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite the procedural-modeling skill and its supporting prompt infrastructure so that procedural assets are generated with proper detail, exposed parameters, modular components, and verified through a mandatory structural repair loop.

**Architecture:** Four files change: (1) SKILL.md gets a complete rewrite with new sections for code-first priority, recipe templates, modular components, parameter exposure, detail standards, probe-first, and visual verification protocol; (2) pi-visionizer config exports a 3D-specific verification prompt; (3) edini-context injects an upgraded verification workflow with mandatory repair loops; (4) harness.ts tool guidelines enforce no-first-commit and structured verification.

**Tech Stack:** Markdown (skill), TypeScript (Pi extensions)

---

## File Structure

| Path | Action | Responsibility |
|------|--------|----------------|
| `skills/procedural-modeling/SKILL.md` | Rewrite | Core skill document — all procedural modeling rules |
| `pi-extensions/pi-visionizer/src/config.ts` | Modify | Add `PROCEDURAL_VERIFY_PROMPT` export |
| `pi-extensions/edini-context/index.ts` | Modify | Update Visual Verification Rules with repair loop |
| `pi-extensions/edini-tools/tools/harness.ts` | Modify | Update promptGuidelines for sandbox and capture tools |

---

## Task 1: Rewrite SKILL.md — Core Sections

**Files:**
- Rewrite: `skills/procedural-modeling/SKILL.md`

- [ ] **Step 1: Replace the entire SKILL.md with the production version**

Replace the full content of `skills/procedural-modeling/SKILL.md` with:

```markdown
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

A procedural asset is NOT complete when it has correct topology. It MUST also pass these detail checks:

### Mandatory post-processing (apply ALL that are relevant):
1. **Edge treatment** — PolyBevel (offset 0.01-0.05) on hard edges of mechanical objects
2. **Subdivision** — At least 1 pass on organic surfaces (set crease weights on sharp edges first)
3. **Normal computation** — Facet or Normal SOP with appropriate cusp angle (30-60°)
4. **Surface variation** — At least ONE of: VEX noise displacement, panel lines, seam geometry, texture-ready UVs

### Detail level rating (never commit level 1-2):
- Level 1: Raw primitives (box, cylinder) — NEVER ACCEPTABLE
- Level 2: Shaped primitives with correct proportions — STILL NOT ENOUGH
- Level 3: Refined shapes with bevels, proper normals, some surface detail — MINIMUM ACCEPTABLE
- Level 4: Production quality with micro-detail, variation, proper edge flow — TARGET

### Per-component detail checklist:
- [ ] No perfectly sharp 90° edges on visible surfaces
- [ ] Proper normal direction (no black faces from flipped normals)
- [ ] At least one surface variation technique applied
- [ ] Organic forms have subdivision + crease weights
- [ ] Mechanical forms have bevel + panel lines or seams

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

## Language Selection

| Task | Use | Why |
|------|-----|-----|
| Per-element math, noise, vector ops | **VEX** (Attribute Wrangle) | Parallel, fast, idiomatic |
| Recursion, external data, complex algorithms | **Python SOP** | Full Python, libraries, recursion |
| Node network generation | **hou Python API** | Only option |
| Procedural textures (Copernicus) | **Python -> node CRUD** | Copernicus is node-based |

## Thinking Strategy: Divide & Conquer

**Build small procedural components first, then combine.** Do not try to generate one monolithic script that does everything. Instead:

1. Decompose the goal into independent sub-components (e.g., base shape + scatter rule + orientation + variation)
2. Build and verify each component separately (one wrangle / one Python SOP per component)
3. Combine with merge/Copy-to-Points/switch nodes
4. Verify the combined result visually

## VEX Guidelines

**VEX generated from scratch fails 64% of the time.** Mitigate with:

1. **Set the run-over class FIRST** — Before writing any VEX logic, determine which class to use:
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
- Avoid backtick characters (`` ` ``)
- Escape backslashes as `\\\\` (double-escape for JSON + Python)
- Use raw strings (`r"..."`) for paths
- For special characters in data (key labels, etc.), use unicode escapes: ``` for backtick

## Harness Rules

- Do not use raw `houdini_run_python` for initial procedural asset generation when `houdini_run_python_sandbox` is available.
- Do not delete a failed procedural node before `houdini_collect_diagnostics`.
- Do not explore Qt widgets, main windows, viewport internals, or unsupported HOM APIs to capture images. Use `houdini_capture_review` and report clean failure if capture is unavailable.
- If a generated Python SOP, VEX wrangle, or node-network attempt fails, diagnose that attempt first. Switching backend is allowed only after diagnostics identify why the current path is unsuitable.
- **NEVER use `commit_on_success=true` on first sandbox execution.** Always capture and verify visually before committing.

## Workflow

1. **Create a recipe** — Use the Recipe Template format above. List all components, parameters, anchors, and verification criteria.
2. **Probe unknown nodes** — If the recipe uses node types you haven't probed this session, probe them first.
3. **Choose backend** — `python_sop` for algorithmic mesh generation, `vex_wrangle` for per-element math, `hybrid` for both.
4. **Generate with sandbox** — Use `houdini_run_python_sandbox` with `commit_on_success=false`.
5. **Trust sandbox diagnostics** — The result includes `diagnostics` and `structural_checks`. No need for separate inspect calls.
6. **Add post-processing** — Apply detail standards: bevel, subdivide, normal, noise as needed.
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
# Always use 4-view for procedural assets
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
| Purpose | Parm name | Type | Example |
|---------|-----------|------|---------|
| Origin X/Y/Z | `originx`, `originy`, `originz` | float | `line.parm("originx").set(0.0)` |
| Direction X/Y/Z | `dirx`, `diry`, `dirz` | float | `line.parm("dirx").set(1.0)` |
| Length | `dist` | float | `line.parm("dist").set(2.5)` |
| Num points | `points` | int | `line.parm("points").set(2)` |

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

### Discovery
If unsure about a node's parm names, create a throwaway probe:
```python
n = container.createNode("nodetype", "_probe")
for p in n.parms():
    print(f"{p.name()} = {p.eval()}")
n.destroy()
```
```

- [ ] **Step 2: Verify SKILL.md markdown is valid**

Check that code fences are balanced:

```powershell
$content = Get-Content "F:\zz\Edini\skills\procedural-modeling\SKILL.md" -Raw; ($content | Select-String '```' -AllMatches).Matches.Count
```

Expected: even number (balanced code fences)

- [ ] **Step 3: Commit**

```powershell
git add skills/procedural-modeling/SKILL.md
git commit -m "docs(skill): rewrite procedural-modeling for production quality

- Add Code-First Priority (prefer Python/VEX over node assembly)
- Add Recipe Template with components, params, anchors, verification
- Add Modular Components section (Copy-to-Points pattern)
- Add Parameter Exposure rules (spare parms + ch())
- Add Detail Standards (minimum level 3, mandatory post-processing)
- Add Probe-First Rule for unknown node types
- Add Visual Verification Protocol with 3D prompt and repair loop
- Add String Safety guidance for JSON pipeline"
```

---

## Task 2: Add 3D Verification Prompt to pi-visionizer

**Files:**
- Modify: `pi-extensions/pi-visionizer/src/config.ts:63`

- [ ] **Step 1: Add PROCEDURAL_VERIFY_PROMPT export after DEFAULT_PROMPT**

After line 63 (the closing of `DEFAULT_PROMPT`), add:

```typescript
export const PROCEDURAL_VERIFY_PROMPT = [
  "You are verifying a procedural 3D asset captured from Houdini viewport (multi-view contact sheet).",
  "",
  "CHECK EACH VIEW FOR THESE DEFECTS:",
  "",
  "1. ORIENTATION: Are all components oriented correctly?",
  "   - Wheels/discs should be VERTICAL (upright), not lying flat",
  "   - Roofs/tops should be on TOP, not on the side",
  "   - Handles/bars should be HORIZONTAL",
  "   - Flag any component that appears rotated 90° from expected",
  "",
  "2. PROPORTIONS: Do parts have reasonable proportions?",
  "   - Compare sub-component sizes to the whole",
  "   - Flag any part that is drastically too large or too small",
  "",
  "3. SYMMETRY: If the object should be symmetric, is it?",
  "   - Check left/right and front/back symmetry where expected",
  "   - Flag missing or extra parts on one side",
  "",
  "4. COMPLETENESS: Are all expected sub-components visible?",
  "   - If something is described as having N parts, can you count N?",
  "   - Flag components that are described but not visible",
  "",
  "5. INTERSECTION: Are parts overlapping when they should not?",
  "   - Bodies passing through other bodies",
  "   - Components embedded inside others",
  "",
  "6. SCALE: Are sub-parts at correct scale relative to the whole?",
  "",
  "7. DETAIL LEVEL: Rate the geometry refinement:",
  "   - 1 = Raw boxes/cylinders (unacceptable)",
  "   - 2 = Shaped primitives, correct proportions but no refinement",
  "   - 3 = Beveled edges, proper normals, some surface detail (minimum acceptable)",
  "   - 4 = Production quality with micro-detail and variation",
  "",
  "OUTPUT FORMAT (use exactly this structure):",
  "DEFECTS:",
  "- [critical/major/minor] description of defect",
  "- [critical/major/minor] description of defect",
  "DETAIL_LEVEL: N",
  "ORIENTATION_OK: yes/no (if no, describe what is wrong)",
  "MISSING_COMPONENTS: list or 'none'",
  "VERDICT: fix (list what) | accept",
].join("\n");
```

- [ ] **Step 2: Verify TypeScript syntax**

```powershell
node -e "const fs=require('fs'); const c=fs.readFileSync('pi-extensions/pi-visionizer/src/config.ts','utf8'); if(c.includes('PROCEDURAL_VERIFY_PROMPT')) console.log('OK: prompt exported'); else process.exit(1)"
```

Expected: `OK: prompt exported`

- [ ] **Step 3: Commit**

```powershell
git add pi-extensions/pi-visionizer/src/config.ts
git commit -m "feat(visionizer): add PROCEDURAL_VERIFY_PROMPT for 3D asset verification

Structured checklist for orientation, proportion, symmetry, completeness,
intersection, scale, and detail level. Used by describe_image during
procedural modeling verification loops."
```

---

## Task 3: Update edini-context Verification Flow

**Files:**
- Modify: `pi-extensions/edini-context/index.ts:105-134`

- [ ] **Step 1: Replace the Visual Verification Rules section**

Replace lines 105-133 (from `## Visual Verification Rules` to the closing backtick before the `// Inject iron rules` comment) with:

```typescript
## Visual Verification Rules

Before reporting completion, decide whether to capture:

**🔴 MUST capture & verify (houdini_capture_review + describe_image with 3D prompt):**
- Procedural asset generation (ANY geometry created via sandbox or code)
- User provided a reference image
- Creating effects: smoke, fire, water, pyro, particles, volume, fluid
- Changing shaders, materials, lighting, or cameras
- User says "match", "look like", or "adjust"

**🟡 SHOULD capture:**
- Modifying existing visible geometry
- 3+ parameter changes on the same node
- User asks "how does it look?"

**🟢 SKIP capture:**
- Read-only operations (get_*, search_*, list_*, check_errors)
- Layout-only (layout_nodes)
- Utility nodes (null, switch, merge, output)
- HDA management

**Procedural Asset Verification Workflow (MANDATORY for all procedural generation):**
1. Generate asset via houdini_run_python_sandbox (commit_on_success=false ALWAYS)
2. Apply post-processing (bevel, subdivide, normal) if not already included
3. houdini_capture_review with views=['perspective','top','front','right']
4. describe_image with CUSTOM PROMPT for 3D verification (check orientation, proportions, completeness, detail level)
5. IF critical/major defects found:
   a. Fix the SPECIFIC defect — do NOT regenerate from scratch
   b. Re-capture and re-describe
   c. Repeat up to 3 repair cycles
6. IF 3 repairs fail → report remaining defects to user and ask for direction
7. IF no critical/major defects AND detail_level >= 3 → commit

**The 3D verification prompt for describe_image:**
When verifying procedural assets, pass this prompt to describe_image:
"Verify this procedural 3D asset. Check: 1) ORIENTATION (wheels vertical, roof on top), 2) PROPORTIONS, 3) SYMMETRY, 4) COMPLETENESS (all components present?), 5) INTERSECTION, 6) SCALE, 7) DETAIL_LEVEL (1-4, must be >=3). Report: DEFECTS list, DETAIL_LEVEL, ORIENTATION_OK, MISSING_COMPONENTS, VERDICT (fix/accept)."

**Non-procedural verification workflow:**
1. Make the change
2. houdini_capture_review → save PNG
3. describe_image on the file → get description
4. Compare to expectations or reference
5. If mismatched → adjust parameters, repeat 2-4
6. Match confirmed → report completion
```

- [ ] **Step 2: Verify file is syntactically valid**

```powershell
node -e "const fs=require('fs'); fs.readFileSync('pi-extensions/edini-context/index.ts','utf8'); console.log('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```powershell
git add pi-extensions/edini-context/index.ts
git commit -m "feat(context): add mandatory repair loop for procedural asset verification

- Procedural generation now requires 4-view capture + 3D verification prompt
- Mandatory repair loop (up to 3 cycles) for critical/major defects
- Explicit prohibition on commit_on_success=true for first sandbox
- Separate workflow for procedural vs non-procedural verification"
```

---

## Task 4: Update harness.ts promptGuidelines

**Files:**
- Modify: `pi-extensions/edini-tools/tools/harness.ts:59-64` and `156-162`

- [ ] **Step 1: Update houdiniRunPythonSandbox guidelines**

Replace lines 59-64 (the `promptGuidelines` array for `houdiniRunPythonSandbox`) with:

```typescript
  promptGuidelines: [
    "ALWAYS use houdini_run_python_sandbox for initial procedural asset generation instead of raw houdini_run_python.",
    "The sandbox provides a Python SOP context — use hou.pwd() and node.geometry() directly in your code.",
    "The sandbox result includes diagnostics and structural_checks (has_geometry, point_count, bounds_nonzero) — no need for separate inspect_geo or check_errors calls.",
    "Do not delete a failed sandbox before reviewing the diagnostics in the result.",
    "NEVER set commit_on_success=true on the first sandbox execution. Always capture (4-view quad) and verify with describe_image using the 3D verification prompt BEFORE committing.",
    "If describe_image reports critical or major defects (wrong orientation, missing components, detail_level < 3), fix the specific issue and re-verify — do NOT commit until verification passes.",
    "Before using unfamiliar node types in your code, PROBE their parameter names first (create + inspect + destroy).",
  ],
```

- [ ] **Step 2: Update houdiniCaptureReview guidelines**

Replace lines 156-162 (the `promptGuidelines` array for `houdiniCaptureReview`) with:

```typescript
  promptGuidelines: [
    "Use houdini_capture_review after generating a procedural asset to verify it from multiple angles.",
    "For procedural assets: ALWAYS use views=['perspective','top','front','right'] for complete structural verification.",
    "For animated/growth assets: use frames=[1,10,20,30] to get a time contact sheet.",
    "Always pass target_path — it automatically isolates the target and frames each view.",
    "The output is a single concatenated PNG — call describe_image with the 3D verification prompt on it.",
    "After describe_image, if VERDICT is 'fix': repair the specific defect, re-capture, and re-verify (up to 3 cycles).",
    "Do NOT skip the describe_image step. Do NOT commit before visual verification passes.",
  ],
```

- [ ] **Step 3: Verify file is valid**

```powershell
node -e "const fs=require('fs'); const c=fs.readFileSync('pi-extensions/edini-tools/tools/harness.ts','utf8'); console.log('Lines:', c.split('\n').length); if(c.includes('NEVER set commit_on_success')) console.log('OK: sandbox guideline present'); if(c.includes('3D verification prompt')) console.log('OK: capture guideline present')"
```

Expected:
```
Lines: ~220
OK: sandbox guideline present
OK: capture guideline present
```

- [ ] **Step 4: Commit**

```powershell
git add pi-extensions/edini-tools/tools/harness.ts
git commit -m "feat(harness): enforce verification-before-commit and probe-first in tool guidelines

- Sandbox: prohibit commit_on_success=true on first run, require 3D verify prompt
- Capture: mandate 4-view quad + describe_image with 3D prompt for procedural assets
- Both: require repair loop (up to 3 cycles) before commit"
```

---

## Task 5: Final Verification

- [ ] **Step 1: Check all modified files are readable**

```powershell
$files = @(
  "skills/procedural-modeling/SKILL.md",
  "pi-extensions/pi-visionizer/src/config.ts",
  "pi-extensions/edini-context/index.ts",
  "pi-extensions/edini-tools/tools/harness.ts"
)
foreach ($f in $files) {
  if (Test-Path $f) { Write-Output "OK: $f" } else { Write-Output "MISSING: $f" }
}
```

Expected: all OK

- [ ] **Step 2: Verify SKILL.md has balanced code fences**

```powershell
$content = Get-Content "skills/procedural-modeling/SKILL.md" -Raw
$count = ([regex]::Matches($content, '```')).Count
if ($count % 2 -eq 0) { "OK: $count fences (balanced)" } else { "ERROR: $count fences (unbalanced)" }
```

Expected: `OK: N fences (balanced)`

- [ ] **Step 3: Verify key terms exist in each file**

```powershell
$checks = @{
  "skills/procedural-modeling/SKILL.md" = @("Code-First Priority", "Recipe Template", "Modular Components", "Parameter Exposure", "Detail Standards", "Probe-First", "Visual Verification Protocol", "Copy-to-Points")
  "pi-extensions/pi-visionizer/src/config.ts" = @("PROCEDURAL_VERIFY_PROMPT", "ORIENTATION", "DETAIL_LEVEL")
  "pi-extensions/edini-context/index.ts" = @("Procedural Asset Verification Workflow", "commit_on_success=false", "repair cycles")
  "pi-extensions/edini-tools/tools/harness.ts" = @("NEVER set commit_on_success=true", "3D verification prompt", "PROBE their parameter names")
}
foreach ($file in $checks.Keys) {
  $content = Get-Content $file -Raw
  foreach ($term in $checks[$file]) {
    if ($content -match [regex]::Escape($term)) { Write-Output "  OK: '$term'" } else { Write-Output "  MISSING: '$term' in $file" }
  }
}
```

Expected: all OK

- [ ] **Step 4: Run existing tests to confirm no regressions**

```powershell
python -m pytest tests/test_pi_harness_tools.py tests/test_capture_tools.py -q
```

Expected: existing tests pass (these check file content patterns)

- [ ] **Step 5: Final commit if any fixes were needed**

Only if Steps 2-4 revealed issues that required fixes.

---

## Verification Checklist (Post-Implementation)

- [ ] `skills/procedural-modeling/SKILL.md` contains all 8 new sections
- [ ] `SKILL.md` code fences are balanced (even count)
- [ ] `pi-visionizer/src/config.ts` exports `PROCEDURAL_VERIFY_PROMPT`
- [ ] `edini-context/index.ts` has "Procedural Asset Verification Workflow" with 3 repair cycles
- [ ] `harness.ts` sandbox guidelines prohibit `commit_on_success=true` on first run
- [ ] `harness.ts` capture guidelines require 3D verification prompt
- [ ] Existing tests pass without regression
