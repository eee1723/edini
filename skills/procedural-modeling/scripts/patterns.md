# Common Procedural Patterns

Use these proven patterns as building blocks. Don't reinvent from scratch.

## Cross-Section Skinning (vehicles, bottles, pipes with varying profiles)
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

## Radial Array (wheels, gears, fan blades, clock faces)
```python
import math
for i in range(count):
    angle = 2 * math.pi * i / count
    x = radius * math.cos(angle)
    z = radius * math.sin(angle)
    # Create component at (x, center_y, z) with orient pointing outward
```

## Profile Curve + Sweep (moldings, rims, tire treads)
```python
# Define 2D profile as a list of (x, y) points
profile = [(0, 0), (0.1, 0), (0.1, 0.05), (0.08, 0.08), ...]
# Create as NURBS or polygon curve, then use Sweep SOP along a path
```

## Panel Lines / Seams as Geometry (mechanical surfaces)
```python
# Method 1: Inset faces then extrude inward (creates grooves)
# Method 2: Create thin strip geometry along edges (separate group for material)
# Method 3: In VEX, select edges by angle threshold and create edge geometry
```
Panel lines are separate primitives in group `seam` — not color/attribute tricks.

## Boolean Subtraction for Cutouts (windows, vents, air intakes)
```python
# Create cutter geometry (box, cylinder) at the cut location
# Use Boolean SOP: input0=body, input1=cutter, operation=subtract
# Result: clean cutout with proper topology
```

## Group-Based Assembly (standard structure for any asset)
```python
# Every component gets a primitive group for material assignment
geo.addAttrib(hou.attribType.Prim, "material_zone", "")
# When creating each component's polygons:
for poly in component_polys:
    poly.setAttribValue("material_zone", "chrome_trim")
    geo.findGroup(hou.primType.Polygon, "chrome_trim")  # or createGroup
```

## Anchor Points for Copy-to-Points (standard pattern)
```python
# Output to a separate geometry stream or group
pt = geo.createPoint()
pt.setPosition(anchor_pos)
pt.setAttribValue("orient", quaternion_as_tuple)  # (x, y, z, w)
pt.setAttribValue("pscale", 1.0)  # 1.0 = original size of component
pt.setAttribValue("component_id", "wheel")
# Group the anchors: geo.createPointGroup("wheel_anchors").add(pt)
```

## Brick / Tile / Rivet Scatter (repeated micro-structure — DO NOT inline-loop)
For any surface covered by ≥10 copies of a small same-shaped piece (bricks,
roof tiles, shingles, rivets along a seam, balusters, chain links), build it as
**one template piece + scatter points + Copy-to-Points**. Never hand-stamp
these in a `for i in range(N):` loop (see the `component-building` Backend
red-line table).

The whole thing is a 3-node network built via `build_procedural_asset`
(one anchored component — the only multi-component build path. Do NOT use
raw `houdini_run_python_sandbox(network_mode=true)` for this: it does not
bake `edini_world_axis` and cannot pass the G3 commit gate):

```
brick_template (python: emit ONE brick, tag component_id="brick")
        ↑
brick_anchors (python: emit a point grid with @P, @orient, @pscale)
        ↓
copytopoints  →  postprocess(normal)  →  OUT
```

**Template** (one unit brick, modeled at unit scale so `@pscale` does the sizing):
```python
node = hou.pwd(); geo = node.geometry()
geo.addAttrib(hou.attribType.Prim, "component_id", "")
# one box ~1×0.5×1 (a brick); pscale on the anchor will size it for real
# emit a single box, tag every prim component_id="brick"
```

**Anchors** (a staggered brick-laying grid — the parametric part):
```python
node = hou.pwd(); geo = node.geometry()
rows = hou.ch("rows"); cols = hou.ch("cols")   # expose as spare parms
bw, bh, bd = hou.ch("brick_w"), hou.ch("brick_h"), hou.ch("brick_d")
for r in range(rows):
    # stagger every other row by half a brick (running-bond)
    x_off = (bw/2) if r % 2 else 0.0
    for c in range(cols):
        pt = geo.createPoint()
        pt.setPosition((c*bw + x_off, r*bh, 0))
        pt.setAttribValue("orient", (0, 0, 0, 1))     # identity
        pt.setAttribValue("pscale", 1.0)              # brick already unit-sized
```

Why this beats a loop: `rows`/`cols`/`brick_w` are spare parms — drag a slider
and the whole wall rebuilds. The template is one editable brick. The structure
gate sees a genuinely modular asset. And per-instance ids transfer automatically
(copytopoints created by the harness auto-presses `resettargetattribs`).

