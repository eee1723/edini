# Asset-level Parameters & Linkage (A2-station)

By default each component's `code` is independent — a hardcoded `wheelbase = 1.0` in the frame does nothing to the wheel anchors. To make a **real parametric asset** (change one value, every dependent part updates), use asset-level `params` + expression-driven anchors.

## Declaring shared params
Top-level `params` installs spare parms on the sandbox root. After commit they live on the final asset, so the user tunes them in the Houdini parameter panel and sees the whole asset update:
```jsonc
"params": {
  "wheelbase": {"default": 1.0, "min": 0.5, "max": 2.0},
  "wheel_r":   {"default": 0.35}
}
```

## Reading params in component code
A component is a child of the sandbox root, so reference a param via a relative channel reference. List the params you read in `reads` so a typo is caught at build (not silently returned as 0):
```python
node = hou.pwd(); geo = node.geometry()
wheelbase = hou.ch('../wheelbase')   # one level up = sandbox root
wheel_r   = hou.ch('../wheel_r')
...
```
```jsonc
{"id": "frame", "code": "...", "reads": ["wheelbase", "wheel_r"]}
```
Changing the parm re-cooks the component automatically (channel dependency).

## Linking anchor positions to params
Anchors accept `position_expr` / `orient_expr` / `pscale_expr` — expression strings (or plain numbers) evaluated against the asset params **at build time**. This is how the wheel follows the frame's wheelbase:
```jsonc
{"position_expr": ["wheelbase/2", "wheel_r", "0"], "component_id": "wheel_fl"}
```
- Expression grammar: parameter names, arithmetic (`+ - * / % **`), unary `-`, and a whitelist of `math` functions (`sin cos sqrt abs min max ...`) plus constants `pi`/`e`/`tau`. Anything else (imports, attributes, calls to non-whitelisted functions) is **rejected** — the engine is a security sandbox, not a Python `eval`.
- A bad expression (unknown param, syntax error, div-by-zero) fails the build with a precise error naming the anchor and the reason.
- `position` (static numbers) and `position_expr` are mutually exclusive; static is the backward-compatible default.

## Design note
Anchor positions are resolved at BUILD time (deterministic) and baked as coordinates — they are assembly-time, not cook-time. Component *shapes* driven by params (e.g. wheel radius) ARE cook-time dynamic via `hou.ch`. This split is intentional: the layout is fixed by the recipe; the parts themselves stay live.

## Parameter Exposure (in the sandbox — not after commit)

Every procedural asset MUST expose user-controllable parameters. Hardcoded Python variables are NOT acceptable. Parameters must be installed on the Python SOP **during the sandbox cook**, so they exist when the user opens the node — not bolted on as a separate post-commit step.

### Method 1: Spare Parameters on Python SOP (preferred)

```python
node = hou.pwd()
geo = node.geometry()

# Declare the parameters with defaults and ranges
PARM_SPECS = [
    ("radius", hou.FloatParmTemplate("radius", "Radius", 1,
        default_value=((0.35,),), min=0.05, max=2.0,
        naming_scheme=hou.parmNamingScheme.Base1)),
    ("count",  hou.IntParmTemplate("count", "Count", 1,
        default_value=((8,),), min=3, max=64,
        naming_scheme=hou.parmNamingScheme.Base1)),
    ("height", hou.FloatParmTemplate("height", "Height", 1,
        default_value=((2.0,),), min=0.1, max=10.0,
        naming_scheme=hou.parmNamingScheme.Base1)),
]

# Install idempotently — only adds what's missing
ptg = node.parmTemplateGroup()
missing = [tmpl for name, tmpl in PARM_SPECS if ptg.find(name) is None]
for tmpl in missing:
    ptg.append(tmpl)
if missing:
    node.setParmTemplateGroup(ptg)  # triggers a recook; this cook continues with defaults

# Read (now guaranteed to exist)
radius = node.evalParm("radius")
count  = node.evalParm("count")
height = node.evalParm("height")

# ... generate geometry using radius, count, height ...
```

On the first cook, the parameters don't exist yet — `missing` is non-empty, we install the templates (which triggers a recook), then the current cook continues using the `default_value`s. On every subsequent cook the parameters exist and the user's edited values are read directly.

### Method 2: VEX Channel References
```vex
float radius = chf("radius");    // Creates slider in UI
int count = chi("count");
vector offset = chv("offset");
float profile = chramp("profile", @curveu);  // Ramp widget
```

### Minimum parameters per asset type
- **Vehicle**: wheelbase, body_length, body_height, wheel_radius, ground_clearance, spoke_count
- **Furniture**: seat_height, width, depth, leg_style, material_roughness
- **Architecture**: floors, floor_height, width, depth, window_density, balcony_depth
- **Organic/Plant**: trunk_height, branch_count, branch_angle, leaf_density, seed
- **Mechanical**: key_size, spacing, row_count, bevel_radius, base_thickness
