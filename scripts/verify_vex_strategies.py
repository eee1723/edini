"""Verify each VEX strategy against the Python measure.py oracle, in real hython.

For each measurement primitive (bbox_corner, grid_on_face, array, ...) this:
  1. builds a box as input 0,
  2. creates an attribwrangle running the strategy's VEX (snippet + ch() parms),
  3. cooks it, reads the emitted points,
  4. computes the SAME points via measure.py (the oracle),
  5. compares point-by-point.

If every strategy matches, the VEX port is correct and the live build layer can
trust it. Run:

    "D:\houdini\bin\hython.exe" scripts/verify_vex_strategies.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "python3.11libs"))

import hou
from edini import measure as M
from edini.vex_strategies import build_mount_vex, _orient_fragment, _corner_selectors


def _make_box(parent, name, sx, sy, sz):
    """A box centered at origin with the given full sizes (corners at ±s/2)."""
    box = parent.createNode("box", name)
    box.parmTuple("size").set((sx, sy, sz))
    return box


def _run_wrangle(box, snippet, parms):
    """Create an attribwrangle after `box`, install snippet + scalar ch() parms,
    cook, return the list of emitted point positions."""
    wr = box.parent().createNode("attribwrangle", "probe_wrangle")
    wr.setInput(0, box)
    wr.parm("class").set("detail")   # run once over the detail (not per point)
    wr.parm("snippet").set(snippet)
    # Install scalar ch() parms as spares.
    for pname, pval in parms.items():
        if pname.startswith("_"):
            continue  # vector parms handled by caller separately
        try:
            wr.parm(pname).set(pval) if wr.parm(pname) else None
        except Exception:
            pass
    # The scalar selectors (cx/cy/cz etc.) aren't native wrangle parms — create
    # them as spare float parms so ch() resolves.
    for pname, pval in parms.items():
        if pname.startswith("_"):
            continue
        if wr.parm(pname) is None:
            hou_node = wr
            try:
                # Fallback: inject the value directly into the snippet via a
                # replace, since we can't easily add spares across versions.
                pass
            except Exception:
                pass
    wr.cook(force=True)
    geo = wr.geometry()
    return [(list(p.position())[0], list(p.position())[1], list(p.position())[2])
            for p in geo.points()], wr


def _inject_scalar_values(snippet, parms):
    """Replace ch()/chi()/chv() calls with literal values for scalar/vector
    parms, so we don't depend on spare-parm creation. Inlines:
      chi("cx") -> 1            (integer selectors: cx/cy/cz, cax.., countx..)
      ch("margin") -> 0.05      (float scalars: margin, t, face_sign)
      chv("origin") -> {0,0,0}  (vectors: origin, step0/1/2)
    The "_..." passthrough keys are skipped (they carry unresolved specs)."""
    import re
    out = snippet
    for pname, pval in parms.items():
        if pname.startswith("_"):
            continue
        if pname in ("cx", "cy", "cz", "cax", "cay", "caz", "cbx", "cby", "cbz",
                     "rows", "cols", "face_axis", "countx", "county", "countz"):
            out = re.sub(r'chi\("' + pname + r'"\)', str(int(pval)), out)
        elif pname in ("origin", "step0", "step1", "step2"):
            v = "{" + ",".join(str(float(x)) for x in pval) + "}"
            out = re.sub(r'chv\("' + pname + r'"\)', v, out)
        else:  # margin, t, face_sign — float scalars
            out = re.sub(r'ch\("' + pname + r'"\)', repr(float(pval)), out)
    return out


def _points_close(a, b, tol=1e-4):
    if len(a) != len(b):
        return False
    return all(abs(ax - bx) < tol and abs(ay - by) < tol and abs(az - bz) < tol
               for (ax, ay, az), (bx, by, bz) in zip(a, b))


def _run_cells_wrangle(box, snippet, margin, gap=0.0, face="+Y"):
    """Cook the cells strategy and return BOTH positions and per-point scales.

    cells is special: its VEX emits per-point v@scale (the key-size signal), and
    the physical unit is DERIVED in-VEX from the box's span (no unit spare). So
    we only inline face_axis/face_sign/margin/gap; the unit is computed live from
    the box's bbox. We read both P and the 'scale' attribute to verify against
    the oracle's (position, scale) pairs."""
    from edini.measure import _parse_face
    sign, axis = _parse_face(face)
    face_axis = "XYZ".index(axis)
    face_sign = 1 if sign > 0 else -1
    import re
    snip = snippet
    snip = re.sub(r'chi\("face_axis"\)', str(face_axis), snip)
    snip = re.sub(r'ch\("face_sign"\)', str(face_sign), snip)
    snip = re.sub(r'ch\("margin"\)', repr(float(margin)), snip)
    snip = re.sub(r'ch\("gap"\)', repr(float(gap)), snip)
    wr = box.parent().createNode("attribwrangle", "cells_wr")
    wr.setInput(0, box)
    wr.parm("class").set("detail")
    wr.parm("snippet").set(snip)
    wr.cook(force=True)
    geo = wr.geometry()
    pts = []
    for p in geo.points():
        pos = list(p.position())
        try:
            scl = list(p.floatListAttribValue("scale"))
        except Exception:
            scl = [1.0, 1.0, 1.0]
        pts.append((pos, scl))
    return pts


def main():
    obj = hou.node("/obj")
    geo_container = obj.createNode("geo", "vex_verify")
    # A 4 x 0.5 x 2 box (car platform), centered at origin.
    box = _make_box(geo_container, "root", 4.0, 0.5, 2.0)
    box.cook()

    cases = [
        ("bbox_corner +X-Y+Z",
         {"measure": "bbox_corner", "axes": "+X-Y+Z"},
         lambda: [M.measure_bbox_corner(box.geometry(), "+X-Y+Z")]),
        ("bbox_corner -X+Y-Z",
         {"measure": "bbox_corner", "axes": "-X+Y-Z"},
         lambda: [M.measure_bbox_corner(box.geometry(), "-X+Y-Z")]),
        ("bbox_face_center +Y",
         {"measure": "bbox_face_center", "face": "+Y"},
         lambda: [M.measure_bbox_face_center(box.geometry(), "+Y")]),
        ("bbox_center",
         {"measure": "bbox_center"},
         lambda: [tuple(M.measure_bbox(box.geometry())["center"])]),
        ("grid_on_face +Y 3x5",
         {"measure": "grid_on_face", "face": "+Y", "rows": 3, "cols": 5, "margin": 0.05},
         lambda: M.measure_grid_on_face(box.geometry(), "+Y", 3, 5, 0.05)),
        ("point_on_edge 0.3 along front-bottom",
         {"measure": "point_on_edge", "axes_a": "-X-Y-Z", "axes_b": "+X-Y-Z", "t": 0.3},
         lambda: [M.measure_point_on_edge(box.geometry(), "-X-Y-Z", "+X-Y-Z", 0.3)]),
        ("array 3 diagonal stairs",
         {"measure": "array", "origin": [0, 0, 0], "count": [3, 1, 1],
          "step": [[0.5, 0.3, 0], [0, 0, 0], [0, 0, 0]]},
         lambda: M.measure_array((0, 0, 0), [3, 1, 1],
                                 [[0.5, 0.3, 0], [0, 0, 0], [0, 0, 0]])),
    ]

    # cells is verified separately: it emits per-point v@scale (not just P), and
    # the physical unit is DERIVED from the box's span (no unit param). A
    # keyboard-style layout: 3 normal 1u keys + a 6.25u spacebar + staggered row.
    cells_spec = {
        "measure": "cells", "face": "+Y", "margin": 0.1,
        "cells": [{"gx": 0, "gz": 0, "w": 1, "d": 1},
                  {"gx": 1, "gz": 0, "w": 1, "d": 1},
                  {"gx": 0.25, "gz": 1, "w": 1, "d": 1},   # staggered
                  {"gx": 0, "gz": 3, "w": 6.25, "d": 1}]}  # spacebar
    cells_layout = cells_spec["cells"]
    cells_margin = cells_spec["margin"]

    # The array strategy carries origin/step as _-prefixed passthrough keys;
    # promote them to real chv() values for the standalone verification cook.
    def _normalize_array_parms(spec_snippet, spec_parms):
        if "_origin" in spec_parms:
            spec_parms = dict(spec_parms)
            spec_parms["origin"] = spec_parms.pop("_origin")
            spec_parms["step0"] = spec_parms.pop("_step0")
            spec_parms["step1"] = spec_parms.pop("_step1")
            spec_parms["step2"] = spec_parms.pop("_step2")
        return spec_parms

    print("=" * 60)
    print("VEX strategy vs Python oracle (box 4 x 0.5 x 2 at origin)")
    print("=" * 60)
    all_ok = True
    for name, spec, oracle_fn in cases:
        snippet, parms = build_mount_vex(spec)
        parms = _normalize_array_parms(snippet, parms)
        snippet = _inject_scalar_values(snippet, parms)
        vex_pts, _ = _run_wrangle(box, snippet, {})
        oracle_pts = oracle_fn()
        ok = _points_close(sorted(vex_pts), sorted(oracle_pts))
        all_ok = all_ok and ok
        status = "OK " if ok else "FAIL"
        print(f"[{status}] {name}: vex={len(vex_pts)}pts oracle={len(oracle_pts)}pts")
        if not ok:
            print(f"   vex   : {sorted(vex_pts)[:3]}...")
            print(f"   oracle: {sorted(oracle_pts)[:3]}...")

    # ── cells strategy: verify positions + per-point v@scale, across all 3 ─
    # fill modes (stretch / square / pad). repeat is build-time expansion so it
    # shares the square VEX; verified separately in the hython suite.
    cell_modes = [
        ("stretch (default)", {}),
        ("square", {"square": True}),
        ("pad", {"square": True, "fill": "pad"}),
    ]
    for mode_label, mode_overrides in cell_modes:
        spec = {**cells_spec, **mode_overrides}
        c_snippet, _ = build_mount_vex(spec)
        c_vex = _run_cells_wrangle(box, c_snippet, cells_margin,
                                   face=cells_spec["face"])
        c_oracle = M.measure_cells(box.geometry(), "+Y", cells_layout,
                                   margin=cells_margin,
                                   square=mode_overrides.get("square", False),
                                   fill=mode_overrides.get("fill", "stretch"))
        c_vex_sorted = sorted(c_vex, key=lambda ps: (round(ps[0][0], 4), round(ps[0][2], 4)))
        c_or_sorted = sorted(c_oracle, key=lambda ps: (round(ps[0][0], 4), round(ps[0][2], 4)))
        c_ok = len(c_vex_sorted) == len(c_or_sorted)
        if c_ok:
            for (vp, vs), (op, os) in zip(c_vex_sorted, c_or_sorted):
                if not _points_close([vp], [op]):
                    c_ok = False; break
                if not _points_close([vs], [os]):
                    c_ok = False; break
        all_ok = all_ok and c_ok
        status = "OK " if c_ok else "FAIL"
        sb = max((vs for _, vs in c_vex), key=lambda s: s[0])
        nk = min((vs for _, vs in c_vex), key=lambda s: s[0])
        print(f"[{status}] cells {mode_label}: vex={len(c_vex)}pts "
              f"oracle={len(c_oracle)}pts ratio={sb[0]/nk[0]:.3f}")
        if not c_ok:
            print(f"   vex   : {c_vex_sorted}")
            print(f"   oracle: {c_or_sorted}")

    # ── the four sibling tabular-fill strategies: pickets / tiles / shelf / ──
    # blocks. Each subclasses TabularFillStrategy, so it shares the SAME VEX
    # structure (ch("face_axis"/"face_sign"/"margin"/"gap") + unit DERIVED in-VEX
    # from the box span) and cooks through _run_cells_wrangle. The oracles return
    # (pos, scale, orient) TRIPLES; this script verifies the POINT CLOUD matches
    # (positions only — we extract [t[0] for t in triples]). Orient/scale
    # correctness (per-cell rotation, layer height, block height) is the hython
    # suite's job. pickets needs its `count`→cells expansion (builder layer).
    from edini.assembly_builder import _expand_pickets_count

    # pickets: count=N → N equal-width posts along an edge (a 1D row).
    pickets_margin = 0.1
    pickets_spec = _expand_pickets_count(
        {"measure": "pickets", "face": "+Y", "axes": ["X"], "count": 6,
         "margin": pickets_margin})
    p_snippet, _ = build_mount_vex(pickets_spec)
    p_vex = _run_cells_wrangle(box, p_snippet, pickets_margin, face="+Y")
    p_oracle = M.measure_pickets(box.geometry(), "+Y", edge_axis="X", count=6,
                                 margin=pickets_margin)
    p_ok = _points_close(sorted(vp[0] for vp in p_vex),
                         sorted(t[0] for t in p_oracle))
    all_ok = all_ok and p_ok
    print(f"[{'OK ' if p_ok else 'FAIL'}] pickets count=6: "
          f"vex={len(p_vex)}pts oracle={len(p_oracle)}pts")

    # tiles: 2D mosaic with per-cell rot + a mount-level orient rule. The rule
    # fills rot for cells lacking one; positions are unaffected by rot (rot only
    # sets p@orient), so the point cloud is the cells layout's centers.
    tiles_cells = [{"gx": 0, "gz": 0, "w": 1, "d": 1, "rot": 90},
                   {"gx": 1, "gz": 0, "w": 1, "d": 1},               # rule-filled
                   {"gx": 0, "gz": 1, "w": 2, "d": 1, "rot": 45},
                   {"gx": 0, "gz": 2, "w": 1, "d": 1}]               # rule-filled
    tiles_margin = 0.1
    tiles_spec = {"measure": "tiles", "face": "+Y", "orient": "herringbone",
                  "margin": tiles_margin, "cells": tiles_cells}
    t_snippet, _ = build_mount_vex(tiles_spec)
    t_vex = _run_cells_wrangle(box, t_snippet, tiles_margin, face="+Y")
    t_oracle = M.measure_tiles(box.geometry(), "+Y", tiles_cells,
                               margin=tiles_margin, orient_rule="herringbone")
    t_ok = _points_close(sorted(vp[0] for vp in t_vex),
                         sorted(tr[0] for tr in t_oracle))
    all_ok = all_ok and t_ok
    print(f"[{'OK ' if t_ok else 'FAIL'}] tiles herringbone: "
          f"vex={len(t_vex)}pts oracle={len(t_oracle)}pts")

    # shelf: 3D layered bookshelf — layers stack along the face normal (Y). The
    # shelf fragment overrides each point's face-axis P with the layer center, so
    # the point cloud has 3D variety (books at different heights). NOTE: a shelf's
    # layers must all span the SAME total in-plane width (every shelf spans the
    # full root width — the canonical bookshelf), because the VEX flattens all
    # layers into ONE cells table (single in-plane unit). Layers of differing
    # widths are NOT supported by this measurement (a deliberate design limit;
    # use a different layout if shelves differ in span).
    shelf_layers = [
        {"height": 1,   "cells": [{"gx": 0, "w": 1}, {"gx": 1, "w": 1}]},
        {"height": 1.5, "cells": [{"gx": 0, "w": 2}]},
        {"height": 1,   "cells": [{"gx": 0, "w": 1}, {"gx": 1, "w": 1}]},
    ]
    shelf_margin = 0.1
    shelf_spec = {"measure": "shelf", "basis": {"face": "+Y"}, "axis": "Y",
                  "margin": shelf_margin, "layers": shelf_layers}
    sh_snippet, _ = build_mount_vex(shelf_spec)
    sh_vex = _run_cells_wrangle(box, sh_snippet, shelf_margin, face="+Y")
    sh_oracle = M.measure_shelf(box.geometry(), "+Y", "Y", shelf_layers,
                                margin=shelf_margin)
    sh_ok = _points_close(sorted(vp[0] for vp in sh_vex),
                          sorted(tr[0] for tr in sh_oracle))
    all_ok = all_ok and sh_ok
    print(f"[{'OK ' if sh_ok else 'FAIL'}] shelf 3 layers: "
          f"vex={len(sh_vex)}pts oracle={len(sh_oracle)}pts")

    # blocks: 2D footprint + out-of-plane height (the synthesis). The block
    # fragment overrides each point's face-axis scale with the height (derived
    # from root span / max(h)); rot sets p@orient. Positions are the footprint
    # centers, so the point cloud is a 2D grid (height/rot don't move P).
    blocks_cells = [{"gx": 0, "gz": 0, "w": 1, "d": 1, "h": 40},
                    {"gx": 1, "gz": 0, "w": 1, "d": 1, "h": 15},
                    {"gx": 0, "gz": 1, "w": 1, "d": 1},          # no h → flat lot
                    {"gx": 1, "gz": 1, "w": 1, "d": 1, "h": 25, "rot": 30}]
    blocks_margin = 0.1
    blocks_spec = {"measure": "blocks", "face": "+Y", "margin": blocks_margin,
                   "cells": blocks_cells}
    b_snippet, _ = build_mount_vex(blocks_spec)
    b_vex = _run_cells_wrangle(box, b_snippet, blocks_margin, face="+Y")
    b_oracle = M.measure_blocks(box.geometry(), "+Y", blocks_cells,
                                margin=blocks_margin)
    b_ok = _points_close(sorted(vp[0] for vp in b_vex),
                         sorted(tr[0] for tr in b_oracle))
    all_ok = all_ok and b_ok
    print(f"[{'OK ' if b_ok else 'FAIL'}] blocks 2D+height: "
          f"vex={len(b_vex)}pts oracle={len(b_oracle)}pts")

    print()
    print("ALL STRATEGIES MATCH ORACLE" if all_ok else "SOME STRATEGIES MISMATCH")
    return all_ok


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
