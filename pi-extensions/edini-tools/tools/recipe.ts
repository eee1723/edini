// pi-extensions/edini-tools/tools/recipe.ts
// Recipe library tool definitions — query, read, capture, and rebuild subnet recipes.
//
// A *recipe* is a JSON serialization of a Houdini subnet's internal node
// network (nodes, connections, changed parameters) plus the subnet's Notes as
// metadata. The library lives under recipes/ at the project root. The agent
// queries the index (recipe_list), reads a recipe to understand it
// (recipe_read), and rebuilds it deterministically with parameter overrides
// (recipe_rebuild) — preferring reuse over hand-building nodes.

import { Type } from "typebox";

const TOOL_PORT = parseInt(process.env.EDINI_TOOL_PORT || "9876", 10);
const TOOL_URL = `http://127.0.0.1:${TOOL_PORT}/execute`;

async function forwardTool(toolName: string, params: Record<string, unknown>) {
  const response = await fetch(TOOL_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tool: toolName, params }),
  });
  const result = await response.json();
  return {
    content: [{ type: "text" as const, text: JSON.stringify(result, null, 2) }],
    details: result,
  };
}

export const recipeList = {
  name: "recipe_list",
  label: "Query Recipe Library",
  description:
    "Search the recipe library index for subnet recipes that match a keyword or category. " +
    "Each recipe is a pre-built, pre-validated Houdini subnet (e.g. tube_along_curve, copy_to_points) " +
    "that can be rebuilt deterministically with recipe_rebuild. ALWAYS call this before hand-building " +
    "nodes — a matching recipe is faster and more reliable than authoring from scratch.",
  promptSnippet: "Search the recipe library for a reusable subnet recipe",
  promptGuidelines: [
    "Call recipe_list FIRST when the user wants geometry — a matching recipe rebuilds deterministically and avoids LLM node-authoring errors.",
    "Matching is case-insensitive substring over the recipe id, function description, category, and exposed parm names. Pass a concise intent keyword (e.g. 'tube', 'copy', 'extrude').",
    "The returned summaries include inputs/outputs counts and exposed_parms — use these to judge fit before reading the full recipe.",
    "If no recipe matches, fall back to houdini_run_python_sandbox or houdini_create_node; after hand-building a reusable pattern, consider recipe_capture to add it to the library.",
  ],
  parameters: Type.Object({
    query: Type.Optional(
      Type.String({
        description: "Keyword to match against recipe id/function/category/tree_path/parms (empty = list all).",
      })
    ),
    category: Type.Optional(
      Type.String({
        description: "Filter by category (tube|extrude|copy|boolean|postprocess|deform|misc).",
      })
    ),
    kind: Type.Optional(
      Type.String({
        description: "Filter by kind: 'network' (node-network recipes) or 'vex' (VEX-snippet recipes).",
      })
    ),
  }),
  async execute(_toolCallId: string, params: { query?: string; category?: string; kind?: string }) {
    return forwardTool("recipe_list", params);
  },
};

export const recipeRead = {
  name: "recipe_read",
  label: "Read Recipe Details",
  description:
    "Read the full recipe JSON for one subnet recipe: its internal node network (which nodes, " +
    "how they connect, which parameters were changed from type defaults), its Notes metadata, " +
    "and its exposed parameters (the top-level parms you may override when rebuilding). " +
    "Call this after recipe_list to understand a recipe before rebuilding it.",
  promptSnippet: "Read the full recipe to understand its node network and exposed params",
  promptGuidelines: [
    "The changed_params on each node are the parameters that matter — they encode the subnet author's intent and the conventions (e.g. endcaptype=1 for closed tubes).",
    "exposed_parms are the ONLY parameters you may override on rebuild — do not target internal node parms directly.",
    "inputs/outputs use relative names (not absolute paths) so the recipe rebuilds identically in any scene.",
  ],
  parameters: Type.Object({
    recipe_id: Type.String({ description: "Recipe id (subnet name), e.g. tube_along_curve" }),
  }),
  async execute(_toolCallId: string, params: { recipe_id: string }) {
    return forwardTool("recipe_read", params);
  },
};

export const recipeCapture = {
  name: "recipe_capture",
  label: "Capture Subnet as Recipe",
  description:
    "Serialize a subnet's internal node network into a reusable recipe JSON, added to the library. " +
    "Reads each child node's type, connections (as relative names), and changed parameters (vs type " +
    "defaults), plus the subnet's Notes as metadata. The subnet's Notes MUST be non-empty and descriptive " +
    "(use the '功能：...' convention and list key params under '重要参数：'). Use this to grow the library " +
    "from subnets you've hand-built.",
  promptSnippet: "Capture a hand-built subnet into the recipe library",
  promptGuidelines: [
    "The subnet's Notes is the MANDATORY metadata source — capture fails on empty or placeholder Notes. Write '功能：<what it does>' plus '重要参数：<comma-separated internal parm names>' before capturing.",
    "Capture records only parameters CHANGED from the type default (plus any listed under 重要参数), keeping recipes lean — the author's intent is what survives.",
    "After capture the index is rebuilt automatically; the recipe is immediately queryable via recipe_list.",
  ],
  parameters: Type.Object({
    subnet_path: Type.String({ description: "Full path of the subnet to capture, e.g. /obj/tube_along_curve" }),
  }),
  async execute(_toolCallId: string, params: { subnet_path: string }) {
    return forwardTool("recipe_capture", params);
  },
};

export const recipeCaptureTree = {
  name: "recipe_capture_tree",
  label: "Capture All Leaf Recipes Under a Tree",
  description:
    "Recursively capture every leaf subnet under a root into the recipe library. " +
    "Walks the tree: container subnets (whose children are all subnets) are descended into; " +
    "leaf subnets (whose children include real SOP nodes like curve/sweep/wrangle) are captured. " +
    "Each leaf gets a tree-path-based recipe_id (e.g. 'Procedural_Modeling.Base_Sweep') so " +
    "same-named leaves in different branches never collide. VEX wrangle snippets are extracted " +
    "into vex_snippets (kind='vex'); output/stashed nodes are ignored. Empty Notes are auto-filled. " +
    "Use this to ingest a hand-built category tree (e.g. /obj/sopnet1) in one call.",
  promptSnippet: "Capture all leaf recipes under a category tree root",
  promptGuidelines: [
    "Pass the root of the category tree (e.g. /obj/sopnet1), NOT an individual leaf. The tool recurses.",
    "Container vs leaf is decided by node-type composition: all-subnet children = container; any SOP child = leaf.",
    "recipe_ids become tree paths (e.g. Procedural_Modeling.Base_Sweep) — use these exact ids in recipe_read/recipe_rebuild.",
    "Each captured entry has 'kind' ('network' or 'vex') and a 'warnings' list (auto-notes, manifest gaps, etc.).",
    "Check 'skipped' in the result for any leaves that failed (rare — only if Notes rejects even auto-fill).",
  ],
  parameters: Type.Object({
    root_path: Type.String({
      description: "Root subnet path to recurse from, e.g. /obj/sopnet1",
    }),
  }),
  async execute(_toolCallId: string, params: { root_path: string }) {
    return forwardTool("recipe_capture_tree", params);
  },
};

export const recipeRebuild = {
  name: "recipe_rebuild",
  label: "Rebuild Subnet from Recipe",
  description:
    "Rebuild a subnet's node network at a target parent from its recipe, deterministically. " +
    "Creates a subnet container, topologically creates the inner nodes, applies changed parameters, " +
    "wires inputs, applies exposed-parameter overrides, and runs a built-in structural verification. " +
    "Prefer this over hand-authoring nodes whenever a matching recipe exists.",
  promptSnippet: "Rebuild a recipe's subnet network with parameter overrides",
  promptGuidelines: [
    "Pass overrides for exposed_parms only (see recipe_read output) — never try to set internal node parms directly.",
    "The built-in verify step reports mismatches; if verify fails, read the mismatches and the warnings rather than ignoring them.",
    "The rebuilt subnet is fully editable (it is NOT a locked HDA) — you can inspect_health, verify_orientation, and commit_sandbox on it like any hand-built network.",
    "For heavy post-build verification (geometry health, orientation, inventory), use the shared inspect_health / verify_orientation / geometry_inventory tools on the rebuilt path.",
  ],
  parameters: Type.Object({
    recipe_id: Type.String({ description: "Recipe id to rebuild, e.g. tube_along_curve" }),
    parent_path: Type.String({ description: "Where to create the rebuilt subnet, e.g. /obj" }),
    name: Type.Optional(
      Type.String({ description: "Name for the rebuilt subnet (defaults to <recipe_id>_1)" })
    ),
    overrides: Type.Optional(
      Type.Record(Type.String(), Type.Unknown(), {
        description:
          "Map of exposed_parm name → value to apply on rebuild (e.g. {radius: 0.1, segments: 24}). " +
          "Only keys present in the recipe's exposed_parms are honored.",
      })
    ),
  }),
  async execute(
    _toolCallId: string,
    params: { recipe_id: string; parent_path: string; name?: string; overrides?: Record<string, unknown> }
  ) {
    return forwardTool("recipe_rebuild", params);
  },
};

export const recipeTreeScan = {
  name: "recipe_tree_scan",
  label: "Scan Recipe Tree",
  description:
    "Read-only scan of a subnet tree (the recipe manager HDA or any root), returning a nested " +
    "structure of containers and leaf recipes WITHOUT writing any files. Use this to browse what " +
    "recipes exist in the live Houdini scene before deciding which to capture/rebuild.",
  promptSnippet: "Browse the live recipe tree without capturing",
  parameters: Type.Object({
    root_path: Type.String({ description: "Root node path to scan, e.g. /obj/edini_recipe_manager" }),
  }),
  async execute(_toolCallId: string, params: { root_path: string }) {
    return forwardTool("recipe_tree_scan", params);
  },
};

export const recipeManagerCreate = {
  name: "recipe_manager_create",
  label: "Create Recipe Manager HDA",
  description:
    "Create the main edini_recipe_manager HDA (unlocked contents) with an initial procedural_modeling " +
    "category container. Call once to bootstrap the recipe library structure. The HDA holds the " +
    "subnet recipe tree that the dashboard panel and recipe tools operate on.",
  promptSnippet: "Create the recipe manager HDA",
  parameters: Type.Object({
    parent_path: Type.Optional(Type.String({ description: "Where to create it (default /obj)" })),
    name: Type.Optional(Type.String({ description: "HDA node name (default edini_recipe_manager)" })),
  }),
  async execute(_toolCallId: string, params: { parent_path?: string; name?: string }) {
    return forwardTool("recipe_manager_create", params);
  },
};

export const recipeSetNotes = {
  name: "recipe_set_notes",
  label: "Set Recipe Notes",
  description:
    "Write Notes (comment) back to a recipe subnet node, after validating non-empty/non-placeholder. " +
    "Notes is the recipe's metadata source (function / important params / avoid). " +
    "Use after editing a subnet's Notes in the dashboard to persist it.",
  promptSnippet: "Write validated Notes to a recipe subnet",
  parameters: Type.Object({
    node_path: Type.String({ description: "Full path of the subnet node" }),
    notes: Type.String({ description: "The Notes text to write" }),
  }),
  async execute(_toolCallId: string, params: { node_path: string; notes: string }) {
    return forwardTool("recipe_set_notes", params);
  },
};

export const recipeTools = [
  recipeList, recipeRead, recipeCapture, recipeCaptureTree, recipeRebuild,
  recipeTreeScan, recipeManagerCreate, recipeSetNotes,
];
