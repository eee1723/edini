# Two-Layer Verification Protocol

**Two layers, not three.** A recurring failure mode was the visual layer
(`capture_review` + `describe_image`) driving rebuild loops: vision
models cannot reliably see small/thin components (bricks, chains, bolts) at
viewport resolution, so they report real geometry as "missing" or "smooth",
contradicting the geometry inventory — and the agent wastes iterations
rebuilding geometry that was already correct. **The visual layer is now an
archive step only, not a verification loop.** Rely on the cheap authoritative
layers; capture a final screenshot for the record but never let it drive a
rebuild.

| Layer | Tool | What it catches | Authority | Cost |
|---|---|---|---|---|
| **1. Geometry health** | `inspect_health` | orphan points, stray open curves (BLOCKING); degenerate faces, non-manifold edges, open boundary edges, coincident points (ADVISORY) | AUTHORITATIVE — blocking checks must pass | cheap (no render) |
| **2a. Orientation** | `verify_orientation` | Wrong axle direction, flipped components, misaligned axes | AUTHORITATIVE — gate | cheap |
| **2b. Inventory data** | `geometry_inventory` / the `geometry_inventory` field returned by `capture_review` | Which component_ids exist, their prim counts + relative sizes | AUTHORITATIVE for "is it present?" | cheap |
| **3. Archive capture** | `capture_review` (optional, commit-time only) | A saved screenshot of the finished asset | **Archive only — NOT a verification loop** | render |

**Run layers in order.** Cheap authoritative layers first; capture is the last
step before commit, for the record.

## Two-tier health checks

`inspect_health` reports `overall_ok`, which is driven ONLY by
the BLOCKING checks:

- **BLOCKING (gate `overall_ok` + commit):** `orphan_points`, `open_curves`.
  These are unambiguous defects — always fix them.
- **ADVISORY (reported, never block):** `degenerate_prims`, `nonmanifold_edges`,
  `open_boundary_edges`, `coincident_points`. These are routinely tolerated or
  EXPECTED. In particular `open_boundary_edges` is normal for open surfaces
  (terrain, a single panel, an intentional gateway/door opening) — do NOT treat
  it as a defect.

`overall_ok == True` means the two blocking checks pass. An ADVISORY finding
with a non-zero count does NOT make `overall_ok` false. If `overall_ok` is
false, fix the named blocking check only.

## Mandatory Pre-Commit Sequence

```
0. CHECK structure_advisory (returned by run_python_sandbox) — if is_monolithic,
   discard and rebuild modular. Do this BEFORE any verification.

1. inspect_health on the OUT node — MANDATORY, not optional.
   - overall_ok reflects ONLY the BLOCKING checks (orphan_points, open_curves).
     If overall_ok is false, fix the named blocking check.
   - ADVISORY findings (non-manifold edges, open boundary edges, degenerate
     faces, coincident points) are reported for your awareness but do NOT block.
     Only act on them if they clearly break a downstream Boolean/Sweep you are
     about to run. Do NOT rebuild to zero them out.

2. verify_orientation on the OUT node
   - Pass all checks from the recipe's ORIENTATION ASSERTS section
   - If any check fails, apply the hint quaternion to the SOURCE code and
     re-run the sandbox. Do NOT rotate post-hoc on geometry.

3. geometry_inventory on the OUT node
   - Confirm every expected component_id is present with prim_count > 0.
   - This is the AUTHORITATIVE answer to "is component X present?". prim_count
     > 0 means it EXISTS — regardless of what any screenshot appears to show.

4. (Optional) capture_review — ONE final screenshot for the archive,
   taken just before commit. This is NOT a verification step:
   - Do NOT call describe_image / analyze_image on it to judge defects.
   - Do NOT rebuild based on anything you see in the screenshot.
   - If you are unsure whether a component is correct, re-check the INVENTORY
     (step 3), not the pixels. Inventory is authoritative; pixels are not.

5. commit_sandbox — runs the modular-structure gate then the
   orientation gate as final checks.
```

## Debug Discipline (anti-flail rules)

The single biggest waste in procedural generation is the **blind rebuild loop**:
a vague signal ("it looks smooth" / "seems missing") triggers a full regenerate,
the geometry is essentially unchanged, repeat 4×. These rules prevent it:

1. **Name the defect before fixing.** State exactly which component_id or which
   health-check field you are fixing. "The chain is missing" is NOT a valid
   defect statement until `geometry_inventory` confirms chain has
   prim_count == 0. If it has prim_count > 0, the component EXISTS — there is
   no defect to rebuild.
2. **One defect per round.** Fix one named thing, re-verify that one thing.
   Don't bundle 5 changes into one rebuild.
3. **Diff the inventory.** Before and after a repair, compare `geometry_inventory`
   output. If the component's prim_count/bounds didn't change, your edit didn't
   take effect — don't rebuild again and hope.
4. **Escalate, don't loop.** If the same defect survives 2 targeted fixes, the
   approach is wrong — switch backend (VEX↔Python SOP) or ask the user. Do NOT
   do a 3rd identical rebuild.
5. **Rebuild = last resort.** `discard_sandbox` + full regenerate is
   only justified when a blocking health check shows fundamental breakage
   (many orphan points / stray curves) OR orientation is structurally wrong
   across multiple components.
6. **Inventory beats pixels.** When the geometry inventory and a screenshot
   disagree about whether a component exists, the inventory is correct. Never
   rebuild real geometry (prim_count > 0) because a screenshot looked wrong.

## Orientation Check Examples

```python
# Wheel: axle should be horizontal (along X for a bike facing +Z)
verify_orientation(
    node_path="/obj/edini_sandbox_.../edini_generate",
    checks=[
        {"component_id": "wheel_fl", "kind": "radial", "expected_axis": "X"},
        {"component_id": "wheel_fr", "kind": "radial", "expected_axis": "X"},
        {"component_id": "wheel_rl", "kind": "radial", "expected_axis": "X"},
        {"component_id": "wheel_rr", "kind": "radial", "expected_axis": "X"},
        # Handlebar long axis transverse (Z direction for a bike facing +Z)
        {"component_id": "handlebar", "kind": "elongated", "expected_axis": "Z"},
        # Saddle normal must point up (signed=true)
        {"component_id": "saddle", "kind": "planar", "expected_axis": "Y", "signed": True},
    ]
)
```

## Repair Loop for Orientation Failures

When `verify_orientation` returns a failure, each failed check includes
a `hint` field with the exact quaternion to apply:

```python
# Example failed check output:
{
    "component_id": "wheel_fl",
    "kind": "radial",
    "expected_axis": "X",
    "detected_axis": "Y",           # wheel lying flat!
    "angle_error_deg": 89.7,
    "passed": False,
    "hint": "wheel_fl rotational symmetry axis (axle) currently along Y
             (...). Expected X. Apply quaternion (x,y,z,w)=(0,0,-0.7,0.7)
             to the component's geometry, or pre-multiply the generating
             transform: hou.Quaternion(0.7, hou.Vector3(0, 0, -0.7))."
}
```

Fix by applying the hint inside the generator code (don't try to rotate
post-hoc on the geometry — fix the source).

## Archive Capture (screenshots)

**`capture_review` is an archive tool now, used ONCE before commit.** It
is no longer part of a defect-judging verification loop:
```
capture_review(
  filepath="review.png",  # auto-routed to $HIP/Edini_screenshots/<task>/
  target_path="/obj/asset_name/OUT",
  views=["perspective", "top", "front", "right"],
  shading_mode="smooth"
)
```

- **Always pass `target_path`** — frames and isolates the generated asset.
- The result includes a `geometry_inventory` text block. This inventory is
  AUTHORITATIVE for presence/absence; the pixels are NOT.
- **Do NOT call `describe_image` / `analyze_image` to judge the capture.** The
  visual-judgment loop has been removed because vision models repeatedly
  misjudged small/repeated geometry (e.g. reporting a 3000-prim brick wall as
  "smooth"), driving wasted rebuilds.
- If capture returns an error, do not retry or explore alternative capture
  methods — skip it and proceed to commit (the geometric layers already verified
  the asset).

## Verification Tools (cheat-sheet)

| Tool | When to use |
|---|---|
| `inspect_health` | After sandbox build, before orientation. `overall_ok` reflects only BLOCKING checks (orphan_points, open_curves); the rest are ADVISORY. |
| `geometry_inventory` | Confirm every expected `component_id` exists with prim_count > 0. AUTHORITATIVE for presence. |
| `capture_review` | ONE archive screenshot before commit. Not a verification loop — do not judge it with a vision model. |
