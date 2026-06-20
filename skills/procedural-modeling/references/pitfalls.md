# Common Pitfalls

Mistakes that waste 30-50% of procedural generation time. Avoid them.

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
