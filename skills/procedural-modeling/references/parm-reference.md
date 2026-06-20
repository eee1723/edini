# Houdini 21 SOP Parameter Reference

Node parameter names differ from older versions. **The authoritative source is `query_parms(type)`** — the tables below are a quick reference only and can go stale; always verify against the tool before writing a recipe.

The build harness also hard-validates `postprocess` parm names against a catalogue generated against the real Houdini install, so a guessed name is a build-time error, not a silent miss.

### Line SOP
| Purpose | Parm name | Type |
|---------|-----------|------|
| Origin X/Y/Z | `originx`, `originy`, `originz` | float |
| Direction X/Y/Z | `dirx`, `diry`, `dirz` | float |
| Length | `dist` | float |
| Num points | `points` | int |

### Circle SOP
| Purpose | Parm name | Type |
|---------|-----------|------|
| Primitive type | `type` | int (1=Polygon) |
| Radius X/Y | `radx`, `rady` | float |
| Divisions | `divs` | int |

### PolyBevel SOP
| Purpose | Parm name | Type |
|---------|-----------|------|
| Bevel offset | `offset` | float (NOT `bevel`) |
| Divisions | `divisions` | int (NOT `iterations`) |

### Subdivide SOP
| Purpose | Parm name | Type |
|---------|-----------|------|
| Iterations | `iterations` | int (NOT `depth`) |

### Transform SOP (xform)
| Purpose | Parm name |
|---------|-----------|
| Translate | `tx`, `ty`, `tz` |
| Rotate | `rx`, `ry`, `rz` |
| Scale | `sx`, `sy`, `sz` |

### PolyExtrude SOP
| Purpose | Parm name |
|---------|-----------|
| Distance | `dist` |
| Output front | `outputfront` (1=front faces only) |

### Attrib Promote SOP (high-misguess node)
Older tutorials say `original`/`newname`. H21 uses these:
| Purpose | Parm name | Type / menu |
|---------|-----------|------|
| Source attrib name | `inname` | string (NOT `original`) |
| Output attrib name | `outname` | string |
| Source class | `inclass` | menu: `point`/`prim`/`vertex`/`detail` |
| Output class | `outclass` | menu: `point`/`prim`/`vertex`/`detail` |
| Promotion mode | `method` | menu: `min`/`max`/`sum`/`average`/`mode` |

### Blast SOP
| Purpose | Parm name | Type / menu |
|---------|-----------|------|
| Group to act on | `group` | string |
| Group type | `grouptype` | menu: `guess`/`prims`/`points`/`edges`/`breakpoints` (NOT a bool/int — use the menu word, e.g. `prims`) |
| Delete non-selected | `negate` | bool (1 = keep group, delete rest) |
| Delete entities | `dodelete`/`delpts` etc. | use defaults unless changing behaviour |

### ForEach (Begin/End) — prefer Sweep+Copy-to-Points when possible
The block_end owns the structural parms; the block_begin only reads them via `blockpath`:
| Purpose | Parm name | Which node | Type / menu |
|---------|-----------|------------|------|
| Method | `method` | **block_end** (the begin reads it) | menu: `count`/`foreachpiece`/`forloopwithmetadata` |
| Iterations | `iterations` | block_end | int |
| Piece attribute | `pieceattrib` | block_end | string (e.g. `component_id`) |
| Block path | `blockpath` | **block_begin** | must point at the block_end node (auto-wired when created together; if "Invalid sop specified", it's unwired) |
| Class | `class` | block_end | menu (NOT block_begin) |

Gotcha: if you create block_begin and block_end separately, `blockpath` is empty → "Invalid sop specified". Either let Houdini create the pair (create the `foreach` HDA, which wires them), or set `begin.parm("blockpath").set(end.path())`. **For tube/frame generation, prefer Sweep 2.0 — no blockpath bookkeeping.**

### Sweep SOP (2.0 — preferred for tubes/frames)
| Purpose | Parm name | Type / menu |
|---------|-----------|------|
| Curve to sweep along (spine) | input 0 | — |
| Cross-section (profile) | input 1 | — |
| Surface shape | `surface` | menu: `raildim`/`ribbon`/`tube` (use `tube` for round tubes) |
| Scale along curve | `scale` | float |
| Roll | `roll` | float (degrees) |
| Output polygon | `outputpoly` | bool |

### Copy-to-Points (2.0)
| Purpose | Parm name | Type / menu |
|---------|-----------|------|
| Source group | `sourcegrp` | string |
| Target group (points) | `targetgrp` | string or attr expr `@component_id==wheel` |
| Pack geometry | `pack` | bool (1 = packed primitives) |
| Use @orient/@pscale/@N+@up | (automatic) | these point attrs drive transform, no parm needed |

### Merge SOP
No parms. Just `merge.setInput(0, a); merge.setInput(1, b); ...` (up to ~50 inputs).

### Normal SOP
> Parm names below may be version-specific — **verify with `query_parms("normal")`** before writing a recipe.
| Purpose | Parm name | Type / menu |
|---------|-----------|------|
| Cusp angle | `cuspangle` | float (degrees, 0-180) |
| Add normals to | `type` | menu: `typepoint`/`typevertex`/`typeprim`/`typedetail` |

### Boolean SOP (2.0)
| Purpose | Parm name | Type / menu |
|---------|-----------|------|
| Operation (subtract/union/intersect) | `subtract`/`union`/`intersect` | bool flags (set the one you want to 1) |

### Fallback probe (only if `query_parms` is unavailable)
```python
n = container.createNode("nodetype", "_probe")
for p in n.parms():
    print(f"{p.name()} = {p.eval()}")
n.destroy()
```
