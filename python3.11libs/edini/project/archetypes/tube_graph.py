"""Archetype spec: ``tube_graph`` — polyline edges between consumed named
anchors, then PolyWire for thickness.

The "connected tubes" component (a bike frame: head_tube → seat_tube →
bottom_bracket). Declare ``ports.in`` consuming an upstream's named markers,
then this archetype connects them per the ``tubes`` spec. Uses VEX (not a
Python SOP) to build the edges — zero Python-SOP error surface (the #1 step-3
failure mode this archetype exists to eliminate).

Phase 2b migration of ``builder._archetype_tube_graph`` — same behavior, now
data-driven.
"""

SPEC = {
    "archetype": "tube_graph",
    "description": ("Build a tube graph (frame/fork/handlebar): polyline edges "
                    "between consumed named anchors, then PolyWire for thickness."),
    "param_specs": {
        # tubes = [{a: <anchor_name>, b: <anchor_name>}, ...] — the graph edges.
        "tubes": {"type": "list", "required": True},
        # radius = number or design_param name (→ live ch() ref). Unchecked
        # type (matches the old code, which accepted either).
        "radius": {"required": False},
    },
    "ops": [
        {"op": "collect_anchors", "as": "tube_cloud"},
        # Detail wrangle builds polyline edges between the named anchor points.
        {"op": "vex_tube_graph", "name": "tube_graph", "from": "tube_cloud",
         "tubes": "$tubes"},
        # PolyWire adds thickness; radius is optional (number or design_param).
        {
            "op": "node", "name": "tube_thickness", "type": "polywire",
            "inputs": {"0": "tube_graph"},
            "params": {"radius": "$radius"},
        },
        {"op": "wire_out", "from": "tube_thickness"},
    ],
}
