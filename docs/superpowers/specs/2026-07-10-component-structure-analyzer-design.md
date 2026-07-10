# Component Structure Analyzer — Design

- **Date:** 2026-07-10
- **Status:** Approved (design) — pending implementation plan
- **Owner:** eee
- **Builds on:** `2026-07-03-modeling-discipline-refinement-design.md` (check-layer), `2026-07-02-project-component-foundation-design.md` (component scaffold)

## 1. Motivation

Two models (deepseek-v4-pro, glm-5.2) each built the same three tasks
(bicycle / table / cake). Analysis of the six session logs surfaced a class of
**construction-quality failures that the existing check-layer does not catch**,
plus a **gate-integrity failure** that let broken models ship:

### 1.1 Construction failures the current tools missed

| Failure | Evidence (verified in logs) | Why it slipped through |
|---|---|---|
| Wheel built as a Python SOP, wrong axis, no CTP | deepseek bike: `front_wheel/wheel_gen` + `rear_wheel/wheel_gen`, both `type=python`; `verify_orientation` **never called** | No gate enforces orientation in the project path; nothing flags Python-SOP geometry |
| Bare open curves at component OUT | glm bike: `frame/out_geometry` 103pts/60prims with `curve_name` prim attr; same at `crankset` (PolyWire node exists but OUT is wired to the curve) | `inspect_health.open_curves` only flags **unclosed** curves, not "curve prims present at OUT" |
| CTP'd candles pointing wrong way | deepseek cake: `copy_candles`=copytopoints, target points have no `orient`/`N`/`up` | No check verifies CTP target-point orientation attributes |
| Repeated parts duplicated instead of CTP'd | deepseek wheels = two hand-built Python subnets; spokes hand-emitted | `_check_modular_structure` detects monolithic Python but only runs in the **sandbox/commit** path, not `project_finalize` |
| Detail params falsely flagged dead | `frosting_overhang`, `top_radius`, `tube_radius` failed `verify_parametric` at OUT | `project_finalize` always points `verify_parametric` at the aggregate OUT, whose bbox is dominated by the largest component |

### 1.2 Gate-integrity failure

`project_finalize` finalization outcomes across the 6 sessions:

| | deepseek | glm |
|---|---|---|
| bicycle | fail→fail→**skip** | fail→**skip** |
| table | clean pass (only one) | fail→clean pass |
| cake | fail→fail→**skip** | fail→pass (**state-JSON edited to pass**) |

- **0/6 first-pass clean finalizes.** 4/6 "finished" only by bypassing the gate
  (3 via `acknowledge_skip` escape hatch, 1 by editing `__edini_state` to widen
  a param range so the bbox test passed).
- `project_finalize` runs only **status + robust + parametric(OUT)**. It does
  NOT run orientation, health, or any structural check, and `acknowledge_skip`
  bypasses all three gates it does run.
- The **sandbox** path (`commit_sandbox`) already runs structure +
  orientation gates (`harness._check_modular_structure`,
  `_run_orientation_gate`). The project path is weaker than the sandbox path.

### 1.3 Root cause

The construction tools (create_node / set_param / connect) are **complete at the
low level** — glm proved Copy-to-Points works for spokes. The gaps are:

1. **No interpretation layer.** The agent already had rich state (deepseek
   called `list_nodes`×6, `inspect_geo`×11 on the bike and still missed the
   Python-SOP wheel). Raw dumps don't yield the signal; **interpreted verdicts**
   do. (Vision is rejected as primary channel — see §9.1.)
2. **Checks wired to the wrong gate.** Structure/orientation checks exist but
   only in sandbox; `project_finalize` is under-gated and skip-bypassable.

## 2. Goals & Non-Goals

### Goals

- **G1.** A per-component structural analyzer that turns node-graph + geometry
  state into **interpreted verdicts** (fatal / advisory / clean) for exactly the
  failure modes in §1.1.
- **G2.** A closed **declare → verify** loop: structural intent declared at
  plan/scaffold time, verified at finalize. Declaration is **required** (plan-time
  lint refuses to scaffold a component missing/inconsistent intent) — the
  shift-left that prevents building broken parts in the first place.
- **G3.** The fatal subset becomes `project_finalize` **Gate 4**, immune to
  `acknowledge_skip`. Closes the gate-integrity failure from §1.2.
- **G4.** Reuse, not reinvent: generalize `harness._check_modular_structure`'s
  node-graph walk into shared helpers used by both sandbox and project paths.

### Non-Goals (explicitly out of scope)

- **Visual / viewport feedback** as a primary state channel (rejected — §9.1).
  An optional gestalt-render complement may be a separate future spec.
- **Broader plan enrichment** (component decomposition, anchor topology,
  dimension chains). The user flagged this as a larger separate work surface;
  this spec covers only **structural intent** declaration.
- **New low-level construction tools / L2 part-helpers** (`make_radial_part`
  etc.). These are the "make wrong states unconstructable" layer and remain a
  follow-on; this spec is the detection + enforcement layer.
- **Changing which checks `inspect_health` does.** Its geometry-topology
  contract stays as-is; the analyzer is a separate, node-graph-aware tool.

## 3. Architecture Overview

```
                      plan/scaffold (shift-left)
   project_plan ──▶ project_build_scaffold ──▶ component subnet built
                          │  (lint: structure intent REQUIRED,
                          │   refuse if missing/inconsistent)
                          ▼
                   component lives in __edini_state.components[].structure
                          │
   ┌──────────────────────┼──────────────────────────────────────┐
   │  analyze_component_structure(core_path, component_id?)       │
   │   reads: node graph (SOP types, CTP nodes)                   │
   │          geometry (prim types, PCA axis, baked edini_world_axis) │
   │          declared intent (components[].structure)            │
   │   emits: fatal[] / advisory[] / signals{}                     │
   └──────────────────────┬──────────────────────────────────────┘
                          │
            ┌─────────────┴──────────────┐
            ▼                            ▼
   agent self-check (anytime)    project_finalize Gate 4
   advisory + fatal reported     fatal non-empty ⇒ finalized:false
                                 IMMUNE to acknowledge_skip
```

New module **`edini/structure.py`** exports `analyze_component_structure(...)`.
Two consumers call the same function: the standalone tool (agent self-check)
and `project_finalize` Gate 4.

Shared helpers (factored out of `harness._check_modular_structure`):
`_walk_component_sops(subnet)`, `_classify_sop(node)` (python / modular /
postprocess / generator), `_geometry_component_ids(geo)`. Both sandbox
`_check_modular_structure` and the new analyzer import these — no logic fork.

## 4. Structural-Intent Declaration (the input)

Added to the per-component spec accepted by `project_build_scaffold`, persisted
in `__edini_state.components[].structure`:

```jsonc
{
  "id": "front_wheel",
  "structure": {
    "kind": "radial",            // radial | planar | repeated | solid
    "expected_axis": "Z",        // required for radial | planar
    "repeats": [                 // repeated sub-parts + construction method
      {"part": "spoke", "count": 28, "method": "copytopoints"},
      {"part": "tire",  "count": 1,  "method": "sweep"}
    ]
  }
}
```

- `kind` semantics:
  - `radial` — disc/ring geometry (wheel, gear): has a well-defined axle axis.
  - `planar` — flat sheet (tabletop): has a normal axis.
  - `repeated` — N identical sub-parts (spokes, candles, legs).
  - `solid` — single-piece (a box body); no structural rules.
- `repeats[].method` ∈ `{copytopoints, sweep, foreach, stamp}` — the declared
  construction method for each repeated sub-part. `copytopoints` is the default
  the SKILL will steer toward for discrete repeated parts.

### 4.1 Plan-time lint (REQUIRED — decision A)

`project_build_scaffold` runs a lint on each component's `structure` and
**refuses to scaffold** (returns a structured error, no nodes created) when:

- `structure` block is entirely missing (not a `solid` default — explicit).
- `kind` ∈ {radial, planar} but `expected_axis` absent.
- `repeats` declared with `method: copytopoints` but no `repeats` entries, or
  `count < 2` on a `copytopoints` method (contradiction).
- `repeats` absent but `kind: repeated` (contradiction).

The refusal reuses the `guards.py` pattern: structured dict with `suggested_fix`
and a `schema_hint` showing the correct `structure` shape. This is the
shift-left: the agent cannot start building a wheel without first declaring
axis=Z + CTP-spokes, so the §1.1 wheel failures become unconstructable by plan.

**Migration / legacy:** components on pre-existing cores without `structure`
are handled by the inference fallback (§6.2) at verify time — the lint only
fires on new scaffold builds, so it does not block already-built projects.

## 5. The Analyzer — Signals Read

`analyze_component_structure(core_path, component_id=None)`:

- If `component_id` given, analyze one component subnet; else analyze all.
- For each component subnet, gather:

**Node-graph signals** (from the subnet, via shared helpers):
- `python_sops` — paths + line counts of Python SOPs that emit geometry.
- `ctp_nodes` — Copy-to-Points nodes (incl. `copytopoints::2.0`).
- `modular_nodes` — sweep/foreach/boolean/polyextrude/etc. (`_MODULAR_NODE_TYPES`).
- `out_wired_to` — the node type the component's `out_geometry` null is fed by.

**Geometry signals** (from `out_geometry` cook):
- `prim_types` — count by prim type name (Poly / NURBSCurve / PolyLine / Bezier / …).
- `principal_axis` — PCA / extent-derived dominant axis; for radial parts, the
  **thin** axis (smallest extent) is the candidate axle.
- `baked_axis` — read the `edini_world_axis` prim attribute baked by the
  scaffold's internal `__edini_axis_bake` node.
- `ctp_target_attrs` — for each CTP node, the attribute names present on its
  target-point input geometry (`orient` / `N` / `up` / none).

**Declared-intent signals** (from `__edini_state.components[].structure`):
- `declared_kind`, `declared_axis`, `declared_repeats`.

## 6. Verdict Rules

Two grades: **fatal** (blocks finalize, immune to skip) and **advisory**
(reported + audited, never blocks).

### 6.1 Fatal rules (F1–F4) — declared → deterministic

| Rule | Condition | Detection |
|---|---|---|
| **F1 bare_curves_at_out** | component `out_geometry` contains curve/NURBS/polyline/bezier prims | scan `prim_types`; any curve-like ⇒ fatal |
| **F2 repeat_no_instancing** | declared `repeats[].method` ∈ {copytopoints, foreach, stamp, copy} (an instancing method) but no node of that type in subnet; **or** inferred repeated sub-geometry (≥2 similar pieces) with no instancing node | declared path: deterministic. inferred path: similar-piece/PCA heuristic with confidence. (Surfacing methods sweep/polywire are covered by F1 — an unsurfaced curve reaches OUT and trips F1.) |
| **F3 axis_mismatch** | `kind` ∈ {radial,planar} and `baked_axis` ≠ `expected_axis` (tolerance 15°) | `baked_axis` (`edini_world_axis`, how the geo was actually built) is ground truth; `principal_axis` (PCA) is a fallback signal only when no baked axis exists |
| **F4 ctp_no_orient** | subnet has `copytopoints` whose target-point input lacks all of `orient`/`N`/`up` | inspect `ctp_target_attrs` |

Each fatal verdict carries `fix` (one-line remediation) + `suggested_tool`
(mirrors `guards.py` refusal shape), so the agent learns the fix in one round.

### 6.2 Declared vs inferred (resolves the §6 PCA-misjudge risk)

- **Declared intent present** ⇒ F2/F3 are **deterministic** (no PCA guesswork):
  F2 = "you declared CTP but there is no copytopoints node"; F3 = "declared axis
  Z ≠ detected/baked axis Y". These are the common path once decision A's
  required-declaration lint is in force.
- **Declared intent absent** (legacy cores) ⇒ F2/F3 fall back to **inference**
  (PCA / similar-piece / radial detection). Inferred fatals carry a `confidence`
  field and are **overridable** via `structure_override` (§7.2) — so a
  false-positive on a genuinely atypical structure has a correct, audited exit.

### 6.3 Advisory rules (A1–A3)

| Rule | Condition | Detection |
|---|---|---|
| **A1 sibling_handbuilt** | ≥2 sibling components look like instances of the same part with no shared template | name heuristic (`front_/rear_`, `_l/_r`) + structural similarity; best-effort |
| **A2 monolithic_python** | multi-component geometry all sourced from one big Python SOP, no modular nodes | reuse `_check_modular_structure` logic, project-scoped |
| **A3 out_bbox_false_negative** | `verify_parametric` failed at aggregate OUT for a param ⇒ auto re-measure at the component the param drives (trace `ch()` or per-component perturb). Component-level pass ⇒ report "OUT度量假阴性, 组件级已验证", **downgrade to advisory, do not block** | extension of `verify_parametric` to per-component node targeting |

A3 directly repairs the §1.1 "detail param falsely dead" failures
(`frosting_overhang`, `top_radius`, `tube_radius`) without weakening the gate:
the param IS verified, just at the correct node.

## 7. Gate 4 Integration & Skip Semantics

### 7.1 Gate 4 in `project_finalize`

After the existing status / robust / parametric gates, add:

```
Gate 4 — structure:
  result = analyze_component_structure(core_path)   # all components
  collect result.fatal[] across components
  if any fatal:
      _add_failure("structure", <fatal details>, component=...)
      # NOT bypassable by acknowledge_skip (see 7.2)
```

`project_finalize` return gains `checks.structure = {fatal:[...], advisory:[...]}`.

### 7.2 Skip / override semantics (closes §1.2)

- `acknowledge_skip=True` bypasses **only** Gate 1–3 (status/robust/parametric).
  It does **NOT** bypass Gate 4 fatal verdicts. (Today it bypasses everything;
  this is the core fix.)
- A new explicit **`structure_override=True`** arg is required to bypass a
  Gate 4 fatal. It demands a `structure_reason`, is audited to the declaration
  log as `structure_override` (distinct from `finalize_skip`), and is the single
  correct exit for an inferred false-positive or a genuinely atypical structure.
- This makes the deepseek/glm skip-hatch behavior impossible for structural
  defects while preserving an honest escape valve. The glm `__edini_state`
  edit-to-pass maneuver (§1.2) is also blocked because Gate 4 reads actual
  cooked geometry + actual node graph, not the editable declaration, for the
  axis/curve/CTP facts (the declaration is used only to know what to expect).

## 8. Tool Surface

### 8.1 Python handler

`TOOL_HANDLERS` (tool_executor.py) entry:

```python
"analyze_component_structure": lambda **kw: analyze_component_structure(
    kw["core_path"],
    component_id=kw.get("component_id"),
),
```

### 8.2 LLM-facing schema

New TS descriptor in `pi-extensions/edini-tools/tools/project.ts` (where sibling
project tools' schemas live), exposing `core_path`, optional `component_id`,
and the docstring describing the verdict report.

### 8.3 Return shape

```jsonc
{
  "success": true,
  "core_path": "/obj/geo1/project4",
  "component_id": "front_wheel",      // null when scanning all
  "overall": "fatal",                 // fatal | advisory | clean
  "fatal": [
    {"rule": "F2_repeat_no_ctp",
     "detail": "declared repeats[{spoke,28,copytopoints}] but no copytopoints node in subnet; geometry emitted by python SOP 'wheel_gen'",
     "fix": "Build one spoke template + Copy-to-Points onto a scatter ring.",
     "suggested_tool": "houdini_create_node",
     "confidence": "declared"}
  ],
  "advisory": [
    {"rule": "A2_monolithic_python", "detail": "...", "fix": "..."}
  ],
  "signals": {
    "python_sops": [{"path":".../wheel_gen","lines":312}],
    "ctp_nodes": [],
    "prim_types": {"Poly": 462},
    "principal_axis": "Y",
    "baked_axis": "Z",
    "ctp_target_attrs": {},
    "declared": {"kind":"radial","expected_axis":"Z","repeats":[{"part":"spoke","count":28,"method":"copytopoints"}]}
  }
}
```

`project_finalize` Gate 4 consumes only the `fatal` lists across components.

## 9. Rejected Alternatives

### 9.1 Vision as the primary state channel

Rejected. Vision→text→LLM is lossy for the bug classes here ("wheel axle along
Z?" is guessed by a VLM; node-graph topology is invisible in a screenshot).
Hard counter-evidence: deepseek already held full state (list_nodes×6,
inspect_geo×11) and still missed the Python-SOP wheel — the gap is
**interpretation**, not acquisition. Vision is demoted to an optional gestalt
complement for a future spec. The right channel is structured instrumentation
sensed at the abstraction layer where each bug lives.

### 9.2 Folding the checks into `inspect_health`

Rejected. `inspect_health` is geometry-topology only (point/prim defects) with a
deliberate two-tier contract. The new checks need **node-graph** analysis
(SOP types, CTP presence) — a different concern. Mixing them would bloat
`inspect_health` and blur its "viewport-invisible topology defects" boundary.

### 9.3 Advisory-only analyzer (option A from brainstorming)

Rejected. An advisory-only tool is ignorable — deepseek ignored
`verify_orientation` entirely. The fatal subset must be an un-skippable gate to
have effect.

## 10. Testing & Acceptance

### 10.1 Pure-logic unit tests (no hou)

F1–F4 detection predicates unit-tested with constructed fake geometry / fake
node graphs, following the existing offline-test pattern in `verify.py` /
`geometry_inspect.py`. Plan-time lint predicates (`structure` validation) are
pure-Python and fully unit-tested via `project/state.py`-style fakes.

### 10.2 Real-Houdini regression (acceptance bar)

The four crashed components from the logs become regression fixtures:

| Fixture (from session) | Required verdict |
|---|---|
| deepseek bike — `front_wheel` / `rear_wheel` (python SOP, no CTP) | **F2 fatal** (+ F3 if axis wrong) |
| deepseek cake — `candles` (CTP, no orient) | **F4 fatal** |
| glm bike — `frame` / `crankset` (bare curves at OUT) | **F1 fatal** |
| deepseek table — `legs` (clean CTP) | **clean** |
| glm table — `legs` (clean CTP) | **clean** |

Plus a finalize-level test: a project with any fatal verdict must return
`finalized:false` **even with** `acknowledge_skip=True`, and must pass only with
`structure_override=True` + `structure_reason`.

### 10.3 A3 regression

`frosting_overhang`-style param (passes at component, fails at aggregate OUT)
must be reported as advisory "OUT false-negative, component-level verified" and
must **not** block finalize.

## 11. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| F2/F3 inference misjudges atypical structures | Required-declaration (decision A) makes the common path deterministic; inference only for legacy, with `confidence` + `structure_override` exit (§6.2, §7.2) |
| Required lint slows simple models / raises barrier | `solid` default + SKILL.md guidance + the lint error itself teaches the correct `structure` shape in one round (guards.py pattern) |
| Gate 4 fatal blocks a legitimate non-standard build | `structure_override` + `structure_reason`, audited distinctly from skip |
| A3 per-component re-measure adds finalize latency | Re-measure only the params that failed at OUT (not all); reuse the existing perturb/restore machinery |
| Generalizing `_check_modular_structure` breaks sandbox path | Shared helpers extracted behind the same signatures; sandbox `_check_modular_structure` keeps its return contract, just delegates to helpers; covered by existing sandbox tests |

## 12. Implementation Surface (for the writing-plans step)

- `edini/structure.py` — new module: `analyze_component_structure`, shared
  helpers factored from `harness._check_modular_structure`.
- `edini/harness.py` — `_check_modular_structure` refactored to delegate to
  shared helpers (no behavior change to sandbox).
- `edini/verify.py` — `project_finalize` gains Gate 4 + `structure_override`
  semantics; A3 per-component parametric re-measure.
- `edini/project/builder.py` — `project_build_scaffold` accepts + persists
  `components[].structure`; plan-time lint.
- `edini/project/state.py` — `structure` in the component schema (no schema
  version bump required; additive field).
- `edini/tool_executor.py` — `TOOL_HANDLERS` entry for
  `analyze_component_structure`.
- `pi-extensions/edini-tools/tools/project.ts` — LLM-facing tool descriptor.
- `skills/project-modeling/SKILL.md` — document the required `structure`
  declaration + the new tool (the agent reads this before building).
- `tests/` — pure-logic + real-Houdini regression per §10.

## 13. Open Questions (to resolve in the implementation plan, not blocking)

1. **A1 detection specificity** — name heuristic (`front_/rear_`) vs structural
   similarity. Start with name heuristic (cheap, low false-positive), revisit if
   it misses real cases.
2. **`expected_axis` source of truth** — RESOLVED in §6.1: `baked_axis`
   (`edini_world_axis`) is ground truth for F3 (it reflects how the geo was
   actually constructed); `principal_axis` (PCA) is a fallback only when no
   baked axis exists.
3. **Whether A3 belongs in this spec's first cut** — it is the highest-value
   item for the §1.1 bbox冤案 but adds the most scope. Recommendation: include
   F1–F4 + Gate 4 + required-declaration in cut 1; A3 as cut 1.5 (same spec,
   sequenced later in the plan).
