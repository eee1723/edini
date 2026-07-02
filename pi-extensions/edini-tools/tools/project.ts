// pi-extensions/edini-tools/tools/project.ts
// Project HDA tool — build rooted geometry inside a Project HDA core node.
//
// A Project HDA (edini::project, SOP context) is a procedural-modeling project
// container. Its declaration carries a rooted `assembly` field; this tool
// builds that assembly's geometry INSIDE the HDA core node (so it lives with
// the project, is editable in place, and its params are live spares on the HDA).
//
// See python3.11libs/edini/project/builder.py (build_project_model) and
// assembly_builder.build_assembly for the build mechanics.

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
    name: "project_build_model",
    label: "Build Project Model",
    description:
      "Build rooted geometry INSIDE a Project HDA core node (edini::project SOP HDA). " +
      "Pass a rooted `assembly` declaration to set it on the project and build in one shot, " +
      "or omit assembly to rebuild the project's existing declaration. The geometry lands " +
      "inside the HDA core as a live SOP network (mounts read the root's bbox via VEX on " +
      "every cook, leaves stamped by copytopoints). Use this once a Project HDA exists and " +
      "you know what to build.",
    promptSnippet: "Build the model inside a Project HDA",
    promptGuidelines: [
      "Use project_build_model when a Project HDA core node already exists and you have a rooted assembly declaration.",
      "The `core_path` is the edini::project SOP HDA instance path, e.g. /obj/project_car/project_core.",
      "Pass the full rooted assembly inline via `assembly` (same schema as build_assembly: {id, params, root, mounts, leaves}).",
    ],
    parameters: Type.Object({
      core_path: Type.String({
        description:
          "Path to the edini::project SOP HDA instance to build inside " +
          "(e.g. /obj/project_car/project_core).",
      }),
      assembly: Type.Optional(
        Type.Object({}, { additionalProperties: true, description:
          "Rooted assembly declaration to set on the project before building. " +
          "Same schema as build_assembly's assembly: {id, params, root, mounts, leaves}. " +
          "Omit to rebuild the existing declaration." }),
      ),
    }),
    async execute(_id: string, params: { core_path: string; assembly?: Record<string, unknown> }) {
      return forwardTool("project_build_model", params);
    },
  },
];
