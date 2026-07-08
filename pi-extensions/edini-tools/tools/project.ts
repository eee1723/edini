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
import { forwardTool } from "./_shared";

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
      "Scaffold component subnets + design params INSIDE a Project HDA core node (edini::project SOP HDA). " +
      "For each component in the declaration, scaffolds an empty subnet with output ports " +
      "(out_geometry/out_anchors nulls + output nodes forming subnet outputs). For each design_param, " +
      "creates a core-level spare parm (with default/min/max) — the core is the single source of truth; " +
      "component subnets reference these via ch('../<name>') after promote. Pass `components` + `design_params` " +
      "to scaffold them in one shot, or omit to rebuild the existing declaration. Geometry is left empty " +
      "for subsequent modeling (the scaffold never builds geometry).",
    promptSnippet: "Scaffold component subnets + design params inside a Project HDA",
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
      "Promote all component subnets' spare parms to the Project HDA core's top-level interface. " +
      "LEGACY/bottom-up path: under the official design_params path (Step 2b), geometry references core parms " +
      "directly via absolute ch(), so you never create subnet spare parms and this returns promoted:[] (correct, " +
      "not a failure). Only relevant if you took the bottom-up path of building subnet spare parms. The LIVE " +
      "guarantee is now checked by verify_parametric, not promote.",
    promptSnippet: "Promote subnet spare parms to core (legacy bottom-up path)",
    promptGuidelines: [
      "Under the design_params path (Step 2b), this returns promoted:[] — that is CORRECT, not a failure. The design params already live on the core and geometry already references them.",
      "Do NOT call promote expecting it to fix parametricity. Use verify_parametric to prove a param reaches the geometry.",
      "Only relevant if you built subnet spare parms (the legacy bottom-up path Step 3 no longer teaches).",
      "Requires core_path (the edini::project SOP HDA instance).",
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
    name: "project_repath_to_relative",
    label: "Repath Component ch() to Relative",
    description:
      "Rewrite ONE component's absolute ch('/obj/.../project_core/<p>') references to relative " +
      "(ch('../../<p>'), depth computed per-node), so the component references its core by POSITION " +
      "not absolute path. Call this BEFORE copy-pasting a component subnet into another project — the " +
      "migrated component then cooks anywhere a <project_core> node sits at the same relative depth. " +
      "Optional/on-demand: leave components on absolute paths (the stable default) unless you intend to migrate them.",
    promptSnippet: "Make a component migratable (absolute ch → relative)",
    promptGuidelines: [
      "Use project_repath_to_relative ONLY when you intend to copy/migrate a component subnet to another project. Absolute paths are the stable default otherwise.",
      "Rewrites every ch('.../project_core/<p>') and hou.ch('.../project_core/<p>') inside the component subtree to relative ch('../../<p>') (depth computed per-node).",
      "Non-ch() expressions and references to other nodes are left untouched.",
      "Scope is ONE component (component_id), not the whole project — minimal blast radius.",
      "After repath, verify with verify_parametric that the geometry still responds to the core params (it should — only the path notation changed, not the link).",
    ],
    parameters: Type.Object({
      core_path: Type.String({
        description: "Path to the edini::project SOP HDA instance.",
      }),
      component_id: Type.String({
        description: "The component subnet name (direct child of core) to repath.",
      }),
    }),
    async execute(_id: string, params: { core_path: string; component_id: string }) {
      return forwardTool("project_repath_to_relative", params);
    },
  },
  {
    name: "project_add_anchors",
    label: "Add Procedural Anchors",
    description:
      "Procedurally generate anchor points by MEASURING a component's geometry (LIVE — recompute when geometry changes). " +
      "Each anchor is a measurement spec resolved into a VEX wrangle that measures the component's bbox on every cook. " +
      "Always measure — never hardcode addpoint coordinates (the platform guard refuses hardcoded addpoint with 'measure violation'). " +
      "Resizing the component (via a design param) automatically moves the measured anchors. Anchors are tagged with @name for downstream components to consume.",
    promptSnippet: "Generate live anchor points from a component's geometry",
    promptGuidelines: [
      "Use project_add_anchors to MEASURE anchor points from geometry — always measure, never hardcode addpoint coordinates.",
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
  {
    name: "project_emit_markers",
    label: "Emit Semantic Markers",
    description:
      "Emit @name-tagged marker points INTO a component's geometry at REAL measured positions, so a downstream " +
      "by_name anchor can pick them. Closes the gap that made by_name harder than bbox: instead of the agent " +
      "hand-writing a marker-emission wrangle, this is a declarative one-call (same measure vocabulary as " +
      "project_add_anchors: bbox_corner/bbox_face_center/bbox_center/...). Each marker {name, measure, ...params} " +
      "becomes a wrangle reading the component's main geometry (out_geometry's source) and emitting ONE point " +
      "tagged @name=<name>, merged into out_geometry. A downstream component then uses " +
      "project_add_anchors with measure:'by_name' + marker:'<name>' to pick that exact point. This is the cure " +
      "for bbox-derived anchors that sit on the bbox hull instead of the real geometric feature (e.g. a bike " +
      "frame's true dropout vs its bbox face center). MUST build the component's geometry first (markers are " +
      "measured from it). Idempotent + append-only across calls.",
    promptSnippet: "Emit named marker points at real geometric positions for by_name anchors",
    promptGuidelines: [
      "Use project_emit_markers AFTER building a component's main geometry — markers are measured from that geometry.",
      "Each marker: {name, measure, ...params}. name = the @name tag (downstream by_name picks it by this name). measure ∈ bbox_corner/bbox_face_center/bbox_center/... (same as anchors).",
      "A marker sits at a REAL geometric position (a measured bbox corner/face/etc.), so when the geometry resizes the marker moves with it — unlike a hardcoded coordinate.",
      "Downstream consumes a marker via project_add_anchors with measure:'by_name' + marker:'<name>' — that picks the exact marker point, not a bbox derivation.",
      "Prefer by_name (marker) anchors for PRECISE assembly points (dropout, head-tube top); use bbox anchors only for gross posture points.",
      "Idempotent: re-running with the same marker name replaces it in place; new names are appended.",
    ],
    parameters: Type.Object({
      core_path: Type.String({ description: "Path to the edini::project SOP HDA instance." }),
      component_id: Type.String({ description: "Which component subnet emits these markers (e.g. 'frame')." }),
      markers: Type.Array(
        Type.Object({}, { additionalProperties: true, description:
          "Marker spec: {measure:'bbox_corner'|..., name:'<marker_name>', ...measure-params}. " +
          "measure selects the strategy; name tags the emitted point's @name." }),
        { description: "List of marker measurement specs (same vocabulary as project_add_anchors)." },
      ),
    }),
    async execute(_id: string, params: { core_path: string; component_id: string; markers: Record<string, unknown>[] }) {
      return forwardTool("project_emit_markers", params);
    },
  },
  {
    name: "project_status",
    label: "Project Completion Status",
    description:
      "One-shot completion snapshot of EVERY component in a Project HDA — replaces calling inspect_health + " +
      "geometry_inventory + check_errors separately per component. For each declared component reports: " +
      "geo_flow (ok|empty|broken — does out_geometry have cooked geometry?), prim/point counts, " +
      "anchors {declared, emitted, missing} (ports.out declarations vs the anchor_<name> wrangles created), " +
      "and error/warning counts across the subtree. Plus an overall summary: how many components have geometry, " +
      "all anchors emitted, errors, and an 'incomplete' list (what's left to build). Read-only, non-destructive. " +
      "Use this to see the whole project's state at a glance; use verify_parametric for the deeper LIVE proof.",
    promptSnippet: "Snapshot every component's completion state in one call",
    promptGuidelines: [
      "Use project_status as the single status check instead of N per-component inspect calls.",
      "Per component: geo_flow=ok means geometry is flowing into out_geometry; empty means the agent hasn't wired geometry yet; broken means a cook error (see cook_error).",
      "anchors.missing lists declared-but-not-yet-emitted anchor names (call project_add_anchors for them).",
      "overall.incomplete is the 'what's left to build' list — a component is complete when geo_flow=ok AND no missing anchors AND no errors.",
      "Read-only. For the LIVE parametric guarantee (change a param → geometry responds), use verify_parametric.",
    ],
    parameters: Type.Object({
      core_path: Type.String({ description: "Path to the edini::project SOP HDA instance." }),
    }),
    async execute(_id: string, params: { core_path: string }) {
      return forwardTool("project_status", params);
    },
  },
];
