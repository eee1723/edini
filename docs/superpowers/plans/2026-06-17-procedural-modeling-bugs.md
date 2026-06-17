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
