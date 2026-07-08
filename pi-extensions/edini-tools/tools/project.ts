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
    name: "project_plan",
    label: "Capture Project Intent (Goal + Success Criteria)",
    description:
      "Capture the modeling intent — the goal + success criteria — BEFORE scaffolding. " +
      "Forces you to articulate what 'done' means up front (platform validates non-empty), " +
      "so upstream errors don't compound into a model that builds but misses the point. " +
      "The success_criteria are stored on the project declaration and are later cross-checkable " +
      "by project_finalize. Call this right after project_create, before project_build_scaffold. " +
      "Replaces the vague 'inspect_health overall_ok = done' trap (overall_ok only proves 'not " +
      "broken right now', not 'parametric + meets intent').",
    promptSnippet: "State the goal + success criteria before building",
    promptGuidelines: [
      "Call project_plan as the FIRST step after project_create — before project_build_scaffold — to commit to what 'done' means.",
      "goal: what the project will build, in natural language (e.g. 'a small parametric table').",
      "success_criteria: a non-empty list of strings — the explicitly-stated conditions for done (e.g. ['tabletop is parametric in length', '4 legs at measured corners', 'passes verify_parametric + verify_robust']).",
      "Both goal and success_criteria are REQUIRED (the tool refuses empty ones) — that's the point: no building until intent is articulated.",
    ],
    parameters: Type.Object({
      core_path: Type.String({ description: "Path to the edini::project SOP HDA instance (from project_create)." }),
      goal: Type.String({ description: "What the project will build, in natural language." }),
      success_criteria: Type.Array(Type.String(), { description: "Non-empty list of conditions for 'done'." }),
    }),
    async execute(_id: string, params: { core_path: string; goal: string; success_criteria: string[] }) {
      return forwardTool("project_plan", params);
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
    name: "project_emit_component",
    label: "Emit Component from Archetype",
    description:
      "Build a component's geometry from an ARCHETYPE — the platform-layer alternative to hand-authoring step 3 " +
      "with raw create_node/set_param (the #1 source of step-3 failures: Python SOP errors, wrong parm names, " +
      "broken ch() refs). Each archetype owns its nodes (deterministic names, idempotent), wires them to " +
      "out_geometry, and references design params via RELATIVE ch() (so archetype-built components are migratable " +
      "across projects — copy a component subnet into another project and it still cooks). Value convention: a size/position component " +
      "is a NUMBER (literal) or a STRING (a design_param name → live ch() ref). " +
      "ARCHETYPES: 'box_panel' — a parametric box (tabletop/seat/panel): params.size=[x,y,z] (each a number or " +
      "design_param name); optional params.markers (list, forwarded to project_emit_markers after the box is " +
      "wired, so by_name anchors pick precise assembly points). " +
      "'copy_array' — stamp a leaf shape (box/tube/...) onto the component's consumed anchor points (legs/spokes/keys): " +
      "params.leaf={type, params:{parm: number|design_param_name}}; the component's declared ports.in determines which anchors are consumed. " +
      "'tube_graph' — build a tube graph (frame/fork/handlebar): polyline edges between the component's consumed named anchors, then PolyWire " +
      "for thickness. params.tubes=[{a:<name>,b:<name>},...] + params.radius (number or design_param name). Uses VEX — zero Python-SOP error surface. " +
      "'extrude_profile' — a parametric tube/pillar (columns/handles/cylinders): params.radius + params.height " +
      "(each a number or design_param name). " +
      "Prefer this over hand-building for any component that matches an archetype — it eliminates the recurring " +
      "step-3 errors (return/addAttrib/createPoint/ch-vs-hou.ch).",
    promptSnippet: "Build a component from a named archetype (box_panel/...) instead of raw nodes",
    promptGuidelines: [
      "Use project_emit_component for any component matching an archetype, BEFORE reaching for raw houdini_create_node/set_param.",
      "box_panel: params={size:[x,y,z]} where each is a number OR a design_param name (e.g. size:['length','thickness','width'] → sizex=ch(length), sizey=ch(thickness), sizez=ch(width)).",
      "box_panel params.markers: optional list of {name, measure, ...} forwarded to project_emit_markers AFTER the box is wired — so a downstream by_name anchor picks precise assembly points (e.g. leg mount corners).",
      "Idempotent: re-running with the same archetype rebuilds the chain (deterministic node names), so you can tweak size/markers and re-run safely.",
      "Only hand-build with raw node tools when NO archetype fits (then follow COMPONENT_TEMPLATE.md's Python SOP skeleton).",
    ],
    parameters: Type.Object({
      core_path: Type.String({ description: "Path to the edini::project SOP HDA instance." }),
      component_id: Type.String({ description: "The component subnet to build inside." }),
      archetype: Type.String({
        description: "Archetype name: 'box_panel' | 'copy_array' | 'tube_graph' | 'extrude_profile'.",
      }),
      params: Type.Optional(
        Type.Object({}, { additionalProperties: true, description:
          "Archetype-specific params. box_panel: {size:[x,y,z]} (each a number or design_param name); " +
          "optional {markers:[{name,measure,...}]}." })
      ),
    }),
    async execute(_id: string, params: { core_path: string; component_id: string; archetype: string; params?: Record<string, unknown> }) {
      return forwardTool("project_emit_component", params);
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
  {
    name: "project_finalize",
    label: "Finalize Project (Hard Verify Gate)",
    description:
      "Hard gate that refuses to mark a Project HDA complete until it passes verification. " +
      "Runs project_status (every component complete?) + verify_robust (model holds across every " +
      "design_param's min/default/max?) + verify_parametric per design_param (each param actually " +
      "drives the geometry?). Returns {success, finalized, failures:[...]} — a non-empty failures list " +
      "means the project is NOT complete (fix the named issues; do NOT just re-declare done). This is " +
      "the structural cure for 'declared done prematurely' (declaring complete after inspect_health " +
      "without ever proving parametricity). ESCAPE HATCH: if verification genuinely cannot run, pass " +
      "acknowledge_skip=true + a non-empty skip_reason; the skip is audited to the project's declaration " +
      "log. A project with NO design_params finalizes on status completeness alone (parametric gates " +
      "are N/A, not skipped).",
    promptSnippet: "Gate the project complete on verification passing",
    promptGuidelines: [
      "Call project_finalize as the LAST step before reporting a Project HDA model as done — it is the hard gate that proves 'done' means 'parametric + robust + complete'.",
      "It runs verification itself (you do not call verify_parametric/verify_robust separately for finalize); on failure it returns a failures[] list naming exactly what to fix.",
      "On failure: FIX the named issues, then re-finalize. Do NOT re-declare done, and do NOT use acknowledge_skip to bypass a real failure.",
      "acknowledge_skip=true + skip_reason is ONLY for when verification genuinely can't run (e.g. an intentionally non-parametric study); the skip is recorded in the project log. Using it to bypass a failure defeats the gate.",
      "A project with no design_params finalizes on status completeness alone — no acknowledge_skip needed for that.",
    ],
    parameters: Type.Object({
      core_path: Type.String({ description: "Path to the edini::project SOP HDA instance." }),
      acknowledge_skip: Type.Optional(Type.Boolean({
        description: "Bypass running verification (requires skip_reason). Audited to the declaration log. Use ONLY when verify genuinely can't run, never to bypass a real failure.",
      })),
      skip_reason: Type.Optional(Type.String({
        description: "Required when acknowledge_skip=true: why verification is skipped.",
      })),
      samples: Type.Optional(Type.String({
        description: "verify_robust sampling: 'min_default_max' (default) or 'min_max'.",
      })),
    }),
    async execute(_id: string, params: { core_path: string; acknowledge_skip?: boolean; skip_reason?: string; samples?: string }) {
      return forwardTool("project_finalize", params);
    },
  },
  {
    name: "project_snapshot_component",
    label: "Snapshot Component",
    description:
      "Snapshot a component's current state (copy it aside) for selective multi-round optimization. " +
      "Snapshot before a risky change, iterate, then project_restore_component if the new version is worse — " +
      "WITHOUT re-running the whole project. The snapshot is stored under the core's _snapshots subnet " +
      "(travels with the .hip; skipped by OUT/inspect). Returns snapshot_id = '<component>_<N>'.",
    promptSnippet: "Save a component version to restore later",
    promptGuidelines: [
      "Use project_snapshot_component BEFORE a risky change to a component (e.g. rebuilding its geometry, changing its archetype).",
      "Returns snapshot_id ('<component>_<N>') — pass it to project_restore_component to revert.",
      "Snapshots persist in the .hip (the _snapshots subnet inside the core); they don't pollute the model (OUT/inspect skip them).",
    ],
    parameters: Type.Object({
      core_path: Type.String({ description: "Path to the edini::project SOP HDA instance." }),
      component_id: Type.String({ description: "The component subnet to snapshot." }),
      label: Type.Optional(Type.String({ description: "Optional human label for the snapshot (e.g. 'before bevel')." })),
    }),
    async execute(_id: string, params: { core_path: string; component_id: string; label?: string }) {
      return forwardTool("project_snapshot_component", params);
    },
  },
  {
    name: "project_restore_component",
    label: "Restore Component from Snapshot",
    description:
      "Restore a component from a snapshot (replaces its current state). copyNodesTo preserves internal wiring " +
      "and external ports.in connections, and the relative ch() refs re-resolve at the restored depth. Use this " +
      "to revert a component to a saved version after an iteration went wrong.",
    promptSnippet: "Revert a component to a saved snapshot",
    promptGuidelines: [
      "Use project_restore_component to revert a component to a prior snapshot (from project_list_snapshots / a returned snapshot_id).",
      "The current component subnet is destroyed and replaced with the snapshot copy; external anchor wires reconnect automatically.",
    ],
    parameters: Type.Object({
      core_path: Type.String({ description: "Path to the edini::project SOP HDA instance." }),
      component_id: Type.String({ description: "The component subnet to restore into." }),
      snapshot_id: Type.String({ description: "The snapshot id (from project_snapshot_component / project_list_snapshots)." }),
    }),
    async execute(_id: string, params: { core_path: string; component_id: string; snapshot_id: string }) {
      return forwardTool("project_restore_component", params);
    },
  },
  {
    name: "project_list_snapshots",
    label: "List Component Snapshots",
    description:
      "List component snapshots in the core's _snapshots store. Pass component_id to filter to one component, " +
      "or omit to list all. Returns [{id, component, label}].",
    promptSnippet: "List saved component snapshots",
    promptGuidelines: [
      "Use project_list_snapshots to see available snapshots before restoring (or to find a snapshot_id).",
    ],
    parameters: Type.Object({
      core_path: Type.String({ description: "Path to the edini::project SOP HDA instance." }),
      component_id: Type.Optional(Type.String({ description: "Filter to one component's snapshots. Omit for all." })),
    }),
    async execute(_id: string, params: { core_path: string; component_id?: string }) {
      return forwardTool("project_list_snapshots", params);
    },
  },
  {
    name: "project_capture_archetype",
    label: "Capture Component as Archetype",
    description:
      "Phase 5b — capture a successfully-built component subnet as a reusable ARCHETYPE spec. " +
      "Walks the component, drops scaffold/anchor/marker plumbing, and emits one node op per " +
      "archetype-owned node + a wire_out. ch() expressions referencing a declared design_param " +
      "are recovered as parametric refs (re-emitted as relative ch(), depth-robust + migratable); " +
      "literal values are baked. The captured spec is saved to the sidecar registry and is " +
      "IMMEDIATELY usable by project_emit_component. Opt-in only — capture components you judge " +
      "reusable across projects (a clean tabletop, a wheel) once they verify clean.",
    promptSnippet: "Turn a reusable component into a parametric archetype",
    promptGuidelines: [
      "Only capture a component AFTER it verifies clean (project_finalize / verify_parametric pass) — capturing propagates whatever is there.",
      "Pick a generic name (e.g. 'panel', 'spoke', 'bracket'), not a project-specific one — the archetype should read across projects.",
      "The captured archetype requires the design_params it references — only re-emit it on a project that declares those same params.",
      "Re-use immediately: project_emit_component(archetype=<name>) works the moment capture returns success.",
    ],
    parameters: Type.Object({
      core_path: Type.String({ description: "Path to the edini::project SOP HDA instance." }),
      component_id: Type.String({ description: "The built component subnet to capture." }),
      name: Type.String({ description: "Archetype name (generic, reusable — e.g. 'panel', 'spoke')." }),
      description: Type.Optional(Type.String({ description: "Human description of what this archetype builds." })),
      recover_param_refs: Type.Optional(Type.Boolean({ description: "Recover ch() refs to design_params as parametric refs (default true).", default: true })),
    }),
    async execute(
      _id: string,
      params: { core_path: string; component_id: string; name: string; description?: string; recover_param_refs?: boolean }
    ) {
      return forwardTool("project_capture_archetype", params);
    },
  },
  {
    name: "project_list_captured_archetypes",
    label: "List Captured Archetypes",
    description:
      "Phase 5b — list captured (data) archetype specs in the sidecar registry " +
      "(~/.pi/agent/edini-archetypes/). Returns [{name, description, requires_design_params}]. " +
      "These are immediately usable as the `archetype` argument to project_emit_component.",
    promptSnippet: "List archetypes captured from past components",
    promptGuidelines: [
      "Use project_list_captured_archetypes to see what reusable archetypes you (or past sessions) have captured before building a similar component from scratch.",
    ],
    parameters: Type.Object({}),
    async execute(_id: string, _params: Record<string, never>) {
      return forwardTool("project_list_captured_archetypes", {});
    },
  },
];
