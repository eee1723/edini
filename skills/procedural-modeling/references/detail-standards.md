# Detail Standards

A procedural asset is NOT complete when it has correct topology. Detail means STRUCTURAL COMPLEXITY, not surface smoothing.

**Do NOT stack PolyBevel + Subdivide as a substitute for real detail.** These are surface treatments that add no structural information. They are fine as finishing touches, but they do NOT raise the detail level.

## What counts as real detail
- **Separate geometric parts** — door panels as distinct geometry, not painted on
- **Panel lines / seams as geometry** — inset faces or extruded edges, not just color
- **Secondary components** — bolts, hinges, vents, handles, trim pieces
- **Varied cross-sections** — a car fender's cross-section changes along its length
- **Functional sub-shapes** — brake calipers, mirror housings, key dish concavity
- **Construction logic** — visible how the object would be manufactured/assembled

## What does NOT count as detail
- PolyBevel on all edges (this is finishing, not detail)
- Subdivide passes (this is smoothing, not detail)
- Normal recalculation (this is shading, not detail)
- Noise displacement (unless creating specific surface texture like bark or leather)

## Detail level rating
- Level 1: Raw primitives (box, cylinder) — NEVER ACCEPTABLE
- Level 2: Correct silhouette but featureless, no sub-parts — NOT ENOUGH
- Level 3: Distinct sub-components, shaped profiles, panel lines or seams — MINIMUM
- Level 4: Secondary components (bolts, vents), varied cross-sections, construction logic — TARGET

## Finishing (apply AFTER structural detail is sufficient)
1. **Normal SOP** — cusp angle 30-60° for correct shading
2. **PolyBevel** — offset 0.01-0.03 on hard edges ONLY if asset will be rendered with smooth shading
3. **Subdivide** — ONLY on organic forms that need smoothing (not mechanical parts)

## Material Group Organization

No texturing required, but geometry MUST be organized for future material assignment:
- Assign primitive groups by material zone: `body`, `glass`, `rubber`, `metal_trim`, `chrome`, etc.
- Use `@shop_materialpath` attribute or primitive groups — either works
- Each visually distinct surface = separate group
- Example: car → groups: `body_paint`, `glass`, `rubber_tire`, `chrome_trim`, `interior`, `headlight_lens`

This enables one-click material assignment later without re-selecting geometry.
