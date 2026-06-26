// pi-extensions/edini-tools/tools/asset.ts
// Declarative procedural-asset pipeline tools.
//
// An *asset* is a JSON description of a multi-component procedural object
// (bicycle, chair, pipe assembly) authored BEFORE geometry exists. It has
// three sections: a param library (every dimension lives here — no hardcoded
// numbers allowed downstream), a skeleton point DAG (named 3D points whose
// coordinates are expressions over params and other points — the linkage
// that keeps everything parametric), and components (filled in milestone 2).
//
// Milestone 1 exposes validate_asset: a pure-data check that runs before any
// Houdini node is touched (shift-left validation). It catches param-library
// errors, skeleton cycles, dangling references, and expression syntax issues
// — the failure modes that used to surface only at Cook time.

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

export const validateAsset = {
  name: "validate_asset",
  label: "Validate Procedural Asset",
  description:
    "Validate a declarative procedural-asset JSON (params + skeleton point DAG) with ZERO Houdini cost. " +
    "This is the first step of the asset pipeline: it catches errors before any geometry is built — " +
    "param-library issues, skeleton cycles, dangling point/param references, and expression syntax. " +
    "Pass an inline 'asset' dict OR an 'asset_path'. Set resolve=true to also resolve every skeleton " +
    "point to a concrete (x,y,z) so you can preview where components will land. The asset JSON shape: " +
    "{asset_schema_version:1, id, params:{name:{kind:'primary'|'derived', default, min, max, from?}}, " +
    "skeleton:{point:{expr:[xStr,yStr,zStr]}}, components:[]}. Skeleton exprs reference params by name " +
    "and other points as point[axis], e.g. rear_axle: {expr:['base[0]','wheel_radius','0']}.",
  promptSnippet: "Validate an asset's param library + skeleton DAG (no Houdini, shift-left)",
  promptGuidelines: [
    "Call validate_asset BEFORE building geometry — it catches param-name typos, skeleton cycles, and dangling references for free, without cooking anything.",
    "The param library is the SINGLE source of truth for every dimension. Rule: no component may hardcode a size — it must read from params. Declare params up front and add new ones as the design grows.",
    "kind:'primary' = user-facing (needs default/min/max). kind:'derived' = computed from other params via 'from' (e.g. {kind:'derived', from:'wheel_radius - bb_drop'}). Derived params are resolved automatically — never give them a default.",
    "Skeleton points reference each other as point[axis] (e.g. front_axle references rear_axle[0]). The DAG must be acyclic — a cycle is caught here. Point names and param names share no namespace, so a typo surfaces as a dangling-ref error.",
    "Use resolve=true to preview coordinates: changing a param and re-validating shows how every point moves, confirming linkage is correct before you commit to building geometry.",
  ],
  parameters: Type.Object({
    asset: Type.Optional(
      Type.Record(Type.String(), Type.Unknown(), {
        description:
          "Inline asset JSON object. Provide this OR asset_path. " +
          "Shape: {asset_schema_version:1, id, params:{...}, skeleton:{point:{expr:[x,y,z]}}, components:[]}.",
      })
    ),
    asset_path: Type.Optional(
      Type.String({
        description: "Path to an asset JSON file on disk (alternative to inline 'asset').",
      })
    ),
    resolve: Type.Optional(
      Type.Boolean({
        description:
          "If true (and validation passes), also resolve every skeleton point to a concrete (x,y,z) " +
          "tuple and return it as 'resolved_skeleton'. Lets you preview coordinates. Default false.",
      })
    ),
  }),
  async execute(
    _toolCallId: string,
    params: { asset?: Record<string, unknown>; asset_path?: string; resolve?: boolean }
  ) {
    return forwardTool("validate_asset", params);
  },
};

export const buildAsset = {
  name: "build_asset",
  label: "Build Procedural Asset",
  description:
    "Build a validated declarative asset into a Houdini node network (milestone 2). " +
    "Each component attaches to a skeleton point BY NAME (declared in the asset's skeleton " +
    "section) and reads its dimensions from the param library — no hardcoded coordinates. " +
    "The builder merges every component into a display-flagged OUT node inside a sandbox " +
    "geo container. Pass an inline 'asset' dict OR an 'asset_path'. ALWAYS call validate_asset " +
    "first to catch param/skeleton errors cheaply; this tool then builds the geometry. " +
    "Returns the OUT path + sandbox_root so you can inspect, adjust, or commit_sandbox the result. " +
    "Component shape: {id, backend:'native_chain', attach:{position:'<skeleton_point>'}, " +
    "nodes:[{type, params:{parm: value|expr}}]}. A node param value that is a STRING is an " +
    "expression over the param library (e.g. box size ['top_size','top_thickness','top_size']).",
  promptSnippet: "Build an asset's components into a Houdini network (skeleton-point attach)",
  promptGuidelines: [
    "Call validate_asset BEFORE build_asset — it catches param typos and skeleton-point reference errors for free, without creating any nodes.",
    "Each component attaches to a DECLARED skeleton point by name (attach.position). Components never carry their own coordinates — the skeleton DAG computes positions, so two components can never disagree about a shared feature's location.",
    "Node param values: a NUMBER is used directly; a STRING is an expression over the param library (e.g. 'wheel_radius', 'top_size/2', 'sqrt(a**2 + b**2)'). This keeps every dimension parametric.",
    "build_asset returns sandbox_root + out_path. To make the asset permanent, call commit_sandbox(sandbox_root, <final_name>). On failure the sandbox is preserved so you can diagnose the partial build.",
    "Milestone 2 implements the native_chain backend only (native SOPs: box/tube/torus/...). vex_skeleton and python backends arrive in a later milestone.",
  ],
  parameters: Type.Object({
    asset: Type.Optional(
      Type.Record(Type.String(), Type.Unknown(), {
        description:
          "Inline asset JSON object. Provide this OR asset_path. " +
          "Must have validated params + skeleton + components already.",
      })
    ),
    asset_path: Type.Optional(
      Type.String({
        description: "Path to a validated asset JSON file (alternative to inline 'asset').",
      })
    ),
    sandbox_name: Type.Optional(
      Type.String({
        description:
          "Name hint for the sandbox geo container (default 'asset'). " +
          "Used in the generated node name and commit defaults.",
      })
    ),
  }),
  async execute(
    _toolCallId: string,
    params: { asset?: Record<string, unknown>; asset_path?: string; sandbox_name?: string }
  ) {
    return forwardTool("build_asset", params);
  },
};

export const assetTools = [validateAsset, buildAsset];
