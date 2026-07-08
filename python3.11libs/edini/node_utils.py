"""edini.node_utils - re-export shim (Phase 4 split).

Historically a single ~4600-line module. Split by responsibility into:

    node_ops         - node CRUD, scene queries, script exec, capture/screenshot
    manifest         - parm-template manifest generation / load / query
    geometry_inspect - geometry read + health inspection
    verify           - orientation/parametric/robust verification + project gates

This file re-exports the union of all four so every existing import -
``from edini.node_utils import X`` - including the private (underscore) helpers
that builder.py, archetype_emitter.py, and the test suite import by name -
keeps working unchanged. Behaviour is identical to the pre-split module.
"""
from __future__ import annotations

from .node_ops import *          # noqa: F401,F403
from .manifest import *          # noqa: F401,F403
from .geometry_inspect import *  # noqa: F401,F403
from .verify import *            # noqa: F401,F403

# ``from x import *`` deliberately skips underscore-prefixed names, but the
# codebase imports many private helpers from here (e.g. ``_apply_one_param``,
# ``_relative_path_to_core``, ``_CH_CALL_RE``, ``_frame_to_bounds``,
# ``_HEALTH_BLOCKING_CHECKS``). Mirror the full private surface of the four
# submodules so those imports still resolve.
import sys as _sys
from . import node_ops as _node_ops, manifest as _manifest
from . import geometry_inspect as _geometry_inspect, verify as _verify

_shim = _sys.modules[__name__]
for _sub in (_node_ops, _manifest, _geometry_inspect, _verify):
    for _name in dir(_sub):
        if _name.startswith("_") and not _name.startswith("__") \
                and not hasattr(_shim, _name):
            setattr(_shim, _name, getattr(_sub, _name))
del _sys, _shim, _sub, _name
del _node_ops, _manifest, _geometry_inspect, _verify
