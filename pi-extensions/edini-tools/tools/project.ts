// pi-extensions/edini-tools/tools/project.ts
// Project HDA tool — build component scaffolds inside a Project HDA core node.
//
// A Project HDA (edini::project, SOP context) is a procedural-modeling project
// container. Its declaration lists components (each = a subnet with output
// ports: out[0]=main geometry, out[1..n]=anchor point clouds). This tool
// builds the SCAFFOLD (empty subnets + null + output nodes) — the geometry is
// filled by subsequent modeling.
//
// See python3.11libs/edini/project/builder.py (build_project_scaffold) and
// docs/superpowers/specs/2026-07-02-project-component-foundation-design.md.

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

export const projectTools = [
  {
    name: "project_build_scaffold",
    label: "Build Project Scaffold",
    description:
      "Build component scaffolds INSIDE a Project HDA core node (edini::project SOP HDA). " +
      "For each component in the declaration, creates an empty subnet with output ports " +
      "(out_geometry/out_anchors nulls + output nodes forming subnet outputs). " +
      "Pass `components` to set the component list and build in one shot, or omit to " +
      "rebuild the project's existing declaration scaffolds. Geometry is left empty for " +
      "subsequent modeling. Use this once a Project HDA exists and the component " +
      "decomposition is decided.",
    promptSnippet: "Build component scaffolds inside a Project HDA",
    promptGuidelines: [
      "Use project_build_scaffold when a Project HDA core node exists and the component decomposition is decided.",
      "The `core_path` is the edini::project SOP HDA instance path, e.g. /obj/project_car/project_core.",
      "Pass `components` (list of {id, purpose, params, ports}) to define what subnets to scaffold.",
      "Each component becomes a subnet named after its id, with out_geometry/out_anchors nulls + output nodes.",
    ],
    parameters: Type.Object({
      core_path: Type.String({
        description:
          "Path to the edini::project SOP HDA instance to build inside " +
          "(e.g. /obj/project_car/project_core).",
      }),
      components: Type.Optional(
        Type.Array(
          Type.Object({}, { additionalProperties: true, description:
            "A component declaration: {id, purpose, params:[], ports:{out:[], in:[]}}. " +
            "id = subnet name; ports.out[0] = main geometry, ports.out[1..n] = anchor clouds." }),
          { description:
            "Component list to set on the project before scaffolding. Omit to rebuild " +
            "the existing declaration's scaffolds." }
        ),
      ),
    }),
    async execute(_id: string, params: { core_path: string; components?: Record<string, unknown>[] }) {
      return forwardTool("project_build_scaffold", params);
    },
  },
];
