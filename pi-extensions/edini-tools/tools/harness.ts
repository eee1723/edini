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
    "Execute Houdini Python code inside a procedural sandbox before committing changes to the live scene. " +
    "Two modes: single-SOP (default) for code that emits geometry from one Python SOP, and network_mode for building a multi-node modular network (body_generate + copytopoints + merge + OUT).",
  promptSnippet: "Run Python code in a Houdini procedural sandbox",
  promptGuidelines: [
    "ALWAYS use houdini_run_python_sandbox for initial procedural asset generation instead of raw houdini_run_python.",
    "Single-SOP mode (network_mode=false, default): the code runs as the cook body of ONE edini_generate Python SOP. It MUST NOT call createNode() on child SOPs — doing so triggers Houdini's 'Infinite recursion in evaluation' guard. Only emit geometry via node.geometry().createPoint()/createPolygon() on the cooking node.",
    "Network mode (network_mode=true): use this for ANY multi-component modular asset (bicycle, vehicle, furniture with swappable parts). The code runs in the sandbox geo CONTAINER, so it can build a multi-node network: container.createNode('python','body_generate'), container.createNode('copytopoints',...), container.createNode('merge'), container.createNode('null','OUT'). This is the ONLY mode that lets modular assets pass the commit structure/orientation gates through the sandbox instead of raw houdini_run_python.",
    "In network mode, use the injected `sandbox_root` variable (the geo container) or hou.node(sandbox_root_path) to create children, and end with a null/merge node named 'OUT' (or pass output_node_name). The harness auto-finds OUT, cooks it, and runs diagnostics on it.",
    "The sandbox result includes diagnostics and structural_checks (has_geometry, point_count, bounds_nonzero) — no need for separate inspect_geo or check_errors calls.",
    "Do not delete a failed sandbox before reviewing the diagnostics in the result.",
    "NEVER set commit_on_success=true on the first sandbox execution. Always capture (4-view quad) and verify with describe_image using the 3D verification prompt BEFORE committing.",
    "If describe_image reports critical or major defects (wrong orientation, missing components, STRUCTURAL_DETAIL < 3), fix the specific issue and re-verify — do NOT commit until verification passes or user approves.",
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

export const houdiniVerifyOrientation = {
  name: "houdini_verify_orientation",
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
      }>;
    }
  ) {
    return forwardTool("houdini_verify_orientation", params);
  },
};

export const houdiniCommitSandbox = {
  name: "houdini_commit_sandbox",
  label: "Commit Houdini Sandbox",
  description:
    "Commit a verified procedural sandbox into the live Houdini scene with a final node name. " +
    "Runs houdini_verify_orientation as a hard gate when the asset has @component_id tags.",
  promptSnippet: "Commit a verified Houdini sandbox",
  promptGuidelines: [
    "HARD GATE: Do NOT call houdini_commit_sandbox unless houdini_verify_orientation has been called on this sandbox AND all checks passed (or the asset has no @component_id tags).",
    "If houdini_verify_orientation returned any failed checks, fix them using the provided hint quaternion and re-verify before committing. You cannot override the gate.",
    "If you have not yet called houdini_capture_review + describe_image on this sandbox, do that first for visual sanity (note: vision models cannot reliably detect orientation — verify_orientation is authoritative for that).",
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
      }>;
      skip_orientation?: boolean;
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

export const houdiniBuildProceduralAsset = {
  name: "houdini_build_procedural_asset",
  label: "Build Procedural Asset (Declarative Recipe)",
  description:
    "Build a modular procedural asset from a declarative JSON recipe. The harness deterministically assembles the multi-node network (component python SOPs -> anchor generators -> Copy-to-Points -> merge -> postprocess -> OUT), cooks it, and runs the structure/orientation gate previews. The agent authors only per-component geometry code — never createNode/wiring/blockpath. This is the PREFERRED path for any multi-component asset.",
  promptSnippet: "Build a modular asset from a declarative recipe",
  promptGuidelines: [
    "PREFERRED for multi-component assets. Use this instead of network_mode hand-writing when the asset fits the body + Copy-to-Points decomposition (vehicles, furniture, any asset with swappable/repeated parts).",
    "You only write PER-COMPONENT geometry code: a single Python SOP cook body that emits geometry on its own node (node = hou.pwd(); geo = node.geometry()) and tags every prim with component_id. NEVER call createNode inside component code.",
    "Every component code MUST: geo.addAttrib(hou.attribType.Prim, 'component_id', '') before geometry, then poly.setAttribValue('component_id', '<id>') on each prim. The builder checks component_id presence post-cook and reports missing ids.",
    "Components with anchors get Copy-to-Points automatically: provide anchors=[{position:[x,y,z], orient:[x,y,z,w], pscale:1.0, component_id:'wheel_fl'}, ...]. Components with empty/omitted anchors go straight into the merge.",
    "pscale semantics: 1.0 = original source size. Model each stamped component at UNIT scale and set pscale to the real size, OR model at real scale and use pscale=1.0.",
    "The builder does NOT commit. After build, inspect the returned diagnostics/structure_advisory/orientation_check/component_id_check, then call houdini_commit_sandbox(root_path, name, orientation_checks=recipe.orientation_asserts) to run the hard gates and commit.",
    "If a component's cook fails, the builder reports which component and preserves the sandbox for diagnostics — do NOT discard before reading the error.",
    "orientation_asserts in the recipe flow to commit_sandbox's orientation gate automatically. Each needs component_id (matching a prim attr value), kind (radial|elongated|planar), expected_axis (X/Y/Z/-X/-Y/-Z).",
  ],
  parameters: Type.Object({
    recipe: Type.Record(Type.String(), Type.Unknown(), {
      description:
        "Declarative recipe object. Keys: asset_name (str), units (str, doc only), params? (asset-level shared params {name: {default, min?, max?, label?}} that the builder installs as spare parms on the sandbox root for true cross-component linkage), components (list of {id, code, reads?, anchors?}) where reads lists param names the component references via hou.ch and anchors support position_expr/orient_expr/pscale_expr strings (evaluated against params at build time) OR static position/orient/pscale numbers, postprocess? (list of {type, params?}), orientation_asserts? (list of {component_id, kind, expected_axis, tolerance_deg?, signed?, construction_axis?}), expected? (dict). See the Declarative Recipe Builder section of the procedural-modeling skill for the full schema.",
    }),
    sandbox_name: Type.Optional(
      Type.String({ description: "Optional name for the sandbox root (defaults to asset_name)" })
    ),
    delete_on_failure: Type.Optional(
      Type.Boolean({ description: "Delete the sandbox automatically when the build fails" })
    ),
  }),
  async execute(
    _toolCallId: string,
    params: {
      recipe: Record<string, unknown>;
      sandbox_name?: string;
      delete_on_failure?: boolean;
    }
  ) {
    return forwardTool("houdini_build_procedural_asset", params);
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
      Type.Tuple([Type.Number(), Type.Number()], {
        description: "Capture resolution (width, height) per cell.",
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
      resolution?: [number, number];
    }
  ) {
    return forwardTool("houdini_capture_component_detail", params);
  },
};

export const harnessTools = [
  houdiniCollectDiagnostics,
  houdiniRunPythonSandbox,
  houdiniVerifyAsset,
  houdiniVerifyOrientation,
  houdiniCommitSandbox,
  houdiniDiscardSandbox,
  houdiniBuildProceduralAsset,
  houdiniCaptureReview,
  houdiniCaptureComponentDetail,
];
