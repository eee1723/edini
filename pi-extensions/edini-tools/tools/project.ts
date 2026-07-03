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
    name: "project_create",
    label: "Create Project HDA",
    description:
      "Create a new Project HDA — the FIRST step of any modeling task. " +
      "Returns the core_path (feed to project_build_scaffold) of a fresh " +
      "edini::project SOP HDA inside a geo shell. Always call this before " +
      "project_build_scaffold.",
    promptSnippet: "Create a new Project HDA to model in",
    promptGuidelines: [
      "Use project_create as the FIRST step of any multi-part modeling task (table, car, keyboard, ...).",
      "It returns core_path — feed that to project_build_scaffold next.",
      "Pass a `goal` describing what to build (used for project metadata).",
    ],
    parameters: Type.Object({
      name: Type.Optional(Type.String({
        description: "Node name for the project (default 'project'). Becomes the geo shell name at /obj/<name>.",
      })),
      goal: Type.Optional(Type.String({
        description: "What the project will build, in natural language (e.g. 'a small table').",
      })),
    }),
    async execute(_id: string, params: { name?: string; goal?: string }) {
      return forwardTool("project_create", params);
    },
  },
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
      "Use project_build_scaffold after project_create, once the component decomposition is decided.",
      "The `core_path` is the edini::project SOP HDA instance path returned by project_create, e.g. /obj/project_table/project_core.",
      "Pass `components` (list of {id, purpose, params, ports}) to define what subnets to scaffold.",
      "Each component becomes a subnet named after its id, with out_geometry/out_anchors nulls + output nodes.",
    ],
    parameters: Type.Object({
      core_path: Type.String({
        description:
          "Path to the edini::project SOP HDA instance to build inside " +
          "(e.g. /obj/project_table/project_core).",
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
  {
    name: "project_promote_params",
    label: "Promote Component Params",
    description:
      "Lift all component subnets' spare parms to the Project HDA core's top-level interface, " +
      "so the whole model is adjustable from one place. Each promoted parm becomes " +
      "<component>_<parm> on the core, driving its subnet via a live ch() reference. " +
      "Run this AFTER modeling inside the component subnets (so the parms you added exist).",
    promptSnippet: "Promote component params to the Project HDA core",
    promptGuidelines: [
      "Use project_promote_params AFTER modeling inside component subnets, to expose adjustable params at the top.",
      "Requires core_path (the edini::project SOP HDA instance).",
      "Each component subnet's spare parms become <component>_<parm> on the core, with live ch() refs.",
    ],
    parameters: Type.Object({
      core_path: Type.String({
        description: "Path to the edini::project SOP HDA instance (e.g. /obj/project_table/project_core).",
      }),
    }),
    async execute(_id: string, params: { core_path: string }) {
      return forwardTool("project_promote_params", params);
    },
  },
];
