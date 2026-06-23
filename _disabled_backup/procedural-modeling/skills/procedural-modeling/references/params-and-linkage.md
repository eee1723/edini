# Asset-level Parameters & Linkage (A2-station)

Each component's `code` is independent by default. Dimensions **must** live in asset-level `params` and be read via `hou.ch('../name')` — a hardcoded `wheelbase = 1.0` literal in the frame is now **rejected at validation (A9, BLOCKING)** because it breaks the parametric contract (editing the asset parm does nothing; the geometry was baked from a literal). To make a **real parametric asset** (change one value, every dependent part updates), declare every size in `params` + use expression-driven anchors.

## Parameter Kinds

### Primary (user-exposed)
Top-level `params` with `kind: "primary"` install spare parms on the sandbox root. After commit they live on the final asset, so the user tunes them in the Houdini parameter panel and sees the whole asset update:
```jsonc
"params": {
  "wheelbase": {"kind": "primary", "default": 1.0, "min": 0.5, "max": 2.0},
  "wheel_r":   {"kind": "primary", "default": 0.35}
}
```

### Derived (computed once, shared globally)
Params with `kind: "derived"` are computed from a `from` expression
referencing primary (or earlier derived) values. The expression is evaluated
ONCE at build time and installed as a spare parm on the sandbox root.
**All components read the same pre-computed value** — zero redundancy:

```jsonc
"params": {
  "wheel_r":      {"kind": "primary", "default": 0.34},
  "bb_drop":      {"kind": "primary", "default": 0.07},
  "bb_height":    {"kind": "derived", "from": "wheel_r - bb_drop"},
  "seat_top_x":   {"kind": "derived", "from": "0.52 * cos(radians(st_angle))"},
  "chainstay_x":  {"kind": "derived", "from": "sqrt(cs_length*cs_length - bb_drop*bb_drop)"}
}
```

- Primary params need `default` (and optionally `min`/`max` for sliders).
- Derived params need `from` — a safe expression (see Expression Grammar below).
- Dependency graph is validated at build: **cycles are rejected**, orphan params (not consumed by any component) generate warnings.
- Evaluation order is automatic (topological sort) — you can reference one derived param from another.

### Constrained (user-editable, with validation)
```jsonc
"tire_width": {
  "kind": "constrained",
  "default": 0.025, "min": 0.020, "max": 0.035,
  "constraints": [
    {"name": "fork_clearance",
     "check": "tire_width + 0.005 < fork_len * 0.15",
     "on_violation": "block",
     "message": "Tire too wide for fork"}
  ]
}
```

## Reading params in component code
A component is a child of the sandbox root, so reference a param via a relative channel reference. List the params you read in `reads` so a typo is caught at build (not silently returned as 0):
```python
node = hou.pwd(); geo = node.geometry()
wheelbase = hou.ch('../wheelbase')   # one level up = sandbox root
wheel_r   = hou.ch('../wheel_r')
# Derived params work the same way:
bb_h      = hou.ch('../bb_height')
sx        = hou.ch('../seat_top_x')
```
```jsonc
{"id": "frame", "code": "...", "reads": ["wheelbase", "wheel_r", "bb_height", "seat_top_x"]}
```
Changing any primary parm re-cooks all dependent components (channel dependency).

## `add_parm` tool — runtime parameter creation

```python
from edini.harness import add_parm

# Add a float parameter to any node
add_parm("/obj/my_asset", "new_param", default=0.5, min=0.1, max=2.0, label="My Param")
# => {"success": True, "channel_path": "/obj/my_asset/new_param", "value": 0.5}

# Add to sandbox root during development
add_parm(sandbox_root_path, "extra_feature", default=1.0)
```

- Creates a spare FloatParmTemplate on the target node.
- Returns the channel path — immediately usable in `hou.ch()`.
- Idempotent: if the parm already exists, returns `already_exists: True`.
- Works on any node, not just sandbox roots.

## Expression Grammar (for `from`, `position_expr`, `orient_expr`, etc.)
