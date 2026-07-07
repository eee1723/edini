# Python SOP Component Template — the one correct shape

> Read this BEFORE you write a Python SOP inside a Project HDA component subnet.
> Every error below was committed 2+ times across two real modeling sessions
> (table + road bike). This template exists so you don't reinvent — and
> re-break — the same wheel per component.

## When to use a Python SOP at all

**Prefer native SOPs + VEX first** (see `DISCIPLINE.md` rule 1). Reach for a
Python SOP inside a component **only** when the geometry is genuinely
algorithmic and awkward in native nodes: a road-bike frame's tube graph, a
spoked wheel, a curved handlebar. A box, a copy-to-points leg array, a shelf
spanning 4 points — these are **native SOPs**, not Python.

If you do use Python, **copy the skeleton below** and fill in only the
geometry-generation part. The skeleton encodes the five things sessions got
wrong repeatedly.

## The skeleton (copy this verbatim, fill the marked gap)

```python
import hou

node = hou.pwd()
geo = node.geometry()
geo.clear()

# (1) Read the upstream anchor from the component's INPUT — NOT from
#     node.geometry() (that is the OUTPUT you're building). node.geometry()
#     is the writable detail you hand back; reading points "from it" gets
#     you nothing or stale input.
inputs = node.inputs()
if inputs and inputs[0].geometry().points():
    anchor_pt = inputs[0].geometry().points()[0]
    origin = anchor_pt.position()

    # (2) Create attributes BEFORE any setAttribValue. An attribute must
    #     exist on the detail before you can write per-primitive/point values
    #     onto it. Declare ALL attributes you'll write up here.
    geo.addAttrib(hou.attribType.Prim, "width", 1.0)
    geo.addAttrib(hou.attribType.Prim, "part", "")

    # ── YOUR GEOMETRY GENERATION GOES HERE ──
    # Build curves/points/primatives from `origin` + design params.
    # For each new point:
    #     pt = geo.createPoint()          # createPoint() takes NO arguments
    #     pt.setPosition(hou.Vector3(x, y, z))
    # For params: use hou.ch('/obj/.../project_core/<param>') (ABSOLUTE).
    pass
# (3) No bare `return` ANYWHERE in this body. The Python SOP cook code is
#     NOT inside a def — a top-level `return` is a SyntaxError ("return
#     outside function"). Guard with `if inputs and ...:` instead, as above.
```

## The five rules the skeleton enforces (and why each was a real incident)

### 1. No bare `return` — the #1 repeat offender (6+ times across sessions)

A Python SOP's `python` parm is executed as the cook body, **not** inside a
function. A top-level `return` raises `SyntaxError: 'return' outside function`
and the whole SOP cooks empty. This hit fork, handlebar, seat, crankset, both
wheels, and shelf_builder.

```python
# WRONG — SyntaxError, empty geometry, silent until you check_errors
inputs = node.inputs()
if not inputs:
    return                         # ← illegal at module top level
# ...rest never runs...

# RIGHT — guard the whole body in one if
if inputs and inputs[0].geometry().points():
    # ...whole body here...
```

### 2. Create attributes BEFORE writing them

`setAttribValue("width", x)` on a primitive fails if `width` doesn't exist on
the detail yet. Both wheels hit this: `width` was declared at the *end* of the
script, after PolyWire-relevant prims already tried to read it.

```python
# WRONG
for prim in geo.prims():
    prim.setAttribValue("width", 2.0)   # error: attrib doesn't exist yet
geo.addAttrib(hou.attribType.Prim, "width", 1.0)   # too late

# RIGHT — declare first, write later
geo.addAttrib(hou.attribType.Prim, "width", 1.0)
for prim in geo.prims():
    prim.setAttribValue("width", 2.0)
```

### 3. Read input geometry from `inputs()[0].geometry()`, not `node.geometry()`

`node.geometry()` is the detail you are **writing** (the output). It starts
empty after `geo.clear()`. To read the upstream anchor points, go through the
input:

```python
# WRONG — reads your own (empty) output, gets 0 points
points = node.geometry().points()      # always [] after clear()

# RIGHT
input_geo = node.inputs()[0].geometry()
points = input_geo.points()
```

### 4. `createPoint()` takes NO positional arguments

`geo.createPoint()` creates a point at the origin and returns it; you set its
position separately. Passing a Vector3 raises `takes 1 positional argument but
2 were given`.

```python
# WRONG
pt = geo.createPoint(hou.Vector3(x, y, z))   # TypeError

# RIGHT
pt = geo.createPoint()
pt.setPosition(hou.Vector3(x, y, z))
```

### 5. `ch()` vs `hou.ch()` — don't mix Hscript and Python expression contexts

Inside a Python SOP, use `hou.ch(...)`. Bare `ch(...)` is an Hscript
expression function that only resolves in parameter expression context, not
in a Python SOP cook body — it silently returns 0 or NameError.

```python
# WRONG / unreliable in a Python SOP body
shelf_h = ch('/obj/.../shelf_thick')

# RIGHT
shelf_h = hou.ch('/obj/.../shelf_thick')
```

## Wiring the Python SOP into the component

After writing the code, wire it into the scaffold's existing chain — do NOT
rebuild the chain:

```
in_<from>_<anchor>  →  your python SOP  →  out_geometry  →  ...  →  output_0
```

For tube-like geometry (frame, fork, bars), add a `polywire` downstream of the
Python SOP to give curves thickness, and reference `tube_radius`:

```
houdini_set_param(<polywire>, "radius", "ch('/obj/.../project_core/tube_radius')")
```

## Critical: sandbox is NOT a component generator

`houdini_run_python_sandbox` runs in an **isolated geo container with no
inputs**. A sandbox Python SOP **cannot see** the component's anchor points
(sessions wasted 3 sandbox iterations discovering this for the shelf).

- **sandbox** = sketch a self-contained generator with hardcoded test data,
  verify the algorithm cooks clean, then **discard** and rebuild inside the
  component subnet.
- **component Python SOP** = the real generator, wired to `in_<from>_<anchor>`,
  reading live anchors.

Never try to make a sandbox consume a component's anchors. It can't.

## Checklist before you call the Python SOP done

- [ ] No bare `return` anywhere in the body (grep for it).
- [ ] Every attribute written is `addAttrib`'d **before** the first `setAttribValue`.
- [ ] Input read via `node.inputs()[0].geometry()`, not `node.geometry()`.
- [ ] Points created with `createPoint()` + `setPosition(hou.Vector3(...))`.
- [ ] Params read via `hou.ch('/obj/.../project_core/<name>')` (absolute, `hou.`-prefixed).
- [ ] `houdini_check_errors` on the component returns no errors.
- [ ] `houdini_inspect_geo` on the Python SOP shows non-zero points/prims.
