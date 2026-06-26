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

export const assetTools = [validateAsset];
