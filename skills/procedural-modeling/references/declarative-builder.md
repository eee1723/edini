# Declarative Recipe Builder

`build_procedural_asset` is the **only build path** for any multi-component asset (vehicles, furniture, anything with swappable/repeated parts). You submit a JSON **recipe** and the harness **deterministically** assembles the modular network — you never write `createNode`/`setInput`/`blockpath`/wiring. This eliminates the whole class of imperative-Houdini-API errors that dominate failed procedural runs.

**When to use which build path:**

| Situation | Tool |
|---|---|
| Multi-component asset (body + wheels/handles/legs via Copy-to-Points) | **`build_procedural_asset`** (this section) — the only path |
| Genuinely single-piece generator (one fractal, one surface) | `houdini_run_python_sandbox` (default single-SOP mode) |
| Non-standard topology you can't express as a recipe | `houdini_run_python_sandbox(network_mode=true)` — **last resort only**, must document why the recipe cannot express it. Raw network_mode does NOT bake `edini_world_axis`, so it **cannot pass the G3 commit gate** if the geometry carries `@component_id` prims. |

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
    //    verify with query_parms("normal").
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

## Backend: `vex_skeleton` (tube / pipe / bar geometry)

For tube/pipe/path geometry, use `backend: "vex_skeleton"` instead of Python.
The VEX code emits **skeletons only** (polylines, never closed polygons).
The `form_node` closes the geometry via PolyExtrude or Sweep.

### Single-wrangle mode (profile → PolyExtrude)

Create a closed face profile in VEX. The form_node extrudes it.
The `dist` parm supports **channel expressions** for parametric length:

```jsonc
{
  "id": "pillar",
  "backend": "vex_skeleton",
  "code": "float r = ch(\"radius\")/2.0; int sides=16; int pts[];\nfor(int i=0;i<sides;i++){float a=2.0*M_PI*float(i)/float(sides);int pt=addpoint(0,set(r*cos(a),r*sin(a),0));push(pts,pt);}\nint prim=addprim(0,\"poly\");for(int i=0;i<len(pts);i++)addvertex(0,prim,pts[i]);",
  "form_node": {
    "type": "polyextrude::2.0",
    "params": {"dist": "ch('../length')", "outputback": 1, "divs": 2}
  },
  "reads": ["radius", "length"]
}
```

**IMPORTANT:** Use `addprim(0, "poly")` to create a polygon FACE, not `"polyline"`.
PolyExtrude extrudes faces, not curves. The `ch('../param')` expression in
form_node params reads from the sandbox root (one level up).

### Dual-wrangle mode (path + section → Sweep) — PREFERRED for tubes

For tubes between two 3D points, use the dual-wrangle Sweep pattern.
Add a `section_code` field containing VEX for the cross-section profile.
The `code` field defines the backbone path. The form_node is `sweep::2.0`:

```jsonc
{
  "id": "frame_tube",
  "backend": "vex_skeleton",
  "code": "float x1=ch(\"end_x\");float y1=ch(\"end_y\");int p0=addpoint(0,set(0,0,0));int p1=addpoint(0,set(x1,y1,0));int prim=addprim(0,\"polyline\");addvertex(0,prim,p0);addvertex(0,prim,p1);",
  "section_code": "float r=ch(\"tube_od\")/2.0;int n=16;int pts[];for(int i=0;i<n;i++){float a=2.0*M_PI*float(i)/float(n);int pt=addpoint(0,set(r*cos(a),0,r*sin(a)));push(pts,pt);}int pr=addprim(0,\"polyline\");for(int i=0;i<len(pts);i++)addvertex(0,pr,pts[i]);addvertex(0,pr,pts[0]);",
  "form_node": {"type": "sweep::2.0", "params": {"surfacetype": 2, "endcaptype": 1}},
  "reads": ["end_x", "end_y", "tube_od"]
}
```

- `code` = path wrangle (Detail mode): creates a polyline from start to end.
  Use `ch("param")` to read spared parms (auto-installed from `reads`).
- `section_code` = cross-section wrangle: creates a closed polyline in the
  XZ plane. Sweep automatically rotates it perpendicular to the path.
- `form_node.type` = `"sweep::2.0"` with `surfacetype=2` (tube) and
  `endcaptype=1` (cap both ends) for a perfectly closed pipe.
- **NEVER set `surfaceshape`** when using `section_code`. The builder forces
  `surfaceshape=0` (default) — any other value (1=roundtube, 2=extrude)
  makes Sweep ignore the second-input cross-section and generate its own
  shape, defeating the dual-wrangle pattern. If you set it, the builder
  warns and overrides it.
- **Cross-section coordinate convention (MANDATORY):** draw the section in
  the **XZ plane**. The section's **Z axis aligns to the path's normal (N)
  direction**, and its **Y axis aligns to the path's up direction**. Drawn
  in the wrong plane, Sweep produces a flat/deformed tube instead of a
  closed pipe. A circular tube cross-section is `set(r*cos(a), 0, r*sin(a))`
  (Y=0, X and Z vary) — NOT `set(r*cos(a), r*sin(a), 0)`.
- For twin tubes (chain stays, seat stays), create TWO polylines in `code`.

This pattern produces **perfect closed tube geometry** with correct normals —
no vertex winding errors, no open boundaries. It is the preferred method for
ALL tube/pipe/frame components.

## Backend: `python` (LAST RESORT)

The `python` backend emits geometry from a single Python SOP cook body. It is
the **last-resort backend** — use it ONLY for geometry no SOP can express
(NURBS / subdivision surfaces, complex organic curves). Simple geometry
(cylinders, boxes, torus, tubes, frames) MUST use `native_chain` or
`vex_skeleton`.

A python component MUST declare a `justification` string explaining why no
SOP can express the geometry, or the builder emits a validation warning:

```jsonc
{
  "id": "saddle",
  "backend": "python",
  "justification": "Organic NURBS saddle surface, no SOP equivalent",
  "code": "<single-SOP python cook body emitting the saddle geometry>",
  "reads": ["saddle_width"]
}
```

The python SOP reads asset params via `hou.ch("../param")` — the builder
installs `reads` as spare parms (same as `vex_skeleton`), so the two backends
behave consistently.

## Backend: `native_chain` (simple shapes)

For cylinders, boxes, hubs, pedals — combine native Houdini SOPs:

```jsonc
{
  "id": "hub",
  "backend": "native_chain",
  "nodes": [
    {"type": "tube", "params": {"rad": [0.025, 0.025], "height": 0.06, "rows": 3, "cols": 16, "type": 1}},
    {"type": "fuse", "params": {"dist": 0.0001}},
    {"type": "attribwrangle", "params": {"class": 1, "snippet": "s@component_id = \"hub\";"}}
  ]
}
```

- `nodes` is an ordered chain of SOPs, wired input-0 to previous.
- The last node's output enters the merge or CTP chain.
- `attribwrangle` with `s@component_id` tags all prims.

## Derived Parameters (computed once, shared globally)

Params can be `"kind": "derived"` — their value is computed from an expression
referencing primary (or earlier derived) params. The expression is evaluated ONCE
at build time and installed as a spare parm, so ALL components read the same
pre-computed value via `hou.ch("../derived_name")`:

```jsonc
"params": {
  "wheel_r":      {"default": 0.35, "kind": "primary"},
  "bb_drop":      {"default": 0.07, "kind": "primary"},
  "bb_height":    {"kind": "derived", "from": "wheel_r - bb_drop"},
  "seat_top_x":   {"kind": "derived", "from": "0.52 * cos(radians(st_angle))"}
}
```

- Primary params need `default` (and optionally `min`/`max` for sliders).
- Derived params need `from` (a safe expression referencing other params).
- The expression engine supports: arithmetic `+ - * / % **`, `sin cos tan sqrt abs min max atan2 radians degrees`, constants `pi e tau`.
- Dependency graph is validated: cycles are rejected, orphans are warned.
- ALL components read derived params via `hou.ch("../param")` — one
  computation, N consumers, zero redundancy.

## `rebuild_component` tool — incremental single-component rebuild

When only ONE component needs to change (a code tweak, a geometry fix), you
don't have to discard the sandbox and rebuild everything. `rebuild_component`
rebuilds just that component's subnet in an existing sandbox, leaving the
others and their cook state intact:

```python
from edini.harness import rebuild_component
rebuild_component(
    sandbox_root_path="/obj/edini_sandbox_..._bicycle_...",  # from build result
    component_id="wheel_rim",                                 # which to rebuild
    component_spec={                                          # full new spec
        "id": "wheel_rim",
        "backend": "vex_skeleton",
        "code": "<new path VEX>",
        "section_code": "<new section VEX>",
        "form_node": {"type": "sweep::2.0", "params": {"surfacetype": 2, "endcaptype": 1}},
        "anchors": [...],
    },
)
```

- The recipe is NOT stored on the sandbox — you pass the new component spec
  explicitly (`component_spec.id` must equal `component_id`).
- Works for direct-merge components (no anchors) and stamped components
  (with anchors) — the stamping layer (`{cid}_anchors` → `copy_{cid}` →
  `{cid}_idfix`) is rebuilt too, preserving per-instance component_ids.
- On failure the sandbox is left in the destroyed state (no rollback) so you
  can diagnose; fix the spec and rebuild again.

Use this INSTEAD of `discard_sandbox` + `build_procedural_asset` when the rest
of the sandbox is fine and only one component changed.

## `add_parm` tool — quick parameter creation

```python
from edini.harness import add_parm
add_parm("/obj/my_asset", "crank_len", default=0.17, min=0.15, max=0.20, label="Crank Length")
# => {"success": True, "channel_path": "/obj/my_asset/crank_len", "value": 0.17}
```

- Creates a spare float parameter on the target node.
- Returns the channel path for immediate use in `hou.ch()`.

## Anchor semantics
- `position`: world-space `[x, y, z]` where the stamp lands.
- `orient`: quaternion `[x, y, z, w]` (NOT Euler). Identity = `[0,0,0,1]`.
- `pscale`: `1.0` = source geometry at original size. Model stamped components at **unit scale** and set `pscale` to real size (cleanest), or model at real scale and use `1.0`.
- `component_id` (per anchor): the **per-instance** id (e.g. `wheel_fl`). The builder overwrites each stamped instance's prim `component_id` with this, so `verify_orientation` can check each instance separately (using its baked `edini_world_axis`).

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
The `build_procedural_asset` result includes:
- `components_built`, `anchors_built` — what actually got built.
- `component_id_check` — `{missing: [...], ok: [...]}`. **Fix any `missing` before committing** (orientation checks will fail for missing ids).
- `structure_advisory` — should be `passed: true` (the builder's Copy-to-Points network is inherently modular, so the monolithic gate never trips).
- `orientation_check` — a PREVIEW of `verify_orientation` (advisory; the hard gate runs at commit). Apply any failed-check `hint` quaternion **in the component code** (fix the source, don't rotate post-hoc).
- `construction_axis_summary` — the deterministic world axis baked on every component (Stage 3: ALL components get an axis, not just those with asserts). Review this to confirm the axis matches how the geometry is generated.
- `defaulted_axes` — components whose axis came from backend inference or the Y fallback (no explicit declaration). **Review these**: if the inferred axis is wrong, declare `construction_axis` explicitly.
- `diagnostics` / `structural_checks` — point/prim counts, bounds.

**G2 bake gate (runs inside build):** after the OUT cook, the builder verifies every prim carries a non-zero `edini_world_axis`. A backend that forgot to wire the bake fails the build with `G2_NOT_BAKED` — you should never see this on a normal recipe; it signals a builder bug.

## Commit (separate step)
```python
commit_sandbox(
    sandbox_root_path="<root_path from build result>",
    final_name="bicycle",
    orientation_checks=<recipe.orientation_asserts>,
)
```
The commit gate (G3) runs three defense-in-depth layers on the built OUT:
- **G3a bake** — every `@component_id` prim must carry a non-zero `edini_world_axis` (refuses raw `network_mode` builds that bypass the builder).
- **G3b orientation** — `verify_orientation` on the asserts.
- **G3c health** — `inspect_geometry_health` BLOCKING checks (orphan_points, open_curves) must pass.

On success, commit returns a **`verification_receipt`** — a tamper-evident JSON object. Your completion report must reference its fields (passed, orientation.failed, health.hard_errors_count) rather than re-counting geometry.

## Construction axis (MANDATORY on every orientation_assert — A8)

`orientation_asserts` carry a **required** `construction_axis` field. The PCA estimation path was **removed** (it misclassified elongated cylinders — the hub 90° bug), so the axis must be **declared, not estimated**:

- `construction_axis`: the **local-space** axis the component is generated around. A wheel built as a ring in the XZ plane has `construction_axis:"Y"` (its axle / symmetry axis). A frame tube drawn along Z has `construction_axis:"Z"`.
- The builder derives the world axis by rotating `construction_axis` through the anchor's `@orient` quaternion — pure algebra, no point sampling, no PCA. It bakes that world axis onto each instance as the `edini_world_axis` prim attribute. `verify_orientation` reads it directly (`method:"construction"`).
- **Omitting `construction_axis` on a non-empty assert is an A8 BLOCKING error** (`A8_MISSING_CONSTRUCTION_AXIS`). There is no fallback. To skip orientation verification entirely, pass an **empty** `orientation_asserts` array (explicit opt-out).

**Every component gets an axis baked (Stage 3, decision 6)** — not just those with asserts. Axis source priority: ① the assert's `construction_axis` ② the component's top-level `construction_axis` field ③ backend inference (native_chain tube/cylinder → Y) ④ Y fallback. Tiers ③④ are recorded in `defaulted_axes` for review.

**The builder also catches self-consistent errors at build time.** If your `construction_axis` + anchor `@orient` + `expected_axis` contradict each other, the build **refuses** before any cook, telling you exactly which field to fix. A wrong mental model can no longer produce a self-consistent-but-incorrect asset.

A construction-path **PCA crosscheck** still runs as a warning-only sanity check: if the declared axis diverges >2× tolerance from the actual geometry distribution, you get a `pca_crosscheck.warning` to review (the construction axis stays authoritative). Read `construction_axis_summary` to confirm which components got deterministic axes and their derived world axes.

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
- `build_procedural_asset` + one anchored component = **one template** copied N times (all instances identical, like 6 identical windows).
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
commit_sandbox(
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
