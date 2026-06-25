---
name: recipe-library
description: Use when the user wants to create or modify geometry in Houdini. BEFORE hand-authoring nodes, query the recipe library (recipe_list) for a pre-built subnet recipe that already solves the task — recipes are pre-validated and rebuild deterministically, which is more reliable than authoring node networks from scratch. Read the recipe (recipe_read) to understand its wiring and exposed parameters, then rebuild it (recipe_rebuild) with overrides. Only fall back to manual houdini_create_node / houdini_run_python_sandbox if no recipe matches.
---

# Recipe Library — prefer reuse over hand-authoring

The recipe library holds subnet recipes authored by a human TD: each recipe is a
correctly-wired node network (nodes, connections, and the parameters that were
changed from type defaults) plus the subnet's Notes as metadata. Recipes rebuild
deterministically, so reusing one avoids the errors that come from an LLM
guessing node parameters and wiring.

## Workflow

1. **Search first.** `recipe_list(query="<intent>")` — pass a concise keyword
   (the geometry type or purpose: "tube", "copy", "extrude", "scatter", or a
   category-path component like "Sim" / "Procedural_Modeling"). Inspect the
   matched summaries (id, kind, category, tree_path, exposed_parms). You may
   filter by `kind` ("vex" for VEX-snippet recipes, "network" for node-network
   recipes) when the user wants a specific type.
2. **Understand the match.** `recipe_read(recipe_id)` — look at the internal
   nodes, the `changed_params` on each (these encode the author's intent and
   conventions, e.g. `endcaptype=1` for closed tubes), the `vex_snippets`
   (the VEX code for any wrangle nodes — read this to understand a 'vex'
   recipe), and the `exposed_parms` list (the ONLY parms you may override).
3. **Rebuild.** `recipe_rebuild(recipe_id, parent_path, overrides={...})` —
   overrides keys must come from `exposed_parms`. The tool topologically orders
   nodes, applies params, restores VEX snippets + run-over class on wrangles,
   wires inputs, and runs a built-in structural verify.
4. **Verify & report.** Read the returned `verify.mismatches` and `warnings`.
   For heavy post-build checks use the shared tools on the rebuilt path:
   `inspect_health`, `verify_orientation`, `geometry_inventory`.
5. **No match?** Fall back to `houdini_run_python_sandbox` or
   `houdini_create_node`. If you hand-build a reusable pattern, offer to
   `recipe_capture` it into the library for next time.

## Rules

- **Override exposed_parms only.** Never set internal node parms directly on a
  rebuilt subnet — `exposed_parms` are the designed control surface.
- **Never ignore a failed verify.** If `recipe_rebuild` returns
  `success: false`, report the mismatches to the user and fix the cause rather
  than papering over it.
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
