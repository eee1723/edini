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
   (the geometry type or purpose: "tube", "copy", "extrude", "scatter").
   Inspect the matched summaries (id, category, inputs/outputs, exposed_parms).
2. **Understand the match.** `recipe_read(recipe_id)` — look at the internal
   nodes, the `changed_params` on each (these encode the author's intent and
   conventions, e.g. `endcaptype=1` for closed tubes), and the `exposed_parms`
   list (the ONLY parms you may override).
3. **Rebuild.** `recipe_rebuild(recipe_id, parent_path, overrides={...})` —
   overrides keys must come from `exposed_parms`. The tool topologically orders
   nodes, applies params, wires inputs, and runs a built-in structural verify.
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
