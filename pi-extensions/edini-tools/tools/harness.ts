// pi-extensions/edini-tools/tools/harness.ts
// Procedural harness tool definitions.

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

export const houdiniCollectDiagnostics = {
  name: "houdini_collect_diagnostics",
  label: "Collect Houdini Diagnostics",
  description:
    "Collect cook errors, parameter values, geometry summaries, and node context for a Houdini node.",
  promptSnippet: "Collect diagnostics for a Houdini node",
  promptGuidelines: [
    "Use houdini_collect_diagnostics after a failed cook, blank output, or unexpected procedural result before changing strategy or deleting nodes.",
  ],
  parameters: Type.Object({
    node_path: Type.String({ description: "Full path of the node to inspect" }),
    include_geometry: Type.Optional(
      Type.Boolean({ description: "Include geometry summaries when available" })
    ),
    include_parms: Type.Optional(
      Type.Boolean({ description: "Include node parameter values when available" })
    ),
  }),
  async execute(
    _toolCallId: string,
    params: {
      node_path: string;
      include_geometry?: boolean;
      include_parms?: boolean;
    }
  ) {
    return forwardTool("houdini_collect_diagnostics", params);
  },
};

export const houdiniRunPythonSandbox = {
  name: "houdini_run_python_sandbox",
  label: "Run Houdini Python Sandbox",
  description:
    "Execute Houdini Python code inside a procedural sandbox before committing changes to the live scene.",
  promptSnippet: "Run Python code in a Houdini procedural sandbox",
  promptGuidelines: [
    "Create assets in a sandbox first, verify them, then commit the sandbox when the result is correct.",
    "Do not delete a failed sandbox before collecting diagnostics from the failed result.",
  ],
  parameters: Type.Object({
    code: Type.String({ description: "Python code to execute in the sandbox" }),
    sandbox_name: Type.Optional(
      Type.String({ description: "Optional name for the sandbox root" })
    ),
    commit_on_success: Type.Optional(
      Type.Boolean({ description: "Commit the sandbox automatically when execution succeeds" })
    ),
    delete_on_failure: Type.Optional(
      Type.Boolean({ description: "Delete the sandbox automatically when execution fails" })
    ),
  }),
  async execute(
    _toolCallId: string,
    params: {
      code: string;
      sandbox_name?: string;
      commit_on_success?: boolean;
      delete_on_failure?: boolean;
    }
  ) {
    return forwardTool("houdini_run_python_sandbox", params);
  },
};

export const houdiniVerifyAsset = {
  name: "houdini_verify_asset",
  label: "Verify Houdini Asset",
  description:
    "Verify a Houdini asset or node against expected procedural output and diagnostics.",
  promptSnippet: "Verify a Houdini asset by node path",
  parameters: Type.Object({
    node_path: Type.String({ description: "Full path of the asset or node to verify" }),
    expected: Type.Optional(
      Type.Unknown({ description: "Optional expected properties or verification criteria" })
    ),
  }),
  async execute(
    _toolCallId: string,
    params: { node_path: string; expected?: unknown }
  ) {
    return forwardTool("houdini_verify_asset", params);
  },
};

export const houdiniCommitSandbox = {
  name: "houdini_commit_sandbox",
  label: "Commit Houdini Sandbox",
  description:
    "Commit a verified procedural sandbox into the live Houdini scene with a final node name.",
  promptSnippet: "Commit a verified Houdini sandbox",
  parameters: Type.Object({
    sandbox_root_path: Type.String({ description: "Full path of the sandbox root node" }),
    final_name: Type.String({ description: "Final node name to use after committing" }),
    replace_existing: Type.Optional(
      Type.Boolean({ description: "Replace an existing node with the same final name" })
    ),
  }),
  async execute(
    _toolCallId: string,
    params: {
      sandbox_root_path: string;
      final_name: string;
      replace_existing?: boolean;
    }
  ) {
    return forwardTool("houdini_commit_sandbox", params);
  },
};

export const houdiniDiscardSandbox = {
  name: "houdini_discard_sandbox",
  label: "Discard Houdini Sandbox",
  description: "Discard a procedural sandbox after it is no longer needed.",
  promptSnippet: "Discard a Houdini procedural sandbox",
  parameters: Type.Object({
    sandbox_root_path: Type.String({ description: "Full path of the sandbox root node" }),
  }),
  async execute(_toolCallId: string, params: { sandbox_root_path: string }) {
    return forwardTool("houdini_discard_sandbox", params);
  },
};

export const houdiniCaptureViewportSafe = {
  name: "houdini_capture_viewport_safe",
  label: "Capture Houdini Viewport Safely",
  description:
    "Capture a Houdini viewport image using the procedural harness safe capture path.",
  promptSnippet: "Safely capture a Houdini viewport screenshot to a file",
  promptGuidelines: [
    "Use houdini_capture_viewport_safe for visual verification after creating or changing procedural assets.",
    "If safe capture fails, report the failure and diagnostics instead of trying Qt widget or viewport internals through Python.",
  ],
  parameters: Type.Object({
    filepath: Type.String({
      description: "Output file path for the screenshot, usually a PNG file",
    }),
    frame: Type.Optional(
      Type.Number({ description: "Optional frame to capture before saving the screenshot" })
    ),
    home_viewport: Type.Optional(
      Type.Boolean({ description: "Home the viewport before capturing" })
    ),
  }),
  async execute(
    _toolCallId: string,
    params: { filepath: string; frame?: number; home_viewport?: boolean }
  ) {
    return forwardTool("houdini_capture_viewport_safe", params);
  },
};

export const harnessTools = [
  houdiniCollectDiagnostics,
  houdiniRunPythonSandbox,
  houdiniVerifyAsset,
  houdiniCommitSandbox,
  houdiniDiscardSandbox,
  houdiniCaptureViewportSafe,
];
