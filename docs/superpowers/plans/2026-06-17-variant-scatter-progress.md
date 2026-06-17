# Variant Scatter Tool — Development Progress

> **Date:** 2026-06-17
> **Status:** Core tool implemented + verified; one H21 API detail pending real-Houdini confirmation.

## What was built

`houdini_variant_scatter` — a new procedural-modeling tool that scatters
**multiple variant geometries** onto points with a **weighted, seeded,
reproducible** distribution. Solves the "6 identical windows" problem from the
procedural house session.

### Final working workflow (design)

```
variants (i@variant tagged) → merge → pack(packbyname)  ─┐
                          1 packed prim per variant        │
                                                           ├→ copytopoints(useidattrib)
scatter points (i@variant weighted+seeded, i@id unique) ──┘     ↓  + Apply Attributes transfers i@id
                                                           unpack → idfix → OUT
                                                           component_id = {variant}_{id}
```

### Key design decisions (hard-won from real-Houdini testing)

1. **Removed Attribute from Pieces (AFP).** AFP requires TWO inputs
   (target points + piece library) and does its own non-deterministic
   assignment. Our Python scatter wrapper already assigns `variant`
   deterministically (weighted + seeded), so Copy to Points dispatches
   directly by matching point.variant == packed-source.variant. Simpler
   and more controllable.

2. **Pack By Name, not Packed Fragments.** Pack's default "Packed
   Fragments" mode MERGES overlapping geometry into a single prim
   (observed `prims=1`). `packbyname=1` + `nameattribute="variant"`
   produces one packed prim per variant index.

3. **H21 Copy to Points parm names:** `useidattrib` (Piece Attribute
   toggle) + `idattrib` (attribute name). NOT `pieceattrib`/`pieceattribname`
   (those don't exist on copytopoints::2.0).

4. **Per-instance ID via Copy to Points Apply Attributes, NOT Connectivity.**
   Connectivity breaks on non-connected variants (window = frame + glass +
   mullions would get DIFFERENT piece values for parts of one instance).
   Instead: scatter points carry `i@id`, Copy to Points transfers `id` onto
   instance points via its Apply Attributes multiparm — all prims of one
   instance share the SAME id regardless of connectivity.

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

## Verification status

### ✅ Confirmed working (real Houdini 21)
- Variant dispatch: box AND sphere both present (`variant values: [0, 1]`)
- Weighted distribution (3 box + 3 sphere with seed=42)
- All nodes cook clean (no errors)
- pack(packbyname) produces 2 packed prims (one per variant)

### ⚠️ Pending (one H21 API detail)
- **Copy to Points Apply Attributes multiparm count parm name.** Houdini 21
  does NOT have `node.setMultiparmInstanceCount()`. The tool tries
  `numapplyattrs` / `numapply` / `applyattrsnum`. If none match the real
  H21 internal name, `id` won't transfer and all instances get `id=0`.
  **Action:** run the diagnostic script and check if the WARNING prints, or
  inspect real parm names via:
  ```python
  print([p.name() for p in hou.node('/obj/variant_diag/copy_dispatch').parms()
         if 'apply' in p.name().lower() or 'num' in p.name().lower()])
  ```

## Test coverage
- **426 tests pass** (78 builder tests including 25 new variant tests)
- Mock enhanced with H21-realistic parm names
- 1 pre-existing stale test failure (`test_procedural_modeling_skill_requires_harness`)
  unrelated to this work

## Next steps (backlog)
1. **Confirm Apply Attributes multiparm count parm name in real H21** → finalize
   per-instance id transfer.
2. **Wire variant scatter into agent's actual generation flow** (SKILL.md
   guidance for when to choose it over single-template Copy-to-Points).
3. **Tool template idea 1 (sweep tube)** — curve + cross-section → tube/beam.
4. **Tool template idea 3 (attribute presets)** — VEX wrangle snippets for
   pscale/orient/N/up/id/Cd.
5. ~~**Bug 1 (capture_component_detail bbox build failed)**~~ — ✅ DONE 2026-06-17.
   See `2026-06-17-procedural-modeling-bugs.md` Bug 1 (fixed: 6-float bbox
   overload + 2 enabler defects + 8 regression tests).
