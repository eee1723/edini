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
      "Build component scaffolds + design params INSIDE a Project HDA core node (edini::project SOP HDA). " +
      "For each component in the declaration, creates an empty subnet with output ports " +
      "(out_geometry/out_anchors nulls + output nodes forming subnet outputs). For each design_param, " +
      "creates a core-level spare parm (with default/min/max) — the core is the single source of truth; " +
      "component subnets reference these via ch('../<name>') after promote. Pass `components` + `design_params` " +
      "to set them and build in one shot, or omit to rebuild the existing declaration. Geometry is left empty " +
      "for subsequent modeling.",
    promptSnippet: "Build component scaffolds + design params inside a Project HDA",
    promptGuidelines: [
      "Use project_build_scaffold after project_create, once the component decomposition + adjustable params are decided.",
      "The `core_path` is the edini::project SOP HDA instance path returned by project_create.",
      "Pass `components` (list of {id, purpose, ports}) to define what subnets to scaffold.",
      "Pass `design_params` (list of {name, default, min, max, label, components}) to define core-level adjustable params. The core owns the values; subnets reference them after promote.",
      "Each component becomes a subnet named after its id, with out_geometry/out_anchors nulls + output nodes.",
      "ports FULL contract (all fields required; build it right the first time — validation reports all errors at once): " +
        "ports.out is a list where out[0] MUST be {index:0, kind:'geometry'} (main geometry). " +
        "out[1+] may be {index:1, kind:'anchors', points:[{name:'<id>', role:'<desc>'}]} — each point needs a name matching ^[A-Za-z][A-Za-z0-9_]*$. " +
        "ports.in is a list; each entry MUST have from (source component id), port (source component's OUTPUT index, int>=0; 1 = its anchor cloud), and anchor (the consumed anchor's @name, unique within this component, same regex). " +
        "Example (table): tabletop ports.out=[{index:0,kind:'geometry'},{index:1,kind:'anchors',points:[{name:'leg_corners',role:'4 bottom corners'}]}]; legs ports.in=[{from:'tabletop',port:1,anchor:'leg_corners'}].",
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
            "A component declaration: {id, purpose, ports:{out:[], in:[]}}. " +
            "id = subnet name; ports.out[0] = main geometry, ports.out[1..n] = anchor clouds." }),
          { description:
            "Component list to set on the project before scaffolding. Omit to rebuild " +
            "the existing declaration's scaffolds." }
        ),
      ),
      design_params: Type.Optional(
        Type.Array(
          Type.Object({}, { additionalProperties: true, description:
            "A design parameter: {name, default, min?, max?, label?, components?}. " +
            "Created on the core HDA as the single source of truth (with default/min/max). " +
            "Component subnets reference it via ch('../<name>') after promote. " +
            "components = list of component ids using it (omit = all components)." }),
          { description:
            "Design params to define at the core level. The core owns the values; subnets follow." }
        ),
      ),
    }),
    async execute(_id: string, params: { core_path: string; components?: Record<string, unknown>[]; design_params?: Record<string, unknown>[] }) {
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
  {
    name: "project_add_anchors",
    label: "Add Procedural Anchors",
    description:
      "Procedurally generate anchor points from a component's geometry (LIVE — recompute when geometry changes). " +
      "Each anchor is a measurement spec resolved into a VEX wrangle that reads the component's bbox on every cook. " +
      "Use this INSTEAD of hardcoded addpoint coordinates, so that resizing the component (via a design param) " +
      "automatically moves the anchors. Anchors are tagged with @name for downstream components to consume.",
    promptSnippet: "Generate live anchor points from a component's geometry",
    promptGuidelines: [
      "Use project_add_anchors to emit anchor points PROCEDURALLY from geometry — never hardcode addpoint coordinates.",
      "Each anchor: {measure, name, ...measure-params}. measure ∈ bbox_corner/bbox_face_center/bbox_center/grid_on_face/...; name = the @name tag (anchor identity).",
      "bbox_corner needs 'axes' (6-char sign string like '+X-Y+Z'); bbox_face_center needs 'face' (like '-Y' for bottom).",
      "Anchors derive from the component's main geometry (out_geometry) by default, so they move when the geometry resizes.",
      "Example: 4 table-leg mounts = [{measure:'bbox_corner',axes:'+X-Y+Z',name:'leg_fr'}, ...3 more corners with -Y fixed].",
    ],
    parameters: Type.Object({
      core_path: Type.String({ description: "Path to the edini::project SOP HDA instance." }),
      component_id: Type.String({ description: "Which component subnet emits these anchors (e.g. 'tabletop')." }),
      anchors: Type.Array(
        Type.Object({}, { additionalProperties: true, description:
          "Anchor spec: {measure:'bbox_corner'|'bbox_face_center'|..., name:'<anchor_name>', ...measure-params}. " +
          "measure selects the strategy; name tags the point's @name; axes/face/etc. configure the measurement." }),
        { description: "List of anchor measurement specs." },
      ),
    }),
    async execute(_id: string, params: { core_path: string; component_id: string; anchors: Record<string, unknown>[] }) {
      return forwardTool("project_add_anchors", params);
    },
  },
];
