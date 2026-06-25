---
name: recipe-library
description: Use when the user wants to create or modify geometry in Houdini. BEFORE hand-authoring nodes, query the recipe library (recipe_list) for a pre-built subnet recipe that already solves the task — recipes are pre-validated and rebuild deterministically, which is more reliable than authoring node networks from scratch. Read the recipe (recipe_read) to understand its wiring and exposed parameters, then rebuild it (recipe_rebuild) with overrides. Only fall back to manual houdini_create_node / houdini_run_python_sandbox if no recipe matches.
---

# Recipe Library — reference patterns that cut authoring errors

The recipe library holds subnet recipes authored by a human TD. Each recipe is a
**reference sample**, not a rigid template: it records how an expert wired a
network correctly (node types, connections, the parameters that matter) so you
can stand on verified syntax instead of guessing Houdini's parameter names and
node-version quirks.

## The core idea: recipes lower your error rate, they don't limit you

When the user wants geometry, search the library for a matching pattern. Read its
`python_script` — a readable Python reconstruction of the author's network. Study
how the nodes are created, wired, and which parameters the author deliberately
set (annotated `# author-marked`). Then **build your own network**, adapted to
what the user actually asked for. You may:

- reuse the script nearly verbatim if it fits,
- modify it (swap nodes, change counts, add stages),
- or just borrow the idiom (e.g. how `copytopoints` + `attribwrangle` pair up)
  while building something the recipe never imagined.

The point is to avoid the errors that come from inventing Houdini syntax cold —
wrong node-version names (`sweep` vs `sweep::2.0`), missing required connections,
parms that don't exist on the node you used. A recipe pre-validates all of that.

## Workflow

1. **Search first.** `recipe_list(query="<intent>")` — pass a concise keyword
   (the geometry type or purpose: "tube", "copy", "extrude", "scatter", or a
   category-path component like "Procedural_Modeling"). Inspect the matched
   summaries (id, kind, category, function).
2. **Read the reference.** `recipe_read(recipe_id)` — the `python_script` field
   is the primary value. Read it to learn:
   - the node types and their correct version names (`sweep::2.0`, `copytopoints::2.0`),
   - the wiring (`node.setInput(0, upstream)`),
   - the `# author-marked` parameters — these encode the conventions that make
     the geometry correct (e.g. `endcaptype=1` for closed tubes), and
   - any inlined VEX (wrangle `snippet` shown as a triple-quoted string).
   The `notes` field (功能/用途/重要参数/不要用于) tells you when this pattern
   applies and when it doesn't (respect 不要用于).
3. **Build, don't just replay.** Using `houdini_run_python_sandbox` (or
   `recipe_rebuild` for a quick faithful copy), construct the network the user
   needs. Adapt the recipe's idiom to the real task — combine ideas across
   multiple recipes if that serves the request.
4. **Verify & report.** After building, use the shared tools:
   `inspect_health`, `verify_orientation`, `geometry_inventory`, then capture
   the viewport if the change is visible.
5. **No match?** Fall back to `houdini_run_python_sandbox` /
   `houdini_create_node`. If you hand-build a reusable pattern, offer to
   `recipe_capture` it into the library for next time.

## Rules

- **python_script is reference material.** Read it to learn, then author with
  your own judgment. Never blindly execute a recipe's script when the user's
  task differs from it — adapt.
- **marked_params are the signal.** The parameters annotated `# author-marked`
  are the ones the author deliberately set; they encode the conventions. Get
  those right; the rest of `changed_params` is supporting detail you can take
  or leave.
- **Notes is the contract.** When capturing (`recipe_capture`), the subnet's
  Notes must be non-empty and descriptive. Use the `功能：` (function) and
  `重要参数：` (key params) convention so the index stays searchable.

## Growing the library

When you build geometry the user will likely reuse (a tube rig, a scatter
setup, a wheel), capture it:
- Set the subnet's Notes: `功能：<what it does>`, then `重要参数：<parm names>`
  that should always be recorded even at default.
- `recipe_capture(subnet_path)` — validates Notes, serializes the network,
  writes `recipe.json`, and rebuilds the index. Capture fails clearly if Notes
  is empty or a placeholder.

### Current primitive library

The library is intentionally a set of *geometry-operation primitives*, not
finished parts. Each encodes "how to do a class of shape correctly" (closed
caps, orientation, axis conventions) and never "what shape to make" — so the
LLM composes them at the layout layer. Reuse these before hand-authoring:

| id | does | key marks |
|---|---|---|
| `tube_along_curve` | sweep a closed tube along any curve (frames/handlebars) | surfacetype, endcaptype, rad |
| `extrude_solid` | extrude a closed 2D profile into a solid (chainring/pedal) | dist, outputfront, outputback |
| `revolve_profile` | revolve a 2D profile into a lathe solid (tire/grip) | surftype, cap, dir, divs |
| `radial_copy` | copy a unit template N times around an axis (spokes) | radial_count, radial_radius |
| `linear_array_copy` | copy a unit template N times along a curve (chain/railing) | array_count |
| `mirror_bilateral` | mirror half-geometry and weld the seam (symmetric bodies) | dir, keepOriginal, consolidatepts |
| `boolean_op` | union/subtract/intersect two solids + clean + recompute normals | op, subtractchoices, booleanop |
| `bevel_edges` | round/chamfer sharp edges by angle (mechanical fillets) | bevel, weight, segments, group |
| `Base_Copy` | scatter randomly-scaled instances on a surface (rivets/grass) | npts, scale, group |

> Note: `exposed_parms` are not yet promoted on these recipes. Until they are,
> rebuilding yields the authored defaults; for now vary the result by editing
> the rebuilt subnet's internal `marked_params` directly (the `重要参数` names).

### Capturing a whole category tree at once

When the user has organized subnets into a nested category taxonomy (e.g.
`/obj/sopnet1/Procedural_Modeling/Base_Sweep`, `.../Sim/RBD/Voronoi_Fracture`),
ingest them all in one call:
- `recipe_capture_tree(root_path)` — recurses from the root, capturing every
  *leaf* subnet (one whose children include real SOP nodes) and descending
  into *container* subnets (whose children are all subnets).
- recipe_ids become tree paths (`Procedural_Modeling.Base_Sweep`) so
  same-named leaves in different branches never collide. Query with
  `recipe_list(query="Sim")` or `recipe_list(query="Procedural_Modeling")` to
  find them by category component.
- VEX wrangle nodes inside a leaf are captured as `vex_snippets` (with their
  run-over class), and the recipe's `kind` flips to `"vex"`. The snippet code
  is NOT folded into changed_params — it lives in its own searchable field.
- `output` / `stashed_geo` nodes are ignored automatically (Houdini plumbing,
  not user content).
- Empty Notes are auto-filled (root path + leaf name + inner node types) rather
  than blocking capture, with a warning so the user knows to hand-edit later.

### Two recipe kinds

| kind | what it is | how to read it |
|------|-----------|----------------|
| `network` | A node network (curve+sweep, grid+scatter+copytopoints) | `nodes[]` with changed_params + wiring |
| `vex` | Contains one or more wrangle nodes whose VEX is the real payload | `vex_snippets[]` (code + runover); nodes[] still has the topology |

Both are searched uniformly via `recipe_list`; pass `kind` to narrow.
