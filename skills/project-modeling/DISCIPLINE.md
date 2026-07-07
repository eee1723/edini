# Modeling Discipline — VEX, native nodes, and Python

> Read this for the methodology of *how* to build geometry inside a component
> subnet. The rules below are not style preferences — each one opposes a real
> failure tendency observed in LLM-driven Houdini modeling.

## The four rules

### 1. VEX first

Most geometric needs are a wrangle (`attribwrangle`) + native SOPs. VEX is
parallel, fast, and the dominant idiom in modern Houdini. Reach for a wrangle
before a Python SOP.

**Why this is not a no-op:** LLMs trained on general Python often default to
solving geometry problems with `hou` scripting inside a Python SOP. That works
once but is slower, harder to hand-edit, and opaque to other Houdini users.
VEX is the shared language of Houdini geometry work.

### 2. No single-SOP Python dumps

If you must use Python, spread the logic across multiple SOPs (like you would
functions), never pile 200 lines into one Python SOP node. A single monolithic
script is unreadable, undebuggable, and unmaintainable.

**The anti-pattern:**
```
# WRONG — one Python SOP doing everything
hou.node(".../do_everything").parm("python").set("""
# 200 lines: build box, add bevel, scatter points, copy tubes, merge...
""")
```

**The fix:** decompose into native nodes connected in sequence. If a step
truly needs Python, isolate it to one small SOP with one responsibility.

**When you do write a Python SOP, copy `COMPONENT_TEMPLATE.md`'s skeleton.**
It encodes the five Python-SOP errors that recurred most across real
modeling sessions (bare `return` SyntaxError, attribute-before-write,
input-vs-output geometry, `createPoint` signature, `ch` vs `hou.ch`). Writing
a Python SOP from a blank string re-breaks one of those five nearly every
time.

**`houdini_run_python_sandbox` is NOT a component generator.** A sandbox runs
in an isolated geo container with **no inputs** — a sandbox Python SOP cannot
see any component's anchor points. Use the sandbox only to sketch a
self-contained generator with hardcoded test data and verify the algorithm
cooks clean; then **discard the sandbox and rebuild inside the component
subnet**, wired to `in_<from>_<anchor>`. Never try to make a sandbox consume a
component's anchors (sessions wasted 3 sandbox iterations discovering this
for the shelf).

### 3. Native nodes where VEX is hard

Some operations have purpose-built native nodes that are more robust than a
hand-written VEX equivalent: `sweep`, `fuse`, `boolean`, `polyextrude`,
`subdivide`. When VEX would be fighting the geometry, use the native node.

### 4. Always `measure` — never hardcode

This is Guardrail 2, restated as a modeling principle: positions, sizes, and
anchor locations come from **measurements of live geometry** (via
`project_add_anchors` or `ch()` references to design params), never from typed
coordinates. This is what keeps the model parametric — change a param, and
every measured quantity follows.

**The test:** if you find yourself typing a literal number for a position (not
a size or count), ask "could this be measured from geometry instead?" If yes,
measure it.

## H21 parameter quick-reference (when a native node needs specific parms)

| Node | Key parms (Houdini 21) |
|---|---|
| Attrib Promote | `dstclass` (0=detail...), `inname`, `method` (0=first...), `deletestat` (0=keep original) |
| Blast | `grouptype`, `group`, `negate`, `fill` (0=remove, 1=keep outside) |
| For-Each (Named Primitive) | `method`=1 (by attr), `attribname`="name", inner block has `metadata` detail attr `numiterations` |
| Sweep | `surface`=2 (primitive), `scale`=ch ref, `ancport` (anchor port) |
| Copy-to-Points | input 0 = template geo, input 1 = target points; `pack` (0/1), use `@orient`/`@scale`/`@N`/`@up` attrs on target pts |
