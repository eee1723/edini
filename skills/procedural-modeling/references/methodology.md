# Methodology — Houdini Procedural Modeling

Distilled from production practice (Horikawa, Entagma, Knipping, SideFX, CGWiki). Encode these as defaults, not aspirations.

## Units & scale contract
- **1 Houdini unit = 1 meter.** Many SOP/sim defaults assume this. Always emit geometry at real-world meter scale. A bicycle wheel is ~0.35m radius, not 35.

## Boolean hygiene
- **Clean before Boolean.** Non-manifold edges and degenerate faces on either input produce garbage output. Run `houdini_inspect_geometry_health` and fix before any Boolean/Sweep that cuts the body.
- **Subdivide AFTER Boolean produces artifacts.** If you need clean topology, VDB-remesh instead, or order PolyExtrude/Bevel before the boolean.

## Orientation VEX recipe (canonical)
```
tangent = normalize(next_P - P);           // along the spine/axis
side    = normalize(cross(tangent, up));   // perpendicular, in-plane
@N      = cross(side, tangent);            // true surface normal
p@orient = quaternion(maketransform(side, @N, tangent));
```

## Standard decomposition by asset type
| Asset | Decomposition |
|---|---|
| Vehicle | Profile curves + Sweep for frame tubes → mirror → Copy-to-Points wheels/handles → Boolean panel cutouts |
| Furniture | Spine + cross-section profiles → Sweep/Skin → Copy-to-Points legs/rungs |
| Architecture | Footprint curve → extrude → Copy-to-Points window/door kits via `@piece` → Boolean openings |
| Organic | L-system or SOP-solver growth → VDB smooth/remesh → attribute scatter for detail |

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

## Common VEX Pitfalls

- **Wrong run-over class** — produces completely different results. Always set explicitly.
- `rand()` returns float; for vectors use `set(rand(s), rand(s+1), rand(s+2))`
- No `float3` — use `vector` with `set()`
- `foreach` syntax: `foreach (elem; array) { ... }`
- Matrix multiply order: `P * M` not `M * P` (column-major)

## Further reading (when stuck on a pattern)
- Junichiro Horikawa — *VEX for Algorithmic Design* (loop/conditional/trig patterns)
- Entagma — *SOP Solver in 5 min* (feedback loops)
- Steven Knipping — *Applied Houdini* (Boolean hard-surface)
- CGWiki (tokeru.com/cgwiki) — *Joy of Vex*, *Copy Stamp ramble* (attribute flow gotchas)
- SideFX — Procedural Modeling Learning Path

## Copernicus (Procedural Textures)
1. Create nodes via `houdini_run_python_sandbox` or future image-context harness tools in `/img` context
2. Prefer Copernicus nodes (`copernicus::noise/ramp/math/merge`) over legacy COP2
3. Import SOP data via `sopimport` COP node
4. Bake via `hou.node(...).parm("execute").pressButton()` on ROP
