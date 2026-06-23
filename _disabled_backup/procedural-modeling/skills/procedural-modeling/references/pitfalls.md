# Common Pitfalls

Mistakes that waste 30-50% of procedural generation time. Avoid them.

## `tube` / `cylinder` need `type:1` (Polygon) — default `type:0` emits 1 primitive

H21 `tube` and `cylinder` SOPs default `type` to `0` (Primitive), which emits
a SINGLE primitive — not a polygon mesh. Copy-to-Points then instances that
single primitive as a degenerate point, and the geometry silently "disappears"
(`geometry_inventory` shows `prim_count: 1, size: [0,0,0]` for the instance).

The builder now **defaults `type` to `1` (Polygon)** when you omit it on
`tube`/`cylinder` in a `native_chain`, so you don't have to remember. But if
you ever set these SOPs by hand (raw network_mode), always set `type:1`.

```jsonc
// ✅ CORRECT — type:1 gives a 12-sided polygon cylinder (real geometry)
{"type": "tube", "params": {"rad": [0.03, 0.03], "height": 0.7, "cols": 12, "type": 1}}
// ❌ WRONG — type defaults to 0 (Primitive), 1 prim, geometry vanishes on CTP
{"type": "tube", "params": {"rad": [0.03, 0.03], "height": 0.7, "cols": 12}}
```

## Raw `network_mode` cannot pass commit (G3 bake gate)

A hand-written `houdini_run_python_sandbox(network_mode=true)` build that emits
`@component_id`-tagged geometry has **no `edini_world_axis`** — only
`build_procedural_asset` bakes that axis (from the declared `construction_axis`).
The commit gate (G3a) refuses such a sandbox outright:

```
G3_NOT_BAKED: asset did not go through build_procedural_asset
(no edini_world_axis on every prim). ... Missing on: ['frame', 'wheel_front']
```

The asset stays in the sandbox (no rename/discard) so you can fix and re-commit.
**Fix**: rebuild via `build_procedural_asset` with a recipe. `network_mode` is
reserved for genuinely single-piece assets that recipe cannot express (one
fractal, one parametric surface) — and even then the commit gate only passes
if the geometry has no `@component_id` prims (i.e. it's not pretending to be a
modular asset).

## Hardcoded size literals are BLOCKING (A9)

A size-named variable (`wheelbase`, `radius`, `bb_height`, ...) assigned a bare
numeric literal in component `code`, where the variable is neither a declared
recipe param nor in the component's `reads` list, is a hardcoded dimension.
`validate_recipe` rejects it at A9:

```
A9_HARDCODED_SIZE: component 'frame' assigns wheelbase = 1.0 as a hardcoded
literal (line 5). Dimensions must live in recipe.params ...
```

**Fix**: add the var to `recipe.params` (becomes a real spare parm) or to the
component's `reads` list (if it's a local alias of a param the component reads).
Loop counters like `i = 0` pass through (no size hint).

## Python `hou.ch()` must use `../` prefix

Params are installed on the sandbox root (one level ABOVE component SOPs).
`hou.ch("param")` looks on the current node itself — always fail.

```python
# ❌ WRONG — looks for param on current Python SOP (doesn't exist)
fs = hou.ch('frame_scale')

# ✅ CORRECT — one level up to sandbox root where params live
fs = hou.ch('../frame_scale')
```

## VEX `ch()` on vex_skeleton wrangles

The builder auto-installs spare parms on wrangle nodes. The expression
for each spare parm is `ch("../param_name")` — reading from the sandbox
root one level up. Your VEX code just calls `ch("param_name")` directly.

```vex
// ✅ CORRECT — the spare parm resolves to ch("../param") behind the scenes
float r = ch("tube_od") / 2.0;
```

## vex_skeleton: use addprim("poly") not "polyline" for PolyExtrude

PolyExtrude only extrudes polygon FACES, not curves. For the single-wrangle
profile mode, create the face with `addprim(0, "poly")`:

```vex
// ✅ CORRECT
int prim = addprim(0, "poly");  // polygon face — PolyExtrude works
// ❌ WRONG
int prim = addprim(0, "polyline");  // curve — PolyExtrude gives zero result
```

For dual-wrangle Sweep mode, the path IS `"polyline"` and the cross-section
IS `"polyline"` (Sweep closes them automatically).

## H21 parm names: outputback NOT output_back

Houdini 21 PolyExtrude uses `outputback` (no underscore), not `output_back`.
Always verify with `query_parms("polyextrude")` before setting parms.

## VEX channel reference syntax

**VEX `ch()` functions take plain string parm names — NOT Python-style `%` formatting.**

```vex
// ❌ WRONG — %radius% is Python-string thinking
float r = chf("%radius%");

// ✅ CORRECT — plain string
float r = chf("radius");
```

## VEX function definitions in wrangles

**VEX wrangles do NOT support `void`/`int[]`/`float[]` function definitions inside the snippet.**
Writing `void make_tube(vector pts[]; float r) { ... }` causes:
`Syntax error, unexpected identifier, expecting integer constant or float constant.`

✅ Use inline code blocks `{ ... }` instead of named functions.

## Node type name mismatches (H21)

| ❌ Wrong | ✅ Correct |
|---|---|
| `transform` | `xform` |
| `polybevel` | `polybevel::3.0` |

## attribcreate menu item names (H21)

```jsonc
// ❌ WRONG — H21 rejects these
{"class1": "prim", "type1": "string"}

// ✅ CORRECT for H21
{"class1": "primitive", "type1": "string"}
```

## Spare parms on non-wrangle nodes

Adding spare parameters to `xform`, `tube`, `torus` etc. via `add_float_parm()` is fragile — these nodes already have their own parameter templates. For parameter linkage across network_mode builds, install shared params on the sandbox CONTAINER and use `ch("../../param")` expressions on child nodes.

## pscale semantics in Copy-to-Points
- `@pscale = 1.0` means **original size** of the source geometry (no scaling)
- `@pscale = wheel_radius` does NOT give you a wheel of that radius — it SCALES by that factor
- If your wheel geometry is already modeled at correct radius, set `@pscale = 1.0`
- If you need to scale: `@pscale = desired_size / source_geo_size`

## Attribute name collisions
- If both body and component have `@Cd`, Copy-to-Points may produce unexpected results
- Rule: only set `@Cd` on the FINAL merged output, not on intermediate component streams
- Use `material_zone` (string) for material intent, not `@Cd` color

## Group expression syntax in Copy-to-Points
- `targetgroup` parameter uses Houdini group syntax, NOT Python expressions
- Valid: `wheel_anchors` (group name), `@component_id==wheel` (attribute expression)
- Invalid: Python string operations, f-strings, regex

## Node destruction cascades
- If you destroy a node that has downstream connections, those connections break
- Always disconnect outputs before destroying: `node.setInput(idx, None)` on all consumers
- Better: rebuild the network in correct order rather than patching live connections

## Attribute creation order
- `geo.addAttrib()` MUST be called BEFORE creating any geometry that uses it
- Creating points first, then adding attribute = crash or silent failure
- Pattern: all `addAttrib` calls at the top, then geometry creation

## String Safety
When embedding string literals in Python code that will pass through JSON → parm.set():
- Avoid backtick characters
- Escape backslashes as `\\\\` (double-escape for JSON + Python)
- Use raw strings (`r"..."`) for paths
- For special characters in data (key labels, etc.), use unicode escapes
