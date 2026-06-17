---
name: procedural-modeling
description: Use at the START of any Houdini geometry-generation task, BEFORE writing code or placing nodes. Covers procedural modeling, programmatic generation, VEX scripting, Python SOP, algorithmic geometry, parametric design, 程序化建模, 程序化生成, scatter with rules, L-systems, fractals, or any task where code drives geometry creation. NOT for pure manual node assembly, LookDev/rendering setup, animation keyframing, or simulation (use dynamics skills instead).
license: MIT
---

# Procedural Modeling — Decision Router

**Code-first:** write and execute code (Python SOP or VEX) to produce procedural results, rather than manually stacking built-in primitive nodes. The goal is parametric controllability and procedural elegance, not node-graph complexity.

Detailed workflows, references, and templates are split across `references/` and `scripts/` — load them on demand with the `read` tool (paths resolve relative to this skill directory).

## Step 1 — Pick Backend

| Approach | When to Use |
|----------|-------------|
| **Python SOP** point/poly generation | Complex shapes, parametric profiles, anything with loops/arrays/recursion |
| **VEX** wrangle (per-element) | Noise displacement, orient randomization, attribute-driven scatter, deformation |
| **Node network** (built-in SOPs) | ONLY post-processing (PolyBevel, Subdivide, Normal) or when a built-in SOP directly solves a sub-problem with zero code (Boolean, Sweep on existing curve) |

Do NOT build shapes by stacking box + transform + merge when you could generate a profile curve in Python then Sweep/Skin, or deform a base grid in VEX.

## Step 2 — Three Iron Rules

These are said **once** here. Refer back to this section; do not re-derive.

**1. No `createNode` inside a Python SOP cook body.** A cook body that calls `hou.node(...).createNode(...)` re-enters cook evaluation → infinite recursion. The cook body may ONLY emit geometry via `node.geometry().createPoint()/createPolygon()/addAttrib()` on its OWN geometry. To BUILD a network, use `network_mode=true` (code runs in the container, not inside a cook). See [Network Mode](#step-3a--build-path) below.

**2. Query parameter names with `houdini_node_parms(type)` before setting any parm.** Parm names drift across Houdini versions (e.g. Normal SOP's cusp-angle parm is `cuspangle`, not `cangle`/`cusp`; Attrib Promote uses `inname`/`inclass`, not `original`). The build harness hard-validates `postprocess` parm names against the real install catalogue — a guessed name is a build-time error, not a silent miss. Quick-reference table: [references/parm-reference.md](references/parm-reference.md).

**3. Tag every distinct geometric part with a `@component_id` prim attribute.** Declare it BEFORE creating geometry (`geo.addAttrib(hou.attribType.Prim, "component_id", "")`), then `poly.setAttribValue("component_id", "<id>")` on every component's polygons. Without it, `houdini_verify_orientation` cannot run and `houdini_commit_sandbox` will refuse to commit.

## Step 3 — Modular Decomposition (structure gate)

Single-Python-SOP monoliths are NOT acceptable. If an asset has more than ~3 distinct components, or any repeated/swappable part, decompose into a Copy-to-Points / Instance structure.

```
Main structure → outputs anchor points (@component_id, @orient, @pscale)
                         ↓
              Copy-to-Points ← Sub-component geometry (separate stream)
```

`houdini_commit_sandbox` runs `_check_modular_structure` and REFUSES to commit an asset that has ≥3 distinct `component_id` values all originating from a single Python SOP with no modular assembly nodes. The bypass `skip_structure_check=true` is only for genuinely simple single-piece assets (one fractal, one parametric surface).

Code templates for modular wiring: [scripts/python-sop-template.py](scripts/python-sop-template.py) (single-SOP + network_mode blocks), [scripts/patterns.md](scripts/patterns.md) (7 reusable patterns).

### Step 3a — Build Path

| Situation | Build path |
|---|---|
| Multi-component asset (≥2 components or any repeated/swappable part) | **`houdini_build_procedural_asset`** (declarative recipe) — PREFERRED. Full schema + construction axis: [references/declarative-builder.md](references/declarative-builder.md). Asset-level params + linkage: [references/params-and-linkage.md](references/params-and-linkage.md). |
| Non-standard topology you can't express as a recipe | `houdini_run_python_sandbox(network_mode=true)` — hand-write the network in the container. |
| Genuinely single-piece generator (one fractal, one surface) | `houdini_run_python_sandbox` (default single-SOP mode). |

**Network mode:** `network_mode=true` lets the code run in the sandbox geo **container** so it can `createNode` child SOPs and wire them. `network_mode=false` (default): code is the cook body of ONE `edini_generate` Python SOP — cannot `createNode`. The harness finds your `OUT` node (or the largest `@component_id`-bearing node), cooks it, and runs the structure gate.

## Step 4 — Recipe First

Before writing ANY code, state the recipe (components, parameters, modular anchors, orientation asserts, verification criteria). Template: [scripts/recipe-template.md](scripts/recipe-template.md). Orientation asserts are MANDATORY — they flow into `houdini_verify_orientation`.

## Step 5 — Workflow

1. **Recipe** — components with `@component_id`, ORIENTATION ASSERTS, PARAMETERS, MODULAR ANCHORS, DETAIL PLAN, VERIFICATION. ([scripts/recipe-template.md](scripts/recipe-template.md))
2. **Look up parm names** — `houdini_node_parms(type)` for any SOP you'll set parms on. ([references/parm-reference.md](references/parm-reference.md))
3. **Choose backend + build path** — see Step 1 + Step 3a.
4. **Generate** — `houdini_build_procedural_asset` (preferred) or `houdini_run_python_sandbox(commit_on_success=false)`. Component code must (a) `addAttrib` before geometry, (b) tag `@component_id`, (c) install spare params idempotently ([references/params-and-linkage.md](references/params-and-linkage.md)), (d) use Copy-to-Points for any repeated/swappable part.
5. **Check `structure_advisory` immediately** — if `is_monolithic: true`, `houdini_discard_sandbox` and rebuild modular. Do NOT proceed to verification on a monolithic asset.
6. **Trust sandbox diagnostics** — the result includes `diagnostics` and `structural_checks`; no need for separate inspect calls.
7. **Add structural detail** — panel lines, seams, secondary components, varied cross-sections. Standards: [references/detail-standards.md](references/detail-standards.md). Then finishing: Normal SOP, optional bevel on render-visible hard edges. Preserve `@component_id`.
8. **Run THREE-LAYER verification** — geometry health → orientation → inventory → visual. Do NOT skip layers; each catches defects the others can't. Layer 1 (health) is mandatory — skipping it lets non-manifold edges / degenerate faces flow into Boolean/Sweep and silently corrupt the result. Full protocol: [references/verification-protocol.md](references/verification-protocol.md).
9. **Repair loop with TARGETED fixes** — each round addresses a SPECIFIC component_id or a SPECIFIC health-check finding. Never rebuild the whole asset without a named defect. Debug Discipline: [references/verification-protocol.md](references/verification-protocol.md).
10. **Commit only when all layers pass** — `houdini_commit_sandbox` runs the modular-structure gate then the orientation gate on the REAL output node. If either fails, commit is refused — fix in source and re-run. Don't bypass with `skip_orientation=true` / `skip_structure_check=true` unless you have a documented reason.

## Harness Rules

- Use `houdini_run_python_sandbox`, never raw `houdini_run_python`, for asset generation (raw bypasses the sandbox, structure gate, orientation gate, and health check; a failed cook leaves half-built nodes on the live scene).
- Do not delete a failed node before `houdini_collect_diagnostics`. Diagnose before switching strategy.
- Do not explore Qt widgets, main windows, viewport internals, or unsupported HOM APIs to capture images. Use `houdini_capture_review` and report clean failure if capture is unavailable.
- Use `houdini_verify_asset` for structural checks (point count, bounds, attribute presence) before visual verification.
- Use `houdini_discard_sandbox` to cleanly abort a failed attempt when diagnostics show the approach is fundamentally wrong.
- **NEVER use `commit_on_success=true` on first sandbox execution.** Always capture and verify visually before committing.
- For procedural textures, use Copernicus nodes (`copernicus::noise/ramp/math/merge`) over legacy COP2. See [references/methodology.md](references/methodology.md).

## Thinking Strategy: Divide & Conquer

Build small procedural components first, then combine. Do not try to generate one monolithic script:
1. Decompose the goal into independent sub-components (base shape + scatter rule + orientation + variation).
2. Build and verify each component separately (one wrangle / one Python SOP per component).
3. Combine with merge / Copy-to-Points / switch nodes.
4. Verify the combined result visually.

## Reference Index (load on demand)

| When you need… | Read this |
|---|---|
| Houdini 21 SOP parameter names | [references/parm-reference.md](references/parm-reference.md) |
| Full 3-layer verification protocol + Debug Discipline | [references/verification-protocol.md](references/verification-protocol.md) |
| Declarative Recipe Builder schema + construction axis | [references/declarative-builder.md](references/declarative-builder.md) |
| Asset-level params + linkage (A2-station) + spare-param install | [references/params-and-linkage.md](references/params-and-linkage.md) |
| Detail level rating + material group organization | [references/detail-standards.md](references/detail-standards.md) |
| Common pitfalls (pscale/orient semantics, attr order, string safety) | [references/pitfalls.md](references/pitfalls.md) |
| VEX guidelines, methodology, decomposition by asset type | [references/methodology.md](references/methodology.md) |
| RECIPE fill-in template | [scripts/recipe-template.md](scripts/recipe-template.md) |
| Python SOP generator skeleton (single-SOP + network_mode) | [scripts/python-sop-template.py](scripts/python-sop-template.py) |
| VEX wrangle skeleton | [scripts/vex-wrangle-template.vfl](scripts/vex-wrangle-template.vfl) |
| 7 reusable procedural patterns (skinning, radial, sweep, boolean…) | [scripts/patterns.md](scripts/patterns.md) |
