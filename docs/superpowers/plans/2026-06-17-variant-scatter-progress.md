# Variant Scatter Tool — Development Progress

> **Date:** 2026-06-17
> **Status:** Core tool implemented + verified; one H21 API detail pending real-Houdini confirmation.

## What was built

`houdini_variant_scatter` — a new procedural-modeling tool that scatters
**multiple variant geometries** onto points with a **weighted, seeded,
reproducible** distribution. Solves the "6 identical windows" problem from the
procedural house session.

### Final working workflow (design) — CORRECTED 2026-06-17 after real-H21 testing

```
variants (i@variant tagged, prim attrib) → merge (UNPACKED)  ─┐
                          NO pack node — Copy dispatches on     │
                          plain source prims by `variant`       ├→ copytopoints(useidattrib, idattrib=variant)
                                                              │     ↓ source prim variant matches target point variant
scatter points (i@id only) ─→ attribfrompieces(pieceattrib=variant, seed) ─┘  + resettargetattribs transfers i@id
                                                                        ↓ (NO unpack — source already expanded)
                                                              idfix → OUT
                                                              component_id = {variant}_{id}
```

### Key design decisions (CORRECTED — real-Houdini 21.0.440 testing)

> **The original design (below, struck) was built on three assumptions that
> real-H21 testing disproved. The corrected decisions follow.**

1. ~~Removed AFP~~ → **AFP IS the variant assigner.** Real-H21 testing proved
   AFP is the RIGHT tool: it draws a `variant` onto each scatter point from
   the source piece library and **reliably covers all variants even at low
   point counts**. The old hand-rolled weighted-random assignment could
   starve low-weight variants (seed=42 over 8 pts → zero points for variant
   2 → win_c never instanced). AFP's default mode (seed-controlled) produces
   a clean distribution.

2. ~~Pack By Name~~ → **NO pack node at all.** Pack By Name HIDES the prim
   `variant` inside the PackedFragment (verified: `variant` is `<unreadable>`
   on the packed prim), so Copy to Points' `useidattrib` piece dispatch cannot
   read it → dispatch collapses (8 scatter pts → 0 packed instances, all
   variants mashed together). Copy to Points dispatches correctly on
   **UNPACKED source** geometry: source prim `variant` matches target point
   `variant` 1:1. (manual_variant_dispatch_diagnose.py /
   manual_attribfrompieces_probe.py)

3. **H21 Copy to Points parm names:** `useidattrib` (Piece Attribute
   toggle) + `idattrib` (attribute name). Confirmed correct. NOT
   `pieceattrib`/`pieceattribname`.

4. ~~Apply Attributes multiparm~~ → **`resettargetattribs` BUTTON.** Real H21
   has NO Apply Attributes multiparm folder and NO `numapplyattrs` count parm
   on a fresh node (the manifest's `useapply#` templates are latent). The
   real transfer mechanism is the `resettargetattribs` BUTTON — press it and
   Houdini auto-populates the `targetattribs` multiparm with default entries
   (entry #1: `applymethod=0` copy, `applyattribs='*,^v,^Alpha,^N,^up,^pscale,
   ^scale,^orient,^rot,^pivot,^trans,^transform'` — copies every target-point
   attribute except the transform family, already covering `id`). Just
   `copy_node.parm("resettargetattribs").pressButton()` — no per-instance
   parm manipulation needed. (manual_resettargetattribs_probe.py)

5. **NO unpack node.** Copy on unpacked source already yields expanded
   geometry, so idfix can overwrite per-prim `component_id` directly.

## Files changed

| File | Change |
|---|---|
| `python3.11libs/edini/harness.py` | `build_variant_scatter()` + 3 code generators + `_MODULAR_NODE_TYPES` (pack/unpack) + improved per-node error collection |
| `python3.11libs/edini/tool_executor.py` | Registered `houdini_variant_scatter` |
| `tests/mock_hou.py` | pack PTG, createNode populates parms from node-type PTG, H21 copytopoints parm names |
| `tests/test_build_procedural_asset.py` | 25 new tests (5 test classes) |
| `skills/procedural-modeling/SKILL.md` | Step 3a Build Path table: variant scatter row |
| `skills/procedural-modeling/references/declarative-builder.md` | Full "Variant Scatter" section |
| `skills/procedural-modeling/scripts/recipe-template.md` | Variant recipe template |
| `tests/manual_variant_scatter_test.py` | End-to-end harness test script |
| `tests/manual_variant_chain_diagnose.py` | Node-by-node diagnostic script |

### Addendum 2026-06-17 (real-H21 architecture rewrite)
The original design used pack(packbyname) + hand-rolled weighted-random
variant assignment + an "Apply Attributes" multiparm. Real-H21 testing
(21.0.440) disproved all three. This addendum records the rewrite.

| File | Change |
|---|---|
| `python3.11libs/edini/harness.py` | `build_variant_scatter` rewritten: removed pack & unpack nodes; inserted `attribfrompieces` (scatter_afp, pieceattrib=variant, seed) to assign variant to scatter points; Copy source is now the UNPACKED variants_merge; `_setup_copy_apply_attributes` reduced to `resettargetattribs.pressButton()`; `_variant_scatter_points_code` simplified to emit only per-point `id` (no variant/weights/random) |
| `tests/mock_hou.py` | copytopoints PTG now matches real H21: `resettargetattribs` Button + `targetattribs` int (replacing the phantom Apply Attributes multiparm); new `MockButtonParmTemplate`; `ButtonParmTemplate` registered on MockHou |
| `tests/test_copy_apply_attributes.py` | Rewritten (8 tests) for the button-press mechanism + variant-scatter integration (no pack/unpack, has scatter_afp) |
| `tests/test_build_procedural_asset.py` | `TestVariantScatterPointsCode` rewritten (wrapper no longer assigns variant); `test_expected_node_network_built` updated for the new node set |
| `tests/manual_variant_dispatch_diagnose.py` | Proved pack hides variant → dispatch collapse |
| `tests/manual_attribfrompieces_probe.py` | Proved the corrected architecture works end-to-end on H21 |
| `tests/manual_resettargetattribs_probe.py` | Captured the resettargetattribs button → targetattribs multiparm structure |

## Verification status

### ✅ Confirmed working (real Houdini 21.0.440) — ARCHITECTURE REWRITE
- **AFP assigns variant to scatter points** covering ALL variants: 8 pts →
  `{0:3, 1:3, 2:2}` (manual_attribfrompieces_probe.py). No more low-weight
  variant starvation.
- **Copy dispatches on UNPACKED source** by `variant`: 3 distinct variants
  present, per-prim tally `{0:3, 1:3, 2:2}` matching the point distribution.
  NO pack node needed (pack broke dispatch by hiding variant).
- **`resettargetattribs` button transfers `id`**: after press, all 8 unique
  ids `[0..7]` present on output points. Default entry #1 (applymethod=0 copy,
  applyattribs='*,^transform...') already covers `id`.
- All nodes cook clean (no errors).

### ⚠️ Pending (one H21 API detail) — RESOLVED 2026-06-17
- ~~Copy to Points Apply Attributes multiparm count parm name~~ → **RESOLVED.**
  Real H21 has NO Apply Attributes multiparm on a fresh node. The real
  transfer mechanism is the `resettargetattribs` BUTTON. `_setup_copy_apply_attributes`
  now just calls `pressButton()`. See decision #4 above and
  manual_resettargetattribs_probe.py for the captured structure.

## Test coverage
- **426 tests pass** (78 builder tests including 25 new variant tests)
- Mock enhanced with H21-realistic parm names
- 1 pre-existing stale test failure (`test_procedural_modeling_skill_requires_harness`)
  unrelated to this work

## Next steps (backlog)
1. ~~**Confirm Apply Attributes multiparm count parm name in real H21**~~ —
   ✅ DONE 2026-06-17, then SUPERSEDED by architecture rewrite. Real H21 has
   no such multiparm; the `resettargetattribs` button is the mechanism. The
   whole pack/AAP/dispatch chain was rewritten (no pack, AFP assigns variant,
   button transfers id). Verified end-to-end on 21.0.440.
2. **Wire variant scatter into agent's actual generation flow** (SKILL.md
   guidance for when to choose it over single-template Copy-to-Points).
3. **Tool template idea 1 (sweep tube)** — curve + cross-section → tube/beam.
4. **Tool template idea 3 (attribute presets)** — VEX wrangle snippets for
   pscale/orient/N/up/id/Cd.
5. ~~**Bug 1 (capture_component_detail bbox build failed)**~~ — ✅ DONE 2026-06-17.
   See `2026-06-17-procedural-modeling-bugs.md` Bug 1 (fixed: 6-float bbox
   overload + 2 enabler defects + 8 regression tests).
