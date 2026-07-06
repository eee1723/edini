# Mistakes & Failure Modes — Project Modeling

> Read this when a tool errors, geometry looks wrong, or the model does not
> behave parametrically. Each row: **symptom → root cause → fix**.
> Vocabulary: `measure` / `anchor` / `scaffold` (see SKILL.md leading words).

## Quick diagnosis table

| Symptom | Root cause | Fix |
|---|---|---|
| **Anchors don't move when you resize the component** | You hardcoded `addpoint(x,y,z)` instead of measuring. The platform guard refuses this with `Refused: measure violation`. | Use `project_add_anchors` — anchors are measured from the bbox on every cook. NEVER hardcode anchor coordinates. |
| **`Refused: measure violation ... hardcoded addpoint`** | The platform guard (`guards.py`) caught `addpoint()` inside a Project HDA component subnet. This is Guardrail 2 made executable. | Replace the hand-written addpoint with `project_add_anchors`. If it is genuinely NOT an anchor (rare), add `// edini-bypass-anchor-guard` to the snippet. |
| **`Refused: ... internal scaffold node ... '__' prefix`** | You tried to edit a node the builder owns (`out_geometry`, `output_0`, `__edini_axis_bake`, etc.). The `__` prefix marks platform-owned nodes. | Edit `tag_component` in the same subnet instead (for component_id / per-component attribs). For axis, update the declaration's `axis` and re-scaffold. |
| **Box can't read a param (zero geometry, "Bad parameter reference")** | Relative `ch("../../length")` across subnet nesting is unreliable. | Use ABSOLUTE paths: `ch('/obj/.../project_core/length')`. The core_path is in the `[Current Houdini Context]` block of every message. |
| **`connect_nodes` can't reach the anchor cloud** | You used the default `output_index=0` (main geometry). Anchors are on port 1. | Pass `output_index=1` to reach the upstream component's anchor cloud. See `PORT_PROTOCOL.md`. |
| **Components float in space, disconnected** | Missing `ports.in` — the builder created no input port, so the downstream component cannot consume upstream anchors. | Declare the dependency in `ports.in` at scaffold time (Guardrail 1). Draw the dependency graph first. |
| **Param has no min/max on the core after promote** | The subnet spare parm was created without min/max. | Add the spare parm on the subnet WITH min/max (FloatParmTemplate), then `project_promote_params` copies them up. Or use step 2b `design_params` (min/max built in). |
| **`project_create` made a new HDA instead of using the selected one** | A stale selection was in the network editor. | Deselect first, or pass the intended core explicitly. |
| **Built geometry but nothing shows at core OUT** | Your geometry never feeds into `out_geometry` → `output_0` → core's OUT merge. | Connect the last geometry node → the subnet's `out_geometry` null. |
| **`verify_orientation` fails with 90° axis mismatch** | The declared `axis` doesn't match how the geometry is actually generated (e.g. a backrest facing +Z declared as `Y`). | Update the declaration's `axis` (e.g. `"Z"`) and re-run `project_build_scaffold`. Do NOT edit `__edini_axis_bake` (it's locked; declaration is source of truth). |
| **Changing a core parm does NOT move the geometry** | The two-layer `ch()` chain is broken — a relative path failed silently, or a subnet parm was never created. | Verify each promoted parm: core `<component>_<parm>` → subnet `ch("../<component>_<parm>")` → geometry node `ch("../<parm>")`. Step 4's completion criterion catches this. |

## Lessons from real incidents

### The chair addpoint incident (why `measure` is platform-enforced)

**What happened:** While modeling a chair, the agent hand-wrote
`addpoint(0, 0.5, 0)` inside the backrest subnet to place a mount anchor. The
geometry cooked correctly once. But when the user changed the seat height
design param, the backrest anchor stayed at `y=0.5` — disconnected from the
geometry that had moved. The agent then tried to "fix" it by editing the
locked `__edini_axis_bake` node (refused), passing `construction_axis`
(ignored by the then-current backend), and cascaded through 5 wasted tool
rounds before giving up.

**Root cause:** Hardcoded coordinates are not parametric. The agent's mental
model ("I need a point here") did not match the parametric requirement ("the
point must follow the geometry").

**Fix:** `guards.py` now refuses `addpoint()` inside Project HDA component
subnets with `Refused: measure violation`. The agent is forced to use
`project_add_anchors`, which emits a VEX wrangle that measures the bbox on
every cook. The leading word `measure` appears in the skill, the tool
description, AND the refusal message — so the agent sees the same vocabulary
whether it learns the rule, calls the tool, or hits the guard.

### The relative-path zero-geometry bug

**What happened:** A box inside `tabletop/` referenced `ch("../../length")`.
Across subnet nesting, Houdini resolved this to a non-existent parm, emitted a
"Bad parameter reference" warning, and the box sized to zero — silent failure.

**Fix:** Always use ABSOLUTE `ch()` paths (`ch('/obj/.../project_core/length')`).
The core_path is provided in every message's context block.

### The "premature done" pattern

**What happened:** The agent built the tabletop and two of four legs, then
declared the model complete. The remaining two legs and all anchors were
missing.

**Fix:** Every workflow step now ends with a **✅ completion criterion** that is
checkable. Step 3 requires *every* declared anchor to be emitted and
`verify_orientation` to pass — so "I built some of it" cannot be mistaken for
"done".
