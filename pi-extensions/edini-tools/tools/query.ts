// pi-extensions/edini-tools/tools/query.ts
// Query, search, and inspection tool definitions.

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

export const houdiniSearchNodes = {
  name: "houdini_search_nodes",
  label: "Search Houdini Nodes",
  description:
    "Search for available Houdini node types by keyword across all categories (Sop, Dop, Vop, etc.).",
  promptSnippet: "Search Houdini node types by keyword",
  promptGuidelines: [
    "When the user asks to create an effect (smoke, fire, water, destruction, etc.), use houdini_search_nodes first to find available node types before creating anything.",
  ],
  parameters: Type.Object({
    keyword: Type.String({ description: "Search keyword" }),
  }),
  async execute(_toolCallId: string, params: { keyword: string }) {
    return forwardTool("houdini_search_nodes", params);
  },
};

export const houdiniGetHelp = {
  name: "houdini_get_help",
  label: "Get Houdini Node Help",
  description: "Get help documentation for a Houdini node type.",
  promptSnippet: "Get Houdini node type help documentation",
  parameters: Type.Object({
    node_type_name: Type.String({ description: "Node type name" }),
  }),
  async execute(_toolCallId: string, params: { node_type_name: string }) {
    return forwardTool("houdini_get_help", params);
  },
};

export const houdiniNodeParms = {
  name: "houdini_node_parms",
  label: "Query Node Type Parameters",
  description:
    "Look up the authoritative parameter list (names/types/menu tokens/defaults) for a Houdini node TYPE (e.g. 'normal', 'attribpromote', 'copytopoints'). " +
    "Use this BEFORE writing postprocess params in a recipe so you never guess a parm name — the catalogue is generated from the real Houdini install and is always accurate (parm names change across Houdini versions, e.g. Normal SOP's cusp-angle parm).",
  promptSnippet: "Look up a node type's real parameter names",
  promptGuidelines: [
    "Use this to get exact parm names/menu tokens for a SOP before writing recipe postprocess params — do NOT rely on memorized names, which go stale across Houdini versions.",
    "Returns {name,type,label,default,menu_items?,min?,max?} per parm. source='manifest' means the pinned catalogue (fast, offline); source='live' means it queried the running Houdini because the type wasn't in the catalogue.",
  ],
  parameters: Type.Object({
    node_type: Type.String({
      description: "Node type name (e.g. 'normal', 'copytopoints', 'attribpromote').",
    }),
    category: Type.Optional(
      Type.String({ description: "NodeType category. Default 'Sop'." })
    ),
  }),
  async execute(
    _toolCallId: string,
    params: { node_type: string; category?: string }
  ) {
    return forwardTool("houdini_node_parms", params);
  },
};

export const houdiniGetNodeInfo = {
  name: "houdini_get_node",
  label: "Get Houdini Node Info",
  description:
    "Get detailed information about a Houdini node: type, inputs, outputs, and all parameters with current values.",
  promptSnippet: "Get Houdini node details by path",
  parameters: Type.Object({
    node_path: Type.String({ description: "Full node path" }),
  }),
  async execute(_toolCallId: string, params: { node_path: string }) {
    return forwardTool("houdini_get_node", params);
  },
};

export const houdiniInspectGeo = {
  name: "houdini_inspect_geo",
  label: "Inspect Houdini Geometry",
  description:
    "Inspect the geometry output of a SOP node: point/prim/vertex counts, attributes, and bounding box.",
  promptSnippet: "Inspect Houdini SOP node geometry",
  parameters: Type.Object({
    node_path: Type.String({ description: "SOP node path to inspect" }),
  }),
  async execute(_toolCallId: string, params: { node_path: string }) {
    return forwardTool("houdini_inspect_geo", params);
  },
};

export const houdiniGeometryInventory = {
  name: "houdini_geometry_inventory",
  label: "Geometry Component Inventory",
  description:
    "List every distinct @component_id on a node's geometry with its prim/point counts, bounds, and relative size (size_fraction). " +
    "The authoritative way to confirm which components exist and flag small ones (size_fraction < 0.08 need a close-up capture).",
  promptSnippet: "List per-component_id geometry inventory",
  promptGuidelines: [
    "Authoritative for 'is component X present?': a component_id with prim_count > 0 EXISTS — do not rebuild it even if a screenshot looks empty.",
    "Flag components with size_fraction < 0.08 as SMALL — they exist but need houdini_capture_component_detail before vision can judge them.",
    "Returns an inventory_text block suitable for pasting into a describe_image message so vision cross-validates presence/absence.",
  ],
  parameters: Type.Object({
    node_path: Type.String({
      description: "SOP node whose geometry contains the @component_id prims",
    }),
    max_components: Type.Optional(
      Type.Number({ description: "Cap on components returned. Default 60." })
    ),
  }),
  async execute(
    _toolCallId: string,
    params: { node_path: string; max_components?: number }
  ) {
    return forwardTool("houdini_geometry_inventory", params);
  },
};

export const houdiniInspectGeometryHealth = {
  name: "houdini_inspect_geometry_health",
  label: "Inspect Geometry Health",
  description:
    "Check a SOP node's geometry for orphan points, open/stray curves, degenerate faces, non-manifold edges, open boundary edges, and coincident points. " +
    "Returns overall_ok plus per-check fix recommendations. MANDATORY layer-1 verification before orientation/visual checks.",
  promptSnippet: "Check geometry health (orphan/degenerate/non-manifold)",
  promptGuidelines: [
    "MANDATORY before orientation/visual verification. Skipping it lets non-manifold edges / degenerate faces flow into Boolean/Sweep and silently corrupt results.",
    "overall_ok must be true before proceeding. Each failed check comes with a concrete fix recommendation.",
    "open_boundary_edges is EXPECTED for open surfaces (terrain, a single panel) — only a defect for assets that should be closed.",
  ],
  parameters: Type.Object({
    node_path: Type.String({ description: "SOP node whose geometry to health-check" }),
    degenerate_area_eps: Type.Optional(
      Type.Number({ description: "Min face area to be non-degenerate. Default 1e-7." })
    ),
    coincident_eps: Type.Optional(
      Type.Number({ description: "Min distance between distinct points. Default 1e-6." })
    ),
  }),
  async execute(
    _toolCallId: string,
    params: {
      node_path: string;
      degenerate_area_eps?: number;
      coincident_eps?: number;
    }
  ) {
    return forwardTool("houdini_inspect_geometry_health", params);
  },
};

export const queryTools = [
  houdiniSearchNodes,
  houdiniGetHelp,
  houdiniNodeParms,
  houdiniGetNodeInfo,
  houdiniInspectGeo,
  houdiniGeometryInventory,
  houdiniInspectGeometryHealth,
];
