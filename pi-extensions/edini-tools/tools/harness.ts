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
    "For sandbox executions, diagnostics are already included in the sandbox result — separate diagnostics call is only needed for non-sandbox nodes.",
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
    "ALWAYS use houdini_run_python_sandbox for initial procedural asset generation instead of raw houdini_run_python.",
    "The sandbox provides a Python SOP context — use hou.pwd() and node.geometry() directly in your code.",
    "The sandbox result includes diagnostics and structural_checks (has_geometry, point_count, bounds_nonzero) — no need for separate inspect_geo or check_errors calls.",
    "Do not delete a failed sandbox before reviewing the diagnostics in the result.",
    "NEVER set commit_on_success=true on the first sandbox execution. Always capture (4-view quad) and verify with describe_image using the 3D verification prompt BEFORE committing.",
    "If describe_image reports critical or major defects (wrong orientation, missing components, detail_level < 3), fix the specific issue and re-verify — do NOT commit until verification passes.",
    "Before using unfamiliar node types in your code, PROBE their parameter names first (create + inspect + destroy).",
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
      Type.Record(Type.String(), Type.Unknown())
    ),
  }),
  async execute(
    _toolCallId: string,
    params: { node_path: string; expected?: Record<string, unknown> }
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

export const houdiniCaptureReview = {
  name: "houdini_capture_review",
  label: "Capture Procedural Review",
  description:
    "Capture a multi-view, multi-frame review contact sheet for procedural assets. " +
    "Supports 4-view (perspective+top+front+right) for complete shape verification, " +
    "frame ranges for time-based review (e.g. growth animation), and combinations of both.",
  promptSnippet: "Capture a review contact sheet of the generated asset",
  promptGuidelines: [
    "Use houdini_capture_review after generating a procedural asset to verify it from multiple angles.",
    "For procedural assets: ALWAYS use views=['perspective','top','front','right'] for complete structural verification.",
    "For animated/growth assets: use frames=[1,10,20,30] to get a time contact sheet.",
    "Always pass target_path — it automatically isolates the target and frames each view.",
    "The output is a single concatenated PNG — call describe_image with the 3D verification prompt on it.",
    "After describe_image, if VERDICT is 'fix': repair the specific defect, re-capture, and re-verify (up to 3 cycles).",
    "Do NOT skip the describe_image step. Do NOT commit before visual verification passes.",
    "If you only need a single view, use views=['perspective'].",
  ],
  parameters: Type.Object({
    filepath: Type.String({
      description: "Output file path for the contact sheet PNG",
    }),
    target_path: Type.Optional(
      Type.String({ description: "Node path to frame and isolate. The generated asset's display/output node." })
    ),
    views: Type.Optional(
      Type.Array(Type.String(), {
        description: "View angles to capture. Default: ['perspective']. Use ['perspective','top','front','right'] for 2×2 quad-view.",
      })
    ),
    frames: Type.Optional(
      Type.Array(Type.Number(), {
        description: "Frame numbers to capture. Default: [1]. Use [1,10,20,30] for a time-lapse contact sheet.",
      })
    ),
    columns: Type.Optional(
      Type.Number({ description: "Grid columns. 0 = auto (best-fit). Default: 0." })
    ),
    shading_mode: Type.Optional(
      Type.String({ description: "Viewport shading: 'smooth', 'wire', 'flat'. Default: 'smooth'." })
    ),
    home_target: Type.Optional(
      Type.Boolean({ description: "Frame the target before each view capture. Default: true." })
    ),
    resolution: Type.Optional(
      Type.Tuple([Type.Number(), Type.Number()], {
        description: "Capture resolution (width, height) per cell. Default: viewport native. Use (960, 540) for consistent quad-view cells."
      })
    ),
  }),
  async execute(
    _toolCallId: string,
    params: {
      filepath: string;
      target_path?: string;
      views?: string[];
      frames?: number[];
      columns?: number;
      shading_mode?: string;
      home_target?: boolean;
    }
  ) {
    return forwardTool("houdini_capture_review", params);
  },
};

export const harnessTools = [
  houdiniCollectDiagnostics,
  houdiniRunPythonSandbox,
  houdiniVerifyAsset,
  houdiniCommitSandbox,
  houdiniDiscardSandbox,
  houdiniCaptureReview,
];
