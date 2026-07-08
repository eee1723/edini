"""Archetype spec package.

Each module here defines a ``SPEC`` dict — a declarative description of one
archetype's geometry as an ordered list of ``ops`` from a fixed vocabulary
(see ``edini.project.archetype_emitter``). A spec is DATA, not code: adding an
archetype = adding a module here, with ZERO emitter changes.

Phase 2a ships ``box_panel`` (migrating the hardcoded ``_archetype_box_panel``).
Phase 2b adds ``copy_array`` + ``tube_graph`` (retiring the last hardcoded
archetype functions) + ``extrude_profile`` (greenfield).
"""
