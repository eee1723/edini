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

export const queryTools = [
  houdiniSearchNodes,
  houdiniGetHelp,
  houdiniGetNodeInfo,
  houdiniInspectGeo,
];
