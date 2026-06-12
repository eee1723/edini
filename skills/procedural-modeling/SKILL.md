---
name: procedural-modeling
description: Use when the user mentions procedural modeling, programmatic generation, VEX scripting, Python SOP, algorithmic geometry, parametric design, 程序化建模, 程序化生成, or wants to create geometry/effects through code rather than manual node placement. Also use when the user asks to generate patterns, fractals, L-systems, scatter with rules, or any task where code drives geometry creation.
---

# Procedural Modeling in Houdini

**Code-first approach:** When the user wants procedural results, write and execute code (Python SOP or VEX) rather than manually creating dozens of nodes.

## Language Selection

| Task | Use | Why |
|------|-----|-----|
| Per-element math, noise, vector ops | **VEX** (Attribute Wrangle) | Parallel, fast, idiomatic |
| Recursion, external data, complex algorithms | **Python SOP** | Full Python, libraries, recursion |
| Node network generation | **hou Python API** | Only option |
| Procedural textures (Copernicus) | **Python → node CRUD** | Copernicus is node-based |

## Thinking Strategy: Divide & Conquer

**Build small procedural components first, then combine.** Do not try to generate one monolithic script that does everything. Instead:

1. Decompose the goal into independent sub-components (e.g., base shape + scatter rule + orientation + variation)
2. Build and verify each component separately (one wrangle / one Python SOP per component)
3. Combine with merge/switch nodes or sequential wiring
4. Verify the combined result visually

This reduces VEX complexity per snippet (higher success rate) and makes debugging tractable.

## VEX Guidelines

**VEX generated from scratch fails 64% of the time.** Mitigate with:

1. **Set the run-over class FIRST** — Before writing any VEX logic, determine which class to use and set the `class` parameter on the Attribute Wrangle:
   - **Points**: per-point operations (position, velocity, custom attributes per particle) — most common
   - **Primitives**: per-face/polygon operations (face normals, primitive groups, per-face coloring)
   - **Vertices**: per-vertex operations (UV manipulation, vertex normals, per-corner attributes)
   - **Detail (Numbers)**: once-per-geometry operations (bounding box, total count, global setup)

   Not setting the correct class is the #1 cause of silent wrong results. Always explicitly state which class you chose and why.

2. **Short snippets** — One wrangle = one operation. 5 transforms → 5 wrangles in sequence.
3. **Template patterns** — Adapt known building blocks rather than writing from zero:
   - Noise displacement: `@P += normalize(@N) * noise(@P * chf("freq")) * chf("amp")`
   - Density scatter: `if(rand(@ptnum) > chramp("density", fit01(@P.y, 0, 1))) removepoint(0, @ptnum)`
   - Orient along direction: `p@orient = quaternion(dihedral({0,1,0}, normalize(@vel)))`
4. **Validate** — After VEX, always `houdini_inspect_geo` to check point counts, attributes, bounds.
5. **Fail twice → switch to Python SOP** — Python is far more reliable for complex logic.

## Python SOP Guidelines

Prefer creating a real Python SOP node over `houdini_run_python` so the result persists:

```python
# Via houdini_run_python — creates a persistent Python SOP
geo_node = hou.node("/obj").createNode("geo", "procedural_result")
py = geo_node.createNode("python", "generate")
py.parm("python").set("node = hou.pwd()\ngeo = node.geometry()\n# generation code here")
```

Use Python SOP for: recursion (L-systems, trees), external data, complex loops, CSG, mesh operations.

## Workflow

1. **Understand intent** — What shape/pattern/effect? What parameters should be adjustable?
2. **Choose approach** — VEX (per-element) / Python SOP (algorithmic) / node network (standard ops)
3. **Build incrementally** — One component at a time, `houdini_inspect_geo` after each step
4. **Visual verify** — `houdini_capture_viewport` + `describe_image` for visual results
5. **Parameterize** — Use `ch()`/`chramp()`/`chv()` in VEX, spare parameters in Python SOP

## Common VEX Pitfalls

- **Wrong run-over class** — point/prim/vertex/detail produces completely different results. Always set explicitly.
- `rand()` returns float; for vectors use `set(rand(s), rand(s+1), rand(s+2))`
- No `float3` — use `vector` with `set()`
- `foreach` syntax: `foreach (elem; array) { ... }`
- Matrix multiply order: `P * M` not `M * P` (column-major)

## Copernicus (Procedural Textures)

1. Create nodes via `houdini_run_python` in `/img` context
2. Prefer Copernicus nodes (`copernicus::noise/ramp/math/merge`) over legacy COP2
3. Import SOP data via `sopimport` COP node
4. Bake via `hou.node(...).parm("execute").pressButton()` on ROP
