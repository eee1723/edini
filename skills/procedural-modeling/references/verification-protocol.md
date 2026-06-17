# Three-Layer Verification Protocol

**Why three layers, not two:** A recurring failure mode was relying on screenshots alone. Vision models cannot reliably see small/thin components (chains, spokes, bolts) at viewport resolution, so they report them as "missing" even when they exist — and the agent wastes iterations rebuilding with no real change. Geometry health checks and per-component inventory data catch what screenshots cannot.

| Layer | Tool | What it catches | Authority | Cost |
|---|---|---|---|---|
| **1. Geometry health** | `houdini_inspect_geometry_health` | Orphan points, open/stray curves, degenerate faces, non-manifold edges, holes, coincident points | AUTHORITATIVE — must pass | cheap (no render) |
| **2a. Orientation** | `houdini_verify_orientation` | Wrong axle direction, flipped components, misaligned axes | AUTHORITATIVE — gate | cheap |
| **2b. Inventory data** | `houdini_geometry_inventory` / the `geometry_inventory` field returned by `capture_review` | Which component_ids exist, their prim counts + relative sizes | AUTHORITATIVE for "is it present?" | cheap |
| **3. Visual** | `houdini_capture_review` + `describe_image` (+ `houdini_capture_component_detail` for small parts) | Proportions, symmetry, intersection, construction logic | Advisory | expensive (render + vision) |

**Run layers in order.** Cheap authoritative layers first; only escalate to vision when the cheap layers can't resolve a question.

## Mandatory Pre-Commit Sequence

```
0. CHECK structure_advisory (returned by run_python_sandbox) — if is_monolithic,
   discard and rebuild modular. Do this BEFORE any verification.

1. houdini_inspect_geometry_health on the OUT node — MANDATORY, not optional.
   - Fix orphan points (Fuse), stray open curves (Blast), degenerate faces
     (Clean), non-manifold edges before anything else. These silently break
     Boolean/Sweep/subdivision downstream.
   - NOTE: open_boundary_edges is EXPECTED for open surfaces (terrain, a
     single panel). Only treat it as a defect for assets that should be closed.

2. houdini_verify_orientation on the OUT node
   - Pass all checks from the recipe's ORIENTATION ASSERTS section
   - If any check fails, apply the hint quaternion to the SOURCE code and
     re-run the sandbox. Do NOT rotate post-hoc on geometry.

3. houdini_geometry_inventory on the OUT node (or read geometry_inventory
   from the capture_review result)
   - Confirm every expected component_id is present with prim_count > 0.
   - Note any component with size_fraction < 0.08 — it is present but SMALL.
     These will need a component close-up (step 5b) before vision can judge them.

4. houdini_capture_review (4-view: perspective/top/front/right) → describe_image
   - The capture now frames each view to the target's bounding box (no more
     clipped ortho views). It also returns a `geometry_inventory` text block.
   - Pass the PROCEDURAL_VERIFY_PROMPT to describe_image, AND include the
     inventory text in your message so the vision model cross-validates.
   - The vision model CANNOT assess orientation — ignore any orientation
     claims it makes. Only act on PROPORTIONS, SYMMETRY, INTERSECTION
     (perspective-confirmed only), STRUCTURAL_DETAIL.

5. IF vision flags a component as missing/unclear, OR the inventory marks it SMALL:
   5a. Check the inventory: if the component_id has prim_count > 0, it EXISTS
       — vision just couldn't see it. Do NOT rebuild it.
   5b. Run houdini_capture_component_detail on that component_id to get a
       close-up, then re-judge. This resolves the "exists but too small"
       ambiguity definitively. Use this tool, NOT a single-view capture_review.

6. Repair loop: fix the SPECIFIC defect → re-verify the SPECIFIC layer →
   repeat. Up to 3 rounds, then ask the user (see Debug Discipline below).

7. houdini_commit_sandbox — runs the modular-structure gate then the
   orientation gate as final checks.
```

## Debug Discipline (anti-flail rules)

The single biggest waste in procedural generation is the **blind rebuild loop**: vision reports a vague defect, the agent regenerates the whole asset hoping it improves, the geometry is essentially unchanged, repeat 4×. These rules prevent it:

1. **Name the defect before fixing.** State exactly which component_id or which health-check field you are fixing. "The chain is missing" is NOT a valid defect statement until you've confirmed via `geometry_inventory` that chain has prim_count == 0. If it has prim_count > 0, the defect is "chain is too small to see" → fix is a close-up capture, not a rebuild.
2. **One defect per round.** Fix one named thing, re-verify that one thing. Don't bundle 5 changes into one rebuild — you won't know which worked.
3. **Diff the inventory.** Before and after a repair, compare `geometry_inventory` output. If the component's prim_count/bounds didn't change, your edit didn't take effect — don't re-capture and hope.
4. **Escalate, don't loop.** If the same defect survives 2 targeted fixes, the approach is wrong — switch backend (VEX↔Python SOP), ask the user, or capture a component detail. Do NOT do a 3rd identical rebuild.
5. **Rebuild = last resort.** `houdini_discard_sandbox` + full regenerate is only justified when the health check shows fundamental topology breakage (non-manifold, many orphan points) OR orientation is structurally wrong across multiple components.

## The Verification Prompt (for describe_image)

Use the canonical `PROCEDURAL_VERIFY_PROMPT` (single source of truth in `pi-visionizer/src/config.ts`). It instructs the vision model to:
- cross-reference a `GEOMETRY_INVENTORY` block you provide alongside the image,
- NOT report small components as "missing" if they appear in the inventory,
- emit a structured `VERDICT: accept | fix:<list> | closer_capture:<list> | uncertain`.

When you call `describe_image`, paste the `geometry_inventory` text (returned by `capture_review`) into the same message so the vision model can cross-validate. Note: vision CANNOT detect orientation — rely on `houdini_verify_orientation` for that.

## Orientation Check Examples

```python
# Wheel: axle should be horizontal (along X for a bike facing +Z)
houdini_verify_orientation(
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

When `houdini_verify_orientation` returns a failure, each failed check includes a `hint` field with the exact quaternion to apply:

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

Fix by applying the hint inside the generator code (don't try to rotate post-hoc on the geometry — fix the source).

## What counts as defects (visual layer)
- **Critical**: missing major component, geometry not visible
- **Major**: obvious proportion error, intersecting parts, no surface detail (level 1-2)
- **Minor**: slight asymmetry, imperfect edge flow, cosmetic issues

(Note: "wrong orientation" is no longer in this list — it's caught by the programmatic gate, not the visual layer.)

## Capture (Screenshots)

**Use `houdini_capture_review`** for all visual verification:
```
houdini_capture_review(
  filepath="review.png",  # auto-routed to $HIP/Edini_screenshots/<task>/
  target_path="/obj/asset_name/OUT",
  views=["perspective", "top", "front", "right"],
  shading_mode="smooth"
)
```

- **Always pass `target_path`** — frames and isolates the generated asset. Each view (including orthographic top/front/right) is framed to the target's bounding box via `setViewToBoundingBox`, so the COMPLETE model is always visible — no more clipped ortho views.
- The result includes a `geometry_inventory` text block listing every `component_id` with its prim count and relative size. **Paste this into your describe_image message** so the vision model can cross-validate presence/absence rather than guessing from pixels.
- Filepath is auto-routed to the session's screenshot folder; AI-supplied basenames are preserved with sequence numbering (`review_001.png`, etc.).
- If capture returns an error, do not retry or explore alternative capture methods.

**Use `houdini_capture_component_detail`** when a component is present (per inventory) but too small to judge in the whole-asset capture:
```
houdini_capture_component_detail(
  filepath="chain_detail.png",
  node_path="/obj/asset_name/OUT",
  component_ids=["chain_top", "chainring", "pedal"],
  views=["perspective"]   # keep cells large; add "top" for a 2-view sheet
)
```
Each component is framed to its OWN bounding box and captured as a separate cell — this is how you resolve the "exists but too small to see" ambiguity.

## Verification Tools (cheat-sheet)

| Tool | When to use |
|---|---|
| `houdini_inspect_geometry_health` | After sandbox build, before orientation. Catches orphan points, stray open curves, degenerate faces, non-manifold edges, holes, coincident points. Returns `overall_ok` + per-check `fix` recommendations. |
| `houdini_geometry_inventory` | Confirm every expected `component_id` exists with prim_count > 0. Flag small components (size_fraction < 0.08) that need a close-up. |
| `houdini_capture_component_detail` | Close-up capture of specific component_ids when they're too small to see in the whole-asset 4-view. |
