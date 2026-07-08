"""Archetype spec: ``extrude_profile`` — a parametric tube/pillar (a circular
profile extruded along an axis).

The simplest archetype (one ``node`` + ``wire_out``), added in Phase 2c to
VALIDATE the core P0 claim: **adding an archetype = adding a spec module, with
ZERO emitter changes** — no new op was needed, it reuses ``node`` + ``wire_out``
+ the tube→Polygon tweak. This is the greenfield proof that the spec format
scales.

params: ``radius`` + ``height``, each a number or a design_param name
(→ live relative ch() ref). The tube→Polygon tweak (``type=1``) avoids H21's
degenerate Primitive default (the same tweak copy_array uses on tube leaves).
"""

SPEC = {
    "archetype": "extrude_profile",
    "description": ("A parametric tube/pillar — a circular profile extruded "
                    "along an axis (columns/handles/cylinders)."),
    "param_specs": {
        # number or design_param name (unchecked type — matches the old
        # archetypes, which accepted either for scalar geometry parms).
        "radius": {"required": True},
        "height": {"required": True},
    },
    "ops": [
        {
            "op": "node", "name": "profile_tube", "type": "tube",
            "params": {"rad1": "$radius", "height": "$height"},
            "tweaks": [{"when_type": "tube", "set_if_unset": {"type": 1}}],
        },
        {"op": "wire_out", "from": "profile_tube"},
    ],
}
