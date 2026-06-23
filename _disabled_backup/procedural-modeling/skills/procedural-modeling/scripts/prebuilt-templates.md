# Prebuilt Component Templates

> **Migration note (2026-06):** the reusable templates here have been promoted
> to a **structured component library** at
> `python3.11libs/edini/components/*.json`. New recipes should reference them
> via the `{"component": "<name>"}` syntax (see
> `references/declarative-builder.md` → Semantic Components) rather than
> copy-pasting the JSON below. This document remains as a reference for the
> underlying native_chain recipes and for authoring new library entries.

Copy-paste these `native_chain` recipes into your Builder recipe. Each produces
one geometric piece with `component_id` already tagged. Combine via CTP anchors
or direct merge.

## H21 NOTE

All templates use `attribwrangle` (Detail mode) for component_id tagging.
`attribcreate` menu items are version-specific and error-prone in H21.
`attribwrangle` with `s@component_id = "..."` is simpler and reliable.

Always verify parm names with `query_parms(type)` before using a template
with unfamiliar SOP types.

**`tube` / `cylinder` `type` parameter:** H21 defaults these to `type=0`
(Primitive), which emits a single primitive instead of a polygon mesh —
procedural workflows always want polygons. The builder now defaults `type`
to `1` (Polygon) when you omit it, but templates below set it explicitly
for clarity.

## How to use

In your `build_procedural_asset` recipe, reference a template like:

```json
{
  "id": "hub",
  "backend": "native_chain",
  "nodes": [
    {"type": "tube", "params": {"rad": [0.03, 0.03], "height": 0.06, "rows": 3, "cols": 16, "type": 1}},
    {"type": "fuse", "params": {}},
    {"type": "attribwrangle", "params": {"class": 1, "snippet": "s@component_id = \"hub\";"}}
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
    {"type": "tube", "params": {"rad": [0.025, 0.025], "height": 0.06, "rows": 3, "cols": 16, "type": 1}},
    {"type": "fuse", "params": {"dist": 0.0001}},
    {"type": "attribwrangle", "params": {"class": 1, "snippet": "s@component_id = \"hub\";"}}
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
    {"type": "tube", "params": {"rad": [0.001, 0.001], "height": 0.34, "rows": 2, "cols": 8, "type": 1}},
    {"type": "attribwrangle", "params": {"class": 1, "snippet": "s@component_id = \"spoke\";"}}
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
    {"type": "attribwrangle", "params": {"class": 1, "snippet": "s@component_id = \"pedal\";"}}
  ]
}
```

---

## Chainring Disc (flattened torus, no teeth)

```jsonc
{
  "id": "chainring",
  "backend": "native_chain",
  "nodes": [
    {"type": "torus", "params": {"radscale": 0.08, "rows": 3, "cols": 48, "type": "poly"}},
    {"type": "attribwrangle", "params": {"class": 1, "snippet": "s@component_id = \"chainring\";"}}
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
    {"type": "attribwrangle", "params": {"class": 1, "snippet": "s@component_id = \"chain_link\";"}}
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
    {"type": "tube", "params": {"rad": [0.018, 0.022], "height": 0.07, "rows": 4, "cols": 20, "type": 1}},
    {"type": "fuse", "params": {"dist": 0.0001}},
    {"type": "attribwrangle", "params": {"class": 1, "snippet": "s@component_id = \"bb_shell\";"}}
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
    {"type": "attribwrangle", "params": {"class": 1, "snippet": "s@component_id = \"brake_caliper\";"}}
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

> **Note:** `surfaceshape: 1` (roundtube) here is the SINGLE-wrangle mode —
> no `section_code`, so Sweep generates its own circular tube from `radius`.
> This is the ONLY case where a non-zero `surfaceshape` is correct. If you
> add a `section_code` (dual-wrangle), the builder will force `surfaceshape=0`
> and warn — see the declarative-builder reference.

---

## Saddle Base (simplified box, replace with vex_skeleton+skin for real saddles)

```jsonc
{
  "id": "saddle_base",
  "backend": "native_chain",
  "nodes": [
    {"type": "box", "params": {"sizex": 0.08, "sizey": 0.012, "sizez": 0.27}},
    {"type": "polybevel", "params": {"offset": 0.008}},
    {"type": "attribwrangle", "params": {"class": 1, "snippet": "s@component_id = \"saddle\";"}}
  ]
}
```
