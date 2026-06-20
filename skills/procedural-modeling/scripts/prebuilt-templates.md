# Prebuilt Component Templates

Copy-paste these `native_chain` recipes into your Builder recipe. Each produces
one geometric piece with `component_id` already tagged. Combine via CTP anchors
or direct merge.

## ⛔ H21 PARM VERIFICATION — READ FIRST

**These templates were written against Houdini 21.0.440. Parm names can change between versions.**
Two known H21 traps that produce build-time errors:

1. **`attribcreate` menu items** — `class1` and `type1` values are version-specific menu strings.
   Testing on H21.0.440 confirmed: using `"prim"`/`"string"` produces `Invalid menu item` errors.
   **ALWAYS verify with `query_parms("attribcreate")` before using any template that sets these.**

2. **`torus` parm names** — The `rad` parm from older Houdini does NOT exist in H21.
   The torus template below uses `query_parms`-verified H21 parms.
   **If you change torus sizing, verify the parm names first.**

**Rule:** Before copy-pasting any template that sets parms on `tube`, `torus`, or `attribcreate`,
run `query_parms(node_type)` and confirm every parm name exists.

## How to use

In your `build_procedural_asset` recipe, reference a template like:

```json
{
  "id": "hub",
  "backend": "native_chain",
  "nodes": [
    {"type": "tube", "params": {"rad": [0.03, 0.03], "height": 0.06, "rows": 3, "cols": 16}},
    {"type": "fuse", "params": {}},
    {"type": "attribcreate", "name": "tag_hub", "params": {"name1": "component_id", "class1": "primitive", "type1": "string", "string1": "hub"}}
  ]
}
```

Never hand-write the geometry in Python when a native SOP template exists.

---

## Cylinder / Hub

```jsonc
{
  "id": "hub",
  "backend": "native_chain",
  "anchors": [/* anchor specs here (optional) */],
  "nodes": [
    {"type": "tube", "params": {"rad": [0.025, 0.025], "height": 0.06, "rows": 3, "cols": 16}},
    {"type": "fuse", "params": {"dist": 0.0001}},
    {"type": "attribcreate", "name": "tag",
     "params": {"name1": "component_id", "class1": "primitive", "type1": "string", "string1": "hub"}}
  ]
}
```

---

## Single Spoke (thin tube, unit-scale for CTP)

```jsonc
{
  "id": "spoke",
  "backend": "native_chain",
  "anchors": [/* scatter wrangle fills these */],
  "nodes": [
    {"type": "tube", "params": {"rad": [0.001, 0.001], "height": 0.34, "rows": 2, "cols": 8}},
    {"type": "attribcreate", "name": "tag",
     "params": {"name1": "component_id", "class1": "primitive", "type1": "string", "string1": "spoke"}}
  ]
}
```

---

## Pedal Body (rectangular block)

```jsonc
{
  "id": "pedal",
  "backend": "native_chain",
  "nodes": [
    {"type": "box", "params": {"sizex": 0.06, "sizey": 0.01, "sizez": 0.03}},
    {"type": "polybevel", "params": {"offset": 0.003}},
    {"type": "fuse", "params": {"dist": 0.0001}},
    {"type": "attribcreate", "name": "tag",
     "params": {"name1": "component_id", "class1": "primitive", "type1": "string", "string1": "pedal"}}
  ]
}
```

---

## Chainring Disc (flattened torus, no teeth)

> ⚠️ **H21 verified**: `rad` parm does NOT exist. Use `radscale` for radius scaling
> and set the torus orientation via `orient`. Verify with `query_parms("torus")`.

```jsonc
{
  "id": "chainring",
  "backend": "native_chain",
  "nodes": [
    {"type": "torus", "params": {"radscale": 0.08, "rows": 3, "cols": 48, "type": "poly"}},
    {"type": "attribcreate", "name": "tag",
     "params": {"name1": "component_id", "class1": "primitive", "type1": "string", "string1": "chainring"}}
  ]
}
```

---

## Gear / Chainring with Teeth (using vex_skeleton for toothed profile)

Pair with `make_gear_profile()` in a `vex_skeleton` component for toothed disc:

```jsonc
{
  "id": "chainring_gear",
  "backend": "vex_skeleton",
  "code": "int prof[] = make_gear_profile(0, chi('chainring_teeth'), chf('cr_outer'), chf('cr_inner'), 'XZ', {0,0,0});",
  "form_node": {
    "type": "polyextrude::2.0",
    "input0": "self",
    "params": {"dist": 0.004, "output_back": 1}
  }
}
```

---

## Chain Link (single plate for CTP)

```jsonc
{
  "id": "chain_link",
  "backend": "native_chain",
  "nodes": [
    {"type": "box", "params": {"sizex": 0.006, "sizey": 0.002, "sizez": 0.012}},
    {"type": "attribcreate", "name": "tag",
     "params": {"name1": "component_id", "class1": "primitive", "type1": "string", "string1": "chain_link"}}
  ]
}
```

---

## Bottom Bracket Shell

```jsonc
{
  "id": "bb_shell",
  "backend": "native_chain",
  "nodes": [
    {"type": "tube", "params": {"rad": [0.018, 0.022], "height": 0.07, "rows": 4, "cols": 20}},
    {"type": "fuse", "params": {"dist": 0.0001}},
    {"type": "attribcreate", "name": "tag",
     "params": {"name1": "component_id", "class1": "primitive", "type1": "string", "string1": "bb_shell"}}
  ]
}
```

---

## Brake Caliper (simplified)

```jsonc
{
  "id": "brake_caliper",
  "backend": "native_chain",
  "nodes": [
    {"type": "box", "params": {"sizex": 0.02, "sizey": 0.025, "sizez": 0.01}},
    {"type": "polybevel", "params": {"offset": 0.002}},
    {"type": "attribcreate", "name": "tag",
     "params": {"name1": "component_id", "class1": "primitive", "type1": "string", "string1": "brake_caliper"}}
  ]
}
```

---

## Fender / Mudguard Profile (vex_skeleton)

```jsonc
{
  "id": "fender",
  "backend": "vex_skeleton",
  "code": "int path[] = make_arc_path(0, 32, chf('fender_radius'), 30, 180, 'XZ', {0,0,0});",
  "form_node": {
    "type": "sweep::2.0",
    "input0": "self",
    "params": {"surfaceshape": 1, "radius": 0.06, "endcaptype": 0}
  }
}
```

---

## Saddle Base (simplified box, replace with vex_skeleton+skin for real saddles)

```jsonc
{
  "id": "saddle_base",
  "backend": "native_chain",
  "nodes": [
    {"type": "box", "params": {"sizex": 0.08, "sizey": 0.012, "sizez": 0.27}},
    {"type": "polybevel", "params": {"offset": 0.008}},
    {"type": "attribcreate", "name": "tag",
     "params": {"name1": "component_id", "class1": "primitive", "type1": "string", "string1": "saddle"}}
  ]
}
```
