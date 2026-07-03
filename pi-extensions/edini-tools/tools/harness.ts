// pi-extensions/edini-tools/tools/harness.ts
// Procedural harness tool definitions.

import { Type } from "typebox";

const TOOL_PORT = parseInt(process.env.EDINI_TOOL_PORT || "9876", 10);
const TOOL_URL = `http://127.0.0.1:${TOOL_PORT}/execute`;

// Visual verification gate — when off, the agent is told to rely on numeric
// evidence (health/inventory) instead of capture_review + describe_image.
// [VISUAL-VERIFY-GATE]
const VISUAL_VERIFY_ON = process.env.EDINI_VISUAL_VERIFICATION === "true";
const VERIFY_GUIDELINES = VISUAL_VERIFY_ON
  ? [
      "NEVER set commit_on_success=true on the first sandbox execution. Always capture (4-view quad) and verify with describe_image using the 3D verification prompt BEFORE committing.",
      "If describe_image reports critical or major defects (wrong orientation, missing components, STRUCTURAL_DETAIL < 3), fix the specific issue and re-verify — do NOT commit until verification passes or user approves.",
    ]
  : [
      "Visual verification (capture_review + describe_image) is disabled. Before committing, confirm success via numeric evidence: the sandbox result's diagnostics/structural_checks, houdini_inspect_geometry_health, and houdini_geometry_inventory. Do NOT call capture_review or describe_image.",
    ];

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
    "Execute Houdini Python code inside a procedural sandbox before committing changes to the live scene. " +
    "Two modes: single-SOP (default) for code that emits geometry from one Python SOP, and network_mode for building a multi-node modular network (body_generate + copytopoints + merge + OUT).",
  promptSnippet: "Run Python code in a Houdini procedural sandbox",
  promptGuidelines: [
    "Prefer the recipe library (recipe_list / recipe_rebuild) for geometry that matches an existing subnet recipe before writing custom Python — recipes are pre-validated and rebuild deterministically.",
    "Single-SOP mode (network_mode=false, default): the code runs as the cook body of ONE edini_generate Python SOP. It MUST NOT call createNode() on child SOPs — doing so triggers Houdini's 'Infinite recursion in evaluation' guard. Only emit geometry via node.geometry().createPoint()/createPolygon() on the cooking node.",
    "Network mode (network_mode=true): use when a recipe does not exist for the topology you need and building it from scratch is genuinely required. The code runs in the sandbox geo CONTAINER, so it can build a multi-node network: container.createNode('python','body_generate'), container.createNode('copytopoints',...), container.createNode('merge'), container.createNode('null','OUT').",
    "In network mode, use the injected `sandbox_root` variable (the geo container) or hou.node(sandbox_root_path) to create children, and end with a null/merge node named 'OUT' (or pass output_node_name). The harness auto-finds OUT, cooks it, and runs diagnostics on it.",
    "The sandbox result includes diagnostics and structural_checks (has_geometry, point_count, bounds_nonzero) — no need for separate inspect_geo or check_errors calls.",
    "Do not delete a failed sandbox before reviewing the diagnostics in the result.",
    ...VERIFY_GUIDELINES,
    "Before using unfamiliar node types in your code, look up their parameter names with houdini_node_parms(type) — do NOT guess or probe manually.",
    "EXECUTION-MODEL CONSTRAINTS (avoid the most common sandbox errors): " +
      "(1) Your code is wrapped in a function body, so do NOT use a top-level `return` statement — assign a result variable or use print() to surface info. " +
      "(2) ch()/hou.ch() RELATIVE paths (e.g. '../width') resolve relative to the SANDBOX container, NOT the live project node you're thinking of — so a sandbox cannot reference a Project HDA core's spare parms via '../width'. To reference an external node's parm, use an ABSOLUTE path: hou.ch('/obj/.../project_core/width'). " +
      "(3) The sandbox is ISOLATED — it cannot read or modify nodes elsewhere in the scene. To inspect or set params on a LIVE node (outside the sandbox), use houdini_get_node / houdini_set_param / houdini_collect_diagnostics directly — do NOT route that through the sandbox.",
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
    network_mode: Type.Optional(
      Type.Boolean({
        description:
          "Run the code in the sandbox geo CONTAINER so it can build a multi-node modular network (createNode on child SOPs, wire, OUT). REQUIRED for any multi-component modular asset. Default false (single Python SOP cook). NOTE: in single-SOP mode, createNode() inside the cook causes infinite-recursion errors — use network_mode=true whenever you need child nodes.",
      })
    ),
    output_node_name: Type.Optional(
      Type.String({
        description:
          "Name of the child node to cook + diagnose in network_mode (e.g. 'OUT'). If omitted, the harness finds a node named OUT/out, else the largest component_id-bearing node.",
      })
    ),
  }),
  async execute(
    _toolCallId: string,
    params: {
      code: string;
      sandbox_name?: string;
      commit_on_success?: boolean;
      delete_on_failure?: boolean;
      network_mode?: boolean;
      output_node_name?: string;
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

export const verifyOrientationTool = {
  name: "verify_orientation",
  label: "Verify Component Orientations",
  description:
    "Programmatically verify per-component axis orientations via PCA on point positions. " +
    "Authoritative for orientation correctness — vision models cannot reliably detect " +
    "wheels lying flat or handlebars pointing the wrong way.",
  promptSnippet: "Verify component orientations via PCA",
  promptGuidelines: [
    "Authoritative orientation check: wheels must have radial symmetry axis horizontal, handlebars must have long axis transverse, etc.",
    "MUST be called before houdini_commit_sandbox if the asset has any @component_id-tagged parts. commit_sandbox will refuse otherwise.",
    "Each check requires: component_id (matching the @component_id prim attr), kind (radial | elongated | planar), expected_axis (X/Y/Z or -X/-Y/-Z).",
    "kind=radial: symmetry axis = smallest eigenvalue's vector (wheel axle, gear axis).",
    "kind=elongated: long axis = largest eigenvalue's vector (handlebar, tube, crank).",
    "kind=planar: surface normal = smallest eigenvalue's vector (fender, saddle, body panel).",
    "When a check fails, the result includes a 'hint' field with the exact hou.Quaternion to apply.",
    "Set signed=true ONLY when direction matters (e.g. saddle normal must point +Y, not just be along Y).",
    "construction_axis (optional): declare the local-space axis a component was generated around, so verify_orientation derives the world axis deterministically instead of falling back to PCA (which can be noisy on sparse geometry).",
  ],
  parameters: Type.Object({
    node_path: Type.String({
      description: "Full path of the SOP node whose geometry contains the components",
    }),
    checks: Type.Array(
      Type.Object({
        component_id: Type.String({
          description: "Primitive attribute value used to filter (matches @component_id)",
        }),
        kind: Type.Union([
          Type.Literal("radial"),
          Type.Literal("elongated"),
          Type.Literal("planar"),
        ], { description: "radial=smallest eig (axle), elongated=largest eig (long axis), planar=smallest eig (normal)" }),
        expected_axis: Type.Union([
          Type.Literal("X"), Type.Literal("Y"), Type.Literal("Z"),
          Type.Literal("-X"), Type.Literal("-Y"), Type.Literal("-Z"),
        ], { description: "Expected dominant axis for this kind's eigenvector" }),
        tolerance_deg: Type.Optional(
          Type.Number({ description: "Allowed angular deviation. Default 15." })
        ),
        signed: Type.Optional(
          Type.Boolean({ description: "Direction matters (default false — axis is a line)" })
        ),
        construction_axis: Type.Optional(
          Type.Union([
            Type.Literal("X"), Type.Literal("Y"), Type.Literal("Z"),
            Type.Literal("-X"), Type.Literal("-Y"), Type.Literal("-Z"),
          ], { description: "B-station (PREFERRED). The local-space axis the component is generated around. When set, the builder derives the world axis deterministically from the anchor @orient (no PCA) and bakes it as edini_world_axis. Omit to fall back to PCA." })
        ),
      })
    ),
  }),
  async execute(
    _toolCallId: string,
    params: {
      node_path: string;
      checks: Array<{
        component_id: string;
        kind: "radial" | "elongated" | "planar";
        expected_axis: "X" | "Y" | "Z" | "-X" | "-Y" | "-Z";
        tolerance_deg?: number;
        signed?: boolean;
        construction_axis?: "X" | "Y" | "Z" | "-X" | "-Y" | "-Z";
      }>;
    }
  ) {
    return forwardTool("verify_orientation", params);
  },
};

export const commitSandboxTool = {
  name: "commit_sandbox",
  label: "Commit Houdini Sandbox",
  description:
    "Commit a verified procedural sandbox into the live Houdini scene with a final node name. " +
    "Runs houdini_verify_orientation as a hard gate when the asset has @component_id tags.",
  promptSnippet: "Commit a verified Houdini sandbox",
  promptGuidelines: [
    "HARD GATE: Do NOT call houdini_commit_sandbox unless houdini_verify_orientation has been called on this sandbox AND all checks passed (or the asset has no @component_id tags).",
    "If houdini_verify_orientation returned any failed checks, fix them using the provided hint quaternion and re-verify before committing. You cannot override the gate.",
    VISUAL_VERIFY_ON
      ? "If you have not yet called houdini_capture_review + describe_image on this sandbox, do that first for visual sanity (note: vision models cannot reliably detect orientation — verify_orientation is authoritative for that)."
      : "Before committing, confirm sanity via numeric evidence: the sandbox diagnostics/structural_checks, houdini_inspect_geometry_health, and houdini_geometry_inventory. Visual verification (capture_review + describe_image) is disabled.",
    "After 3 failed repair attempts, ask the user — do NOT commit anyway.",
    "Pass orientation_checks inline if you have not called houdini_verify_orientation separately; it runs the same gate at commit time.",
    "Use skip_orientation=true ONLY with a documented reason (e.g. abstract art where orientation is intentionally ambiguous).",
  ],
  parameters: Type.Object({
    sandbox_root_path: Type.String({ description: "Full path of the sandbox root node" }),
    final_name: Type.String({ description: "Final node name to use after committing" }),
    replace_existing: Type.Optional(
      Type.Boolean({ description: "Replace an existing node with the same final name" })
    ),
    orientation_checks: Type.Optional(
      Type.Array(
        Type.Object({
          component_id: Type.String(),
          kind: Type.Union([
            Type.Literal("radial"),
            Type.Literal("elongated"),
            Type.Literal("planar"),
          ]),
          expected_axis: Type.Union([
            Type.Literal("X"), Type.Literal("Y"), Type.Literal("Z"),
            Type.Literal("-X"), Type.Literal("-Y"), Type.Literal("-Z"),
          ]),
          tolerance_deg: Type.Optional(Type.Number()),
          signed: Type.Optional(Type.Boolean()),
          construction_axis: Type.Optional(
            Type.Union([
              Type.Literal("X"), Type.Literal("Y"), Type.Literal("Z"),
              Type.Literal("-X"), Type.Literal("-Y"), Type.Literal("-Z"),
            ], { description: "B-station: local construction axis (deterministic). Omit for PCA fallback." })
          ),
        }),
        { description: "Orientation checks to run as a commit gate (same schema as houdini_verify_orientation)" }
      )
    ),
    skip_orientation: Type.Optional(
      Type.Boolean({ description: "Bypass orientation gate. Only use with a documented reason." })
    ),
  }),
  async execute(
    _toolCallId: string,
    params: {
      sandbox_root_path: string;
      final_name: string;
      replace_existing?: boolean;
      orientation_checks?: Array<{
        component_id: string;
        kind: "radial" | "elongated" | "planar";
        expected_axis: "X" | "Y" | "Z" | "-X" | "-Y" | "-Z";
        tolerance_deg?: number;
        signed?: boolean;
        construction_axis?: "X" | "Y" | "Z" | "-X" | "-Y" | "-Z";
      }>;
      skip_orientation?: boolean;
    }
  ) {
    return forwardTool("commit_sandbox", params);
  },
};

export const discardSandboxTool = {
  name: "discard_sandbox",
  label: "Discard Houdini Sandbox",
  description: "Discard a procedural sandbox after it is no longer needed.",
  promptSnippet: "Discard a Houdini procedural sandbox",
  parameters: Type.Object({
    sandbox_root_path: Type.String({ description: "Full path of the sandbox root node" }),
  }),
  async execute(_toolCallId: string, params: { sandbox_root_path: string }) {
    return forwardTool("discard_sandbox", params);
  },
};

export const captureReviewTool = {
  name: "capture_review",
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
      Type.Array(Type.Number(), {
        description: "Capture resolution [width, height] per cell. Default: viewport native. Use [960, 540] for consistent quad-view cells."
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
    return forwardTool("capture_review", params);
  },
};

export const houdiniCaptureComponentDetail = {
  name: "houdini_capture_component_detail",
  label: "Capture Component Detail",
  description:
    "Capture close-up cells of specific @component_id values when they are present (per inventory) but too small to judge in the whole-asset 4-view. " +
    "Each component is framed to its OWN bounding box — this resolves the 'exists but too small to see' ambiguity definitively.",
  promptSnippet: "Close-up capture of specific component_ids",
  promptGuidelines: [
    "Use this (NOT another capture_review) when geometry_inventory shows a component with prim_count > 0 but size_fraction < 0.08, OR when vision flagged a component as missing/unclear that inventory says exists.",
    "Each component_id is framed to its own bounding box and captured as a separate cell — vision can then judge details (spokes, bolts, chains) it couldn't see in the whole-asset view.",
    "Keep views minimal (['perspective'] or ['perspective','top']) so cells stay large.",
  ],
  parameters: Type.Object({
    filepath: Type.String({
      description: "Output file path for the contact sheet PNG (auto-routed to the session screenshot folder)",
    }),
    node_path: Type.String({
      description: "SOP node whose geometry contains the @component_id prims",
    }),
    component_ids: Type.Array(Type.String(), {
      description: "component_id values to capture as individual close-up cells",
    }),
    views: Type.Optional(
      Type.Array(Type.String(), {
        description: "View angles per cell. Default ['perspective']. Add 'top' for a 2-view sheet.",
      })
    ),
    shading_mode: Type.Optional(
      Type.String({ description: "Viewport shading: 'smooth', 'wire', 'flat'. Default 'smooth'." })
    ),
    resolution: Type.Optional(
      Type.Array(Type.Number(), {
        description: "Capture resolution [width, height] per cell.",
      })
    ),
  }),
  async execute(
    _toolCallId: string,
    params: {
      filepath: string;
      node_path: string;
      component_ids: string[];
      views?: string[];
      shading_mode?: string;
      resolution?: number[];
    }
  ) {
    return forwardTool("houdini_capture_component_detail", params);
  },
};

export const dumpParmCatalogTool = {
  name: "dump_parm_catalog",
  label: "Generate Parm Catalog",
  description:
    "Generate the Houdini parameter catalog from the installed Houdini version. " +
    "Call once per session so recipe capture can compare live values against type defaults.",
  promptSnippet: "Generate the Houdini parameter catalog",
  parameters: Type.Object({
    output_path: Type.Optional(Type.String()),
    force: Type.Optional(Type.Boolean({ description: "Regenerate even if cached. Default false." })),
  }),
  async execute(_toolCallId: string, params: { output_path?: string; force?: boolean }) {
    return forwardTool("dump_parm_catalog", params);
  },
};

export const harnessTools = [
  houdiniCollectDiagnostics,
  houdiniRunPythonSandbox,
  houdiniVerifyAsset,
  verifyOrientationTool,
  commitSandboxTool,
  discardSandboxTool,
  // captureReviewTool is gated by EDINI_VISUAL_VERIFICATION (registered only
  // when visual verification is on) — kept out of the default array so it's
  // hidden from the agent when VV is off. [VISUAL-VERIFY-GATE]
  ...(VISUAL_VERIFY_ON ? [captureReviewTool] : []),
  houdiniCaptureComponentDetail,
  dumpParmCatalogTool,
];
