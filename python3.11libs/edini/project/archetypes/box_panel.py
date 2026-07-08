"""Archetype spec: ``box_panel`` — a parametric box (tabletop / seat / panel).

A SPEC is DATA (a dict), realized by :mod:`edini.project.archetype_emitter`.
The emitter's op vocabulary does the building; this module only declares WHAT
to build. Adding a new archetype = adding a module like this one.

``box_panel`` maps the agent's ``size: [x, y, z]`` (each entry a NUMBER literal
or a design_param NAME → a live relative ``ch()`` ref, migratable across
projects) onto the box's ``sizex`` / ``sizey`` / ``sizez``, wires the box to
``out_geometry``, and optionally forwards ``markers`` to :func:`emit_markers`
so a downstream ``by_name`` anchor can pick precise assembly points.

This is the Phase 2a migration of ``builder._archetype_box_panel`` — same
behavior (parametric + LIVE + idempotent rebuild + marker forwarding), now
data-driven.
"""

SPEC = {
    "archetype": "box_panel",
    "description": "A parametric box (tabletop/seat/panel).",
    # Agent params merged over these defaults (agent wins).
    "defaults": {"size": [1, 1, 1]},
    # Loud-fail param validation (restores the old _archetype_box_panel guard:
    # size must be a 3-list of numbers or design_param names).
    "param_specs": {
        "size": {"type": "list", "len": 3, "item": "number_or_name"},
        "markers": {"type": "list", "required": False},
    },
    "ops": [
        # `$size.0` / `$size.1` / `$size.2` resolve to params['size'][0..2].
        # Each is a number (literal) or a design_param name (→ relative ch()
        # via _set_archetype_parm → _relative_path_to_core, Phase 1a).
        {
            "op": "node",
            "name": "panel_box",
            "type": "box",
            "params": {
                "sizex": "$size.0",
                "sizey": "$size.1",
                "sizez": "$size.2",
            },
        },
        # Wire the box into the component's out_geometry (→ output_0 / OUT).
        {"op": "wire_out", "from": "panel_box"},
        # Optional: forward markers to emit_markers. `$markers` resolves to
        # params['markers']; absent → None → this op is a no-op.
        {"op": "emit_markers", "markers": "$markers"},
    ],
}
