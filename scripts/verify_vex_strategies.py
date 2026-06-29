"""Verify each VEX strategy against the Python measure.py oracle, in real hython.

For each measurement primitive (bbox_corner, grid_on_face, array, ...) this:
  1. builds a box as input 0,
  2. creates an attribwrangle running the strategy's VEX (snippet + ch() parms),
  3. cooks it, reads the emitted points,
  4. computes the SAME points via measure.py (the oracle),
  5. compares point-by-point.

If every strategy matches, the VEX port is correct and the live build layer can
trust it. Run:

    D:/houdini/bin/hython.exe scripts/verify_vex_strategies.py
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

    print()
    print("ALL STRATEGIES MATCH ORACLE" if all_ok else "SOME STRATEGIES MISMATCH")
    return all_ok


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
