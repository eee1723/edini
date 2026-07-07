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
| **Changing a core parm does NOT move the geometry** | Under the design_params path (Step 2b), geometry references core parms via absolute `ch('/obj/.../project_core/<p>')`. If the parm is misspelled or the path is wrong, the reference silently evals to 0 → zero/flat geometry. | Run `verify_parametric(param="length", ...)` — it perturbs the parm and reports whether the geometry moved. If `passed:false`, the `ch()` reference is broken. Check the exact core path (in every message's `[Current Houdini Context]` block) and the parm name against the design_params declaration. |
| **`project_promote_params` returns `promoted: []` (zero items)** | **This is correct, not a failure**, under the design_params path (Step 2b). `promote` lifts *subnet spare parms* to the core; but you reference design params directly via absolute `ch()`, so you never create subnet spare parms — there is nothing to promote. | Nothing to fix. The design params already live on the core and geometry already references them. The LIVE guarantee is checked by `verify_parametric` (Step 4), NOT by promote. Do NOT call promote expecting it to "fix" parametricity. (Promote is only relevant if you took the legacy bottom-up path of building subnet spare parms — which Step 3 no longer teaches.) |
| **Component breaks when copied to another project** | Absolute `ch('/obj/geo1/project2/...')` ties the component to its current project path. Copying the subnet to project3 leaves stale references → broken geometry. | Call `project_repath_to_relative(component_id="<id>")` BEFORE copying — it rewrites the component's absolute core references to relative (depth-computed, typically `ch("../../<p>")`). The copied component then cooks anywhere a `<project_core>` node sits at the same relative depth. |
| **Python SOP cooks empty / `'return' outside function`** | A bare top-level `return` inside the Python SOP `python` parm. The cook code runs as a module body, not inside a `def`, so `return` is a SyntaxError and the whole SOP silently produces nothing. | Wrap the entire body in `if inputs and inputs[0].geometry().points():` — never use bare `return`. See `COMPONENT_TEMPLATE.md` rule 1. |
| **`AttributeError` / `Error running Python code` on `setAttribValue`** | You called `prim.setAttribValue("width", x)` before `geo.addAttrib(...)` created the attribute. Attributes must exist on the detail before you write per-element values. | Declare EVERY attribute you'll write (`addAttrib`) at the top of the body, before any `setAttribValue`. See `COMPONENT_TEMPLATE.md` rule 2. |
| **Python SOP reads 0 points from "its geometry"** | You read `node.geometry().points()` — but `node.geometry()` is the OUTPUT detail you're building (empty after `geo.clear()`), not the input. | Read the upstream anchor via `node.inputs()[0].geometry().points()`. See `COMPONENT_TEMPLATE.md` rule 3. |
| **`createPoint() takes 1 positional argument but 2 were given`** | `geo.createPoint(hou.Vector3(...))` — createPoint takes NO arguments; it creates a point at the origin and returns it. | `pt = geo.createPoint(); pt.setPosition(hou.Vector3(x,y,z))`. See `COMPONENT_TEMPLATE.md` rule 4. |
| **Python SOP param reads as 0 or `NameError: name 'ch' is not defined`** | You used bare `ch(...)` (an Hscript expression function) inside a Python SOP cook body. It only resolves in parameter-expression context, not Python. | Use `hou.ch('/obj/.../project_core/<name>')` (absolute path, `hou.`-prefixed). See `COMPONENT_TEMPLATE.md` rule 5. |
| **You spent many steps reconnecting a cross-component wire that was correct** | You distrusted the scaffold's `ports.in` wiring and tried to reconnect the filter nodes / dropped to a sandbox setInput, breaking the chain. The scaffold wires `setInput(i, upstream, from_port)` correctly from the declaration. | Read `build_project_scaffold`'s returned `input_wires[]` — it reports the ACTUAL connection state (`wired`, `port_matches`, `carries`, `internal_chain_ready`). If `port_matches:true`, the wire is good; don't touch it. See Layer A / session-logs-analysis. |
| **`by_name` anchor cook errors with "marker 'X' not found"** | The `by_name` measure picks a point by its `@name` tag from the root generator. The marker name you passed doesn't exist in the upstream geometry — usually a typo, or the generator forgot to emit `@name=<marker>` at a real location. (Previously this failed silently with 0 points; it now hard-errors via VEX `error()` so you can tell "marker not found" from "upstream empty".) | Check the marker spelling against what the root generator actually emits. The generator must output a point tagged `@name="head_tube_top"` (etc.) at the real coordinate; then `project_add_anchors(measure="by_name", marker="head_tube_top")` picks that exact point. The error message names the missing marker. |
| **`verify_parametric` reports `passed:false` but the param is fine / scene looks unchanged after the check** | Two possibilities: (a) the `ch()` reference from geometry to the core param is broken (wrong path/name) — the param exists but doesn't reach the geometry; (b) you're checking the wrong node. The tool ALWAYS restores the param to its original value after the check (non-destructive) — even if the perturbed cook errors, the finally restores it, so the scene is never mutated by a check. | If `passed:false` with a "no bbox axis changed" reason, the `ch()` chain is broken — run `verify_parametric` again after fixing the reference. The `restored:true` field confirms the param was put back. |

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
