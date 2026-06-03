// pi-extensions/edini-tools/tools/scene.ts
// Scene and node manipulation tool definitions.
// These are proxy tools — execution is forwarded to Houdini via HTTP.

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

export const houdiniGetSceneInfo = {
  name: "houdini_get_scene_info",
  label: "Get Houdini Scene Info",
  description:
    "Get an overview of the current Houdini scene: hip file name, root children, total node count, current path, and /obj children.",
  promptSnippet: "Get Houdini scene overview",
  parameters: Type.Object({}),
  async execute(_toolCallId: string, _params: {}) {
    return forwardTool("houdini_get_scene_info", {});
  },
};

export const houdiniCreateNode = {
  name: "houdini_create_node",
  label: "Create Houdini Node",
  description:
    "Create a new node in the Houdini scene. Specify node type, optional name, and optional parent path (default /obj).",
  promptSnippet: "Create a Houdini node by type, optional name, and parent path",
  parameters: Type.Object({
    node_type: Type.String({ description: "Node type name, e.g. 'geo', 'null', 'file'" }),
    name: Type.Optional(Type.String({ description: "Optional node name" })),
    parent_path: Type.Optional(
      Type.String({ description: "Parent network path, default /obj" })
    ),
  }),
  async execute(
    _toolCallId: string,
    params: { node_type: string; name?: string; parent_path?: string }
  ) {
    return forwardTool("houdini_create_node", params);
  },
};

export const houdiniDeleteNode = {
  name: "houdini_delete_node",
  label: "Delete Houdini Node",
  description: "Delete a node from the Houdini scene by its full path.",
  promptSnippet: "Delete a Houdini node by path",
  parameters: Type.Object({
    node_path: Type.String({ description: "Full path of the node to delete" }),
  }),
  async execute(_toolCallId: string, params: { node_path: string }) {
    return forwardTool("houdini_delete_node", params);
  },
};

export const houdiniConnectNodes = {
  name: "houdini_connect_nodes",
  label: "Connect Houdini Nodes",
  description: "Connect the output of one node to the input of another.",
  promptSnippet:
    "Connect from node to another node, optionally specifying input index",
  parameters: Type.Object({
    from_path: Type.String({ description: "Source node path" }),
    to_path: Type.String({ description: "Destination node path" }),
    input_index: Type.Optional(
      Type.Number({ description: "Input index on destination (0-based), default 0" })
    ),
  }),
  async execute(
    _toolCallId: string,
    params: { from_path: string; to_path: string; input_index?: number }
  ) {
    return forwardTool("houdini_connect_nodes", params);
  },
};

export const houdiniSetParam = {
  name: "houdini_set_param",
  label: "Set Houdini Parameter",
  description: "Set a parameter value on a Houdini node.",
  promptSnippet: "Set a Houdini node parameter to a value",
  parameters: Type.Object({
    node_path: Type.String({ description: "Full node path" }),
    param_name: Type.String({
      description: "Parameter name, e.g. 'tx', 'file'",
    }),
    value: Type.Unknown({
      description: "New value (number, string, or bool)",
    }),
  }),
  async execute(
    _toolCallId: string,
    params: { node_path: string; param_name: string; value: unknown }
  ) {
    return forwardTool("houdini_set_param", params);
  },
};

export const houdiniGetParam = {
  name: "houdini_get_param",
  label: "Get Houdini Parameter",
  description: "Read the current value of a parameter on a Houdini node.",
  promptSnippet: "Get Houdini node parameter value",
  parameters: Type.Object({
    node_path: Type.String({ description: "Full node path" }),
    param_name: Type.String({ description: "Parameter name" }),
  }),
  async execute(
    _toolCallId: string,
    params: { node_path: string; param_name: string }
  ) {
    return forwardTool("houdini_get_param", params);
  },
};

export const houdiniListNodes = {
  name: "houdini_list_nodes",
  label: "List Houdini Nodes",
  description:
    "List nodes under a parent path, optionally filtered by type.",
  promptSnippet:
    "List Houdini nodes under a path, optionally filtered by type",
  parameters: Type.Object({
    parent_path: Type.Optional(
      Type.String({ description: "Parent path, default /" })
    ),
    type_filter: Type.Optional(
      Type.String({ description: "Optional node type filter" })
    ),
  }),
  async execute(
    _toolCallId: string,
    params: { parent_path?: string; type_filter?: string }
  ) {
    return forwardTool("houdini_list_nodes", params);
  },
};

export const houdiniLayoutNodes = {
  name: "houdini_layout_nodes",
  label: "Layout Houdini Nodes",
  description: "Auto-layout nodes in a network.",
  promptSnippet: "Auto-layout Houdini nodes in a network",
  parameters: Type.Object({
    parent_path: Type.Optional(
      Type.String({ description: "Parent path, default /obj" })
    ),
  }),
  async execute(_toolCallId: string, params: { parent_path?: string }) {
    return forwardTool("houdini_layout_nodes", params);
  },
};

export const sceneTools = [
  houdiniGetSceneInfo,
  houdiniCreateNode,
  houdiniDeleteNode,
  houdiniConnectNodes,
  houdiniSetParam,
  houdiniGetParam,
  houdiniListNodes,
  houdiniLayoutNodes,
];
