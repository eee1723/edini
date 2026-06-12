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
  promptGuidelines: [
    "Use houdini_get_scene_info at the start of a task when you need to understand the current scene structure. The user may also have injected context about the current network and selected nodes in their message.",
  ],
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

export const houdiniSetParamsBatch = {
  name: "houdini_set_params_batch",
  label: "Set Multiple Houdini Parameters",
  description:
    "Set multiple parameters on a single Houdini node in one call. Much faster than calling houdini_set_param repeatedly.",
  promptSnippet: "Set multiple parameters on a Houdini node at once",
  promptGuidelines: [
    "Use houdini_set_params_batch when setting 3+ parameters on the same node — it's significantly faster than individual calls.",
  ],
  parameters: Type.Object({
    node_path: Type.String({ description: "Full path of the node" }),
    params: Type.Record(Type.String(), Type.Unknown(), {
      description: "Map of parameter names to values",
    }),
  }),
  async execute(
    _toolCallId: string,
    params: { node_path: string; params: Record<string, unknown> }
  ) {
    return forwardTool("houdini_set_params_batch", params);
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
  promptGuidelines: [
    "After creating or connecting nodes, use houdini_layout_nodes to organize the network graph so the user can see the structure clearly.",
  ],
  parameters: Type.Object({
    parent_path: Type.Optional(
      Type.String({ description: "Parent path, default /obj" })
    ),
  }),
  async execute(_toolCallId: string, params: { parent_path?: string }) {
    return forwardTool("houdini_layout_nodes", params);
  },
};

export const houdiniGetSelection = {
  name: "houdini_get_selection",
  label: "Get Selected Nodes",
  description:
    "Get the list of nodes currently selected by the user in Houdini. " +
    "Returns each node's name, full path, and type. Use this when the user " +
    "refers to 'this node' or 'the selected node' without specifying a path.",
  promptSnippet: "Get user's currently selected Houdini nodes",
  promptGuidelines: [
    "When the user says 'modify this node' or 'change the selected', use houdini_get_selection to find which nodes they mean. The user's message may also contain [Current Houdini Context] with selected nodes.",
  ],
  parameters: Type.Object({}),
  async execute(_toolCallId: string, _params: {}) {
    return forwardTool("houdini_get_selection", {});
  },
};

export const houdiniCheckErrors = {
  name: "houdini_check_errors",
  label: "Check Houdini Node Errors",
  description:
    "Check for errors and warnings on a specific node or across the entire scene. " +
    "Returns error messages, warning messages, and node paths. Essential for debugging.",
  promptSnippet: "Check Houdini node errors (single node or full scene)",
  promptGuidelines: [
    "When the user reports unexpected behavior (blank viewport, missing geometry, render issues), use houdini_check_errors to scan for node errors before making changes.",
  ],
  parameters: Type.Object({
    node_path: Type.Optional(
      Type.String({ description: "Optional: check a specific node. Omit to scan entire scene." })
    ),
  }),
  async execute(
    _toolCallId: string,
    params: { node_path?: string }
  ) {
    return forwardTool("houdini_check_errors", params);
  },
};

export const houdiniSetDisplayFlag = {
  name: "houdini_set_display_flag",
  label: "Set Display Flag",
  description:
    "Set a node as the display/render flag node, making it the one shown in the viewport. " +
    "Use this after creating geometry to ensure the user sees your result.",
  promptSnippet: "Set a node to be displayed in the viewport",
  promptGuidelines: [
    "After creating or modifying geometry nodes, use houdini_set_display_flag on the final output node so the user sees the result in the viewport.",
  ],
  parameters: Type.Object({
    node_path: Type.String({ description: "Full path of the node to display" }),
  }),
  async execute(_toolCallId: string, params: { node_path: string }) {
    return forwardTool("houdini_set_display_flag", params);
  },
};

export const houdiniCaptureViewport = {
  name: "houdini_capture_viewport",
  label: "Capture Houdini Viewport",
  description:
    "Capture the active Houdini scene viewport as an image file. " +
    "Saves a PNG screenshot of what the user currently sees in the viewport. " +
    "Use this after creating or modifying nodes to verify visual results. " +
    "Combine with describe_image to let the vision model check the output.",
  promptSnippet: "Capture Houdini viewport screenshot to a PNG file",
  promptGuidelines: [
    "After making visual changes in Houdini, use houdini_capture_viewport to take a screenshot, then use describe_image on the saved file to verify the result matches expectations. This is especially useful when the user provides a reference image.",
    "Prefer houdini_capture_viewport_safe for new visual verification. houdini_capture_viewport is backward-compatible and should be used only when safe capture is unavailable.",
  ],
  parameters: Type.Object({
    filepath: Type.String({
      description: "Output file path for the screenshot (e.g. 'screenshots/viewport_001.png')",
    }),
  }),
  async execute(_toolCallId: string, params: { filepath: string }) {
    return forwardTool("houdini_capture_viewport", params);
  },
};

export const houdiniCaptureNetwork = {
  name: "houdini_capture_network",
  label: "Capture Houdini Node Network",
  description:
    "Capture the Houdini node network editor as an image file. " +
    "Saves a PNG screenshot showing the node graph at the specified parent path. " +
    "Use this to verify node layouts, connections, and network structure.",
  promptSnippet: "Capture Houdini node network screenshot to a PNG file",
  promptGuidelines: [
    "Use houdini_capture_network to take screenshots of the node graph for documentation or to verify that nodes are connected correctly. Combine with describe_image for visual verification.",
  ],
  parameters: Type.Object({
    filepath: Type.String({
      description: "Output file path for the screenshot (e.g. 'screenshots/network_001.png')",
    }),
    parent_path: Type.Optional(
      Type.String({ description: "Network path to capture, default /obj" })
    ),
  }),
  async execute(
    _toolCallId: string,
    params: { filepath: string; parent_path?: string }
  ) {
    return forwardTool("houdini_capture_network", params);
  },
};

export const sceneTools = [
  houdiniGetSceneInfo,
  houdiniCreateNode,
  houdiniDeleteNode,
  houdiniConnectNodes,
  houdiniSetParam,
  houdiniSetParamsBatch,
  houdiniGetParam,
  houdiniListNodes,
  houdiniLayoutNodes,
  houdiniGetSelection,
  houdiniCheckErrors,
  houdiniSetDisplayFlag,
  houdiniCaptureViewport,
  houdiniCaptureNetwork,
];
