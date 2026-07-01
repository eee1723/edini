// pi-extensions/edini-tools/tools/rooted.ts
// Rooted-modeling tool — the Root → Measure → Mount → Shape assembly builder.
//
// An *assembly* describes a procedural object where a leaf's placement is
// DERIVED by measuring the root's real geometry, not hardcoded as coordinates.
// This is the redesign of the archived declarative-asset pipeline: positions
// come from measurements (bbox corners/face centers, edge parametric points),
// so when the root changes shape the leaves move with it automatically.
//
// Four roles:
//   root   — the foundational component (a native SOP box/tube/...). Its cooked
//            geometry is the single source of truth for everything below.
//   mount  — a {position, orient} measured off the root (or a sibling). Never
//            a hardcoded coordinate. position.measure ∈ {bbox_corner,
//            bbox_face_center, bbox_center, point_on_edge}; orient optionally
//            derived from a measured direction between two points.
//   shape  — a self-contained leaf asset (a wheel, a keycap, a door). Its FORM
//            is independent of the root; only its PLACEMENT is derived.
//   leaf   — a shape placed onto a mount (optionally scaled by a param expr).

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

export const buildAssembly = {
  name: "build_assembly",
  label: "Build Rooted Assembly",
  description:
    "Build a procedural model where leaves attach to the ROOT by MEASURING its real geometry — " +
    "no hardcoded coordinates. The build is LIVE: each mount is an attribwrangle that reads the root's " +
    "bbox via getbbox_min/max on every cook, and leaves are stamped by copytopoints. Every root-shape " +
    "param becomes an editable spare parm on the container, so changing a param in the Houdini UI " +
    "updates the whole model live WITHOUT rebuilding — e.g. change a car's 'length' and the wheels " +
    "slide to the new measured corners automatically. The root is a native SOP (box/tube/torus/...) " +
    "built first; each mount derives its position(s) from a measurement of that cooked geometry. " +
    "Single-point measures: bbox_corner '+X-Y+Z', bbox_face_center '+Y', bbox_center, point_on_edge. " +
    "Multi-point measures (fan one leaf out to MANY instances): grid_on_face {face, rows, cols, margin} " +
    "lays a key/window grid across a face; array {origin, count, step} steps a lattice of treads. " +
    "Orientation is a quaternion via dihedral (the leaf's +Y faces the measured direction). " +
    "Pass an inline 'assembly' dict. Returns OUT path + sandbox_root + mount/leaf ids. Assembly shape: " +
    "{id, params:{name: number|{default}}, root:{shape:{type:'box'|'tube'|'torus'|'sphere', params:{parm: value|expr}}}, " +
    "mounts:[{id, position:{measure:'bbox_corner'|'bbox_face_center'|'bbox_center'|'point_on_edge'|'grid_on_face'|'array', from:'root', ...kind_fields}, orient?:{from:'root', from_a:{...}, from_b:{...}}}], " +
    "leaves:[{id, mount:<mount_id>, shape:{type, params} | {chain:[{type, params}]}, scale?:\"param_expr\"}]}. " +
    "A leaf shape may be a single SOP ({type:'box'|'tube'|'torus'|'sphere'|'grid'}) or a CHAIN of SOPs for detail " +
    "({chain:[{type:'box',params:...}, {type:'polyextrude::2.0',params:{group:'0',dist:'rim'}}, {type:'polybevel::2.0',params:{offset:0.02}}]}). " +
    "Orientation takes align_axis ('+Y' default, the leaf axis mapped onto the measured direction — a torus wheel's symmetry axis is +Y so it stands on its axle). A leaf may declare origin:{anchor:'bbox_center'|'bbox_face:±XYZ'|[x,y,z], offset:[x,y,z]} to normalize its pose before copy (clear the root). Identical leaves auto-group onto one shape + one CTP.",
  promptSnippet: "Build a rooted model: leaves placed by MEASURING the root's geometry (no hardcoded coords)",
  promptGuidelines: [
    "CORE PRINCIPLE: never write a coordinate. A leaf's position is a MEASUREMENT of the already-cooked root " +
      "(bbox_corner '+X-Y+Z', bbox_face_center '+Y', or point_on_edge at t∈[0,1]). Change a param and the leaf moves automatically.",
    "First build the ROOT — the one component everything hangs off. A car's platform, a keyboard's tray, a building's mass. " +
      "It is a native SOP whose size reads from params (e.g. box size ['length','thickness','width']).",
    "Then declare MOUNTS by measuring the root. A wheel at a corner = position.measure 'bbox_corner' axes '+X-Y+Z'. " +
      "A key on a tray = 'bbox_face_center' face '+Y'. A door along a wall = 'point_on_edge' axes_a/axes_b + t=0.3.",
    "A mount's ORIENT (optional) is also derived: give two measured points and the builder computes the direction the " +
      "leaf's built +Y axis should align to. A wheel's axle = the direction between two opposite corners along the long edge.",
    "FAN-OUT: a multi-point mount (grid_on_face or array) places ONE leaf definition at MANY positions. A keyboard = " +
      "one keycap shape + a grid_on_face mount → rows*cols keys, each at a measured grid point. Declare the shape once.",
    "A LEAF's shape is independent of the root (a torus wheel, a box keycap) — only its placement is derived. " +
      "Scale it with a param expression (e.g. scale:'wheel_radius') so size stays parametric too.",
    "The build is LIVE: every root-shape param is an editable spare on the container. After building, open the sandbox " +
      "in Houdini, change a root param (e.g. a car's 'length'), and the whole model updates WITHOUT rebuilding — wheels " +
      "slide to the new measured corners, the key grid re-samples the face. If it doesn't move live, the mount was mis-specified. " +
      "NOTE: ALL params are live — root-shape (length/width), leaf-shape (wheel_radius, cabin_length), leaf scale, and origin offset all re-cook when tweaked. Only mount internals (grid rows/cols/margin, array step) are baked at build and need a rebuild to change.",
    "Use commit_sandbox(sandbox_root, <name>) to make it permanent. The sandbox reuses Houdini's standard lifecycle.",
  ],
  parameters: Type.Object({
    assembly: Type.Optional(
      Type.Record(Type.String(), Type.Unknown(), {
        description:
          "Inline assembly JSON. Provide this OR assembly_path. " +
          "Shape: {id, params, root:{shape}, mounts:[], leaves:[]}.",
      })
    ),
    assembly_path: Type.Optional(
      Type.String({
        description: "Path to an assembly JSON file (alternative to inline 'assembly').",
      })
    ),
    sandbox_name: Type.Optional(
      Type.String({
        description: "Name hint for the sandbox geo container (default 'assembly').",
      })
    ),
  }),
  async execute(
    _toolCallId: string,
    params: { assembly?: Record<string, unknown>; assembly_path?: string; sandbox_name?: string }
  ) {
    return forwardTool("build_assembly", params);
  },
};

export const rootedTools = [buildAssembly];
