"""Archetype spec: ``copy_array`` — stamp a leaf shape onto consumed anchor
points (legs / spokes / keys).

The classic "array" component: declare ``ports.in`` consuming an upstream
component's anchors; this archetype builds the leaf once and Copy-to-Points
stamps it at every consumed anchor point. CTP reads ``@orient``/``@scale``/
``@N`` on the anchor points (via ``init_ctp_attribs``) so a leaf can be
oriented/scaled per-anchor when the upstream emitted those attribs.

Phase 2b migration of ``builder._archetype_copy_array`` — same behavior, now
data-driven.
"""

SPEC = {
    "archetype": "copy_array",
    "description": ("Stamp a leaf shape onto the component's consumed anchor "
                    "points (legs/spokes/keys)."),
    "param_specs": {
        # leaf = {type: 'box'|'tube'|..., params: {parm: number|design_param_name}}
        "leaf": {"type": "dict", "required": True},
    },
    "ops": [
        # Build the leaf once. $leaf.type / $leaf.params come from the agent's
        # {leaf: {type, params}}. The tube→Polygon tweak fires only for tube
        # leaves the agent didn't already set 'type' on (H21's default is
        # Primitive → a degenerate single prim).
        {
            "op": "node", "name": "array_leaf", "type": "$leaf.type",
            "params": "$leaf.params",
            "tweaks": [{"when_type": "tube", "set_if_unset": {"type": 1}}],
        },
        # Collect the consumed anchor points (scaffold's in_<from>_<anchor>
        # nulls) into one cloud.
        {"op": "collect_anchors", "as": "array_cloud"},
        # CTP the leaf onto the cloud; read per-anchor orient/scale/N.
        {
            "op": "node", "name": "array_ctp", "type": "copytopoints",
            "inputs": {"0": "array_leaf", "1": "array_cloud"},
            "init_ctp_attribs": True,
        },
        {"op": "wire_out", "from": "array_ctp"},
    ],
}
