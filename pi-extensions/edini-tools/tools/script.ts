// pi-extensions/edini-tools/tools/script.ts
// VEX, Python, and HDA tool definitions.

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

export const houdiniRunPython = {
  name: "houdini_run_python",
  label: "Run Houdini Python",
  description:
    "Execute arbitrary Python code in the Houdini environment. This is not sandboxed; prefer dedicated tools or houdini_run_python_sandbox when available.",
  promptSnippet: "Run Python code in Houdini",
  promptGuidelines: [
    "Use houdini_run_python only when dedicated tools and the sandbox cannot accomplish the task.",
    "For procedural modeling, prefer houdini_run_python_sandbox so failed cooks preserve diagnostics and do not overwrite live scene nodes.",
  ],
  parameters: Type.Object({
    code: Type.String({ description: "Python code to execute" }),
  }),
  async execute(_toolCallId: string, params: { code: string }) {
    return forwardTool("houdini_run_python", params);
  },
};

export const houdiniRunVex = {
  name: "houdini_run_vex",
  label: "Run VEX Code",
  description:
    "Execute VEX code by creating a temporary Attribute Wrangle node in /obj.",
  promptSnippet: "Run VEX code in a temporary Attribute Wrangle",
  parameters: Type.Object({
    code: Type.String({ description: "VEX snippet to run" }),
    node_path: Type.Optional(
      Type.String({ description: "Optional input node path for the wrangle" })
    ),
    attrib_name: Type.Optional(
      Type.String({ description: "Attribute name to create/write, default 'result'" })
    ),
  }),
  async execute(
    _toolCallId: string,
    params: { code: string; node_path?: string; attrib_name?: string }
  ) {
    return forwardTool("houdini_run_vex", params);
  },
};

export const houdiniCreateHda = {
  name: "houdini_create_hda",
  label: "Create HDA",
  description: "Create a digital asset (HDA) from an existing node.",
  promptSnippet: "Create HDA from a node",
  parameters: Type.Object({
    node_path: Type.String({
      description: "Path of the node to convert to HDA",
    }),
    hda_name: Type.String({ description: "Internal name for the HDA" }),
    hda_label: Type.Optional(
      Type.String({ description: "Display label for the HDA" })
    ),
  }),
  async execute(
    _toolCallId: string,
    params: { node_path: string; hda_name: string; hda_label?: string }
  ) {
    return forwardTool("houdini_create_hda", params);
  },
};

export const houdiniGetHdaInfo = {
  name: "houdini_get_hda_info",
  label: "Get HDA Info",
  description: "Get information about a loaded HDA definition.",
  promptSnippet: "Get HDA definition info by name",
  parameters: Type.Object({
    hda_name: Type.String({ description: "HDA internal name" }),
  }),
  async execute(_toolCallId: string, params: { hda_name: string }) {
    return forwardTool("houdini_get_hda_info", params);
  },
};

export const scriptTools = [
  houdiniRunPython,
  houdiniRunVex,
  houdiniCreateHda,
  houdiniGetHdaInfo,
];
