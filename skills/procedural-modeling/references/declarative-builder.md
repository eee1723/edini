# Declarative Recipe Builder

`houdini_build_procedural_asset` is the **preferred path** for any multi-component asset (vehicles, furniture, anything with swappable/repeated parts). You submit a JSON **recipe** and the harness **deterministically** assembles the modular network — you never write `createNode`/`setInput`/`blockpath`/wiring. This eliminates the whole class of imperative-Houdini-API errors that dominate failed procedural runs.

**When to use which build path:**

| Situation | Tool |
|---|---|
| Multi-component asset (body + wheels/handles/legs via Copy-to-Points) | **`houdini_build_procedural_asset`** (this section) — PREFERRED |
| Non-standard topology you can't express as a recipe | `houdini_run_python_sandbox(network_mode=true)` (hand-write the network) |
| Genuinely single-piece generator (one fractal, one surface) | `houdini_run_python_sandbox` (default single-SOP mode) |

## The recipe schema

```jsonc
{
  "asset_name": "bicycle",
  "units": "meters",
  "params": {                                    // see references/params-and-linkage.md
    "wheelbase": {"default": 1.0, "min": 0.5, "max": 2.0, "label": "Wheelbase"},
    "wheel_r":   {"default": 0.35, "label": "Wheel Radius"}
  },
  "components": [
    {
      "id": "frame",                              // -> component_id prim attr value
      "code": "<single-SOP python: emit geometry, tag component_id='frame'>",
      "reads": ["wheelbase", "wheel_r"],          // params this component reads (via hou.ch)
      "anchors": []                               // empty -> goes straight into merge
    },
    {
      "id": "wheel",                              // template id (unit-radius wheel)
      "code": "<emit a unit-radius wheel; tag prims component_id='wheel'>",
      "anchors": [                                // position_expr strings reference params -> linked
        {"position_expr": ["wheelbase/2", "wheel_r", "-0.55"], "orient": [0,0,0,1], "pscale": 1.0, "component_id": "wheel_fl"},
        {"position_expr": ["wheelbase/2", "wheel_r",  "0.55"], "orient": [0,0,0,1], "pscale": 1.0, "component_id": "wheel_fr"},
        {"position_expr": ["-wheelbase/2", "wheel_r", "-0.55"], "orient": [0,0,0,1], "pscale": 1.0, "component_id": "wheel_rl"},
        {"position_expr": ["-wheelbase/2", "wheel_r",  "0.55"], "orient": [0,0,0,1], "pscale": 1.0, "component_id": "wheel_rr"}
      ]                                            // (static "position": [x,y,z] numbers are also valid)
    }
  ],
  "postprocess": [                                // optional SOP Chain after merge.
                                                   // Order matters: fuse → clean → normal.
    // 1. fuse — merge coincident points. ADD THIS whenever the asset has adjacent
    //    boxes sharing a coplanar face (inset panels, lids, stacked bodies, mullions
    //    on glass). Without it, those coincident points produce phantom non-manifold
    //    edges that silently corrupt any downstream Boolean/Sweep/Subdivide.
    //    No params → use Fuse defaults (safest; the C-station validator enforces H21
    //    parm names, so only set {"dist": <m>} if you need a non-default tolerance).
    {"type": "fuse"},
    // 2. clean — remove non-manifold edges + degenerate faces left after fuse.
    //    No params → Clean defaults. (H21 parms if needed: fusepts, deldegengeo.)
    {"type": "clean"},
    // 3. normal — cusp normals for shading. parm NAMES are version-specific —
    //    verify with houdini_node_parms("normal").
    {"type": "normal", "params": {"cuspangle": 60}}
  ],
  // WHEN TO OMIT fuse+clean: a genuinely single-piece asset (one box, one parametric
  // surface, one fractal) with no adjacent coplanar geometry has no coincident points
  // and can use "postprocess": [{"type":"normal",...}] alone. But multi-box assets
  // (houses, vehicles, furniture) almost always need fuse+clean — add them by default.
  "orientation_asserts": [                        // flows to commit_sandbox's orientation gate
    {"component_id": "wheel_fl", "kind": "radial", "expected_axis": "X",
     "construction_axis": "Y"},                    // local axis the wheel is generated around
    {"component_id": "frame", "kind": "elongated", "expected_axis": "Z",
     "construction_axis": "Z"}
  ],
  "expected": {"min_points": 100}                 // optional, for verify_asset
}
```

## Component code rules
Each component's `code` is a **single Python SOP cook body**. It MUST:
1. Read its own geometry: `node = hou.pwd(); geo = node.geometry()`.
2. Declare the attribute **before** geometry: `geo.addAttrib(hou.attribType.Prim, "component_id", "")`.
3. Tag every prim: `poly.setAttribValue("component_id", "<id>")`.
4. **NEVER call `createNode`** — the builder owns the network. Only emit geometry on the cooking node. Violating this triggers infinite recursion (see SKILL.md Iron Rule 1).

The builder **post-checks** `component_id` presence on the cooked OUT and reports any missing ids in `component_id_check.missing`.

## Anchor semantics
- `position`: world-space `[x, y, z]` where the stamp lands.
- `orient`: quaternion `[x, y, z, w]` (NOT Euler). Identity = `[0,0,0,1]`.
- `pscale`: `1.0` = source geometry at original size. Model stamped components at **unit scale** and set `pscale` to real size (cleanest), or model at real scale and use `1.0`.
- `component_id` (per anchor): the **per-instance** id (e.g. `wheel_fl`). The builder overwrites each stamped instance's prim `component_id` with this, so `houdini_verify_orientation` can PCA each instance separately.

## What the builder assembles (deterministic — you don't write this)
```
<id>_python     (your code)        ─┐
<id>_anchors    (builder: points)  ─┤-> copy_<id> (copytopoints) -> <id>_idfix (overwrite component_id) -> merge
                                     │                                                              │
(no-anchor components go straight to merge) ───────────────────────────────────────────────────────────────┤
                                                                                                           v
                                                              merge_all -> postprocess... -> OUT (null, display)
```

## Build result (read these before committing)
The `houdini_build_procedural_asset` result includes:
- `components_built`, `anchors_built` — what actually got built.
- `component_id_check` — `{missing: [...], ok: [...]}`. **Fix any `missing` before committing** (orientation checks will fail for missing ids).
- `structure_advisory` — should be `passed: true` (the builder's Copy-to-Points network is inherently modular, so the monolithic gate never trips).
- `orientation_check` — a PREVIEW of `verify_orientation` (advisory; the hard gate runs at commit). Apply any failed-check `hint` quaternion **in the component code** (fix the source, don't rotate post-hoc).
- `diagnostics` / `structural_checks` — point/prim counts, bounds.

## Commit (separate step)
```python
houdini_commit_sandbox(
    sandbox_root_path="<root_path from build result>",
    final_name="bicycle",
    orientation_checks=<recipe.orientation_asserts>,
)
```
The existing structure gate + orientation gate run on the built OUT automatically — no gate changes were needed for the builder.

## Construction axis (PREFERRED over leaving orientation to PCA)

`orientation_asserts` gain an optional `construction_axis` field. Set it whenever you can — it makes orientation a **deterministic** check instead of a PCA estimate:

- `construction_axis`: the **local-space** axis the component is generated around. A wheel built as a ring in the XZ plane has `construction_axis:"Y"` (its axle / symmetry axis). A frame tube drawn along Z has `construction_axis:"Z"`.
- The builder derives the world axis by rotating `construction_axis` through the anchor's `@orient` quaternion — pure algebra, no point sampling, no PCA. It bakes that world axis onto each instance as the `edini_world_axis` prim attribute. `verify_orientation` reads it directly (`method:"construction"`).
- Without `construction_axis`, the check falls back to PCA on point positions (`method:"pca"`). PCA is an *estimate* and is noisy on uneven point distributions — prefer the deterministic path.

**The builder also catches self-consistent errors at build time.** If your `construction_axis` + anchor `@orient` + `expected_axis` contradict each other (e.g. you declare `construction_axis:"Y"` but the anchor orient rotates Y to world Z while `expected_axis` says X), the build **refuses** before any cook, telling you exactly which field to fix. This is the key value: a wrong mental model can no longer produce a self-consistent-but-incorrect asset that PCA would happily confirm.

Read the build result's `construction_axis_summary` to confirm which components got deterministic axes (`method:"construction"`) and their derived world axes.

For a component with **no anchors** (direct-merge), the world frame is identity, so `construction_axis` and `expected_axis` are usually the same value.

---

## Variant Scatter (变体散布)

`houdini_variant_scatter` builds an asset where **multiple variant geometries** are distributed onto scatter points. Use it when a repeated part has several interchangeable styles (3 window designs, 4 tree species, 2 door types) and you want the variation to be controllable + reproducible.

**The workflow (Houdini 21 verified architecture):**
```
variants (prim `variant` int tagged) → merge (UNPACKED)
                                          │   scatter_points (emit @P, get i@id) ──┤
                                          ↓
                                   attribfrompieces (pieceattrib=variant, seed)
                                          │   ← draws a `variant` onto each scatter
                                          │     point from the source piece library
                                          ↓
                                   copytopoints 2.0 (useidattrib=1, idattrib=variant)
                                          │   ← dispatches UNPACKED source prim `variant`
                                          │     against target point `variant` 1:1
                                          │   ← resettargetattribs button transfers i@id
                                          ↓
                                   idfix → OUT   (no unpack; source already expanded)
                                   component_id = {variant_id}_{id}
```

**Why this architecture (all from real-H21 testing):**
- **No Pack node.** Pack By Name HIDES the prim `variant` inside the PackedFragment, so Copy to Points' piece dispatch can't read it → dispatch collapses. Copy dispatches correctly on **unpacked** source geometry.
- **attribfrompieces owns variant assignment.** It draws a `variant` onto each scatter point from the source piece library and reliably covers ALL variants even at low point counts (the old weighted-random assignment could starve low-weight variants).
- **resettargetattribs button transfers `id`.** Real H21 has no Apply Attributes multiparm on a fresh Copy node; pressing the button auto-populates the transfer. You do NOT set this yourself.

**When to use variant scatter vs single-template Copy-to-Points:**
- `houdini_build_procedural_asset` + one anchored component = **one template** copied N times (all instances identical, like 6 identical windows).
- `houdini_variant_scatter` = **N variant templates**, each instance gets one drawn from the source library per `seed` (6 windows, some style-A, some style-B, …). This is what raises detail from "uniform repetition" to "lived-in variation".

### Tool call parameters

```jsonc
houdini_variant_scatter({
  "recipe": {                         // REQUIRED — the recipe object (schema below)
    "asset_name": "window_wall",      // optional; defaults to "variant_asset"
    "variants": [                     // REQUIRED — 2+ variant source geometries
      {"id": "win_a", "code": "<single-SOP cook body emitting window style A>"},
      {"id": "win_b", "code": "<emit window style B>"},
      {"id": "win_c", "code": "<emit window style C>"}
    ],
    "scatter": {                      // REQUIRED
      "source": "<python code: emit scatter points with @P, optional @orient/@pscale/@N>",
      "seed": 42,                     // REQUIRED integer — reproducible runs
      "weights": {"win_a": 0.6, "win_b": 0.3, "win_c": 0.1}  // OPTIONAL
    },
    "postprocess": [                  // OPTIONAL — same chain as build_procedural_asset
      {"type": "fuse"}, {"type": "clean"},
      {"type": "normal", "params": {"cuspangle": 60}}
    ],
    "orientation_asserts": [...]      // OPTIONAL — per-variant orientation checks
  },
  "sandbox_name": "window_wall",      // OPTIONAL; defaults to asset_name
  "delete_on_failure": false          // OPTIONAL; default false (preserve on error)
})
```

| Parameter | Required | Type | Notes |
|---|---|---|---|
| `recipe` | **yes** | object | The recipe (see schema). |
| `recipe.variants` | **yes** | list | 2+ objects, each `{id, code}`. `id` non-empty unique string; `code` non-empty string. |
| `recipe.scatter` | **yes** | object | `{source, seed, weights?}`. |
| `recipe.scatter.source` | **yes** | string | Python cook body emitting scatter points (`@P` required). |
| `recipe.scatter.seed` | **yes** | integer | Drives AFP's draw; reproducible across runs. |
| `recipe.scatter.weights` | no | object | `{variant_id: number}`; validated against known ids; echoed in result (AFP's own distribution is currently uniform — see Gotchas). |
| `recipe.asset_name` | no | string | Sandbox root name; default `"variant_asset"`. |
| `recipe.postprocess` | no | list | Same chain semantics as `build_procedural_asset`. |
| `recipe.orientation_asserts` | no | list | Per-component orientation asserts; evaluated after build. |
| `sandbox_name` | no | string | Overrides `asset_name` for the sandbox root. |
| `delete_on_failure` | no | bool | Default `false` — sandbox is preserved on error so you can diagnose. |

### Variant code rules
Each variant's `code` is a single-SOP cook body (same Iron Rules as a recipe component). It MUST:
1. Declare + tag `component_id` (the variant id, e.g. `win_a`) — used as the *prefix* for per-instance ids.
2. **NEVER call `createNode`** — the builder owns the network.

The builder wraps each variant's code to additionally tag every prim with an integer `variant` attribute (the variant's index) — you do NOT set this yourself.

### Scatter source rules
`scatter.source` is python code that emits the target points. It should set `@P` (required) and may set `@orient`/`@pscale`/`@N` (optional, carried through to instances). The builder wraps your code to additionally stamp each point with an integer `id` (its point number). **You do NOT assign `variant` here** — that is the job of the downstream `attribfrompieces` SOP.

### Per-instance component_id
Each instance gets `component_id = "{variant_id}_{id}"` (e.g. `win_a_0`, `win_b_3`). The `idfix` SOP reads the prim `variant` (which variant, tagged on the source) + the point `id` (which instance, transferred via `resettargetattribs`) to build a globally-unique id. Use these per-instance ids in `orientation_asserts` — but since you can't predict which variant lands on which point, assert on a representative instance or use `construction_axis` on the variant source geometry.

### Build result (read these before committing)
- `variants_built`, `n_variants`, `weights`, `seed`, `piece_attribute` (`"variant"`)
- `structure_advisory` — passes (the attribfrompieces/copytopoints chain is modular)
- `component_id_check` — confirms each variant prefix produced at least one instance
- `diagnostics` / `structural_checks` — point/prim counts, bounds
- `orientation_check` — preview (if asserts declared)

### Commit (separate step)
```python
houdini_commit_sandbox(
    sandbox_root_path="<root_path from build result>",
    final_name="window_wall",
    orientation_checks=<recipe.orientation_asserts>,
)
```

### Gotchas
- The `variant` piece attribute is **integer** (never float — Copy to Points silently drops points on a float piece attr).
- **`weights` are echoed but not yet wired into AFP's distribution** — AFP currently assigns variants uniformly across the source piece library. If you need true weighted distribution, set AFP's `weightattrib`/`weightmethod` manually after build, or contribute the wiring. The `seed` still controls reproducibility.
- Changing `seed` reshuffles which variant lands on which point — fully reproducible across runs with the same seed + same scatter topology.
- For pipeline stability across upstream topology changes, prefer anchoring scatter points to a persistent `id` attribute rather than relying on `@ptnum` order.
