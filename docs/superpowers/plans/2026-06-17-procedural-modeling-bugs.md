# Procedural Modeling — Known Bugs

**Source of evidence:** Session `2026-06-17T06-16-18-416Z` (task: "做一个程序化房子"),
correlated against `skills/procedural-modeling/` references and the harness code.

These are **real, reproducible** defects observed in a live run, not theoretical concerns.
Each entry cites the session event, the symptom, the suspected root cause in code, and a
concrete fix direction.

> **For agentic workers:** Pick ONE bug per task. Steps use checkbox (`- [ ]`) syntax.

---

## Bug 1 — `houdini_capture_component_detail` fails with `bbox build failed` (BLOCKER) ✅ FIXED

**Status:** Fixed 2026-06-17. Root cause confirmed + 2 related defects fixed
alongside it; regression test added.

**Severity:** HIGH — disables the only sanctioned path for verifying small/hidden parts
(`verification-protocol.md` step 5b). Without it the agent must fall back to raw
`houdini_run_python` viewport hacks, which is exactly what happened in the session.

**Observed (session):**
- 7 of 7 component-detail captures returned:
  `"All captures failed: ['window_back_l: bbox build failed', ...]"` (events 35, 36).
- The agent then tried `houdini_run_python` to rotate the viewport camera and hit two
  further API errors (`buildLookAtRotation` not on `hmath`; `setRotation` wants
  `hou.Matrix3 const &`, got a tuple) — events 39, 41. This downstream thrash is a direct
  symptom of this blocker.

**Suspected root cause:** `python3.11libs/edini/node_utils.py:2113-2121`
```python
try:
    bbox = hou.BoundingBox(
        hou.Vector3(bnds["min"]),
        hou.Vector3(bnds["max"]),
    )
except Exception:
    cell_errors.append(f"{cid}: bbox build failed")
    continue
```
`_component_bounds` (node_utils.py:836-854) returns `bounds.min`/`max` as `list[float]`
(e.g. `[-3.4, 0, -2.9]`). On Houdini 21, `hou.Vector3(list)` is accepted but
`hou.BoundingBox(min, max)` has historically been finicky about the exact sequence type it
unpacks — when the list is passed straight through, the constructor can raise, which is
swallowed by the bare `except Exception` and surfaced as the generic `bbox build failed`
with no traceback.

**Note:** the SAME `bnds` dict is consumed without issue elsewhere as plain floats, so the
failure is specifically the `BoundingBox`/`Vector3` construction path, not the data.

**Fix direction:**
- [x] Reproduce: mock now exposes `hou.Vector3` / `hou.BoundingBox`, so the
      exact failing path (`hou.BoundingBox(hou.Vector3(list), ...)`) runs under
      the test suite. Confirmed the construction was the failure point.
- [x] Replace with a robust construction that does not depend on `hou.Vector3` accepting a
      list — builds the bbox from explicit scalars:
      `hou.BoundingBox(mn[0], mn[1], mn[2], mx[0], mx[1], mx[2])` (the 6-float overload).
      `python3.11libs/edini/node_utils.py:2113`.
- [x] Surface the real exception in `cell_errors` instead of the generic string so future
      regressions are diagnosable: `f"{cid}: bbox build failed ({type}: {msg})"`.
- [x] Add a regression test: `tests/test_capture_component_detail.py` — 8 tests covering
      the 6-float overload, the legacy 2-arg overload, and end-to-end capture on a
      known-good 2-component (body + knob) asset (the case named in this bug).

### Related defects fixed in the same pass

These were uncovered *by* the regression test and are direct enablers of
"capture produces a usable output file" — both pre-existing, both latent on
real Houdini (where Pillow is normally importable so the concat path succeeds):

1. **Unguarded `viewport.settings()` call** (`node_utils.py:2060`) sat *outside*
   its try/except, so any viewport-API hiccup aborted the whole capture at the
   "get_viewer" stage with a traceback. Moved inside the best-effort shading
   block.
2. **Concat-fallback copied a temp file *after* deleting it**
   (`capture_review` ~line 1875 and `capture_component_detail` ~line 2167).
   When `_concat_images_grid` failed (e.g. Pillow unavailable/ABI-incompatible),
   the fallback `shutil.copy(captured[0], filepath)` ran after the tmp-cleanup
   loop had already removed `captured[0]`, so the fallback was a silent no-op
   and capture returned "Output not created". Reordered: copy fallback first,
   then delete tmps. Affects BOTH capture functions.

---

## Bug 2+3 (merged) — Coincident points between adjacent boxes → phantom non-manifold edges

**Severity:** HIGH — this is the root cause of the Layer-1 health-check `overall_ok: false`
that the session rationalized away. It will corrupt any future Boolean/Sweep/Subdivide.

**Observed (session event 29):**
```
overall_ok: false
nonmanifold_edges: 176   (passed: false)
coincident_points: 20    (passed: false)
open_boundary_edges: 286 (passed: false — EXPECTED for open roof bottom, not a defect)
```

### Root cause — CORRECTED (original analysis was wrong)

> **The earlier draft of this section blamed `add_box` face winding. That was incorrect.**
> Verified against the detector implementation at
> `python3.11libs/edini/node_utils.py:959-1124`:
> ```python
> def _edge_key(a, b): return (a, b) if a <= b else (b, a)   # UNDIRECTED edge
> ...
> nonmanifold = [k for k, c in edge_counts.items() if c >= 3]  # count >= 3, winding-agnostic
> ```
> The detector counts how many polygons share an **undirected** edge and flags edges
> shared by **≥ 3** polygons. It does **not** consider winding direction. An edge shared
> by exactly 2 polygons with opposite winding is healthy (count = 2). **A single isolated
> box therefore emits ZERO non-manifold edges regardless of its winding table** — every
> edge is shared by exactly 2 faces.

The true root cause is **coincident points between adjacent boxes that share a coplanar
face.** In the session's house:

- The door's inset panels have their back face at `z = depth/2 + 0.06`, which is the
  exact same plane as the door slab's front face (`z_face + dt` with `dt = 0.06`).
- Each `add_box` mints its own 8 point objects (no point reuse), so the panel's 4
  back-face corners are *distinct point numbers* at *identical positions* to slab points.
- The `coincident_points` sample `[78,97],[79,104],[82,101],[83,108],[88,103],[89,94],
  [92,107],[93,98]` = exactly the 4 back-corners of each of the 2 panels coinciding
  with slab points.
- A panel back-face edge that crosses a slab edge creates a third coincident edge segment
  in space → the geometric edge is shared by 3 polygons → flagged non-manifold.

The same pattern stacks up across chimney body+cap, window frame+mullion+glass, etc.
→ 176 non-manifold edges + 20 coincident points are **two symptoms of one bug.**

### Why the session's justification was still invalid

The session said: *"intentional overlap, no Boolean downstream, acceptable."* This is
wrong per `verification-protocol.md` step 1, which mandates fixing non-manifold edges
*unconditionally* because they "silently break Boolean/Sweep/subdivision downstream."
A procedural house is very likely to be Boolean'd (window cutouts) or subdivided (roof
bevel) later, at which point these 176 edges produce garbage topology.

### Fix direction (single effective fix)

- [x] **Document `fuse` + `clean` as the recommended postprocess health chain** in
      `references/declarative-builder.md`. `fuse` merges coincident points; `clean`
      removes the residual non-manifold/degenerate geometry. Both already resolve in the
      harness (`harness.py:2289-2308` is generic — any `type` string works) and are
      registered in the H21 manifest.
- [x] **Add a canonical `add_box` helper** to `scripts/python-sop-template.py` with the
      verified outward winding table + a comment explicitly stating winding is NOT the
      fix for non-manifold edges (prevents the same misdiagnosis recurring).
- [ ] **Decision (user-approved): do NOT auto-inject.** Document recommendation only;
      agents add `fuse`/`clean` per-asset when adjacent coplanar boxes exist. Auto-inject
      would risk merging cross-component points and breaking material isolation.

### Note on what winding normalization does NOT do

Standardizing the `add_box` winding table (canonical outward CCW) is still worth doing —
for correct normals and so agents stop reinventing it — but it will **not reduce the
non-manifold count by a single edge.** The non-manifold and coincident-point failures are
both solved by `fuse` in postprocess.

---

## Bug 4 — 429 rate-limit errors create wasted `0-token` turns (INFRA)

**Severity:** LOW (annoyance + context bloat) but worth tracking.

**Observed:** 8 events in the 22-minute session returned
`"usage":{...,"totalTokens":0}, "stopReason":"error", errorMessage:"429 该模型当前访问量过大"`.
Each is a pure round-trip with no work done.

**Fix direction:**
- [ ] In the harness/provider layer, add exponential backoff retry for 429 with a small
      cap (e.g. 3 retries, 2s/4s/8s) so transient throttling doesn't pollute the session
      log. (Out of scope for the modeling skill itself.)

---

## Bug 5 — No sanctioned "capture from arbitrary angle" path

**Severity:** MEDIUM — agents reach for raw `houdini_run_python` viewport APIs and fail.

**Observed (events 39, 41):** To verify back/side windows (which were hidden from the
front-facing perspective), the agent tried to rotate the viewport camera via
`houdini_run_python`. Two failures:
1. `hou.hmath.buildLookAtRotation` — does not exist on `hmath`.
2. `GeometryViewportCamera.setRotation` — expects `hou.Matrix3 const &`, received a tuple.

This violates the spirit of Harness Rules ("do not explore viewport internals").

**Fix direction:**
- [ ] Add an `orbit` / `eye`+`target` parameter to `houdini_capture_review` so the agent
      never needs to touch viewport camera APIs directly. OR
- [ ] Document ONE verified camera-reposition snippet in `verification-protocol.md`.

---

## Bugs explicitly NOT confirmed (ruled out by evidence)

- **"4 windows are actually missing"** — FALSE. `geometry_inventory` (event 30) lists all
  6 window component_ids with `prim_count: 40` and bounds correctly OUTSIDE the wall
  planes (e.g. `window_back_l` z∈[-2.565,-2.515], walls end at z=-2.5). Wireframe
  re-analysis (event 42) confirmed all 6 present. This was a vision-model false negative,
  handled correctly by the projection-immunity rule. NOT a bug.
- **Orientation failures** — none. All 7 checks passed with `method:construction`,
  `angle_error_deg: 0`. NOT a bug.

---

# Session 2026-06-18 — Castle run new findings

**Source of evidence:** Session `2026-06-18T02-15-49-139Z` (task: "做一个程序化城堡"),
52 events, ~30 min. Asset: 22-component procedural castle, final 2013 pts / 1474 prims,
committed to `/obj/procedural_castle`. Built via `houdini_build_procedural_asset` (recipe
path). Succeeded overall but exposed the following NEW defects (not covered above).

> These are distinct from Bugs 1-5: the castle run did NOT trip capture/health-gate
> blockers, but it surfaced orientation-math, diagnostics, and trust-layer issues.

---

## Bug 6 — `KIND_EIGEN_RANK["radial"]=0` misjudges elongated cylinders (P0)

**Severity:** HIGH — any "long rotational solid" (tower, pillar, pipe, tank, column)
declared `kind=radial` is systematically misjudged 90°. Agents work around it by
mis-declaring `elongated`, which is semantically wrong.

**Observed (session event 28):** All 4 corner towers (`tower_fl/fr/rl/rr`) declared
`kind=radial, expected_axis=Y` and ALL FAILED with `angle_error_deg: 90`.
```
eigenvalues: [1.938578, 1.938578, 13.966169]   # X≈Z (radial plane), Y largest (axial)
eigenvectors: [[0,0,1],[1,0,0],[0,1,0]]
radial rank=0 → picks smallest-eigenvalue vec = [0,0,1] = Z
detected_axis: Z   expected: Y   angle_error: 90°  ❌
```
Agent changed kind to `elongated` (rank 2, largest eigenvalue → Y) and all 4 passed
(event 30). But a tower IS rotationally symmetric — `elongated` is a semantic mismatch.

**Root cause:** `python3.11libs/edini/orientation_math.py:23`
```python
KIND_EIGEN_RANK = {
    "radial": 0,     # smallest eigenvalue → symmetry axis (axle)
    ...
}
```
The comment "smallest eigenvalue → axle" is only true for **thin discs/rings** (wheel:
points spread in the radial plane, axle normal is the thinnest direction). For an
**axially-extruded cylinder** (tower), points spread MOST along the axle → axle has the
LARGEST eigenvalue, and the radial-plane eigenvalues (X, Z) are ~equal. `rank=0` then
picks arbitrarily among the two near-equal small eigenvalues → can land on X or Z.

Single-rank selection cannot distinguish "thin disc" from "long cylinder" — both are
radially symmetric but have opposite eigenvalue profiles.

**Fix direction:**
- [ ] **PCA degeneracy detection.** When `kind=radial` AND
      `abs(eigs[0] - eigs[1]) / max(eigs) < ~0.15` (radial plane near-isotropic), flag
      `pca_degenerate: true` and fall back to `rank=2` (largest eigenvalue = the axle
      for a long cylinder). ~10 lines in `node_utils.py` PCA branch.
- [ ] **Surface the degeneracy in the `hint`** so the agent knows to add
      `construction_axis` for a deterministic check next time.
- [ ] Regression test using the castle's exact eigenvalues `[1.938578, 1.938578, 13.966169]`
      — must now pass with `kind=radial, expected_axis=Y`.

---

## Bug 7 — `geometry_stats` crashes on ObjNode (P0, diagnostics double-failure)

**Severity:** HIGH — when a build FAILS (the moment diagnostics matter most), the
diagnostics layer itself crashes and swallows the geometry/parm snapshot, leaving the
agent with only a raw traceback.

**Observed (session event 21):** First castle build failed on `FloatParmTemplate` type
error. `collect_diagnostics` then raised a SECOND exception:
```
AttributeError: 'ObjNode' object has no attribute 'geometry'
  File "harness.py", line 109, in geometry_stats
    geo = node.geometry()
```

**Root cause:** `python3.11libs/edini/harness.py:109`
```python
def geometry_stats(node_path):
    node = hou.node(node_path)
    geo = node.geometry()   # ObjNode has no .geometry()
```
The sandbox root (`/obj/edini_sandbox_...`) is an ObjNode. ObjNode has no `.geometry()`;
must go through `node.node("OUT")` or `node.renderNode()`.

**Fix direction:**
- [ ] In `geometry_stats`, detect node type. If ObjNode/`obj` context, resolve to
      display/render child (prefer a child named `OUT`, else `node.renderNode()`).
      Fall back gracefully if neither exists.
- [ ] Add a test with the mock exposing an obj-level node.

---

## Bug 8 — Parameters mutated externally with NO signal in tool results (P0, trust)

**Severity:** HIGH — this is the most consequential finding. It breaks the Skill's own
"Inventory is authoritative" principle: when the verification environment itself is
untrusted (parms changed under the agent), inventory/orientation results are meaningless
and the agent burns many turns explaining a phenomenon that isn't its fault.

**Observed (session events 26 → 28):** Right after a successful build (event 23,
`castle_size=14`, bounds 19×13.5×19, inventory normal in event 26), by the time
`verify_orientation` ran (event 28) the parameters had silently become random values
within their min/max ranges — with NO `set_params` call anywhere in the log:
```
castle_size:  14   → 23.2    (ratio 1.66)
tower_sides:  12   → 24      (ratio 2.0)
keep_height:  10   → 14.6    (ratio 1.46)
flag_size:    1.2  → 2.48    (ratio 2.07)
```
The non-uniform ratios (1.23–2.07) rule out a global scale; they look like randomized
values within each parm's range — consistent with a fuzzer / robustness probe.

The agent spent **6 thinking turns (events 33-38)** inferring "maybe a fuzzer did it,"
because the tool results gave no indication the parameters had been touched.

**Root cause (process, not code):** Whatever mutates the parms (likely a fuzzer harness)
does so as a side effect invisible to the verification tools. `verify_orientation`,
`geometry_inventory`, `inspect_geometry_health` all return geometry-derived data but
NOT the current parameter values that produced it.

**Fix direction:**
- [ ] **Attach a `parm_snapshot` to every verification-tool result** (sandbox-root parms
      as `{name: value}`). Cheap to collect (already enumerated elsewhere).
- [ ] **Detect drift:** compare against the snapshot taken at build time; if different,
      set `params_drifted: true` and include a before/after diff. This turns the
      "6-turn mystery" into a one-line field the agent reads instantly.
- [ ] Investigate whether a fuzzer is actually running and, if so, whether its mutations
      should be surfaced explicitly (e.g. a `fuzzer_active: true` flag on sandbox tools).

---

## Bug 9 — fuse+clean documented as non-manifold cure, but only fixes point-level coincidence (P1, doc)

**Severity:** MEDIUM — causes agent confusion (event 27 thinking: "why didn't fuse work?")
and sets wrong expectations. Related to Bug 2+3 above but adds a corrected understanding.

**Observed (session event 25):** The castle DID include `fuse + clean` in postprocess
(builder creates them correctly, verified in `harness.py:2341-2358`). Yet 787 non-manifold
edges remained. Agent was confused in thinking.

**Root cause (now correctly understood):** `fuse` merges **coincident points** (identical
positions). The castle's non-manifold edges come from adjacent boxes **sharing an entire
face** — the shared face's 4 edges, after fuse consolidates the coincident corner points,
become referenced by 3+ polygons (box A's 2 faces + box B's 2 faces). This is
**topology-level** non-manifold, not point-level. `clean`'s remove-non-manifold only
deletes the extra faces; it cannot repair design-level volumetric overlap.

**Fix direction:**
- [ ] Rewrite the `fuse+clean` guidance in `declarative-builder.md:43-52` and
      `SKILL.md:91` to distinguish:
        - **Point-level** coincidence (inset panel corners coinciding with slab) → fuse fixes.
        - **Topology-level** overlap (two boxes sharing a full face) → must be avoided at
          generation time (inset/offset gap, or Boolean union).
- [ ] Add an advisory threshold heuristic: non-manifold count > 20% of prim_count suggests
      structural overlap, not benign coincidence.

---

## Bug 10 — eval_stats / search_knowledge unavailable in live sandbox (P2, doc)

**Severity:** LOW — 2 wasted tool round-trips per session.

**Observed (session events 9, 10):**
- `edini_get_eval_stats` → `"Eval system not available in this context"`
- `edini_search_knowledge` → `[]`

The Skill's Step 0 implicitly expects these to work.

**Fix direction:**
- [ ] Add a live-sandbox skip condition in `SKILL.md` Step 0: "If `edini_get_eval_stats`
      returns 'not available', you are in a live sandbox — skip eval/knowledge and proceed."

---

## Bug 11 — `FloatParmTemplate` default_value type error (P2, template)

**Severity:** LOW — one-shot API misuse, agent self-corrected.

**Observed (session event 21):** `default_value` passed as scalar instead of nested tuple.
```
TypeError: argument 4 of type 'std::vector<double,...> const &'
```

**Fix direction:**
- [ ] Make the `((0.35,),)` nested-tuple form more prominent in
      `scripts/python-sop-template.py` and `params-and-linkage.md` (it IS shown, but the
      agent still missed it — consider a one-line "MUST be ((val,),)" callout).
- [ ] Long-term: a param-template helper tool (see user proposal Q1) eliminates hand-written
      `FloatParmTemplate` entirely.
