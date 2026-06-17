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
  "postprocess": [                                // optional SOP Chain after merge
    {"type": "normal", "params": {"cuspangle": 60}} // parm NAMES are version-specific —
                                                   // verify with houdini_node_parms("normal")
  ],
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
