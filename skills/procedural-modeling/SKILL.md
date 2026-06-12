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
| Procedural textures (Copernicus) | **Python -> node CRUD** | Copernicus is node-based |

## Thinking Strategy: Divide & Conquer

**Build small procedural components first, then combine.** Do not try to generate one monolithic script that does everything. Instead:

1. Decompose the goal into independent sub-components (e.g., base shape + scatter rule + orientation + variation)
2. Build and verify each component separately (one wrangle / one Python SOP per component)
3. Combine with merge/switch nodes or sequential wiring
4. Verify the combined result visually

This reduces VEX complexity per snippet (higher success rate) and makes debugging tractable.

## VEX Guidelines

**VEX generated from scratch fails 64% of the time.** Mitigate with:

1. **Set the run-over class FIRST** - Before writing any VEX logic, determine which class to use and set the `class` parameter on the Attribute Wrangle:
   - **Points**: per-point operations (position, velocity, custom attributes per particle) - most common
   - **Primitives**: per-face/polygon operations (face normals, primitive groups, per-face coloring)
   - **Vertices**: per-vertex operations (UV manipulation, vertex normals, per-corner attributes)
   - **Detail (Numbers)**: once-per-geometry operations (bounding box, total count, global setup)

   Not setting the correct class is the #1 cause of silent wrong results. Always explicitly state which class you chose and why.

2. **Short snippets** - One wrangle = one operation. 5 transforms -> 5 wrangles in sequence.
3. **Template patterns** - Adapt known building blocks rather than writing from zero:
   - Noise displacement: `@P += normalize(@N) * noise(@P * chf("freq")) * chf("amp")`
   - Density scatter: `if(rand(@ptnum) > chramp("density", fit01(@P.y, 0, 1))) removepoint(0, @ptnum)`
   - Orient along direction: `p@orient = quaternion(dihedral({0,1,0}, normalize(@vel)))`
4. **Validate** - After VEX, always `houdini_inspect_geo` to check point counts, attributes, bounds.
5. **Diagnose repeated failures before switching** - After repeated VEX failures, preserve the wrangle, call `houdini_collect_diagnostics` / `houdini_inspect_geo`, then switch to Python SOP only if diagnostics show VEX is unsuitable. Python SOP is often more reliable for complex logic, but diagnostics must justify the backend change.

## Python SOP Guidelines

Prefer creating a real Python SOP node over `houdini_run_python` so the result persists:

```python
# Via houdini_run_python_sandbox - creates a persistent Python SOP in a sandbox
geo_node = hou.node("/obj").createNode("geo", "procedural_result")
py = geo_node.createNode("python", "generate")
py.parm("python").set("node = hou.pwd()\ngeo = node.geometry()\n# generation code here")
```

Use Python SOP for: recursion (L-systems, trees), external data, complex loops, CSG, mesh operations.

## Harness Rules

- Do not use raw `houdini_run_python` for initial procedural asset generation when `houdini_run_python_sandbox` is available.
- Do not delete a failed procedural node before `houdini_collect_diagnostics`.
- Do not explore Qt widgets, main windows, viewport internals, or unsupported HOM APIs to capture images. Use `houdini_capture_viewport_safe` and report clean failure if capture is unavailable.
- If a generated Python SOP, VEX wrangle, or node-network attempt fails, diagnose that attempt first. Switching backend is allowed only after diagnostics identify why the current path is unsuitable.

## Workflow

1. **Create a recipe first** - State asset type, backend, parameters, and expected structural checks.
2. **Choose backend** - `python_sop` for algorithmic mesh generation, `vex_wrangle` for per-element math, `node_network` for native SOP composition.
3. **Use the harness first** - For procedural assets, use `houdini_run_python_sandbox` or future harness tools instead of raw `houdini_run_python`.
4. **Preserve failed nodes** - Do not delete a failed procedural node before calling `houdini_collect_diagnostics`.
5. **Diagnose before switching strategy** - For Python SOP cook errors, VEX wrangle failures, or node-network failures, inspect node errors, warnings, parameters, traceback or generated code, and geometry state before falling back to another backend.
6. **Verify structurally** - Use `houdini_verify_asset` and/or `houdini_inspect_geo` to check point counts, primitive counts, bounds, and expected components.
7. **Capture safely** - Use `houdini_capture_viewport_safe` for visual verification. Do not explore Qt widgets or unsupported viewport internals during normal modeling.
8. **Commit only after verification** - Use `houdini_commit_sandbox` only after structural checks pass. Use `houdini_discard_sandbox` only when the sandbox is no longer useful.

### Capture (Screenshots)

- **Only use `houdini_capture_viewport_safe`** — `houdini_capture_network` is unsupported in Houdini 21 (`NetworkEditor.grab` removed).
- If safe capture returns an error, do not retry or explore alternative capture methods. Trust geometry diagnostics instead.
- `describe_image` is a best-effort visual confirmation. If it returns ambiguous results ("faint", "ghostly"), rely on geometry stats (point/prim counts, bounds) as the authoritative verification.
- Visual verification via capture is supplementary; structural diagnostics are primary.

## Common VEX Pitfalls

- **Wrong run-over class** - point/prim/vertex/detail produces completely different results. Always set explicitly.
- `rand()` returns float; for vectors use `set(rand(s), rand(s+1), rand(s+2))`
- No `float3` - use `vector` with `set()`
- `foreach` syntax: `foreach (elem; array) { ... }`
- Matrix multiply order: `P * M` not `M * P` (column-major)

## Copernicus (Procedural Textures)

1. Create nodes via `houdini_run_python_sandbox` or future image-context harness tools in `/img` context when available
2. Prefer Copernicus nodes (`copernicus::noise/ramp/math/merge`) over legacy COP2
3. Import SOP data via `sopimport` COP node
4. Bake via `hou.node(...).parm("execute").pressButton()` on ROP
